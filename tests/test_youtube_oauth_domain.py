"""F8-05: regras puras de OAuth do YouTube — sem rede, sem SDK, sem segredo em repr."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES,
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_UPLOAD_SCOPE,
    OAuthConfigurationError,
    OAuthReconnectRequired,
    OAuthScopeMissing,
    OAuthTokenResponse,
    OAuthTokenSet,
    OAuthTransientError,
    authorization_url,
    classify_token_error,
    derive_channel_status,
    mask,
    pkce_pair,
    token_set_from_response,
    validate_scopes,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def test_scopes_require_youtube_upload_and_reject_unknown_or_blank():
    assert validate_scopes([YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE, YOUTUBE_UPLOAD_SCOPE]) == (
        YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE)
    assert validate_scopes(DEFAULT_SCOPES) == DEFAULT_SCOPES
    for scopes in ([], [YOUTUBE_READONLY_SCOPE], [""], ["not-a-url"]):
        with pytest.raises(OAuthScopeMissing):
            validate_scopes(scopes)


def test_scopes_accept_the_openid_names_google_adds_to_the_token_response():
    # ao pedir `userinfo.email`, o Google devolve também `openid` (e às vezes `email`/`profile`)
    granted = ["https://www.googleapis.com/auth/userinfo.email", "openid", YOUTUBE_UPLOAD_SCOPE,
               YOUTUBE_READONLY_SCOPE, "email", "profile"]
    assert validate_scopes(granted) == tuple(granted)
    with pytest.raises(OAuthScopeMissing):
        validate_scopes([YOUTUBE_UPLOAD_SCOPE, "OPENID"])  # só os nomes padrão exatos


def test_authorization_url_is_offline_consent_with_pkce_and_no_secret():
    verifier, challenge = pkce_pair()
    url = authorization_url(client_id="client-123.apps.googleusercontent.com",
                            redirect_uri="http://localhost:8000/studio/oauth/callback",
                            scopes=DEFAULT_SCOPES, state="state-abcdefghijklmn", code_challenge=challenge)
    parts = urlsplit(url)
    assert parts.scheme == "https" and parts.hostname == "accounts.google.com" and parts.path == "/o/oauth2/v2/auth"
    query = parse_qs(parts.query)
    assert query["response_type"] == ["code"] and query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"] and query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state-abcdefghijklmn"] and query["code_challenge"] == [challenge]
    assert set(query["scope"][0].split()) == set(DEFAULT_SCOPES)
    assert "client_secret" not in query and "secret" not in url.lower()
    assert 43 <= len(verifier) <= 128 and challenge != verifier


def test_authorization_url_refuses_an_insecure_redirect_or_blank_client():
    _, challenge = pkce_pair()
    for kwargs in (
        {"client_id": "", "redirect_uri": "http://localhost/cb"},
        {"client_id": "client", "redirect_uri": "https://evil.example/cb"},
        {"client_id": "client", "redirect_uri": "javascript:alert(1)"},
        {"client_id": "client", "redirect_uri": "http://localhost/cb", "state": ""},
        {"client_id": "client", "redirect_uri": "http://localhost/cb", "code_challenge": ""},
    ):
        with pytest.raises(ValueError):
            authorization_url(scopes=DEFAULT_SCOPES, state=kwargs.pop("state", "s"), code_challenge=kwargs.pop("code_challenge", challenge), **kwargs)


def test_pkce_pair_is_deterministic_only_when_a_verifier_is_given_and_is_s256():
    verifier, challenge = pkce_pair("a" * 64)
    assert verifier == "a" * 64
    assert challenge == "_-BU_nrgy23GXDr5th1SCfQ5hR20PQulmXM33xVGaOs"
    with pytest.raises(ValueError):
        pkce_pair("short")
    with pytest.raises(ValueError):
        pkce_pair("a" * 43 + "!")


def test_token_set_expiry_is_derived_with_skew_and_never_prints_secret():
    response = OAuthTokenResponse(access_token="ya29.access-secret-value", refresh_token="1//refresh-secret",
                                  expires_in=3600, scopes=(YOUTUBE_UPLOAD_SCOPE,))
    tokens = token_set_from_response(response, now=NOW)
    assert tokens.expires_at == NOW + timedelta(seconds=3600)
    assert tokens.refresh_token == "1//refresh-secret"
    assert not tokens.is_expired(NOW)
    assert tokens.is_expired(NOW + timedelta(seconds=3600 - 120))  # 2 min de folga para não usar token vencendo
    assert tokens.is_expired(NOW + timedelta(hours=2))
    text = f"{tokens!r} {tokens!s}"
    assert "access-secret-value" not in text and "1//refresh-secret" not in text
    assert "…" in text
    assert mask("ya29.abcdef") == "ya2…cdef"


def test_token_response_rejects_a_blank_access_token_or_nonsense_expiry():
    for response in (
        OAuthTokenResponse(access_token="", refresh_token=None, expires_in=3600, scopes=DEFAULT_SCOPES),
        OAuthTokenResponse(access_token="x", refresh_token=None, expires_in=0, scopes=DEFAULT_SCOPES),
        OAuthTokenResponse(access_token="x", refresh_token=None, expires_in=-1, scopes=DEFAULT_SCOPES),
    ):
        with pytest.raises(ValueError):
            token_set_from_response(response, now=NOW)


@pytest.mark.parametrize("status,code,error", [
    (400, "invalid_grant", OAuthReconnectRequired),
    (401, "invalid_client", OAuthConfigurationError),
    (400, "invalid_scope", OAuthConfigurationError),
    (429, None, OAuthTransientError),
    (500, None, OAuthTransientError),
    (503, "backend_error", OAuthTransientError),
    (None, None, OAuthTransientError),
    (400, "weird", OAuthReconnectRequired),
])
def test_token_error_classification_is_explicit(status, code, error):
    assert classify_token_error(status, code) is error


def test_channel_status_derives_from_the_real_vault_state():
    assert derive_channel_status(has_credentials=False, revoked=False, expires_at=None, now=NOW) == "DISCONNECTED"
    assert derive_channel_status(has_credentials=True, revoked=True, expires_at=NOW + timedelta(hours=1), now=NOW) == "REVOKED"
    assert derive_channel_status(has_credentials=True, revoked=False, expires_at=NOW, now=NOW) == "EXPIRED"
    assert derive_channel_status(has_credentials=True, revoked=False, expires_at=NOW + timedelta(minutes=5), now=NOW) == "CONNECTED"
    assert derive_channel_status(has_credentials=True, revoked=False, expires_at=None, now=NOW, stored="ERROR") == "ERROR"