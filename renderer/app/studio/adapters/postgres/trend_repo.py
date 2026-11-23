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

_RECORD_COLUMNS = (
    "id, project_id, topic, topic_key, source_name, source_url, "
    "observed_at, window_start, window_end, metric_name, metric_value, evidence, category_id"
)


def _record(row: dict) -> TrendRecord:
    return TrendRecord(
        id=row["id"],
        project_id=row["project_id"],
        topic=row["topic"],
        topic_key=row["topic_key"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        observed_at=row["observed_at"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        metric_name=row["metric_name"],
        metric_value=float(row["metric_value"]) if row["metric_value"] is not None else None,
        evidence=row["evidence"] or [],
        category_id=row.get("category_id"),
    )


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
                        observed_at, window_start, window_end, metric_name, metric_value, evidence, category_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (project_id, topic_key, source_name, window_end) DO UPDATE SET
                        topic = EXCLUDED.topic,
                        observed_at = EXCLUDED.observed_at,
                        window_start = EXCLUDED.window_start,
                        metric_name = EXCLUDED.metric_name,
                        metric_value = EXCLUDED.metric_value,
                        evidence = EXCLUDED.evidence,
                        category_id = EXCLUDED.category_id
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
                        item.category_id,
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
            SELECT {_RECORD_COLUMNS}
            FROM studio.trend_topics
            WHERE window_end >= %s {clause}
            ORDER BY metric_value DESC NULLS LAST, observed_at DESC
        """

        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [_record(r) for r in rows]

    def find_by_topic_key(self, project_id: str, topic_key: str) -> TrendRecord | None:
        query = f"""
            SELECT {_RECORD_COLUMNS}
            FROM studio.trend_topics
            WHERE project_id = %s AND topic_key = %s
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
        """
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (check_id(project_id), topic_key))
            row = cur.fetchone()
        return _record(row) if row is not None else None

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
