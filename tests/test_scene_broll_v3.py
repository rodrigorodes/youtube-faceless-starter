"""Testes de metadados de B-Roll em cenas (F02/V3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.domain.contracts import Scene, Video, VideoFormat, VideoStatus


def test_storyboard_renders_broll_controls_for_focused_scene():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    scenes = [
        {
            "scene_id": "sc1",
            "narration": "Texto da cena com b-roll ativo.",
            "broll_enabled": True,
            "broll_note": "Corte para tela do app",
        }
    ]
    html = render_video_workspace(video, active_area="cenas", script=None, scenes=scenes, sources=[])
    assert 'id="cena-broll-enabled"' in html or 'name="broll_enabled"' in html
    assert 'id="cena-broll-note"' in html or 'name="broll_note"' in html
    assert 'id="cena-broll-note-wrap"' in html
    assert "Corte para tela do app" in html


def test_scene_model_and_storyboard_defaults_without_broll():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
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

    html, _ = render_video_workspace(video, active_area="cenas", scenes=[scene])
    assert 'id="cena-broll-enabled"' in html
    assert 'id="cena-broll-note"' in html

    # Parse scenesData from script tag
    start_tag = '<script type="application/json" id="storyboard-scenes-data">'
    assert start_tag in html
    data_str = html.split(start_tag, 1)[1].split("</script>", 1)[0]
    scenes_data = json.loads(data_str)
    assert len(scenes_data) == 1
    assert scenes_data[0]["broll_enabled"] is False
    assert scenes_data[0]["broll_note"] is None


def test_storyboard_page_js_syncs_and_updates_broll_in_scenes_data():
    video = Video(id="v" * 32, project_id="p" * 32, topic="Tema", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    scenes = [
        {
            "id": "s1",
            "narration": "Cena 1 com broll",
            "image_prompt": "Prompt visual 1",
            "broll_enabled": True,
            "broll_note": "Nota da cena 1",
        },
        {
            "id": "s2",
            "narration": "Cena 2 sem broll",
            "image_prompt": "Prompt visual 2",
            "broll_enabled": False,
            "broll_note": None,
        },
    ]
    html, _ = render_video_workspace(video, active_area="cenas", scenes=scenes)

    # JS listeners and synchronization in PAGE_JS
    assert "cena-broll-enabled" in html
    assert "cena-broll-note" in html
    assert "broll_enabled" in html
    assert "broll_note" in html
    assert "renderActiveScene" in html


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

