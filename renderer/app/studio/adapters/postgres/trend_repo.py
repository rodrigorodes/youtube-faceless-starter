"""Repositório de tópicos e métricas de tendência (Postgres)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from psycopg.rows import dict_row

from ...application.ports import TrendRecord, TrendRepository
from ...domain.ids import check_id
from ...domain.panel import topic_key
from ...domain.trend_priority import SavedTrendSnapshot
from ...domain.trends import TrendItem
from .editorial_repo import _Base
from .repo import _translated

_RECORD_COLUMNS = (
    "id, project_id, topic, topic_key, source_name, source_url, "
    "observed_at, window_start, window_end, metric_name, metric_value, evidence, category_id"
)


def _is_sqlite(conn: object) -> bool:
    mod = getattr(conn.__class__, "__module__", "").lower()
    name = getattr(conn.__class__, "__name__", "").lower()
    return "sqlite" in mod or "sqlite" in name


def _execute(conn: object, sql: str, params: tuple = ()) -> None:
    if _is_sqlite(conn):
        conn.execute(sql.replace("%s", "?"), params)
    else:
        conn.execute(sql, params)


def _query_all(conn: object, sql: str, params: tuple = ()) -> list[dict]:
    if _is_sqlite(conn):
        cur = conn.cursor()
        cur.execute(sql.replace("%s", "?"), params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    else:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _query_one(conn: object, sql: str, params: tuple = ()) -> dict | None:
    if _is_sqlite(conn):
        cur = conn.cursor()
        cur.execute(sql.replace("%s", "?"), params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description] if cur.description else []
        return dict(zip(cols, row))
    else:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def _saved_snapshot(row: dict) -> SavedTrendSnapshot:
    created_at = row.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            pass
    return SavedTrendSnapshot(
        project_id=row["project_id"],
        video_id=row["video_id"],
        title=row["title"],
        channel_title=row.get("channel_title"),
        thumbnail_url=row.get("thumbnail_url"),
        video_url=row.get("video_url"),
        duration=row.get("duration") or "",
        views=int(row.get("views") or 0),
        category_name=row.get("category_name"),
        score=int(row.get("score") or 0),
        created_at=created_at,
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

    def save_trend_snapshot(self, project_id: str, snapshot: SavedTrendSnapshot) -> None:
        created_at = snapshot.created_at or datetime.now(timezone.utc)
        query = """
            INSERT INTO studio.saved_trends (
                project_id, video_id, title, channel_title, thumbnail_url,
                video_url, duration, views, category_name, score, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, video_id) DO UPDATE SET
                title = EXCLUDED.title,
                channel_title = EXCLUDED.channel_title,
                thumbnail_url = EXCLUDED.thumbnail_url,
                video_url = EXCLUDED.video_url,
                duration = EXCLUDED.duration,
                views = EXCLUDED.views,
                category_name = EXCLUDED.category_name,
                score = EXCLUDED.score
        """
        params = (
            project_id,
            snapshot.video_id,
            snapshot.title,
            snapshot.channel_title,
            snapshot.thumbnail_url,
            snapshot.video_url,
            snapshot.duration or "",
            snapshot.views or 0,
            snapshot.category_name,
            snapshot.score or 0,
            created_at,
        )
        with _translated(), self._connect() as conn:
            _execute(conn, query, params)

    def unsave_trend(self, project_id: str, video_id: str) -> None:
        query = "DELETE FROM studio.saved_trends WHERE project_id = %s AND video_id = %s"
        with _translated(), self._connect() as conn:
            _execute(conn, query, (project_id, video_id))

    def list_saved_trends(self, project_id: str) -> list[SavedTrendSnapshot]:
        query = """
            SELECT project_id, video_id, title, channel_title, thumbnail_url,
                   video_url, duration, views, category_name, score, created_at
            FROM studio.saved_trends
            WHERE project_id = %s
            ORDER BY created_at DESC
        """
        with _translated(), self._connect() as conn:
            rows = _query_all(conn, query, (project_id,))
        return [_saved_snapshot(r) for r in rows]

    def is_trend_saved(self, project_id: str, video_id: str) -> bool:
        query = "SELECT 1 FROM studio.saved_trends WHERE project_id = %s AND video_id = %s LIMIT 1"
        with _translated(), self._connect() as conn:
            row = _query_one(conn, query, (project_id, video_id))
        return row is not None
