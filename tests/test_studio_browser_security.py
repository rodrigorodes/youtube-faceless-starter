import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.routes import make_router


def test_cross_origin_browser_cannot_mutate_studio():
    app = FastAPI()
    app.include_router(make_router(lambda: None, lambda: False))
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.post("/studio/videos/" + "a" * 32 + "/approve",
                           headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403


def test_dns_rebinding_host_is_denied():
    app = FastAPI()
    app.include_router(make_router(lambda: None, lambda: False))
    client = TestClient(app, base_url="http://localhost:8000")
    response = client.post("/studio/videos/" + "a" * 32 + "/approve",
                           headers={"Host": "attacker.example:8000"})
    assert response.status_code == 403


def test_same_origin_and_internal_clients_reach_application():
    app = FastAPI()
    app.include_router(make_router(lambda: None, lambda: False))
    client = TestClient(app, base_url="http://localhost:8000")
    path = "/studio/videos/" + "a" * 32 + "/approve"
    assert client.post(path, auth=("test-user", "test-browser-password"), headers={"Origin": "http://localhost:8000"}).status_code == 503
    assert client.post(path, headers={"Authorization": "Bearer test-worker-token"}).status_code == 503
