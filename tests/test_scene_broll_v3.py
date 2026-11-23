"""Testes de metadados de B-Roll em cenas (F02/V3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.domain.contracts import Scene, Video, VideoFormat, VideoStatus


class _Script:
    version = 2
    scenes = ()


def _video():
    return Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)


def test_storyboard_renders_broll_controls_in_every_scene_card():
    scenes = [
        {"id": "s1", "narration": "Texto da cena com b-roll ativo.", "image_prompt": "Prompt visual 1",
         "broll_enabled": True, "broll_note": "Corte para tela do app"},
        {"id": "s2", "narration": "Cena dois sem b-roll nenhum.", "image_prompt": "Prompt visual 2"},
    ]
    html, _ = render_video_workspace(_video(), active_area="cenas", script=_Script(), scenes=scenes, sources=[])
    cards = html.split('<div class="scene" data-sid="')[1:]
    # `sceneCard` do protótipo: cada cena traz o seu botão e, ativo, a descrição do B-roll
    assert len(cards) >= 2
    assert 'data-a="broll" data-sid="s1"' in html and 'data-a="broll" data-sid="s2"' in html
    assert "B-roll ativo" in cards[0] and 'aria-pressed="true"' in cards[0]
    assert 'data-a="brollnote" data-sid="s1"' in cards[0] and 'value="Corte para tela do app"' in cards[0]
    assert "+ B-roll" in cards[1] and 'data-a="brollnote"' not in cards[1]


def test_scene_model_and_storyboard_defaults_without_broll():
    video = _video()
    scene = Scene(
        id="s1",
        video_id=video.id,
        idx=0,
        narration="Narração de teste com tamanho adequado.",
        caption="Legenda",
        label="Cena 1",
        image_prompt="Descrição do prompt visual com mais de 10 caracteres.",
    )
    assert scene.broll_enabled is False
    assert scene.broll_note is None

    html, _ = render_video_workspace(video, active_area="cenas", script=_Script(), scenes=[scene])
    assert "+ B-roll" in html and 'aria-pressed="false"' in html

    start_tag = '<script type="application/json" id="storyboard-data">'
    assert start_tag in html
    data = json.loads(html.split(start_tag, 1)[1].split("</script>", 1)[0])
    assert len(data["scenes"]) == 1
    assert data["scenes"][0]["broll_enabled"] is False
    assert data["scenes"][0]["broll_note"] is None


def test_storyboard_page_js_persists_broll_through_the_scene_endpoint():
    html, _ = render_video_workspace(_video(), active_area="cenas", script=_Script(), scenes=[
        {"id": "s1", "narration": "Cena 1 com broll", "image_prompt": "Prompt visual 1", "broll_enabled": True,
         "broll_note": "Nota da cena 1"}])
    assert "/broll'" in html and "broll_enabled" in html and "broll_note" in html


def test_repo_scene_from_row_reads_broll_metadata():
    from app.studio.adapters.postgres.repo import _scene_from_row

    row_with_broll = {
        "id": "s" * 32,
        "video_id": "v" * 32,
        "idx": 0,
        "narration": "Narração da cena de teste.",
        "caption": "Legenda da cena",
        "label": "Intro",
        "image_prompt": "Prompt visual detalhado da cena de teste.",
        "claim_ids": ["c1"],
        "asset_id": None,
        "duration_s": 4.5,
        "broll_enabled": True,
        "broll_note": "Corte para tela do aplicativo",
    }
    s1 = _scene_from_row(row_with_broll)
    assert s1.broll_enabled is True
    assert s1.broll_note == "Corte para tela do aplicativo"

    row_without_broll = {
        "id": "s" * 32,
        "video_id": "v" * 32,
        "idx": 1,
        "narration": "Narração da cena sem b-roll.",
        "caption": "Legenda",
        "label": "Cena 2",
        "image_prompt": "Prompt visual detalhado da cena de teste 2.",
    }
    s2 = _scene_from_row(row_without_broll)
    assert s2.broll_enabled is False
    assert s2.broll_note is None


def test_repo_save_scenes_and_load_scenes_sql():
    from unittest.mock import MagicMock
    from app.studio.adapters.postgres.repo import save_scenes, _load_scenes

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    video_id = "a" * 32
    scene = Scene(
        id="b" * 32,
        video_id=video_id,
        idx=0,
        narration="Narração de teste com tamanho adequado.",
        caption="Legenda",
        label="Cena 1",
        image_prompt="Descrição do prompt visual com mais de 10 caracteres.",
        broll_enabled=True,
        broll_note="Exemplo de b-roll",
    )

    save_scenes(mock_conn, video_id, [scene])
    assert mock_cursor.execute.called
    query, params = mock_cursor.execute.call_args[0]
    assert "broll_enabled" in query
    assert "broll_note" in query
    assert True in params
    assert "Exemplo de b-roll" in params

    # Test _load_scenes
    mock_cursor.fetchall.return_value = [
        {
            "id": scene.id,
            "video_id": video_id,
            "idx": 0,
            "narration": scene.narration,
            "caption": scene.caption,
            "label": scene.label,
            "image_prompt": scene.image_prompt,
            "claim_ids": [],
            "asset_id": None,
            "duration_s": None,
            "broll_enabled": True,
            "broll_note": "Exemplo de b-roll",
        }
    ]
    loaded = _load_scenes(mock_conn, video_id)
    assert len(loaded) == 1
    assert loaded[0].broll_enabled is True
    assert loaded[0].broll_note == "Exemplo de b-roll"

