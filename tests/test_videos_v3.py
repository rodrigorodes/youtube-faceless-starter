"""UX V3: Tela Vídeos segue a proposta aprovada (docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3, `pgVideos`).

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
    assert "Biblioteca de vídeos" in html  # eyebrow do protótipo
    assert '<p class="sub">Canal Principal</p>' in html  # subtítulo = nome do canal
    assert 'class="crumb"' not in html
    assert re.search(r'href="/studio/panel/novo-video(?:\?project_id=[^"]+)?"', html)

    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'href="/studio/panel/videos(?:\?project_id=[^"]+)?" aria-current="page"', main)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S)
    assert markup.count('aria-current="page"') == 1


def test_videos_search_and_filter_controls():
    html, _ = _videos_page()
    assert 'id="busca-videos"' in html
    # pills do protótipo (`vfilter`): "Todos" ativo por padrão, com contagem real
    assert re.search(r'class="pill btnlike accent"[^>]*data-filtro="todos">Todos · 0</span>', html)
    for key in ("aprovar", "rascunho", "falha", "publicados"):
        assert f'data-filtro="{key}"' in html, key


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
    assert 'data-situacao="outros"' in html  # em produção: só aparece em "Todos"
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


def test_videos_filters_follow_the_prototype_labels():
    """Os cinco filtros de `pgVideos`, com contagem ao lado do rótulo."""
    html, _ = _videos_page()
    for label in ("Todos", "Para aprovar", "Rascunhos", "Com falha", "Publicados"):
        assert f"{label} · 0</span>" in html, label


def test_videos_table_has_only_columns_the_product_knows():
    rows = [_row("v1", "Qualquer", VideoStatus.AWAITING_APPROVAL, updated_at=NOW)]
    html, _ = _videos_page(videos=rows)
    head = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    assert re.findall(r"<th>(.*?)</th>", head) == ["Vídeo", "Formato", "Estado", "Custo", "Atualizado"]
    assert "Não informado" not in html


# ------------------------------------------- UX-01/W1.1: "Aprovado" não é "Publicado"


def _card_of(html: str, video_id: str) -> str:
    cards = re.findall(r'<tr class="click".*?</tr>', html, re.S)
    picked = [c for c in cards if f'"/studio/panel/videos/{video_id}"' in c]
    assert len(picked) == 1, f"cartão de {video_id} não é único: {len(picked)}"
    return picked[0]


def test_approved_video_shows_as_approved_and_stays_out_of_published():
    """UX-01 (R5, cenário A21): aprovar não publica.

    Um vídeo apenas aprovado, sem upload, aparece como "Aprovado" e não pode ser
    apresentado como publicado nem entrar no filtro "Publicados".
    """
    rows = [_row("v1", "Aprovado sem upload", VideoStatus.APPROVED, updated_at=NOW)]
    html, _ = _videos_page(videos=rows)
    card = _card_of(html, "v1")
    assert "Aprovado" in card
    assert "Publicado" not in card
    assert 'data-situacao="publicados"' not in card


def test_only_effectively_published_videos_are_in_the_published_filter():
    """Publicar é status PUBLISHED ou publicação UPLOADED; aprovado continua de fora."""
    from app.studio.domain.contracts import PublicationStatus

    rows = [
        _row("v1", "Publicado pelo status", VideoStatus.PUBLISHED, updated_at=NOW),
        _row("v2", "Aprovado e enviado", VideoStatus.APPROVED,
             pub=PublicationStatus.UPLOADED, updated_at=NOW),
        _row("v3", "Apenas aprovado", VideoStatus.APPROVED, updated_at=NOW),
    ]
    html, _ = _videos_page(videos=rows)
    assert 'data-situacao="publicados"' in _card_of(html, "v1")
    assert 'data-situacao="publicados"' in _card_of(html, "v2")
    assert 'data-situacao="publicados"' not in _card_of(html, "v3")
