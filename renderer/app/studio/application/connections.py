"""Conexões: conta Google → autorizações → canais do YouTube (YT-04a).

Serviço puro quanto a I/O (só portas) da identidade nova descrita em
`docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md`: conectar uma conta,
completar o consentimento (conta + autorização + **canal escolhido**), listar o que está
conectado, vincular um canal do estúdio e revogar uma autorização **isoladamente**.

Invariantes que este módulo respeita:

- os tokens vivem **só no cofre**, por autorização (`oauth_grant:{grant_id}`); o banco guarda
  apenas metadados (escopos, status, expiração) e nenhuma resposta carrega access/refresh token;
- o vínculo autorização↔canal é **validado**: existir a linha já afirma que houve conferência
  (`validated_at`), porque quem grava é o resultado de um `channels.list` real;
- reconectar um canal cria/atualiza **a autorização daquele canal**, sem tocar nas outras;
- o status nunca é presumido: sem credencial → `DISCONNECTED`, vencido → `EXPIRED`,
  revogado → `REVOKED` (derivado do cofre + vínculo, nunca de um campo digitado);
- o fluxo antigo por projeto (`application/youtube_oauth.py`, escopo `youtube:{project_id}`)
  continua de pé — nada aqui o substitui.
"""
from __future__ import annotations

import secrets as _secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from ..domain.channel import ChannelYouTubeTargetNotFound
from ..domain.ids import check_id
from ..domain.youtube_channel import OAuthStatus
from ..domain.youtube_identity import (
    ChannelAuthorization,
    GoogleAccount,
    OAuthGrant,
    YouTubeChannelIdentity,
    validate_email,
    validate_youtube_channel_id,
)
from ..domain.youtube_oauth import (
    DEFAULT_SCOPES,
    OAuthIdentity,
    derive_channel_status,
    pkce_pair,
    token_set_from_response,
)
from .errors import InvalidInput, ServiceUnavailable
from .ports import (
    ChannelAuthorizationRepository,
    ChannelProfileRepository,
    GoogleAccountRepository,
    OAuthClient,
    OAuthGrantRepository,
    SecretStore,
    YouTubeChannelIdentityRepository,
)
from .youtube_channels import (
    ACCESS_TOKEN,
    OAUTH_CODE_VERIFIER,
    OAUTH_REVOKED,
    OAUTH_SCOPES,
    OAUTH_STATE,
    OAUTH_STATE_EXPIRES_AT,
    REFRESH_TOKEN,
    TOKEN_EXPIRES_AT,
)

# Mesma validade curta do fluxo antigo (F8-05): o consentimento abandonado não fica eterno.
CONSENT_TTL = timedelta(minutes=10)
DEFAULT_REDIRECT_URI = "http://localhost:8000/studio/oauth/callback"
_CREDENTIAL_KEYS = (ACCESS_TOKEN, REFRESH_TOKEN)
_MAX_STATE = 256


class ConnectionNotFound(LookupError):
    """O canal do estúdio ou o canal do YouTube referenciado não existe."""


class AuthorizationNotFound(LookupError):
    """O vínculo autorização↔canal referenciado não existe."""


class AccountConsentStateInvalid(InvalidInput):
    """O `state` do consentimento não confere, expirou ou não existe (→ 422)."""


class AccountIdentityUnavailable(InvalidInput):
    """O consentimento não expôs a identidade da conta (e-mail): não se inventa a conta (→ 422)."""


def grant_scope(grant_id: str) -> str:
    """Escopo do cofre da autorização (tokens no cofre, nunca no banco)."""
    return f"oauth_grant:{check_id(grant_id)}"


def consent_scope(state: str) -> str:
    """Escopo do cofre do consentimento em curso (PKCE por `state`)."""
    return f"oauth_consent:{state}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe(operation):
    try:
        return operation()
    except Exception as exc:  # cofre indisponível vira 503, nunca 500 cru
        raise ServiceUnavailable("secret store unavailable") from exc


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _valid_state(state: object) -> str:
    """O `state` é opaco e vem da rede: recusa forma inválida antes de virar escopo do cofre."""
    if not isinstance(state, str):
        raise AccountConsentStateInvalid("the OAuth callback has no state")
    cleaned = state.strip()
    if not cleaned or len(cleaned) > _MAX_STATE or any(ch not in
                                                       "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-:"
                                                       for ch in cleaned):
        raise AccountConsentStateInvalid("the OAuth callback state is not in the expected form")
    return cleaned


class BeginAccountConsent:
    """Gera a URL de autorização + `state` (PKCE); guarda state/verifier no cofre com validade curta."""

    def __init__(self, oauth: OAuthClient, secrets: SecretStore, *, redirect_uri: str = DEFAULT_REDIRECT_URI,
                 scopes: Sequence[str] = DEFAULT_SCOPES, clock=_utc_now):
        self.oauth, self.secrets = oauth, secrets
        self.redirect_uri, self.scopes, self.clock = redirect_uri, tuple(scopes), clock

    def execute(self) -> dict[str, object]:
        verifier, challenge = pkce_pair()
        state = _secrets.token_urlsafe(32)
        expires_at = self.clock() + CONSENT_TTL
        url = self.oauth.authorization_url(self.redirect_uri, self.scopes, state, challenge)
        scope = consent_scope(state)
        _safe(lambda: self.secrets.set(scope, OAUTH_STATE, state))
        _safe(lambda: self.secrets.set(scope, OAUTH_CODE_VERIFIER, verifier))
        _safe(lambda: self.secrets.set(scope, OAUTH_STATE_EXPIRES_AT, _iso(expires_at)))
        return {"authorization_url": url, "state": state, "expires_at": _iso(expires_at)}


class CompleteAccountConsent:
    """Troca o código, identifica a **conta** e o canal, e grava conta/grant/canal/vínculo validado.

    A autorização (grant) guarda os tokens no cofre (`oauth_grant:{grant_id}`); o banco guarda só
    metadados. O vínculo é gravado com `validated_at` porque existir a linha já afirma que a
    conferência (`oauth.identity`, `channels.list mine=true`) foi feita para aquele canal.
    """

    def __init__(self, oauth: OAuthClient, accounts: GoogleAccountRepository, grants: OAuthGrantRepository,
                 channels: YouTubeChannelIdentityRepository, links: ChannelAuthorizationRepository,
                 secrets: SecretStore, *, redirect_uri: str = DEFAULT_REDIRECT_URI, clock=_utc_now):
        self.oauth, self.accounts, self.grants = oauth, accounts, grants
        self.channels, self.links, self.secrets = channels, links, secrets
        self.redirect_uri, self.clock = redirect_uri, clock

    def execute(self, code: str, state: str, *, email: str | None = None) -> dict[str, object]:
        state = _valid_state(state)
        scope = consent_scope(state)
        expected = _safe(lambda: self.secrets.get(scope, OAUTH_STATE))
        expires_at = _parse_iso(_safe(lambda: self.secrets.get(scope, OAUTH_STATE_EXPIRES_AT)))
        if not expected or not _secrets.compare_digest(expected, state):
            raise AccountConsentStateInvalid("the OAuth state does not match the started consent")
        if expires_at is None or expires_at <= self.clock():
            raise AccountConsentStateInvalid("the OAuth consent state expired; start the consent again")
        verifier = _safe(lambda: self.secrets.get(scope, OAUTH_CODE_VERIFIER))
        if not verifier:
            raise AccountConsentStateInvalid("the OAuth consent lost its PKCE verifier; start again")
        if not isinstance(code, str) or not code.strip():
            raise AccountConsentStateInvalid("the OAuth callback has no code")

        response = self.oauth.exchange_code(code.strip(), self.redirect_uri, verifier)
        tokens = token_set_from_response(response, now=self.clock())
        identity: OAuthIdentity = self.oauth.identity(tokens.access_token)

        chosen_email = (getattr(identity, "email", "") or email or "").strip()
        if not chosen_email:
            raise AccountIdentityUnavailable(
                "the authorized account did not expose an email; reconnect with account identity")
        account_email = validate_email(chosen_email)  # e-mail malformado nunca vira conta
        youtube_channel_id = validate_youtube_channel_id(identity.channel_id)

        now = self.clock()
        account = self.accounts.upsert(GoogleAccount(id=uuid.uuid4().hex, email=account_email))
        channel = self.channels.upsert(YouTubeChannelIdentity(youtube_channel_id=youtube_channel_id,
                                                             title=identity.title))
        grant = self.grants.create(OAuthGrant(id=uuid.uuid4().hex, account_id=account.id,
                                              scopes=tokens.scopes, status=OAuthStatus.CONNECTED,
                                              token_expires_at=tokens.expires_at))
        link = self.links.link(ChannelAuthorization(grant_id=grant.id,
                                                    youtube_channel_id=channel.youtube_channel_id,
                                                    status=OAuthStatus.CONNECTED, validated_at=now))

        # Tokens por autorização, só no cofre. Uma falha do cofre derruba o caso de uso sem deixar
        # token órfão; a autorização fica sem credencial (status derivado DISCONNECTED, honesto).
        gscope = grant_scope(grant.id)
        _safe(lambda: self.secrets.set(gscope, ACCESS_TOKEN, tokens.access_token))
        if tokens.refresh_token:
            _safe(lambda: self.secrets.set(gscope, REFRESH_TOKEN, tokens.refresh_token))
        _safe(lambda: self.secrets.set(gscope, TOKEN_EXPIRES_AT, _iso(tokens.expires_at)))
        _safe(lambda: self.secrets.set(gscope, OAUTH_SCOPES, " ".join(tokens.scopes)))

        _safe(lambda: self.secrets.delete(scope, OAUTH_STATE))
        _safe(lambda: self.secrets.delete(scope, OAUTH_CODE_VERIFIER))
        _safe(lambda: self.secrets.delete(scope, OAUTH_STATE_EXPIRES_AT))

        return {"account": {"id": account.id, "email": account.email, "display_name": account.display_name},
                "channel": {"youtube_channel_id": channel.youtube_channel_id, "title": channel.title},
                "grant_id": grant.id, "status": link.status.value,
                "validated_at": link.validated_at.isoformat() if link.validated_at else None}


class ListConnections:
    """O quadro real: conta → canais (do **nosso** banco) → status → qual canal do estúdio publica ali.

    Não há chamada ao vivo: a lista é o que já foi conferido e gravado (conta, autorização,
    identidade do canal e vínculo validado). O status é derivado do cofre + do vínculo.
    """

    def __init__(self, accounts: GoogleAccountRepository, grants: OAuthGrantRepository,
                 channels: YouTubeChannelIdentityRepository, links: ChannelAuthorizationRepository,
                 profiles: ChannelProfileRepository, secrets: SecretStore, *, clock=_utc_now):
        self.accounts, self.grants, self.channels = accounts, grants, channels
        self.links, self.profiles, self.secrets = links, profiles, secrets
        self.clock = clock

    def _status(self, grant: OAuthGrant, link: ChannelAuthorization, now: datetime) -> tuple[str, datetime | None]:
        gscope = grant_scope(grant.id)
        names = set(_safe(lambda: self.secrets.names(gscope)))
        has_credentials = bool(names & set(_CREDENTIAL_KEYS))
        expiry = _parse_iso(_safe(lambda: self.secrets.get(gscope, TOKEN_EXPIRES_AT))) or grant.token_expires_at
        status = derive_channel_status(has_credentials=has_credentials,
                                       revoked=link.status == OAuthStatus.REVOKED,
                                       expires_at=expiry, now=now, stored=grant.status.value)
        return status, expiry

    def execute(self) -> dict[str, object]:
        now = self.clock()
        accounts = self.accounts.list()
        grants_by_account = {account.id: self.grants.list_for_account(account.id) for account in accounts}
        grants_by_id = {grant.id: grant for grants in grants_by_account.values() for grant in grants}
        board = {account.id: {"id": account.id, "email": account.email,
                              "display_name": account.display_name, "channels": []} for account in accounts}

        studio: dict[str, list[dict[str, object]]] = {}
        for profile in self.profiles.list(include_archived=True):
            if profile.youtube_channel_id:
                studio.setdefault(profile.youtube_channel_id, []).append(
                    {"id": profile.id, "name": profile.name, "archived": profile.archived})

        for channel in self.channels.list():
            for link in self.links.authorizations_for_channel(channel.youtube_channel_id):
                grant = grants_by_id.get(link.grant_id)
                if grant is None or grant.account_id not in board:  # vínculo órfão: honesto, não inventa
                    continue
                status, expiry = self._status(grant, link, now)
                board[grant.account_id]["channels"].append({
                    "youtube_channel_id": channel.youtube_channel_id,
                    "title": channel.title,
                    "grant_id": link.grant_id,
                    "status": status,
                    "token_expires_at": expiry.isoformat() if expiry else None,
                    "validated_at": link.validated_at.isoformat() if link.validated_at else None,
                    "studio_channels": studio.get(channel.youtube_channel_id, []),
                })
        return {"accounts": list(board.values())}


class LinkStudioChannel:
    """Aponta o canal do estúdio para o canal do YouTube que já foi validado no consentimento."""

    def __init__(self, profiles: ChannelProfileRepository, channels: YouTubeChannelIdentityRepository):
        self.profiles, self.channels = profiles, channels

    def _change(self, profile_id: str, youtube_channel_id: str | None):
        pid = check_id(profile_id)
        profile = self.profiles.get(pid)
        if profile is None:
            raise ConnectionNotFound("channel profile not found")
        if youtube_channel_id is not None:
            cid = validate_youtube_channel_id(youtube_channel_id)
            if self.channels.get(cid) is None:
                raise ChannelYouTubeTargetNotFound(f"youtube channel {cid!r} does not exist")
            changes: dict[str, object] = {"youtube_channel_id": cid}
        else:
            changes = {"youtube_channel_id": None}
        updated = self.profiles.update(pid, profile.version, changes)
        if updated is None:
            raise ConnectionNotFound("channel profile not found")
        return updated

    def execute(self, profile_id: str, youtube_channel_id: str):
        return self._change(profile_id, youtube_channel_id)


class Unlink:
    """Limpa o destino de publicação do canal do estúdio (o canal deixa de publicar em qualquer lugar)."""

    def __init__(self, profiles: ChannelProfileRepository):
        self.profiles = profiles

    def execute(self, profile_id: str):
        pid = check_id(profile_id)
        profile = self.profiles.get(pid)
        if profile is None:
            raise ConnectionNotFound("channel profile not found")
        updated = self.profiles.update(pid, profile.version, {"youtube_channel_id": None})
        if updated is None:
            raise ConnectionNotFound("channel profile not found")
        return updated


class RevokeAuthorization:
    """Revoga uma autorização **isoladamente**: marca o vínculo REVOKED sem tocar nas outras.

    Só revoga no Google e apaga os tokens da autorização quando **nenhum outro** vínculo vivo a
    usa — o modelo absorve um grant com vários canais, e revogar um canal não pode derrubar o outro.
    """

    def __init__(self, grants: OAuthGrantRepository, links: ChannelAuthorizationRepository,
                 channels: YouTubeChannelIdentityRepository, secrets: SecretStore,
                 oauth: OAuthClient | None = None, *, clock=_utc_now):
        self.grants, self.links, self.channels = grants, links, channels
        self.secrets, self.oauth, self.clock = secrets, oauth, clock

    def _has_other_live_link(self, grant_id: str, youtube_channel_id: str) -> bool:
        for channel in self.channels.list():
            if channel.youtube_channel_id == youtube_channel_id:
                continue
            for link in self.links.authorizations_for_channel(channel.youtube_channel_id):
                if link.grant_id == grant_id and link.status != OAuthStatus.REVOKED:
                    return True
        return False

    def execute(self, grant_id: str, youtube_channel_id: str) -> dict[str, object]:
        gid = check_id(grant_id)
        cid = validate_youtube_channel_id(youtube_channel_id)
        if self.links.get(gid, cid) is None:
            raise AuthorizationNotFound(f"authorization {gid!r}/{cid!r} does not exist")

        self.links.revoke(gid, cid)  # marca este vínculo; não apaga a linha nem o `validated_at`

        if self._has_other_live_link(gid, cid):  # a autorização ainda serve outro canal: não tocar
            return {"grant_id": gid, "youtube_channel_id": cid, "status": OAuthStatus.REVOKED.value}

        gscope = grant_scope(gid)
        token = (_safe(lambda: self.secrets.get(gscope, REFRESH_TOKEN))
                 or _safe(lambda: self.secrets.get(gscope, ACCESS_TOKEN)))
        if self.oauth is not None and token:
            self.oauth.revoke(token)  # revogar duas vezes é idempotente no adapter
        for key in (ACCESS_TOKEN, REFRESH_TOKEN, TOKEN_EXPIRES_AT, OAUTH_SCOPES, OAUTH_REVOKED):
            _safe(lambda k=key: self.secrets.delete(gscope, k))
        self.grants.update_status(gid, OAuthStatus.REVOKED)
        return {"grant_id": gid, "youtube_channel_id": cid, "status": OAuthStatus.REVOKED.value}
