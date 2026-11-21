"""Consentimento OAuth real, refresh e revogação do canal YouTube (F8-05).

Os tokens vivem só no `SecretStore` (chave `youtube:<project_id>`); o banco guarda metadados.
O status do canal é derivado do token real (expiração/revogação), nunca de um campo digitado.
Nenhuma resposta devolve access/refresh token.
"""
from __future__ import annotations

import secrets as _secrets
from dataclasses import replace
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from ..domain.ids import InvalidId, check_id
from ..domain.youtube_channel import OAuthStatus, YouTubeChannel
from ..domain.youtube_oauth import (
    DEFAULT_SCOPES,
    OAuthError,
    OAuthIdentity,
    OAuthReconnectRequired,
    OAuthTokenSet,
    derive_channel_status,
    pkce_pair,
    token_set_from_response,
)
from .errors import ServiceUnavailable
from .ports import OAuthClient, SecretStore, YouTubeChannelRepository
from .youtube_channels import (
    ACCESS_TOKEN,
    OAUTH_CODE_VERIFIER,
    OAUTH_REVOKED,
    OAUTH_SCOPES,
    OAUTH_STATE,
    OAUTH_STATE_EXPIRES_AT,
    REFRESH_TOKEN,
    TOKEN_EXPIRES_AT,
    youtube_scope,
)

CONSENT_TTL = timedelta(minutes=10)
DEFAULT_REDIRECT_URI = "http://localhost:8000/studio/oauth/callback"
_STATE_SEPARATOR = "."  # separa o projeto do nonce aleatório no `state` (não é segredo)


def consent_project_id(state: object) -> str | None:
    """Projeto codificado no `state` do consentimento, ou None se o `state` não for reconhecido.

    O Google devolve `?code=...&state=...` ao `redirect_uri`, que não carrega o projeto. O `state`
    já é emitido e comparado pelo `BeginConsent`/`CompleteConsent`; embutir o id (32 hex, público)
    permite que a página de callback saiba para qual projeto chamar o `POST .../callback` sem
    abrir a validação de `redirect_uri` do Google. O nonce aleatório continua intacto.
    """
    if not isinstance(state, str):
        return None
    prefix, separator, _ = state.partition(_STATE_SEPARATOR)
    if not separator:
        return None
    try:
        return check_id(prefix)
    except InvalidId:
        return None


class ConsentStateInvalid(OAuthError):
    """O `state` não confere, expirou ou não existe: o callback não pode trocar o código."""


class ChannelNotConnected(OAuthReconnectRequired):
    """Não há refresh token no cofre para este projeto: rode o consentimento (não é falha transitória)."""


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


def _public(project_id: str, channel: YouTubeChannel, *, store: SecretStore, now: datetime,
            expiry: datetime | None = None, revoked: bool = False) -> dict[str, object]:
    names = set(_safe(lambda: store.names(youtube_scope(project_id))))
    has_credentials = bool(names & {ACCESS_TOKEN, REFRESH_TOKEN})
    real_expiry = expiry if expiry is not None else channel.token_expires_at
    status = derive_channel_status(has_credentials=has_credentials, revoked=revoked, expires_at=real_expiry,
                                   now=now, stored=channel.oauth_status.value)
    return {
        "project_id": project_id,
        "channel_id": channel.channel_id,
        "title": channel.title,
        "scopes": list(channel.scopes),
        "oauth_status": status,
        "connected": status == "CONNECTED",
        "token_expires_at": real_expiry.isoformat() if real_expiry else None,
        "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
    }


def _revoke_mark(repo: YouTubeChannelRepository, project_id: str, store: SecretStore) -> None:
    _safe(lambda: store.set(youtube_scope(project_id), OAUTH_REVOKED, "1"))
    channel = repo.get(project_id)
    if channel is not None:
        repo.upsert(replace(channel, oauth_status=OAuthStatus.REVOKED))


class BeginConsent:
    """Gera URL de autorização + state + PKCE; grava state/verifier no cofre com validade curta."""

    def __init__(self, oauth: OAuthClient, secrets: SecretStore, *, redirect_uri: str = DEFAULT_REDIRECT_URI,
                 scopes: Sequence[str] = DEFAULT_SCOPES, clock=_utc_now):
        self.oauth, self.secrets = oauth, secrets
        self.redirect_uri, self.scopes, self.clock = redirect_uri, tuple(scopes), clock

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        scope = youtube_scope(p_id)
        verifier, challenge = pkce_pair()
        state = f"{p_id}{_STATE_SEPARATOR}{_secrets.token_urlsafe(32)}"
        expires_at = self.clock() + CONSENT_TTL
        url = self.oauth.authorization_url(self.redirect_uri, self.scopes, state, challenge)
        _safe(lambda: self.secrets.set(scope, OAUTH_STATE, state))
        _safe(lambda: self.secrets.set(scope, OAUTH_CODE_VERIFIER, verifier))
        _safe(lambda: self.secrets.set(scope, OAUTH_STATE_EXPIRES_AT, _iso(expires_at)))
        _safe(lambda: self.secrets.delete(scope, OAUTH_REVOKED))
        return {"project_id": p_id, "authorization_url": url, "state": state, "expires_at": _iso(expires_at)}


class CompleteConsent:
    """Recebe `code`+`state`, troca por tokens, identifica o canal e grava tudo no cofre."""

    def __init__(self, oauth: OAuthClient, repo: YouTubeChannelRepository, secrets: SecretStore, *,
                 redirect_uri: str = DEFAULT_REDIRECT_URI, clock=_utc_now):
        self.oauth, self.repo, self.secrets = oauth, repo, secrets
        self.redirect_uri, self.clock = redirect_uri, clock

    def execute(self, project_id: str, code: str, state: str) -> dict[str, object]:
        p_id = check_id(project_id)
        scope = youtube_scope(p_id)
        expected = _safe(lambda: self.secrets.get(scope, OAUTH_STATE))
        expires_at = _parse_iso(_safe(lambda: self.secrets.get(scope, OAUTH_STATE_EXPIRES_AT)))
        if not expected or not isinstance(state, str) or not _secrets.compare_digest(expected, state):
            raise ConsentStateInvalid("the OAuth state does not match the started consent")
        if expires_at is None or expires_at <= self.clock():
            raise ConsentStateInvalid("the OAuth consent state expired; start the consent again")
        verifier = _safe(lambda: self.secrets.get(scope, OAUTH_CODE_VERIFIER))
        if not verifier:
            raise ConsentStateInvalid("the OAuth consent lost its PKCE verifier; start again")
        if not isinstance(code, str) or not code.strip():
            raise ConsentStateInvalid("the OAuth callback has no code")

        response = self.oauth.exchange_code(code.strip(), self.redirect_uri, verifier)
        tokens = token_set_from_response(response, now=self.clock())
        identity: OAuthIdentity = self.oauth.identity(tokens.access_token)

        written: list[str] = []

        def write(key: str, value: str) -> None:
            _safe(lambda: self.secrets.set(scope, key, value))
            written.append(key)

        try:
            write(ACCESS_TOKEN, tokens.access_token)
            if tokens.refresh_token:
                write(REFRESH_TOKEN, tokens.refresh_token)
            write(TOKEN_EXPIRES_AT, _iso(tokens.expires_at))
            write(OAUTH_SCOPES, " ".join(tokens.scopes))
            _safe(lambda: self.secrets.delete(scope, OAUTH_REVOKED))
            channel = self.repo.upsert(YouTubeChannel(
                project_id=p_id, channel_id=identity.channel_id, title=identity.title,
                scopes=tokens.scopes, oauth_status=OAuthStatus.CONNECTED,
                token_expires_at=tokens.expires_at))
        except BaseException:
            for key in written:
                _safe(lambda k=key: self.secrets.delete(scope, k))
            raise
        _safe(lambda: self.secrets.delete(scope, OAUTH_STATE))
        _safe(lambda: self.secrets.delete(scope, OAUTH_CODE_VERIFIER))
        _safe(lambda: self.secrets.delete(scope, OAUTH_STATE_EXPIRES_AT))
        return _public(p_id, channel, store=self.secrets, now=self.clock(), expiry=tokens.expires_at)


class EnsureAccessToken:
    """Devolve um access token válido, renovando pelo refresh token quando necessário.

    `invalid_grant` marca o canal como REVOKED e apaga o access vencido: reconectar é decisão
    humana/UI, nunca retry cego.
    """

    def __init__(self, oauth: OAuthClient, repo: YouTubeChannelRepository, secrets: SecretStore, *, clock=_utc_now):
        self.oauth, self.repo, self.secrets, self.clock = oauth, repo, secrets, clock

    def execute(self, project_id: str) -> str:
        p_id = check_id(project_id)
        scope = youtube_scope(p_id)
        now = self.clock()
        access = _safe(lambda: self.secrets.get(scope, ACCESS_TOKEN))
        expiry = _parse_iso(_safe(lambda: self.secrets.get(scope, TOKEN_EXPIRES_AT)))
        refresh = _safe(lambda: self.secrets.get(scope, REFRESH_TOKEN))
        if access and (expiry is None or expiry > now + timedelta(seconds=120)):
            return access
        if not refresh:
            raise ChannelNotConnected("the channel has no refresh token; run the OAuth consent flow")
        try:
            response = self.oauth.refresh(refresh)
        except OAuthReconnectRequired:
            _safe(lambda: self.secrets.delete(scope, ACCESS_TOKEN))
            _revoke_mark(self.repo, p_id, self.secrets)
            raise
        tokens = token_set_from_response(response, now=now)
        refreshed = tokens.refresh_token or refresh
        _safe(lambda: self.secrets.set(scope, ACCESS_TOKEN, tokens.access_token))
        _safe(lambda: self.secrets.set(scope, REFRESH_TOKEN, refreshed))
        _safe(lambda: self.secrets.set(scope, TOKEN_EXPIRES_AT, _iso(tokens.expires_at)))
        _safe(lambda: self.secrets.set(scope, OAUTH_SCOPES, " ".join(tokens.scopes)))
        return tokens.access_token


class RevokeConsent:
    """Revoga no Google, apaga os tokens do cofre e mantém o canal como REVOKED (auditável)."""

    def __init__(self, oauth: OAuthClient, repo: YouTubeChannelRepository, secrets: SecretStore, *, clock=_utc_now):
        self.oauth, self.repo, self.secrets, self.clock = oauth, repo, secrets, clock

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        scope = youtube_scope(p_id)
        token = _safe(lambda: self.secrets.get(scope, REFRESH_TOKEN)) or _safe(lambda: self.secrets.get(scope, ACCESS_TOKEN))
        if token:
            self.oauth.revoke(token)
        for key in (ACCESS_TOKEN, REFRESH_TOKEN, TOKEN_EXPIRES_AT, OAUTH_SCOPES,
                    OAUTH_STATE, OAUTH_CODE_VERIFIER, OAUTH_STATE_EXPIRES_AT):
            _safe(lambda k=key: self.secrets.delete(scope, k))
        _revoke_mark(self.repo, p_id, self.secrets)
        channel = self.repo.get(p_id)
        if channel is None:
            return {"project_id": p_id, "channel_id": None, "title": "", "scopes": [], "oauth_status": "REVOKED",
                    "connected": False, "token_expires_at": None, "updated_at": None}
        return _public(p_id, channel, store=self.secrets, now=self.clock(), revoked=True)


class RefreshYouTubeChannel:
    """Renova o access token e devolve o status público (nunca o token) para a UI."""

    def __init__(self, ensure: EnsureAccessToken, status: GetChannelStatus):
        self.ensure, self.status = ensure, status

    def execute(self, project_id: str) -> dict[str, object]:
        self.ensure.execute(project_id)
        return self.status.execute(project_id)


class GetChannelStatus:
    """Leitura de status que usa a expiração real do token no cofre (não o campo do banco)."""

    def __init__(self, repo: YouTubeChannelRepository, secrets: SecretStore, *, clock=_utc_now):
        self.repo, self.secrets, self.clock = repo, secrets, clock

    def execute(self, project_id: str) -> dict[str, object]:
        p_id = check_id(project_id)
        channel = self.repo.get(p_id)
        if channel is None:
            return {"project_id": p_id, "channel_id": None, "title": "", "scopes": [], "oauth_status": "DISCONNECTED",
                    "connected": False, "token_expires_at": None, "updated_at": None}
        scope = youtube_scope(p_id)
        expiry = _parse_iso(_safe(lambda: self.secrets.get(scope, TOKEN_EXPIRES_AT)))
        revoked = _safe(lambda: self.secrets.get(scope, OAUTH_REVOKED)) == "1"
        return _public(p_id, channel, store=self.secrets, now=self.clock(), expiry=expiry, revoked=revoked)