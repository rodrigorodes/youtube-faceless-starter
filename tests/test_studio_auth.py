import base64
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
from app.studio.api.routes import make_router


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STUDIO_BROWSER_USER", "test-user")
    monkeypatch.setenv("STUDIO_BROWSER_PASSWORD", "test-browser-password")
    monkeypatch.setenv("STUDIO_WORKER_TOKEN", "test-worker-token")
    app = FastAPI()
    app.include_router(make_router(lambda: None, lambda: False))
    return TestClient(app, base_url="http://localhost:8000")


def basic(password="test-browser-password"):
    value = base64.b64encode(f"test-user:{password}".encode()).decode()
    return {"Authorization": f"Basic {value}"}


def test_missing_authentication_fails(client):
    assert client.get("/studio/videos/" + "a" * 32).status_code == 401


def test_basic_and_worker_are_independent(client):
    path = "/studio/videos/" + "a" * 32
    assert client.get(path, headers=basic()).status_code == 503
    assert client.get(path, headers={"Authorization": "Bearer test-worker-token"}).status_code == 503
    assert client.get(path, headers=basic("test-worker-token")).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer test-browser-password"}).status_code == 401


@pytest.mark.parametrize("variable", ["STUDIO_BROWSER_USER", "STUDIO_BROWSER_PASSWORD", "STUDIO_WORKER_TOKEN"])
def test_missing_configuration_fails_closed(client, monkeypatch, variable):
    monkeypatch.delenv(variable)
    assert client.get("/studio/videos/" + "a" * 32, headers=basic()).status_code == 503


def test_shared_password_and_token_fail_closed(client, monkeypatch):
    monkeypatch.setenv("STUDIO_WORKER_TOKEN", "test-browser-password")
    assert client.get("/studio/videos/" + "a" * 32, headers=basic()).status_code == 503


def test_basic_mutation_requires_same_origin_and_worker_rejects_origin(client):
    path = "/studio/videos/" + "a" * 32 + "/approve"
    assert client.post(path, headers=basic()).status_code == 403
    assert client.post(path, headers={**basic(), "Origin": "http://localhost:8000"}).status_code == 503
    assert client.post(path, headers={"Authorization": "Bearer test-worker-token", "Origin": "http://localhost:8000"}).status_code == 403
    assert client.post(path, headers={"Authorization": "Bearer test-worker-token"}).status_code == 503


def test_wrong_origin_and_rebinding_are_rejected_even_with_credentials(client):
    path = "/studio/videos/" + "a" * 32 + "/approve"
    assert client.post(path, headers={**basic(), "Origin": "https://attacker.example"}).status_code == 403
    assert client.post(path, headers={**basic(), "Host": "attacker.example:8000", "Origin": "http://attacker.example:8000"}).status_code == 403
