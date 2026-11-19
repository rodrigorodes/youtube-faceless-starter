import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.contracts import VideoFormat, VideoStatus  # noqa: E402
from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.states import InvalidTransition  # noqa: E402


@pytest.fixture()
def repo(conn, dsn):
    migrate(conn)
    return PostgresVideoRepository(lambda: psycopg.connect(dsn))


@pytest.fixture()
def project(repo):
    return repo.create_project("canal", niche="música", language="pt-BR")


def db_status(conn, video_id):
    conn.commit()
    return conn.execute("SELECT status FROM studio.videos WHERE id=%s", (video_id,)).fetchone()[0]


def test_new_video_is_private_idea(repo, project):
    v = repo.create_video(project.id, "ADE 2026", VideoFormat.short)
    assert v.status == VideoStatus.IDEA and v.privacy == "private" and repo.get_video(v.id) == v


def test_project_roundtrip(repo):
    p = repo.create_project("canal", niche="x")
    got = repo.get_project(p.id)
    assert got.name == "canal" and got.niche == "x" and got.config == {} and got.budget_usd_month == 15.0


def test_unknown_ids(repo):
    assert repo.get_video("0" * 32) is None and repo.get_project("0" * 32) is None
    with pytest.raises(InvalidId):
        repo.get_video("../etc")


def test_transition_false_when_state_moved(repo, project, conn):
    v = repo.create_video(project.id, "ADE 2026", VideoFormat.short)
    assert repo.transition_video(v.id, VideoStatus.IDEA, VideoStatus.SCRIPTED) is True
    assert repo.transition_video(v.id, VideoStatus.IDEA, VideoStatus.SCRIPTED) is False
    assert db_status(conn, v.id) == "SCRIPTED"


def test_invalid_transition_raises_before_touching_db(repo, project, conn):
    v = repo.create_video(project.id, "ADE 2026", VideoFormat.short)
    with pytest.raises(InvalidTransition):
        repo.transition_video(v.id, VideoStatus.RENDERED, VideoStatus.APPROVED)
    assert db_status(conn, v.id) == "IDEA"


def test_transition_wins_once_under_concurrency(repo, project):
    for _ in range(20):  # repetido para não esconder corrida
        v = repo.create_video(project.id, "ADE 2026", VideoFormat.short)
        barrier, results = threading.Barrier(2), []

        def attempt():
            barrier.wait()
            results.append(repo.transition_video(v.id, VideoStatus.IDEA, VideoStatus.SCRIPTED))

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sorted(results) == [False, True]


def test_unknown_schema_version_in_db_is_rejected(repo, project, conn):
    v = repo.create_video(project.id, "ADE 2026", VideoFormat.short)
    conn.execute("UPDATE studio.videos SET qa_report = %s::jsonb WHERE id = %s", ('{"schema_version": 99, "passed": true}', v.id))
    conn.commit()
    with pytest.raises(ValueError):
        repo.get_video(v.id)
    conn.execute("UPDATE studio.videos SET qa_report = NULL, schema_version = 99 WHERE id = %s", (v.id,))
    conn.commit()
    with pytest.raises(ValueError):
        repo.get_video(v.id)


def test_dead_connection_becomes_service_unavailable(dsn):
    from app.studio.application.use_cases import ServiceUnavailable
    closed = psycopg.connect(dsn)
    closed.close()
    with pytest.raises(ServiceUnavailable):
        PostgresVideoRepository(lambda: closed).get_video("0" * 32)


def test_nul_byte_is_invalid_input(repo):
    from app.studio.application.use_cases import InvalidInput
    with pytest.raises(InvalidInput):
        repo.create_project("a\x00b")
