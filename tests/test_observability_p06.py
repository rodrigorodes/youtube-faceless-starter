import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.observability import retry_transient


class HttpFailure(Exception):
    def __init__(self, status):
        self.status_code = status


def test_retry_only_transient_with_bounded_delays():
    calls, delays = [], []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise HttpFailure(503)
        return "ok"

    assert retry_transient(operation, attempts=3, sleep=delays.append, random_value=lambda: 0.5) == "ok"
    assert len(calls) == 3 and delays == [0.5, 1.0]


def test_client_error_never_retries():
    calls = []

    def operation():
        calls.append(1)
        raise HttpFailure(400)

    with pytest.raises(HttpFailure):
        retry_transient(operation, sleep=lambda _: pytest.fail("must not sleep"))
    assert len(calls) == 1


def test_run_step_records_success_and_emits_structured_log(conn, dsn, caplog):
    import json
    import logging
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.application.observability import run_step
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("c").id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    calls = []
    with caplog.at_level(logging.INFO, logger="studio.steps"):
        assert run_step(repo, video.id, "script", "a" * 64, lambda: calls.append(1)) is True
        assert run_step(repo, video.id, "script", "a" * 64, lambda: calls.append(2)) is False
    assert calls == [1]
    record = json.loads(caplog.records[0].message)
    assert record["video_id"] == video.id and record["step"] == "script" and record["attempt"] == 1


def test_step_runs_reuse_success_only_for_identical_input(conn, dsn):
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal")
    video = videos.create_video(project.id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    run = repo.begin(video.id, "script", "a" * 64)
    assert run is not None
    with pytest.raises(RuntimeError):
        repo.begin(video.id, "script", "a" * 64)
    assert repo.finish(run, True)
    assert repo.begin(video.id, "script", "a" * 64) is None
    new = repo.begin(video.id, "script", "b" * 64)
    assert new and new != run
    assert not repo.finish(run, False)
    assert repo.finish(new, False)


def test_resume_only_starts_render_for_assets_ready():
    from types import SimpleNamespace
    from app.studio.application.observability import Resume
    from app.studio.application.editorial import StateConflict
    from app.studio.domain.contracts import VideoStatus

    video = SimpleNamespace(status=VideoStatus.ASSETS_READY)
    videos = SimpleNamespace(get_video=lambda _: video)
    calls = []
    resume = Resume(videos, SimpleNamespace(execute=lambda ident: calls.append(ident) or "job"))
    assert resume.execute("a" * 32) == "job" and calls == ["a" * 32]
    video.status = VideoStatus.APPROVED
    with pytest.raises(StateConflict):
        resume.execute("a" * 32)


def test_failed_step_can_be_retried_and_does_not_log_exception_text(conn, dsn, caplog):
    import logging
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.application.observability import run_step
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("c").id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    def fail():
        raise ValueError("sensitive exception text")
    with caplog.at_level(logging.INFO, logger="studio.steps"):
        with pytest.raises(ValueError):
            run_step(repo, video.id, "render", "c" * 64, fail)
        assert run_step(repo, video.id, "render", "c" * 64, lambda: None)
    assert "sensitive exception text" not in caplog.text
    assert '"attempt": 2' in caplog.text


@pytest.mark.parametrize("failure_point", ["attempt", "finish"])
def test_render_recovers_orphan_after_bookkeeping_failure(conn, dsn, monkeypatch, failure_point):
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.application.observability import run_step
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("c").id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    original = getattr(repo, failure_point)

    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(repo, failure_point, fail)
    if failure_point == "attempt":
        monkeypatch.setattr(repo, "finish", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        run_step(repo, video.id, "render", "a" * 64, lambda: None, reusable=False)
    monkeypatch.setattr(repo, failure_point, original)
    if failure_point == "attempt":
        monkeypatch.undo()
    assert run_step(repo, video.id, "render", "a" * 64, lambda: None, reusable=False)
    rows = conn.execute("SELECT status FROM studio.step_runs WHERE video_id=%s ORDER BY attempt", (video.id,)).fetchall()
    assert rows == [("FAILED",), ("SUCCEEDED",)]


@pytest.mark.parametrize("drop_lock_session", [False, True])
def test_live_render_step_is_not_reaped(conn, dsn, drop_lock_session):
    import threading
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.application.observability import run_step
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("c").id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    entered, release = threading.Event(), threading.Event()
    errors = []

    def operation():
        entered.set()
        assert release.wait(10)

    def worker():
        try:
            run_step(repo, video.id, "render", "a" * 64, operation, reusable=False)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(10)
        if drop_lock_session:
            pid = conn.execute(
                "SELECT pid FROM pg_locks WHERE locktype='advisory' AND granted "
                "AND classid = (hashtextextended(%s, 0) >> 32)::int::oid "
                "AND objid = (hashtextextended(%s, 0) & 4294967295)::oid",
                ("render-step:" + video.id, "render-step:" + video.id),
            ).fetchone()[0]
            assert conn.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
        with pytest.raises(RuntimeError):
            run_step(repo, video.id, "render", "b" * 64, lambda: None, reusable=False)
        assert conn.execute("SELECT status FROM studio.step_runs WHERE video_id=%s", (video.id,)).fetchone() == ("RUNNING",)
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not errors


def test_render_recovery_respects_another_session_lock(conn, dsn):
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.adapters.postgres.step_repo import PostgresStepRepository
    from app.studio.application.observability import run_step
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    video = videos.create_video(videos.create_project("c").id, "tema", VideoFormat.short)
    repo = PostgresStepRepository(connect)
    run_id = repo.begin(video.id, "render", "a" * 64, reusable=False)
    with connect() as other:
        other.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", ("render-step:" + video.id,))
        with pytest.raises(RuntimeError, match="already running"):
            run_step(repo, video.id, "render", "b" * 64, lambda: None, reusable=False)
        assert conn.execute("SELECT status FROM studio.step_runs WHERE id=%s", (run_id,)).fetchone() == ("RUNNING",)
