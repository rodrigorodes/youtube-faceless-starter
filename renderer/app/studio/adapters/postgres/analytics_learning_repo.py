"""Persistência F9: medição ligada à versão, experimento e decisão de revisão.

Nenhuma linha é gravada sem origem declarada. `save_measurements` é idempotente pelo
`observation_id` determinístico; a FK composta de `script_version` impede versão inventada.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...application.analytics_ports import (
    AnalyticsVideoInfo,
    ChannelAnalyticsState,
    StoredMetric,
)
from ...domain.analytics_learning import (
    ExperimentConclusion,
    ExperimentRecord,
    ExperimentVariant,
    MetricMeasurement,
    RecommendationDecision,
)
from ...domain.ids import check_id
from ...domain.insight import ConfidenceDeclaration, MetricObservation, MetricWindow
from .editorial_repo import _Base
from .repo import _translated

_VIDEO_SQL = """
SELECT v.id, v.project_id, v.topic, v.format, v.status, v.created_at, v.updated_at,
       s.version AS script_version,
       p.id AS publication_id, p.youtube_video_id, p.status AS publication_status
FROM studio.videos v
LEFT JOIN LATERAL (
    SELECT version FROM studio.scripts WHERE video_id = v.id ORDER BY version DESC LIMIT 1
) s ON true
LEFT JOIN studio.publications p ON p.video_id = v.id
"""

_OBSERVATION_SQL = """
SELECT o.*, v.topic, v.format, c.name AS pillar_name
FROM studio.metric_observations o
JOIN studio.videos v ON v.id = o.video_id
LEFT JOIN studio.project_categories c ON c.id = o.pillar_id
WHERE o.project_id = %s AND o.window_start >= %s AND o.window_end <= %s
"""


def _video(row: dict) -> AnalyticsVideoInfo:
    return AnalyticsVideoInfo(
        id=row["id"], project_id=row["project_id"], topic=row["topic"], format=row["format"],
        status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
        script_version=row["script_version"], publication_id=row["publication_id"],
        youtube_video_id=row["youtube_video_id"], publication_status=row["publication_status"],
    )


def _measurement(row: dict) -> MetricMeasurement:
    value = row["value"]
    observation = MetricObservation(
        observation_id=row["observation_id"], metric=row["metric"], unit=row["unit"],
        window=MetricWindow(start_at=row["window_start"], end_at=row["window_end"]),
        source=row["source"], collected_at=row["collected_at"],
        state="measured" if value is not None else "not_yet_available",
        value=float(value) if value is not None else None,
        unavailable_reason=row["unavailable_reason"],
    )
    return MetricMeasurement(
        observation=observation,
        origin=row["origin"],
        attribution={
            "video_id": row["video_id"],
            "script_version": row["script_version"],
            "brief_version": row["brief_version"],
            "packaging_version": row["packaging_version"],
            "publication_id": row["publication_id"],
            "youtube_video_id": row["youtube_video_id"],
            "missing": row["missing_links"],
        },
        pillar_id=row["pillar_id"],
        experiment_id=row["experiment_id"],
        variant_id=row["variant_id"],
    )


class PostgresAnalyticsLearningRepository(_Base):
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        super().__init__(connect)

    # -- leitura de contexto -------------------------------------------------------------

    def projects(self) -> list[tuple[str, str]]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name FROM studio.projects ORDER BY name")
            return [(row["id"], row["name"]) for row in cur.fetchall()]

    def project_name(self, project_id: str) -> str | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT name FROM studio.projects WHERE id = %s", (check_id(project_id),))
            row = cur.fetchone()
            return row["name"] if row else None

    def videos(self, project_id: str) -> list[AnalyticsVideoInfo]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_VIDEO_SQL + " WHERE v.project_id = %s ORDER BY v.updated_at DESC LIMIT 500",
                        (check_id(project_id),))
            return [_video(row) for row in cur.fetchall()]

    def video(self, video_id: str) -> AnalyticsVideoInfo | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_VIDEO_SQL + " WHERE v.id = %s", (check_id(video_id),))
            row = cur.fetchone()
            return _video(row) if row else None

    def pillars(self, project_id: str) -> list[tuple[str, str]]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, name FROM studio.project_categories "
                        "WHERE project_id = %s ORDER BY name", (check_id(project_id),))
            return [(row["id"], row["name"]) for row in cur.fetchall()]

    def channel_state(self, project_id: str) -> ChannelAnalyticsState:
        now = datetime.now(timezone.utc)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT channel_id, scopes, oauth_status, token_expires_at "
                        "FROM studio.channel_youtube_channels WHERE project_id = %s",
                        (check_id(project_id),))
            row = cur.fetchone()
        if row is None:
            return ChannelAnalyticsState(connected=False, channel_id=None, scopes=(),
                                         token_expires_at=None)
        scopes = tuple(row["scopes"] or ())
        expires = row["token_expires_at"]
        connected = (row["oauth_status"] == "CONNECTED"
                     and (expires is None or expires > now))
        return ChannelAnalyticsState(connected=connected, channel_id=row["channel_id"],
                                     scopes=scopes, token_expires_at=expires)

    # -- medições ------------------------------------------------------------------------

    def observations(self, *, project_id: str, start: datetime, end: datetime,
                     video_id: str | None = None,
                     pillar_id: str | None = None) -> list[StoredMetric]:
        sql = _OBSERVATION_SQL
        params: list[object] = [check_id(project_id), start, end]
        if video_id is not None:
            sql += " AND o.video_id = %s"
            params.append(check_id(video_id))
        if pillar_id is not None:
            sql += " AND o.pillar_id = %s"
            params.append(check_id(pillar_id))
        sql += " ORDER BY o.collected_at, o.observation_id"
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, tuple(params))
            return [StoredMetric(measurement=_measurement(row), topic=row["topic"],
                                 format=row["format"], pillar_name=row["pillar_name"])
                    for row in cur.fetchall()]

    def last_collected_at(self, project_id: str) -> datetime | None:
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT MAX(collected_at) FROM studio.metric_observations "
                        "WHERE project_id = %s", (check_id(project_id),))
            return cur.fetchone()[0]

    def save_measurements(self, project_id: str,
                          rows: Sequence[MetricMeasurement]) -> int:
        p_id = check_id(project_id)
        sql = """
            INSERT INTO studio.metric_observations (
                observation_id, project_id, video_id, youtube_video_id, pillar_id, metric, unit,
                value, unavailable_reason, window_start, window_end, source, origin,
                script_version, brief_version, packaging_version, publication_id, missing_links,
                experiment_id, variant_id, collected_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (observation_id) DO UPDATE SET
                value = EXCLUDED.value,
                unavailable_reason = EXCLUDED.unavailable_reason,
                collected_at = EXCLUDED.collected_at,
                missing_links = EXCLUDED.missing_links,
                pillar_id = EXCLUDED.pillar_id,
                script_version = EXCLUDED.script_version,
                publication_id = EXCLUDED.publication_id,
                youtube_video_id = EXCLUDED.youtube_video_id
        """
        with _translated(), self._connect() as conn:
            for measurement in rows:
                observation = measurement.observation
                attribution = measurement.attribution
                conn.execute(sql, (
                    observation.observation_id, p_id, attribution.video_id,
                    attribution.youtube_video_id, measurement.pillar_id, observation.metric,
                    observation.unit, observation.value, observation.unavailable_reason,
                    observation.window.start_at, observation.window.end_at, observation.source,
                    measurement.origin, attribution.script_version, attribution.brief_version,
                    attribution.packaging_version, attribution.publication_id,
                    Jsonb([link.model_dump() for link in attribution.missing]),
                    measurement.experiment_id, measurement.variant_id, observation.collected_at,
                ))
        return len(rows)

    # -- experimentos --------------------------------------------------------------------

    def experiments(self, project_id: str) -> list[ExperimentRecord]:
        p_id = check_id(project_id)
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM studio.analytics_experiments WHERE project_id = %s "
                        "ORDER BY created_at DESC, experiment_id", (p_id,))
            experiments = cur.fetchall()
            if not experiments:
                return []
            cur.execute("SELECT * FROM studio.analytics_experiment_variants "
                        "WHERE experiment_id = ANY(%s) ORDER BY is_control DESC, variant_id",
                        ([row["experiment_id"] for row in experiments],))
            variants: dict[str, list[ExperimentVariant]] = {}
            for row in cur.fetchall():
                variants.setdefault(row["experiment_id"], []).append(
                    ExperimentVariant(variant_id=row["variant_id"], label=row["label"],
                                      is_control=row["is_control"]))
        result = []
        for row in experiments:
            window = (MetricWindow(start_at=row["window_start"], end_at=row["window_end"])
                      if row["window_start"] is not None else None)
            conclusion = None
            if row["conclusion"] is not None:
                conclusion = ExperimentConclusion(
                    statement=row["conclusion"],
                    confidence=ConfidenceDeclaration(
                        level=row["conclusion_confidence"],
                        basis=row["conclusion_basis"],
                        declared_by=row["concluded_by"],
                    ),
                    observation_ids=tuple(row["conclusion_observation_ids"] or ()),
                    concluded_at=row["concluded_at"],
                )
            result.append(ExperimentRecord(
                experiment_id=row["experiment_id"], project_id=row["project_id"],
                video_id=row["video_id"], kind=row["kind"], status=row["status"],
                variants=tuple(variants.get(row["experiment_id"], ())),
                approved_by=row["approved_by"], approved_at=row["approved_at"],
                platform_note=row["platform_note"],
                platform_ab_supported=row["platform_ab_supported"],
                window=window, conclusion=conclusion,
            ))
        return result

    def save_experiment(self, experiment: ExperimentRecord) -> None:
        conclusion = experiment.conclusion
        sql = """
            INSERT INTO studio.analytics_experiments (
                experiment_id, project_id, video_id, kind, status, platform_ab_supported,
                platform_note, approved_by, approved_at, window_start, window_end, conclusion,
                conclusion_confidence, conclusion_basis, conclusion_observation_ids,
                concluded_by, concluded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (experiment_id) DO UPDATE SET
                kind = EXCLUDED.kind, status = EXCLUDED.status,
                platform_note = EXCLUDED.platform_note, approved_by = EXCLUDED.approved_by,
                approved_at = EXCLUDED.approved_at, window_start = EXCLUDED.window_start,
                window_end = EXCLUDED.window_end, conclusion = EXCLUDED.conclusion,
                conclusion_confidence = EXCLUDED.conclusion_confidence,
                conclusion_basis = EXCLUDED.conclusion_basis,
                conclusion_observation_ids = EXCLUDED.conclusion_observation_ids,
                concluded_by = EXCLUDED.concluded_by, concluded_at = EXCLUDED.concluded_at
        """
        with _translated(), self._connect() as conn:
            conn.execute(sql, (
                experiment.experiment_id, experiment.project_id, experiment.video_id,
                experiment.kind, experiment.status, experiment.platform_ab_supported,
                experiment.platform_note, experiment.approved_by, experiment.approved_at,
                experiment.window.start_at if experiment.window else None,
                experiment.window.end_at if experiment.window else None,
                conclusion.statement if conclusion else None,
                conclusion.confidence.level if conclusion else None,
                conclusion.confidence.basis if conclusion else None,
                list(conclusion.observation_ids) if conclusion else [],
                conclusion.confidence.declared_by if conclusion else None,
                conclusion.concluded_at if conclusion else None,
            ))
            conn.execute("UPDATE studio.analytics_experiment_variants SET is_control = false "
                         "WHERE experiment_id = %s", (experiment.experiment_id,))
            conn.execute("DELETE FROM studio.analytics_experiment_variants "
                         "WHERE experiment_id = %s AND NOT (variant_id = ANY(%s))",
                         (experiment.experiment_id,
                          [variant.variant_id for variant in experiment.variants]))
            for variant in experiment.variants:
                conn.execute(
                    "INSERT INTO studio.analytics_experiment_variants "
                    "(experiment_id, variant_id, label, is_control) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (experiment_id, variant_id) DO UPDATE SET "
                    "label = EXCLUDED.label, is_control = EXCLUDED.is_control",
                    (experiment.experiment_id, variant.variant_id, variant.label,
                     variant.is_control))

    # -- decisões ------------------------------------------------------------------------

    def decisions(self, project_id: str) -> list[RecommendationDecision]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT recommendation_id, decision, decided_by, decided_at "
                        "FROM studio.analytics_recommendation_decisions WHERE project_id = %s "
                        "ORDER BY decided_at DESC", (check_id(project_id),))
            return [RecommendationDecision(recommendation_id=row["recommendation_id"],
                                           decision=row["decision"], decided_by=row["decided_by"],
                                           decided_at=row["decided_at"])
                    for row in cur.fetchall()]

    def save_decision(self, project_id: str, decision: RecommendationDecision) -> None:
        with _translated(), self._connect() as conn:
            conn.execute(
                "INSERT INTO studio.analytics_recommendation_decisions "
                "(recommendation_id, project_id, decision, decided_by, decided_at, evidence) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (recommendation_id) DO UPDATE SET "
                "decision = EXCLUDED.decision, decided_by = EXCLUDED.decided_by, "
                "decided_at = EXCLUDED.decided_at",
                (decision.recommendation_id, check_id(project_id), decision.decision,
                 decision.decided_by, decision.decided_at, Jsonb([])),
            )