"""Testes do Storyboard V3 (Cena em Foco, Desfazer/Refazer e Histórico de Áudio)."""
from __future__ import annotations

import re
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


def _scenes():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    rows = [("Introdução", "Como a luz do sol vira eletricidade na sua casa.", "Painel solar fotovoltaico brilhando sob o sol azul."),
            ("Mecanismo", "Os fótons atingem o silício e liberam elétrons livres.", "Diagrama macro de elétrons na célula de silício."),
            ("Conversão", "O inversor transforma a corrente contínua em alternada.", "Inversor moderno na parede piscando leds verdes.")]
    return video, [Scene(id=f"s{i + 1}", video_id=video.id, idx=i, narration=n, caption="c", label=l, image_prompt=p,
                         duration_s=6.5) for i, (l, n, p) in enumerate(rows)]


class _Script:
    version = 3
    scenes = ()


def test_v3_storyboard_renders_every_scene_card_in_order_with_prototype_controls():
    video, scenes = _scenes()
    html, _ = render_video_workspace(video, "cenas", script=_Script(), scenes=scenes)
    # VE-08.1: sem seletor nem cena em foco; um `sceneCard` completo por cena, na ordem do roteiro
    assert 'id="seletor-cenas"' not in html and 'id="cena-em-foco"' not in html
    assert html.count('<div class="scene" data-sid="') >= 3
    nums = re.findall(r'<span class="num">([^<]+)</span>', html)
    assert nums[:3] == ["CENA 1 · INTRODUÇÃO", "CENA 2 · MECANISMO", "CENA 3 · CONVERSÃO"]
    for token in ("btn-undo-cenas", "btn-redo-cenas", "↶ Desfazer", "↷ Refazer", "Regenerar áudio da cena",
                  "Histórico da voz", "Escolher mídia", "Storyboard integrado", "Ouvir trecho", "Prompt da imagem"):
        assert token in html, token
    assert 'data-a="text" data-sid="s1"' in html and 'data-a="prompt" data-sid="s3"' in html
    assert "Ver roteiro completo · 3 cenas" in html
    assert 'id="dlg-media"' in html and 'id="dlg-audio-history"' in html
    assert "role=\"dialog\"" not in html and "aria-modal" not in html          # <dialog> nativo


def test_v3_storyboard_has_undo_redo_client_logic_and_native_dialogs():
    video, scenes = _scenes()
    html, _ = render_video_workspace(video, "cenas", script=_Script(), scenes=scenes)
    assert "var undo = [], redo = [];" in html and "showModal" in html
    assert "Edi\\u00e7\\u00e3o restaurada. Publica\\u00e7\\u00f5es e custos n\\u00e3o s\\u00e3o desfeitos." in html


def test_v3_storyboard_csp_compliance_no_inline_handlers():
    video, scenes = _scenes()
    scenes[0] = scenes[0].model_copy(update={"asset_id": "asset-1"})
    html, _ = render_video_workspace(video, "cenas", script=_Script(), scenes=scenes)
    assert "onerror=" not in html and "onclick=" not in html
    assert "document.addEventListener('error'" in html


def test_v3_storyboard_escapes_script_tag_in_json():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    xss_scene = {"id": "s1", "idx": 0, "narration": "Texto com perigo </script><script>alert('xss')</script>!",
                 "caption": "Legenda", "label": "Cena XSS", "image_prompt": "Prompt seguro."}
    html, _ = render_video_workspace(video, "cenas", script=_Script(), scenes=[xss_scene])
    payload = html.split('id="storyboard-data">')[1].split("</script>")[0]
    assert "</script><script>" not in payload and "<\\/script>" in payload


def test_v3_storyboard_audio_history_is_read_only_and_real():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema Solar", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    scene = {"id": "s1", "idx": 0, "narration": "Texto atual da cena.", "caption": "Legenda", "label": "Cena 1",
             "image_prompt": "Prompt visual.", "audio_history": [
                 {"version": 1, "text": "Texto antigo diferente.", "duration_s": 5.0},
                 {"version": 2, "text": "Texto atual da cena.", "duration_s": 4.8}]}
    html, _ = render_video_workspace(video, "cenas", script=_Script(), scenes=[scene])
    assert "v2 (atual) · voz gerada" not in html                       # nada de versão inventada
    assert 'id="audio-history-list"' in html and "Nenhuma gera\\u00e7\\u00e3o guardada ainda." in html
    assert "Texto antigo diferente." in html.split('id="storyboard-data">')[1]
    assert "Restaurar" not in html                                      # sem backend para restaurar


def test_nova_cena_is_an_in_place_action_with_the_script_version():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    scenes = [Scene(id="s1", video_id=video.id, idx=0, narration="Como a luz do sol vira eletricidade.",
                    caption="Energia", label="Introdução", image_prompt="Painel solar sob o sol azul.", duration_s=6.5)]

    class _Script:
        version = 3
        scenes = ()

    html = render_video_workspace(video, active_area="cenas", script=_Script(), scenes=scenes, sources=[])
    assert 'id="btn-nova-cena"' in html and 'data-script-version="3"' in html
    assert f'href="/studio/videos/{video.id}/roteiro">+ Nova cena' not in html
    # o texto-padrão da cena nova é o do protótipo (`mkScene('Nova cena', ...)`)
    assert "Escreva aqui o texto da narra" in html and "descreva a imagem desejada" in html
