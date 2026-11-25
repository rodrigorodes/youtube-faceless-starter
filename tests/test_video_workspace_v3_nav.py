"""Testes da reestruturação da navegação do workspace V3 (6 áreas canônicas + diagnóstico)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_nav import (
    ALL_AREA_IDS,
    ALL_VALID_AREAS,
    AREA_IDS,
    DEFAULT_AREA,
    VIDEO_AREAS,
    normalize_area,
    video_area_nav,
)
from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.application.panel import VideoDetailView
from app.studio.domain.contracts import Video, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage


def _sample_view(video_id: str = "vid1234567890abcdef") -> VideoDetailView:
    return VideoDetailView(
        video=Video(
            id=video_id,
            project_id="p1",
            topic="Vídeo de Teste V3",
            title="Vídeo de Teste V3",
            format=VideoFormat.short,
            status=VideoStatus.IDEA,
        ),
        stage=Stage.PENDING,
        cost_text="sem registro de uso",
        steps=[],
        usage=[],
        render_error=None,
        publication=None,
        sources=[],
        latest_run=None,
    )


def test_v3_video_nav_has_six_primary_areas():
    area_ids = [aid for aid, _ in VIDEO_AREAS]
    assert area_ids == ["direcao", "cenas", "composicao", "qualidade", "publicacao", "fontes"]
    assert "producao" not in area_ids

    labels = [label for _, label in VIDEO_AREAS]
    assert labels == [
        "Direção criativa",
        "Cenas & Storyboard",
        "Composição & Legendas",
        "Qualidade & Aprovação",
        "Publicação YouTube",
        "Fontes & Evidências",
    ]


def test_producao_recognized_as_valid_route_outside_main_nav():
    assert normalize_area("producao") == "producao"
    assert "producao" not in AREA_IDS
    assert "producao" in ALL_VALID_AREAS
    assert "producao" in ALL_AREA_IDS


def test_v3_video_nav_normalizes_legacy_and_unknown_areas_to_cenas():
    assert DEFAULT_AREA == "cenas"
    assert normalize_area("visao-geral") == "cenas"
    assert normalize_area("narracao") == "cenas"
    assert normalize_area("desconhecida") == "cenas"
    assert normalize_area(None) == "cenas"

    for area_id in ["direcao", "cenas", "composicao", "qualidade", "publicacao", "fontes"]:
        assert normalize_area(area_id) == area_id


def test_video_area_nav_renders_exactly_six_tab_links():
    video_id = "testvideo123"
    nav = video_area_nav(video_id, "cenas")

    anchors = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', nav)
    assert len(anchors) == 6

    expected_links = [
        (f"/studio/panel/videos/{video_id}/direcao", "Direção criativa"),
        (f"/studio/panel/videos/{video_id}/cenas", "Cenas &amp; Storyboard"),
        (f"/studio/panel/videos/{video_id}/composicao", "Composição &amp; Legendas"),
        (f"/studio/panel/videos/{video_id}/qualidade", "Qualidade &amp; Aprovação"),
        (f"/studio/panel/videos/{video_id}/publicacao", "Publicação YouTube"),
        (f"/studio/panel/videos/{video_id}/fontes", "Fontes &amp; Evidências"),
    ]
    assert anchors == expected_links

    # Apenas a aba ativa tem aria-current="page"
    assert nav.count('aria-current="page"') == 1
    assert 'href="/studio/panel/videos/testvideo123/cenas" aria-current="page"' in nav
    assert "producao" not in nav


def test_render_video_workspace_renders_diagnostico_link_in_header():
    view = _sample_view("vid_diag_test")
    html, headers = render_video_workspace(view, "cenas")

    diag_href = f"/studio/panel/videos/{view.video.id}/producao"
    assert f'href="{diag_href}"' in html
    assert "Ver progresso / Diagnóstico" in html

    # O link de diagnóstico está no `.head` e usa o estilo do protótipo: `btn ghost small`
    match = re.search(
        r'<a[^>]*href="' + re.escape(diag_href) + r'"[^>]*>([^<]+)</a>',
        html,
    )
    assert match is not None
    assert "Ver progresso / Diagnóstico" in match.group(1)
    tag = match.group(0)
    assert "btn" in tag
    assert "ghost" in tag
    assert "small" in tag
