"""F9-01/03/05: dashboard por canal/vídeo/pilar/período com ausência explícita.

Tudo roda com repositório falso: o objetivo é provar as regras de honestidade do recorte —
Short e long-form nunca somados, taxa nunca vira média de médias, versão ausente declarada,
zero medido diferente de ausência, e recomendação só com amostra mínima e revisão humana.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.studio.application.analytics_dashboard import BuildAnalyticsDashboard
from app.studio.application.analytics_ports import (
    AnalyticsVideoInfo,
    ChannelAnalyticsState,
    StoredMetric,
)
from app.studio.application.errors import ProjectNotFound
from app.studio.domain.analytics_learning import (
    ANALYTICS_READONLY_SCOPE,
    AnalyticsPeriod,
    DashboardQuery,
    ExperimentConclusion,
    ExperimentRecord,
    ExperimentVariant,
    RecommendationDecision,
    VersionAttribution,
    MissingVersionLink,
)
from app.studio.domain.insight import MetricObservation, MetricWindow, ConfidenceDeclaration

PROJECT = "b" * 32
CHANNEL = "UC1234567890abcdefghij"
V1, V2, V3, V4 = "1" * 32, "2" * 32, "3" * 32, "4" * 32


def at(day=9, hour=12):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def window():
    start = at(2)
    return MetricWindow(start_at=start, end_at=at(9))


def attribution(video=V1, **overrides):
    missing = []
    values = {"video_id": video, "script_version": 1}
    values.update(overrides)
    absent = {
        "brief": values.get("brief_version") is None,
        "script": values.get("script_version") is None,
        "publication": values.get("publication_id") is None,
        "youtube_video": values.get("youtube_video_id") is None,
        "packaging": values.get("packaging_version") is None,
    }
    missing = tuple(MissingVersionLink(kind=kind, reason=f"{kind} não registrado")
                    for kind, is_absent in absent.items() if is_absent)
    return VersionAttribution(**values, missing=missing)


def stored(metric, value, *, video=V1, topic="Vídeo real", format="long", pillar="Finanças",
           origin="youtube_analytics_api", measured=True, collected=at(9),
           script_version=1, publication_id=None, youtube_video_id=None):
    if measured:
        observation = MetricObservation(
            observation_id=f"{video[:4]}-{metric}"[-32:].rjust(32, "0"),
            metric=metric,
            unit={"ctr": "percent", "average_view_percentage": "percent",
                  "average_view_duration_s": "seconds", "estimated_minutes_watched": "minutes"}.get(metric, "count"),
            window=window(), source="API YouTube Analytics", collected_at=collected,
            state="measured", value=value,
        )
    else:
        observation = MetricObservation(
            observation_id=f"{video[:4]}-{metric}"[-32:].rjust(32, "0"),
            metric=metric, unit="count", window=window(), source="API YouTube Analytics",
            collected_at=collected, state="not_yet_available", value=None,
            unavailable_reason="a API não devolveu esta métrica",
        )
    return StoredMetric(
        measurement=__import__("app.studio.domain.analytics_learning", fromlist=["MetricMeasurement"]).MetricMeasurement(
            observation=observation, origin=origin,
            attribution=attribution(video, script_version=script_version,
                                    publication_id=publication_id,
                                    youtube_video_id=youtube_video_id),
        ),
        topic=topic, format=format, pillar_name=pillar,
    )


def video_info(video=V1, **overrides):
    values = {
        "id": video, "project_id": PROJECT, "topic": "Vídeo real", "format": "long",
        "status": "PUBLISHED", "created_at": at(1), "updated_at": at(2),
        "script_version": 1, "publication_id": "a" * 32, "youtube_video_id": "AbCdEf12345",
        "publication_status": "UPLOADED",
    }
    values.update(overrides)
    return AnalyticsVideoInfo(**values)


class FakeRepo:
    def __init__(self, *, project="Canal Real", videos=(), rows=(), pillars=("Finanças",),
                 channel=None, last=None, experiments=(), decisions=()):
        self.name = project
        self._videos = list(videos) if videos else [video_info()]
        self.rows = list(rows)
        self._pillars = [(f"{i:032x}", name) for i, name in enumerate(pillars)]
        self.channel = channel or ChannelAnalyticsState(
            connected=True, channel_id=CHANNEL, scopes=(ANALYTICS_READONLY_SCOPE,),
            token_expires_at=None)
        self.last = last
        self._experiments = list(experiments)
        self._decisions = list(decisions)
        self.saved_decisions = []

    def projects(self):
        return [(PROJECT, self.name or "Canal Real")]

    def project_name(self, project_id):
        return self.name

    def videos(self, project_id):
        return list(self._videos)

    def video(self, video_id):
        return next((v for v in self._videos if v.id == video_id), None)

    def pillars(self, project_id):
        return list(self._pillars)

    def channel_state(self, project_id):
        return self.channel

    def observations(self, *, project_id, start, end, video_id=None, pillar_id=None):
        rows = [row for row in self.rows
                if row.measurement.observation.window.start_at >= start
                and row.measurement.observation.window.end_at <= end]
        if video_id:
            rows = [row for row in rows if row.measurement.attribution.video_id == video_id]
        return rows

    def last_collected_at(self, project_id):
        return self.last

    def save_measurements(self, project_id, rows):
        raise AssertionError("dashboard não grava")

    def experiments(self, project_id):
        return list(self._experiments)

    def save_experiment(self, experiment):
        raise AssertionError("dashboard não grava")

    def decisions(self, project_id):
        return list(self._decisions)

    def save_decision(self, project_id, decision):
        raise AssertionError("dashboard não grava")


def build(repo, *, days=7, video_id=None, pillar_id=None, clock=None):
    return BuildAnalyticsDashboard(repo, clock=clock or (lambda: at(9))).execute(
        DashboardQuery(project_id=PROJECT, video_id=video_id, pillar_id=pillar_id,
                       period=AnalyticsPeriod(days=days, end_at=at(9))))


def tile(view, metric):
    return next(item for item in view.tiles if item.metric == metric)


def test_unknown_project_raises_project_not_found():
    with pytest.raises(ProjectNotFound):
        BuildAnalyticsDashboard(FakeRepo(project=None), clock=lambda: at(9)).execute(
            DashboardQuery(project_id=PROJECT,
                           period=AnalyticsPeriod(days=7, end_at=at(9))))


def test_empty_channel_is_explicitly_unavailable_and_never_zero():
    view = build(FakeRepo(rows=()))
    assert view.has_measurements is False
    for metric in ("views", "ctr", "average_view_percentage", "estimated_minutes_watched"):
        item = tile(view, metric)
        assert item.groups
        assert all(group.state == "not_yet_available" for group in item.groups)
        assert all(group.text is None for group in item.groups)
        assert all(group.why for group in item.groups)
    assert view.last_collected_at is None
    assert view.readiness.is_ready is True
    assert view.insights == ()
    assert view.recommendations == ()
    assert view.insufficient_sample is True


def test_single_video_shows_real_metric_tiles_with_origin_and_period():
    rows = [stored("views", 1200.0), stored("ctr", 4.8), stored("average_view_percentage", 41.2),
            stored("estimated_minutes_watched", 318.0)]
    view = build(FakeRepo(rows=rows))
    views = tile(view, "views")
    assert len(views.groups) == 1
    group = views.groups[0]
    assert group.comparison == "long"
    assert group.state == "measured"
    assert "1.200" in group.text
    assert group.origin_label == "API YouTube Analytics"
    assert tile(view, "ctr").groups[0].text == "4,8%"
    assert tile(view, "average_view_percentage").groups[0].text == "41,2%"
    assert "5,3 h" in tile(view, "estimated_minutes_watched").groups[0].text
    assert view.has_measurements is True


def test_zero_measured_is_shown_as_zero_not_as_absence():
    views = tile(build(FakeRepo(rows=[stored("views", 0.0)])), "views").groups[0]
    assert views.state == "measured"
    assert views.text == "0"


def test_absent_value_keeps_the_explicit_reason():
    rows = [stored("views", None, measured=False)]
    group = tile(build(FakeRepo(rows=rows)), "views").groups[0]
    assert group.state == "not_yet_available"
    assert group.text is None
    assert "não devolveu" in group.why


def test_ctr_is_not_averaged_between_two_videos():
    rows = [stored("ctr", 4.0, video=V1), stored("ctr", 8.0, video=V2)]
    group = tile(build(FakeRepo(rows=rows, videos=[video_info(V1), video_info(V2)])), "ctr").groups[0]
    assert group.state == "not_yet_available"
    assert "não é agregada" in group.why
    assert group.text is None


def test_views_sum_only_with_complete_coverage():
    complete = [stored("views", 10.0, video=V1), stored("views", 32.0, video=V2)]
    group = tile(build(FakeRepo(rows=complete, videos=[video_info(V1), video_info(V2)])), "views").groups[0]
    assert group.text == "42"

    incomplete = complete + [stored("views", None, video=V3, measured=False)]
    group = tile(build(FakeRepo(rows=incomplete, videos=[video_info(v) for v in (V1, V2, V3)])), "views").groups[0]
    assert group.state == "not_yet_available"
    assert "cobertura" in group.why


def test_short_and_long_are_never_summed_in_one_number():
    rows = [stored("views", 100.0, video=V1, format="long"),
            stored("views", 900.0, video=V2, format="short")]
    groups = tile(build(FakeRepo(rows=rows, videos=[video_info(V1), video_info(V2, format="short")])), "views").groups
    assert {group.comparison for group in groups} == {"long", "short"}
    assert sorted(group.text for group in groups) == ["100", "900"]


def test_mixed_origin_is_labelled_unknown_never_global():
    rows = [stored("views", 1.0, video=V1), stored("views", 2.0, video=V2, origin="unknown_origin")]
    group = tile(build(FakeRepo(rows=rows, videos=[video_info(V1), video_info(V2)])), "views").groups[0]
    assert group.origin_label == "origem desconhecida"
    assert "Global" not in " ".join(str(group))


def test_video_rows_show_version_attribution_or_its_absence():
    rows = [stored("views", 10.0, script_version=3)]
    view = build(FakeRepo(rows=rows))
    row = view.video_rows[0]
    assert row.topic == "Vídeo real"
    assert "Roteiro v3" in row.attribution_text
    assert "Briefing não registrado" in row.attribution_text
    assert "Embalagem não registrada" in row.attribution_text
    assert row.pillar_text == "Pilar: Finanças"
    assert row.cells


def test_pillar_grouping_respects_format_and_reports_coverage():
    rows = [stored("views", 10.0, video=V1, format="long"),
            stored("views", 20.0, video=V2, format="long"),
            stored("views", 90.0, video=V3, format="short")]
    view = build(FakeRepo(rows=rows, videos=[video_info(V1), video_info(V2), video_info(V3, format="short")]))
    assert len(view.pillar_rows) == 2
    groups = {row.format_label for row in view.pillar_rows}
    assert groups == {"Long-form", "Short"}
    long_row = next(row for row in view.pillar_rows if row.format_label == "Long-form")
    assert "30" in long_row.views_text
    assert "2 de 2" in long_row.coverage_text


def test_three_comparable_videos_generate_a_low_confidence_recommendation():
    rows = [stored("views", 100.0, video=v) for v in (V1, V2, V3)]
    view = build(FakeRepo(rows=rows, videos=[video_info(v) for v in (V1, V2, V3)]))
    assert view.insufficient_sample is False
    assert len(view.insights) == 1
    insight = view.insights[0]
    assert insight.confidence_label == "baixa"
    assert insight.observations and insight.hypotheses
    assert len(view.recommendations) == 1
    recommendation = view.recommendations[0]
    assert recommendation.requires_human_review is True
    assert recommendation.auto_applied is False
    assert recommendation.status == "proposed"
    assert "Avaliar" in recommendation.statement
    assert recommendation.evidence_ids


def test_two_videos_are_not_enough_for_a_recommendation():
    rows = [stored("views", 100.0, video=v) for v in (V1, V2)]
    view = build(FakeRepo(rows=rows, videos=[video_info(v) for v in (V1, V2)]))
    assert view.insufficient_sample is True
    assert view.recommendations == ()
    assert view.insights == ()


def test_a_recorded_decision_is_shown_and_does_not_apply_anything():
    rows = [stored("views", 100.0, video=v) for v in (V1, V2, V3)]
    first = build(FakeRepo(rows=rows, videos=[video_info(v) for v in (V1, V2, V3)]))
    recommendation = first.recommendations[0]
    decision = RecommendationDecision(recommendation_id=recommendation.recommendation_id,
                                      decision="rejected", decided_by="operador", decided_at=at(10))
    view = build(FakeRepo(rows=rows, videos=[video_info(v) for v in (V1, V2, V3)],
                          decisions=[decision]))
    assert view.recommendations[0].status == "rejected"
    assert view.recommendations[0].status_label == "recusada"
    assert view.recommendations[0].auto_applied is False


def test_experiment_history_maps_status_and_conclusion_without_claiming_platform_ab():
    variants = (ExperimentVariant(variant_id="controle", label="Thumbnail atual", is_control=True),
                ExperimentVariant(variant_id="b", label="Thumbnail com número", is_control=False))
    conclusion = ExperimentConclusion(
        statement="Diferença não mensurável nesta amostra.",
        confidence=ConfidenceDeclaration(level="low", basis="1 rotação", declared_by="operador"),
        observation_ids=("obs-1",), concluded_at=at(9),
    )
    experiment = ExperimentRecord(
        experiment_id="e" * 32, project_id=PROJECT, video_id=V1, kind="thumbnail",
        status="finished", variants=variants, approved_by="operador",
        platform_note="A API do YouTube não expõe A/B; rotação manual aprovada.",
        window=window(), conclusion=conclusion,
    )
    view = build(FakeRepo(experiments=[experiment]))
    assert len(view.experiments) == 1
    item = view.experiments[0]
    assert item.kind_label == "Thumbnail"
    assert item.status_label == "Concluído"
    assert "controle" in item.variants_text
    assert "Diferença não mensurável" in item.conclusion_text
    assert "não expõe A/B" in item.platform_note


def test_readiness_reports_the_scope_rail_honestly():
    repo = FakeRepo(channel=ChannelAnalyticsState(
        connected=True, channel_id=CHANNEL, scopes=(), token_expires_at=None))
    view = build(repo)
    assert view.readiness.is_ready is False
    assert any("yt-analytics.readonly" in reason for reason in view.readiness.reasons)
    assert view.scope_text == "não concedido"


def test_video_filter_narrows_the_dashboard_and_rejects_foreign_video():
    rows = [stored("views", 10.0, video=V1), stored("views", 20.0, video=V2)]
    view = build(FakeRepo(rows=rows, videos=[video_info(V1), video_info(V2)]), video_id=V1)
    assert len(view.video_rows) == 1 and view.video_rows[0].video_id == V1
    with pytest.raises(Exception, match="video"):
        build(FakeRepo(rows=rows, videos=[video_info(V1)]), video_id=V2)


def test_observations_are_deduplicated_by_latest_collection():
    older = stored("views", 5.0, video=V1, collected=at(8))
    newer = stored("views", 7.0, video=V1, collected=at(9))
    # o id determinístico é o mesmo: repositório devolve as duas versões da mesma medição
    newer = StoredMetric(newer.measurement, newer.topic, newer.format, newer.pillar_name)
    view = build(FakeRepo(rows=[older, newer]))
    assert "7" in tile(view, "views").groups[0].text

def test_rate_with_partial_coverage_does_not_hide_behind_one_of_one():
    rows = [stored("views", 10.0, video=v) for v in (V1, V2, V3)]
    rows.append(stored("ctr", 4.8, video=V1))
    group = tile(build(FakeRepo(rows=rows, videos=[video_info(v) for v in (V1, V2, V3)])),
                 "ctr").groups[0]
    assert group.state == "not_yet_available"
    assert group.text is None
    assert group.coverage_text == "1 de 3 vídeos"
    assert "não é agregada" in group.why
