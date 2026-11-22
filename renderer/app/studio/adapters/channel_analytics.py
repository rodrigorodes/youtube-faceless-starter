"""Porta de coleta por canal: lê escopo/token do cofre e delega à YouTube Analytics API.

O token nunca é logado nem devolvido. Sem canal associado, sem escopo ou sem token, a coleta
é recusada com erro de autorização — não há tentativa "anônima" de adivinhar métrica.
"""
from __future__ import annotations

from ..application.analytics_collection import (
    AnalyticsNotAuthorized,
    AnalyticsPoint,
    AnalyticsQuery,
    AnalyticsUnavailable,
)
from ..application.ports import ChannelProfileRepository, SecretStore, YouTubeChannelRepository
from ..application.youtube_channels import ACCESS_TOKEN, youtube_scope
from ..domain.analytics_learning import ANALYTICS_READONLY_SCOPE
from .youtube_analytics import YoutubeAnalyticsAdapter

_UNSET = object()


class ChannelAnalyticsAdapter:
    """Resolve o canal do projeto e usa o token do cofre; nunca aceita escopo do cliente."""

    scope = ANALYTICS_READONLY_SCOPE

    def __init__(self, channels: YouTubeChannelRepository, secrets: SecretStore,
                 http_get=_UNSET, *, targets: ChannelProfileRepository | None = None,
                 grant_tokens=None):
        """`targets`/`grant_tokens` (F01.T02): canal com destino lê o token do **grant** dele.

        Sem destino configurado, vale o caminho legado (cofre `youtube:{project}` + escopos do
        vínculo). A coleta nunca mistura identidades: ou o grant do canal de destino, ou o legado.
        """
        self.channels = channels
        self.secrets = secrets
        self._http_get = http_get
        self.targets = targets
        self.grant_tokens = grant_tokens

    def collect(self, query: AnalyticsQuery) -> tuple[AnalyticsPoint, ...]:
        if not query.project_id:
            raise AnalyticsNotAuthorized("canal não identificado; coleta não autorizada")
        profile = None
        if self.targets is not None:
            try:
                profile = self.targets.get_by_project(query.project_id)
            except Exception:  # id inválido é "sem destino", como no gate de publicação
                profile = None
        if profile is not None and profile.youtube_channel_id is not None and self.grant_tokens is not None:
            return self._collect_with_grant(profile.youtube_channel_id, query)

        channel = self.channels.get(query.project_id)
        if channel is None:
            raise AnalyticsNotAuthorized("nenhum canal YouTube associado a este projeto")
        scope_name = youtube_scope(query.project_id)
        try:
            token = self.secrets.get(scope_name, ACCESS_TOKEN)
        except Exception as exc:  # cofre indisponível não vira 500 na coleta
            raise AnalyticsUnavailable("cofre de segredos indisponível") from exc
        return self._adapter(channel.channel_id, token or "",
                             ANALYTICS_READONLY_SCOPE in channel.scopes, query)

    def _collect_with_grant(self, channel_id: str, query: AnalyticsQuery):
        """Token do grant do canal de destino; sem o escopo de leitura, recusa (não adivinha)."""
        try:
            access = self.grant_tokens.execute(query.project_id)
        except Exception as exc:  # sem vínculo/revogado: recusa explícita, não 500
            raise AnalyticsNotAuthorized(
                "a autorização do canal de destino não está disponível para a coleta") from exc
        if ANALYTICS_READONLY_SCOPE not in tuple(access.scopes):
            raise AnalyticsNotAuthorized(
                "a autorização do canal de destino não inclui a leitura de analytics; reconecte com esse escopo")
        return self._adapter(channel_id, access.token, True, query)

    def _adapter(self, channel_id: str, token: str, scope_granted: bool, query: AnalyticsQuery):
        adapter = YoutubeAnalyticsAdapter(
            channel_id=channel_id,
            access_token=token,
            scope_granted=scope_granted,
            **({} if self._http_get is _UNSET else {"http_get": self._http_get}),
        )
        return adapter.collect(query)