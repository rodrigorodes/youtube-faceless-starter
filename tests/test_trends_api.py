import base64
import sys
from datetime import datetime, timedelta, timezone
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

BASIC_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


@pytest.fixture()
def api_env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Trends API", niche="Eletronica", language="pt-BR")

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)
    return {"client": client, "videos": videos, "project_id": project.id, "conn": conn}


def _payload(project_id, source_url="https://www.googleapis.com/youtube/v3/search"):
    now = datetime.now(timezone.utc).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {
        "project_id": project_id,
        "items": [
            {
                "topic": "ADE Lineup 2026",
                "source_name": "YouTube Data API",
                "source_url": source_url,
                "observed_at": now,
                "window_start": past,
                "window_end": now,
                "metric_name": "views",
                "metric_value": 1500000.0,
                "evidence": [
                    {"title": "Video 1", "url": "https://youtube.com/watch?v=1", "views": 1500000}
                ],
            }
        ],
    }


def test_trends_ingestion_requires_worker_auth(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    payload = _payload(p_id)

    # Sem auth -> 401
    r_none = client.post("/studio/trends", json=payload)
    assert r_none.status_code == 401

    # Basic auth (navegador) -> 403 (apenas worker)
    r_basic = client.post("/studio/trends", json=payload, headers=BASIC_HEADER)
    assert r_basic.status_code == 403


def test_trends_ingestion_stores_valid_items(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    payload = _payload(p_id)

    r = client.post("/studio/trends", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 202
    assert r.json() == {"stored": 1}


def test_trends_ingestion_refuses_invalid_host(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]
    payload = _payload(p_id, source_url="https://evil.com/trends")

    r = client.post("/studio/trends", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 422


def test_trends_ingestion_project_not_found(api_env):
    client = api_env["client"]
    payload = _payload("0" * 32)

    r = client.post("/studio/trends", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 404


def test_trends_ingestion_empty_batch(api_env):
    client = api_env["client"]
    p_id = api_env["project_id"]

    r = client.post("/studio/trends", json={"project_id": p_id, "items": []}, headers=WORKER_HEADER)
    assert r.status_code == 422
