"""Contrato F9: métrica ligada à versão, origem honesta e recomendação que não aplica nada.

Os testes aqui são de contrato puro: não há banco, HTTP nem coleta. O que se prova é que o
domínio recusa estado incoerente — valor ausente tratado como zero, versão inventada, origem
"Global", recomendação autoaplicada e experimento A/B que o YouTube não oferece.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.studio.domain.analytics_learning import (
    ADDITIVE_METRICS,
    ANALYTICS_READONLY_SCOPE,
    AnalyticsLearningBundle,
    AnalyticsPeriod,
    CollectionReadiness,
    ExperimentConclusion,
    ExperimentRecord,
    ExperimentVariant,
    MetricAggregate,
    MetricMeasurement,
    MissingVersionLink,
    RATE_METRICS,
    RecommendationDecision,
    ThemeFormatRecommendation,
    VersionAttribution,
    aggregate_metric,
    origin_label,
)
from app.studio.domain.insight import (
    ConfidenceDeclaration,
    InsightHypothesis,
    InsightRecommendation,
    LearningInsight,
    MetricObservation,
    MetricWindow,
)

VIDEO = "a" * 32
PROJECT = "b" * 32
PUBLICATION = "c" * 32


def at(day=1, hour=0):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def window(days=7):
    start = at()
    return MetricWindow(start_at=start, end_at=start + timedelta(days=days))


def missing_all(**overrides):
    """Toda versão ausente precisa de motivo explícito: nada é inventado."""
    links = {
        "brief": "briefing ainda não é persistido nesta versão",
        "script": "nenhum roteiro persistido para este vídeo",
        "publication": "nenhuma publicação registrada para este vídeo",
        "youtube_video": "sem id remoto do YouTube enquanto F8 não existir",
        "packaging": "embalagem ainda não é persistida nesta versão",
    }
    links.update(overrides)
    return tuple(MissingVersionLink(kind=kind, reason=reason) for kind, reason in links.items())


def attribution(**overrides):
    values = {"video_id": VIDEO, "missing": missing_all()}
    values.update(overrides)
    return VersionAttribution(**values)


def observation(**overrides):
    values = {
        "observation_id": "obs-views",
        "metric": "views",
        "unit": "count",
        "window": window(),
        "source": "YouTube Analytics API",
        "collected_at": at(day=9),
        "state": "measured",
        "value": 1200.0,
    }
    values.update(overrides)
    return MetricObservation(**values)


def measurement(**overrides):
    values = {
        "observation": observation(),
        "origin": "youtube_analytics_api",
        "attribution": attribution(),
    }
    values.update(overrides)
    return MetricMeasurement(**values)


def test_every_absent_version_requires_an_explicit_reason():
    with pytest.raises(ValidationError, match="missing"):
        attribution(missing=missing_all()[:-1])


def test_attribution_rejects_a_reason_for_a_version_that_exists():
    with pytest.raises(ValidationError, match="missing"):
        attribution(script_version=2, missing=missing_all())


def test_attribution_accepts_versions_and_explains_only_the_absent_ones():
    missing = tuple(link for link in missing_all() if link.kind not in ("script", "publication", "youtube_video"))
    result = attribution(script_version=3, publication_id=PUBLICATION, youtube_video_id="AbCdEf12345",
                         missing=missing)
    assert result.script_version == 3
    assert result.is_complete is False  # brief/packaging ainda ausentes
    assert {link.kind for link in result.missing} == {"brief", "packaging"}


def test_remote_youtube_id_without_local_publication_is_refused():
    missing = tuple(link for link in missing_all() if link.kind != "youtube_video")
    with pytest.raises(ValidationError, match="publication"):
        attribution(youtube_video_id="AbCdEf12345", missing=missing)


def test_youtube_id_must_have_the_remote_format():
    missing = tuple(link for link in missing_all() if link.kind not in ("publication", "youtube_video"))
    with pytest.raises(ValidationError, match="youtube_video_id"):
        attribution(publication_id=PUBLICATION, youtube_video_id="curto", missing=missing)


def test_missing_links_cannot_repeat():
    duplicated = missing_all() + (MissingVersionLink(kind="brief", reason="outro motivo"),)
    with pytest.raises(ValidationError, match="missing"):
        attribution(missing=duplicated)


def test_origin_unknown_is_never_called_global():
    assert origin_label("unknown_origin") == "origem desconhecida"
    assert origin_label("youtube_analytics_api") == "API YouTube Analytics"
    with pytest.raises(ValueError):
        origin_label("Global")
    with pytest.raises(ValidationError):
        measurement(origin="global")


def test_measurement_metric_must_belong_to_the_analytics_contract():
    with pytest.raises(ValidationError, match="metric"):
        measurement(observation=observation(metric="faturamento_inventado"))


def test_measurement_unit_is_canonical_for_the_metric():
    with pytest.raises(ValidationError, match="unit"):
        measurement(observation=observation(metric="ctr", unit="count", value=4.1))


def test_percentage_metrics_are_bounded():
    with pytest.raises(ValidationError, match="ctr"):
        measurement(observation=observation(metric="ctr", unit="percent", value=180.0))


def test_measured_observation_keeps_zero_distinct_from_absence():
    zero = measurement(observation=observation(value=0.0))
    absent = measurement(observation=observation(state="not_yet_available", value=None,
                                                  unavailable_reason="a API não devolveu views"))
    assert zero.observation.value == 0.0
    assert zero.observation.is_measured
    assert absent.observation.value is None
    assert not absent.observation.is_measured


def test_unavailable_metric_from_the_api_still_requires_an_explicit_reason():
    # A origem é a API, mas o valor não veio: sem motivo, o estado mentiria que "não há dado".
    absent = measurement(observation=observation(state="not_yet_available", value=None,
                                                  unavailable_reason="a API não devolveu views"))
    assert absent.observation.unavailable_reason == "a API não devolveu views"
    with pytest.raises(ValidationError, match="unavailable_reason"):
        measurement(observation=observation(state="not_yet_available", value=None))


def test_collection_readiness_requires_a_reason_whenever_it_is_not_ready():
    with pytest.raises(ValidationError, match="reason"):
        CollectionReadiness(channel_connected=False, scope_granted=False, publication_available=False)
    ready = CollectionReadiness(channel_connected=True, scope_granted=True, publication_available=True)
    assert ready.is_ready is True
    assert ready.reasons == ()


def test_collection_readiness_lists_the_scope_it_needs():
    assert ANALYTICS_READONLY_SCOPE == "yt-analytics.readonly"
    ready = CollectionReadiness(channel_connected=True, scope_granted=True, publication_available=True)
    assert ready.scope == "yt-analytics.readonly"


def test_period_only_accepts_the_windows_the_screen_offers():
    assert AnalyticsPeriod(days=7, end_at=at(day=9)).start_at == at(day=2)
    for days in (1, 14, 30, 365):
        with pytest.raises(ValidationError):
            AnalyticsPeriod(days=days, end_at=at(day=9))


def test_period_end_must_be_an_aware_instant():
    with pytest.raises(ValidationError):
        AnalyticsPeriod(days=7, end_at=datetime(2026, 11, 9))


def test_additive_metric_sums_only_with_complete_coverage():
    rows = [
        measurement(observation=observation(observation_id="obs-a", value=10.0)),
        measurement(observation=observation(observation_id="obs-b", value=32.0),
                    attribution=attribution(video_id="b" * 32)),
    ]
    aggregate = aggregate_metric(rows, "views")
    assert isinstance(aggregate, MetricAggregate)
    assert aggregate.value == 42.0
    assert aggregate.coverage == (2, 2)
    assert aggregate.origin == "youtube_analytics_api"

    partial = rows + [
        measurement(observation=observation(observation_id="obs-c", state="not_yet_available",
                                            value=None, unavailable_reason="sem views na janela"),
                    attribution=attribution(video_id="c" * 32)),
    ]
    aggregate = aggregate_metric(partial, "views")
    assert aggregate.value is None
    assert aggregate.state == "not_yet_available"
    assert aggregate.coverage == (2, 3)
    assert "cobertura" in aggregate.reason


def test_additive_metric_refuses_mixed_origins_instead_of_claiming_one():
    mixed = [
        measurement(observation=observation(observation_id="obs-a", value=1.0)),
        measurement(observation=observation(observation_id="obs-b", value=2.0),
                    origin="unknown_origin", attribution=attribution(video_id="b" * 32)),
    ]
    aggregate = aggregate_metric(mixed, "views")
    assert aggregate.origin == "unknown_origin"


def test_rate_metric_is_not_averaged_across_videos():
    rows = [
        measurement(observation=observation(observation_id="obs-a", metric="ctr", unit="percent", value=4.0)),
        measurement(observation=observation(observation_id="obs-b", metric="ctr", unit="percent", value=8.0),
                    attribution=attribution(video_id="b" * 32)),
    ]
    aggregate = aggregate_metric(rows, "ctr")
    assert aggregate.value is None
    assert "não é agregada" in aggregate.reason
    single = aggregate_metric(rows[:1], "ctr")
    assert single.value == 4.0


def test_additive_and_rate_metric_sets_are_disjoint():
    assert ADDITIVE_METRICS.isdisjoint(RATE_METRICS)
    assert "views" in ADDITIVE_METRICS and "ctr" in RATE_METRICS


def test_experiment_history_refuses_a_platform_ab_claim_the_api_does_not_offer():
    variants = (ExperimentVariant(variant_id="controle", label="Thumbnail atual", is_control=True),
                ExperimentVariant(variant_id="b", label="Thumbnail com rosto", is_control=False))
    with pytest.raises(ValidationError, match="A/B|platform_ab_supported"):
        ExperimentRecord(experiment_id="exp-1", project_id=PROJECT, video_id=VIDEO, kind="thumbnail",
                         status="planned", variants=variants, approved_by="operador",
                         platform_note="rotação manual", platform_ab_supported=True)


def test_experiment_requires_exactly_one_control():
    variants = (ExperimentVariant(variant_id="a", label="A", is_control=True),
                ExperimentVariant(variant_id="b", label="B", is_control=True))
    with pytest.raises(ValidationError, match="controle"):
        ExperimentRecord(experiment_id="exp-1", project_id=PROJECT, video_id=VIDEO, kind="thumbnail",
                         status="planned", variants=variants, approved_by="operador",
                         platform_note="rotação manual")


def test_finished_experiment_requires_a_conclusion_bound_to_observations():
    variants = (ExperimentVariant(variant_id="controle", label="Atual", is_control=True),
                ExperimentVariant(variant_id="b", label="Nova", is_control=False))
    with pytest.raises(ValidationError, match="conclusão|conclusion"):
        ExperimentRecord(experiment_id="exp-1", project_id=PROJECT, video_id=VIDEO, kind="title",
                         status="finished", variants=variants, approved_by="operador",
                         platform_note="rotação manual", window=window())
    conclusion = ExperimentConclusion(
        statement="O título em pergunta não mostrou diferença mensurável nesta amostra.",
        confidence=ConfidenceDeclaration(level="low", basis="1 rotação, sem controle de período",
                                         declared_by="operador"),
        observation_ids=("obs-views",), concluded_at=at(day=9),
    )
    record = ExperimentRecord(experiment_id="exp-1", project_id=PROJECT, video_id=VIDEO, kind="title",
                              status="finished", variants=variants, approved_by="operador",
                              platform_note="rotação manual", window=window(), conclusion=conclusion)
    assert record.conclusion.statement.startswith("O título")
    assert record.conclusion.confidence.level == "low"


def test_recommendation_is_always_for_human_review_and_never_auto_applied():
    insight = LearningInsight(
        insight_id="i-1",
        title="Formato na janela",
        observations=(observation(),),
        confidence=ConfidenceDeclaration(level="low", basis="3 vídeos em uma janela",
                                         declared_by="Studio (regra de análise)"),
        hypotheses=(InsightHypothesis(hypothesis_id="h-1", statement="Formato longo reteve mais",
                                      support="supported", observation_ids=("obs-views",)),),
        recommendations=(InsightRecommendation(action="Revisar formato", rationale="evidência",
                                               hypothesis_ids=("h-1",)),),
    )
    recommendation = ThemeFormatRecommendation(
        recommendation_id="d" * 32, project_id=PROJECT, kind="format",
        statement="Avaliar manter o formato longo no próximo briefing.",
        rationale="Maior mediana de views na janela; correlação, não causalidade.",
        evidence=("obs-views",), confidence=insight.confidence,
        target_profile_field="target_duration_s",
    )
    bundle = AnalyticsLearningBundle(insight=insight, recommendations=(recommendation,))
    assert bundle.recommendations[0].requires_human_review is True
    assert bundle.recommendations[0].auto_applied is False
    with pytest.raises(ValidationError):
        ThemeFormatRecommendation(
            recommendation_id="d" * 32, project_id=PROJECT, kind="format",
            statement="Aplicar automaticamente", rationale="x", evidence=("obs-views",),
            confidence=insight.confidence, auto_applied=True,
        )


def test_recommendation_evidence_must_be_a_measured_observation_of_the_bundle():
    insight = LearningInsight(
        insight_id="i-1", title="t",
        observations=(observation(),),
        confidence=ConfidenceDeclaration(level="low", basis="b", declared_by="d"),
    )
    with pytest.raises(ValidationError, match="evidence|observa"):
        AnalyticsLearningBundle(
            insight=insight,
            recommendations=(ThemeFormatRecommendation(
                recommendation_id="d" * 32, project_id=PROJECT, kind="theme",
                statement="Explorar o pilar X", rationale="views", evidence=("obs-inexistente",),
                confidence=insight.confidence,
            ),),
        )


def test_decision_is_a_review_record_and_has_no_apply_state():
    decision = RecommendationDecision(recommendation_id="d" * 32, decision="accepted_for_review",
                                      decided_by="operador", decided_at=at(day=10))
    assert decision.decision == "accepted_for_review"
    with pytest.raises(ValidationError):
        RecommendationDecision(recommendation_id="d" * 32, decision="applied",
                               decided_by="operador", decided_at=at(day=10))