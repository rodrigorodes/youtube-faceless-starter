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
    # `pgHome` do protótipo V4/V3: hero → "Precisa de você" / "Primeiros passos" → tendências.
    assert "O que você vai criar hoje?" in text
    assert "Digite um tema ou cole seu roteiro" in text
    assert "Comece por uma tendência no seu nicho" in text
    assert "Ver todas as tendências" not in text  # o protótipo v4-v3 não tem esse link
    assert "Continuar de onde parou" not in text and "Ver todos os vídeos" not in text
    assert 'class="hero"' in html and 'class="prompt"' in html
    # formato como no protótipo: Short 9:16 marcado por padrão (o canal sem perfil não define outro)
    assert re.search(r'name="format"[^>]*value="short"[^>]*checked', html)
    assert "Short · 9:16" in text and "Vídeo · 16:9" in text


def test_home_navigation_is_the_approved_ia():
    html = _home()
    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    # os ícones do protótipo são glifos (`⌂ ✦ ▤ …`) dentro de `<span aria-hidden>`: não são rótulo.
    labels = [re.sub(r"<span aria-hidden.*?</span>|<[^>]+>", "", li).strip()
              for li in re.findall(r"<li>(.*?)</li>", main, re.S)]
    # NAV do protótipo (`prototype/index.html:583`): sete itens numa lista só, Configurações incluso.
    assert labels == ["Início", "Criar vídeo", "Vídeos", "Tendências e ideias", "Desempenho",
                      "Biblioteca", "Configurações"]
    assert main.count('aria-current="page"') == 1
    # F02.T01: o item ativo pode carregar o canal ativo (?project_id=)
    assert re.search(r'<a href="/studio/panel(?:\?project_id=[^"]+)?" aria-current="page">', main)
    cfg = [li for li in re.findall(r"<li>(.*?)</li>", main, re.S) if "Configurações" in li][0]
    assert re.search(r'href="/studio/configuracoes/canais(?:\?project_id=[^"]+)?"', cfg)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_home_drops_the_legacy_chrome():
    html = _home()
    text = _visible_text(html)
    for legacy in ("Estado das fases", "Série / Playlist", "Transforme uma ideia",
                   "Última falha", "Mockup com dados de exemplo"):
        assert legacy not in text, legacy
    assert 'class="rail"' not in html and 'class="sidebar"' not in html


def test_home_topbar_has_channel_selector_and_no_theme_toggle():
    html = _home()
    # topbar do protótipo: seletor de canal + pill de estilo/voz à esquerda, "✦ Criar vídeo" à direita.
    assert '<select class="canal-select" id="canal-ativo">' in html and "Canal Principal" in html
    assert 'id="chstyle"' in html
    assert 'id="btn-tema"' not in html  # o protótipo é dark nativo, sem alternância de tema
    assert 'class="crumb"' not in html


def test_home_shows_only_videos_that_need_you_and_first_steps_when_empty():
    empty = _visible_text(_home())
    assert "Primeiros passos do canal" in empty
    assert "Precisa de você" not in empty

    html = _home(videos=[
        _row("v-old", "Vídeo concluído", VideoStatus.PUBLISHED, updated_at=NOW - timedelta(days=1)),
        _row("v-wait", "Aguardando você", VideoStatus.AWAITING_APPROVAL, updated_at=NOW - timedelta(hours=5)),
        _row("v-fail", "Falhou aqui", VideoStatus.FAILED, updated_at=NOW - timedelta(hours=1)),
    ])
    grid = html[html.index('class="grade"'):html.index('id="tendencias"')]
    text = _visible_text(grid)
    # "Precisa de você": aprovar antes de retomar falha; o que não depende do usuário não aparece
    assert 'href="/studio/panel/videos/v-wait/qualidade"' in grid and 'href="/studio/panel/videos/v-fail/producao"' in grid
    assert "v-old" not in grid
    assert grid.index("v-wait") < grid.index("v-fail")
    assert "Aguardando aprovação" in text and "Revisar e aprovar" in text
    assert "Falhou na produção" in text and "Ver e retomar" in text
    assert "Precisa de você" in _visible_text(html)
    assert "Primeiros passos" not in _visible_text(html)


def test_home_trend_card_shows_evidence_and_creates_from_topic():
    html = _home(trends=[_trend()])
    card = html[html.index('class="card cartao-tendencia"'):]
    text = _visible_text(card)
    for expected in ("YouTube Brasil (Em Alta)", "GTA VI: dia 3", "Brasil", "Canal X", "18/11/2026"):
        assert expected in text, expected
    assert 'data-usar-tendencia="GTA VI: dia 3"' in card
    # protótipo v4-v3: o cartão de Início é pill + título + uma linha + ação; o vídeo base com link
    # fica na tela Tendências.
    assert "Vídeo base" not in card


def test_home_prefills_topic_and_never_renders_zero_cost_or_inline_handlers():
    html = _home(topic="meu tema <b>")
    assert 'value="meu tema &lt;b&gt;"' in html
    assert "US$ 0,00" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "Não disponível: nenhuma chamada registrada neste mês." in _visible_text(html)


def test_home_still_creates_a_video_through_the_real_endpoint():
    html = _home()
    assert 'id="create-video-form"' in html and ('id="homeTopic"' in html or 'id="topic"' in html)
    assert "fetch('/studio/videos'" in html
    assert "/studio/panel/videos/" in html  # abre o vídeo criado para informar a fonte


def test_home_v3_quick_creation_has_idea_and_script_toggle():
    html = _home()
    assert 'name="tipo-entrada"' in html or 'data-kind="input-toggle"' in html
    assert "Tenho uma ideia" in html
    assert "Já tenho roteiro" in html
    assert 'id="home-topico"' in html or 'id="homeTopic"' in html
    assert "Padrões de Canal Principal · 60s · Padrão" in html
    assert "⚡ Gerar vídeo completo" in html
    assert "/studio/panel/novo-video" in html
    assert "Personalizar este vídeo" in html
    assert "local://roteiro-inicial" in html
    assert "/sources" in html
    assert "production_mode" in html


def test_home_v3_quick_creation_action_button_director_mode():
    from app.studio.api.panel import render_panel

    repo = FakePanelRepo()
    view = BuildPanel(repo, 15.0, lambda: NOW).execute()
    object.__setattr__(view, "channels", [
        {"id": "p1", "project_id": "p1", "name": "Canal Geek", "target_duration_s": 45, "visual_identity": "Tech Clean", "default_mode": "diretor"}
    ])
    html = render_panel(view)[0]
    assert "🎬 Abrir storyboard" in html
    assert "Padrões de Canal Geek · 45s · Tech Clean" in html


