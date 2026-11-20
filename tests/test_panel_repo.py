import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.panel_repo import (  # noqa: E402
    PanelRepository,
    PostgresPanelRepository,
    PubInfo,
    StepInfo,
    UsageInfo,
    VideoDetail,
    VideoRow,
)
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.contracts import JobStatus, PublicationStatus, VideoFormat, VideoStatus  # noqa: E402


@pytest.fixture()
def repo_env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    repo = PostgresPanelRepository(connect)
    project = videos.create_project("Canal Principal", niche="Musica", language="pt-BR")
    return {"repo": repo, "videos": videos, "project_id": project.id, "conn": conn, "connect": connect}


def test_projects_lists_all_projects(repo_env):
    repo = repo_env["repo"]
    projects = repo.projects()
    assert len(projects) == 1
    assert projects[0] == (repo_env["project_id"], "Canal Principal")


def test_videos_aggregation_and_filters(repo_env):
    repo = repo_env["repo"]
    videos = repo_env["videos"]
    conn = repo_env["conn"]
    p_id = repo_env["project_id"]

    v1 = videos.create_video(p_id, "Tema Um", VideoFormat.short)
    v2 = videos.create_video(p_id, "Tema Dois", VideoFormat.short)

    # v1 has two render jobs: first failed, second running
    conn.execute(
        "INSERT INTO studio.render_jobs (id, video_id, status, attempt, input_hash) "
        "VALUES (%s, %s, 'FAILED', 1, 'h1'), (%s, %s, 'RUNNING', 2, 'h2')",
        (uuid.uuid4().hex, v1.id, uuid.uuid4().hex, v1.id),
    )
    # v1 has usage entries
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'opencode', 'gpt:free', 0.0), (%s, 'image', 'opencode', 'veo', 0.40)",
        (v1.id, v1.id),
    )

    # v2 has running step
    conn.execute(
        "INSERT INTO studio.step_runs (id, video_id, step, attempt, status, input_hash) "
        "VALUES (%s, %s, 'storyboard', 1, 'RUNNING', 'hash_sb')",
        (uuid.uuid4().hex, v2.id),
    )

    conn.commit()

    rows = repo.videos(since=None, project_id=p_id, limit=10)
    assert len(rows) == 2
    row_v1 = next(r for r in rows if r.id == v1.id)
    assert row_v1.job_status == JobStatus.RUNNING
    assert row_v1.step_running is False
    assert len(row_v1.cost_rows) == 2

    row_v2 = next(r for r in rows if r.id == v2.id)
    assert row_v2.step_running is True
    assert row_v2.job_status is None


def test_video_detail_never_includes_upload_uri(repo_env):
    repo = repo_env["repo"]
    videos = repo_env["videos"]
    conn = repo_env["conn"]
    p_id = repo_env["project_id"]

    v = videos.create_video(p_id, "Tema Com Publicacao", VideoFormat.short)
    secret_uri = "https://youtube.googleapis.com/upload/SECRET_URI_XYZ"

    conn.execute(
        "INSERT INTO studio.publications (id, video_id, status, attempt, upload_uri, error) "
        "VALUES (%s, %s, 'FAILED', 2, %s, 'Falha de rede')",
        (uuid.uuid4().hex, v.id, secret_uri),
    )
    conn.commit()

    detail = repo.video_detail(v.id)
    assert detail is not None
    assert detail.publication is not None
    assert detail.publication.status == PublicationStatus.FAILED
    assert detail.publication.attempt == 2
    assert not hasattr(detail.publication, "upload_uri")
    assert secret_uri not in repr(detail)


def test_month_usage_and_unattributed_usage(repo_env):
    repo = repo_env["repo"]
    videos = repo_env["videos"]
    conn = repo_env["conn"]
    p_id = repo_env["project_id"]

    v = videos.create_video(p_id, "Tema Uso", VideoFormat.short)

    # 1. known free (cost 0.0, model ends with :free) -> known
    # 2. known paid (cost 0.50) -> known
    # 3. unknown (cost 0.0, paid model) -> unknown
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (%s, 'text', 'opencode', 'gpt:free', 0.0), "
        "(%s, 'image', 'veo', 'veo-model', 0.50), "
        "(%s, 'text', 'opencode', 'gpt-4o-paid', 0.0)",
        (v.id, v.id, v.id),
    )
    # Unattributed call (video_id is NULL)
    conn.execute(
        "INSERT INTO studio.usage_ledger (video_id, step, provider, model, cost_usd) "
        "VALUES (NULL, 'editorial', 'opencode', 'gpt-4o-paid', 0.0)"
    )
    conn.commit()

    known_usd, calls, unknown_calls = repo.month_usage()
    assert known_usd == pytest.approx(0.50)
    assert calls == 4
    assert unknown_calls == 2

    unattributed = repo.unattributed_usage()
    assert len(unattributed) == 1
    assert unattributed[0] == ("opencode", "gpt-4o-paid", 0.0)
