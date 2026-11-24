import sys
from pathlib import Path
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import (  # noqa: E402
    PostgresEditorialRepository, PostgresScriptRepository,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import (  # noqa: E402
    SceneAsset, VideoFormat, VideoStatus,
)


def _create_asset(conn, asset_id: str):
    conn.execute(
        "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
        "VALUES (%s, 'image', %s, %s, 'test_provider', 'test_model', 'CC0') "
        "ON CONFLICT (id) DO NOTHING",
        (asset_id, hashlib_key(asset_id), f"cache/{asset_id}.png"),
    )


def hashlib_key(seed: str) -> str:
    import hashlib
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal_test")
    video = videos.create_video(project.id, "Video Test", VideoFormat.short)
    scripts = PostgresEditorialRepository(connect)
    drafts = [
        SceneDraft("Primeira cena de teste válida.", "Legenda 1", "LBL1", "prompt visual um", []),
        SceneDraft("Segunda cena de teste válida.", "Legenda 2", "LBL2", "prompt visual dois", []),
    ]
    scripts.save_and_advance(video.id, "Roteiro base", drafts, [], VideoStatus.IDEA, VideoStatus.SCRIPTED)
    return {
        "connect": connect,
        "conn": conn,
        "video": video,
        "scripts": scripts,
    }


def test_postgres_editorial_repository_is_available():
    assert issubclass(PostgresEditorialRepository, PostgresScriptRepository) or PostgresEditorialRepository is PostgresScriptRepository


def test_insert_and_retrieve_multiple_scene_assets(env):
    scenes = env["scripts"].scenes(env["video"].id)
    scene = scenes[0]

    asset1_id = uuid.uuid4().hex
    asset2_id = uuid.uuid4().hex
    _create_asset(env["conn"], asset1_id)
    _create_asset(env["conn"], asset2_id)
    env["conn"].commit()

    sa1 = SceneAsset(
        scene_id=scene.id,
        asset_id=asset1_id,
        position=0,
        start_s=0.0,
        end_s=2.5,
        role="base",
        motion="zoom_in",
        transition_kind="fade",
        transition_duration_s=0.5,
    )
    sa2 = SceneAsset(
        scene_id=scene.id,
        asset_id=asset2_id,
        position=1,
        start_s=2.5,
        end_s=5.0,
        role="overlay",
        motion="none",
        transition_kind="cut",
        transition_duration_s=0.0,
    )

    env["scripts"].save_scene_assets(scene.id, [sa1, sa2])

    loaded_assets = env["scripts"].get_scene_assets(scene.id)
    assert len(loaded_assets) == 2
    assert loaded_assets[0].position == 0
    assert loaded_assets[0].asset_id == asset1_id
    assert loaded_assets[0].start_s == 0.0
    assert loaded_assets[0].end_s == 2.5
    assert loaded_assets[0].role == "base"
    assert loaded_assets[0].motion == "zoom_in"
    assert loaded_assets[0].transition_kind == "fade"
    assert loaded_assets[0].transition_duration_s == 0.5

    assert loaded_assets[1].position == 1
    assert loaded_assets[1].asset_id == asset2_id
    assert loaded_assets[1].start_s == 2.5
    assert loaded_assets[1].end_s == 5.0
    assert loaded_assets[1].role == "overlay"
    assert loaded_assets[1].motion == "none"
    assert loaded_assets[1].transition_kind == "cut"

    # Also check through env["scripts"].scenes(video.id)
    reloaded_scenes = env["scripts"].scenes(env["video"].id)
    assert len(reloaded_scenes[0].assets) == 2
    assert reloaded_scenes[0].assets[0].asset_id == asset1_id
    assert reloaded_scenes[0].assets[1].asset_id == asset2_id


def test_cascade_delete_with_scene(env):
    scenes = env["scripts"].scenes(env["video"].id)
    scene = scenes[0]

    asset_id = uuid.uuid4().hex
    _create_asset(env["conn"], asset_id)
    env["conn"].commit()

    sa = SceneAsset(
        scene_id=scene.id,
        asset_id=asset_id,
        position=0,
        start_s=0.0,
        end_s=3.0,
    )
    env["scripts"].save_scene_assets(scene.id, [sa])

    assert len(env["scripts"].get_scene_assets(scene.id)) == 1

    # Delete the scene from studio.scenes
    env["conn"].execute("DELETE FROM studio.scenes WHERE id = %s", (scene.id,))
    env["conn"].commit()

    # studio.scene_assets should have cascade-deleted the asset
    count = env["conn"].execute(
        "SELECT COUNT(*) FROM studio.scene_assets WHERE scene_id = %s", (scene.id,)
    ).fetchone()[0]
    assert count == 0


def test_scene_without_assets_returns_empty_list(env):
    scenes = env["scripts"].scenes(env["video"].id)
    scene = scenes[0]
    assert env["scripts"].get_scene_assets(scene.id) == []
    assert scene.assets == []


def test_scene_asset_timing_validation():
    with pytest.raises(ValueError, match="end_s .* must be greater than start_s"):
        SceneAsset(
            scene_id="s1",
            asset_id="a1",
            position=0,
            start_s=3.0,
            end_s=3.0,
        )

    with pytest.raises(ValueError, match="end_s .* must be greater than start_s"):
        SceneAsset(
            scene_id="s1",
            asset_id="a1",
            position=0,
            start_s=4.0,
            end_s=2.0,
        )


def test_unique_position_constraint(env):
    scenes = env["scripts"].scenes(env["video"].id)
    scene = scenes[0]

    asset1_id = uuid.uuid4().hex
    asset2_id = uuid.uuid4().hex
    _create_asset(env["conn"], asset1_id)
    _create_asset(env["conn"], asset2_id)
    env["conn"].commit()

    # Direct insert with conflicting (scene_id, position)
    env["conn"].execute(
        "INSERT INTO studio.scene_assets (id, scene_id, asset_id, position, start_s, end_s) "
        "VALUES (gen_random_uuid(), %s, %s, 0, 0.0, 2.0)",
        (scene.id, asset1_id),
    )
    env["conn"].commit()

    with pytest.raises(psycopg.errors.UniqueViolation):
        env["conn"].execute(
            "INSERT INTO studio.scene_assets (id, scene_id, asset_id, position, start_s, end_s) "
            "VALUES (gen_random_uuid(), %s, %s, 0, 2.0, 4.0)",
            (scene.id, asset2_id),
        )
        env["conn"].commit()
    env["conn"].rollback()
