"""Domínio da identidade de publicação do YouTube (YT-01). Puro: conta, grant, canal, vínculo."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus  # noqa: E402
from app.studio.domain.youtube_identity import (  # noqa: E402
    ChannelAuthorization,
    ChannelAuthorizationInvalid,
    GoogleAccount,
    GoogleAccountInvalid,
    OAuthGrant,
    OAuthGrantInvalid,
    YouTubeChannelIdentity,
    YouTubeChannelIdentityInvalid,
)

AID = "a" * 32
GID = "b" * 32
NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)


def test_google_account_validates_the_email():
    account = GoogleAccount(id=AID, email="  eu@gmail.com  ", display_name="Eu")
    assert account.email == "eu@gmail.com" and account.display_name == "Eu"
    for bad in ("sem-arroba", "a@b", "", "  ", 42):
        with pytest.raises(GoogleAccountInvalid):
            GoogleAccount(id=AID, email=bad)


def test_oauth_grant_normalizes_scopes_and_deduplicates():
    grant = OAuthGrant(id=GID, account_id=AID, scopes=("youtube.upload", " youtube.upload ", "youtube.readonly"))
    assert grant.scopes == ("youtube.upload", "youtube.readonly")
    assert grant.status is OAuthStatus.CONNECTED
    with pytest.raises(OAuthGrantInvalid):
        OAuthGrant(id=GID, account_id=AID, scopes=("",))


def test_oauth_grant_rejects_an_unknown_status():
    with pytest.raises(OAuthGrantInvalid):
        OAuthGrant(id=GID, account_id=AID, status="WEIRD")


def test_oauth_grant_effective_status_is_derived_not_presumed():
    grant = OAuthGrant(id=GID, account_id=AID, token_expires_at=NOW + timedelta(hours=1))
    # sem credencial no vault, mesmo com status declarado CONNECTED, o estado real é DISCONNECTED
    assert grant.effective_status(has_credentials=False, now=NOW) is OAuthStatus.DISCONNECTED
    assert grant.effective_status(has_credentials=True, now=NOW) is OAuthStatus.CONNECTED
    assert grant.effective_status(has_credentials=True, now=NOW + timedelta(hours=2)) is OAuthStatus.EXPIRED
    assert grant.effective_status(has_credentials=True, now=NOW, revoked=True) is OAuthStatus.REVOKED


def test_youtube_channel_identity_holds_the_official_id_not_the_account():
    channel = YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História")
    assert channel.youtube_channel_id == "UCabc123" and channel.title == "História"
    for bad in ("", "   ", "com espaço", 7):
        with pytest.raises(YouTubeChannelIdentityInvalid):
            YouTubeChannelIdentity(youtube_channel_id=bad)


def test_channel_authorization_links_a_grant_to_a_channel():
    link = ChannelAuthorization(grant_id=GID, youtube_channel_id="UCabc123", validated_at=NOW)
    assert link.grant_id == GID and link.youtube_channel_id == "UCabc123"
    assert link.status is OAuthStatus.CONNECTED and link.validated_at == NOW
    with pytest.raises(InvalidId):
        ChannelAuthorization(grant_id="nao-e-id", youtube_channel_id="UCabc123")
    with pytest.raises(ChannelAuthorizationInvalid):
        ChannelAuthorization(grant_id=GID, youtube_channel_id="UCabc123", validated_at="ontem")
