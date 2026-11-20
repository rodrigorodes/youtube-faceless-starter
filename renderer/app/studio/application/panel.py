"""Caso de uso de construção da visão operacional do painel do Studio."""
import re
import urllib.parse
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..domain.categories import ProjectCategory
from ..domain.contracts import VideoFormat
from ..domain.panel import Stage, classify, is_known_cost, topic_key
from .editorial import VideoNotFound
from .errors import InvalidInput
from .ports import CategoryRepository, PanelRepository, PubInfo, StepInfo, TrendRepository, UsageInfo, VideoRow


class CostKind(str, Enum):
    """Rótulo de custo exibido ao operador. Espelha `usage_ledger.cost_confirmation_kind`."""

    REAL = "real"           # ACTUAL: cobrança comprovada
    ESTIMATE = "estimate"   # ESTIMATE (ou valor positivo ainda sem confirmação)
    FREE = "free"           # FREE ou gratuidade reconhecida pelo provedor/modelo
    UNKNOWN = "unknown"     # sem confirmação e sem custo conhecido


def cost_kind(kind: str | None, provider: str, model: str, cost_usd: float) -> CostKind:
    """Classifica um lançamento do ledger nos quatro rótulos, sem inventar separação.

    A coluna `cost_confirmation_kind` é a fonte de verdade. Sem confirmação, o valor só é
    conhecido pelas regras de gratuidade já existentes: um zero reconhecido é "Sem custo"; um
    valor positivo não confirmado é uma estimativa (a cobrança ainda não foi comprovada); o
    restante é desconhecido — nunca tratado como zero.
    """
    if kind == "ACTUAL":
        return CostKind.REAL
    if kind == "ESTIMATE":
        return CostKind.ESTIMATE
    if kind == "FREE":
        return CostKind.FREE
    if not is_known_cost(provider, model, cost_usd):
        return CostKind.UNKNOWN
    return CostKind.FREE if cost_usd == 0.0 else CostKind.ESTIMATE


_COST_LABELS = {
    CostKind.REAL: "Real",
    CostKind.ESTIMATE: "Estimado",
    CostKind.FREE: "Sem custo",
    CostKind.UNKNOWN: "Desconhecido",
}


def cost_label(kind: CostKind) -> str:
    return _COST_LABELS[kind]


@dataclass(frozen=True)
class CostBreakdown:
    """Custo somado por rótulo. Nunca funde real e estimado num único número."""

    real_usd: float = 0.0
    real_calls: int = 0
    estimate_usd: float = 0.0
    estimate_calls: int = 0
    free_calls: int = 0
    unknown_calls: int = 0

    @property
    def calls(self) -> int:
        return self.real_calls + self.estimate_calls + self.free_calls + self.unknown_calls

    @property
    def known_usd(self) -> float:
        return self.real_usd + self.estimate_usd


def cost_breakdown(rows: Iterable[tuple[str, str, float, str | None]]) -> CostBreakdown:
    real = estimate = 0.0
    real_calls = estimate_calls = free_calls = unknown_calls = 0
    for provider, model, cost_usd, kind in rows:
        classified = cost_kind(kind, provider, model, cost_usd)
        if classified is CostKind.REAL:
            real += cost_usd
            real_calls += 1
        elif classified is CostKind.ESTIMATE:
            estimate += cost_usd
            estimate_calls += 1
        elif classified is CostKind.FREE:
            free_calls += 1
        else:
            unknown_calls += 1
    return CostBreakdown(real, real_calls, estimate, estimate_calls, free_calls, unknown_calls)


def sum_breakdowns(breakdowns: Iterable[CostBreakdown]) -> CostBreakdown:
    items = list(breakdowns)
    if not items:
        return CostBreakdown()
    return CostBreakdown(
        real_usd=sum(b.real_usd for b in items),
        real_calls=sum(b.real_calls for b in items),
        estimate_usd=sum(b.estimate_usd for b in items),
        estimate_calls=sum(b.estimate_calls for b in items),
        free_calls=sum(b.free_calls for b in items),
        unknown_calls=sum(b.unknown_calls for b in items),
    )


def _usd(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def cost_summary_text(b: CostBreakdown) -> str:
    """Texto rotulado por categoria. Ausência de uso e gratuidade nunca viram 'US$ 0,00'."""
    if b.calls == 0:
        return "sem registro de uso"
    parts = []
    if b.real_calls:
        parts.append(f"Real US$ {_usd(b.real_usd)}")
    if b.estimate_calls:
        parts.append(f"Estimado US$ {_usd(b.estimate_usd)}")
    if b.free_calls:
        parts.append(cost_label(CostKind.FREE))
    if b.unknown_calls:
        parts.append(cost_label(CostKind.UNKNOWN))
    return " · ".join(parts) if parts else "sem registro de uso"


@dataclass(frozen=True)
class MonthCost:
    text: str
    known_usd: float
    cap_usd: float
    unknown_calls: int
    percent: float | None
    breakdown: CostBreakdown = field(default_factory=CostBreakdown)


@dataclass(frozen=True)
class VideoItem:
    id: str
    topic: str
    title: str
    stage: Stage
    cost_text: str
    updated_at: datetime
    actions: list[str]
    format: VideoFormat = VideoFormat.short


@dataclass(frozen=True)
class TopicGroup:
    key: str
    label: str
    counts: dict[Stage, int]
    cost_text: str
    videos: list[VideoItem]


@dataclass(frozen=True)
class TrendItemView:
    topic: str
    key: str
    source_name: str
    source_url: str
    observed_at: datetime
    stale: bool
    metric_text: str | None
    evidence: list[dict]
    counts: dict[Stage, int]
    cost_text: str
    create_action: bool
    category_id: str | None = None
    category_name: str | None = None
    video_id: str | None = None
    thumbnail_url: str | None = None
    video_url: str | None = None
    channel_title: str | None = None
    published_text: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class PanelView:
    generated_at: datetime
    days: int
    projects: list[tuple[str, str]]
    totals: dict[Stage, int]
    month: MonthCost
    topics: list[TopicGroup]
    truncated: bool = False
    trends: list[TrendItemView] = field(default_factory=list)
    trends_status: str = "never_collected"
    last_collected_at: datetime | None = None
    categories: list[ProjectCategory] = field(default_factory=list)
    project_id: str | None = None


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
    def __init__(
        self,
        repo: PanelRepository,
        monthly_cap_usd: float,
        clock: Callable[[], datetime],
        trends: TrendRepository | None = None,
        categories_repo: CategoryRepository | None = None,
    ):
        self.repo = repo
        self.monthly_cap_usd = monthly_cap_usd
        self.clock = clock
        self.trends = trends
        self.categories_repo = categories_repo

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

        grouped_videos: dict[str, list[tuple[VideoRow, Stage, CostBreakdown, VideoItem]]] = defaultdict(list)

        for r in rows:
            st = classify(r.status, job=r.job_status, step_running=r.step_running, publication=r.publication_status)
            totals[st] += 1

            c_summary = cost_breakdown(r.cost_rows)

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
                cost_text=cost_summary_text(c_summary),
                updated_at=r.updated_at,
                actions=actions,
                format=r.format,
            )
            key = topic_key(r.topic)
            grouped_videos[key].append((r, st, c_summary, item))

        topic_groups: list[TopicGroup] = []
        for key, entries in grouped_videos.items():
            # label comes from the most recently updated video in the group, cleaned of extra whitespace
            entries.sort(key=lambda x: x[0].updated_at, reverse=True)
            label = re.sub(r"\s+", " ", entries[0][0].topic).strip()

            counts = {stage: 0 for stage in Stage}
            v_items = []

            for r, st, c_sum, item in entries:
                counts[st] += 1
                v_items.append(item)

            group_cost = sum_breakdowns(c_sum for _, _, c_sum, _ in entries)
            topic_groups.append(TopicGroup(
                key=key,
                label=label,
                counts=counts,
                cost_text=cost_summary_text(group_cost),
                videos=v_items,
            ))

        # Order groups by most recent video update
        topic_groups.sort(key=lambda g: g.videos[0].updated_at, reverse=True)

        m_breakdown = cost_breakdown(self.repo.month_usage())
        m_known = m_breakdown.known_usd
        percent = (m_known / self.monthly_cap_usd * 100.0) if self.monthly_cap_usd > 0 else None
        month = MonthCost(
            text=cost_summary_text(m_breakdown),
            known_usd=m_known,
            cap_usd=self.monthly_cap_usd,
            unknown_calls=m_breakdown.unknown_calls,
            percent=percent,
            breakdown=m_breakdown,
        )

        trend_views: list[TrendItemView] = []
        trends_status = "never_collected"
        last_col = None

        categories: list[ProjectCategory] = []
        target_project_id = project_id or (projects[0][0] if projects else None)
        if self.categories_repo is not None and target_project_id:
            categories = self.categories_repo.list(target_project_id)

        if self.trends is not None:
            last_col = self.trends.last_collected_at(project_id)
            if last_col is not None:
                recs = self.trends.list(project_id, since=since)
                trends_status = "stale" if last_col < since else "ok"
                for r in recs:
                    if r.topic_key in grouped_videos:
                        entries = grouped_videos[r.topic_key]
                        c_counts = {stage: 0 for stage in Stage}
                        for _, st, _, _ in entries:
                            c_counts[st] += 1
                        t_cost_text = cost_summary_text(sum_breakdowns(c_sum for _, _, c_sum, _ in entries))
                    else:
                        c_counts = {stage: 0 for stage in Stage}
                        t_cost_text = "Nenhum vídeo ainda"

                    metric_text = (
                        f"{int(r.metric_value):,} visualizações".replace(",", ".")
                        if r.metric_value is not None else None
                    )
                    is_stale = r.observed_at < since
                    create_action = len(r.topic) <= 300

                    matched_cat_id = None
                    matched_cat_name = None
                    rec_cat_id = getattr(r, "category_id", None)
                    if rec_cat_id:
                        for cat in categories:
                            if cat.id == rec_cat_id:
                                matched_cat_id = cat.id
                                matched_cat_name = cat.name
                                break
                    if not matched_cat_id:
                        topic_lower = r.topic.lower()
                        for cat in categories:
                            found = False
                            for q in cat.queries:
                                q_lower = q.lower()
                                if q_lower in topic_lower or any(q_lower in ev.get("title", "").lower() for ev in r.evidence):
                                    matched_cat_id = cat.id
                                    matched_cat_name = cat.name
                                    found = True
                                    break
                            if found:
                                break

                    region = None
                    if r.source_name == "YouTube Brasil (Em Alta)":
                        region = "BR"
                    elif r.source_name == "YouTube EUA (Em Alta)":
                        region = "US"
                    elif r.source_name == "YouTube Global (Em Alta)":
                        region = "UNKNOWN"
                    else:
                        match = re.fullmatch(r"YouTube ([A-Z]{2}) \(Em Alta\)", r.source_name)
                        if match:
                            region = match.group(1)

                    video_id = None
                    thumbnail_url = None
                    video_url = None
                    channel_title = None
                    published_text = None

                    if r.evidence:
                        ev = r.evidence[0]
                        video_url = ev.get("url")
                        if video_url:
                            try:
                                parsed = urllib.parse.urlparse(video_url)
                                if "youtu.be" in parsed.netloc:
                                    video_id = parsed.path.lstrip("/").split("/")[0] or None
                                else:
                                    qs = urllib.parse.parse_qs(parsed.query)
                                    if "v" in qs and qs["v"]:
                                        video_id = qs["v"][0]
                            except Exception:
                                pass
                            if not video_id:
                                m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", video_url)
                                if m:
                                    video_id = m.group(1)

                        if video_id:
                            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

                        channel_title = ev.get("channel")

                        pub = ev.get("published_at")
                        if isinstance(pub, str):
                            try:
                                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                published_text = dt.strftime("%d/%m/%Y")
                            except ValueError:
                                published_text = None
                        elif isinstance(pub, datetime):
                            published_text = pub.strftime("%d/%m/%Y")

                    trend_views.append(TrendItemView(
                        topic=r.topic,
                        key=r.topic_key,
                        source_name=r.source_name,
                        source_url=r.source_url,
                        observed_at=r.observed_at,
                        stale=is_stale,
                        metric_text=metric_text,
                        evidence=r.evidence,
                        counts=c_counts,
                        cost_text=t_cost_text,
                        create_action=create_action,
                        category_id=matched_cat_id,
                        category_name=matched_cat_name,
                        video_id=video_id,
                        thumbnail_url=thumbnail_url,
                        video_url=video_url,
                        channel_title=channel_title,
                        published_text=published_text,
                        region=region,
                    ))

        return PanelView(
            generated_at=now,
            days=days,
            projects=projects,
            totals=totals,
            month=month,
            topics=topic_groups,
            truncated=truncated,
            trends=trend_views,
            trends_status=trends_status,
            last_collected_at=last_col,
            categories=categories,
            project_id=target_project_id,
        )

    def detail(self, video_id: str) -> VideoDetailView:
        d = self.repo.video_detail(video_id)
        if d is None:
            raise VideoNotFound(video_id)

        st = classify(d.video.status, job=d.video.job_status, step_running=d.video.step_running, publication=d.video.publication_status)
        usage_rows = (
            [(u.provider, u.model, u.cost_usd, u.cost_confirmation_kind) for u in d.usage]
            if d.usage else d.video.cost_rows
        )
        c_text = cost_summary_text(cost_breakdown(usage_rows))

        return VideoDetailView(
            video=d.video,
            stage=st,
            cost_text=c_text,
            steps=d.steps,
            usage=d.usage,
            render_error=d.render_error,
            publication=d.publication,
        )
