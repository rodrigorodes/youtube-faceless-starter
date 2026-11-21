"""Portas compartilhadas da fatia F9 (analytics e loop de aprendizado).

Só dependem do domínio. O adaptador Postgres e o cliente HTTP do YouTube implementam estas
interfaces; a aplicação nunca importa SDK nem psycopg.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..domain.analytics_learning import (
    ExperimentRecord,
    MetricMeasurement,
    RecommendationDecision,
)


@dataclass(frozen=True)
class AnalyticsVideoInfo:
    """Vídeo com as versões reais que a atribuição consegue enxergar hoje."""

    id: str
    project_id: str
    topic: str
    format: str
    status: str
    created_at: datetime
    updated_at: datetime
    script_version: int | None = None
    publication_id: str | None = None
    youtube_video_id: str | None = None
    publication_status: str | None = None


@dataclass(frozen=True)
class StoredMetric:
    """Medição persistida com o contexto de vídeo/pilar que o dashboard precisa."""

    measurement: MetricMeasurement
    topic: str
    format: str
    pillar_name: str | None = None


@dataclass(frozen=True)
class ChannelAnalyticsState:
    """Metadados OAuth do canal; nunca inclui token nem segredo."""

    connected: bool
    channel_id: str | None
    scopes: tuple[str, ...]
    token_expires_at: datetime | None = None


class AnalyticsRepository(Protocol):
    """Persistência do loop de aprendizado. Nenhum método devolve segredo."""

    def projects(self) -> list[tuple[str, str]]: ...

    def project_name(self, project_id: str) -> str | None: ...

    def videos(self, project_id: str) -> list[AnalyticsVideoInfo]: ...

    def video(self, video_id: str) -> AnalyticsVideoInfo | None: ...

    def pillars(self, project_id: str) -> list[tuple[str, str]]: ...

    def channel_state(self, project_id: str) -> ChannelAnalyticsState: ...

    def observations(self, *, project_id: str, start: datetime, end: datetime,
                     video_id: str | None = None,
                     pillar_id: str | None = None) -> list[StoredMetric]: ...

    def last_collected_at(self, project_id: str) -> datetime | None: ...

    def save_measurements(self, project_id: str,
                          rows: Sequence[MetricMeasurement]) -> int: ...

    def experiments(self, project_id: str) -> list[ExperimentRecord]: ...

    def save_experiment(self, experiment: ExperimentRecord) -> None: ...

    def decisions(self, project_id: str) -> list[RecommendationDecision]: ...

    def save_decision(self, project_id: str, decision: RecommendationDecision) -> None: ...