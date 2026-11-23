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
    # Sem cenas reais o protótipo (`prior.scenes`) mostra o cabeçalho "Storyboard integrado" e um
    # cartão vazio: nada de seletor, de undo/redo nem de roteiro completo sobre cenas que não existem.
    assert "Storyboard integrado" in html
    assert "Sem cenas." in html
    assert "+ Nova cena" in html
    assert 'id="seletor-cenas"' not in html
    assert 'id="cena-em-foco"' not in html


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
    assert "Regenerar áudio da cena" in html
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


def test_v3_storyboard_csp_compliance_no_inline_onerror():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    sample_scenes = [
        Scene(
            id="s1",
            video_id=video.id,
            idx=0,
            narration="Texto da cena 1.",
            caption="Legenda 1",
            label="Intro",
            image_prompt="Prompt da cena 1.",
            asset_id="asset-1",
        )
    ]
    html, _ = render_video_workspace(video, "cenas", scenes=sample_scenes)

    # Imagem de preview não deve conter manipulador inline onerror para conformidade com CSP
    assert '<img id="foco-midia-img"' in html
    assert 'onerror=' not in html
    # Ouvinte de erro anexado via addEventListener no JS do cliente
    assert "mediaImg.addEventListener('error'" in html


def test_v3_storyboard_escapes_script_tag_in_json():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    xss_scene = {
        "id": "s1",
        "idx": 0,
        "narration": "Texto com perigo </script><script>alert('xss')</script>!",
        "caption": "Legenda",
        "label": "Cena XSS",
        "image_prompt": "Prompt seguro.",
    }
    html, _ = render_video_workspace(video, "cenas", scenes=[xss_scene])

    # O script JSON embutido não pode conter '</' sem escape
    assert "</script><script>" not in html.split('id="storyboard-scenes-data">')[1].split("</script>")[0]
    assert "<\\/script>" in html


def test_v3_storyboard_audio_history_dynamic_and_restore_stale_logic():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    scene_with_history = {
        "id": "s1",
        "idx": 0,
        "narration": "Texto atual da cena.",
        "caption": "Legenda",
        "label": "Cena 1",
        "image_prompt": "Prompt visual.",
        "audio_history": [
            {"version": 1, "text": "Texto antigo diferente.", "duration_s": 5.0},
            {"version": 2, "text": "Texto atual da cena.", "duration_s": 4.8},
        ],
    }
    html, _ = render_video_workspace(video, "cenas", scenes=[scene_with_history])

    # Não deve ter versões falsas hardcoded no HTML estático
    assert "v2 (atual) · voz gerada" not in html
    assert "Nenhuma versão anterior gravada para esta cena." in html
    assert 'id="dialog-audio-history-list"' in html

    # Lógica de restauração com marcação de stale/ok e indicação na pill no JS
    assert "renderAudioHistory" in html
    assert "btn-restaurar-audio" in html
    assert "Áudio desatualizado" in html
    assert "✓ Áudio atual" in html
    assert "· atualizar voz" in html
    assert "audio_history" in html


def test_v3_storyboard_undo_redo_saves_snapshot_on_focusin_before_mutation():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    html, _ = render_video_workspace(video, "cenas", scenes=[])

    # Snapshot salvo no focusin antes de iniciar a mutação de texto
    assert "focusin" in html
    assert "isEditingNarration" in html
    assert "btnUndo.addEventListener('click'" in html
    assert "btnRedo.addEventListener('click'" in html
