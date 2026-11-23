"""O retorno do Google não cai na tela antiga: o fluxo de Conexões conclui na própria tela de Conexões.

O `state` do fluxo de Conexões (`BeginAccountConsent`) é um nonce sem prefixo de projeto; só o fluxo
legado por projeto codifica `<project_id>.<nonce>`. Sem prefixo reconhecido, `/studio/oauth/callback`
repassa `code`/`state`/`error` à tela de Conexões, que já conclui o consentimento pela API.
"""
import base64
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.studio.api.routes import make_router

AUTH = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
GOOGLE_QUERY = ("?state=qfVMiFfzBBGAmbLSAG-WpuQX_XhlIbx4QZtcvaNZzbM&iss=https://accounts.google.com"
                "&code=4/0AUnSYNTHETIC&scope=https://www.googleapis.com/auth/youtube.upload")


def _client():
    app = FastAPI()
    app.include_router(make_router(lambda: None, lambda: True))
    return TestClient(app)


def test_connections_state_is_forwarded_to_the_connections_screen():
    r = _client().get("/studio/oauth/callback" + GOOGLE_QUERY, headers=AUTH, follow_redirects=False)
    assert r.status_code == 303
    target = urlsplit(r.headers["location"])
    assert target.path == "/studio/panel/conexoes"
    query = parse_qs(target.query)
    assert query["code"] == ["4/0AUnSYNTHETIC"]
    assert query["state"] == ["qfVMiFfzBBGAmbLSAG-WpuQX_XhlIbx4QZtcvaNZzbM"]
    assert "iss" not in query and "scope" not in query


def test_provider_error_is_forwarded_to_the_connections_screen():
    r = _client().get("/studio/oauth/callback?error=access_denied&state=abc", headers=AUTH,
                      follow_redirects=False)
    assert r.status_code == 303
    assert parse_qs(urlsplit(r.headers["location"]).query)["error"] == ["access_denied"]


def test_project_prefixed_state_keeps_the_legacy_project_flow():
    state = "a" * 32 + ".nonce"
    r = _client().get(f"/studio/oauth/callback?state={state}&code=x", headers=AUTH, follow_redirects=False)
    assert r.status_code == 200
