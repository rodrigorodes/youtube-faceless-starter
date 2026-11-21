"""Prova de boot do app novo: o renderer sobe (importa `app.main:app`) e as rotas de fachada
respondem. Cobre o `/health` e a rota `/videos`, que existe apenas para declarar que o endpoint
legado (MVP) foi removido.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

LEGACY_MESSAGE = "legacy unauthenticated endpoint removed"


def test_boot_imports_app_and_health_responds():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["ffmpeg"] is True
    assert body["studio_db"] in {"ok", "unavailable"}  # sem banco configurado: degradado, não quebra


def test_legacy_videos_route_is_replaced_by_410():
    client = TestClient(app)
    assert client.get("/videos").status_code == 410
    assert client.post("/videos", json={"topic": "x"}).status_code == 410
    assert client.head("/videos").status_code == 410
    assert LEGACY_MESSAGE in client.get("/videos").json()["detail"]
    nested = client.get("/videos/abc/file")
    assert nested.status_code == 410 and LEGACY_MESSAGE in nested.json()["detail"]
