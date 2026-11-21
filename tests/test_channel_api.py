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


def test_put_project_config_validates_persists_and_never_echoes_rejected_values(api):
    client = api["client"]
    p_id = api["project_id"]
    valid = {"text": "demo", "image": "placeholder", "voice": "piper:pt_BR-faber-medium",
             "renderer": "ffmpeg:rich"}
    r = client.put(f"/studio/projects/{p_id}/config", json=valid, headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    assert r.json()["config"] == valid
    assert client.get(f"/studio/projects/{p_id}/config", headers=WORKER_HEADER).json()["config"] == valid

    # chave desconhecida (com valor com cara de segredo) -> 422 e o valor não vaza
    extra = client.put(f"/studio/projects/{p_id}/config",
                       json={**valid, "OPENAI_API_KEY": "sk-live-LEAK"}, headers=WORKER_HEADER)
    assert extra.status_code == 422
    assert "OPENAI_API_KEY" in extra.text and "LEAK" not in extra.text

    # provedor inexistente -> 422 (antes: 200 e só quebrava no render, em `provider_for`)
    ghost = client.put(f"/studio/projects/{p_id}/config",
                       json={**valid, "text": "nope-do-not-echo"}, headers=WORKER_HEADER)
    assert ghost.status_code == 422, ghost.text
    assert "nope-do-not-echo" not in ghost.text  # o valor ofensor não vaza
    assert "demo" in ghost.text and "opencode" in ghost.text  # mas a mensagem diz o que existe

    # spec em branco -> 422
    assert client.put(f"/studio/projects/{p_id}/config",
                      json={**valid, "text": "   "}, headers=WORKER_HEADER).status_code == 422
    # nome de provedor vazio (":x") -> 422 sem ecoar o valor ofensor
    empty_name = client.put(f"/studio/projects/{p_id}/config",
                            json={**valid, "text": ":x-do-not-echo"}, headers=WORKER_HEADER)
    assert empty_name.status_code == 422
    assert "x-do-not-echo" not in empty_name.text
    # valor não-string -> 422 apenas com a mensagem (sem o valor)
    non_string = client.put(f"/studio/projects/{p_id}/config",
                            json={**valid, "text": 123}, headers=WORKER_HEADER)
    assert non_string.status_code == 422
    assert "123" not in non_string.text
    # porta faltando -> 422 listando as portas ausentes
    missing = client.put(f"/studio/projects/{p_id}/config",
                         json={"text": "demo"}, headers=WORKER_HEADER)
    assert missing.status_code == 422 and "image" in missing.text and "renderer" in missing.text
    # o config persistido não mudou depois das recusas
    assert client.get(f"/studio/projects/{p_id}/config", headers=WORKER_HEADER).json()["config"] == valid


def test_put_project_config_accepts_registered_but_unvalidated_provider_and_catalog_tells_the_reason(api):
    client = api["client"]
    p_id = api["project_id"]
    valid = {"text": "demo", "image": "placeholder", "voice": "piper", "renderer": "ffmpeg"}
    # `veo` está registrado mas não validado: aceitar não trava o usuário; o catálogo conta o motivo.
    r = client.put(f"/studio/projects/{p_id}/config",
                   json={**valid, "image": "veo:veo-3.1"}, headers=WORKER_HEADER)
    assert r.status_code == 200, r.text
    assert r.json()["config"]["image"] == "veo:veo-3.1"
    assert client.get(f"/studio/projects/{p_id}/config", headers=WORKER_HEADER).json()["config"]["image"] == "veo:veo-3.1"
    cards = client.get(f"/studio/projects/{p_id}/providers", headers=WORKER_HEADER).json()
    image = next(c for c in cards if c["kind"] == "image")
    assert image["name"] == "veo" and image["availability"] == "UNAVAILABLE"
    assert image["reason"]  # motivo real exposto, não silêncio


def test_create_project_response_does_not_carry_config(api):
    r = api["client"].post("/studio/projects", json={"name": "sem config"}, headers=WORKER_HEADER)
    assert r.status_code == 201
    assert "config" not in r.json()


def test_channel_api_round_trips_the_style_reference(api):
    from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository
    style = PostgresVisualStyleRepository(api["connect"]).create("Cinemático")
    p_id = api["project_id"]
    created = api["client"].post(f"/studio/projects/{p_id}/channels",
                                 json={"name": "História", "style_id": style.id}, headers=WORKER_HEADER)
    assert created.status_code == 201 and created.json()["style_id"] == style.id
    assert api["client"].get(f"/studio/projects/{p_id}/channels", headers=WORKER_HEADER).json()["style_id"] == style.id


def test_channel_api_refuses_a_channel_pointing_to_an_unknown_style(api):
    other = api["videos"].create_project("Outro", niche="Geral", language="pt-BR")
    r = api["client"].post(f"/studio/projects/{other.id}/channels",
                           json={"name": "História", "style_id": "f" * 32}, headers=WORKER_HEADER)
    assert r.status_code == 422 and "style" in r.json()["detail"].lower()


def test_channel_api_round_trips_the_youtube_target(api):
    from app.studio.adapters.postgres.youtube_identity_repo import PostgresYouTubeChannelIdentityRepository
    from app.studio.domain.youtube_identity import YouTubeChannelIdentity
    PostgresYouTubeChannelIdentityRepository(api["connect"]).upsert(
        YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    p_id = api["project_id"]

    created = api["client"].post(f"/studio/projects/{p_id}/channels",
                                 json={"name": "História", "youtube_channel_id": "UCabc123"}, headers=WORKER_HEADER)
    assert created.status_code == 201, created.text
    assert created.json()["youtube_channel_id"] == "UCabc123"
    got = api["client"].get(f"/studio/projects/{p_id}/channels", headers=WORKER_HEADER)
    assert got.json()["youtube_channel_id"] == "UCabc123"

    profile_id = created.json()["id"]
    cleared = api["client"].patch(f"/studio/channels/{profile_id}",
                                  json={"expected_version": 1, "changes": {"youtube_channel_id": None}},
                                  headers=WORKER_HEADER)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["youtube_channel_id"] is None


def test_channel_api_refuses_a_channel_pointing_to_an_unknown_youtube_channel(api):
    other = api["videos"].create_project("Outro", niche="Geral", language="pt-BR")
    r = api["client"].post(f"/studio/projects/{other.id}/channels",
                           json={"name": "História", "youtube_channel_id": "UCinexistente"}, headers=WORKER_HEADER)
    assert r.status_code == 422 and "youtube" in r.json()["detail"].lower()
