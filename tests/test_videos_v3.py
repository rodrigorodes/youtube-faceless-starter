"""UX V3: Tela Vídeos segue a proposta aprovada (docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html).

Lista de todos os vídeos do canal, busca por tema e filtro por situação.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.studio.application.panel import BuildPanel
from app.studio.domain.contracts import VideoStatus
from test_panel import FakePanelRepo, _row
from test_ux_contract import assert_ux_contract

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def _videos_page(videos=None):
    from app.studio.api.panel_videos import render_videos

    repo = FakePanelRepo(videos_list=videos or [])
    view = BuildPanel(repo, 15.0, lambda: NOW).execute(days=7)
    return render_videos(view)


def test_videos_uses_v3_shell_and_nav():
    html, _ = _videos_page()
    assert html.count("<h1") == 1
    assert "Estúdio &nbsp;/&nbsp; <b>Vídeos</b>" in html
    assert "SEU CONTEÚDO" in html
    assert "Todos os vídeos do canal, em um só lugar." in html
    assert re.search(r'href="/studio/panel/novo-video(?:\?project_id=[^"]+)?"', html)

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/videos(?:\?project_id=[^"]+)?" aria-current="page"', main)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_videos_search_and_filter_controls():
    html, _ = _videos_page()
    assert 'id="busca-videos"' in html
    assert 'name="filtro"' in html
    assert re.search(r'name="filtro"[^>]*value="todos"[^>]*checked', html)
    assert 'value="producao"' in html
    assert 'value="aprovar"' in html
    assert 'value="publicados"' in html


def test_videos_empty_state():
    html, _ = _videos_page(videos=[])
    assert "Nenhum vídeo ainda" in html


def test_videos_renders_real_cards_with_filter_attributes():
    rows = [
        _row("v1", "GTA VI Guia Completo", VideoStatus.PUBLISHED, updated_at=NOW - timedelta(days=1)),
        _row("v2", "IA Autônoma no Trabalho", VideoStatus.AWAITING_APPROVAL, updated_at=NOW - timedelta(hours=2)),
        _row("v3", "Renderizando Cenas", VideoStatus.SCRIPTED, step_running=True, updated_at=NOW - timedelta(hours=1)),
    ]
    html, _ = _videos_page(videos=rows)
    assert 'data-situacao="publicados"' in html
    assert 'data-situacao="aprovar"' in html
    assert 'data-situacao="producao"' in html
    assert 'href="/studio/panel/videos/v1"' in html
    assert 'href="/studio/panel/videos/v2"' in html
    assert 'href="/studio/panel/videos/v3"' in html
    assert "GTA VI Guia Completo" in html
    assert "IA Autônoma no Trabalho" in html
    assert "Renderizando Cenas" in html


def test_videos_satisfies_ux_contract():
    rows = [_row("v1", "Vídeo de Teste", VideoStatus.PUBLISHED)]
    html, _ = _videos_page(videos=rows)
    assert_ux_contract(html, page="painel/vídeos")
    assert not re.search(r"\son[a-z]+=", html)
