import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.trend_priority import PriorityBreakdown, SavedTrendSnapshot, calculate_priority

T0 = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


def test_high_velocity_niche_aligned_gets_high_priority():
    published = T0 - timedelta(hours=24)
    # 240.000 views em 24h = 10.000 views/h; mediana do nicho = 50.000 (ratio = 4.8x)
    bd = calculate_priority(
        views=240_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=["Vídeo Antigo de Culinária"],
        title="O Segredo do Satélite Soviético",
        now=T0,
    )
    assert bd.total_score >= 80
    assert bd.risk_level == "ok"
    assert bd.is_evergreen is False
    assert bd.velocity_score >= 90
    assert bd.niche_ratio_score >= 90


def test_repetitive_title_triggers_warning():
    published = T0 - timedelta(hours=48)
    recent = [
        "Satélite soviético misterioso",
        "Outro satélite da guerra fria",
        "Mais um mistério soviético",
    ]
    bd = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=recent,
        title="O que a NASA encontrou no satélite soviético",
        now=T0,
    )
    assert bd.variety_score <= 40
    assert "repetição" in bd.risk_status.lower() or bd.risk_level == "warn"


def test_evergreen_classification():
    published = T0 - timedelta(days=200)
    bd = calculate_priority(
        views=500_000,
        published_at=published,
        niche_median_views=100_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Buracos misteriosos na Amazônia",
        now=T0,
    )
    assert bd.is_evergreen is True


def test_not_evergreen_if_under_180_days():
    published = T0 - timedelta(days=100)
    bd = calculate_priority(
        views=500_000,
        published_at=published,
        niche_median_views=100_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Buracos misteriosos na Amazônia",
        now=T0,
    )
    assert bd.is_evergreen is False


def test_not_evergreen_if_low_views():
    published = T0 - timedelta(days=200)
    bd = calculate_priority(
        views=50_000,
        published_at=published,
        niche_median_views=100_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Buracos misteriosos na Amazônia",
        now=T0,
    )
    assert bd.is_evergreen is False


def test_monetization_risk_detection_and_penalty():
    published = T0 - timedelta(hours=24)
    # Título seguro
    bd_safe = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="O Segredo das Pirâmides do Egito",
        now=T0,
    )
    # Título com termo sensível (violência / armas)
    bd_risk = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Massacre e tiroteio com armas de fogo ilegais",
        now=T0,
    )
    assert bd_risk.risk_level == "danger"
    assert "monetização" in bd_risk.risk_status.lower()
    # Penalidade de 30 pontos aplicada
    assert bd_risk.total_score <= bd_safe.total_score - 25


def test_execucao_disambiguation_benign_vs_danger():
    published = T0 - timedelta(hours=24)
    # Frase benigna com "execução" não deve acionar risco de desmonetização
    bd_benign = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Como fazer a execução de projeto com perfeição",
        now=T0,
    )
    assert bd_benign.risk_level == "ok"
    assert bd_benign.risk_status == "Sem risco detectado"

    # Frase com execução sumária deve acionar risco
    bd_danger = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Caso de execução sumária na cidade",
        now=T0,
    )
    assert bd_danger.risk_level == "danger"
    assert "monetização" in bd_danger.risk_status.lower()


def test_zero_and_edge_cases_no_zerodivision():
    bd = calculate_priority(
        views=0,
        published_at=None,
        niche_median_views=0.0,
        is_trending_chart=True,
        has_category=False,
        recent_channel_titles=[],
        title="",
        now=T0,
    )
    assert 0 <= bd.total_score <= 100
    assert bd.velocity_score == 0
    assert bd.competition_score == 50  # Trending chart = 50 neutro
    assert bd.is_evergreen is False
    assert bd.risk_level in ("ok", "warn", "danger")


def test_published_at_naive_datetime():
    published_naive = datetime(2026, 11, 22, 12)  # naive
    bd = calculate_priority(
        views=10_000,
        published_at=published_naive,
        niche_median_views=5_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Mistérios do Oceano Profundo",
        now=T0,
    )
    assert bd.total_score > 0


def test_saved_trend_snapshot_dataclass():
    snap = SavedTrendSnapshot(
        project_id="proj_1",
        video_id="vid_123",
        title="Ideia Salva no Canal",
        channel_title="Canal X",
        thumbnail_url="https://i.ytimg.com/vi/vid_123/hqdefault.jpg",
        video_url="https://youtube.com/watch?v=vid_123",
        duration="11:40",
        views=1_400_000,
        category_name="Mistérios",
        score=86,
    )
    assert snap.project_id == "proj_1"
    assert snap.video_id == "vid_123"
    assert snap.score == 86
    assert snap.created_at is None
