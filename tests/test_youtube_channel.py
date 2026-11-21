"""Associação de canal YouTube + status OAuth (F10-06) e secret store (F10-07).

O status é derivado: sem credenciais no vault o canal aparece DISCONNECTED, mesmo com linha no
banco. Nenhuma resposta carrega access/refresh token.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.secret_store import FileSecretStore, SecretStoreError  # noqa: E402
from app.studio.application.youtube_channels import (  # noqa: E402
    AssociateYouTubeChannel,
    DisconnectYouTubeChannel,
    GetYouTubeChannel,
)
from app.studio.domain.youtube_channel import (  # noqa: E402
    OAuthStatus,
    YouTubeChannel,
    YouTubeChannelInvalid,
)

PID = "a" * 32
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


class FakeYouTubeRepo:
    def __init__(self):
        self.rows = {}

    def get(self, project_id):
        return self.rows.get(project_id)

    def upsert(self, channel):
        self.rows[channel.project_id] = channel
        return channel

    def delete(self, project_id):
        return self.rows.pop(project_id, None) is not None


class MemorySecretStore:
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


# ------------------------------------------------------------------ domain


def test_channel_validates_identity():
    channel = YouTubeChannel(project_id=PID, channel_id="UC123abc", title="História")
    assert channel.oauth_status is OAuthStatus.CONNECTED
    with pytest.raises(YouTubeChannelInvalid):
        YouTubeChannel(project_id=PID, channel_id="")
    with pytest.raises(YouTubeChannelInvalid):
        YouTubeChannel(project_id=PID, channel_id="com espaço")


def test_public_view_never_carries_tokens():
    channel = YouTubeChannel(project_id=PID, channel_id="UC1", title="Canal",
                             token_expires_at=NOW + timedelta(hours=1))
    public = channel.public(has_credentials=True, now=NOW)
    assert public["oauth_status"] == "CONNECTED"
    assert public["connected"] is True
    for forbidden in ("access_token", "refresh_token", "token", "client_secret"):
        assert forbidden not in public


def test_without_credentials_status_is_disconnected():
    channel = YouTubeChannel(project_id=PID, channel_id="UC1", title="Canal", token_expires_at=NOW - timedelta(hours=1))
    public = channel.public(has_credentials=False, now=NOW)
    assert public["connected"] is False
    assert public["oauth_status"] == "DISCONNECTED"


def test_expired_token_reports_expired():
    channel = YouTubeChannel(project_id=PID, channel_id="UC1", title="Canal", token_expires_at=NOW - timedelta(minutes=1))
    public = channel.public(has_credentials=True, now=NOW)
    assert public["oauth_status"] == "EXPIRED"
    assert public["connected"] is False


# -------------------------------------------------------------- application


def test_associate_stores_credentials_in_vault_and_not_in_response():
    repo, store = FakeYouTubeRepo(), MemorySecretStore()
    result = AssociateYouTubeChannel(repo, store).execute(
        PID, channel_id="UC1", title="Canal", scopes=("https://www.googleapis.com/auth/youtube.upload",),
        access_token="ya29.access", refresh_token="1//refresh", token_expires_at=NOW + timedelta(hours=1))
    assert result["connected"] is True
    assert result["oauth_status"] == "CONNECTED"
    assert "ya29.access" not in str(result) and "1//refresh" not in str(result)
    assert store.get(f"youtube:{PID}", "refresh_token") == "1//refresh"
    assert store.get(f"youtube:{PID}", "access_token") == "ya29.access"
    assert repo.get(PID).channel_id == "UC1"


def test_associate_without_credentials_is_refused():
    with pytest.raises(YouTubeChannelInvalid):
        AssociateYouTubeChannel(FakeYouTubeRepo(), MemorySecretStore()).execute(
            PID, channel_id="UC1", title="Canal", scopes=(), refresh_token="")


def test_get_status_without_row_is_disconnected():
    status = GetYouTubeChannel(FakeYouTubeRepo(), MemorySecretStore()).execute(PID)
    assert status["connected"] is False
    assert status["oauth_status"] == "DISCONNECTED"
    assert status["channel_id"] is None


def test_get_status_flags_missing_credentials_even_with_row():
    repo, store = FakeYouTubeRepo(), MemorySecretStore()
    repo.upsert(YouTubeChannel(project_id=PID, channel_id="UC1", title="Canal",
                               token_expires_at=NOW + timedelta(hours=1)))
    status = GetYouTubeChannel(repo, store, now=lambda: NOW).execute(PID)
    assert status["connected"] is False
    assert status["oauth_status"] == "DISCONNECTED"


def test_disconnect_removes_row_and_secrets():
    repo, store = FakeYouTubeRepo(), MemorySecretStore()
    AssociateYouTubeChannel(repo, store).execute(
        PID, channel_id="UC1", title="Canal", scopes=(), refresh_token="1//refresh")
    assert DisconnectYouTubeChannel(repo, store).execute(PID) is True
    assert repo.get(PID) is None
    assert store.names(f"youtube:{PID}") == ()
    assert DisconnectYouTubeChannel(repo, store).execute(PID) is False


# ------------------------------------------------------------ FileSecretStore


def test_file_secret_store_roundtrip(tmp_path):
    store = FileSecretStore(tmp_path / "vault")
    store.set("youtube:proj", "refresh_token", "1//x")
    assert store.get("youtube:proj", "refresh_token") == "1//x"
    assert store.names("youtube:proj") == ("refresh_token",)
    store.delete("youtube:proj", "refresh_token")
    assert store.get("youtube:proj", "refresh_token") is None


def test_file_secret_store_never_stores_readable_world_permissions(tmp_path):
    vault = tmp_path / "vault"
    store = FileSecretStore(vault)
    store.set("youtube:proj", "refresh_token", "1//x")
    mode = (vault / "youtube_proj.json").stat().st_mode & 0o777
    assert mode & 0o077 == 0  # nada para grupo/outros


def test_file_secret_store_refuses_path_traversal(tmp_path):
    store = FileSecretStore(tmp_path / "vault")
    with pytest.raises(SecretStoreError):
        store.get("../../etc", "passwd")
    with pytest.raises(SecretStoreError):
        store.set("youtube:proj", "bad/key", "x")
