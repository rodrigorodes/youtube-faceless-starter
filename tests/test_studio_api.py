import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

DEAD = "postgresql://x:y@127.0.0.1:1/z"


def client_for(studio):
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app)


@pytest.fixture()
def client(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    return client_for(Studio(Settings(database_url=dsn, storage_root=tmp_path)))


@pytest.fixture()
def video_id(client):
    pid = client.post("/studio/projects", json={"name": "canal"}).json()["id"]
    r = client.post("/studio/videos", json={"project_id": pid, "topic": "ADE 2026", "format": "short"})
    assert r.status_code == 201
    return r.json()["id"]


def test_create_and_get_video(client, video_id):
    r = client.get(f"/studio/videos/{video_id}")
    assert r.status_code == 200 and r.json()["status"] == "IDEA" and r.json()["privacy"] == "private"


def test_video_for_unknown_project_is_404(client):
    r = client.post("/studio/videos", json={"project_id": "0" * 32, "topic": "ADE 2026", "format": "short"})
    assert r.status_code == 404


def test_transition_conflict_is_409(client, video_id):
    body = {"expected": "IDEA", "new": "SCRIPTED"}
    assert client.post(f"/studio/videos/{video_id}/transition", json=body).status_code == 200
    assert client.post(f"/studio/videos/{video_id}/transition", json=body).status_code == 409


def test_forbidden_transition_is_422_and_state_untouched(client, video_id):
    r = client.post(f"/studio/videos/{video_id}/transition", json={"expected": "IDEA", "new": "RENDERED"})
    assert r.status_code == 422
    assert client.get(f"/studio/videos/{video_id}").json()["status"] == "IDEA"


def test_bad_ids_are_rejected(client):
    assert client.get("/studio/videos/" + "A" * 32).status_code == 422
    assert client.get("/studio/videos/..%2Fetc").status_code in (404, 422)
    assert client.get("/studio/videos/" + "0" * 32).status_code == 404
    assert client.post("/studio/videos/" + "A" * 32 + "/transition", json={"expected": "IDEA", "new": "SCRIPTED"}).status_code == 422


def test_unknown_status_value_is_422(client, video_id):
    assert client.post(f"/studio/videos/{video_id}/transition", json={"expected": "IDEA", "new": "NOPE"}).status_code == 422


def test_health_with_db(dsn, conn, tmp_path, monkeypatch):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    monkeypatch.setattr(main, "studio", Studio(Settings(database_url=dsn, storage_root=tmp_path)))
    r = TestClient(main.app).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "ffmpeg": True, "studio_db": "ok"}


@pytest.mark.parametrize("url", [None, DEAD])
def test_health_and_studio_survive_db_down(url, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "studio", Studio(Settings(database_url=url, storage_root=tmp_path)))
    c = TestClient(main.app)
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["ffmpeg"] is True and r.json()["studio_db"] == "unavailable"
    assert c.post("/studio/projects", json={"name": "x"}).status_code == 503
    assert c.get("/studio/videos/" + "0" * 32).status_code == 503


def test_nul_byte_is_422_not_500(client):
    assert client.post("/studio/projects", json={"name": "a\u0000b"}).status_code == 422


@pytest.mark.parametrize("target", ["APPROVED", "REJECTED", "PUBLISHED"])
def test_generic_endpoint_cannot_approve_reject_or_publish(client, video_id, target):
    r = client.post(f"/studio/videos/{video_id}/transition", json={"expected": "AWAITING_APPROVAL", "new": target})
    assert r.status_code == 403
    assert client.get(f"/studio/videos/{video_id}").json()["status"] == "IDEA"
