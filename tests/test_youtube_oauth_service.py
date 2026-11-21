"""F8-05: consentimento, refresh e revogação com o cofre de segredos (sem rede real)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.youtube_channels import (  # noqa: E402
    ACCESS_TOKEN, REFRESH_TOKEN, GetYouTubeChannel,
)
from app.studio.application.youtube_oauth import (  # noqa: E402
    BeginConsent, CompleteConsent, EnsureAccessToken, RevokeConsent,
)
from app.studio.domain.youtube_channel import YouTubeChannel  # noqa: E402
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, YOUTUBE_READONLY_SCOPE, YOUTUBE_UPLOAD_SCOPE, OAuthIdentity, OAuthReconnectRequired,
    OAuthScopeMissing, OAuthTokenResponse, authorization_url,
)

PID = "a" * 32
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ACCESS = "ya29.SYNTHETIC_access_value_only_for_tests"
REFRESH = "1//SYNTHETIC_refresh_value_only_for_tests"


class Secrets:
    def __init__(self):
        self.data = {}

    def get(self, scope, key):
        return self.data.get((scope, key))

    def set(self, scope, key, value):
        self.data[(scope, key)] = value

    def delete(self, scope, key):
        self.data.pop((scope, key), None)

    def names(self, scope):
        return tuple(sorted(k for (s, k) in self.data if s == scope))


class Channels:
    def __init__(self):
        self.rows = {}

    def get(self, project_id):
        return self.rows.get(project_id)

    def upsert(self, channel):
        self.rows[channel.project_id] = channel
        return channel

    def delete(self, project_id):
        return self.rows.pop(project_id, None) is not None


class OAuthFake:
    def __init__(self):
        self.exchange_error = None
        self.refresh_error = None
        self.revoke_error = None
        self.exchange_calls = []
        self.refresh_calls = []
        self.revoked = []
        self.channel = OAuthIdentity(channel_id="UC_synthetic", title="Canal autorizado")

    def authorization_url(self, redirect_uri, scopes, state, code_challenge):
        return authorization_url(client_id="client-id.apps.googleusercontent.com", redirect_uri=redirect_uri,
                                 scopes=scopes, state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=("http://localhost:8000/studio/oauth/callback",))

    def exchange_code(self, code, redirect_uri, code_verifier):
        self.exchange_calls.append((code, redirect_uri, code_verifier))
        if self.exchange_error:
            raise self.exchange_error
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=REFRESH, expires_in=3600,
                                  scopes=DEFAULT_SCOPES)

    def refresh(self, refresh_token):
        self.refresh_calls.append(refresh_token)
        if self.refresh_error:
            raise self.refresh_error
        return OAuthTokenResponse(access_token=ACCESS + ".new", refresh_token=None, expires_in=1800,
                                  scopes=DEFAULT_SCOPES)

    def revoke(self, token):
        self.revoked.append(token)
        if self.revoke_error:
            raise self.revoke_error

    def identity(self, access_token):
        assert access_token in (ACCESS, ACCESS + ".new")
        return self.channel


def services(secrets=None, channels=None, oauth=None):
    secrets, channels, oauth = secrets or Secrets(), channels or Channels(), oauth or OAuthFake()
    clock = lambda: NOW
    begin = BeginConsent(oauth, secrets, clock=clock, redirect_uri="http://localhost:8000/studio/oauth/callback")
    complete = CompleteConsent(oauth, channels, secrets, clock=clock, redirect_uri="http://localhost:8000/studio/oauth/callback")
    ensure = EnsureAccessToken(oauth, channels, secrets, clock=clock)
    revoke = RevokeConsent(oauth, channels, secrets, clock=clock)
    return begin, complete, ensure, revoke


def test_begin_consent_stores_state_and_verifier_and_returns_only_the_url():
    secrets = Secrets()
    begin, *_ = services(secrets=secrets)
    out = begin.execute(PID)
    assert out["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge=" in out["authorization_url"] and "state=" in out["authorization_url"]
    assert ACCESS not in str(out) and REFRESH not in str(out) and "client_secret" not in str(out)
    scope = f"youtube:{PID}"
    assert secrets.get(scope, "oauth_state") == out["state"]
    assert len(secrets.get(scope, "oauth_code_verifier")) >= 43
    assert secrets.get(scope, "oauth_state_expires_at") == (NOW + timedelta(minutes=10)).isoformat()
    with pytest.raises(ValueError):
        BeginConsent(OAuthFake(), secrets, redirect_uri="https://evil.example/cb").execute(PID)


def test_complete_consent_refuses_wrong_or_expired_state_before_calling_google():
    secrets, oauth = Secrets(), OAuthFake()
    begin, complete, *_ = services(secrets=secrets, oauth=oauth)
    out = begin.execute(PID)
    with pytest.raises(Exception, match="state"):
        complete.execute(PID, "code-123", "wrong-state-abcdefghijklmnop")
    assert oauth.exchange_calls == []
    secrets.set(f"youtube:{PID}", "oauth_state_expires_at", (NOW - timedelta(seconds=1)).isoformat())
    with pytest.raises(Exception, match="expired"):
        complete.execute(PID, "code-123", out["state"])
    assert oauth.exchange_calls == [] and secrets.names(f"youtube:{PID}")


def test_complete_consent_stores_real_tokens_and_channel_identity():
    secrets, channels, oauth = Secrets(), Channels(), OAuthFake()
    begin, complete, _, _ = services(secrets=secrets, channels=channels, oauth=oauth)
    state = begin.execute(PID)["state"]
    result = complete.execute(PID, "code-123", state)
    scope = f"youtube:{PID}"
    verifier = oauth.exchange_calls[0][2]
    assert 43 <= len(verifier) <= 128
    assert oauth.exchange_calls[0][:2] == ("code-123", "http://localhost:8000/studio/oauth/callback")
    assert secrets.get(scope, ACCESS_TOKEN) == ACCESS and secrets.get(scope, REFRESH_TOKEN) == REFRESH
    assert secrets.get(scope, "token_expires_at") == (NOW + timedelta(seconds=3600)).isoformat()
    assert secrets.get(scope, "oauth_state") is None and secrets.get(scope, "oauth_code_verifier") is None
    assert channels.get(PID).channel_id == "UC_synthetic" and channels.get(PID).title == "Canal autorizado"
    assert set(channels.get(PID).scopes) == set(DEFAULT_SCOPES)
    assert result["oauth_status"] == "CONNECTED" and result["connected"] is True
    assert ACCESS not in str(result) and REFRESH not in str(result)


def test_complete_consent_requires_the_upload_scope_and_writes_nothing_on_failure():
    secrets, channels, oauth = Secrets(), Channels(), OAuthFake()
    oauth.exchange_code = lambda code, redirect_uri, verifier: OAuthTokenResponse(
        access_token=ACCESS, refresh_token=REFRESH, expires_in=3600, scopes=(YOUTUBE_READONLY_SCOPE,))
    begin, complete, *_ = services(secrets=secrets, channels=channels, oauth=oauth)
    state = begin.execute(PID)["state"]
    with pytest.raises(OAuthScopeMissing):
        complete.execute(PID, "code-123", state)
    assert channels.get(PID) is None
    assert secrets.get(f"youtube:{PID}", ACCESS_TOKEN) is None and secrets.get(f"youtube:{PID}", REFRESH_TOKEN) is None


def test_complete_consent_invalid_grant_does_not_create_a_channel():
    secrets, channels, oauth = Secrets(), Channels(), OAuthFake()
    oauth.exchange_error = OAuthReconnectRequired("invalid_grant")
    begin, complete, *_ = services(secrets=secrets, channels=channels, oauth=oauth)
    state = begin.execute(PID)["state"]
    with pytest.raises(OAuthReconnectRequired):
        complete.execute(PID, "code-123", state)
    assert channels.get(PID) is None and secrets.get(f"youtube:{PID}", REFRESH_TOKEN) is None


def _connected():
    secrets, channels, oauth = Secrets(), Channels(), OAuthFake()
    _, complete, ensure, revoke = services(secrets=secrets, channels=channels, oauth=oauth)
    begin = BeginConsent(oauth, secrets, clock=lambda: NOW, redirect_uri="http://localhost:8000/studio/oauth/callback")
    complete.execute(PID, "code-123", begin.execute(PID)["state"])
    return secrets, channels, oauth, ensure, revoke


def test_ensure_access_token_uses_a_valid_token_without_refreshing():
    secrets, channels, oauth, ensure, _ = _connected()
    assert ensure.execute(PID) == ACCESS and oauth.refresh_calls == []


def test_ensure_access_token_refreshes_an_expired_token_and_preserves_the_refresh_token():
    secrets, channels, oauth, ensure, _ = _connected()
    secrets.set(f"youtube:{PID}", "token_expires_at", (NOW - timedelta(minutes=1)).isoformat())
    assert ensure.execute(PID) == ACCESS + ".new"
    assert oauth.refresh_calls == [REFRESH]
    assert secrets.get(f"youtube:{PID}", REFRESH_TOKEN) == REFRESH  # a resposta não trouxe novo refresh
    assert secrets.get(f"youtube:{PID}", "token_expires_at") == (NOW + timedelta(seconds=1800)).isoformat()


def test_ensure_access_token_without_consent_refuses_and_marks_revoked_on_invalid_grant():
    secrets, channels, oauth, ensure, _ = _connected()
    with pytest.raises(OAuthReconnectRequired):
        services(secrets=Secrets(), channels=Channels(), oauth=OAuthFake())[2].execute(PID)
    oauth.refresh_error = OAuthReconnectRequired("invalid_grant")
    secrets.set(f"youtube:{PID}", "token_expires_at", (NOW - timedelta(minutes=1)).isoformat())
    with pytest.raises(OAuthReconnectRequired):
        ensure.execute(PID)
    assert secrets.get(f"youtube:{PID}", "oauth_revoked") == "1"
    assert secrets.get(f"youtube:{PID}", ACCESS_TOKEN) is None
    assert channels.get(PID).oauth_status.value == "REVOKED"


def test_revoke_calls_google_deletes_tokens_and_reports_revoked():
    secrets, channels, oauth, _, revoke = _connected()
    result = revoke.execute(PID)
    assert oauth.revoked == [REFRESH]
    assert secrets.get(f"youtube:{PID}", ACCESS_TOKEN) is None and secrets.get(f"youtube:{PID}", REFRESH_TOKEN) is None
    assert result["oauth_status"] == "REVOKED" and result["connected"] is False
    revoke.execute(PID)  # idempotente, sem tokens
    assert oauth.revoked == [REFRESH]


def test_channel_status_comes_from_the_vault_not_the_typed_row():
    secrets, channels, _, _, _ = _connected()
    # O banco diz "expira em 1h", mas o token real no cofre venceu: EXPIRED.
    channels.upsert(YouTubeChannel(project_id=PID, channel_id="UC_synthetic", title="Canal",
                                   token_expires_at=NOW + timedelta(hours=1)))
    secrets.set(f"youtube:{PID}", "token_expires_at", (NOW - timedelta(minutes=1)).isoformat())
    assert GetYouTubeChannel(channels, secrets, now=lambda: NOW).execute(PID)["oauth_status"] == "EXPIRED"
    # O contrário: banco vencido, cofre válido: CONNECTED.
    channels.upsert(YouTubeChannel(project_id=PID, channel_id="UC_synthetic", title="Canal",
                                   token_expires_at=NOW - timedelta(minutes=1)))
    secrets.set(f"youtube:{PID}", "token_expires_at", (NOW + timedelta(hours=1)).isoformat())
    assert GetYouTubeChannel(channels, secrets, now=lambda: NOW).execute(PID)["oauth_status"] == "CONNECTED"