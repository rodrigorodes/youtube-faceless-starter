"""HTTP do backend de canais (F10-03..07) com Postgres descartável.

Cobre CRUD de canal, catálogo/teste/roteamento de providers, budget hard/soft com painel honesto,
associação YouTube sem tokens na resposta e Project.config sanitizado.
"""
import base64
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402
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
    return {"client": client, "project_id": project.id, "conn": conn, "videos": videos,
            "dsn": dsn, "connect": connect}


# ------------------------------------------------------------------- canais


def test_channel_crud(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.post(f"/studio/projects/{p_id}/channels",
                    json={"name": "História", "strategy": "cronológica", "pillars": ["Roma", "Roma", " Egito "]},
                    headers=WORKER_HEADER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "História"
    assert body["pillars"] == ["Roma", "Egito"]
    assert body["version"] == 1
    profile_id = body["id"]

    got = client.get(f"/studio/projects/{p_id}/channels", headers=WORKER_HEADER)
    assert got.status_code == 200 and got.json()["id"] == profile_id

    listed = client.get("/studio/channels", headers=WORKER_HEADER)
    assert listed.status_code == 200 and [c["id"] for c in listed.json()] == [profile_id]

    patched = client.patch(f"/studio/channels/{profile_id}",
                           json={"expected_version": 1, "changes": {"name": "História Sem Fim", "archived": True}},
                           headers=WORKER_HEADER)
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "História Sem Fim"
    assert patched.json()["version"] == 2

    stale = client.patch(f"/studio/channels/{profile_id}",
                         json={"expected_version": 1, "changes": {"name": "x"}},
                         headers=WORKER_HEADER)
    assert stale.status_code == 409


def test_channel_duplicate_and_project_not_found(api):
    client = api["client"]
    p_id = api["project_id"]
    assert client.post(f"/studio/projects/{p_id}/channels", json={"name": "A"}, headers=WORKER_HEADER).status_code == 201
    dup = client.post(f"/studio/projects/{p_id}/channels", json={"name": "B"}, headers=WORKER_HEADER)
    assert dup.status_code == 409
    missing = client.post(f"/studio/projects/{'0' * 32}/channels", json={"name": "C"}, headers=WORKER_HEADER)
    assert missing.status_code == 404


def test_channel_invalid_name_is_422_not_500(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.post(f"/studio/projects/{p_id}/channels", json={"name": "   "}, headers=WORKER_HEADER)
    assert r.status_code == 422


def test_channel_requires_auth(api):
    assert api["client"].get("/studio/channels").status_code == 401


# ----------------------------------------------------------------- providers


def test_list_providers_reports_availability(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.get(f"/studio/projects/{p_id}/providers", headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    by_kind = {c["kind"]: c for c in r.json()}
    assert by_kind["text"]["availability"] == "AVAILABLE"
    assert by_kind["text"]["name"] == "demo"
    assert by_kind["text"]["cost"]["kind"] == "FREE"
    assert by_kind["text"]["cost"]["label"] == "Sem custo"


def test_provider_connection_test_available_and_unvalidated(api):
    client = api["client"]
    p_id = api["project_id"]
    ok = client.post(f"/studio/projects/{p_id}/providers/test", json={"kind": "text"}, headers=WORKER_HEADER)
    assert ok.status_code == 200, ok.text
    assert ok.json()["available"] is True and ok.json()["checked"] is True

    # provider sem implementação: UNAVAILABLE, nunca finge
    bad = client.post(f"/studio/projects/{p_id}/providers/test",
                      json={"kind": "voice", "spec": "elevenlabs:flash"}, headers=WORKER_HEADER)
    assert bad.status_code == 200
    assert bad.json()["available"] is False
    assert "no implementation" in bad.json()["reason"].lower()


def test_provider_route_uses_economic_profile(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.post(f"/studio/projects/{p_id}/providers/route",
                    json={"kind": "text", "profile": "ECONOMY"}, headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    assert r.json()["primary"]["name"] == "demo"


# -------------------------------------------------------------------- budget


def test_budget_get_defaults_then_put_and_get(api):
    client = api["client"]
    p_id = api["project_id"]
    default = client.get(f"/studio/projects/{p_id}/budget", headers=WORKER_HEADER)
    assert default.status_code == 200, default.text
    assert default.json()["configured"] is False
    assert default.json()["summary"]["labels"]["real"] == "Sem registro de uso"
    assert default.json()["summary"]["has_usage"] is False

    put = client.put(f"/studio/projects/{p_id}/budget",
                     json={"hard_monthly_usd": "20", "soft_monthly_usd": "10",
                           "hard_video_usd": "4", "soft_video_usd": "2", "economic_profile": "ECONOMY"},
                     headers=WORKER_HEADER)
    assert put.status_code == 200, put.text
    assert put.json()["limits"]["hard_monthly_usd"] == "20.00"
    assert put.json()["limits"]["economic_profile"] == "ECONOMY"

    got = client.get(f"/studio/projects/{p_id}/budget", headers=WORKER_HEADER)
    assert got.json()["configured"] is True
    assert got.json()["limits"]["soft_monthly_usd"] == "10.00"


def test_budget_rejects_soft_above_hard(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.put(f"/studio/projects/{p_id}/budget",
                   json={"hard_monthly_usd": "5", "soft_monthly_usd": "9",
                         "hard_video_usd": "1", "soft_video_usd": "1"}, headers=WORKER_HEADER)
    assert r.status_code == 422


# ----------------------------------------------------------- youtube channel


def test_youtube_association_never_returns_tokens(api):
    client = api["client"]
    p_id = api["project_id"]
    before = client.get(f"/studio/projects/{p_id}/youtube-channel", headers=WORKER_HEADER)
    assert before.status_code == 200
    assert before.json()["connected"] is False
    assert before.json()["oauth_status"] == "DISCONNECTED"

    payload = {"channel_id": "UC123", "title": "Canal",
               "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
               "access_token": "ya29.access-secret", "refresh_token": "1//refresh-secret",
               "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    r = client.put(f"/studio/projects/{p_id}/youtube-channel", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    raw = r.text
    assert "ya29.access-secret" not in raw and "1//refresh-secret" not in raw
    assert r.json()["connected"] is True
    assert r.json()["channel_id"] == "UC123"

    after = client.get(f"/studio/projects/{p_id}/youtube-channel", headers=WORKER_HEADER)
    assert after.json()["connected"] is True
    assert "refresh-secret" not in after.text

    gone = client.delete(f"/studio/projects/{p_id}/youtube-channel", headers=WORKER_HEADER)
    assert gone.status_code == 200 and gone.json()["deleted"] is True
    assert client.get(f"/studio/projects/{p_id}/youtube-channel", headers=WORKER_HEADER).json()["connected"] is False


def test_youtube_requires_refresh_token(api):
    client = api["client"]
    p_id = api["project_id"]
    r = client.put(f"/studio/projects/{p_id}/youtube-channel",
                   json={"channel_id": "UC1", "title": "Canal"}, headers=WORKER_HEADER)
    assert r.status_code == 422


# ------------------------------------------------------------- config/segredos


def test_project_config_never_exposes_secrets(api):
    client = api["client"]
    p_id = api["project_id"]
    api["conn"].execute(
        "UPDATE studio.projects SET config = %s WHERE id = %s",
        (Jsonb({"text": "demo", "OPENAI_API_KEY": "sk-live-LEAK", "YOUTUBE_CLIENT_SECRET": "shh"}), p_id),
    )
    api["conn"].commit()
    r = client.get(f"/studio/projects/{p_id}/config", headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    assert r.json()["config"] == {"text": "demo"}
    assert "LEAK" not in r.text and "shh" not in r.text


def test_create_project_response_does_not_carry_config(api):
    r = api["client"].post("/studio/projects", json={"name": "sem config"}, headers=WORKER_HEADER)
    assert r.status_code == 201
    assert "config" not in r.json()
