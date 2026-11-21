"""HTTP da biblioteca de estilos (VS-05a) com Postgres descartável.

Cobre criar/listar/editar/arquivar, os 404/422/409, o round-trip dos parâmetros e a contagem de
uso medida (`channels_using`). O estilo é compartilhado: nenhum endpoint pede `project_id`.
"""
import base64
import sys
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

BASIC_HEADER = {
    "Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode(),
    "Origin": "http://testserver",
}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


@pytest.fixture()
def api(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="Geral", language="pt-BR")
    settings = Settings(database_url=dsn, storage_root=tmp_path)
    studio = Studio(settings, environ={"STUDIO_TEXT": "demo", "STUDIO_IMAGE": "placeholder"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)
    return {"client": client, "project_id": project.id, "conn": conn, "videos": videos, "connect": connect}


# ----------------------------------------------------------------- biblioteca


def test_style_crud_round_trips_params(api):
    client = api["client"]
    params = {"motion": ["zoom_in"], "music": {"bpm": 110},
              "caption": {"font_size": 58}, "extra": {"lut": "warm"}}
    created = client.post("/studio/styles", json={"name": "Documentário Cinemático", "params": params},
                          headers=WORKER_HEADER)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Documentário Cinemático"
    assert body["params"] == params
    assert body["version"] == 1 and body["archived"] is False
    assert body["channels_using"] == 0
    style_id = body["id"]

    got = client.get(f"/studio/styles/{style_id}", headers=WORKER_HEADER)
    assert got.status_code == 200 and got.json()["id"] == style_id
    listed = client.get("/studio/styles", headers=WORKER_HEADER)
    assert listed.status_code == 200 and [s["id"] for s in listed.json()] == [style_id]

    patched = client.patch(f"/studio/styles/{style_id}",
                           json={"expected_version": 1, "changes": {"name": "Cinemático", "params": {"music": {"bpm": 122}}}},
                           headers=WORKER_HEADER)
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Cinemático"
    assert patched.json()["params"] == {"music": {"bpm": 122}}
    assert patched.json()["version"] == 2


def test_style_archive_is_soft_delete(api):
    client = api["client"]
    style_id = client.post("/studio/styles", json={"name": "Arquivável"}, headers=WORKER_HEADER).json()["id"]
    archived = client.post(f"/studio/styles/{style_id}/archive", headers=WORKER_HEADER)
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    # Some da lista padrão, mas continua existindo; o nome libera para reúso.
    assert client.get("/studio/styles", headers=WORKER_HEADER).json() == []
    assert client.get("/studio/styles?include_archived=true", headers=WORKER_HEADER).json()[0]["archived"] is True
    assert client.get(f"/studio/styles/{style_id}", headers=WORKER_HEADER).status_code == 200
    again = client.post("/studio/styles", json={"name": "Arquivável"}, headers=WORKER_HEADER)
    assert again.status_code == 201, again.text


def test_style_not_found_is_404(api):
    client = api["client"]
    missing = "a" * 32
    assert client.get(f"/studio/styles/{missing}", headers=WORKER_HEADER).status_code == 404
    patch = client.patch(f"/studio/styles/{missing}",
                         json={"expected_version": 1, "changes": {"name": "x"}}, headers=WORKER_HEADER)
    assert patch.status_code == 404
    assert client.post(f"/studio/styles/{missing}/archive", headers=WORKER_HEADER).status_code == 404


def test_style_invalid_params_is_422_with_a_clear_message(api):
    client = api["client"]
    r = client.post("/studio/styles", json={"name": "Ruim", "params": {"music": {"bpm": 999}}},
                    headers=WORKER_HEADER)
    assert r.status_code == 422
    assert "bpm" in r.json()["detail"]
    assert "Traceback" not in r.text  # nada de stack trace para o operador

    unknown = client.post("/studio/styles", json={"name": "Ruim", "params": {"colour": "#fff"}},
                          headers=WORKER_HEADER)
    assert unknown.status_code == 422 and "colour" in unknown.json()["detail"]


def test_style_duplicate_and_version_conflict_are_409(api):
    client = api["client"]
    first = client.post("/studio/styles", json={"name": "Cinemático"}, headers=WORKER_HEADER)
    assert first.status_code == 201
    dup = client.post("/studio/styles", json={"name": "cinemático"}, headers=WORKER_HEADER)
    assert dup.status_code == 409  # único sem distinguir caixa

    style_id = first.json()["id"]
    ok = client.patch(f"/studio/styles/{style_id}", json={"expected_version": 1, "changes": {"name": "v2"}},
                      headers=WORKER_HEADER)
    assert ok.status_code == 200
    stale = client.patch(f"/studio/styles/{style_id}", json={"expected_version": 1, "changes": {"name": "v3"}},
                         headers=WORKER_HEADER)
    assert stale.status_code == 409


def test_style_unknown_update_field_is_422(api):
    client = api["client"]
    style_id = client.post("/studio/styles", json={"name": "Estilo"}, headers=WORKER_HEADER).json()["id"]
    r = client.patch(f"/studio/styles/{style_id}", json={"expected_version": 1, "changes": {"colour": "#fff"}},
                     headers=WORKER_HEADER)
    assert r.status_code == 422


def test_style_requires_auth(api):
    assert api["client"].get("/studio/styles").status_code == 401
    assert api["client"].get("/studio/panel/estilos").status_code == 401


def test_channels_using_is_measured_not_estimated(api):
    client = api["client"]
    style_id = client.post("/studio/styles", json={"name": "Cinemático"}, headers=WORKER_HEADER).json()["id"]
    videos = api["videos"]
    for name in ("A", "B"):
        project = videos.create_project(name, niche="", language="pt-BR")
        created = client.post(f"/studio/projects/{project.id}/channels",
                              json={"name": name, "style_id": style_id}, headers=WORKER_HEADER)
        assert created.status_code == 201, created.text
    # Um canal sem estilo não entra na conta.
    empty = videos.create_project("C", niche="", language="pt-BR")
    assert client.post(f"/studio/projects/{empty.id}/channels", json={"name": "C"},
                       headers=WORKER_HEADER).status_code == 201

    listed = client.get("/studio/styles", headers=WORKER_HEADER).json()
    assert listed[0]["channels_using"] == 2
    assert client.get(f"/studio/styles/{style_id}", headers=WORKER_HEADER).json()["channels_using"] == 2
