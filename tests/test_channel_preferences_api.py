import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate
from app.studio.api.routes import make_router
from app.studio.composition import Settings, Studio

WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


@pytest.fixture()
def client(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    settings = Settings(database_url=dsn, storage_root=tmp_path)
    studio = Studio(settings)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return TestClient(app, headers=WORKER_HEADER)


def test_api_channel_transactional_creation(client):
    body = {
        "name": "Canal API Transacional",
        "niche": "Negócios",
        "default_mode": "diretor",
        "default_format": "long",
        "hard_monthly_usd": 30.0,
        "soft_monthly_usd": 15.0,
    }
    resp = client.post("/studio/channels/transactional", json=body, headers={"Idempotency-Key": "api-key-1"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["project"]["name"] == "Canal API Transacional"
    assert data["profile"]["default_mode"] == "diretor"
    assert data["profile"]["default_format"] == "long"
    assert data["budget"]["hard_monthly_usd"] == 30.0
    assert data["budget"]["soft_monthly_usd"] == 15.0


def test_api_channel_transactional_idempotent_replay(client):
    body = {
        "name": "Canal Replay",
        "niche": "História",
        "default_mode": "diretor",
        "default_format": "long",
        "hard_monthly_usd": 50.0,
    }
    resp1 = client.post("/studio/channels/transactional", json=body, headers={"Idempotency-Key": "replay-key-1"})
    assert resp1.status_code == 201
    data1 = resp1.json()

    resp2 = client.post("/studio/channels/transactional", json=body, headers={"Idempotency-Key": "replay-key-1"})
    assert resp2.status_code == 201
    data2 = resp2.json()

    assert data1["project"]["id"] == data2["project"]["id"]
    assert data1["profile"]["id"] == data2["profile"]["id"]
    assert data1["budget"]["project_id"] == data2["budget"]["project_id"]


def test_api_channel_transactional_idempotency_conflict(client):
    body1 = {"name": "Canal Original", "niche": "Geral"}
    body2 = {"name": "Canal Divergente", "niche": "Geral"}

    resp1 = client.post("/studio/channels/transactional", json=body1, headers={"Idempotency-Key": "conflict-key"})
    assert resp1.status_code == 201

    resp2 = client.post("/studio/channels/transactional", json=body2, headers={"Idempotency-Key": "conflict-key"})
    assert resp2.status_code == 409
    assert "Idempotency conflict" in resp2.json()["detail"]


def test_api_channel_transactional_invalid_key_format(client):
    body = {"name": "Canal Chave Invalida"}
    resp = client.post("/studio/channels/transactional", json=body, headers={"Idempotency-Key": "INVALID KEY WITH SPACES"})
    assert resp.status_code == 422


def test_api_channel_transactional_without_idempotency_key(client):
    body = {"name": "Canal Sem Chave"}
    resp = client.post("/studio/channels/transactional", json=body)
    assert resp.status_code == 201
    assert resp.json()["project"]["name"] == "Canal Sem Chave"


def test_api_video_creation_with_production_mode(client):
    c_resp = client.post("/studio/channels/transactional", json={"name": "Canal Video Mode"})
    assert c_resp.status_code == 201
    p_id = c_resp.json()["project"]["id"]

    v_resp = client.post(f"/studio/projects/{p_id}/videos", json={
        "topic": "Vídeo no modo diretor",
        "format": "short",
        "production_mode": "diretor",
    })
    assert v_resp.status_code == 201
    assert v_resp.json()["production_mode"] == "diretor"

    # Default production_mode
    v_default = client.post(f"/studio/projects/{p_id}/videos", json={
        "topic": "Vídeo no modo default",
        "format": "short",
    })
    assert v_default.status_code == 201
    assert v_default.json()["production_mode"] == "piloto"


def test_api_channel_profile_get_and_patch_preferences(client):
    c_resp = client.post("/studio/channels/transactional", json={
        "name": "Canal Patch Prefs",
        "default_mode": "piloto",
        "default_format": "short",
    })
    assert c_resp.status_code == 201
    p_id = c_resp.json()["project"]["id"]
    prof_id = c_resp.json()["profile"]["id"]

    # GET
    get_resp = client.get(f"/studio/projects/{p_id}/channels")
    assert get_resp.status_code == 200
    assert get_resp.json()["default_mode"] == "piloto"
    assert get_resp.json()["default_format"] == "short"

    # PATCH
    patch_resp = client.patch(f"/studio/channels/{prof_id}", json={
        "expected_version": 1,
        "changes": {
            "default_mode": "diretor",
            "default_format": "long",
        },
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["default_mode"] == "diretor"
    assert patch_resp.json()["default_format"] == "long"
    assert patch_resp.json()["version"] == 2

    # Verify persisted via GET
    get_resp2 = client.get(f"/studio/projects/{p_id}/channels")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["default_mode"] == "diretor"
    assert get_resp2.json()["default_format"] == "long"
