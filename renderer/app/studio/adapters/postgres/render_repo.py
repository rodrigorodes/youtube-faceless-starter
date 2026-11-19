"""Repositório Postgres dos jobs de render. A unicidade do job ativo é do índice parcial (verificar e agir numa operação só)."""
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.contracts import Asset, QaReport, RenderJob, VideoStatus
from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated

_COLUMNS = "id, video_id, status, attempt, input_hash, output_asset_id, error"


class PostgresRenderJobRepository(_Base):
    def enqueue(self, video_id: str, input_hash: str) -> tuple[RenderJob, bool]:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"INSERT INTO studio.render_jobs(id, video_id, input_hash, attempt) VALUES (%s, %s, %s, "
                        f"(SELECT COALESCE(MAX(attempt), 0) + 1 FROM studio.render_jobs WHERE video_id = %s)) "
                        f"ON CONFLICT (video_id) WHERE status IN ('QUEUED', 'RUNNING') DO NOTHING RETURNING {_COLUMNS}",
                        (uuid.uuid4().hex, check_id(video_id), input_hash, video_id))
            row = cur.fetchone()
            if row:
                return RenderJob.model_validate(row), True
            cur.execute(f"SELECT {_COLUMNS} FROM studio.render_jobs WHERE video_id = %s AND status IN ('QUEUED', 'RUNNING')", (video_id,))
            return RenderJob.model_validate(cur.fetchone()), False

    def get(self, job_id: str) -> RenderJob | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.render_jobs WHERE id = %s", (check_id(job_id),))
            row = cur.fetchone()
            return RenderJob.model_validate(row) if row else None

    def latest(self, video_id: str) -> RenderJob | None:
        with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM studio.render_jobs WHERE video_id = %s ORDER BY created_at DESC, attempt DESC LIMIT 1", (check_id(video_id),))
            row = cur.fetchone()
            return RenderJob.model_validate(row) if row else None

    def start(self, job_id: str) -> bool:
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.render_jobs SET status = 'RUNNING', started_at = now() WHERE id = %s AND status = 'QUEUED'", (check_id(job_id),))
            return cur.rowcount == 1

    def fail(self, job_id: str, error: str) -> None:
        with _translated(), self._connect() as conn:
            conn.execute("UPDATE studio.render_jobs SET status = 'FAILED', error = %s, finished_at = now() "
                         "WHERE id = %s AND status IN ('QUEUED', 'RUNNING')", (error.replace("\x00", "")[:500], check_id(job_id)))

    def fail_interrupted(self) -> int:
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.render_jobs SET status = 'FAILED', error = 'interrupted by a restart', finished_at = now() "
                               "WHERE status IN ('QUEUED', 'RUNNING')")
            return cur.rowcount

    def complete(self, job_id: str, asset: Asset, qa: QaReport) -> bool:
        with _translated(), self._connect() as conn:
            job = conn.execute("SELECT video_id FROM studio.render_jobs WHERE id = %s AND status = 'RUNNING' FOR UPDATE", (check_id(job_id),)).fetchone()
            if job is None:
                return False
            video_id = job[0]
            row = conn.execute("SELECT status FROM studio.videos WHERE id = %s FOR UPDATE", (video_id,)).fetchone()
            if row is None or row[0] not in (VideoStatus.ASSETS_READY.value, VideoStatus.RENDERED.value):
                return False
            new = VideoStatus.AWAITING_APPROVAL if qa.passed else VideoStatus.RENDERED
            conn.execute("UPDATE studio.videos SET status = %s, qa_report = %s, updated_at = now() WHERE id = %s",
                         (new.value, Jsonb(qa.model_dump(mode="json")), video_id))
            conn.execute("UPDATE studio.render_jobs SET status = 'SUCCEEDED', output_asset_id = %s, finished_at = now() WHERE id = %s",
                         (check_id(asset.id), job_id))
            return True
