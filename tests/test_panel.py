import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.editorial import VideoNotFound
from app.studio.application.errors import InvalidInput
from app.studio.application.panel import BuildPanel, MonthCost, PanelView, TopicGroup, VideoDetailView, VideoItem
from app.studio.application.ports import PubInfo, StepInfo, UsageInfo, VideoDetail, VideoRow
from app.studio.domain.contracts import JobStatus, PublicationStatus, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage


class FakePanelRepo:
    def __init__(self, projects_list=None, videos_list=None, detail_map=None, month=(0.0, 0, 0), unattributed=None):
        self._projects = projects_list or [("p1", "Canal Principal")]
        self._videos = videos_list or []
        self._details = detail_map or {}
        self._month = month
        self._unattributed = unattributed or []

    def projects(self):
        return self._projects

    def videos(self, since, project_id, limit):
        res = self._videos
        if since:
            res = [v for v in res if v.updated_at >= since]
        if project_id:
            res = [v for v in res if v.project_id == project_id]
        return res[:limit]

    def video_detail(self, video_id):
        return self._details.get(video_id)

    def month_usage(self):
        return self._month

    def unattributed_usage(self):
        return self._unattributed


def _row(id, topic, status=VideoStatus.IDEA, job=None, step_running=False, pub=None, error=None, costs=None, updated_at=None):
    return VideoRow(
        id=id,
        project_id="p1",
        topic=topic,
        format=VideoFormat.short,
        status=status,
        title="",
        updated_at=updated_at or datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
        job_status=job,
        step_running=step_running,
        publication_status=pub,
        error=error,
        cost_rows=costs or [],
    )


def test_invalid_days_raises_invalid_input():
    panel = BuildPanel(FakePanelRepo(), 15.0, lambda: datetime(2026, 11, 20, tzinfo=timezone.utc))
    with pytest.raises(InvalidInput):
        panel.execute(days=5)
    with pytest.raises(InvalidInput):
        panel.execute(days=0)
    # Valid days
    assert panel.execute(days=7).days == 7
    assert panel.execute(days=14).days == 14
    assert panel.execute(days=30).days == 30


def test_groups_topics_by_normalized_key():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    v1 = _row("v1", "ADE Lineup!", VideoStatus.AWAITING_APPROVAL, updated_at=now)
    v2 = _row("v2", "  ade   lineup  ", VideoStatus.RENDERED, updated_at=now + timedelta(minutes=5))
    v3 = _row("v3", "Outro Tema", VideoStatus.IDEA, updated_at=now)

    repo = FakePanelRepo(videos_list=[v2, v1, v3])
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.execute(days=7)

    assert len(view.topics) == 2
    ade_group = next(t for t in view.topics if t.key == "ade lineup")
    assert len(ade_group.videos) == 2
    assert ade_group.counts[Stage.AWAITING_APPROVAL] == 2
    assert ade_group.label == "ade lineup"


def test_totals_counts_by_stage():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    v1 = _row("v1", "T1", VideoStatus.AWAITING_APPROVAL)
    v2 = _row("v2", "T2", VideoStatus.PUBLISHED, pub=PublicationStatus.UPLOADED)
    v3 = _row("v3", "T3", VideoStatus.FAILED)

    repo = FakePanelRepo(videos_list=[v1, v2, v3])
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.execute(days=7)

    assert view.totals[Stage.AWAITING_APPROVAL] == 1
    assert view.totals[Stage.COMPLETED] == 1
    assert view.totals[Stage.FAILED] == 1
    assert view.totals[Stage.IN_PRODUCTION] == 0


def test_month_cost_percentage_and_unknowns():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    # known 3.0, 5 calls, 1 unknown
    repo = FakePanelRepo(month=(3.0, 5, 1))
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.execute(days=7)

    assert view.month.known_usd == 3.0
    assert view.month.cap_usd == 15.0
    assert view.month.percent == pytest.approx(20.0)
    assert "1 chamada sem custo informado" in view.month.text
    assert "US$ 0,00 (gratuito)" not in view.month.text


def test_actions_per_stage():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    v_awaiting = _row("v1", "T1", VideoStatus.AWAITING_APPROVAL)
    v_prod = _row("v2", "T2", VideoStatus.SCRIPTED, step_running=True)

    repo = FakePanelRepo(videos_list=[v_awaiting, v_prod])
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.execute(days=7)

    item1 = next(item for t in view.topics for item in t.videos if item.id == "v1")
    assert "preview" in item1.actions
    assert "progress" in item1.actions

    item2 = next(item for t in view.topics for item in t.videos if item.id == "v2")
    assert "progress" in item2.actions
    assert "preview" not in item2.actions


def test_detail_raises_video_not_found():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    repo = FakePanelRepo(detail_map={})
    panel = BuildPanel(repo, 15.0, lambda: now)
    with pytest.raises(VideoNotFound):
        panel.detail("nonexistent")


def test_detail_returns_view_when_found():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    row = _row("v1", "Tema 1", VideoStatus.AWAITING_APPROVAL)
    detail = VideoDetail(
        video=row,
        steps=[StepInfo("script", 1, "SUCCEEDED", None, None, now, now)],
        usage=[UsageInfo("text", "opencode", "gpt:free", 0.0, now)],
        render_error=None,
        publication=None,
    )
    repo = FakePanelRepo(detail_map={"v1": detail})
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.detail("v1")
    assert view.video.id == "v1"
    assert view.stage == Stage.AWAITING_APPROVAL
    assert view.cost_text == "US$ 0,00 (gratuito)"
    assert len(view.steps) == 1
