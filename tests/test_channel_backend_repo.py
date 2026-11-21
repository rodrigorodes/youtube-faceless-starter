"""Repositórios Postgres do backend de canais (F10-05/F10-06): banco descartável."""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.channel_budget_repo import (  # noqa: E402
    PostgresChannelBudgetRepository,
    PostgresChannelUsageRepository,
)
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.youtube_channel_repo import PostgresYouTubeChannelRepository  # noqa: E402
from app.studio.application.errors import ProjectNotFound  # noqa: E402
from app.studio.domain.channel_budget import BudgetLimitInvalid, BudgetLimits  # noqa: E402
from app.studio.domain.provider import EconomicProfile  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.youtube_channel import OAuthStatus, YouTubeChannel  # noqa: E402


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Budget", niche="Geral", language="pt-BR")
    return {"conn": conn, "dsn": dsn, "connect": connect, "videos": videos, "project_id": project.id}


def limits(project_id, **kw):
    base = dict(project_id=project_id, hard_monthly_usd=Decimal("20"), soft_monthly_usd=Decimal("10"),
                hard_video_usd=Decimal("4"), soft_video_usd=Decimal("2"))
    base.update(kw)
    return BudgetLimits(**base)


def test_budget_upsert_read_and_update(env):
    repo = PostgresChannelBudgetRepository(env["connect"])
    p_id = env["project_id"]
    assert repo.get(p_id) is None
    saved = repo.upsert(limits(p_id))
    assert saved.hard_monthly_usd == Decimal("20")
    assert saved.economic_profile is EconomicProfile.BALANCED
    assert repo.get(p_id).soft_video_usd == Decimal("2")
    updated = repo.upsert(limits(p_id, hard_monthly_usd=Decimal("30"), soft_monthly_usd=Decimal("25"),
                                 economic_profile=EconomicProfile.PREMIUM))
    assert updated.hard_monthly_usd == Decimal("30")
    assert repo.get(p_id).economic_profile is EconomicProfile.PREMIUM


def test_budget_invalid_limits_refused_before_writing(env):
    repo = PostgresChannelBudgetRepository(env["connect"])
    with pytest.raises(BudgetLimitInvalid):
        repo.upsert(limits(env["project_id"], soft_monthly_usd=Decimal("99")))
    assert repo.get(env["project_id"]) is None


def test_budget_project_missing_is_translated(env):
    repo = PostgresChannelBudgetRepository(env["connect"])
    with pytest.raises(ProjectNotFound):
        repo.upsert(limits("f" * 32))


def test_budget_db_check_rejects_soft_above_hard(env):
    conn = env["conn"]
    insert = ("INSERT INTO studio.channel_budgets(project_id, hard_monthly_usd, soft_monthly_usd, "
              "hard_video_usd, soft_video_usd) VALUES (%s, %s, %s, %s, %s)")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, (env["project_id"], 10, 11, 4, 2))
    conn.rollback()


def test_youtube_channel_upsert_get_delete(env):
    repo = PostgresYouTubeChannelRepository(env["connect"])
    p_id = env["project_id"]
    assert repo.get(p_id) is None
    channel = YouTubeChannel(project_id=p_id, channel_id="UC123", title="Canal",
                             scopes=("https://www.googleapis.com/auth/youtube.upload",),
                             oauth_status=OAuthStatus.CONNECTED)
    saved = repo.upsert(channel)
    assert saved.channel_id == "UC123"
    assert saved.scopes == ("https://www.googleapis.com/auth/youtube.upload",)
    assert repo.get(p_id).title == "Canal"
    assert repo.delete(p_id) is True
    assert repo.get(p_id) is None
    assert repo.delete(p_id) is False


def test_youtube_channel_project_missing_is_translated(env):
    repo = PostgresYouTubeChannelRepository(env["connect"])
    with pytest.raises(ProjectNotFound):
        repo.upsert(YouTubeChannel(project_id="f" * 32, channel_id="UC1", title="x"))


def test_usage_summary_only_counts_channel_videos(env):
    conn, p_id = env["conn"], env["project_id"]
    videos = env["videos"]
    other = videos.create_project("Outro Canal", language="pt-BR")
    v1 = videos.create_video(p_id, "tema um", VideoFormat.short)
    v2 = videos.create_video(other.id, "tema dois", VideoFormat.short)
    insert = ("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, "
              "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
              "cost_confirmed_by, cost_confirmed_at) "
              "VALUES (%s, 's', 'p', 'm', %s, %s, %s, 'ref', 'tester', now())")
    conn.execute(insert, (v1.id, 1.5, "ACTUAL", 1.5))
    conn.execute(insert, (v1.id, 0.2, "ESTIMATE", 0.2))
    conn.execute(insert, (v1.id, 0.0, "FREE", 0.0))
    conn.execute(insert, (v2.id, 9.0, "ACTUAL", 9.0))  # outro canal: não conta
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (NULL, 's', 'p', 'legacy', 3.0)")
    conn.commit()
    summary = PostgresChannelUsageRepository(env["connect"]).month_summary(p_id)
    assert summary.real_usd == Decimal("1.5")
    assert summary.estimate_usd == Decimal("0.2")
    assert summary.free_calls == 1
    assert summary.unknown_calls == 0
    assert summary.has_usage is True


def test_usage_summary_without_rows_is_empty(env):
    summary = PostgresChannelUsageRepository(env["connect"]).month_summary(env["project_id"])
    assert summary.has_usage is False
    assert summary.real_usd == Decimal("0")
    assert summary.labels()["real"] == "Sem registro de uso"
