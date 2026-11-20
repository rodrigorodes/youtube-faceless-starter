"""Atomic step attempt bookkeeping; callers own side effects and recovery."""
import re
import uuid

from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated


class PostgresStepRepository(_Base):
    def begin(self, video_id: str, step: str, input_hash: str) -> str | None:
        if not step or len(step) > 100 or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise ValueError("invalid step or input hash")
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT id FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
            if not row:
                raise ValueError("video not found")
            if conn.execute("SELECT 1 FROM studio.step_runs WHERE video_id=%s AND step=%s AND status='RUNNING'", (video_id, step)).fetchone():
                raise RuntimeError("step already running")
            if conn.execute("SELECT 1 FROM studio.step_runs WHERE video_id=%s AND step=%s AND input_hash=%s AND status='SUCCEEDED'",
                            (video_id, step, input_hash)).fetchone():
                return None
            run_id = uuid.uuid4().hex
            conn.execute("INSERT INTO studio.step_runs(id, video_id, step, attempt, status, input_hash) "
                         "VALUES (%s,%s,%s,(SELECT COALESCE(MAX(attempt),0)+1 FROM studio.step_runs WHERE video_id=%s AND step=%s),'RUNNING',%s)",
                         (run_id, video_id, step, video_id, step, input_hash))
            return run_id

    def finish(self, run_id: str, succeeded: bool) -> bool:
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.step_runs SET status=%s, finished_at=now() WHERE id=%s AND status='RUNNING'",
                               ("SUCCEEDED" if succeeded else "FAILED", check_id(run_id)))
            return cur.rowcount == 1

    def attempt(self, run_id: str) -> int:
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT attempt FROM studio.step_runs WHERE id=%s", (check_id(run_id),)).fetchone()
            if not row:
                raise ValueError("step run not found")
            return row[0]
