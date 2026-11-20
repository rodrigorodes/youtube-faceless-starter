"""Repositório de tópicos e métricas de tendência (Postgres)."""
import json
import uuid
from datetime import datetime

from psycopg.rows import dict_row

from ...application.ports import TrendRecord, TrendRepository
from ...domain.ids import check_id
from ...domain.panel import topic_key
from ...domain.trends import TrendItem
from .editorial_repo import _Base
from .repo import _translated


class PostgresTrendRepository(_Base):
    def upsert(self, project_id: str, items: list[TrendItem]) -> int:
        p_id = check_id(project_id)
        if not items:
            return 0

        with _translated(), self._connect() as conn:
            for item in items:
                t_id = uuid.uuid4().hex
                t_key = topic_key(item.topic)
                evidence_json = json.dumps([ev.model_dump(mode="json") for ev in item.evidence])

                conn.execute(
                    """
                    INSERT INTO studio.trend_topics (
                        id, project_id, topic, topic_key, source_name, source_url,
                        observed_at, window_start, window_end, metric_name, metric_value, evidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (project_id, topic_key, source_name, window_end) DO UPDATE SET
                        topic = EXCLUDED.topic,
                        observed_at = EXCLUDED.observed_at,
                        window_start = EXCLUDED.window_start,
                        metric_name = EXCLUDED.metric_name,
                        metric_value = EXCLUDED.metric_value,
                        evidence = EXCLUDED.evidence
                    """,
                    (
                        t_id,
                        p_id,
                        item.topic,
                        t_key,
                        item.source_name,
                        item.source_url,
                        item.observed_at,
                        item.window_start,
                        item.window_end,
                        item.metric_name,
                        item.metric_value,
                        evidence_json,
                    ),
                )
        return len(items)

    def list(self, project_id: str | None, since: datetime) -> list[TrendRecord]:
        params: list[object] = [since]
        clause = ""
        if project_id is not None:
            clause = "AND project_id = %s"
            params.append(check_id(project_id))

        query = f"""
            SELECT id, project_id, topic, topic_key, source_name, source_url,
                   observed_at, window_start, window_end, metric_name, metric_value, evidence
            FROM studio.trend_topics
            WHERE window_end >= %s {clause}
            ORDER BY metric_value DESC NULLS LAST, observed_at DESC
        """

        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            TrendRecord(
                id=r["id"],
                project_id=r["project_id"],
                topic=r["topic"],
                topic_key=r["topic_key"],
                source_name=r["source_name"],
                source_url=r["source_url"],
                observed_at=r["observed_at"],
                window_start=r["window_start"],
                window_end=r["window_end"],
                metric_name=r["metric_name"],
                metric_value=float(r["metric_value"]) if r["metric_value"] is not None else None,
                evidence=r["evidence"] or [],
            )
            for r in rows
        ]

    def last_collected_at(self, project_id: str | None) -> datetime | None:
        params: list[object] = []
        clause = ""
        if project_id is not None:
            clause = "WHERE project_id = %s"
            params.append(check_id(project_id))

        query = f"SELECT MAX(observed_at) FROM studio.trend_topics {clause}"
        with _translated(), self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            res = cur.fetchone()
            return res[0] if res and res[0] is not None else None
