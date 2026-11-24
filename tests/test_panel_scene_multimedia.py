"""Testes da bancada da cena com tomadas multishot e gerenciamento de scene_assets (Onda 4 / Task 4)."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresEditorialRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import VideoFormat, VideoStatus, SceneAsset  # noqa: E402


def test_editorial_repo_add_and_delete_scene_asset(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    e_repo = PostgresEditorialRepository(connect)

    project = v_repo.create_project("Canal SceneAssets")
    video = v_repo.create_video(project.id, "Tema SceneAssets", VideoFormat.short)

    drafts = [
        SceneDraft("Cena 1 para teste de tomadas.", "Legenda 1", "LBL1", "prompt visual longo de teste", []),
    ]
    e_repo.save_and_advance(video.id, "Roteiro base", drafts, [], VideoStatus.IDEA, VideoStatus.SCRIPTED)
    scenes = e_repo.scenes(video.id)
    assert len(scenes) == 1
    scene_id = scenes[0].id

    # Criação de asset
    aid1 = "1" * 32
    aid2 = "2" * 32
    k1 = "a" * 64
    k2 = "b" * 64
    conn.execute(
        "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
        "VALUES (%s, 'image', %s, 'path/1.png', 'p', 'm', 'CC0'), "
        "       (%s, 'video', %s, 'path/2.mp4', 'p', 'm', 'CC0') "
        "ON CONFLICT DO NOTHING",
        (aid1, k1, aid2, k2),
    )
    conn.commit()

    sa1 = SceneAsset(
        scene_id=scene_id,
        asset_id=aid1,
        position=0,
        start_s=0.0,
        end_s=2.5,
        motion="zoom_in",
    )
    sa2 = SceneAsset(
        scene_id=scene_id,
        asset_id=aid2,
        position=1,
        start_s=2.5,
        end_s=5.0,
        motion="none",
    )

    e_repo.add_scene_asset(scene_id, sa1)
    e_repo.add_scene_asset(scene_id, sa2)

    loaded = e_repo.get_scene_assets(scene_id)
    assert len(loaded) == 2
    assert loaded[0].asset_id == aid1
    assert loaded[0].motion == "zoom_in"
    assert loaded[1].asset_id == aid2

    # Deletar 1
    e_repo.delete_scene_asset(str(sa1.id))
    loaded_after = e_repo.get_scene_assets(scene_id)
    assert len(loaded_after) == 1
    assert loaded_after[0].asset_id == aid2


def test_api_scene_assets_crud_endpoints(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    e_repo = PostgresEditorialRepository(connect)

    project = v_repo.create_project("Canal API SceneAssets")
    video = v_repo.create_video(project.id, "Tema API SceneAssets", VideoFormat.short)

    drafts = [
        SceneDraft("Cena 1 texto.", "Legenda 1", "LBL1", "prompt visual longo de teste", []),
    ]
    e_repo.save_and_advance(video.id, "Roteiro base", drafts, [], VideoStatus.IDEA, VideoStatus.SCRIPTED)
    scenes = e_repo.scenes(video.id)
    scene_id = scenes[0].id

    aid_api = "3" * 32
    k_api = "c" * 64
    conn.execute(
        "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
        "VALUES (%s, 'image', %s, 'path/a.png', 'p', 'm', 'CC0') "
        "ON CONFLICT DO NOTHING",
        (aid_api, k_api),
    )
    conn.commit()

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    # 1. GET lista vazia
    res_get = client.get(f"/studio/videos/{video.id}/scenes/{scene_id}/assets")
    assert res_get.status_code == 200
    assert res_get.json() == []

    # 2. POST adiciona asset
    payload = {
        "asset_id": aid_api,
        "position": 0,
        "start_s": 0.0,
        "end_s": 3.0,
        "motion": "zoom_in",
        "transition_kind": "none",
        "transition_duration_s": 0.0,
    }
    res_post = client.post(f"/studio/videos/{video.id}/scenes/{scene_id}/assets", json=payload)
    assert res_post.status_code == 201, res_post.text
    created = res_post.json()
    assert created["asset_id"] == aid_api
    asset_id_db = created["id"]

    # 3. GET lista com 1
    res_get2 = client.get(f"/studio/videos/{video.id}/scenes/{scene_id}/assets")
    assert res_get2.status_code == 200
    assert len(res_get2.json()) == 1

    # 4. DELETE asset
    res_del = client.delete(f"/studio/videos/{video.id}/scenes/{scene_id}/assets/{asset_id_db}")
    assert res_del.status_code == 200
    assert res_del.json()["ok"] is True

    # 5. GET lista vazia novamente
    res_get3 = client.get(f"/studio/videos/{video.id}/scenes/{scene_id}/assets")
    assert res_get3.status_code == 200
    assert res_get3.json() == []


def test_storyboard_card_renders_tomadas_section(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    e_repo = PostgresEditorialRepository(connect)

    project = v_repo.create_project("Canal Storyboard")
    video = v_repo.create_video(project.id, "Tema Storyboard", VideoFormat.short)

    drafts = [
        SceneDraft("Cena 1 com tomadas.", "Legenda 1", "LBL1", "prompt visual longo de teste", []),
    ]
    e_repo.save_and_advance(video.id, "Roteiro base", drafts, [], VideoStatus.IDEA, VideoStatus.SCRIPTED)

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/panel/videos/{video.id}/cenas")
    assert res.status_code == 200, res.text
    html = res.text
    assert "TOMADAS DESTA CENA" in html
    assert "+ Adicionar mídia" in html
    assert "Ritmo:" in html
