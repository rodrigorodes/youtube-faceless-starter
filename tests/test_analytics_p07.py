import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))


@pytest.fixture
def analytics(conn, dsn):
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.analytics_repo import PostgresAnalyticsRepository
    from app.studio.adapters.postgres.repo import PostgresVideoRepository
    from app.studio.domain.contracts import VideoFormat

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal")
    video = videos.create_video(project.id, "tema", VideoFormat.short)
    return PostgresAnalyticsRepository(connect), video.id


def test_daily_upsert_and_aggregate_report_preserve_missing_values(analytics):
    from app.studio.application.analytics import DailyMetric

    repo, video = analytics
    day = date(2026, 11, 10)
    repo.upsert(DailyMetric(video_id=video, date=day, views=4, likes=None))
    repo.upsert(DailyMetric(video_id=video, date=day, views=9, likes=None))
    repo.upsert(DailyMetric(video_id=video, date=date(2026, 11, 11), views=3, likes=1))
    report = repo.weekly(date(2026, 11, 9), date(2026, 11, 15))
    assert len(report) == 1
    assert report[0]["views"] == 12 and report[0]["likes"] == 1
    assert report[0]["days"] == [day, date(2026, 11, 11)]
    assert report[0]["sample_small"] is True
    assert report[0]["suggestion"] is None


def test_invalid_metrics_are_rejected():
    from app.studio.application.analytics import DailyMetric

    with pytest.raises(ValueError):
        DailyMetric(video_id="a" * 32, date=date(2026, 11, 10), views=-1)
    with pytest.raises(ValueError):
        DailyMetric(video_id="a" * 32, date=date(2026, 11, 10), average_view_duration_s=float("nan"))


def test_sufficient_sample_produces_exploratory_suggestion_with_provenance(analytics):
    from app.studio.application.analytics import DailyMetric

    repo, video = analytics
    day = date(2026, 11, 10)
    repo.upsert(DailyMetric(video_id=video, date=day, views=120))
    row = repo.weekly(day, day)[0]
    assert row["sample_small"] is False
    assert row["suggestion"]["topic"] == "tema"
    assert row["suggestion"]["evidence"] == [{"video_id": video, "date": day}]


def test_unknown_view_counts_prevent_suggestion(analytics):
    from app.studio.application.analytics import DailyMetric

    repo, video = analytics
    first, second = date(2026, 11, 10), date(2026, 11, 11)
    repo.upsert(DailyMetric(video_id=video, date=first, views=120))
    repo.upsert(DailyMetric(video_id=video, date=second, views=None))
    row = repo.weekly(first, second)[0]
    assert row["suggestion"] is None


def test_missing_day_in_week_prevents_suggestion(analytics):
    from app.studio.application.analytics import DailyMetric

    repo, video = analytics
    first, last = date(2026, 11, 10), date(2026, 11, 16)
    repo.upsert(DailyMetric(video_id=video, date=first, views=120))
    row = repo.weekly(first, last)[0]
    assert row["views_complete"] is False
    assert row["suggestion"] is None


def test_composition_exposes_analytics_and_resume(conn, dsn, tmp_path):
    from app.studio.composition import Settings, Studio

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    try:
        use_cases = studio.use_cases()
        assert use_cases is not None
        assert callable(use_cases.analytics.upsert)
        assert callable(use_cases.analytics.weekly)
        assert callable(use_cases.resume.execute)
    finally:
        studio.shutdown()


def test_analytics_to_editorial_uses_real_metrics_and_blocks_incomplete_sample(analytics):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.studio.api.routes import make_router
    from app.studio.application.analytics import Analytics, DailyMetric
    from app.studio.application.editorial import CostGuard
    from app.studio.application.ideas import ScoreIdeas
    from test_ideas import Text, Usage, item

    repo, video = analytics
    first, second = date(2026, 11, 10), date(2026, 11, 11)
    repo.upsert(DailyMetric(video_id=video, date=first, views=120))
    text, usage = Text({"ideas": [item("tema", 4, 4, 4, 4)]}), Usage()
    scorer = ScoreIdeas(text, CostGuard(usage, 0.0, 15.0), usage)
    uc = SimpleNamespace(analytics=Analytics(repo), editorial=SimpleNamespace(score_ideas=scorer),
                         get_video=SimpleNamespace(execute=lambda _: SimpleNamespace(project_id="b" * 32)))
    app = FastAPI()
    app.include_router(make_router(lambda: uc, lambda: True))
    client = TestClient(app)
    body = {"video_id": video, "start": str(first), "end": str(second)}
    headers = {"Authorization": "Bearer test-worker-token"}
    assert client.post("/studio/ideas/from-analytics", json=body, headers=headers).json() == {"ranked": []}
    assert text.calls == 0
    repo.upsert(DailyMetric(video_id=video, date=second, views=1))
    result = client.post("/studio/ideas/from-analytics", json=body, headers=headers).json()["ranked"]
    assert result[0]["topic"] == "tema"
    assert result[0]["evidence"] == [{"video_id": video, "date": str(first)}, {"video_id": video, "date": str(second)}]
    assert text.calls == 1
