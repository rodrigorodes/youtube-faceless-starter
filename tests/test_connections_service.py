"""YT-04a: o serviço de Conexões sem rede e sem banco (duplos das portas).

Cobre o consentimento (conta + autorização + canal + vínculo validado), reconexão do mesmo
e-mail sem duplicar conta, o quadro de Conexões, o vínculo do canal do estúdio e a revogação
**isolada** — sempre com os tokens só no cofre e nunca na resposta.
"""
import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.connections import (  # noqa: E402
    AccountConsentStateInvalid, AccountIdentityUnavailable, AuthorizationNotFound, BeginAccountConsent,
    CompleteAccountConsent, ConnectionNotFound, LinkStudioChannel, ListConnections, RevokeAuthorization, Unlink,
    grant_scope,
)
from app.studio.domain.channel import ChannelProfile, ChannelYouTubeTargetNotFound  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus  # noqa: E402
from app.studio.domain.youtube_identity import (  # noqa: E402
    ChannelAuthorization, GoogleAccount, OAuthGrant, YouTubeChannelIdentity,
)
from app.studio.domain.youtube_oauth import (  # noqa: E402
    DEFAULT_SCOPES, OAuthIdentity, OAuthTokenResponse, authorization_url,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
PID = "c" * 32
PROFILE = "d" * 32
ACCESS = "ya29.SYNTHETIC_connections_access"
REFRESH = "1//SYNTHETIC_connections_refresh"


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


class Accounts:
    def __init__(self):
        self.rows = {}

    def upsert(self, account):
        key = account.email.lower()
        existing = next((a for a in self.rows.values() if a.email.lower() == key), None)
        if existing is not None:
            saved = dataclasses.replace(existing, display_name=account.display_name)
        else:
            saved = account
        self.rows[saved.id] = saved
        return saved

    def get(self, account_id):
        return self.rows.get(account_id)

    def get_by_email(self, email):
        return next((a for a in self.rows.values() if a.email.lower() == email.lower()), None)

    def list(self):
        return sorted(self.rows.values(), key=lambda a: a.email.lower())


class Grants:
    def __init__(self):
        self.rows = {}

    def create(self, grant):
        self.rows[grant.id] = grant
        return grant

    def get(self, grant_id):
        return self.rows.get(grant_id)

    def list_for_account(self, account_id):
        return [g for g in self.rows.values() if g.account_id == account_id]

    def update_status(self, grant_id, status, *, token_expires_at=dataclasses.MISSING):
        grant = self.rows.get(grant_id)
        if grant is None:
            return None
        changes = {"status": status}
        if token_expires_at is not dataclasses.MISSING:
            changes["token_expires_at"] = token_expires_at
        self.rows[grant_id] = dataclasses.replace(grant, **changes)
        return self.rows[grant_id]


class Identities:
    def __init__(self):
        self.rows = {}

    def upsert(self, channel):
        self.rows[channel.youtube_channel_id] = channel
        return channel

    def get(self, youtube_channel_id):
        return self.rows.get(youtube_channel_id)

    def list(self):
        return sorted(self.rows.values(), key=lambda c: c.youtube_channel_id)


class Links:
    def __init__(self):
        self.rows = {}

    def link(self, authorization):
        self.rows[(authorization.grant_id, authorization.youtube_channel_id)] = authorization
        return authorization

    def get(self, grant_id, youtube_channel_id):
        return self.rows.get((grant_id, youtube_channel_id))

    def authorizations_for_channel(self, youtube_channel_id):
        return [a for (g, c), a in self.rows.items() if c == youtube_channel_id]

    def revoke(self, grant_id, youtube_channel_id):
        existing = self.rows.get((grant_id, youtube_channel_id))
        if existing is None:
            return False
        self.rows[(grant_id, youtube_channel_id)] = dataclasses.replace(existing, status=OAuthStatus.REVOKED)
        return True


class Profiles:
    def __init__(self):
        self.rows = {}

    def add(self, profile):
        self.rows[profile.id] = profile
        return profile

    def get(self, profile_id):
        return self.rows.get(profile_id)

    def list(self, include_archived=False):
        return [p for p in self.rows.values() if include_archived or not p.archived]

    def update(self, profile_id, expected_version, changes):
        profile = self.rows.get(profile_id)
        if profile is None or profile.version != expected_version:
            return None
        updated = dataclasses.replace(profile, version=profile.version + 1, **changes)
        self.rows[profile_id] = updated
        return updated


class OAuthFake:
    def __init__(self, *, email="EU@gmail.com", channel_id="UC_principal", title="Canal principal"):
        self.identity_value = OAuthIdentity(channel_id=channel_id, title=title, email=email)
        self.exchange_error = None
        self.granted_scopes = DEFAULT_SCOPES
        self.exchange_calls = []
        self.revoked = []

    def authorization_url(self, redirect_uri, scopes, state, code_challenge):
        return authorization_url(client_id="client-id.apps.googleusercontent.com", redirect_uri=redirect_uri,
                                 scopes=scopes, state=state, code_challenge=code_challenge,
                                 allowed_redirect_uris=("http://localhost:8000/studio/oauth/callback",))

    def exchange_code(self, code, redirect_uri, code_verifier):
        self.exchange_calls.append((code, redirect_uri, code_verifier))
        if self.exchange_error:
            raise self.exchange_error
        return OAuthTokenResponse(access_token=ACCESS, refresh_token=REFRESH, expires_in=3600,
                                  scopes=self.granted_scopes)

    def refresh(self, refresh_token):  # pragma: no cover - não usado aqui
        raise AssertionError("refresh não deveria ser chamado no consentimento")

    def revoke(self, token):
        self.revoked.append(token)

    def identity(self, access_token):
        return self.identity_value


def world(*, email="EU@gmail.com", channel_id="UC_principal", title="Canal principal", profiles=None, oauth=None):
    secrets = Secrets()
    accounts, grants, identities, links = Accounts(), Grants(), Identities(), Links()
    profiles = profiles if profiles is not None else Profiles()
    oauth = oauth or OAuthFake(email=email, channel_id=channel_id, title=title)
    clock = lambda: NOW
    return {
        "secrets": secrets, "accounts": accounts, "grants": grants, "identities": identities,
        "links": links, "profiles": profiles, "oauth": oauth, "clock": clock,
        "begin": BeginAccountConsent(oauth, secrets, clock=clock,
                                     redirect_uri="http://localhost:8000/studio/oauth/callback"),
        "complete": CompleteAccountConsent(oauth, accounts, grants, identities, links, secrets, clock=clock,
                                           redirect_uri="http://localhost:8000/studio/oauth/callback"),
    }


def connect(w, *, email="EU@gmail.com"):
    state = w["begin"].execute()["state"]
    return w["complete"].execute("code-123", state, email=email)


# -- BeginAccountConsent ----------------------------------------------------


def test_begin_stores_state_and_verifier_and_returns_only_the_url():
    w = world()
    out = w["begin"].execute()
    assert out["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge=" in out["authorization_url"] and "state=" in out["authorization_url"]
    assert ACCESS not in str(out) and REFRESH not in str(out) and "client_secret" not in str(out)
    scope = f"oauth_consent:{out['state']}"
    assert w["secrets"].get(scope, "oauth_state") == out["state"]
    assert len(w["secrets"].get(scope, "oauth_code_verifier")) >= 43
    assert w["secrets"].get(scope, "oauth_state_expires_at") == (NOW + timedelta(minutes=10)).isoformat()


def test_begin_asks_for_the_account_email_scope_so_the_account_can_be_identified():
    # sem `userinfo.email` o Google não revela a conta e a conexão real nunca conclui
    url = world()["begin"].execute()["authorization_url"]
    assert "youtube.upload" in url and "userinfo.email" in url


# -- CompleteAccountConsent -------------------------------------------------


def test_complete_creates_account_authorization_channel_and_validated_link_without_leaking_tokens():
    w = world()
    result = connect(w)
    account = next(iter(w["accounts"].rows.values()))
    assert account.email == "EU@gmail.com"
    assert result["account"] == {"id": account.id, "email": "EU@gmail.com", "display_name": ""}
    assert result["channel"] == {"youtube_channel_id": "UC_principal", "title": "Canal principal"}
    assert result["status"] == "CONNECTED" and result["validated_at"] == NOW.isoformat()

    grant = w["grants"].get(result["grant_id"])
    assert grant.account_id == account.id and set(grant.scopes) == set(DEFAULT_SCOPES)
    link = w["links"].get(result["grant_id"], "UC_principal")
    assert link is not None and link.validated_at == NOW and link.status == OAuthStatus.CONNECTED
    assert w["identities"].get("UC_principal").title == "Canal principal"

    # tokens vivem só no cofre, por autorização — e nunca na resposta
    scope = grant_scope(result["grant_id"])
    assert w["secrets"].get(scope, "access_token") == ACCESS
    assert w["secrets"].get(scope, "refresh_token") == REFRESH
    assert ACCESS not in str(result) and REFRESH not in str(result)


def test_complete_reuses_the_account_for_the_same_email_regardless_of_case():
    w = world()
    first = connect(w)
    # novo consentimento, mesmo e-mail em outra caixa, canal diferente: mesma conta, sem duplicar
    w["oauth"].identity_value = OAuthIdentity(channel_id="UC_secundario", title="Canal secundário", email="eu@GMAIL.com")
    state = w["begin"].execute()["state"]
    out = w["complete"].execute("code-456", state)
    assert out["account"]["id"] == first["account"]["id"]
    assert out["grant_id"] != first["grant_id"]  # a autorização do outro canal é independente
    assert len(w["accounts"].rows) == 1


def test_complete_refuses_wrong_or_expired_state_before_calling_google():
    w = world()
    state = w["begin"].execute()["state"]
    with pytest.raises(AccountConsentStateInvalid, match="state"):
        w["complete"].execute("code-123", "outro-state-qualquer")
    assert w["oauth"].exchange_calls == []
    w["secrets"].set(f"oauth_consent:{state}", "oauth_state_expires_at", (NOW - timedelta(seconds=1)).isoformat())
    with pytest.raises(AccountConsentStateInvalid, match="expired"):
        w["complete"].execute("code-123", state)
    assert w["oauth"].exchange_calls == []
    with pytest.raises(AccountConsentStateInvalid):
        w["complete"].execute("code-123", "!!!inválido!!!")


def test_complete_accepts_the_openid_scopes_google_returns_with_the_email_scope():
    # regressão: `openid` (não-URL) na resposta do token derrubava a conexão com "must be https URLs"
    w = world()
    w["oauth"].granted_scopes = ("openid", "https://www.googleapis.com/auth/userinfo.email",
                                 *DEFAULT_SCOPES)
    result = connect(w)
    assert result["account"]["email"] == "EU@gmail.com"
    assert "openid" in next(iter(w["grants"].rows.values())).scopes


def test_complete_without_an_account_email_never_invents_the_account():
    w = world(email="")
    state = w["begin"].execute()["state"]
    with pytest.raises(AccountIdentityUnavailable):
        w["complete"].execute("code-123", state)
    assert w["accounts"].rows == {} and w["grants"].rows == {}


# -- ListConnections --------------------------------------------------------


def test_list_connections_shows_account_channels_status_and_the_studio_channel():
    profiles = Profiles()
    profiles.add(ChannelProfile(id=PROFILE, project_id=PID, name="História", youtube_channel_id="UC_principal"))
    w = world(profiles=profiles)
    result = connect(w)
    board = ListConnections(w["accounts"], w["grants"], w["identities"], w["links"], w["profiles"],
                            w["secrets"], clock=w["clock"]).execute()
    account = board["accounts"][0]
    assert account["email"] == "EU@gmail.com"
    channel = account["channels"][0]
    assert channel["youtube_channel_id"] == "UC_principal"
    assert channel["grant_id"] == result["grant_id"]
    assert channel["status"] == "CONNECTED" and channel["validated_at"] == NOW.isoformat()
    assert channel["studio_channels"] == [{"id": PROFILE, "name": "História", "archived": False}]


def test_list_connections_status_comes_from_the_vault_not_a_typed_field():
    w = world()
    result = connect(w)
    scope = grant_scope(result["grant_id"])
    board = lambda: ListConnections(w["accounts"], w["grants"], w["identities"], w["links"], w["profiles"],
                                    w["secrets"], clock=w["clock"]).execute()["accounts"][0]["channels"][0]
    # sem credencial no cofre: DISCONNECTED (não "presume" conexão pelo vínculo existir)
    w["secrets"].delete(scope, "access_token")
    w["secrets"].delete(scope, "refresh_token")
    assert board()["status"] == "DISCONNECTED"
    # token vencido: EXPIRED
    w["secrets"].set(scope, "access_token", ACCESS)
    w["secrets"].set(scope, "token_expires_at", (NOW - timedelta(minutes=1)).isoformat())
    assert board()["status"] == "EXPIRED"


# -- RevokeAuthorization ----------------------------------------------------


def test_revoke_authorization_is_isolated_to_the_chosen_channel():
    w = world()
    first = connect(w)
    w["oauth"].identity_value = OAuthIdentity(channel_id="UC_secundario", title="Canal secundário", email="EU@gmail.com")
    state = w["begin"].execute()["state"]
    second = w["complete"].execute("code-456", state)

    revoked = RevokeAuthorization(w["grants"], w["links"], w["identities"], w["secrets"], w["oauth"],
                                  clock=w["clock"]).execute(first["grant_id"], "UC_principal")
    assert revoked == {"grant_id": first["grant_id"], "youtube_channel_id": "UC_principal", "status": "REVOKED"}
    # só aquele vínculo foi tocado; o outro canal da mesma conta continua CONNECTED
    assert w["links"].get(first["grant_id"], "UC_principal").status == OAuthStatus.REVOKED
    assert w["links"].get(second["grant_id"], "UC_secundario").status == OAuthStatus.CONNECTED
    assert w["grants"].get(second["grant_id"]).status == OAuthStatus.CONNECTED
    # tokens do grant revogado foram apagados; os do outro canal permanecem
    assert w["secrets"].names(grant_scope(first["grant_id"])) == ()
    assert w["secrets"].get(grant_scope(second["grant_id"]), "refresh_token") == REFRESH
    # revogar de novo é idempotente
    RevokeAuthorization(w["grants"], w["links"], w["identities"], w["secrets"], w["oauth"],
                        clock=w["clock"]).execute(first["grant_id"], "UC_principal")


def test_revoke_authorization_404s_when_the_link_does_not_exist():
    w = world()
    with pytest.raises(AuthorizationNotFound):
        RevokeAuthorization(w["grants"], w["links"], w["identities"], w["secrets"], w["oauth"],
                            clock=w["clock"]).execute("b" * 32, "UC_inexistente")


# -- LinkStudioChannel / Unlink ---------------------------------------------


def test_link_and_unlink_studio_channel_round_trip():
    profiles = Profiles()
    profiles.add(ChannelProfile(id=PROFILE, project_id=PID, name="História"))
    w = world(profiles=profiles)
    connect(w)
    link = LinkStudioChannel(w["profiles"], w["identities"])
    linked = link.execute(PROFILE, "UC_principal")
    assert linked.youtube_channel_id == "UC_principal" and linked.version == 2
    assert link.execute(PROFILE, "UC_principal").youtube_channel_id == "UC_principal"
    unlinked = Unlink(w["profiles"]).execute(PROFILE)
    assert unlinked.youtube_channel_id is None and unlinked.version == 4


def test_link_studio_channel_refuses_unknown_targets_and_profiles():
    profiles = Profiles()
    profiles.add(ChannelProfile(id=PROFILE, project_id=PID, name="História"))
    w = world(profiles=profiles)
    link = LinkStudioChannel(w["profiles"], w["identities"])
    with pytest.raises(ChannelYouTubeTargetNotFound):
        link.execute(PROFILE, "UC_nao_validado")
    with pytest.raises(ConnectionNotFound):
        link.execute("f" * 32, "UC_principal")
    with pytest.raises(ConnectionNotFound):
        Unlink(w["profiles"]).execute("f" * 32)
