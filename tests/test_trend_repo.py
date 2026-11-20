import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.trend_repo import PostgresTrendRepository  # noqa: E402
from app.studio.domain.trends import Evidence, TrendItem  # noqa: E402


@pytest.fixture()
def trend_env(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    repo = PostgresTrendRepository(connect)
    project = videos.create_project("Canal Trends", niche="Musica", language="pt-BR")
    return {"repo": repo, "project_id": project.id, "conn": conn, "connect": connect}


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
