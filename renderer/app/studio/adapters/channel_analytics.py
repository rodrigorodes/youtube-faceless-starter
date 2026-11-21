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
from ..application.ports import SecretStore, YouTubeChannelRepository
from ..application.youtube_channels import ACCESS_TOKEN, youtube_scope
from ..domain.analytics_learning import ANALYTICS_READONLY_SCOPE
from .youtube_analytics import YoutubeAnalyticsAdapter

_UNSET = object()


class ChannelAnalyticsAdapter:
    """Resolve o canal do projeto e usa o token do cofre; nunca aceita escopo do cliente."""

    scope = ANALYTICS_READONLY_SCOPE

    def __init__(self, channels: YouTubeChannelRepository, secrets: SecretStore,
                 http_get=_UNSET):
        self.channels = channels
        self.secrets = secrets
        self._http_get = http_get

    def collect(self, query: AnalyticsQuery) -> tuple[AnalyticsPoint, ...]:
        if not query.project_id:
            raise AnalyticsNotAuthorized("canal não identificado; coleta não autorizada")
        channel = self.channels.get(query.project_id)
        if channel is None:
            raise AnalyticsNotAuthorized("nenhum canal YouTube associado a este projeto")
        scope_name = youtube_scope(query.project_id)
        try:
            token = self.secrets.get(scope_name, ACCESS_TOKEN)
        except Exception as exc:  # cofre indisponível não vira 500 na coleta
            raise AnalyticsUnavailable("cofre de segredos indisponível") from exc
        adapter = YoutubeAnalyticsAdapter(
            channel_id=channel.channel_id,
            access_token=token or "",
            scope_granted=ANALYTICS_READONLY_SCOPE in channel.scopes,
            **({} if self._http_get is _UNSET else {"http_get": self._http_get}),
        )
        return adapter.collect(query)