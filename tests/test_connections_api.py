"""YT-04a: HTTP das Conexões (conta → autorizações → canais) com Postgres descartável.

O `OAuthClient` é um duplo injetado (nenhuma chamada ao Google). Cobre o round-trip dos endpoints,
o token fora das respostas, o vínculo do canal do estúdio pelo `PATCH /channels` existente e os
erros (422 para estado/referência inválidos, 404 para alvo inexistente).
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
from app.studio import composition  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, OAuthIdentity, OAuthTokenResponse, authorization_url,
)

WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}
ACCESS = "ya29.SYNTHETIC_api_access_value"
REFRESH = "1//SYNTHETIC_api_refresh_value"


class OAuthFake:
    """Duplo do `OAuthClient`: nenhuma rede; a identidade (canal + e-mail) é ajustável."""

    def __init__(self):
        self.identity_value = OAuthIdentity(channel_id="UC_principal", title="Canal principal", email="EU@gmail.com")
        self.revoked = []

    def authorization_url(self, redirect_uri, scopes, state, code_challenge):
        return authorization_url(client_id="client-id.apps.googleusercontent.com", redirect_uri=redirect_uri,
                                 scopes=scopes, state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=("http://localhost:8000/studio/oauth/callback",))

    def exchange_code(self, code, redirect_uri, code_verifier):
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=REFRESH, expires_in=3600, scopes=DEFAULT_SCOPES)

    def refresh(self, refresh_token):  # pragma: no cover
        raise AssertionError("refresh não deveria ser chamado")

    def revoke(self, token):
        self.revoked.append(token)

    def identity(self, access_token):
        return self.identity_value


@pytest.fixture()
def api(conn, dsn, tmp_path, monkeypatch):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="Geral", language="pt-BR")
    oauth = OAuthFake()
    monkeypatch.setattr(composition, "build_google_oauth", lambda settings: oauth)
    settings = Settings(database_url=dsn, storage_root=tmp_path)
    studio = Studio(settings, environ={"STUDIO_TEXT": "demo", "STUDIO_IMAGE": "placeholder"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "project_id": project.id, "oauth": oauth, "connect": connect}


def _connect(client, *, code="code-123"):
    started = client.post("/studio/connections/oauth/start", headers=WORKER_HEADER)
    assert started.status_code == 200, started.text
    started_body = started.json()
    assert started_body["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    done = client.post("/studio/connections/oauth/callback",
                       json={"code": code, "state": started_body["state"]}, headers=WORKER_HEADER)
    assert done.status_code == 200, done.text
    return started_body, done.json()


def test_connections_consent_round_trip_never_leaks_tokens(api):
    client = api["client"]
    _, consent = _connect(client)
    assert consent["account"]["email"] == "EU@gmail.com"
    assert consent["channel"] == {"youtube_channel_id": "UC_principal", "title": "Canal principal"}
    assert consent["status"] == "CONNECTED" and consent["grant_id"]

    raw = client.post("/studio/connections/oauth/callback", json={"code": "x", "state": "y"},
                      headers=WORKER_HEADER)
    assert raw.status_code == 422  # estado inválido nunca troca o código

    board = client.get("/studio/connections", headers=WORKER_HEADER)
    assert board.status_code == 200, board.text
    assert ACCESS not in board.text and REFRESH not in board.text
    channels = board.json()["accounts"][0]["channels"]
    assert channels[0]["youtube_channel_id"] == "UC_principal" and channels[0]["status"] == "CONNECTED"


def test_connections_link_studio_channel_through_existing_patch(api):
    client, p_id = api["client"], api["project_id"]
    _, consent = _connect(client)
    created = client.post(f"/studio/projects/{p_id}/channels", json={"name": "História"}, headers=WORKER_HEADER)
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    linked = client.patch(f"/studio/channels/{profile_id}",
                          json={"expected_version": 1, "changes": {"youtube_channel_id": "UC_principal"}},
                          headers=WORKER_HEADER)
    assert linked.status_code == 200, linked.text
    assert linked.json()["youtube_channel_id"] == "UC_principal"

    channel = client.get("/studio/connections", headers=WORKER_HEADER).json()["accounts"][0]["channels"][0]
    assert channel["studio_channels"] == [{"id": profile_id, "name": "História", "archived": False}]

    # destino inexistente (nunca validado) -> 422
    ghost = client.patch(f"/studio/channels/{profile_id}",
                         json={"expected_version": 2, "changes": {"youtube_channel_id": "UC_fantasma"}},
                         headers=WORKER_HEADER)
    assert ghost.status_code == 422 and "youtube" in ghost.json()["detail"].lower()
    assert consent["grant_id"]  # sanity


def test_connections_revoke_is_isolated_and_404s_for_unknown(api):
    client = api["client"]
    _, first = _connect(client)
    api["oauth"].identity_value = OAuthIdentity(channel_id="UC_secundario", title="Canal secundário", email="EU@gmail.com")
    _, second = _connect(client, code="code-456")

    revoked = client.post(f"/studio/connections/authorizations/{first['grant_id']}/UC_principal/revoke",
                          headers=WORKER_HEADER)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"grant_id": first["grant_id"], "youtube_channel_id": "UC_principal", "status": "REVOKED"}

    channels = client.get("/studio/connections", headers=WORKER_HEADER).json()["accounts"][0]["channels"]
    by_id = {c["youtube_channel_id"]: c for c in channels}
    assert by_id["UC_principal"]["status"] == "REVOKED"
    assert by_id["UC_secundario"]["status"] == "CONNECTED"  # o outro canal da conta segue conectado

    missing = client.post(f"/studio/connections/authorizations/{second['grant_id']}/UC_fantasma/revoke",
                          headers=WORKER_HEADER)
    assert missing.status_code == 404
    invalid = client.post("/studio/connections/authorizations/not-an-id/UC_principal/revoke", headers=WORKER_HEADER)
    assert invalid.status_code == 422


def test_connections_require_auth(api):
    assert api["client"].get("/studio/connections").status_code == 401
    assert api["client"].post("/studio/connections/oauth/start").status_code == 401
