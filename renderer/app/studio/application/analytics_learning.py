"""Casos de uso de revisão e histórico de experimentos (F9-05/F9-06).

Nenhum dos dois altera configuração de canal. A decisão grava apenas o registro de revisão
(``accepted_for_review``/``rejected``) e o experimento grava a rotação manual aprovada por
humano. "Aplicar" não existe como operação nesta fatia.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from ..domain.analytics_learning import (
    ExperimentConclusion,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentVariant,
    RecommendationDecision,
)
from ..domain.insight import ConfidenceDeclaration, MetricWindow
from .analytics_collection import AnalyticsVideoNotFound
from .analytics_ports import AnalyticsRepository
from .errors import InvalidInput, ProjectNotFound

PLATFORM_NOTE = ("A API do YouTube Analytics não expõe experimentos A/B de thumbnail/título; "
                 "o histórico registra uma rotação manual aprovada por humano.")


class DecideRecommendation:
    """Registra a revisão humana de uma recomendação; não toca no perfil do canal."""

    def __init__(self, repo: AnalyticsRepository,
                 clock=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.clock = clock

    def execute(self, project_id: str, recommendation_id: str, decision: str,
                decided_by: str) -> RecommendationDecision:
        if self.repo.project_name(project_id) is None:
            raise ProjectNotFound(project_id)
        if decision not in ("accepted_for_review", "rejected"):
            raise InvalidInput("decision must be accepted_for_review or rejected")
        record = RecommendationDecision(
            recommendation_id=recommendation_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=self.clock(),
        )
        self.repo.save_decision(project_id, record)
        return record


class RegisterExperiment:
    """Grava um experimento manual; o suporte A/B da plataforma não é declarado."""

    def __init__(self, repo: AnalyticsRepository):
        self.repo = repo

    def execute(self, *, project_id: str, video_id: str, kind: str, status: ExperimentStatus,
                variants: Sequence[ExperimentVariant], approved_by: str,
                window: MetricWindow | None = None,
                conclusion: ExperimentConclusion | None = None) -> ExperimentRecord:
        video = self.repo.video(video_id)
        if video is None or video.project_id != project_id:
            raise AnalyticsVideoNotFound(f"video {video_id!r} not in project")
        if not approved_by.strip():
            raise InvalidInput("approved_by is required")
        record = ExperimentRecord(
            experiment_id=_experiment_id(video_id, kind, str(status), window, conclusion),
            project_id=project_id,
            video_id=video_id,
            kind=kind,
            status=status,
            variants=tuple(variants),
            approved_by=approved_by,
            platform_note=PLATFORM_NOTE,
            window=window,
            conclusion=conclusion,
        )
        self.repo.save_experiment(record)
        return record


def _experiment_id(video_id: str, kind: str, status: str,
                   window: MetricWindow | None, conclusion: ExperimentConclusion | None) -> str:
    import uuid

    start = window.start_at.isoformat() if window else ""
    end = window.end_at.isoformat() if window else ""
    statement = conclusion.statement if conclusion else ""
    return uuid.uuid5(uuid.NAMESPACE_URL,
                      f"studio-experiment|{video_id}|{kind}|{status}|{start}|{end}|{statement}").hex


def conclusion_from(*, statement: str | None, level: str | None, basis: str | None,
                    observation_ids: Sequence[str], declared_by: str,
                    concluded_at: datetime | None = None) -> ExperimentConclusion | None:
    """Monta a conclusão declarada; campos faltando são erro explícito, não default inventado."""
    if not statement:
        if level or basis or observation_ids:
            raise InvalidInput("confidence/evidence without a conclusion statement")
        return None
    if not level or not basis or not observation_ids:
        raise InvalidInput(
            "conclusion requires statement, confidence, basis and at least one observation id")
    return ExperimentConclusion(
        statement=statement,
        confidence=ConfidenceDeclaration(level=level, basis=basis, declared_by=declared_by),
        observation_ids=tuple(observation_ids),
        concluded_at=concluded_at or datetime.now(timezone.utc),
    )