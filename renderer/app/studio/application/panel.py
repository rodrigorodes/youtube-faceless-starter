"""Caso de uso de construção da visão operacional do painel do Studio."""
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..domain.panel import CostSummary, Stage, classify, cost_text, is_known_cost, topic_key
from .editorial import VideoNotFound
from .ports import PanelRepository, PubInfo, StepInfo, UsageInfo, VideoRow
from .use_cases import InvalidInput


@dataclass(frozen=True)
class MonthCost:
    text: str
    known_usd: float
    cap_usd: float
    unknown_calls: int
    percent: float | None


@dataclass(frozen=True)
class VideoItem:
    id: str
    topic: str
    title: str
    stage: Stage
    cost_text: str
    updated_at: datetime
    actions: list[str]


@dataclass(frozen=True)
class TopicGroup:
    key: str
    label: str
    counts: dict[Stage, int]
    cost_text: str
    videos: list[VideoItem]


@dataclass(frozen=True)
class PanelView:
    generated_at: datetime
    days: int
    projects: list[tuple[str, str]]
    totals: dict[Stage, int]
    month: MonthCost
    topics: list[TopicGroup]
    truncated: bool = False


@dataclass(frozen=True)
class VideoDetailView:
    video: VideoRow
    stage: Stage
    cost_text: str
    steps: list[StepInfo]
    usage: list[UsageInfo]
    render_error: str | None
    publication: PubInfo | None


class BuildPanel:
    def __init__(self, repo: PanelRepository, monthly_cap_usd: float, clock: Callable[[], datetime]):
        self.repo = repo
        self.monthly_cap_usd = monthly_cap_usd
        self.clock = clock

    def execute(self, days: int = 7, project_id: str | None = None) -> PanelView:
        if days not in (7, 14, 30):
            raise InvalidInput("days must be 7, 14 or 30")

        now = self.clock()
        since = now - timedelta(days=days)
        limit = 500
        rows = self.repo.videos(since=since, project_id=project_id, limit=limit)
        truncated = len(rows) >= limit

        projects = self.repo.projects()
        totals = {stage: 0 for stage in Stage}

        grouped_videos: dict[str, list[tuple[VideoRow, Stage, CostSummary, VideoItem]]] = defaultdict(list)

        for r in rows:
            st = classify(r.status, job=r.job_status, step_running=r.step_running, publication=r.publication_status)
            totals[st] += 1

            known = sum(c for p, m, c in r.cost_rows if is_known_cost(p, m, c))
            calls = len(r.cost_rows)
            unknown = sum(1 for p, m, c in r.cost_rows if not is_known_cost(p, m, c))
            c_summary = CostSummary(known, calls, unknown)

            actions = []
            if st in (Stage.AWAITING_APPROVAL, Stage.APPROVED, Stage.COMPLETED):
                actions.append("preview")
            if st in (Stage.AWAITING_APPROVAL, Stage.IN_PRODUCTION, Stage.FAILED, Stage.PENDING):
                actions.append("progress")

            item = VideoItem(
                id=r.id,
                topic=r.topic,
                title=r.title,
                stage=st,
                cost_text=cost_text(c_summary),
                updated_at=r.updated_at,
                actions=actions,
            )
            key = topic_key(r.topic)
            grouped_videos[key].append((r, st, c_summary, item))

        topic_groups: list[TopicGroup] = []
        for key, entries in grouped_videos.items():
            # label comes from the most recently updated video in the group, cleaned of extra whitespace
            entries.sort(key=lambda x: x[0].updated_at, reverse=True)
            label = re.sub(r"\s+", " ", entries[0][0].topic).strip()

            counts = {stage: 0 for stage in Stage}
            total_known = 0.0
            total_calls = 0
            total_unknown = 0
            v_items = []

            for r, st, c_sum, item in entries:
                counts[st] += 1
                total_known += c_sum.known_usd
                total_calls += c_sum.calls
                total_unknown += c_sum.unknown_calls
                v_items.append(item)

            group_cost = CostSummary(total_known, total_calls, total_unknown)
            topic_groups.append(TopicGroup(
                key=key,
                label=label,
                counts=counts,
                cost_text=cost_text(group_cost),
                videos=v_items,
            ))

        # Order groups by most recent video update
        topic_groups.sort(key=lambda g: g.videos[0].updated_at, reverse=True)

        m_known, m_calls, m_unknown = self.repo.month_usage()
        m_cost = CostSummary(m_known, m_calls, m_unknown)
        percent = (m_known / self.monthly_cap_usd * 100.0) if self.monthly_cap_usd > 0 else None
        month = MonthCost(
            text=cost_text(m_cost),
            known_usd=m_known,
            cap_usd=self.monthly_cap_usd,
            unknown_calls=m_unknown,
            percent=percent,
        )

        return PanelView(
            generated_at=now,
            days=days,
            projects=projects,
            totals=totals,
            month=month,
            topics=topic_groups,
            truncated=truncated,
        )

    def detail(self, video_id: str) -> VideoDetailView:
        d = self.repo.video_detail(video_id)
        if d is None:
            raise VideoNotFound(video_id)

        st = classify(d.video.status, job=d.video.job_status, step_running=d.video.step_running, publication=d.video.publication_status)
        usage_tuples = [(u.provider, u.model, u.cost_usd) for u in d.usage] if d.usage else d.video.cost_rows
        known = sum(c for p, m, c in usage_tuples if is_known_cost(p, m, c))
        calls = len(usage_tuples)
        unknown = sum(1 for p, m, c in usage_tuples if not is_known_cost(p, m, c))
        c_text = cost_text(CostSummary(known, calls, unknown))

        return VideoDetailView(
            video=d.video,
            stage=st,
            cost_text=c_text,
            steps=d.steps,
            usage=d.usage,
            render_error=d.render_error,
            publication=d.publication,
        )
