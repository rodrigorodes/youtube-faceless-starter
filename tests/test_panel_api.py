import base64
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}


@pytest.fixture()
def client_env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Teste", niche="Eletronica", language="pt-BR")

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)
    return {"client": client, "videos": videos, "project_id": project.id, "conn": conn}


def test_panel_data_requires_auth(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel/data")
    assert r.status_code == 401


def test_panel_data_host_guard(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel/data", headers={**AUTH_HEADER, "Host": "evil.com"})
    assert r.status_code == 403


def test_panel_data_returns_200_and_payload(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Painel", VideoFormat.short)
    r = client.get("/studio/panel/data?days=7", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert "totals" in data
    assert "month" in data
    assert "topics" in data
    assert len(data["topics"]) == 1
    assert data["topics"][0]["label"] == "Tema Painel"


def test_panel_data_invalid_days(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel/data?days=5", headers=AUTH_HEADER)
    assert r.status_code == 422


def test_panel_video_data_invalid_id(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel/videos/bad-id/data", headers=AUTH_HEADER)
    assert r.status_code == 422


def test_panel_video_data_not_found(client_env):
    client = client_env["client"]
    r = client.get(f"/studio/panel/videos/{'a'*32}/data", headers=AUTH_HEADER)
    assert r.status_code == 404


def test_panel_video_data_never_exposes_upload_uri(client_env):
    client = client_env["client"]
    videos = client_env["videos"]
    conn = client_env["conn"]
    p_id = client_env["project_id"]

    v = videos.create_video(p_id, "Tema Publicado", VideoFormat.short)
    secret_uri = "https://youtube.googleapis.com/upload/SECRET_URI_RESUMABLE_999"

    conn.execute(
        "INSERT INTO studio.publications (id, video_id, status, attempt, upload_uri, error) "
        "VALUES (%s, %s, 'FAILED', 1, %s, 'Erro')",
        (uuid.uuid4().hex, v.id, secret_uri),
    )
    conn.commit()

    r = client.get(f"/studio/panel/videos/{v.id}/data", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert secret_uri not in r.text
