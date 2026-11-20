"""Daily upsert and SQL aggregates; no credentials or YouTube calls."""
from psycopg.rows import dict_row

from ...application.analytics import DailyMetric
from .editorial_repo import _Base
from .repo import _translated

_METRICS = ("views", "estimated_minutes_watched", "average_view_duration_s", "average_view_percentage",
            "likes", "comments", "shares", "subscribers_gained")


class PostgresAnalyticsRepository(_Base):
    def upsert(self, metric: DailyMetric) -> None:
        columns = ("video_id", "date", *_METRICS)
        updates = ", ".join(f"{column}=EXCLUDED.{column}" for column in _METRICS)
        with _translated(), self._connect() as conn:
            conn.execute(f"INSERT INTO studio.video_metrics ({', '.join(columns)}) "
                         f"VALUES ({', '.join(['%s'] * len(columns))}) "
                         f"ON CONFLICT (video_id, date) DO UPDATE SET {updates}",
                         tuple(getattr(metric, column) for column in columns))

    def weekly(self, start, end):
        if end < start or (end - start).days > 6:
            raise ValueError("report interval must be at most seven days")
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT m.video_id, v.topic, SUM(views) AS views, SUM(likes) AS likes, "
                        "SUM(comments) AS comments, SUM(shares) AS shares, "
                        "SUM(estimated_minutes_watched) AS estimated_minutes_watched, "
                        "BOOL_AND(views IS NOT NULL) AS views_complete, "
                        "array_agg(m.date ORDER BY m.date) AS days FROM studio.video_metrics m "
                        "JOIN studio.videos v ON v.id=m.video_id "
                        "WHERE m.date BETWEEN %s AND %s GROUP BY m.video_id, v.topic ORDER BY m.video_id", (start, end))
            rows = cur.fetchall()
        result = []
        for row in rows:
            small = row["views"] is None or row["views"] < 100
            suggestion = None if small or not row["views_complete"] else {
                "topic": row["topic"],
                "note": "Explorar variações deste tema; visualizações não demonstram desempenho superior.",
                "evidence": [{"video_id": row["video_id"], "date": day} for day in row["days"]],
            }
            result.append({**row, "sample_small": small, "suggestion": suggestion})
        return result
