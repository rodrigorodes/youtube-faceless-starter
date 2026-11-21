"""F9-02: coletar métricas autorizadas por porta, sem inventar número nem origem.

O serviço decide a prontidão (canal conectado, escopo ``yt-analytics.readonly`` concedido e
publicação com id remoto), chama a porta só quando tudo existe e converte a resposta em
``MetricMeasurement`` ligada às versões do vídeo. Falha de autorização, timeout ou resposta
inválida viram estado ``not_yet_available`` com motivo — nunca 0, nunca média estimada.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ..domain.analytics_learning import (
    ANALYTICS_READONLY_SCOPE,
    CANONICAL_UNITS,
    PERCENT_METRICS,
    AnalyticsPeriod,
    CollectionReadiness,
    MetricMeasurement,
    MissingVersionLink,
    VersionAttribution,
)
from ..domain.insight import MetricObservation, MetricWindow
from .analytics_ports import AnalyticsRepository, AnalyticsVideoInfo, ChannelAnalyticsState

# Métricas que o dashboard promete. Ausência de qualquer uma vira "ainda não disponível".
CORE_METRICS = ("views", "impressions", "ctr", "average_view_percentage",
                "estimated_minutes_watched")
# Métricas que entram se a API devolver; não poluem a tela quando não vêm.
OPTIONAL_METRICS = ("average_view_duration_s", "likes", "comments", "shares",
                    "subscribers_gained")
_KNOWN_METRICS = (*CORE_METRICS, *OPTIONAL_METRICS)

SOURCE_API = "API YouTube Analytics"


class AnalyticsCollectionError(Exception):
    """Erro de coleta que vira estado explícito, não stack trace."""


class AnalyticsNotAuthorized(AnalyticsCollectionError):
    """Sem escopo ou sem token: a porta não pode chamar a API."""


class AnalyticsUnavailable(AnalyticsCollectionError):
    """API fora do ar, tempo esgotado ou resposta fora do contrato."""


class AnalyticsVideoNotFound(LookupError):
    """Vídeo inexistente no Studio."""


class AnalyticsPillarNotFound(LookupError):
    """Pilar que não pertence ao projeto do vídeo: não atribuímos métrica a ele."""


@dataclass(frozen=True)
class AnalyticsQuery:
    channel_id: str
    start: datetime
    end: datetime
    youtube_video_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class AnalyticsPoint:
    metric: str
    value: float


class AnalyticsCollectionPort(Protocol):
    scope: str

    def collect(self, query: AnalyticsQuery) -> tuple[AnalyticsPoint, ...]: ...


@dataclass(frozen=True)
class CollectionRequest:
    video_id: str
    period: AnalyticsPeriod
    pillar_id: str | None = None


@dataclass(frozen=True)
class CollectionOutcome:
    readiness: CollectionReadiness
    collected: bool
    measurements: tuple[MetricMeasurement, ...] = ()
    reason: str | None = None
    saved: int = 0


def _missing(video: AnalyticsVideoInfo) -> tuple[MissingVersionLink, ...]:
    """Motivos explícitos para cada versão que o Studio ainda não consegue enxergar."""
    links: list[MissingVersionLink] = []
    if video.script_version is None:
        links.append(MissingVersionLink(kind="script",
                                        reason="nenhum roteiro persistido para este vídeo"))
    if video.publication_id is None:
        links.append(MissingVersionLink(kind="publication",
                                        reason="nenhuma publicação registrada para este vídeo"))
    if video.youtube_video_id is None:
        links.append(MissingVersionLink(kind="youtube_video",
                                        reason="sem id remoto do YouTube (F8 não implementado)"))
    # Briefing e embalagem existem como contrato (F3/F7), mas ainda não como persistência.
    links.append(MissingVersionLink(kind="brief",
                                    reason="briefing ainda não é persistido nesta versão"))
    links.append(MissingVersionLink(kind="packaging",
                                    reason="embalagem ainda não é persistida nesta versão"))
    return tuple(links)


def attribution_for(video: AnalyticsVideoInfo) -> VersionAttribution:
    """Atribuição real do vídeo. Versão ausente nunca vira zero nem é omitida."""
    return VersionAttribution(
        video_id=video.id,
        script_version=video.script_version,
        publication_id=video.publication_id,
        youtube_video_id=video.youtube_video_id,
        missing=_missing(video),
    )


def _known_metric(metric: str, value: float) -> None:
    if metric not in CANONICAL_UNITS:
        raise AnalyticsUnavailable(f"métrica desconhecida na resposta: {metric!r}")
    if not isinstance(value, float) or not math.isfinite(value):
        raise AnalyticsUnavailable(f"valor não finito para {metric}")
    if value < 0:
        raise AnalyticsUnavailable(f"valor negativo para {metric}")
    if metric in PERCENT_METRICS and value > 100:
        raise AnalyticsUnavailable(f"percentual fora de 0..100 para {metric}")


class CollectMetrics:
    """Caso de uso da coleta. Só persiste quando a autorização e o id remoto existem."""

    def __init__(self, port: AnalyticsCollectionPort, repo: AnalyticsRepository,
                 clock=lambda: datetime.now(timezone.utc)):
        self.port = port
        self.repo = repo
        self.clock = clock

    def readiness(self, video: AnalyticsVideoInfo,
                  channel: ChannelAnalyticsState) -> CollectionReadiness:
        reasons: list[str] = []
        if not channel.connected:
            reasons.append("canal YouTube não conectado: OAuth ausente ou expirado")
        if ANALYTICS_READONLY_SCOPE not in channel.scopes:
            reasons.append("escopo yt-analytics.readonly não concedido para este canal")
        if not (video.publication_id and video.youtube_video_id):
            reasons.append(
                "nenhuma publicação autorizada/coletada: o vídeo ainda não tem id remoto do YouTube")
        return CollectionReadiness(
            channel_connected=channel.connected,
            scope_granted=ANALYTICS_READONLY_SCOPE in channel.scopes,
            publication_available=bool(video.publication_id and video.youtube_video_id),
            reasons=tuple(reasons),
        )

    def execute(self, request: CollectionRequest) -> CollectionOutcome:
        video = self.repo.video(request.video_id)
        if video is None:
            raise AnalyticsVideoNotFound(f"video {request.video_id!r} not found")
        if request.pillar_id is not None:
            known = {pillar_id for pillar_id, _ in self.repo.pillars(video.project_id)}
            if request.pillar_id not in known:
                raise AnalyticsPillarNotFound(
                    f"pillar {request.pillar_id!r} not in project")
        channel = self.repo.channel_state(video.project_id)
        readiness = self.readiness(video, channel)
        if not readiness.is_ready:
            return CollectionOutcome(readiness=readiness, collected=False,
                                      reason="; ".join(readiness.reasons))

        query = AnalyticsQuery(channel_id=channel.channel_id or "",
                               start=request.period.start_at,
                               end=request.period.end_at,
                               youtube_video_id=video.youtube_video_id,
                               project_id=video.project_id)
        try:
            points = tuple(self.port.collect(query))
        except AnalyticsNotAuthorized as exc:
            return CollectionOutcome(readiness=readiness, collected=False,
                                      reason=f"coleta não autorizada: {exc}")
        except AnalyticsUnavailable as exc:
            return CollectionOutcome(readiness=readiness, collected=False,
                                      reason=f"coleta indisponível: {exc}")

        values: dict[str, float] = {}
        for point in points:
            _known_metric(point.metric, point.value)
            if point.metric in _KNOWN_METRICS:
                values[point.metric] = float(point.value)

        now = self.clock()
        window = MetricWindow(start_at=request.period.start_at, end_at=request.period.end_at)
        attribution = attribution_for(video)
        metrics = list(CORE_METRICS) + [m for m in OPTIONAL_METRICS if m in values]
        rows: list[MetricMeasurement] = []
        for metric in metrics:
            measured = metric in values
            observation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"studio-analytics|{video.id}|{metric}|{query.start.isoformat()}"
                f"|{query.end.isoformat()}|{video.youtube_video_id}",
            ).hex
            observation = MetricObservation(
                observation_id=observation_id,
                metric=metric,
                unit=CANONICAL_UNITS[metric],
                window=window,
                source=SOURCE_API,
                collected_at=now,
                state="measured" if measured else "not_yet_available",
                value=values.get(metric) if measured else None,
                unavailable_reason=None if measured else (
                    f"a {SOURCE_API} não devolveu {metric} na janela"),
            )
            rows.append(MetricMeasurement(
                observation=observation,
                origin="youtube_analytics_api",
                attribution=attribution,
                pillar_id=request.pillar_id,
            ))
        saved = self.repo.save_measurements(video.project_id, rows)
        return CollectionOutcome(readiness=readiness, collected=True,
                                  measurements=tuple(rows), saved=saved)