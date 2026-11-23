"""Testes do Storyboard V3 (Cena em Foco, Desfazer/Refazer e Histórico de Áudio)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.domain.contracts import Scene, Video, VideoFormat, VideoStatus


def test_v3_storyboard_renders_scene_selector_and_full_script_details():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    # Render da área 'cenas'
    html = render_video_workspace(video, active_area="cenas", script=None, scenes=[], sources=[])
    assert 'id="seletor-cenas"' in html or 'class="seletor-cenas"' in html
    assert "Ver roteiro completo" in html
    assert "Desfazer" in html or "btn-undo" in html


def test_v3_storyboard_renders_focused_scene_and_action_buttons():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    sample_scenes = [
        Scene(
            id="s1",
            video_id=video.id,
            idx=0,
            narration="Como a luz do sol vira eletricidade na sua casa.",
            caption="Energia solar em 60 segundos",
            label="Introdução",
            image_prompt="Painel solar fotovoltaico brilhando sob o sol azul.",
            duration_s=6.5,
        ),
        Scene(
            id="s2",
            video_id=video.id,
            idx=1,
            narration="Os fótons atingem o silício e liberam elétrons livres.",
            caption="Efeito fotoelétrico",
            label="Mecanismo",
            image_prompt="Diagrama macro de elétrons se movendo através da célula de silício.",
            duration_s=8.0,
        ),
        Scene(
            id="s3",
            video_id=video.id,
            idx=2,
            narration="O inversor transforma a corrente contínua em alternada.",
            caption="Inversor de corrente",
            label="Conversão",
            image_prompt="Inversor moderno na parede piscando leds verdes de geração.",
            duration_s=7.5,
        ),
    ]

    html, headers = render_video_workspace(video, "cenas", scenes=sample_scenes)

    # Seletor de cenas com botões para cada cena
    assert 'id="seletor-cenas"' in html
    assert 'data-scene-idx="0"' in html
    assert 'data-scene-idx="1"' in html
    assert 'data-scene-idx="2"' in html
    assert 'aria-pressed="true"' in html

    # Cartão de cena em foco
    assert 'id="cena-em-foco"' in html
    assert "Como a luz do sol vira eletricidade" in html
    assert "Painel solar fotovoltaico" in html

    # Ações da cena e do storyboard
    assert "btn-undo-cenas" in html
    assert "btn-redo-cenas" in html
    assert "Desfazer" in html
    assert "Refazer" in html
    assert "Regenerar voz" in html
    assert "Histórico da voz" in html
    assert "Trocar mídia" in html

    # Badges de áudio
    assert "badge-audio" in html or "pill-audio" in html or "audio-state" in html

    # Roteiro completo colapsável
    assert '<details class="diag"' in html or '<details class="diag' in html
    assert "Ver roteiro completo · 3 cenas" in html
    assert "Mecanismo" in html
    assert "Inversor moderno na parede" in html

    # Diálogos de histórico e mídia
    assert 'id="dialog-audio-history"' in html
    assert 'id="dialog-trocar-midia"' in html


def test_v3_storyboard_includes_undo_redo_and_modal_client_js():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    html, _ = render_video_workspace(video, "cenas", scenes=[])

    # Presença do script de manipulação no cliente
    assert "undoStack" in html
    assert "redoStack" in html
    assert "dialog-audio-history" in html
    assert "dialog-trocar-midia" in html
