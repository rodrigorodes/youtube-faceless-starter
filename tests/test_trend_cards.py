import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.panel import BuildPanel, TrendItemView  # noqa: E402
from app.studio.application.ports import TrendRecord  # noqa: E402
from app.studio.domain.trend_cards import SEARCH_SOURCE, TrendCard, build_trend_cards  # noqa: E402
from app.studio.domain.trend_priority import PriorityBreakdown, SavedTrendSnapshot  # noqa: E402

T0 = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)


@dataclass
class Rec:
    topic: str
    source_name: str
    observed_at: datetime
    evidence: list = field(default_factory=list)
    metric_value: float | None = None
    source_url: str = "https://www.youtube.com/feed/trending"
    category_id: str | None = None


def ev(vid, channel, views, title="Título"):
    return {"title": f"{title} {vid}", "url": f"https://youtube.com/watch?v={vid}", "channel": channel, "views": views}


def popular(vid, channel, views, at=T0):
    return Rec(f"Título {vid}", "YouTube Brasil (Em Alta)", at, [ev(vid, channel, views)], float(views))


def test_the_same_video_collected_many_times_appears_once_with_the_latest_collection():
    records = [popular("aaaaaaaaaaa", "Canal A", 100, T0 + timedelta(hours=h)) for h in range(5)]
    records[-1].metric_value = 999.0
    cards = build_trend_cards(records)
    assert len(cards) == 1 and cards[0].metric_value == 999.0 and cards[0].observed_at == T0 + timedelta(hours=4)


def test_a_search_row_becomes_one_card_per_video_with_the_term_kept():
    row = Rec("Tchami", SEARCH_SOURCE, T0, [ev("v1111111111", "A", 10), ev("v2222222222", "B", 30), ev("v3333333333", "C", 20)],
              60.0, "https://www.googleapis.com/youtube/v3/search")
    cards = build_trend_cards([row])
    assert [c.topic for c in cards] == ["Título v2222222222", "Título v3333333333", "Título v1111111111"]  # por visualizações
    assert {c.query for c in cards} == {"Tchami"}
    assert [c.metric_value for c in cards] == [30.0, 20.0, 10.0]  # a métrica é a do vídeo, não a soma do termo


def test_one_channel_takes_at_most_two_cards_keeping_the_most_viewed():
    records = [popular(f"vid{n:08d}", "Mega Canal", 1000 - n) for n in range(5)] + [popular("outro0000000", "Pequeno", 1)]
    cards = build_trend_cards(records)
    assert [c.channel for c in cards] == ["Mega Canal", "Mega Canal", "Pequeno"]
    assert [c.metric_value for c in cards[:2]] == [1000.0, 999.0]


def test_the_channel_cap_is_case_insensitive_and_unknown_channels_are_not_capped():
    cards = build_trend_cards([popular("a0000000001", "Canal X", 5), popular("a0000000002", "canal x", 4), popular("a0000000003", "CANAL X", 3)]
                              + [popular(f"s{n:010d}", "", 2) for n in range(4)])
    assert sum(1 for c in cards if c.channel.lower() == "canal x") == 2
    assert sum(1 for c in cards if not c.channel) == 4


def test_the_same_video_from_search_and_trending_is_one_card():
    row = Rec("Tchami", SEARCH_SOURCE, T0 + timedelta(hours=1), [ev("same0000001", "A", 10)], 10.0)
    assert len(build_trend_cards([popular("same0000001", "A", 10), row])) == 1


def test_other_sources_keep_one_card_per_record():
    rec = Rec("Tema do n8n", "Fonte externa", T0, [ev("x0000000001", "A", 1), ev("x0000000002", "B", 2)], 3.0)
    cards = build_trend_cards([rec])
    assert len(cards) == 1 and cards[0].topic == "Tema do n8n" and len(cards[0].evidence) == 1


def test_per_channel_zero_disables_the_cap():
    assert len(build_trend_cards([popular(f"vid{n:08d}", "Mesmo", 10 - n) for n in range(4)], per_channel=0)) == 4


def test_trend_cards_contain_velocity_and_priority_score():
    records = [popular("v1", "Canal 1", 500_000, T0 - timedelta(hours=10))]
    cards = build_trend_cards(records, now=T0)
    assert hasattr(cards[0], "priority_score")
    assert hasattr(cards[0], "velocity_text")
    assert hasattr(cards[0], "duration_text")
    assert cards[0].priority_score > 0
    assert cards[0].velocity_text == "50 mil/h"


def test_trend_cards_duration_and_niche_ratio():
    ev1 = ev("v1", "C1", 100_000)
    ev1["duration"] = "11:40"
    ev2 = ev("v2", "C2", 340_000)
    ev2["duration"] = "05:20"
    records = [
        Rec("T1", SEARCH_SOURCE, T0, [ev1], 100_000.0, category_id="cat1"),
        Rec("T2", SEARCH_SOURCE, T0, [ev2], 340_000.0, category_id="cat1"),
    ]
    cards = build_trend_cards(records, now=T0)
    assert hasattr(cards[0], "niche_ratio_text")
    assert hasattr(cards[0], "duration_text")
    assert any(c.duration_text == "11:40" for c in cards)
    assert any(c.duration_text == "05:20" for c in cards)
    assert any("▲" in c.niche_ratio_text or "▼" in c.niche_ratio_text for c in cards)


def test_trend_cards_defensive_duration_s():
    ev_invalid = ev("v_inv", "C1", 100_000)
    ev_invalid["duration_s"] = "not_a_number"
    ev_str = ev("v_str", "C2", 100_000)
    ev_str["duration_s"] = "125"  # 02:05
    ev_int = ev("v_int", "C3", 100_000)
    ev_int["duration_s"] = 3661  # 01:01:01

    records = [
        Rec("T_inv", SEARCH_SOURCE, T0, [ev_invalid], 100_000.0),
        Rec("T_str", SEARCH_SOURCE, T0, [ev_str], 100_000.0),
        Rec("T_int", SEARCH_SOURCE, T0, [ev_int], 100_000.0),
    ]
    cards = build_trend_cards(records, now=T0)
    card_map = {c.evidence[0]["url"].split("=")[-1]: c for c in cards}
    assert card_map["v_inv"].duration_text == ""
    assert card_map["v_str"].duration_text == "02:05"
    assert card_map["v_int"].duration_text == "01:01:01"


class FakeTrendRepo:
    def __init__(self, records=None, last_collected=None, saved_trends=None):
        self._records = records or []
        self._last_collected = last_collected
        self._saved_trends = saved_trends or []

    def list(self, project_id, since=None):
        if since is None:
            return self._records
        return [r for r in self._records if r.observed_at >= since]

    def last_collected_at(self, project_id):
        return self._last_collected

    def find_by_topic_key(self, project_id, topic_key):
        for r in self._records:
            if getattr(r, "project_id", None) == project_id and getattr(r, "topic_key", None) == topic_key:
                return r
        return None

    def list_saved_trends(self, project_id):
        return [s for s in self._saved_trends if s.project_id == project_id]

    def is_trend_saved(self, project_id, video_id):
        return any(s.project_id == project_id and s.video_id == video_id for s in self._saved_trends)


class FakePanelRepo:
    def __init__(self, projects_list=None, videos_list=None, month_rows=None):
        self._projects = projects_list or [("p1", "Canal Principal")]
        self._videos = videos_list or []
        self._month_rows = month_rows or []

    def projects(self):
        return self._projects

    def videos(self, since, project_id, limit):
        res = self._videos
        if since:
            res = [v for v in res if v.updated_at >= since]
        if project_id:
            res = [v for v in res if v.project_id == project_id]
        return res[:limit]

    def month_usage(self):
        return self._month_rows

    def unattributed_usage(self):
        return []


def test_build_panel_enriches_trend_item_views_with_metrics_and_saved_state():
    now = T0
    ev1 = ev("v1", "Canal 1", 500_000)
    ev1["duration"] = "11:40"
    ev1["published_at"] = (now - timedelta(hours=10)).isoformat()

    rec = Rec("Tema Tendencia", "YouTube Brasil (Em Alta)", now, [ev1], 500_000.0)
    saved = SavedTrendSnapshot(
        project_id="p1",
        video_id="v1",
        title="Tema Tendencia",
        channel_title="Canal 1",
        thumbnail_url="https://i.ytimg.com/vi/v1/hqdefault.jpg",
        video_url="https://youtube.com/watch?v=v1",
        duration="11:40",
        views=500_000,
        category_name=None,
        score=85,
        created_at=now,
    )
    trend_repo = FakeTrendRepo(records=[rec], last_collected=now, saved_trends=[saved])
    panel_repo = FakePanelRepo()

    view = BuildPanel(panel_repo, 15.0, lambda: now, trends=trend_repo).execute(days=7, project_id="p1")
    assert len(view.trends) == 1
    t = view.trends[0]

    assert hasattr(t, "velocity_text")
    assert hasattr(t, "niche_ratio_text")
    assert hasattr(t, "duration_text")
    assert hasattr(t, "priority_score")
    assert hasattr(t, "priority_summary")
    assert hasattr(t, "priority_breakdown")
    assert hasattr(t, "risk_status")
    assert hasattr(t, "risk_level")
    assert hasattr(t, "is_saved")
    assert hasattr(t, "is_evergreen")

    assert t.duration_text == "11:40"
    assert t.velocity_text == "50 mil/h"
    assert t.is_saved is True
    assert t.priority_score > 0
    assert isinstance(t.priority_breakdown, PriorityBreakdown)


def test_build_panel_sorting_options():
    now = T0
    # Fast: 200k in 2h = 100k/h
    ev_fast = ev("v_fast", "Canal A", 200_000)
    ev_fast["published_at"] = (now - timedelta(hours=2)).isoformat()
    rec_fast = Rec("Tema Rapido", "YouTube Brasil (Em Alta)", now, [ev_fast], 200_000.0)

    # Slow: 100k in 100h = 1k/h, but observed more recently
    ev_slow = ev("v_slow", "Canal B", 100_000)
    ev_slow["published_at"] = (now - timedelta(hours=100)).isoformat()
    rec_slow = Rec("Tema Lento", "YouTube Brasil (Em Alta)", now + timedelta(minutes=5), [ev_slow], 100_000.0)

    trend_repo = FakeTrendRepo(records=[rec_fast, rec_slow], last_collected=now)
    panel = BuildPanel(FakePanelRepo(), 15.0, lambda: now, trends=trend_repo)

    # Sort by prioridade
    view_prio = panel.execute(days=7, sort="prioridade")
    assert view_prio.sort == "prioridade"
    assert len(view_prio.trends) == 2

    # Sort by velocidade
    view_vel = panel.execute(days=7, sort="velocidade")
    assert view_vel.sort == "velocidade"
    assert view_vel.trends[0].topic == "Tema Rapido"

    # Sort by recentes
    view_rec = panel.execute(days=7, sort="recentes")
    assert view_rec.sort == "recentes"
    assert view_rec.trends[0].topic == "Tema Lento"


def test_build_panel_tipo_filtering_and_saved_trends_outside_7_day_window():
    now = T0
    # Current trend
    ev_now = ev("v_now", "Canal X", 50_000)
    rec_now = Rec("Tema Atual", "YouTube Brasil (Em Alta)", now, [ev_now], 50_000.0)

    # Saved trend from 30 days ago (outside 7-day window)
    old_date = now - timedelta(days=30)
    saved_old = SavedTrendSnapshot(
        project_id="p1",
        video_id="v_old",
        title="Ideia Antiga Guardada",
        channel_title="Canal Y",
        thumbnail_url="https://i.ytimg.com/vi/v_old/hqdefault.jpg",
        video_url="https://youtube.com/watch?v=v_old",
        duration="15:00",
        views=300_000,
        category_name="Geral",
        score=90,
        created_at=old_date,
    )

    trend_repo = FakeTrendRepo(records=[rec_now], last_collected=now, saved_trends=[saved_old])
    panel = BuildPanel(FakePanelRepo(), 15.0, lambda: now, trends=trend_repo)

    # tipo == "todos" -> only current collected trends
    view_all = panel.execute(days=7, project_id="p1", tipo="todos")
    assert len(view_all.trends) == 1
    assert view_all.trends[0].topic == "Tema Atual"

    # tipo == "guardados" -> loads saved trend even outside 7-day window
    view_saved = panel.execute(days=7, project_id="p1", tipo="guardados")
    assert view_saved.tipo == "guardados"
    assert len(view_saved.trends) == 1
    assert view_saved.trends[0].video_id == "v_old"
    assert view_saved.trends[0].is_saved is True
    assert view_saved.trends[0].duration_text == "15:00"
    assert view_saved.trends[0].priority_score == 90


def test_build_panel_tipo_perenes_and_sem_risco():
    now = T0
    # 1. Perene: > 180 dias e >= 100.000 views, título seguro
    ev_perene = ev("v_perene", "Canal Perene", 250_000, title="Tema Perene Consolidado")
    ev_perene["published_at"] = (now - timedelta(days=200)).isoformat()
    rec_perene = Rec("Tema Perene Consolidado", "YouTube Brasil (Em Alta)", now, [ev_perene], 250_000.0)

    # 2. Risco alto (danger): título com palavra de risco de monetização
    ev_danger = ev("v_danger", "Canal Polêmico", 80_000, title="Massacre e tiroteio na fronteira")
    ev_danger["published_at"] = (now - timedelta(days=1)).isoformat()
    rec_danger = Rec("Massacre e tiroteio na fronteira", "YouTube Brasil (Em Alta)", now, [ev_danger], 80_000.0)

    # 3. Recente e seguro: < 180 dias, sem risco
    ev_safe = ev("v_safe", "Canal Seguro", 40_000, title="Tema Recente e Seguro")
    ev_safe["published_at"] = (now - timedelta(days=2)).isoformat()
    rec_safe = Rec("Tema Recente e Seguro", "YouTube Brasil (Em Alta)", now, [ev_safe], 40_000.0)

    trend_repo = FakeTrendRepo(records=[rec_perene, rec_danger, rec_safe], last_collected=now)
    panel = BuildPanel(FakePanelRepo(), 15.0, lambda: now, trends=trend_repo)

    # tipo == "perenes" -> apenas os vídeos com is_evergreen == True
    view_perenes = panel.execute(days=7, project_id="p1", tipo="perenes")
    assert view_perenes.tipo == "perenes"
    assert len(view_perenes.trends) == 1
    assert view_perenes.trends[0].topic == "Tema Perene Consolidado"
    assert view_perenes.trends[0].is_evergreen is True

    # tipo == "sem_risco" -> apenas os vídeos com risk_level == "ok"
    view_sem_risco = panel.execute(days=7, project_id="p1", tipo="sem_risco")
    assert view_sem_risco.tipo == "sem_risco"
    assert len(view_sem_risco.trends) == 2
    assert all(t.risk_level == "ok" for t in view_sem_risco.trends)
    assert not any("Massacre" in t.topic for t in view_sem_risco.trends)


