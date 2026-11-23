import base64
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.api.routes import make_router
from app.studio.application.panel import VideoDetailView
from app.studio.application.use_cases import UseCases
from app.studio.application.video_style import VideoStylePatch, VideoStylePatchConflict, VideoStyleView
from app.studio.domain.contracts import Video, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage
from app.studio.domain.visual_style import StylePatch, StylePatchInvalid, VisualStyle

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADER = {**AUTH_HEADER, "Origin": "http://testserver"}


def _sample_style() -> VisualStyle:
    return VisualStyle(
        id="a" * 32,
        name="Cinemático V3",
        params={
            "caption": {"font_size": 42, "bottom": 96},
            "palette": {"caption_text": "#ffffff", "caption_box": "#00000099", "accent": "#a78bfa"},
            "motion": ["zoom_in", "pan_left"],
            "music": {"bpm": 120, "seed": 7},
            "transition": {"kind": "fade", "duration_ticks": 6},
        },
    )


def _sample_style_view(style: VisualStyle | None = None) -> VideoStyleView:
    st = style or _sample_style()
    return VideoStyleView(
        video_id="1" * 32,
        project_id="2" * 32,
        override_style_id=None,
        channel_style_id=st.id,
        inherited_style_name=st.name,
        styles=(st,),
    )


def test_v3_composition_tab_renders_active_controls():
    video = Video(id="1" * 32, project_id="2" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.IDEA)
    style = _sample_style()
    style_view = _sample_style_view(style)
    res = render_video_workspace(video, active_area="composicao", style_view=style_view, script=None, scenes=[], sources=[])
    html = str(res)

    # Controles ativos de legenda
    assert "Tamanho da legenda" in html
    assert 'name="caption.font_size"' in html or 'id="composicao-font-size"' in html
    assert 'value="42"' in html

    assert "Distância da base" in html
    assert 'name="caption.bottom"' in html or 'id="composicao-bottom"' in html
    assert 'value="96"' in html

    # Paleta de cores
    assert "Paleta de cores" in html
    assert "texto da legenda" in html.lower() or "caption_text" in html
    assert "caixa da legenda" in html.lower() or "caption_box" in html
    assert "destaque" in html.lower() or "accent" in html
    assert "#ffffff" in html
    assert "#a78bfa" in html

    # Movimento de câmera
    assert "Movimento" in html
    assert "zoom" in html.lower()
    assert "estático" in html.lower() or "estatico" in html.lower()

    # Controles de música (music.bpm e music.seed)
    assert "Andamento da música" in html or "BPM" in html
    assert 'id="composicao-music-bpm"' in html
    assert 'value="120"' in html
    assert "Semente da música" in html or "seed" in html
    assert 'id="composicao-music-seed"' in html
    assert 'value="7"' in html


def test_v3_composition_tab_labels_unsupported_controls_honestly():
    video = Video(id="1" * 32, project_id="2" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.IDEA)
    style_view = _sample_style_view()
    res = render_video_workspace(video, active_area="composicao", style_view=style_view, script=None, scenes=[], sources=[])
    html = str(res)

    # 1. Posição da legenda: Topo / Meio / Base rotulado "Em breve no Plano 2", disabled
    assert "Posição da legenda" in html
    pos_match = re.search(r'Posição da legenda.*?(?:Topo.*?Meio.*?Base|Base.*?Meio.*?Topo)', html, re.S | re.I)
    assert pos_match is not None, "bloco de posição da legenda não encontrado"
    pos_block = pos_match.group(0)
    assert "Em breve no Plano 2" in pos_block
    assert "disabled" in pos_block

    # 2. Fonte da legenda: Inter / Roboto / Georgia rotulado "Em breve no Plano 2", disabled
    assert "Fonte da legenda" in html
    fonte_match = re.search(r'Fonte da legenda.*?(?:Inter.*?Roboto.*?Georgia)', html, re.S | re.I)
    assert fonte_match is not None, "bloco de fonte da legenda não encontrado"
    fonte_block = fonte_match.group(0)
    assert "Em breve no Plano 2" in fonte_block
    assert "disabled" in fonte_block

    # 3. Estilo da legenda: Destaque por palavra / Caixa / Simples rotulado "Em breve no Plano 2", disabled
    assert "Estilo da legenda" in html
    estilo_match = re.search(r'Estilo da legenda.*?(?:Destaque por palavra.*?Caixa.*?Simples)', html, re.S | re.I)
    assert estilo_match is not None, "bloco de estilo da legenda não encontrado"
    estilo_block = estilo_match.group(0)
    assert "Em breve no Plano 2" in estilo_block
    assert "disabled" in estilo_block

    # 4. Transição entre cenas: Fade / Corte seco / Deslizar rotulado "Em breve no Plano 2", disabled
    assert "Transição entre cenas" in html
    trans_match = re.search(r'Transição entre cenas.*?(?:Fade.*?Corte seco.*?Deslizar)', html, re.S | re.I)
    assert trans_match is not None, "bloco de transição entre cenas não encontrado"
    trans_block = trans_match.group(0)
    assert "Em breve no Plano 2" in trans_block
    assert "disabled" in trans_block

    # 5. Taxa de quadros / FPS: 25 fps vigente, 24/30/60 marcadas como "Em breve no Plano 2"
    assert "Taxa de quadros" in html or "FPS" in html
    fps_match = re.search(r'(?:Taxa de quadros|FPS).*?60 fps', html, re.S | re.I)
    assert fps_match is not None, "bloco de FPS não encontrado"
    fps_block = fps_match.group(0)
    assert "25 fps" in fps_block
    assert "Em breve no Plano 2" in fps_block

    # Badges visuais padrão pill
    assert '<span class="pill pill-espera">Em breve no Plano 2</span>' in html


def test_v3_composition_tab_submits_supported_changes_to_style_patch():
    video = Video(id="1" * 32, project_id="2" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.IDEA)
    style_view = _sample_style_view()
    res = render_video_workspace(video, active_area="composicao", style_view=style_view, script=None, scenes=[], sources=[])
    html = str(res)

    # Form ou container com endpoint PATCH para /studio/videos/{id}/style-patch (e NÃO /style)
    assert f'/studio/videos/{video.id}/style-patch' in html
    assert 'id="form-composicao"' in html
    assert 'id="comp-patch-revision"' in html
    assert 'id="btn-salvar-composicao"' in html

    # Client JS manipula PATCH para /style-patch com os campos suportados (caption, palette, motion, music)
    assert "form-composicao" in html
    assert "PATCH" in html
    assert "style-patch" in html
    assert "expected_revision" in html
    assert "caption" in html
    assert "palette" in html
    assert "motion" in html
    assert "music" in html


def test_v3_task6_sync_agendamento_and_publish_at_in_page_js():
    video = Video(id="1" * 32, project_id="2" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.APPROVED)
    res = render_video_workspace(video, active_area="publicacao")
    html = str(res)

    # Verifica se PAGE_JS sincroniza #agendamento-data com #publish_at e limpa ao marcar #publicar-agora
    assert "publish_at" in html
    assert "agendamento-data" in html
    assert "publicar-agora" in html
    assert "syncPublishAt" in html


class _MockSetVideoStylePatch:
    def __init__(self):
        self.calls = []
        self.revision = 0
        self.patch = None

    def execute(self, video_id: str, expected_revision: int, patch: object):
        if expected_revision != self.revision:
            raise VideoStylePatchConflict(f"revision conflict: expected {expected_revision}, found {self.revision}")
        typed_patch = StylePatch.from_mapping(patch, where="video style patch") if patch else None
        self.revision += 1
        self.patch = typed_patch
        self.calls.append((video_id, expected_revision, typed_patch))
        return VideoStylePatch(revision=self.revision, patch=typed_patch)


class _MockSetVideoStyle:
    def __init__(self):
        self.calls = []

    def execute(self, video_id: str, style_id: str | None):
        self.calls.append((video_id, style_id))
        return Video(id=video_id, project_id="2" * 32, topic="Tema", format=VideoFormat.short, style_id=style_id)


def test_v3_api_video_style_patch_persists_without_erasing_style_id():
    video_id = "3" * 32
    mock_patch_service = _MockSetVideoStylePatch()
    mock_style_service = _MockSetVideoStyle()

    uc = UseCases(
        None,
        None,
        None,
        None,
        set_video_style=mock_style_service,
        set_video_style_patch=mock_patch_service,
    )
    app = FastAPI()
    app.include_router(make_router(lambda: uc, lambda: True))
    client = TestClient(app)

    # 1. Submete o patch com caption, palette, motion, music
    payload = {
        "expected_revision": 0,
        "patch": {
            "caption": {"font_size": 48, "bottom": 100},
            "palette": {"accent": "#a78bfa"},
            "motion": ["zoom_in", "pan_left"],
            "music": {"bpm": 130, "seed": 42},
        },
    }
    r = client.patch(f"/studio/videos/{video_id}/style-patch", json=payload, headers=POST_HEADER)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["revision"] == 1
    assert data["patch"]["caption"]["font_size"] == 48
    assert data["patch"]["music"]["bpm"] == 130

    # Garante que set_video_style NÃO foi chamado (ou seja, style_id do vídeo não foi tocado/apagado)
    assert len(mock_style_service.calls) == 0

    # 2. Conflito otimista com revisão divergente (409)
    r_conflict = client.patch(f"/studio/videos/{video_id}/style-patch", json=payload, headers=POST_HEADER)
    assert r_conflict.status_code == 409

    # 3. Patch com campo inválido rejeitado com 422
    bad_payload = {"expected_revision": 1, "patch": {"campo_desconhecido": "valor"}}
    r_bad = client.patch(f"/studio/videos/{video_id}/style-patch", json=bad_payload, headers=POST_HEADER)
    assert r_bad.status_code == 422
