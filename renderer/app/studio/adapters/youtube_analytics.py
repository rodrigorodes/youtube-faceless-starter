"""Adaptador da YouTube Analytics API v2 (escopo ``yt-analytics.readonly``).

Sem SDK de provedor e sem chamar a rede nos testes: o cliente HTTP é injetável. O adaptador
recusa a chamada sem escopo/token, exige uma única linha de resposta para o vídeo filtrado e
converte nomes de coluna da API para as métricas canônicas do contrato F9.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

from ..application.analytics_collection import (
    AnalyticsNotAuthorized,
    AnalyticsPoint,
    AnalyticsQuery,
    AnalyticsUnavailable,
)
from ..domain.analytics_learning import ANALYTICS_READONLY_SCOPE, CANONICAL_UNITS

BASE_URL = "https://youtubeanalytics.googleapis.com/v2/reports"

# Nome da coluna na API -> métrica canônica do contrato.
API_METRIC_NAMES: dict[str, str] = {
    "views": "views",
    "impressions": "impressions",
    "impressionClickThroughRate": "ctr",
    "averageViewPercentage": "average_view_percentage",
    "estimatedMinutesWatched": "estimated_minutes_watched",
    "averageViewDuration": "average_view_duration_s",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "subscribersGained": "subscribers_gained",
}
ANALYTICS_METRICS = tuple(API_METRIC_NAMES)
_UNSET = object()


def _default_http_get(url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
    import httpx

    try:
        response = httpx.get(url, headers=dict(headers), timeout=15.0)
    except httpx.HTTPError as exc:
        raise AnalyticsUnavailable(f"falha de rede na coleta: {exc}") from exc
    if response.status_code in (401, 403):
        raise AnalyticsNotAuthorized(
            f"a API recusou a leitura (HTTP {response.status_code}); "
            "verifique o escopo yt-analytics.readonly e o token")
    if response.status_code >= 400:
        raise AnalyticsUnavailable(f"a API respondeu HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise AnalyticsUnavailable("a resposta da API não é JSON") from exc
    if not isinstance(payload, Mapping):
        raise AnalyticsUnavailable("a resposta da API não é um objeto")
    return payload


class YoutubeAnalyticsAdapter:
    """Porta concreta de coleta. Nunca loga token nem devolve credencial."""

    scope = ANALYTICS_READONLY_SCOPE

    def __init__(self, *, channel_id: str, access_token: str, scope_granted: bool,
                 http_get: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = _UNSET,
                 base_url: str = BASE_URL):
        self.channel_id = channel_id
        self._access_token = access_token
        self.scope_granted = scope_granted
        self.base_url = base_url
        self._http_get = _default_http_get if http_get is _UNSET else http_get

    def _authorize(self) -> None:
        if not self.scope_granted:
            raise AnalyticsNotAuthorized(
                f"escopo {ANALYTICS_READONLY_SCOPE} não concedido; coleta não autorizada")
        if not self._access_token.strip():
            raise AnalyticsNotAuthorized("token OAuth ausente; coleta não autorizada")

    def _url(self, query: AnalyticsQuery) -> str:
        if not self.channel_id.strip():
            raise AnalyticsUnavailable("canal sem id: coleta não pode ser direcionada")
        if query.end <= query.start:
            raise AnalyticsUnavailable("janela de coleta inválida: fim deve ser depois do início")
        params = {
            "ids": f"channel=={self.channel_id}",
            "startDate": query.start.date().isoformat(),
            "endDate": query.end.date().isoformat(),
            "metrics": ",".join(ANALYTICS_METRICS),
        }
        if query.youtube_video_id:
            params["filters"] = f"video=={query.youtube_video_id}"
        return f"{self.base_url}?{urlencode(params)}"

    def collect(self, query: AnalyticsQuery) -> tuple[AnalyticsPoint, ...]:
        self._authorize()
        if self._http_get is None:
            raise AnalyticsUnavailable("cliente HTTP da coleta não configurado")
        payload = self._http_get(self._url(query),
                                 {"Authorization": f"Bearer {self._access_token}"})
        headers = payload.get("columnHeaders")
        rows = payload.get("rows", [])
        if not isinstance(headers, list) or not isinstance(rows, list):
            raise AnalyticsUnavailable("resposta da API sem columnHeaders/rows válidos")
        names: list[str] = []
        for header in headers:
            name = header.get("name") if isinstance(header, Mapping) else None
            if not isinstance(name, str) or not name:
                raise AnalyticsUnavailable("columnHeader sem nome")
            names.append(name)
        if not names:
            raise AnalyticsUnavailable("a API não devolveu colunas para a consulta")
        if len(set(names)) != len(names):
            raise AnalyticsUnavailable("a API devolveu colunas duplicadas")
        if not rows:
            return ()
        if len(rows) != 1:
            # Com `filters=video==ID` a API devolve uma linha; somar várias esconderia dimensão.
            raise AnalyticsUnavailable(
                f"a API devolveu {len(rows)} linhas para um vídeo filtrado")
        row = rows[0]
        if not isinstance(row, list) or len(row) != len(names):
            raise AnalyticsUnavailable("linha da API não casa com as colunas")

        points: list[AnalyticsPoint] = []
        for name, raw in zip(names, row):
            metric = API_METRIC_NAMES.get(name)
            if metric is None:
                continue  # coluna extra: ignorada, nunca vira métrica inventada
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise AnalyticsUnavailable(f"valor não numérico para {metric}")
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise AnalyticsUnavailable(f"valor inválido para {metric}: {raw!r}")
            if metric in ("ctr", "average_view_percentage") and not 0.0 <= value <= 100.0:
                raise AnalyticsUnavailable(f"percentual fora de 0..100 para {metric}")
            points.append(AnalyticsPoint(metric=metric, value=value))
        return tuple(points)