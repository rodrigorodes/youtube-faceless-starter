"""UX V3: o Início segue a proposta aprovada (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).

Cada asserção cita o que o protótipo mostra. Dado é sempre o real; ausência vira texto explícito.
"""
import re
from datetime import datetime, timedelta, timezone

from test_panel import FakePanelRepo, FakeTrendRepo, _row, _visible_text
from app.studio.application.panel import BuildPanel
from app.studio.application.ports import TrendRecord
from app.studio.domain.contracts import VideoStatus

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def _home(videos=None, trends=None, topic="", days=7):
    from app.studio.api.panel import render_panel

    repo = FakePanelRepo(videos_list=videos or [])
    trend_repo = FakeTrendRepo(records=trends or [], last_collected=NOW if trends else None)
    view = BuildPanel(repo, 15.0, lambda: NOW, trends=trend_repo).execute(days=days)
    return render_panel(view, topic=topic)[0]


def _trend(topic="GTA VI: dia 3", region="BR", url="https://www.youtube.com/watch?v=abc123XYZ_0"):
    return TrendRecord(
        id="t1", project_id="p1", topic=topic, topic_key=topic.lower(), source_name="YouTube Brasil (Em Alta)",
        source_url="https://www.googleapis.com/youtube/v3/videos", observed_at=NOW,
        window_start=NOW - timedelta(days=7), window_end=NOW, metric_name="views", metric_value=840000.0,
        evidence=[{"url": url, "title": topic, "channel": "Canal X", "published_at": "2026-11-18T09:00:00Z"}],
    )


def test_home_uses_the_v3_hero_and_sections():
    html = _home()
    assert html.count("<h1") == 1
    assert re.search(r"<h1[^>]*>O que você vai criar hoje\?</h1>", html)
    text = _visible_text(html)
    assert "SEU ESPAÇO DE CRIAÇÃO" in text
    assert "De uma ideia para um vídeo pronto" in text
    assert "Continuar de onde parou" in text
    assert "Tendências do canal" in text
    assert "Ver todos os vídeos" in text and "Ver todas as tendências" in text
    assert 'class="hero"' in html and 'class="campo-tema"' in html
    # formato como no protótipo: Vídeo (16:9) marcado por padrão e Short (9:16)
    assert re.search(r'name="format"[^>]*value="long"[^>]*checked', html)
    assert "Short (9:16)" in text and "Vídeo (16:9)" in text


def test_home_navigation_is_the_approved_ia():
    html = _home()
    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    labels = [re.sub(r"<[^>]+>", "", li).strip() for li in re.findall(r"<li>(.*?)</li>", main, re.S)]
    assert labels == ["Início", "Novo vídeo", "Vídeos", "Tendências", "Desempenho"]
    assert main.count('aria-current="page"') == 1
    assert re.search(r'<a href="/studio/panel" aria-current="page">', main)
    cfg = re.search(r'<nav aria-label="Configuração">(.*?)</nav>', html, re.S).group(1)
    assert "Configurações" in cfg and 'href="/studio/configuracoes/canais"' in cfg
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_home_drops_the_legacy_chrome():
    html = _home()
    text = _visible_text(html)
    for legacy in ("Estado das fases", "Série / Playlist", "Transforme uma ideia", "Precisa de você",
                   "Última falha", "Mockup com dados de exemplo"):
        assert legacy not in text, legacy
    assert 'class="rail"' not in html and 'class="sidebar"' not in html


def test_home_topbar_has_breadcrumb_channel_selector_and_theme_toggle():
    html = _home()
    assert re.search(r'<p class="crumb">Estúdio &nbsp;/&nbsp; <b>Início</b></p>', html)
    assert '<select class="canal-select" id="canal-ativo">' in html and "Canal Principal" in html
    btn = re.search(r'<button[^>]*id="btn-tema"[^>]*>', html).group(0)
    assert " hidden" in btn  # sem JS não existe controle morto
    assert 'name="color-scheme" content="light dark"' in html
    assert "light-dark(" in html


def test_home_shows_real_videos_with_status_and_empty_state():
    empty = _home()
    assert "Nenhum vídeo ainda" in _visible_text(empty)

    html = _home(videos=[
        _row("v-old", "Vídeo concluído", VideoStatus.PUBLISHED, updated_at=NOW - timedelta(days=1)),
        _row("v-wait", "Aguardando você", VideoStatus.AWAITING_APPROVAL, updated_at=NOW - timedelta(hours=5)),
    ])
    grid = html[html.index('class="grade"'):]
    assert 'href="/studio/panel/videos/v-wait"' in grid and 'href="/studio/panel/videos/v-old"' in grid
    # o que precisa de você vem primeiro, mesmo sendo mais antigo
    assert grid.index("v-wait") < grid.index("v-old")
    text = _visible_text(grid)
    assert "Esperando sua aprovação" in text
    assert "Nenhum vídeo ainda" not in text


def test_home_trend_card_shows_evidence_and_creates_from_topic():
    html = _home(trends=[_trend()])
    card = html[html.index('class="cartao-tendencia"'):]
    text = _visible_text(card)
    for expected in ("YouTube Brasil (Em Alta)", "GTA VI: dia 3", "Região", "Brasil", "Canal X", "18/11/2026"):
        assert expected in text, expected
    assert 'data-usar-tendencia="GTA VI: dia 3"' in card
    assert 'href="https://www.youtube.com/watch?v=abc123XYZ_0"' in card
    assert 'rel="noopener noreferrer"' in card


def test_home_prefills_topic_and_never_renders_zero_cost_or_inline_handlers():
    html = _home(topic="meu tema <b>")
    assert 'value="meu tema &lt;b&gt;"' in html
    assert "US$ 0,00" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "Não disponível: nenhuma chamada registrada neste mês." in _visible_text(html)


def test_home_still_creates_a_video_through_the_real_endpoint():
    html = _home()
    assert 'id="create-video-form"' in html and 'id="topic"' in html
    assert "fetch('/studio/videos'" in html
    assert "/studio/panel/videos/" in html  # abre o vídeo criado para informar a fonte
