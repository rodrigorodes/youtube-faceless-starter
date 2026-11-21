"""F8-05: CLI de consentimento — gera URL, troca código e grava no cofre sem imprimir token."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_oauth_consent as cli  # noqa: E402
from app.studio.domain.youtube_channel import YouTubeChannel  # noqa: E402
from app.studio.domain.youtube_oauth import DEFAULT_SCOPES, OAuthTokenResponse, authorization_url  # noqa: E402

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


class OAuth:
    def __init__(self):
        self.revoked = []

    def authorization_url(self, redirect_uri, scopes, state, code_challenge):
        return authorization_url(client_id="client-id.apps.googleusercontent.com", redirect_uri=redirect_uri,
                                 scopes=scopes, state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=("http://localhost:8000/studio/oauth/callback",))

    def exchange_code(self, code, redirect_uri, code_verifier):
        assert code == "code-123" and 43 <= len(code_verifier) <= 128
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=REFRESH, expires_in=3600,
                                  scopes=DEFAULT_SCOPES)

    def refresh(self, refresh_token):
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=None, expires_in=3600, scopes=DEFAULT_SCOPES)

    def revoke(self, token):
        self.revoked.append(token)

    def identity(self, access_token):
        from app.studio.domain.youtube_oauth import OAuthIdentity
        return OAuthIdentity(channel_id="UC_synthetic", title="Canal de teste")


def run(argv, *, secrets=None, channels=None, oauth=None, env=None):
    output = []
    code = cli.main(argv, env={"STUDIO_DATABASE_URL": "postgresql://unused", **(env or {})},
                    client=oauth or OAuth(), store=secrets or Secrets(), repo=channels or Channels(),
                    out=output.append)
    return code, "\n".join(output)


def test_url_prints_the_consent_url_and_no_secret():
    secrets, oauth = Secrets(), OAuth()
    code, output = run(["url", "--project-id", PID], secrets=secrets, oauth=oauth)
    assert code == 0
    body = json.loads(output)
    assert body["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert body["state"] and body["expires_at"]
    assert ACCESS not in output and REFRESH not in output and "client_secret" not in output
    assert secrets.get(f"youtube:{PID}", "oauth_state") == body["state"]


def test_exchange_stores_the_refresh_token_in_the_vault_and_prints_only_public_data():
    secrets, channels, oauth = Secrets(), Channels(), OAuth()
    _, first = run(["url", "--project-id", PID], secrets=secrets, channels=channels, oauth=oauth)
    state = json.loads(first)["state"]
    code, output = run(["exchange", "--project-id", PID, "--code", "code-123", "--state", state],
                       secrets=secrets, channels=channels, oauth=oauth)
    assert code == 0
    body = json.loads(output)
    assert body["oauth_status"] == "CONNECTED" and body["channel_id"] == "UC_synthetic"
    assert ACCESS not in output and REFRESH not in output
    assert secrets.get(f"youtube:{PID}", "refresh_token") == REFRESH
    assert channels.get(PID).channel_id == "UC_synthetic"


def test_exchange_without_code_or_state_is_refused(capsys):
    code, _ = run(["exchange", "--project-id", PID], secrets=Secrets(), channels=Channels(), oauth=OAuth())
    assert code == 2 and "code and --state" in capsys.readouterr().err


def test_status_and_revoke_never_print_tokens():
    secrets, channels, oauth = Secrets(), Channels(), OAuth()
    _, first = run(["url", "--project-id", PID], secrets=secrets, channels=channels, oauth=oauth)
    run(["exchange", "--project-id", PID, "--code", "code-123", "--state", json.loads(first)["state"]],
        secrets=secrets, channels=channels, oauth=oauth)
    code, status = run(["status", "--project-id", PID], secrets=secrets, channels=channels, oauth=oauth)
    assert code == 0 and json.loads(status)["connected"] is True and ACCESS not in status and REFRESH not in status
    code, revoked = run(["revoke", "--project-id", PID], secrets=secrets, channels=channels, oauth=oauth)
    assert code == 0 and json.loads(revoked)["oauth_status"] == "REVOKED" and oauth.revoked == [REFRESH]


def test_missing_configuration_fails_without_dumping_environment(capsys):
    output = []
    code = cli.main(["url", "--project-id", PID], env={}, out=output.append)
    assert code == 2 and output == [] and "client_secret" not in capsys.readouterr().err.lower()