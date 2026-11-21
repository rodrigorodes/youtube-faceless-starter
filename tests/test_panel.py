import json
import re
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
from app.studio.application.ports import LatestRun, PubInfo, SourceInfo, StepInfo, UsageInfo, VideoDetail, VideoRow
from app.studio.domain.contracts import JobStatus, PublicationStatus, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage


class FakePanelRepo:
    def __init__(self, projects_list=None, videos_list=None, detail_map=None, month_rows=None, unattributed=None):
        self._projects = projects_list or [("p1", "Canal Principal")]
        self._videos = videos_list or []
        self._details = detail_map or {}
        self._month_rows = month_rows or []
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
        return self._month_rows

    def unattributed_usage(self):
        return self._unattributed


def _norm_costs(costs):
    out = []
    for row in costs or []:
        provider, model, cost_usd, *rest = row
        out.append((provider, model, float(cost_usd), rest[0] if rest else None))
    return out


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
        cost_rows=_norm_costs(costs),
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


def test_month_cost_matches_execute_month_and_never_zero_for_absence():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    empty = BuildPanel(FakePanelRepo(month_rows=[]), 15.0, lambda: now)
    assert empty.month_cost() == empty.execute(days=7).month
    assert empty.month_cost().text == "sem registro de uso"

    paid = FakePanelRepo(month_rows=[("opencode", "gpt-5-mini", 0.07, "ACTUAL")])
    panel = BuildPanel(paid, 15.0, lambda: now)
    assert panel.month_cost() == panel.execute(days=7).month
    assert panel.month_cost().breakdown.real_calls == 1


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
    # 3.0 estimado (legado positivo sem confirmação) + 1 chamada desconhecida
    rows = [("opencode", "gpt-est", 3.0, None), ("opencode", "gpt-4o-paid", 0.0, None)]
    repo = FakePanelRepo(month_rows=rows)
    panel = BuildPanel(repo, 15.0, lambda: now)
    view = panel.execute(days=7)

    assert view.month.known_usd == 3.0
    assert view.month.cap_usd == 15.0
    assert view.month.percent == pytest.approx(20.0)
    assert view.month.unknown_calls == 1
    assert "Estimado US$ 3,00" in view.month.text
    assert "Desconhecido" in view.month.text
    assert "US$ 0,00" not in view.month.text


def test_month_cost_labels_real_estimate_free_and_unknown_without_single_number():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    rows = [
        ("opencode", "gpt-paid", 0.07, "ACTUAL"),
        ("opencode", "gpt-est", 0.05, "ESTIMATE"),
        ("piper", "piper", 0.0, "FREE"),
        ("opencode", "gpt:free", 0.0, None),
        ("opencode", "gpt-4o-paid", 0.0, None),
    ]
    view = BuildPanel(FakePanelRepo(month_rows=rows), 15.0, lambda: now).execute(days=7)

    assert "Real US$ 0,07" in view.month.text
    assert "Estimado US$ 0,05" in view.month.text
    assert "Sem custo" in view.month.text
    assert "Desconhecido" in view.month.text
    assert "US$ 0,12" not in view.month.text  # nunca funde real e estimado num único número
    assert "US$ 0,00" not in view.month.text  # gratuidade/desconhecido nunca viram zero
    assert view.month.breakdown.real_usd == pytest.approx(0.07)
    assert view.month.breakdown.estimate_usd == pytest.approx(0.05)
    assert view.month.breakdown.free_calls == 2
    assert view.month.breakdown.unknown_calls == 1


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
    assert view.cost_text == "Sem custo"
    assert len(view.steps) == 1


class FakeTrendRepo:
    def __init__(self, records=None, last_collected=None):
        self._records = records or []
        self._last_collected = last_collected

    def list(self, project_id, since):
        return [r for r in self._records if r.window_end >= since]

    def last_collected_at(self, project_id):
        return self._last_collected

    def find_by_topic_key(self, project_id, topic_key):
        for r in self._records:
            if r.project_id == project_id and r.topic_key == topic_key:
                return r
        return None


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
    # IA-01: as tendências passaram a viver na tela Tendências (/studio/panel/tendencias).
    from app.studio.api.panel import render_tendencias
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
    html, _ = render_tendencias(view)
    assert f'data-region-code="{expected_region}"' in html
    assert f'data-region="{expected_region}"' in html
    assert f"{label} (1)" in html
    assert f">{label}</span>" in html
    assert "Em Alta Mundo" not in html


def test_legacy_global_label_is_displayed_as_unknown_not_global():
    # IA-01: as tendências passaram a viver na tela Tendências (/studio/panel/tendencias).
    from app.studio.api.panel import render_tendencias
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
    html, _ = render_tendencias(view)
    assert 'data-region-code="UNKNOWN"' in html
    assert 'data-region="UNKNOWN"' in html
    assert "Origem desconhecida (1)" in html
    assert "Origem desconhecida</span>" in html
    assert "YouTube Global (Em Alta)" not in html
    assert "Em Alta Mundo" not in html


def test_panel_header_lists_distinct_sources_for_mixed_trends():
    # IA-01: o cabeçalho de fontes pertence à tela Tendências (/studio/panel/tendencias).
    from app.studio.api.panel import render_tendencias
    from app.studio.application.ports import TrendRecord

    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    sources = [
        ("YouTube Brasil (Em Alta)", "https://www.youtube.com/feed/trending"),
        ("YouTube EUA (Em Alta)", "https://www.youtube.com/feed/trending"),
        ("YouTube Global (Em Alta)", "https://www.youtube.com/feed/trending"),
        ("YouTube Data API", "https://www.googleapis.com/youtube/v3/search"),
        ("YouTube Brasil (Em Alta)", "https://www.youtube.com/feed/trending"),
    ]
    records = [
        TrendRecord(id=str(i), project_id="p1", topic=f"Video {i}", topic_key=f"video {i}",
                    source_name=name, source_url=url, observed_at=now, window_start=now,
                    window_end=now, metric_name="views", metric_value=1, evidence=[])
        for i, (name, url) in enumerate(sources)
    ]
    view = BuildPanel(FakePanelRepo(), 15.0, lambda: now,
                      trends=FakeTrendRepo(records, now)).execute(days=7)
    html, _ = render_tendencias(view)
    header = html.split('<div class="trends-source">', 1)[1].split("</div>", 1)[0]
    assert "Fontes (todas as tendências):" in header
    assert header.count("YouTube Brasil (Em Alta)") == 1
    assert "YouTube EUA (Em Alta)" in header
    assert "YouTube (origem desconhecida)" in header
    assert "YouTube Data API" in header
    assert "https://www.googleapis.com/youtube/v3/search" in header
    assert "YouTube Global (Em Alta)" not in header


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
const br = element({'data-filter-type': 'region', 'data-region-code': 'BR'}, ['cat-pill']);
const us = element({'data-filter-type': 'region', 'data-region-code': 'US'}, ['cat-pill']);
const category = element({'data-filter-type': 'category', 'data-cat-id': 'six'}, ['cat-pill']);
const pills = [all, jp, br, us, category];
const items = Array.from({length: 9}, (_, i) =>
  element({'data-region': i < 7 ? 'BR' : 'JP', 'data-category-id': i < 6 ? 'six' : 'other'},
          i >= 6 ? ['trend-item-extra'] : []));
const toggle = element({'data-expanded': 'false', 'aria-expanded': 'false', 'data-total': '9'});
toggle.parentElement = {hidden: false};
const document = {
  querySelectorAll: (selector) => selector.startsWith('.cat-pill') ? pills : items,
  querySelector: () => pills.find((p) => p.classList.contains('active')),
  getElementById: (id) => id === 'btn-toggle-more-trends' ? toggle : null
};
"""
    checks = """
jp.click();
assert.equal(items[7].style.display, '');
assert.equal(items[8].style.display, '');
assert.ok(items.slice(0, 7).every((item) => item.style.display === 'none'));
assert.equal(toggle.hidden, true);
assert.equal(jp.attrs['aria-pressed'], 'true');
assert.equal(all.attrs['aria-pressed'], 'false');
br.click();
assert.equal(toggle.hidden, false);
assert.match(toggle.textContent, /\\(\\+1\\)/);
assert.equal(toggle.attrs['aria-expanded'], 'false');
toggle.click();
assert.equal(toggle.attrs['aria-expanded'], 'true');
assert.match(toggle.textContent, /Recolher/);
assert.equal(items[6].style.display, '');
category.click();
assert.equal(toggle.hidden, true);
assert.equal(toggle.attrs['aria-expanded'], 'false');
assert.equal(items.filter((item) => item.style.display === '').length, 6);
us.click();
assert.equal(toggle.hidden, true);
assert.equal(toggle.attrs['aria-expanded'], 'false');
assert.ok(items.every((item) => item.style.display === 'none'));
all.click();
assert.equal(toggle.hidden, false);
assert.equal(toggle.attrs['aria-expanded'], 'false');
assert.match(toggle.textContent, /\\(\\+3\\)/);
assert.equal(items[6].style.display, 'none');
toggle.click();
toggle.click();
assert.match(toggle.textContent, /\\(\\+3\\)/);
"""
    result = subprocess.run([node, "-e", setup + script + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _render_panel_html(repo=None, *, days=7, clock=None):
    from app.studio.api.panel import render_panel

    now = clock or datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    view = BuildPanel(repo or FakePanelRepo(), 15.0, lambda: now).execute(days=days)
    return render_panel(view)[0]


def _primary_nav(html):
    match = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', html, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _nav_text(item):
    return " ".join(re.sub(r"<[^>]+>", " ", item).split())


def _visible_text(html):
    without_regions = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", without_regions).split())


def _state_count(html, state):
    match = re.search(rf'data-state="{state}"[^>]*>.*?<span class="state-count">(\d+)</span>', html, re.S)
    assert match is not None, f"estado {state} sem contador explícito"
    return int(match.group(1))


def test_render_panel_shell_marks_exactly_one_active_nav_item():
    html = _render_panel_html()
    items = _primary_nav(html)
    labels = [_nav_text(item) for item in items]

    for expected in ("Início", "Produção", "Tendências", "Vídeos", "Canais", "Analytics", "Estilos", "Equipe"):
        assert any(expected in label for label in labels), expected

    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1
    assert "Início" in _nav_text(active[0])
    assert active[0].lstrip().startswith("<a ")
    assert html.count('aria-current="page"') == 1

    for label, href in (
        # IA-01: Início, Produção e Tendências são rotas de servidor reais; "Vídeos" aponta para
        # a rota real /studio/panel/videos (302 para o bloco #videos do Início) — não âncoras.
        ("Início", "/studio/panel"),
        ("Produção", "/studio/panel/producao"),
        ("Tendências", "/studio/panel/tendencias"),
        ("Vídeos", "/studio/panel/videos"),
        ("Canais", "/studio/canais"),
        ("Analytics", "/studio/panel/analytics"),
    ):
        item = next(item for item in items if label in _nav_text(item))
        assert f'href="{href}"' in item


def test_render_panel_shell_nav_targets_exist_in_the_page():
    """IA-01: "Vídeos" aponta para a rota real /studio/panel/videos (302 → `#videos` do Início).

    A casca deixou de ter âncoras para Início/Produção/Tendências (viraram rotas de servidor); a
    única âncora que o Início publica é `#videos`, e é ela que a rota de Vídeos resolve.
    """
    html = _render_panel_html()
    items = _primary_nav(html)

    videos = next(item for item in items if "Vídeos" in _nav_text(item))
    assert 'href="/studio/panel/videos"' in videos
    assert 'id="videos"' in html

    for item in items:
        match = re.search(r'href="(#[^"]+)"', item)
        if match is None:
            continue
        assert f'id="{match.group(1)[1:]}"' in html, f"âncora morta na casca: {match.group(1)}"


def test_render_panel_shell_has_no_disabled_nav_items_and_estilos_is_a_real_link():
    html = _render_panel_html()
    items = _primary_nav(html)

    # "Configurações — em breve" virou a tela real de Estilos (biblioteca compartilhada, VS-05a):
    # nenhum destino morto na casca.
    assert not any('aria-disabled="true"' in item for item in items)
    estilos = next(item for item in items if "Estilos" in _nav_text(item))
    assert 'href="/studio/panel/estilos"' in estilos
    assert not estilos.lstrip().startswith("<span ")
    assert estilos.lstrip().startswith("<a ")


def test_render_panel_has_one_h1_section_ids_and_no_invented_product_state():
    html = _render_panel_html()
    visible = _visible_text(html)

    assert html.count("<h1") == 1
    assert 'lang="pt-BR"' in html
    # IA-01: o Início publica só as suas seções. Produção (`producao-section`) e Tendências
    # (`trending-section`) viraram telas separadas; aqui ficam os resumos e o bloco Vídeos.
    for section_id in ("inicio-section", "inicio-producao-section", "precisa-section",
                       "inicio-tendencias-section", "videos", "new-video-section"):
        assert f'id="{section_id}"' in html
    assert 'id="producao-section"' not in html
    assert 'id="trending-section"' not in html

    for forbidden in (
        "Implementado", "Plano Pro", "créditos/mês", "Gerando imagens", "62%",
        "Rodrigo Dev", "Ana Costa", "Carlos Lima", "Mariana Alves", "Administrador",
        "Docker Local", "Saudável",
    ):
        assert forbidden not in visible
    assert re.search(r"\d+(?:[.,]\d+)?\s*%", visible) is None


def test_render_panel_empty_state_is_explicit_and_has_no_fake_progress():
    html = _render_panel_html()

    assert "Nenhuma execução registrada" in html
    assert 'role="progressbar"' not in html
    assert "<progress" not in html
    assert 'class="budget-fill"' not in html
    assert "0%" not in _visible_text(html)


def test_render_panel_always_states_done_running_and_action_with_text():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    rows = [
        _row("done", "Concluído", VideoStatus.PUBLISHED, pub=PublicationStatus.UPLOADED),
        _row("running", "Executando", VideoStatus.SCRIPTED, step_running=True),
        _row("action", "Aguardando", VideoStatus.AWAITING_APPROVAL),
        _row("idle", "Sem início", VideoStatus.IDEA),
    ]
    html = _render_panel_html(FakePanelRepo(videos_list=rows), clock=now)

    assert _state_count(html, "done") == 1
    assert _state_count(html, "running") == 1
    assert _state_count(html, "action") == 1
    for label in ("Concluído", "Em execução", "Ação necessária", "Sem execução registrada"):
        assert label in _visible_text(html)
    assert "0 concluídos · 0 em produção" not in html


def test_render_panel_only_offers_actions_valid_for_the_current_stage():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    html = _render_panel_html(FakePanelRepo(videos_list=[_row("v1", "Sem render", VideoStatus.IDEA)]), clock=now)

    assert "Ver Progresso" in html
    assert "Ver Prévia" not in html
    assert "Aprovar" not in html


def test_render_panel_labels_cost_origin_and_never_zero_for_unknown_or_absent():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)

    paid = _render_panel_html(FakePanelRepo(videos_list=[
        _row("paid", "Pago", VideoStatus.IDEA, costs=[("opencode", "gpt-paid", 0.5, "ACTUAL")]),
    ]), clock=now)
    assert "Real US$ 0,50" in paid

    estimated = _render_panel_html(FakePanelRepo(videos_list=[
        _row("est", "Estimado", VideoStatus.IDEA, costs=[("opencode", "gpt-est", 0.2, "ESTIMATE")]),
    ]), clock=now)
    assert "Estimado US$ 0,20" in estimated

    free = _render_panel_html(FakePanelRepo(videos_list=[
        _row("free", "Gratuito", VideoStatus.IDEA, costs=[("opencode", "gpt:free", 0.0, "FREE")]),
    ]), clock=now)
    assert "Sem custo" in free
    assert "US$ 0,00" not in free

    unknown = _render_panel_html(FakePanelRepo(videos_list=[
        _row("unknown", "Desconhecido", VideoStatus.IDEA, costs=[("opencode", "gpt-4o-paid", 0.0, None)]),
    ]), clock=now)
    assert "Desconhecido" in unknown
    assert "US$ 0,00" not in unknown

    absent = _render_panel_html(FakePanelRepo(videos_list=[_row("absent", "Sem uso", VideoStatus.IDEA)]), clock=now)
    assert "sem registro de uso" in absent
    assert "US$ 0,00" not in absent


def test_render_panel_legacy_positive_cost_is_estimated_not_zero():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    # Sem cost_confirmation_kind: um valor positivo não confirmado é uma estimativa, nunca real nem zero.
    html = _render_panel_html(FakePanelRepo(videos_list=[
        _row("legacy", "Legado", VideoStatus.IDEA, costs=[("opencode", "gpt-paid", 0.5, None)]),
    ]), clock=now)
    assert "Estimado US$ 0,50" in html
    assert "Real US$" not in html
    assert "US$ 0,00" not in html


def test_video_detail_usage_list_labels_each_call_kind():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    row = _row("v1", "Uso misto", VideoStatus.AWAITING_APPROVAL)
    usage = [
        UsageInfo("render", "opencode", "gpt-paid", 0.07, now, "ACTUAL"),
        UsageInfo("image", "opencode", "gpt-est", 0.05, now, "ESTIMATE"),
        UsageInfo("voice", "piper", "piper", 0.0, now, "FREE"),
        UsageInfo("text", "opencode", "gpt-4o-paid", 0.0, now, None),
    ]
    html = _detail_view(row, stage=Stage.AWAITING_APPROVAL, usage=usage)
    advanced_area = html.split('id="advanced-diagnostics"', 1)[1]

    assert "Real: US$ 0,07" in advanced_area
    assert "Estimado: US$ 0,05" in advanced_area
    assert "Sem custo" in advanced_area
    assert "Desconhecido" in advanced_area
    assert "US$ 0,00" not in advanced_area


def test_render_panel_has_closed_advanced_diagnostics():
    html = _render_panel_html()
    match = re.search(r'<details class="[^"]*advanced[^"]*" id="advanced-diagnostics"([^>]*)>', html)
    assert match is not None
    assert "open" not in match.group(1)
    assert "Avançado — diagnóstico" in html
    assert "<code>p1</code>" in html


def test_render_panel_declares_viewport_and_responsive_layout():
    html = _render_panel_html()
    assert 'name="viewport"' in html
    assert "@media (max-width: 820px)" in html


def test_panel_uses_dark_mockup_palette_tokens_and_visible_focus():
    from app.studio.api.panel import CSS

    root = CSS.split(":root {", 1)[1].split("\n}", 1)[0]
    expectations = {
        "--bg-app": "#0a0f19",
        "--bg-canvas": "#101827",
        "--surface": "#131b2d",
        "--surface-raised": "#1b263e",
        "--border": "#2a3350",
        "--border-soft": "#1f2942",
        "--text": "#e6e9f5",
        "--text-muted": "#aab3c8",
        "--text-dim": "#7f8aa6",
        "--accent": "#7c3aed",
        "--accent-strong": "#5b08f6",
        "--accent-soft": "#331e7e",
        "--accent-contrast": "#ffffff",
        "--success": "#74d6a6",
        "--success-surface": "#12322a",
        "--success-contrast": "#06130d",
        "--info": "#0abcff",
        "--warn": "#e3b341",
        "--danger": "#ff5a6e",
        "--radius": "18px",
    }
    for token, value in expectations.items():
        assert f"{token}: {value};" in root, token

    assert "color-scheme: dark" in root
    assert "accent-color: var(--accent);" in root
    assert "scrollbar-color: var(--border) var(--bg-app);" in root
    assert "prefers-color-scheme" not in CSS
    assert ":focus-visible" in CSS
    assert "outline: 2px solid var(--info)" in CSS

    for block in re.findall(r"\{([^{}]*)\}", CSS):
        if "background: var(--success-surface)" in block:
            assert re.search(r"color:\s*(#ffffff|#fff|white|var\(--accent-contrast\))", block) is None, block
    assert "var(--success-contrast)" in CSS


def _detail_view(row, *, stage=Stage.PENDING, steps=None, usage=None, render_error=None, publication=None,
                 sources=None, latest_run=None, base_video_url=None, base_video_source_name=None):
    detail = VideoDetailView(
        video=row,
        stage=stage,
        cost_text="sem registro de uso",
        steps=steps or [],
        usage=usage or [],
        render_error=render_error,
        publication=publication,
        sources=sources or [],
        latest_run=latest_run,
        base_video_url=base_video_url,
        base_video_source_name=base_video_source_name,
    )
    from app.studio.api.panel import render_video
    return render_video(detail)[0]


def test_video_detail_hides_approval_when_no_artifact_is_ready():
    row = _row("v1", "Sem artefato", VideoStatus.IDEA)
    html = _detail_view(row, stage=Stage.PENDING)
    assert "Aprovar" not in html


def test_video_detail_keeps_raw_traceback_out_of_main_area_and_states_correction():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    row = _row("v1", "Falha crua", VideoStatus.IDEA)
    step = StepInfo("render", 1, "FAILED", None, "Traceback (most recent call last): boom", now, now)
    html = _detail_view(row, stage=Stage.FAILED, steps=[step], render_error="Traceback (most recent call last): boom")

    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert "Traceback" not in main_area
    assert "Passo de correção" in main_area
    advanced_area = html.split('id="advanced-diagnostics"', 1)[1]
    assert "Traceback" in advanced_area


def test_video_detail_advanced_diagnostics_is_closed_and_holds_usage_ledger():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    row = _row("v1", "Com uso", VideoStatus.AWAITING_APPROVAL)
    usage = [UsageInfo("text", "opencode", "gpt-4o-paid", 0.0, now)]
    html = _detail_view(row, stage=Stage.AWAITING_APPROVAL, usage=usage)

    match = re.search(r'<details class="[^"]*advanced[^"]*" id="advanced-diagnostics"([^>]*)>', html)
    assert match is not None
    assert "open" not in match.group(1)
    assert "Avançado — diagnóstico" in html
    advanced_area = html.split('id="advanced-diagnostics"', 1)[1]
    assert "Registro de Uso de Modelos" in advanced_area
    assert "Desconhecido" in advanced_area


def test_video_detail_offers_retry_only_when_resume_is_valid():
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    valid = _row("v1", "Pronto para render", VideoStatus.ASSETS_READY)
    html = _detail_view(valid, stage=Stage.FAILED, render_error="FFmpeg falhou")
    assert 'id="btn-retry-render"' in html
    assert "/studio/videos/v1/resume" in html

    invalid = _row("v2", "Sem artefato", VideoStatus.IDEA)
    html_invalid = _detail_view(invalid, stage=Stage.FAILED, render_error="FFmpeg falhou")
    assert 'id="btn-retry-render"' not in html_invalid


def test_render_panel_matches_approved_mockup_structure_without_illustrative_data():
    html = _render_panel_html()
    visible = _visible_text(html)

    for group in ("Operação", "Gestão"):
        assert group in visible

    assert 'class="hero"' in html
    assert "accent-word" in html
    assert "Transforme uma ideia em um vídeo" in visible
    assert 'role="tablist"' in html

    assert "Nenhuma execução registrada" in visible
    for step in ("Roteiro", "Fontes", "Fact-check", "Cenas", "Voz", "Render", "QA", "Publicação"):
        assert step in visible
    assert "Não há percentual" in visible

    for rail in ("Custo do mês", "Última falha", "Estado das fases"):
        assert rail in visible
    assert "F8 Publicação" in visible and "F11 SaaS" in visible

    assert 'id="advanced-diagnostics"' in html

    for forbidden in (
        "Como a OpenAI ganha dinheiro?", "1,2 mi views", "890 mil views", "650 mil views",
        "US$ 0,07", "US$ 0,05", "run_7f3a", "vid_2b91", "9f2c", "Agentes de IA na prática",
        "Rodrigo Dev", "Faber", "Plano Pro",
    ):
        assert forbidden not in visible


def test_render_panel_series_tab_is_disabled_and_not_focusable():
    html = _render_panel_html()
    match = re.search(r'<button[^>]*id="tab-serie"[^>]*>', html)
    assert match is not None
    tag = match.group(0)
    assert 'role="tab"' in tag
    assert 'aria-disabled="true"' in tag
    assert 'tabindex="-1"' in tag

    ideia = re.search(r'<button[^>]*id="tab-ideia"[^>]*>', html)
    assert ideia is not None and 'aria-selected="true"' in ideia.group(0)


# ---------- PROD-01/PROD-04: criar→abrir o vídeo, fontes e (nova) produção ----------


def test_home_create_form_opens_the_video_page_without_starting_production():
    """PROD-04 (achado 4): o Início cria o vídeo e abre a página do vídeo, **sem** iniciar run.

    Isto reverte deliberadamente o auto-start do PROD-01. O fluxo aprovado em
    JORNADA-E-TELAS.md é Produzir vídeo → Pesquisar fontes → Roteiro: a 1ª etapa do DAG
    (`script`) exige fontes, e a fonte só pode ser adicionada depois que o vídeo existe — então
    iniciar no ato de criar garantia um run `FAILED` ("SourceRefused: no sources...") na cara
    do usuário. O vídeo abre onde vivem Fontes e «Iniciar produção».
    """
    html = _render_panel_html()
    # Cria o vídeo pelo mesmo endpoint...
    assert "/studio/videos" in html
    # ...mas não inicia produção nenhuma: nenhum POST /production-runs sai do Início.
    assert "/production-runs" not in html
    # O destino é a página do vídeo (onde a fonte é registrada e a produção começa).
    assert "location.href = '/studio/panel/videos/' + encodeURIComponent(data.id)" in html
    # A tela declara o novo fluxo, sem prometer que a produção já começa.
    assert "pesquisar as fontes" in _visible_text(html)


# ---------- PROD-04 (achado 3): a criação carrega o vídeo base da tendência ----------


def test_evidence_video_url_is_the_shared_trend_extraction():
    """Uma só extração da URL do vídeo base, usada pelo cartão de tendência e pela página do vídeo."""
    from app.studio.application.panel import evidence_video_url

    assert evidence_video_url([{"url": "https://youtube.com/watch?v=abc"}]) == "https://youtube.com/watch?v=abc"
    assert evidence_video_url([]) is None
    assert evidence_video_url([{}]) is None
    assert evidence_video_url([{"title": "sem url"}]) is None


def _detail_with_trends(topic, *, records):
    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    row = _row("v1", topic, VideoStatus.IDEA)
    detail = VideoDetail(video=row, steps=[], usage=[], render_error=None, publication=None)
    panel = BuildPanel(FakePanelRepo(detail_map={"v1": detail}), 15.0, lambda: now,
                       trends=FakeTrendRepo(records, now))
    return panel.detail("v1")


def test_detail_resolves_base_video_url_by_topic_key():
    """O tema do vídeo casa com a tendência por `topic_key` do domínio (a prova do achado 3)."""
    from app.studio.application.ports import TrendRecord
    from app.studio.domain.panel import topic_key

    now = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    topic = "GTA VI: DIA 3 ZERANDO  🔴 CORINGA AO VIVO"
    assert topic_key(topic) == "gta vi: dia 3 zerando 🔴 coringa ao vivo"
    trend = TrendRecord(
        id="t1", project_id="p1", topic=topic, topic_key=topic_key(topic),
        source_name="YouTube Brasil (Em Alta)", source_url="https://www.youtube.com/feed/trending",
        observed_at=now, window_start=now - timedelta(days=7), window_end=now,
        metric_name="views", metric_value=1000.0,
        evidence=[{"url": "https://youtube.com/watch?v=nTJ5Z9gZsZU"}],
    )
    view = _detail_with_trends(topic, records=[trend])
    assert view.base_video_url == "https://youtube.com/watch?v=nTJ5Z9gZsZU"
    assert view.base_video_source_name == "YouTube Brasil (Em Alta)"


def test_detail_without_a_matching_trend_has_no_base_video_url():
    view = _detail_with_trends("Tema sem tendência correspondente", records=[])
    assert view.base_video_url is None
    assert view.base_video_source_name is None


def test_video_detail_sources_card_prefills_the_base_video_url():
    html = _detail_view(
        _row("v1", "Tema com base"),
        base_video_url="https://youtube.com/watch?v=nTJ5Z9gZsZU",
        base_video_source_name="YouTube Brasil (Em Alta)",
    )
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'value="https://youtube.com/watch?v=nTJ5Z9gZsZU"' in main_area
    assert "vídeo base" in main_area
    assert "https://youtube.com/watch?v=nTJ5Z9gZsZU" in main_area


def test_video_detail_sources_card_stays_empty_without_a_matching_trend():
    html = _detail_view(_row("v1", "Tema sem base"))
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert "vídeo base" not in main_area
    match = re.search(r'<input[^>]*id="source-url"[^>]*>', main_area)
    assert match is not None and "value=" not in match.group(0)


# ---------- PROD-04 (achado 5): produção nova num vídeo que já tem run ----------


@pytest.mark.parametrize("state", ["FAILED", "CANCELLED", "SUCCEEDED"])
def test_video_detail_terminal_run_offers_new_production(state):
    failed = state == "FAILED"
    html = _detail_view(_row("v1", "Run terminal"), latest_run=LatestRun(
        run_id="a" * 32, state=state,
        failed_stage="script" if failed else None,
        failure_reason="no sources with checkable claims: add sources first" if failed else None))
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'id="btn-new-production"' in main_area
    assert "Iniciar nova produção" in main_area
    # Deixa claro que não é o retry: recomeça do zero.
    assert "recomeça do zero" in main_area


def test_video_detail_live_run_does_not_offer_new_production():
    for state in ("RUNNING", "WAITING_HUMAN"):
        html = _detail_view(_row("v1", "Run vivo"), latest_run=LatestRun(run_id="a" * 32, state=state))
        main_area = html.split('id="advanced-diagnostics"', 1)[0]
        assert 'id="btn-new-production"' not in main_area, state
        assert 'id="btn-start-production"' not in main_area, state
        assert "Abrir execução" in main_area, state


def test_video_detail_lists_registered_sources_with_url_and_size():
    html = _detail_view(_row("v1", "Com fontes"), sources=[
        SourceInfo(id="s1", url="https://exemplo.com/a", chars=120),
        SourceInfo(id="s2", url="https://exemplo.com/b", chars=1),
    ])
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert "Fontes" in main_area
    assert "https://exemplo.com/a" in main_area and "120 caracteres" in main_area
    assert "https://exemplo.com/b" in main_area and "1 caractere" in main_area
    assert "2 fonte(s) registrada(s)" in main_area


def test_video_detail_has_the_sources_form_with_url_and_textarea():
    html = _detail_view(_row("v1", "Sem fontes"))
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'id="video-sources-form"' in main_area
    assert 'id="source-url"' in main_area and 'required' in main_area
    assert 'id="source-text"' in main_area and "<textarea" in main_area
    # A regra real explicada em linguagem de usuário, sem prometer o que não faz.
    assert "o texto colado é a fonte" in main_area
    assert "STUDIO_SOURCE_ALLOWLIST" in main_area


def test_video_detail_without_run_offers_start_production():
    html = _detail_view(_row("v1", "Sem run"), latest_run=None)
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'id="btn-start-production"' in main_area and "Iniciar produção" in main_area
    assert 'id="btn-retry-production"' not in main_area


def test_video_detail_failed_run_shows_real_reason_and_retry():
    html = _detail_view(_row("v1", "Run falho"), latest_run=LatestRun(
        run_id="a" * 32, state="FAILED", failed_stage="script",
        failure_reason="no sources with checkable claims: add sources first"))
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'id="btn-retry-production"' in main_area
    assert "Tentar novamente" in main_area
    # O motivo real do servidor, não um erro genérico.
    assert "no sources with checkable claims: add sources first" in main_area
    assert "Parou na etapa" in main_area and "Roteiro" in main_area
    assert 'id="btn-start-production"' not in main_area


def test_video_detail_running_run_explains_no_retry_without_inert_button():
    html = _detail_view(_row("v1", "Run em execução"), latest_run=LatestRun(
        run_id="a" * 32, state="RUNNING"))
    main_area = html.split('id="advanced-diagnostics"', 1)[0]
    assert 'id="btn-retry-production"' not in main_area
    assert 'id="btn-start-production"' not in main_area
    assert "Nova tentativa só é válida quando a execução está em falha" in main_area
    assert "Abrir execução" in main_area
