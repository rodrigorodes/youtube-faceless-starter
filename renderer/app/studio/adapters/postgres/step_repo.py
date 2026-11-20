"""Atomic step attempt bookkeeping; callers own side effects and recovery."""
import re
import uuid
import contextlib
import threading
import weakref

import psycopg
from ...domain.ids import check_id
from .editorial_repo import _Base
from .repo import _translated

_render_locks = weakref.WeakValueDictionary()
_render_locks_guard = threading.Lock()


class PostgresStepRepository(_Base):
    @contextlib.contextmanager
    def render_guard(self, video_id: str):
        """Serialize recovery and render execution, even if the lock connection drops."""
        video_id = check_id(video_id)
        with _render_locks_guard:
            lock = _render_locks.get(video_id)
            if lock is None:
                lock = threading.Lock()
                _render_locks[video_id] = lock
        if not lock.acquire(blocking=False):
            raise RuntimeError("step already running")
        conn = None
        try:
            with _translated():
                conn = self._connect()
                conn.autocommit = True
                acquired = conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                                        ("render-step:" + video_id,)).fetchone()[0]
                if not acquired:
                    raise RuntimeError("step already running")
                conn.execute("UPDATE studio.step_runs SET status='FAILED', error_class='Interrupted', finished_at=now() "
                             "WHERE video_id=%s AND step='render' AND status='RUNNING'", (video_id,))
            yield
        finally:
            if conn is not None:
                try:
                    conn.close()
                except psycopg.Error:
                    pass
            lock.release()

    def begin(self, video_id: str, step: str, input_hash: str, *, reusable: bool = True) -> str | None:
        if not step or len(step) > 100 or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise ValueError("invalid step or input hash")
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT id FROM studio.videos WHERE id = %s FOR UPDATE", (check_id(video_id),)).fetchone()
            if not row:
                raise ValueError("video not found")
            if conn.execute("SELECT 1 FROM studio.step_runs WHERE video_id=%s AND step=%s AND status='RUNNING'", (video_id, step)).fetchone():
                raise RuntimeError("step already running")
            if reusable and conn.execute("SELECT 1 FROM studio.step_runs WHERE video_id=%s AND step=%s AND input_hash=%s AND status='SUCCEEDED'",
                            (video_id, step, input_hash)).fetchone():
                return None
            run_id = uuid.uuid4().hex
            conn.execute("INSERT INTO studio.step_runs(id, video_id, step, attempt, status, input_hash) "
                         "VALUES (%s,%s,%s,(SELECT COALESCE(MAX(attempt),0)+1 FROM studio.step_runs WHERE video_id=%s AND step=%s),'RUNNING',%s)",
                         (run_id, video_id, step, video_id, step, input_hash))
            return run_id

    def fail_interrupted_render(self) -> int:
        with _translated(), self._connect() as conn:
            cur = conn.execute("UPDATE studio.step_runs SET status='FAILED', error_class='Interrupted', "
                               "finished_at=now() WHERE step='render' AND status='RUNNING'")
            return cur.rowcount

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
