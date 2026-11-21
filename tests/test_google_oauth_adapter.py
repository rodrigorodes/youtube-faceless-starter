"""F8-05: cliente OAuth real (httpx injetável, offline). Nenhum token/segredo vaza em erro/log."""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.google_oauth import GoogleOAuthClient, google_oauth_from_client_secret  # noqa: E402
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, OAuthConfigurationError, OAuthReconnectRequired, OAuthTransientError, pkce_pair,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ACCESS = "ya29.SYNTHETIC_access_value_only_for_tests"
REFRESH = "1//SYNTHETIC_refresh_value_only_for_tests"
SECRET = "SYNTHETIC_client_secret_value"


def client(handler, **kwargs):
    calls = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    return GoogleOAuthClient("client-id.apps.googleusercontent.com", SECRET,
                             transport=httpx.MockTransport(wrapped), clock=lambda: NOW, **kwargs), calls


def body_of(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()} if request.content else {}


def test_authorization_url_is_built_from_the_configured_app_and_exact_redirect():
    app, _ = client(lambda request: httpx.Response(500))
    verifier, challenge = pkce_pair()
    url = app.authorization_url("http://localhost:8000/studio/oauth/callback", DEFAULT_SCOPES,
                                "state-abcdefghijklmnop", challenge)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_secret" not in url and SECRET not in url and verifier not in url
    with pytest.raises(ValueError):
        app.authorization_url("http://evil.example/callback", DEFAULT_SCOPES, "state-abcdefghijklmnop", challenge)


def test_exchange_code_posts_the_code_verifier_and_parses_tokens():
    def handler(request):
        assert request.method == "POST" and str(request.url) == "https://oauth2.googleapis.com/token"
        form = body_of(request)
        assert form["grant_type"] == "authorization_code" and form["code"] == "code-123"
        assert form["code_verifier"] == "v" * 64 and form["redirect_uri"] == "http://localhost:8000/studio/oauth/callback"
        assert form["client_id"] == "client-id.apps.googleusercontent.com" and form["client_secret"] == SECRET
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        return httpx.Response(200, json={"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600,
                                         "scope": " ".join(DEFAULT_SCOPES), "token_type": "Bearer"})

    app, calls = client(handler)
    response = app.exchange_code("code-123", "http://localhost:8000/studio/oauth/callback", "v" * 64)
    assert response.access_token == ACCESS and response.refresh_token == REFRESH
    assert response.expires_in == 3600 and set(response.scopes) == set(DEFAULT_SCOPES)
    assert len(calls) == 1 and "Authorization" not in calls[0].headers


def test_refresh_sends_only_the_refresh_grant_and_never_follows_redirects():
    def handler(request):
        form = body_of(request)
        assert form == {"grant_type": "refresh_token", "refresh_token": REFRESH,
                        "client_id": "client-id.apps.googleusercontent.com", "client_secret": SECRET}
        return httpx.Response(200, json={"access_token": ACCESS, "expires_in": 1800, "scope": " ".join(DEFAULT_SCOPES)})

    app, calls = client(handler)
    refreshed = app.refresh(REFRESH)
    assert refreshed.access_token == ACCESS and refreshed.expires_in == 1800
    assert len(calls) == 1 and calls[0].headers["accept"] == "application/json"


@pytest.mark.parametrize("status,error,exception", [
    (400, "invalid_grant", OAuthReconnectRequired),
    (401, "invalid_client", OAuthConfigurationError),
    (400, "invalid_scope", OAuthConfigurationError),
    (429, "rateLimitExceeded", OAuthTransientError),
    (503, "backendError", OAuthTransientError),
])
def test_token_endpoint_errors_are_classified_without_leaking_the_body(status, error, exception):
    leak = f"{ACCESS} {REFRESH} {SECRET}"
    app, _ = client(lambda request: httpx.Response(status, json={"error": error, "error_description": leak}))
    with pytest.raises(exception) as caught:
        app.exchange_code("code-123", "http://localhost:8000/cb", "v" * 64)
    text = str(caught.value)
    assert ACCESS not in text and REFRESH not in text and SECRET not in text
    assert error in text  # o código do erro é diagnóstico seguro


def test_network_failure_is_transient_and_does_not_echo_the_request():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    app, _ = client(handler)
    with pytest.raises(OAuthTransientError) as caught:
        app.refresh(REFRESH)
    assert REFRESH not in str(caught.value) and "ConnectError" in str(caught.value)


def test_identity_uses_the_bearer_token_and_returns_the_real_channel():
    def handler(request):
        assert request.method == "GET" and str(request.url).startswith("https://www.googleapis.com/youtube/v3/channels?")
        assert request.headers["authorization"] == f"Bearer {ACCESS}"
        assert "mine=true" in str(request.url)
        return httpx.Response(200, json={"items": [{"id": "UC_synthetic_channel", "snippet": {"title": "Canal de teste"}}]})

    app, _ = client(handler)
    identity = app.identity(ACCESS)
    assert identity.channel_id == "UC_synthetic_channel" and identity.title == "Canal de teste"


def test_identity_without_a_channel_requires_reconnect():
    app, _ = client(lambda request: httpx.Response(200, json={"items": []}))
    with pytest.raises(OAuthReconnectRequired, match="no YouTube channel"):
        app.identity(ACCESS)


def test_revoke_is_idempotent_and_never_sends_the_secret():
    def handler(request):
        assert request.method == "POST" and str(request.url) == "https://oauth2.googleapis.com/revoke"
        assert body_of(request) == {"token": REFRESH}
        assert SECRET not in request.content.decode()
        return httpx.Response(200, json={})

    app, _ = client(handler)
    app.revoke(REFRESH)

    broken = lambda request: httpx.Response(400, json={"error": "invalid_token"})
    app, _ = client(broken)
    app.revoke(REFRESH)  # revogado duas vezes não é falha


def test_revoke_server_error_is_transient():
    app, _ = client(lambda request: httpx.Response(503, json={"error": "backendError"}))
    with pytest.raises(OAuthTransientError):
        app.revoke(REFRESH)


def test_nothing_sensitive_is_logged(caplog):
    app, _ = client(lambda request: httpx.Response(200, json={
        "access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600, "scope": " ".join(DEFAULT_SCOPES)}))
    with caplog.at_level(logging.DEBUG):
        app.exchange_code("code-123", "http://localhost:8000/cb", "v" * 64)
    assert ACCESS not in caplog.text and REFRESH not in caplog.text and SECRET not in caplog.text


def test_client_can_be_built_from_the_web_client_secret_json_without_copying_it(tmp_path):
    secret_file = tmp_path / "client-secret-synthetic.json"
    secret_file.write_text(json.dumps({"web": {
        "client_id": "client-id.apps.googleusercontent.com", "client_secret": SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8000/studio/oauth/callback"]}}), encoding="utf-8")
    app = google_oauth_from_client_secret(secret_file, redirect_uri="http://localhost:8000/studio/oauth/callback",
                                          transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert SECRET not in repr(app) and SECRET not in str(app)
    url = app.authorization_url("http://localhost:8000/studio/oauth/callback", DEFAULT_SCOPES,
                                "state-abcdefghijklmnop", pkce_pair()[1])
    assert "client-id.apps.googleusercontent.com" in url and SECRET not in url
    with pytest.raises(OAuthConfigurationError):
        google_oauth_from_client_secret(secret_file, redirect_uri="https://other.example/callback")


def test_malformed_client_secret_json_is_rejected_without_echoing_content(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"web": {"client_id": "", "client_secret": SECRET}}))
    with pytest.raises(OAuthConfigurationError) as caught:
        google_oauth_from_client_secret(bad)
    assert SECRET not in str(caught.value)

def test_web_app_without_redirect_uris_still_builds_and_only_accepts_a_safe_callback(tmp_path):
    secret_file = tmp_path / "client-secret-synthetic.json"
    secret_file.write_text(json.dumps({"web": {
        "client_id": "client-id.apps.googleusercontent.com", "client_secret": SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth"}}), encoding="utf-8")
    app = google_oauth_from_client_secret(secret_file, redirect_uri="http://localhost:8000/studio/oauth/callback",
                                          transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert app.authorization_url("http://localhost:8000/studio/oauth/callback", DEFAULT_SCOPES,
                                 "state-abcdefghijklmnop", pkce_pair()[1]).startswith("https://accounts.google.com/")
    with pytest.raises(ValueError):
        app.authorization_url("http://evil.example/cb", DEFAULT_SCOPES, "state-abcdefghijklmnop", pkce_pair()[1])
