"""F01.T01: o token da publicação resolve pela autorização (grant) do canal de destino.

O projeto aponta para um canal do YouTube (`channel_profiles.youtube_channel_id`); a autorização
validada daquele canal (`channel_authorizations`) leva ao grant, e é o **grant** que guarda e
renova os tokens no cofre (`oauth_grant:{id}`). Sem destino, o caminho legado continua explícito e
restrito — nunca como fallback de um canal com destino.

Sem rede e sem banco: duplos das portas. Os tokens nunca aparecem em `repr`, resposta ou erro.
"""
import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.channel_grant import (  # noqa: E402
    ChannelGrantMissing, ChannelGrantRevoked, ChannelGrantUnusable, EnsureGrantAccessToken,
)
from app.studio.application.connections import grant_scope  # noqa: E402
from app.studio.application.publication_execution import TargetChannelTokenProvider  # noqa: E402
from app.studio.application.youtube_channels import (  # noqa: E402
    ACCESS_TOKEN, REFRESH_TOKEN, TOKEN_EXPIRES_AT,
)
from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus  # noqa: E402
from app.studio.domain.youtube_identity import ChannelAuthorization, OAuthGrant  # noqa: E402
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, OAuthReconnectRequired, OAuthTokenResponse,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
PROJECT_A = "a" * 32
PROJECT_B = "b" * 32
PROFILE_A = "c" * 32
PROFILE_B = "d" * 32
GRANT_A = "1" * 32
GRANT_B = "2" * 32
TARGET_A = "UCtargetA"
TARGET_B = "UCtargetB"
TOKEN_A = "ya29.SYNTHETIC_grant_a_access"
TOKEN_B = "ya29.SYNTHETIC_grant_b_access"
REFRESH_A = "1//SYNTHETIC_grant_a_refresh"
RENEWED_A = "ya29.SYNTHETIC_grant_a_access_renewed"


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


class Profiles:
    def __init__(self, *profiles):
        self.rows = {profile.project_id: profile for profile in profiles}

    def get_by_project(self, project_id):
        return self.rows.get(project_id)


class Links:
    def __init__(self, *links):
        self.rows = list(links)
        self.revoked = []

    def authorizations_for_channel(self, youtube_channel_id):
        # mesma ordem do repositório real: created_at ASC, grant_id ASC
        return [link for link in self.rows if link.youtube_channel_id == youtube_channel_id]

    def revoke(self, grant_id, youtube_channel_id):
        self.revoked.append((grant_id, youtube_channel_id))
        for index, link in enumerate(self.rows):
            if link.grant_id == grant_id and link.youtube_channel_id == youtube_channel_id:
                self.rows[index] = dataclasses.replace(link, status=OAuthStatus.REVOKED)
                return True
        return False


class Grants:
    def __init__(self, *grants):
        self.rows = {grant.id: grant for grant in grants}
        self.statuses = []

    def get(self, grant_id):
        return self.rows.get(grant_id)

    def update_status(self, grant_id, status, *, token_expires_at=dataclasses.MISSING):
        grant = self.rows.get(grant_id)
        if grant is None:
            return None
        changes = {"status": status}
        if token_expires_at is not dataclasses.MISSING:
            changes["token_expires_at"] = token_expires_at
        self.rows[grant_id] = dataclasses.replace(grant, **changes)
        self.statuses.append((grant_id, status))
        return self.rows[grant_id]


class OAuth:
    def __init__(self, error=None):
        self.error = error
        self.refresh_calls = []

    def refresh(self, token):
        self.refresh_calls.append(token)
        if self.error:
            raise self.error
        return OAuthTokenResponse(access_token=RENEWED_A, refresh_token=None, expires_in=1800,
                                  scopes=DEFAULT_SCOPES, token_type="Bearer")

    def exchange_code(self, code, redirect_uri, code_verifier):  # pragma: no cover - não usado
        raise AssertionError("the grant token path never exchanges a code")

    def revoke(self, token):  # pragma: no cover - não usado
        raise AssertionError("the grant token path never revokes on the happy path")

    def identity(self, access_token):  # pragma: no cover - a identidade vem do vínculo validado
        raise AssertionError("the grant token path must not re-identify the token")


def profile(project_id, profile_id, target):
    return ChannelProfile(id=profile_id, project_id=project_id, name="Canal", youtube_channel_id=target)


def link(grant_id, target, *, validated_at=NOW, status=OAuthStatus.CONNECTED, created_at=None):
    return ChannelAuthorization(grant_id=grant_id, youtube_channel_id=target, status=status,
                                validated_at=validated_at, created_at=created_at)


def grant(grant_id=GRANT_A, *, status=OAuthStatus.CONNECTED, expires=None):
    return OAuthGrant(id=grant_id, account_id="e" * 32, scopes=DEFAULT_SCOPES, status=status,
                      token_expires_at=expires)


def store(secrets, grant_id, *, access=TOKEN_A, refresh=REFRESH_A, expires=None):
    scope = grant_scope(grant_id)
    if access is not None:
        secrets.set(scope, ACCESS_TOKEN, access)
    if refresh is not None:
        secrets.set(scope, REFRESH_TOKEN, refresh)
    if expires is not None:
        secrets.set(scope, TOKEN_EXPIRES_AT, expires.isoformat())


def world(*, target=TARGET_A, project=PROJECT_A, profile_id=PROFILE_A, authorization=None,
          grant_row=None, oauth=None):
    channels, links, grants = Profiles(profile(project, profile_id, target)), Links(), Grants()
    if target is not None:
        links.rows.append(authorization or link(GRANT_A, target))
    grants.rows[(grant_row or grant()).id] = grant_row or grant()
    return channels, links, grants, Secrets(), oauth or OAuth()


def ensure(channels, links, grants, secrets, oauth):
    return EnsureGrantAccessToken(channels, links, grants, secrets, oauth, clock=lambda: NOW)


# -- EnsureGrantAccessToken: obtém pela autorização do canal de destino ---------


def test_grant_token_is_used_without_refresh_and_reports_the_target_channel():
    channels, links, grants, secrets, oauth = world()
    store(secrets, GRANT_A, expires=NOW + timedelta(hours=1))

    access = ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)

    assert access.token == TOKEN_A and access.youtube_channel_id == TARGET_A
    assert oauth.refresh_calls == []  # token válido não é renovado à toa
    assert TOKEN_A not in repr(access)  # AccessToken mascara o valor


def test_expired_grant_token_is_refreshed_by_its_own_grant_and_persisted_only_there():
    channels, links, grants, secrets, oauth = world()
    store(secrets, GRANT_A, access=TOKEN_A, refresh=REFRESH_A, expires=NOW - timedelta(minutes=1))
    # um segundo grant (outro canal) não pode ser tocado nem servir de atalho
    grants.rows[GRANT_B] = grant(GRANT_B)
    store(secrets, GRANT_B, access=TOKEN_B, refresh="1//SYNTHETIC_grant_b_refresh",
          expires=NOW - timedelta(minutes=1))

    access = ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)

    assert access.token == RENEWED_A and access.youtube_channel_id == TARGET_A
    assert oauth.refresh_calls == [REFRESH_A]  # renovou pelo refresh do grant do destino
    assert secrets.get(grant_scope(GRANT_A), ACCESS_TOKEN) == RENEWED_A
    assert secrets.get(grant_scope(GRANT_A), REFRESH_TOKEN) == REFRESH_A  # resposta não trouxe novo
    assert secrets.get(grant_scope(GRANT_A), TOKEN_EXPIRES_AT) == (NOW + timedelta(seconds=1800)).isoformat()
    # o outro canal ficou exatamente como estava
    assert secrets.get(grant_scope(GRANT_B), ACCESS_TOKEN) == TOKEN_B
    assert grants.statuses == [(GRANT_A, OAuthStatus.CONNECTED)]
    assert grants.get(GRANT_B).token_expires_at is None


def test_the_newest_validated_authorization_wins_after_reconnecting_the_channel():
    """Reconectar cria um grant novo; o vínculo mais recente é o que a publicação usa."""
    channels, links, grants, secrets, oauth = world(
        authorization=link("0" * 32, TARGET_A, validated_at=NOW - timedelta(days=1), created_at=NOW - timedelta(days=1)))
    grants.rows["0" * 32] = grant("0" * 32)
    store(secrets, "0" * 32, access="ya29.SYNTHETIC_old_grant", expires=NOW + timedelta(hours=1))
    links.rows.append(link(GRANT_A, TARGET_A, validated_at=NOW, created_at=NOW))
    store(secrets, GRANT_A, expires=NOW + timedelta(hours=1))

    access = ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)

    assert access.token == TOKEN_A  # o grant novo, não o antigo
    assert oauth.refresh_calls == []


def test_a_target_without_a_connected_authorization_fails_closed():
    channels, links, grants, secrets, oauth = world(
        authorization=link(GRANT_A, TARGET_A, status=OAuthStatus.REVOKED))
    store(secrets, GRANT_A, expires=NOW + timedelta(hours=1))

    with pytest.raises(ChannelGrantMissing, match=TARGET_A):
        ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)
    assert oauth.refresh_calls == []
    assert secrets.get(grant_scope(GRANT_A), ACCESS_TOKEN) == TOKEN_A  # nada foi apagado


def test_a_revoked_grant_blocks_before_any_refresh_or_use():
    channels, links, grants, secrets, oauth = world(grant_row=grant(status=OAuthStatus.REVOKED))
    store(secrets, GRANT_A, expires=NOW + timedelta(hours=1))

    with pytest.raises(ChannelGrantRevoked, match="REVOKED"):
        ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)
    assert oauth.refresh_calls == []


def test_an_expired_grant_without_a_refresh_token_blocks_with_a_clear_error():
    channels, links, grants, secrets, oauth = world()
    store(secrets, GRANT_A, access=TOKEN_A, refresh=None, expires=NOW - timedelta(minutes=1))

    with pytest.raises(ChannelGrantUnusable, match="refresh"):
        ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)
    assert oauth.refresh_calls == []


def test_a_transient_refresh_failure_keeps_the_authorization_for_a_later_retry():
    from app.studio.domain.youtube_oauth import OAuthTransientError

    channels, links, grants, secrets, oauth = world(oauth=OAuth(OAuthTransientError("backendError")))
    store(secrets, GRANT_A, access=TOKEN_A, refresh=REFRESH_A, expires=NOW - timedelta(minutes=1))

    with pytest.raises(OAuthTransientError):
        ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)
    assert links.revoked == [] and grants.get(GRANT_A).status is OAuthStatus.CONNECTED
    assert secrets.get(grant_scope(GRANT_A), REFRESH_TOKEN) == REFRESH_A


def test_invalid_grant_revokes_that_link_clears_dead_tokens_and_never_leaks_values():
    channels, links, grants, secrets, oauth = world(oauth=OAuth(OAuthReconnectRequired("invalid_grant")))
    store(secrets, GRANT_A, access=TOKEN_A, refresh=REFRESH_A, expires=NOW - timedelta(minutes=1))

    with pytest.raises(OAuthReconnectRequired) as caught:
        ensure(channels, links, grants, secrets, oauth).execute(PROJECT_A)

    message = str(caught.value)
    assert TOKEN_A not in message and REFRESH_A not in message
    assert links.revoked == [(GRANT_A, TARGET_A)]
    assert links.rows[0].status is OAuthStatus.REVOKED
    assert grants.get(GRANT_A).status is OAuthStatus.REVOKED
    assert secrets.get(grant_scope(GRANT_A), ACCESS_TOKEN) is None
    assert secrets.get(grant_scope(GRANT_A), REFRESH_TOKEN) is None


def test_each_project_gets_only_the_token_of_its_own_channel():
    channels = Profiles(profile(PROJECT_A, PROFILE_A, TARGET_A), profile(PROJECT_B, PROFILE_B, TARGET_B))
    links = Links(link(GRANT_A, TARGET_A), link(GRANT_B, TARGET_B))
    grants = Grants(grant(GRANT_A), grant(GRANT_B))
    secrets, oauth = Secrets(), OAuth()
    store(secrets, GRANT_A, access=TOKEN_A, refresh=REFRESH_A, expires=NOW + timedelta(hours=1))
    store(secrets, GRANT_B, access=TOKEN_B, refresh="1//SYNTHETIC_grant_b_refresh",
          expires=NOW + timedelta(hours=1))

    service = ensure(channels, links, grants, secrets, oauth)
    granted_a = service.execute(PROJECT_A)
    granted_b = service.execute(PROJECT_B)

    assert (granted_a.token, granted_a.youtube_channel_id) == (TOKEN_A, TARGET_A)
    assert (granted_b.token, granted_b.youtube_channel_id) == (TOKEN_B, TARGET_B)
    assert TOKEN_A not in str(granted_b) and TOKEN_B not in str(granted_a)


# -- TargetChannelTokenProvider: legado explícito x grant, sem fallback cruzado -


class FixedTokens:
    def __init__(self, token="ya29.SYNTHETIC_legacy", channel_id=None, error=None):
        self.token, self.channel_id, self.error = token, channel_id, error
        self.calls = 0

    def execute(self, project_id):
        self.calls += 1
        if self.error:
            raise self.error
        from app.studio.application.ports import AccessToken
        return AccessToken(self.token, self.channel_id)


def test_a_project_with_a_target_takes_the_token_from_the_grant_only():
    channels, links, grants, secrets, oauth = world()
    store(secrets, GRANT_A, expires=NOW + timedelta(hours=1))
    grant_tokens = ensure(channels, links, grants, secrets, oauth)
    legacy = FixedTokens()
    provider = TargetChannelTokenProvider(channels, grant_tokens, legacy)

    access = provider.execute(PROJECT_A)

    assert access.token == TOKEN_A and access.youtube_channel_id == TARGET_A
    assert legacy.calls == 0


def test_a_project_without_a_target_keeps_the_explicit_legacy_path():
    channels, links, grants, secrets, oauth = world(target=None)
    legacy = FixedTokens(channel_id="UClegacy")
    provider = TargetChannelTokenProvider(channels, ensure(channels, links, grants, secrets, oauth), legacy)

    access = provider.execute(PROJECT_A)

    assert access.token == "ya29.SYNTHETIC_legacy" and access.youtube_channel_id == "UClegacy"
    assert legacy.calls == 1
    assert oauth.refresh_calls == []


def test_a_grant_failure_never_falls_back_to_the_legacy_token():
    channels, links, grants, secrets, oauth = world(
        authorization=link(GRANT_A, TARGET_A, status=OAuthStatus.REVOKED))
    legacy = FixedTokens()
    provider = TargetChannelTokenProvider(channels, ensure(channels, links, grants, secrets, oauth), legacy)

    with pytest.raises(ChannelGrantMissing):
        provider.execute(PROJECT_A)
    assert legacy.calls == 0  # sem fallback cruzado: o legado não serve um canal com destino


def test_an_invalid_project_id_is_read_as_no_target_exactly_like_the_gate():
    from app.studio.domain.ids import InvalidId

    class BrokenProfiles:
        def get_by_project(self, project_id):
            raise InvalidId("bad project id")

    legacy = FixedTokens()
    provider = TargetChannelTokenProvider(BrokenProfiles(), FixedTokens(error=AssertionError("grant path")), legacy)

    assert provider.execute("not-a-hex-id").token == "ya29.SYNTHETIC_legacy" and legacy.calls == 1