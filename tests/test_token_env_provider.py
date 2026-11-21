"""F8-05: fallback do refresh token do ambiente, sem copiar o arquivo e sem vazar o valor."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.token_env import EnvRefreshTokenProvider  # noqa: E402
from app.studio.application.publication_execution import (  # noqa: E402
    FallbackTokenProvider, MissingTokenProvider,
)
from app.studio.application.youtube_oauth import ChannelNotConnected  # noqa: E402
from app.studio.domain.youtube_oauth import OAuthReconnectRequired, OAuthTokenResponse  # noqa: E402

REFRESH = "1//SYNTHETIC_refresh_value_only_for_tests"
ACCESS = "ya29.SYNTHETIC_access_value_only_for_tests"


class OAuth:
    def __init__(self):
        self.seen = []

    def refresh(self, token):
        self.seen.append(token)
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=None, expires_in=3600, scopes=())

    def exchange_code(self, code, redirect_uri, code_verifier):
        raise NotImplementedError

    def revoke(self, token):
        raise NotImplementedError

    def identity(self, access_token):
        raise NotImplementedError


def env_file(tmp_path, value=REFRESH, quote=False):
    path = tmp_path / "token.env"
    rendered = '"' + value + '"' if quote else value
    text = 'YOUTUBE_API_KEY="not-a-real-key"\nYOUTUBE_REFRESH_TOKEN=' + rendered + "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_env_provider_reads_only_the_refresh_variable_and_returns_the_new_access(tmp_path):
    oauth = OAuth()
    path = env_file(tmp_path)
    provider = EnvRefreshTokenProvider(oauth, path)
    assert provider.execute("a" * 32) == ACCESS and oauth.seen == [REFRESH]
    assert REFRESH not in repr(provider) and ACCESS not in repr(provider)


def test_env_provider_accepts_a_quoted_value(tmp_path):
    oauth = OAuth()
    assert EnvRefreshTokenProvider(oauth, env_file(tmp_path, quote=True)).execute("a" * 32) == ACCESS


def test_env_provider_never_leaks_the_value_when_it_is_missing(tmp_path):
    oauth = OAuth()
    path = tmp_path / "token.env"
    path.write_text("YOUTUBE_API_KEY=only\n", encoding="utf-8")
    with pytest.raises(OAuthReconnectRequired) as caught:
        EnvRefreshTokenProvider(oauth, path).execute("a" * 32)
    assert "YOUTUBE_REFRESH_TOKEN" in str(caught.value) and REFRESH not in str(caught.value)
    with pytest.raises(OAuthReconnectRequired):
        EnvRefreshTokenProvider(oauth, tmp_path / "missing.env").execute("a" * 32)


def test_fallback_only_switches_when_the_project_has_no_consent(tmp_path):
    class NoVault:
        def execute(self, project_id):
            raise ChannelNotConnected("no refresh token")

    class Revoked:
        def execute(self, project_id):
            raise OAuthReconnectRequired("invalid_grant")

    oauth = OAuth()
    env = EnvRefreshTokenProvider(oauth, env_file(tmp_path))
    assert FallbackTokenProvider(NoVault(), env).execute("a" * 32) == ACCESS
    with pytest.raises(OAuthReconnectRequired, match="invalid_grant"):
        FallbackTokenProvider(Revoked(), env).execute("a" * 32)


def test_missing_provider_fails_closed_with_an_actionable_message():
    with pytest.raises(ChannelNotConnected, match="OAuth app"):
        MissingTokenProvider().execute("a" * 32)