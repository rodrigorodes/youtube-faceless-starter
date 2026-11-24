"""Testes do endpoint de download e resumo audiovisual (Onda 4 / Task 5)."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresEditorialRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.application.ports import SceneDraft  # noqa: E402
from app.studio.domain.contracts import VideoFormat, VideoStatus  # noqa: E402


def test_download_endpoint_returns_404_when_unrendered(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    project = v_repo.create_project("Canal Download")
    video = v_repo.create_video(project.id, "Tema Não Renderizado", VideoFormat.short)

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/videos/{video.id}/download")
    assert res.status_code == 404
    assert "rendered file not available" in res.json()["detail"]


def test_download_endpoint_serves_mp4_file(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    project = v_repo.create_project("Canal Download Rendered")
    video = v_repo.create_video(project.id, "Tema Renderizado para Download", VideoFormat.short)

    # Cria asset e render_job com output_asset_id
    asset_id = "f" * 32
    job_id = "e" * 32
    rel_path = f"projects/{project.id}/videos/{video.id}/final-{asset_id}.mp4"
    full_path = tmp_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")

    k = "d" * 64
    conn.execute(
        "INSERT INTO studio.assets(id, kind, cache_key, path, provider, model, license) "
        "VALUES (%s, 'video', %s, %s, 'p', 'm', 'CC0')",
        (asset_id, k, rel_path),
    )
    conn.execute(
        "INSERT INTO studio.render_jobs(id, video_id, status, output_asset_id, finished_at, created_at, attempt) "
        "VALUES (%s, %s, 'SUCCEEDED', %s, NOW(), NOW(), 1)",
        (job_id, video.id, asset_id),
    )
    conn.execute(
        "UPDATE studio.videos SET status = 'RENDERED' WHERE id = %s",
        (video.id,),
    )
    conn.commit()

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/videos/{video.id}/download")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "video/mp4"
    assert "attachment" in res.headers.get("content-disposition", "")
    assert res.content == b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def test_composicao_and_qualidade_html_controls(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    project = v_repo.create_project("Canal Workspace")
    video = v_repo.create_video(project.id, "Tema Workspace", VideoFormat.short)

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    # 1. Composição: volume, ducking e estilo ativo
    res_comp = client.get(f"/studio/panel/videos/{video.id}/composicao")
    assert res_comp.status_code == 200, res_comp.text
    html_comp = res_comp.text
    assert 'id="comp-music-vol"' in html_comp
    assert '<input type="range" id="comp-music-vol"' in html_comp
    assert 'disabled' not in html_comp.split('id="comp-music-vol"')[1][:30]
    assert 'id="comp-ducking"' in html_comp
    assert 'disabled' not in html_comp.split('id="comp-ducking"')[1][:30]
    assert 'Destaque por palavra (karaokê)' in html_comp
    assert 'id="comp-music-track"' in html_comp

    # 2. Qualidade: botão de download e resumo audiovisual
    res_qual = client.get(f"/studio/panel/videos/{video.id}/qualidade")
    assert res_qual.status_code == 200, res_qual.text
    html_qual = res_qual.text
    assert 'id="btn-baixar-mp4"' in html_qual
    assert f'/studio/videos/{video.id}/download' in html_qual
    assert 'Resumo audiovisual desta versão' in html_qual
