import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.trend_repo import PostgresTrendRepository  # noqa: E402
from app.studio.domain.trend_priority import SavedTrendSnapshot  # noqa: E402
from app.studio.domain.trends import Evidence, TrendItem  # noqa: E402


@pytest.fixture()
def trend_env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    repo = PostgresTrendRepository(connect)
    project = videos.create_project("Canal Trends", niche="Musica", language="pt-BR")
    return {"repo": repo, "project_id": project.id, "conn": conn, "connect": connect}


@pytest.fixture()
def repo(request):
    dsn = os.environ.get("STUDIO_TEST_DSN")
    if dsn and os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        try:
            env = request.getfixturevalue("trend_env")
            return env["repo"]
        except Exception:
            pass

    sqlite_conn = sqlite3.connect(":memory:")
    sqlite_conn.execute("ATTACH DATABASE ':memory:' AS studio")
    sqlite_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS studio.saved_trends (
            project_id text NOT NULL,
            video_id text NOT NULL,
            title text NOT NULL,
            channel_title text,
            thumbnail_url text,
            video_url text,
            duration text NOT NULL DEFAULT '',
            views bigint NOT NULL DEFAULT 0,
            category_name text,
            score int NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, video_id)
        )
        """
    )
    return PostgresTrendRepository(lambda: sqlite_conn)


def _item(topic="ADE Lineup 2026", metric_val=1000.0, offset_hours=0, window_end=None):
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc) + timedelta(hours=offset_hours)
    w_end = window_end or now
    return TrendItem(
        topic=topic,
        source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search",
        observed_at=now,
        window_start=w_end - timedelta(days=7),
        window_end=w_end,
        metric_name="views",
        metric_value=metric_val,
        evidence=[Evidence(title="Video 1", url="https://youtube.com/watch?v=abc", views=int(metric_val))],
    )


def test_trend_repo_upsert_is_idempotent_and_updates_observation(trend_env):
    repo = trend_env["repo"]
    p_id = trend_env["project_id"]
    fixed_window = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)

    item1 = _item("ADE Lineup", 1000.0, window_end=fixed_window)
    stored = repo.upsert(p_id, [item1])
    assert stored == 1

    # Second upsert for same window with updated views and observation time
    item1_updated = _item("ADE Lineup", 2500.0, offset_hours=1, window_end=fixed_window)
    stored2 = repo.upsert(p_id, [item1_updated])
    assert stored2 == 1

    since = datetime(2026, 11, 1, tzinfo=timezone.utc)
    records = repo.list(p_id, since=since)
    assert len(records) == 1
    assert records[0].metric_value == pytest.approx(2500.0)
    assert records[0].topic_key == "ade lineup"


def test_trend_repo_list_filters_by_since(trend_env):
    repo = trend_env["repo"]
    p_id = trend_env["project_id"]

    item = _item("Tema Antigo", 500.0, offset_hours=-48)
    repo.upsert(p_id, [item])

    since_recent = datetime(2026, 11, 20, tzinfo=timezone.utc)
    assert len(repo.list(p_id, since=since_recent)) == 0

    since_old = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert len(repo.list(p_id, since=since_old)) == 1


def test_trend_repo_last_collected_at(trend_env):
    repo = trend_env["repo"]
    p_id = trend_env["project_id"]

    assert repo.last_collected_at(p_id) is None

    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    repo.upsert(p_id, [_item("Tema Um", 100.0)])
    assert repo.last_collected_at(p_id) == now


def test_saved_trends_lifecycle(repo):
    p_id = "project-123"
    snap = SavedTrendSnapshot(
        project_id=p_id,
        video_id="vid_test_99",
        title="Ideia Salva no Canal",
        channel_title="Canal X",
        thumbnail_url="https://i.ytimg.com/vi/vid_test_99/hqdefault.jpg",
        video_url="https://youtube.com/watch?v=vid_test_99",
        duration="11:40",
        views=1_400_000,
        category_name="Mistérios",
        score=86,
    )
    repo.save_trend_snapshot(p_id, snap)
    assert repo.is_trend_saved(p_id, "vid_test_99") is True
    saved = repo.list_saved_trends(p_id)
    assert len(saved) == 1
    assert saved[0].title == "Ideia Salva no Canal"

    repo.unsave_trend(p_id, "vid_test_99")
    assert repo.is_trend_saved(p_id, "vid_test_99") is False
    assert len(repo.list_saved_trends(p_id)) == 0


def test_saved_trends_upsert_and_project_isolation(repo):
    p1 = "project-111"
    p2 = "project-222"
    now1 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
    now2 = datetime(2026, 11, 23, 11, 0, tzinfo=timezone.utc)

    snap1 = SavedTrendSnapshot(
        project_id=p1,
        video_id="vid_1",
        title="Ideia 1",
        views=1000,
        score=50,
        created_at=now1,
    )
    snap2 = SavedTrendSnapshot(
        project_id=p1,
        video_id="vid_2",
        title="Ideia 2",
        views=2000,
        score=80,
        created_at=now2,
    )
    snap_p2 = SavedTrendSnapshot(
        project_id=p2,
        video_id="vid_p2",
        title="Ideia Canal 2",
        views=5000,
        score=90,
    )

    repo.save_trend_snapshot(p1, snap1)
    repo.save_trend_snapshot(p1, snap2)
    repo.save_trend_snapshot(p2, snap_p2)

    # Project isolation
    p1_trends = repo.list_saved_trends(p1)
    assert len(p1_trends) == 2
    # Sorted by created_at DESC (snap2 was at 11:00, snap1 at 10:00)
    assert p1_trends[0].video_id == "vid_2"
    assert p1_trends[1].video_id == "vid_1"

    p2_trends = repo.list_saved_trends(p2)
    assert len(p2_trends) == 1
    assert p2_trends[0].video_id == "vid_p2"

    # Upsert (update existing snapshot)
    snap1_updated = SavedTrendSnapshot(
        project_id=p1,
        video_id="vid_1",
        title="Ideia 1 Atualizada",
        views=1500,
        score=65,
    )
    repo.save_trend_snapshot(p1, snap1_updated)
    p1_trends_after = repo.list_saved_trends(p1)
    assert len(p1_trends_after) == 2
    updated_snap1 = next(s for s in p1_trends_after if s.video_id == "vid_1")
    assert updated_snap1.title == "Ideia 1 Atualizada"
    assert updated_snap1.views == 1500
    assert updated_snap1.score == 65

    # Unsaving non-existent is no-op
    repo.unsave_trend(p1, "non_existent_vid")
    assert len(repo.list_saved_trends(p1)) == 2


