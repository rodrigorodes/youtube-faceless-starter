"""Token da publicação resolvido pela autorização (grant) do canal de destino (F01.T01).

Resolução: projeto → canal do estúdio (`channel_profiles`) → destino do YouTube →
autorização validada (`channel_authorizations`) → grant (`oauth_grants`) → tokens no cofre
(`oauth_grant:{grant_id}`), renovando **pelo refresh do próprio grant**.

Por que assim:

- o token é da autorização **daquele canal**, conferida no consentimento (`validated_at`); não é
  um token do projeto nem do ambiente, e não existe cópia de token entre canais;
- entre vínculos vigentes vale o **mais recente**: reconectar um canal cria um grant novo, e é
  ele que passa a publicar (o vínculo anterior fica no histórico, mas não é escolhido);
- ausência de autorização vigente, grant revogado/em erro ou credencial sem como renovar **falha
  fechado** com erro nomeado (`OAuthReconnectRequired`): nenhum upload acontece e nenhum outro
  canal é tentado;
- `invalid_grant` marca aquele vínculo e o grant como `REVOKED` e apaga os tokens mortos do
  escopo do grant — sem tocar em outros canais/grants;
- o cofre é a única fonte de valores: nenhum token aparece em `repr`, resposta ou mensagem de erro.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..domain.ids import check_id
from ..domain.youtube_channel import OAuthStatus
from ..domain.youtube_identity import ChannelAuthorization
from ..domain.youtube_oauth import (
    TOKEN_SKEW,
    OAuthReconnectRequired,
    token_set_from_response,
)
from .connections import grant_scope
from .errors import ServiceUnavailable
from .ports import (
    AccessToken,
    ChannelAuthorizationRepository,
    ChannelProfileRepository,
    OAuthClient,
    OAuthGrantRepository,
    SecretStore,
)
from .youtube_channels import (
    ACCESS_TOKEN,
    OAUTH_SCOPES,
    REFRESH_TOKEN,
    TOKEN_EXPIRES_AT,
)

_MIN_INSTANT = datetime.min.replace(tzinfo=timezone.utc)


class ChannelGrantMissing(OAuthReconnectRequired):
    """O canal de destino não tem autorização vigente: reconectar antes de publicar (falha fechada)."""


class ChannelGrantRevoked(OAuthReconnectRequired):
    """A autorização do canal de destino foi revogada (ou está em erro): não se publica."""


class ChannelGrantUnusable(OAuthReconnectRequired):
    """A autorização existe, mas não fornece token: sem credencial ou sem refresh para renovar."""


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


class EnsureGrantAccessToken:
    """Access token do canal de destino, obtido e renovado pela autorização (grant) daquele canal.

    Implementa a mesma porta que o caminho legado (`TokenProvider.execute(project_id)`) e devolve
    o canal junto do token — que é o destino validado do projeto, não um canal deduzido do valor do
    token. Com destino configurado, este é o **único** caminho de token: não há fallback.
    """

    def __init__(self, channels: ChannelProfileRepository, authorizations: ChannelAuthorizationRepository,
                 grants: OAuthGrantRepository, secrets: SecretStore, oauth: OAuthClient, *, clock=_utc_now):
        self.channels, self.authorizations, self.grants = channels, authorizations, grants
        self.secrets, self.oauth, self.clock = secrets, oauth, clock

    def _target(self, project_id: str) -> str:
        channel = self.channels.get_by_project(project_id)
        if channel is None or channel.youtube_channel_id is None:
            # Só chega aqui quem tem destino; o legado é decidido por `TargetChannelTokenProvider`.
            raise ChannelGrantMissing(f"the project {project_id} has no YouTube target configured")
        return channel.youtube_channel_id

    def _authorization(self, target: str) -> ChannelAuthorization:
        live = [authorization for authorization in self.authorizations.authorizations_for_channel(target)
                if authorization.youtube_channel_id == target
                and authorization.status is OAuthStatus.CONNECTED]
        if not live:
            raise ChannelGrantMissing(
                f"no connected authorization for the expected YouTube channel {target}; reconnect it")
        # O vínculo mais recente é o resultado da última conferência (reconectar cria um novo).
        live.sort(key=lambda authorization: (authorization.validated_at or authorization.created_at or _MIN_INSTANT,
                                             authorization.grant_id))
        return live[-1]

    def _renew(self, grant_id: str, target: str, scope: str, refresh: str, now: datetime) -> AccessToken:
        try:
            response = self.oauth.refresh(refresh)
        except OAuthReconnectRequired:
            # A credencial morreu: não há retry cego. Apaga só os tokens mortos deste grant e marca
            # o vínculo/grant como revogados — os demais canais e grants ficam intactos.
            _safe(lambda: self.secrets.delete(scope, ACCESS_TOKEN))
            _safe(lambda: self.secrets.delete(scope, REFRESH_TOKEN))
            self.authorizations.revoke(grant_id, target)
            self.grants.update_status(grant_id, OAuthStatus.REVOKED)
            raise
        tokens = token_set_from_response(response, now=now)
        refreshed = tokens.refresh_token or refresh
        _safe(lambda: self.secrets.set(scope, ACCESS_TOKEN, tokens.access_token))
        _safe(lambda: self.secrets.set(scope, REFRESH_TOKEN, refreshed))
        _safe(lambda: self.secrets.set(scope, TOKEN_EXPIRES_AT, _iso(tokens.expires_at)))
        _safe(lambda: self.secrets.set(scope, OAUTH_SCOPES, " ".join(tokens.scopes)))
        self.grants.update_status(grant_id, OAuthStatus.CONNECTED, token_expires_at=tokens.expires_at)
        return AccessToken(tokens.access_token, target, tuple(tokens.scopes))

    def execute(self, project_id: str) -> AccessToken:
        p_id = check_id(project_id)
        target = self._target(p_id)
        authorization = self._authorization(target)
        grant = self.grants.get(authorization.grant_id)
        if grant is None:
            raise ChannelGrantMissing(
                f"the authorization {authorization.grant_id!r} of channel {target} no longer exists; reconnect it")
        if grant.status in (OAuthStatus.REVOKED, OAuthStatus.ERROR):
            raise ChannelGrantRevoked(
                f"the authorization of channel {target} is {grant.status.value}; reconnect it")

        scope = grant_scope(grant.id)
        now = self.clock()
        access = _safe(lambda: self.secrets.get(scope, ACCESS_TOKEN))
        expiry = _parse_iso(_safe(lambda: self.secrets.get(scope, TOKEN_EXPIRES_AT))) or grant.token_expires_at
        if access and (expiry is None or expiry > now + TOKEN_SKEW):
            return AccessToken(access, target, tuple(grant.scopes))  # vigente do canal certo
        refresh = _safe(lambda: self.secrets.get(scope, REFRESH_TOKEN))
        if not refresh:
            raise ChannelGrantUnusable(
                f"the authorization of channel {target} has no refresh token to renew it; reconnect it")
        return self._renew(grant.id, target, scope, refresh, now)