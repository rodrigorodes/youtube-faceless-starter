"""Testes de integração dos repositórios Postgres da identidade de publicação (YT-01b).

Banco descartável (mesmas fixtures `conn`/`dsn` de `conftest.py` que os demais *_repo).
Cobre o ciclo conta → grants → canais → vínculos, a unicidade de e-mail sem caixa, o
cascade da conta e a preservação do `validated_at` — sem nunca tocar em tokens.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.youtube_identity_repo import (  # noqa: E402
    PostgresChannelAuthorizationRepository,
    PostgresGoogleAccountRepository,
    PostgresOAuthGrantRepository,
    PostgresYouTubeChannelIdentityRepository,
)
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
AID2 = "d" * 32
GID = "b" * 32
GID2 = "e" * 32
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def identity(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    return {
        "accounts": PostgresGoogleAccountRepository(connect),
        "grants": PostgresOAuthGrantRepository(connect),
        "channels": PostgresYouTubeChannelIdentityRepository(connect),
        "links": PostgresChannelAuthorizationRepository(connect),
        "dsn": dsn,
    }


def _rows(dsn, query, params=()):
    with psycopg.connect(dsn) as c, c.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def _account(repo, *, account_id=AID, email="EU@gmail.com", display_name="Eu"):
    return repo.upsert(GoogleAccount(id=account_id, email=email, display_name=display_name))


def _grant(repo, *, grant_id=GID, account_id=AID, scopes=("youtube.upload",), expires=None):
    return repo.create(OAuthGrant(id=grant_id, account_id=account_id, scopes=scopes, token_expires_at=expires))


# --- GoogleAccount ---------------------------------------------------------

def test_account_upsert_reads_back_and_lists(identity):
    accounts = identity["accounts"]
    saved = _account(accounts)
    assert saved.id == AID and saved.email == "EU@gmail.com" and saved.display_name == "Eu"
    assert saved.created_at is not None and saved.updated_at is not None
    assert accounts.get(AID) == saved
    assert accounts.list() == [saved]
    assert accounts.get("f" * 32) is None


def test_account_email_is_unique_without_case(identity):
    accounts = identity["accounts"]
    first = _account(accounts)
    # Mesmo e-mail em outra caixa e outro id: atualiza a linha existente, não duplica.
    again = accounts.upsert(GoogleAccount(id=AID2, email="eu@GMAIL.com", display_name="Eu Novo"))
    assert again.id == first.id
    assert again.display_name == "Eu Novo"
    assert again.created_at == first.created_at
    assert _rows(identity["dsn"], "SELECT count(*) FROM studio.google_accounts") == [(1,)]
    assert accounts.get_by_email("EU@gmail.com").id == first.id
    assert {a.id for a in accounts.list()} == {first.id}


def test_account_get_by_email_validates_the_address(identity):
    with pytest.raises(GoogleAccountInvalid):
        identity["accounts"].get_by_email("sem-arroba")


# --- OAuthGrant ------------------------------------------------------------

def test_grant_is_created_for_the_account_and_listed(identity):
    accounts, grants = identity["accounts"], identity["grants"]
    _account(accounts)
    created = _grant(grants, scopes=("youtube.upload", " youtube.readonly "), expires=NOW + timedelta(hours=1))
    assert created.id == GID and created.account_id == AID
    assert created.scopes == ("youtube.upload", "youtube.readonly")
    assert created.status is OAuthStatus.CONNECTED
    assert created.token_expires_at == NOW + timedelta(hours=1)
    assert grants.get(GID) == created
    assert grants.list_for_account(AID) == [created]
    assert grants.list_for_account(AID2) == []
    assert grants.get("f" * 32) is None


def test_grant_for_an_unknown_account_is_refused(identity):
    with pytest.raises(OAuthGrantInvalid):
        _grant(identity["grants"], account_id="f" * 32)


def test_deleting_the_account_cascades_its_grants(identity):
    accounts, grants = identity["accounts"], identity["grants"]
    _account(accounts)
    _grant(grants)
    assert _rows(identity["dsn"], "SELECT count(*) FROM studio.oauth_grants") == [(1,)]
    with psycopg.connect(identity["dsn"]) as c, c.cursor() as cur:
        cur.execute("DELETE FROM studio.google_accounts WHERE id = %s", (AID,))
    assert grants.get(GID) is None


def test_update_status_changes_state_but_keeps_absent_expiry(identity):
    accounts, grants = identity["accounts"], identity["grants"]
    _account(accounts)
    _grant(grants, expires=NOW + timedelta(hours=1))
    moved = grants.update_status(GID, OAuthStatus.EXPIRED)
    assert moved.status is OAuthStatus.EXPIRED
    assert moved.token_expires_at == NOW + timedelta(hours=1)  # não informado: preservado
    cleared = grants.update_status(GID, OAuthStatus.REVOKED, token_expires_at=None)
    assert cleared.status is OAuthStatus.REVOKED and cleared.token_expires_at is None
    assert grants.update_status("f" * 32, OAuthStatus.ERROR) is None


def test_update_status_refuses_a_derived_status(identity):
    accounts, grants = identity["accounts"], identity["grants"]
    _account(accounts)
    _grant(grants)
    with pytest.raises(OAuthGrantInvalid):
        grants.update_status(GID, OAuthStatus.DISCONNECTED)


# --- YouTubeChannelIdentity ------------------------------------------------

def test_channel_upsert_updates_title_and_lists(identity):
    channels = identity["channels"]
    first = channels.upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    assert first.youtube_channel_id == "UCabc123" and first.title == "História"
    assert channels.get("UCabc123") == first
    updated = channels.upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História Nova"))
    assert updated.title == "História Nova" and updated.created_at == first.created_at
    channels.upsert(YouTubeChannelIdentity(youtube_channel_id="UCzzz", title="Outro"))
    assert [c.youtube_channel_id for c in channels.list()] == ["UCabc123", "UCzzz"]
    assert channels.get("UCnada") is None


def test_channel_get_validates_the_id(identity):
    with pytest.raises(YouTubeChannelIdentityInvalid):
        identity["channels"].get("com espaço")


# --- ChannelAuthorization --------------------------------------------------

def _link(identity, *, validated_at=NOW, grant_id=GID, channel_id="UCabc123"):
    return identity["links"].link(
        ChannelAuthorization(grant_id=grant_id, youtube_channel_id=channel_id, validated_at=validated_at)
    )


def test_link_records_the_validated_authorization(identity):
    _account(identity["accounts"])
    _grant(identity["grants"])
    identity["channels"].upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    link = _link(identity)
    assert link.grant_id == GID and link.youtube_channel_id == "UCabc123"
    assert link.status is OAuthStatus.CONNECTED and link.validated_at == NOW
    assert identity["links"].get(GID, "UCabc123") == link
    assert identity["links"].authorizations_for_channel("UCabc123") == [link]
    assert identity["links"].authorizations_for_channel("UCnada") == []


def test_link_refuses_unknown_grant_or_channel(identity):
    _account(identity["accounts"])
    _grant(identity["grants"])
    identity["channels"].upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    with pytest.raises(ChannelAuthorizationInvalid, match="oauth grant"):
        _link(identity, grant_id="f" * 32)
    with pytest.raises(ChannelAuthorizationInvalid, match="youtube channel"):
        _link(identity, channel_id="UCinexistente")


def test_revoke_keeps_the_line_and_the_validated_at(identity):
    _account(identity["accounts"])
    _grant(identity["grants"])
    identity["channels"].upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    _link(identity)
    assert identity["links"].revoke(GID, "UCabc123") is True
    revoked = identity["links"].get(GID, "UCabc123")
    assert revoked.status is OAuthStatus.REVOKED and revoked.validated_at == NOW
    assert identity["links"].revoke(GID, "UCnada") is False


def test_relinking_refreshes_status_and_validation_instant(identity):
    _account(identity["accounts"])
    _grant(identity["grants"])
    identity["channels"].upsert(YouTubeChannelIdentity(youtube_channel_id="UCabc123", title="História"))
    first = _link(identity)
    identity["links"].revoke(GID, "UCabc123")
    later = NOW + timedelta(days=1)
    again = _link(identity, validated_at=later)
    assert again.status is OAuthStatus.CONNECTED and again.validated_at == later
    assert again.created_at == first.created_at  # o vínculo é o mesmo (PK), só revalidado
