"""F9-01/03/05: dashboard e recomendações derivadas de medição real, com ausência explícita.

A camada não desenha HTML. Ela transforma medições persistidas em um recorte legível e aplica
as regras que a tela não pode violar:

- Short e long-form nunca entram no mesmo agregado;
- métrica aditiva só é somada com cobertura completa; taxa não é média de médias;
- origem mista vira ``origem desconhecida`` (nunca "Global");
- recomendação exige amostra mínima (3 vídeos comparáveis por pilar e formato), é declarada
  com confiança baixa e nasce como proposta para revisão humana — não altera configuração.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..domain.analytics_learning import (
    AnalyticsLearningBundle,
    AnalyticsPeriod,
    CollectionReadiness,
    DashboardQuery,
    ExperimentRecord,
    MetricAggregate,
    MetricMeasurement,
    RecommendationDecision,
    RecommendationKind,
    ThemeFormatRecommendation,
    aggregate_metric,
    origin_label,
)
from ..domain.insight import (
    ConfidenceDeclaration,
    InsightHypothesis,
    LearningInsight,
)
from .analytics_ports import AnalyticsRepository, StoredMetric
from .errors import ProjectNotFound

FORMAT_LABELS = {"long": "Long-form", "short": "Short"}
METRIC_LABELS = {
    "views": "Views",
    "impressions": "Impressões",
    "ctr": "CTR (cliques / impressões)",
    "average_view_percentage": "Retenção média",
    "estimated_minutes_watched": "Tempo assistido",
    "average_view_duration_s": "Duração média assistida",
    "likes": "Likes",
    "comments": "Comentários",
    "shares": "Compartilhamentos",
    "subscribers_gained": "Inscritos ganhos",
}
TILE_METRICS = ("views", "ctr", "average_view_percentage", "estimated_minutes_watched")
TILE_WHY = {
    "views": "O valor só existe depois do primeiro envio com o escopo de leitura autorizado.",
    "ctr": "Depende de impressões, que a API expõe por janela e permissão. Sem isso, não estimamos.",
    "average_view_percentage": "Só vem da API de Analytics do canal. Não derivamos de duração nem de palavras por minuto.",
    "estimated_minutes_watched": "Mesma origem da retenção. Ausência de dado não é zero.",
}
MINIMUM_SAMPLE = 3
_PT_BR_MONTH = "%d/%m/%Y"
_EMPTY = "Ainda não disponível"


def _int_pt(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def _decimal_pt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _percent(value: float) -> str:
    return f"{_decimal_pt(value)}%"


def _watch_time(minutes: float) -> str:
    if minutes < 60:
        return f"{_int_pt(minutes)} min"
    return f"{_decimal_pt(minutes / 60)} h"


def format_metric(metric: str, value: float | None) -> str | None:
    if value is None:
        return None
    if metric in ("ctr", "average_view_percentage"):
        return _percent(value)
    if metric == "estimated_minutes_watched":
        return _watch_time(value)
    if metric == "average_view_duration_s":
        return f"{_decimal_pt(value)} s"
    return _int_pt(value)


def _date(value: datetime) -> str:
    return value.strftime(_PT_BR_MONTH)


@dataclass(frozen=True)
class AggregateView:
    metric: str
    state: str
    text: str | None
    why: str
    coverage_text: str
    origin_label: str

    @property
    def measured(self) -> bool:
        return self.state == "measured"


def aggregate_view(aggregate: MetricAggregate) -> AggregateView:
    measured, total = aggregate.coverage
    coverage = "sem vídeos comparáveis" if total == 0 else f"{measured} de {total} vídeos"
    return AggregateView(
        metric=aggregate.metric,
        state=aggregate.state,
        text=format_metric(aggregate.metric, aggregate.value),
        why=aggregate.reason,
        coverage_text=coverage,
        origin_label=origin_label(aggregate.origin),
    )


@dataclass(frozen=True)
class TileGroup:
    comparison: str
    label: str
    state: str
    text: str | None
    why: str
    origin_label: str
    coverage_text: str


@dataclass(frozen=True)
class Tile:
    metric: str
    label: str
    groups: tuple[TileGroup, ...]
    why: str


@dataclass(frozen=True)
class Cell:
    metric: str
    label: str
    state: str
    text: str | None
    why: str
    origin_label: str


@dataclass(frozen=True)
class VideoOption:
    id: str
    label: str


@dataclass(frozen=True)
class VideoMetricsView:
    video_id: str
    topic: str
    format_label: str
    pillar_text: str
    attribution_text: str
    cells: tuple[Cell, ...]
    origin_label: str
    observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class PillarMetricsView:
    pillar_text: str
    format_label: str
    views: AggregateView
    watch: AggregateView
    ctr: AggregateView
    retention: AggregateView
    coverage_text: str

    @property
    def views_text(self) -> str:
        return self.views.text or _EMPTY

    @property
    def ctr_text(self) -> str:
        return self.ctr.text or _EMPTY

    @property
    def retention_text(self) -> str:
        return self.retention.text or _EMPTY


@dataclass(frozen=True)
class ObservationView:
    observation_id: str
    label: str
    value_text: str
    source_label: str
    window_text: str
    measured: bool


@dataclass(frozen=True)
class HypothesisView:
    statement: str
    support_label: str
    evidence_text: str


@dataclass(frozen=True)
class InsightView:
    insight_id: str
    title: str
    confidence_label: str
    confidence_basis: str
    declared_by: str
    observations: tuple[ObservationView, ...]
    hypotheses: tuple[HypothesisView, ...]


@dataclass(frozen=True)
class RecommendationView:
    recommendation_id: str
    kind_label: str
    statement: str
    rationale: str
    evidence_text: str
    evidence_ids: tuple[str, ...]
    confidence_label: str
    confidence_basis: str
    status: str
    status_label: str
    decided_by: str | None
    requires_human_review: bool = True
    auto_applied: bool = False


@dataclass(frozen=True)
class ExperimentView:
    experiment_id: str
    kind_label: str
    status_label: str
    variants_text: str
    window_text: str
    conclusion_text: str
    confidence_label: str | None
    approved_by: str
    platform_note: str
    platform_ab_supported: bool


@dataclass(frozen=True)
class AnalyticsDashboardView:
    project_id: str
    project_name: str
    period: AnalyticsPeriod
    generated_at: datetime
    selected_video_id: str | None
    selected_pillar_id: str | None
    projects: tuple[VideoOption, ...]
    videos: tuple[VideoOption, ...]
    pillars: tuple[VideoOption, ...]
    tiles: tuple[Tile, ...]
    video_rows: tuple[VideoMetricsView, ...]
    pillar_rows: tuple[PillarMetricsView, ...]
    insights: tuple[InsightView, ...]
    recommendations: tuple[RecommendationView, ...]
    experiments: tuple[ExperimentView, ...]
    readiness: CollectionReadiness
    last_collected_at: datetime | None
    has_measurements: bool
    insufficient_sample: bool
    notes: tuple[str, ...]
    observation_ids: tuple[str, ...]
    experiment_ids: tuple[str, ...]
    scope_text: str
    channel_text: str

    @property
    def last_collected_text(self) -> str:
        if self.last_collected_at is None:
            return "nunca"
        return self.last_collected_at.strftime("%d/%m/%Y %H:%M")

    @property
    def period_label(self) -> str:
        return f"{self.period.days} dias"


@dataclass
class _Group:
    format: str
    pillar_name: str | None
    rows: list[StoredMetric] = field(default_factory=list)


def _dedupe(rows: list[StoredMetric]) -> list[StoredMetric]:
    """Uma medição por (vídeo, métrica): fica a coleta mais recente."""
    latest: dict[tuple[str, str], StoredMetric] = {}
    for row in rows:
        key = (row.measurement.attribution.video_id, row.measurement.metric)
        current = latest.get(key)
        if current is None:
            latest[key] = row
            continue
        if row.measurement.observation.collected_at > current.measurement.observation.collected_at:
            latest[key] = row
        elif (row.measurement.observation.collected_at == current.measurement.observation.collected_at
              and row.measurement.origin == "youtube_analytics_api"):
            latest[key] = row
    return list(latest.values())


def _absence_reason(readiness: CollectionReadiness) -> str:
    if not readiness.channel_connected:
        return "canal YouTube não conectado: OAuth ausente ou expirado"
    if not readiness.scope_granted:
        return "escopo yt-analytics.readonly não concedido para este canal"
    if not readiness.publication_available:
        return "nenhuma publicação coletada ainda neste canal"
    return "nenhuma medição autorizada na janela selecionada"


def _attribution_text(measurement: MetricMeasurement) -> str:
    parts: list[str] = []
    attribution = measurement.attribution
    parts.append(f"Roteiro v{attribution.script_version}" if attribution.script_version
                 else "Roteiro não registrado")
    parts.append("Briefing registrado" if attribution.brief_version else "Briefing não registrado")
    parts.append("Embalagem registrada" if attribution.packaging_version
                 else "Embalagem não registrada")
    parts.append("Publicação registrada" if attribution.publication_id
                 else "Publicação não registrada")
    return " · ".join(parts)


def _cell(metric: str, rows: list[StoredMetric]) -> Cell:
    aggregate = aggregate_metric([row.measurement for row in rows], metric)
    return Cell(metric=metric, label=METRIC_LABELS[metric], state=aggregate.state,
                text=format_metric(metric, aggregate.value), why=aggregate.reason,
                origin_label=origin_label(aggregate.origin))


def _observation_view(row: StoredMetric) -> ObservationView:
    observation = row.measurement.observation
    value_text = format_metric(metric=observation.metric, value=observation.value)
    window = f"{_date(observation.window.start_at)} a {_date(observation.window.end_at)}"
    return ObservationView(
        observation_id=observation.observation_id,
        label=METRIC_LABELS.get(observation.metric, observation.metric),
        value_text=value_text or (observation.unavailable_reason or _EMPTY),
        source_label=observation.source,
        window_text=window,
        measured=observation.is_measured,
    )


_CONFIDENCE_LABELS = {"low": "baixa", "medium": "média", "high": "alta"}
_STATUS_LABELS = {"proposed": "proposta", "accepted_for_review": "aceita para revisão",
                  "rejected": "recusada"}
_KIND_LABELS = {"theme": "Tema", "format": "Formato", "hook": "Hook", "pacing": "Pacing"}
_EXPERIMENT_KIND = {"thumbnail": "Thumbnail", "title": "Título"}
_EXPERIMENT_STATUS = {"planned": "Planejado", "running": "Em andamento",
                      "finished": "Concluído", "abandoned": "Abandonado"}


def _recommendation_id(*parts: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, "studio-analytics|" + "|".join(parts)).hex


def _propose(rows: list[StoredMetric], period: AnalyticsPeriod,
             project_id: str) -> tuple[tuple[AnalyticsLearningBundle, ...], bool]:
    """Gera propostas só com amostra mínima; devolve também se a amostra foi insuficiente."""
    groups: dict[tuple[str, str | None], _Group] = {}
    for row in rows:
        key = (row.format, row.pillar_name)
        groups.setdefault(key, _Group(format=row.format, pillar_name=row.pillar_name)).rows.append(row)

    bundles: list[AnalyticsLearningBundle] = []
    for (format_name, pillar_name), group in groups.items():
        views_rows = [row for row in group.rows if row.measurement.metric == "views"
                      and row.measurement.is_measured]
        video_ids = {row.measurement.attribution.video_id for row in views_rows}
        if len(video_ids) < MINIMUM_SAMPLE:
            continue
        views_agg = aggregate_metric([row.measurement for row in group.rows], "views")
        if views_agg.state != "measured":
            continue
        format_label = FORMAT_LABELS[format_name]
        # O id precisa ser estável entre recarregamentos da mesma janela: a borda do período
        # (now) muda a cada request, então usamos a janela real das observações.
        observed_start = min(row.measurement.observation.window.start_at for row in views_rows)
        observed_end = max(row.measurement.observation.window.end_at for row in views_rows)
        confidence = ConfidenceDeclaration(
            level="low",
            basis=(f"{len(video_ids)} vídeos comparáveis em uma janela; "
                   "sem grupo de controle de idade, tema ou impressões"),
            declared_by="Studio (regra de análise)",
        )
        subject = f"pilar {pillar_name}" if pillar_name else f"formato {format_label}"
        insight_id = _recommendation_id("insight", observed_start.isoformat(),
                                        observed_end.isoformat(), format_name,
                                        pillar_name or "")
        hypothesis = InsightHypothesis(
            hypothesis_id=f"h-{insight_id[:28]}",
            statement=(
                f"O {subject} parece concentrar o volume de visualizações do formato "
                f"{format_label} nesta janela."
            ),
            support="supported",
            observation_ids=tuple(row.measurement.observation.observation_id for row in views_rows),
        )
        insight = LearningInsight(
            insight_id=insight_id,
            title=f"Views por pilar e formato · {period.days} dias",
            observations=tuple(row.measurement.observation for row in views_rows),
            confidence=confidence,
            hypotheses=(hypothesis,),
        )
        if pillar_name:
            kind: RecommendationKind = "theme"
            statement = f"Avaliar o pilar {pillar_name} no próximo briefing ({format_label})."
            target = "pillars"
            rationale = ("Maior volume de views medidas no recorte; correlação descritiva, "
                         "não causalidade. A janela não controla idade, tema nem impressões.")
        else:
            kind = "format"
            statement = f"Avaliar manter o formato {format_label} nas próximas produções."
            target = "target_duration_s"
            rationale = ("Vídeos comparáveis do mesmo formato com views medidas na janela. "
                         "Short e long-form não entram na mesma média.")
        evidence = tuple(row.measurement.observation.observation_id for row in views_rows)
        recommendation = ThemeFormatRecommendation(
            recommendation_id=_recommendation_id("recommendation", observed_start.isoformat(),
                                                 observed_end.isoformat(), kind,
                                                 pillar_name or format_name, statement),
            project_id=project_id,
            kind=kind,
            statement=statement,
            rationale=rationale,
            evidence=evidence,
            confidence=confidence,
            target_profile_field=target,
        )
        bundles.append(AnalyticsLearningBundle(insight=insight, recommendations=(recommendation,)))
    return tuple(bundles), not bundles


class BuildAnalyticsDashboard:
    def __init__(self, repo: AnalyticsRepository,
                 clock=lambda: datetime.now(timezone.utc)):
        self.repo = repo
        self.clock = clock

    def execute(self, query: DashboardQuery) -> AnalyticsDashboardView:
        project_name = self.repo.project_name(query.project_id)
        if not project_name:
            raise ProjectNotFound(query.project_id)
        videos = self.repo.videos(query.project_id)
        if query.video_id is not None and not any(v.id == query.video_id for v in videos):
            raise AnalyticsFilterNotFound(f"video {query.video_id!r} not in project")
        if query.pillar_id is not None and not any(
                pid == query.pillar_id for pid, _ in self.repo.pillars(query.project_id)):
            raise AnalyticsFilterNotFound(f"pillar {query.pillar_id!r} not in project")

        rows = _dedupe(self.repo.observations(
            project_id=query.project_id,
            start=query.period.start_at,
            end=query.period.end_at,
            video_id=query.video_id,
            pillar_id=query.pillar_id,
        ))
        channel = self.repo.channel_state(query.project_id)
        last = self.repo.last_collected_at(query.project_id)
        pillars = self.repo.pillars(query.project_id)
        experiments = self.repo.experiments(query.project_id)
        decisions = {item.recommendation_id: item for item in self.repo.decisions(query.project_id)}

        selected = next((v for v in videos if v.id == query.video_id), None)
        publication_available = bool(
            (selected.publication_id and selected.youtube_video_id) if selected
            else any(v.publication_id and v.youtube_video_id for v in videos)
        )
        reasons: list[str] = []
        if not channel.connected:
            reasons.append("canal YouTube não conectado: OAuth ausente ou expirado")
        if "yt-analytics.readonly" not in channel.scopes:
            reasons.append("escopo yt-analytics.readonly não concedido para este canal")
        if not publication_available:
            reasons.append("nenhuma publicação coletada ainda neste canal")
        readiness = CollectionReadiness(
            channel_connected=channel.connected,
            scope_granted="yt-analytics.readonly" in channel.scopes,
            publication_available=publication_available,
            reasons=tuple(reasons),
        )

        published = [
            video for video in videos
            if video.publication_id and video.youtube_video_id
            and video.created_at <= query.period.end_at
            and (query.video_id is None or video.id == query.video_id)
        ]
        expected_by_format = {
            format_name: sum(1 for video in published if video.format == format_name)
            for format_name in ("long", "short")
        }
        tiles = self._tiles(rows, readiness, expected_by_format)
        video_rows = self._video_rows(rows)
        pillar_rows = self._pillar_rows(rows)
        bundles, insufficient = _propose(rows, query.period, query.project_id)
        insights = tuple(self._insight_view(bundle.insight) for bundle in bundles)
        recommendations = tuple(
            self._recommendation_view(recommendation, decisions.get(recommendation.recommendation_id))
            for bundle in bundles for recommendation in bundle.recommendations
        )
        experiment_views = tuple(self._experiment_view(item) for item in experiments)

        notes: list[str] = []
        if insufficient:
            notes.append(
                f"Amostra insuficiente para recomendação: são necessários ao menos "
                f"{MINIMUM_SAMPLE} vídeos comparáveis por pilar e formato. Nenhuma sugestão é gerada."
            )
        notes.append("Short e long-form não entram na mesma média; taxa não é somada entre vídeos.")

        return AnalyticsDashboardView(
            project_id=query.project_id,
            project_name=project_name,
            period=query.period,
            generated_at=self.clock(),
            selected_video_id=query.video_id,
            selected_pillar_id=query.pillar_id,
            projects=tuple(VideoOption(pid, name) for pid, name in self.repo.projects()),
            videos=tuple(VideoOption(v.id, v.topic) for v in videos),
            pillars=tuple(VideoOption(pid, name) for pid, name in pillars),
            tiles=tiles,
            video_rows=video_rows,
            pillar_rows=pillar_rows,
            insights=insights,
            recommendations=recommendations,
            experiments=experiment_views,
            readiness=readiness,
            last_collected_at=last,
            has_measurements=bool(rows),
            insufficient_sample=insufficient,
            notes=tuple(notes),
            observation_ids=tuple(sorted(row.measurement.observation.observation_id for row in rows)),
            experiment_ids=tuple(item.experiment_id for item in experiments),
            scope_text="concedido" if "yt-analytics.readonly" in channel.scopes else "não concedido",
            channel_text="conectado" if channel.connected else "não conectado",
        )

    # -- tiles ---------------------------------------------------------------------------

    def _tiles(self, rows: list[StoredMetric], readiness: CollectionReadiness,
               expected_by_format: dict[str, int]) -> tuple[Tile, ...]:
        tiles: list[Tile] = []
        for metric in TILE_METRICS:
            groups: list[TileGroup] = []
            for format_name in ("long", "short"):
                subset = [row for row in rows if row.format == format_name]
                aggregate = aggregate_metric([row.measurement for row in subset], metric,
                                             expected_videos=expected_by_format.get(format_name, 0))
                if aggregate.coverage == (0, 0):
                    continue
                groups.append(TileGroup(
                    comparison=format_name,
                    label=FORMAT_LABELS[format_name],
                    state=aggregate.state,
                    text=format_metric(metric, aggregate.value),
                    why=aggregate.reason,
                    origin_label=origin_label(aggregate.origin),
                    coverage_text=(f"{aggregate.coverage[0]} de {aggregate.coverage[1]} vídeos"),
                ))
            tiles.append(Tile(metric=metric, label=METRIC_LABELS[metric],
                              groups=tuple(groups),
                              why="" if groups else _absence_reason(readiness)))
        return tuple(tiles)

    # -- vídeos --------------------------------------------------------------------------

    def _video_rows(self, rows: list[StoredMetric]) -> tuple[VideoMetricsView, ...]:
        by_video: dict[str, list[StoredMetric]] = {}
        for row in rows:
            by_video.setdefault(row.measurement.attribution.video_id, []).append(row)
        result: list[VideoMetricsView] = []
        for video_id, group in by_video.items():
            first = group[0]
            cells = tuple(_cell(metric, group) for metric in TILE_METRICS)
            origins = {row.measurement.origin for row in group if row.measurement.is_measured}
            result.append(VideoMetricsView(
                video_id=video_id,
                topic=first.topic,
                format_label=FORMAT_LABELS.get(first.format, first.format),
                pillar_text=(f"Pilar: {first.pillar_name}" if first.pillar_name
                             else "Pilar não registrado"),
                attribution_text=_attribution_text(first.measurement),
                cells=cells,
                origin_label=(origin_label(next(iter(origins))) if len(origins) == 1
                              else origin_label("unknown_origin")),
                observation_ids=tuple(sorted(row.measurement.observation.observation_id
                                             for row in group)),
            ))
        result.sort(key=lambda item: item.topic)
        return tuple(result)

    # -- pilares -------------------------------------------------------------------------

    def _pillar_rows(self, rows: list[StoredMetric]) -> tuple[PillarMetricsView, ...]:
        groups: dict[tuple[str, str | None], list[StoredMetric]] = {}
        for row in rows:
            groups.setdefault((row.format, row.pillar_name), []).append(row)
        result = []
        for (format_name, pillar_name), group in groups.items():
            measurements = [row.measurement for row in group]
            expected = len({row.measurement.attribution.video_id for row in group})
            views = aggregate_view(aggregate_metric(measurements, "views",
                                                    expected_videos=expected))
            expected = len({row.measurement.attribution.video_id for row in group})
            result.append(PillarMetricsView(
                pillar_text=(f"Pilar: {pillar_name}" if pillar_name else "Pilar não registrado"),
                format_label=FORMAT_LABELS.get(format_name, format_name),
                views=views,
                watch=aggregate_view(aggregate_metric(
                    measurements, "estimated_minutes_watched", expected_videos=expected)),
                ctr=aggregate_view(aggregate_metric(measurements, "ctr",
                                                    expected_videos=expected)),
                retention=aggregate_view(aggregate_metric(
                    measurements, "average_view_percentage", expected_videos=expected)),
                coverage_text=views.coverage_text,
            ))
        result.sort(key=lambda item: (item.format_label, item.pillar_text))
        return tuple(result)

    # -- insights/recomendações ----------------------------------------------------------

    def _insight_view(self, insight: LearningInsight) -> InsightView:
        return InsightView(
            insight_id=insight.insight_id,
            title=insight.title,
            confidence_label=_CONFIDENCE_LABELS[insight.confidence.level],
            confidence_basis=insight.confidence.basis,
            declared_by=insight.confidence.declared_by,
            observations=tuple(_observation_view_from(item) for item in insight.observations),
            hypotheses=tuple(HypothesisView(
                statement=item.statement,
                support_label=("com evidência medida" if item.support == "supported"
                               else "sem evidência declarada"),
                evidence_text=(f"{len(item.observation_ids)} observação(ões) medida(s)"
                               if item.observation_ids else (item.no_evidence_reason or "")),
            ) for item in insight.hypotheses),
        )

    def _recommendation_view(self, recommendation: ThemeFormatRecommendation,
                             decision: RecommendationDecision | None) -> RecommendationView:
        status = decision.decision if decision else "proposed"
        return RecommendationView(
            recommendation_id=recommendation.recommendation_id,
            kind_label=_KIND_LABELS[recommendation.kind],
            statement=recommendation.statement,
            rationale=recommendation.rationale,
            evidence_text=f"{len(recommendation.evidence)} observação(ões) medida(s)",
            evidence_ids=recommendation.evidence,
            confidence_label=_CONFIDENCE_LABELS[recommendation.confidence.level],
            confidence_basis=recommendation.confidence.basis,
            status=status,
            status_label=_STATUS_LABELS[status],
            decided_by=decision.decided_by if decision else None,
        )

    def _experiment_view(self, experiment: ExperimentRecord) -> ExperimentView:
        window_text = (
            f"{_date(experiment.window.start_at)} a {_date(experiment.window.end_at)}"
            if experiment.window else "sem janela registrada"
        )
        variants = ", ".join(
            f"{variant.label} (controle)" if variant.is_control else variant.label
            for variant in experiment.variants
        )
        return ExperimentView(
            experiment_id=experiment.experiment_id,
            kind_label=_EXPERIMENT_KIND[experiment.kind],
            status_label=_EXPERIMENT_STATUS[experiment.status],
            variants_text=variants,
            window_text=window_text,
            conclusion_text=(experiment.conclusion.statement if experiment.conclusion
                             else "sem conclusão registrada"),
            confidence_label=(_CONFIDENCE_LABELS[experiment.conclusion.confidence.level]
                              if experiment.conclusion else None),
            approved_by=experiment.approved_by,
            platform_note=experiment.platform_note,
            platform_ab_supported=experiment.platform_ab_supported,
        )


def _observation_view_from(observation) -> ObservationView:
    window = f"{_date(observation.window.start_at)} a {_date(observation.window.end_at)}"
    return ObservationView(
        observation_id=observation.observation_id,
        label=METRIC_LABELS.get(observation.metric, observation.metric),
        value_text=format_metric(observation.metric, observation.value)
        or (observation.unavailable_reason or _EMPTY),
        source_label=observation.source,
        window_text=window,
        measured=observation.is_measured,
    )


class AnalyticsFilterNotFound(LookupError):
    """Vídeo/pilar do filtro não pertence ao projeto: 404, nunca recorte silencioso."""
