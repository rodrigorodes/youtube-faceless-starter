import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

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


class FakeTrendRepo:
    def __init__(self, records=None, last_collected=None):
        self._records = records or []
        self._last_collected = last_collected

    def list(self, project_id, since):
        return [r for r in self._records if r.window_end >= since]

    def last_collected_at(self, project_id):
        return self._last_collected


def test_panel_trends_never_collected():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    repo = FakePanelRepo()
    trends = FakeTrendRepo(last_collected=None)
    panel = BuildPanel(repo, 15.0, lambda: now, trends=trends)
    view = panel.execute(days=7)
    assert view.trends_status == "never_collected"
    assert view.trends == []


def test_panel_joins_trends_with_existing_videos_by_topic_key():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    from app.studio.application.ports import TrendRecord

    t_rec = TrendRecord(
        id="t1",
        project_id="p1",
        topic="ADE Lineup 2026",
        topic_key="ade lineup 2026",
        source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search",
        observed_at=now,
        window_start=now - timedelta(days=7),
        window_end=now,
        metric_name="views",
        metric_value=1200000.0,
        evidence=[],
    )
    v1 = _row("v1", "ade  lineup 2026!", VideoStatus.AWAITING_APPROVAL, updated_at=now)

    repo = FakePanelRepo(videos_list=[v1])
    trends = FakeTrendRepo(records=[t_rec], last_collected=now)
    panel = BuildPanel(repo, 15.0, lambda: now, trends=trends)
    view = panel.execute(days=7)

    assert view.trends_status == "ok"
    assert len(view.trends) == 1
    t_view = view.trends[0]
    assert t_view.topic == "ADE Lineup 2026"
    assert t_view.counts[Stage.AWAITING_APPROVAL] == 1
    assert t_view.stale is False


def test_panel_matches_trend_category_and_exposes_categories():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    from app.studio.application.ports import TrendRecord
    from app.studio.domain.categories import ProjectCategory

    c_id = uuid.uuid4().hex
    p_id = uuid.uuid4().hex

    cat = ProjectCategory(
        id=c_id,
        project_id=p_id,
        name="Música Eletrônica",
        queries=["ADE", "Tomorrowland"],
    )

    class FakeCatRepo:
        def list(self, project_id: str):
            return [cat]

    t_rec = TrendRecord(
        id="t1",
        project_id=p_id,
        topic="ADE Lineup 2026 Revelado",
        topic_key="ade lineup 2026 revelado",
        source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search",
        observed_at=now,
        window_start=now - timedelta(days=7),
        window_end=now,
        metric_name="views",
        metric_value=500000.0,
        evidence=[],
    )

    repo = FakePanelRepo(projects_list=[(p_id, "Canal Eletrônico")])
    trends = FakeTrendRepo(records=[t_rec], last_collected=now)
    panel = BuildPanel(repo, 15.0, lambda: now, trends=trends, categories_repo=FakeCatRepo())
    view = panel.execute(days=7)

    assert len(view.categories) == 1
    assert view.categories[0].name == "Música Eletrônica"
    assert len(view.trends) == 1
    assert view.trends[0].category_id == cat.id
    assert view.trends[0].category_name == "Música Eletrônica"


def test_build_panel_extracts_video_metadata_and_region():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    from app.studio.application.ports import TrendRecord

    t_br = TrendRecord(
        id="t_br",
        project_id="p1",
        topic="Video Viral BR",
        topic_key="video viral br",
        source_name="YouTube Brasil (Em Alta)",
        source_url="https://www.youtube.com/feed/trending",
        observed_at=now,
        window_start=now - timedelta(days=7),
        window_end=now,
        metric_name="views",
        metric_value=1200000.0,
        evidence=[
            {
                "title": "Clipe Viral BR",
                "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                "channel": "Canal Brasil",
                "views": 1200000,
                "published_at": "2026-11-19T14:30:00Z",
            }
        ],
    )
    t_global = TrendRecord(
        id="t_global",
        project_id="p1",
        topic="Global Hit Video",
        topic_key="global hit video",
        source_name="YouTube Global (Em Alta)",
        source_url="https://www.youtube.com/feed/trending",
        observed_at=now,
        window_start=now - timedelta(days=7),
        window_end=now,
        metric_name="views",
        metric_value=5000000.0,
        evidence=[
            {
                "title": "Global Hit",
                "url": "https://youtu.be/9bZkp7q19f0",
                "channel": "Worldwide Music",
                "views": 5000000,
                "published_at": datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc),
            }
        ],
    )
    t_pillar = TrendRecord(
        id="t_pillar",
        project_id="p1",
        topic="Pillar Tech Topic",
        topic_key="pillar tech topic",
        source_name="YouTube Data API",
        source_url="https://www.googleapis.com/youtube/v3/search",
        observed_at=now,
        window_start=now - timedelta(days=7),
        window_end=now,
        metric_name="views",
        metric_value=300000.0,
        evidence=[],
    )

    repo = FakePanelRepo()
    trends = FakeTrendRepo(records=[t_br, t_global, t_pillar], last_collected=now)
    panel = BuildPanel(repo, 15.0, lambda: now, trends=trends)
    view = panel.execute(days=7)

    assert len(view.trends) == 3

    # BR popular trend
    br_view = next(t for t in view.trends if t.topic == "Video Viral BR")
    assert br_view.region == "BR"
    assert br_view.video_id == "dQw4w9WgXcQ"
    assert br_view.thumbnail_url == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert br_view.video_url == "https://youtube.com/watch?v=dQw4w9WgXcQ"
    assert br_view.channel_title == "Canal Brasil"
    assert br_view.published_text == "19/11/2026"

    # The legacy label does not identify a specific region or a global aggregate.
    global_view = next(t for t in view.trends if t.topic == "Global Hit Video")
    assert global_view.region == "UNKNOWN"
    assert global_view.video_id == "9bZkp7q19f0"
    assert global_view.thumbnail_url == "https://i.ytimg.com/vi/9bZkp7q19f0/hqdefault.jpg"
    assert global_view.video_url == "https://youtu.be/9bZkp7q19f0"
    assert global_view.channel_title == "Worldwide Music"
    assert global_view.published_text == "18/11/2026"

    # Pillar trend (no region, no evidence)
    pillar_view = next(t for t in view.trends if t.topic == "Pillar Tech Topic")
    assert pillar_view.region is None
    assert pillar_view.video_id is None
    assert pillar_view.thumbnail_url is None
    assert pillar_view.video_url is None
    assert pillar_view.channel_title is None
    assert pillar_view.published_text is None


@pytest.mark.parametrize(
    ("code", "expected_region", "label"),
    [("BR", "BR", "🇧🇷 Em Alta Brasil"), ("US", "US", "🇺🇸 Em Alta EUA"),
     ("JP", "JP", "Em Alta JP")],
)
def test_popular_region_flows_from_adapter_to_panel_and_page(monkeypatch, code, expected_region, label):
    from app.studio.adapters.youtube_trends import fetch_popular_trends
    from app.studio.api.panel import render_panel
    from app.studio.application.ports import TrendRecord

    response = MagicMock()
    response.read.return_value = json.dumps({
        "items": [{"id": "v123", "snippet": {"title": "Popular Video"}, "statistics": {}}]
    }).encode()
    response.__enter__.return_value = response
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    item = fetch_popular_trends("key", code)[0]
    record = TrendRecord(
        id="t1", project_id="p1", topic=item.topic, topic_key=item.topic.lower(),
        source_name=item.source_name, source_url=item.source_url,
        observed_at=item.observed_at, window_start=item.window_start, window_end=item.window_end,
        metric_name=item.metric_name, metric_value=item.metric_value,
        evidence=[ev.model_dump(mode="json") for ev in item.evidence],
    )
    panel = BuildPanel(FakePanelRepo(), 15.0, lambda: item.observed_at,
                       trends=FakeTrendRepo([record], item.observed_at))
    view = panel.execute(days=7)
    assert view.trends[0].region == expected_region
    assert f"regionCode={code}" in urlopen.call_args[0][0].full_url
    html, _ = render_panel(view)
    assert f'data-region-code="{expected_region}"' in html
    assert f'data-region="{expected_region}"' in html
    assert f"{label} (1)" in html
    assert f">{label}</span>" in html
    assert "Em Alta Mundo" not in html


def test_legacy_global_label_is_displayed_as_unknown_not_global():
    from app.studio.api.panel import render_panel
    from app.studio.application.ports import TrendRecord

    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    record = TrendRecord(
        id="old", project_id="p1", topic="Legacy Video", topic_key="legacy video",
        source_name="YouTube Global (Em Alta)", source_url="https://www.youtube.com/feed/trending",
        observed_at=now, window_start=now - timedelta(days=7), window_end=now,
        metric_name="views", metric_value=1, evidence=[],
    )
    view = BuildPanel(FakePanelRepo(), 15.0, lambda: now,
                      trends=FakeTrendRepo([record], now)).execute(days=7)
    assert view.trends[0].region == "UNKNOWN"
    html, _ = render_panel(view)
    assert 'data-region-code="UNKNOWN"' in html
    assert 'data-region="UNKNOWN"' in html
    assert "Origem desconhecida (1)" in html
    assert "Origem desconhecida</span>" in html
    assert "YouTube Global (Em Alta)" not in html
    assert "Em Alta Mundo" not in html


def test_region_filter_shows_matching_items_beyond_initial_six():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js necessário para exercitar o filtro JavaScript")
    from app.studio.api.panel import render_panel

    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    html, _ = render_panel(BuildPanel(FakePanelRepo(), 15.0, lambda: now).execute(days=7))
    script = html.split("// Pill Filtering (Region, Category & All) & Compact Trends Expansion", 1)[1]
    script = script.split("// Modal Open & Close", 1)[0]
    setup = """
const assert = require('node:assert/strict');
function element(attrs, classes = []) {
  const c = new Set(classes);
  return {
    attrs, style: {}, classList: {
      add: (x) => c.add(x), remove: (x) => c.delete(x), contains: (x) => c.has(x)
    },
    getAttribute: function(k) { return this.attrs[k] || null; },
    setAttribute: function(k, v) { this.attrs[k] = v; },
    addEventListener: function(_, callback) { this.click = callback; }
  };
}
const all = element({'data-filter-type': 'all'}, ['cat-pill', 'active']);
const jp = element({'data-filter-type': 'region', 'data-region-code': 'JP'}, ['cat-pill']);
const pills = [all, jp];
const items = Array.from({length: 7}, (_, i) =>
  element({'data-region': i === 6 ? 'JP' : 'BR'}, i === 6 ? ['trend-item-extra'] : []));
const toggle = element({'data-expanded': 'false', 'data-total': '7'});
const document = {
  querySelectorAll: (selector) => selector.startsWith('.cat-pill') ? pills : items,
  querySelector: () => pills.find((p) => p.classList.contains('active')),
  getElementById: (id) => id === 'btn-toggle-more-trends' ? toggle : null
};
"""
    checks = """
jp.click();
assert.equal(items[6].style.display, '');
assert.ok(items.slice(0, 6).every((item) => item.style.display === 'none'));
assert.equal(jp.attrs['aria-pressed'], 'true');
assert.equal(all.attrs['aria-pressed'], 'false');
all.click();
assert.equal(items[6].style.display, 'none');
"""
    result = subprocess.run([node, "-e", setup + script + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
