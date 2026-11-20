"""Contrato de insight: observação não é hipótese, zero não é ausência de dado."""

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.studio.domain.insight import (
    ConfidenceDeclaration,
    InsightHypothesis,
    InsightRecommendation,
    LearningInsight,
    MetricObservation,
    MetricWindow,
)


def at(year=2026, month=1, day=1):
    return datetime(year, month, day, tzinfo=timezone.utc)


def window(**changes):
    values = {"start_at": at(day=1), "end_at": at(day=8)}
    values.update(changes)
    return MetricWindow(**values)


def observation(**changes):
    values = {
        "observation_id": "obs-views",
        "metric": "views",
        "unit": "count",
        "window": window(),
        "source": "YouTube Analytics",
        "collected_at": at(day=9),
        "state": "measured",
        "value": 1200.0,
    }
    values.update(changes)
    return MetricObservation(**values)


def missing_observation(**changes):
    values = {
        "observation_id": "obs-ctr",
        "metric": "impressions_ctr",
        "unit": "ratio",
        "window": window(),
        "source": "YouTube Analytics",
        "collected_at": at(day=9),
        "state": "not_yet_available",
        "value": None,
        "unavailable_reason": "A API ainda não publicou a janela solicitada",
    }
    values.update(changes)
    return MetricObservation(**values)


def confidence(**changes):
    values = {
        "level": "medium",
        "basis": "Amostra semanal declarada pelo produtor, sem teste estatístico",
        "declared_by": "editorial-agent",
    }
    values.update(changes)
    return ConfidenceDeclaration(**values)


def hypothesis(**changes):
    values = {
        "hypothesis_id": "hyp-1",
        "statement": "Hooks mais diretos podem aumentar a retenção inicial",
        "support": "supported",
        "observation_ids": ("obs-views",),
    }
    values.update(changes)
    return InsightHypothesis(**values)


def recommendation(**changes):
    values = {
        "action": "Revisar o hook dos próximos dois vídeos",
        "rationale": "A hipótese sugere testar a abertura antes de reconfigurar o canal",
        "hypothesis_ids": ("hyp-1",),
    }
    values.update(changes)
    return InsightRecommendation(**values)


def insight(**changes):
    values = {
        "insight_id": "insight-1",
        "title": "Abertura e retenção inicial",
        "observations": (observation(),),
        "confidence": confidence(),
        "hypotheses": (hypothesis(),),
        "recommendations": (recommendation(),),
    }
    values.update(changes)
    return LearningInsight(**values)


def test_valid_observation_keeps_metric_window_source_and_collection_time():
    result = observation()

    assert result.schema_version == 1
    assert result.metric == "views"
    assert result.unit == "count"
    assert result.window.start_at == at(day=1)
    assert result.window.end_at == at(day=8)
    assert result.source == "YouTube Analytics"
    assert result.collected_at == at(day=9)
    assert result.state == "measured"
    assert result.value == 1200.0
    assert result.is_measured is True
    assert result.unavailable_reason is None


def test_zero_measured_and_not_yet_available_are_distinct_states():
    zero = observation(value=0.0)
    absent = missing_observation()

    assert zero.value == 0.0
    assert zero.value is not None
    assert absent.value is None
    assert absent.value != 0.0
    assert zero.is_measured is True
    assert absent.is_measured is False
    assert zero != absent
    assert zero.model_dump() != absent.model_dump()
    assert zero.model_dump()["state"] == "measured"
    assert absent.model_dump()["state"] == "not_yet_available"
    assert absent.model_dump()["unavailable_reason"] == "A API ainda não publicou a janela solicitada"
    assert zero.model_dump()["unavailable_reason"] is None


def test_not_yet_available_cannot_carry_zero_or_any_value():
    for value in (0, 0.0, 1.0):
        with pytest.raises(ValidationError):
            missing_observation(value=value)


def test_measured_requires_a_finite_value():
    with pytest.raises(ValidationError):
        observation(value=None)


def test_unavailable_requires_an_explicit_reason():
    with pytest.raises(ValidationError):
        missing_observation(unavailable_reason=None)
    with pytest.raises(ValidationError):
        missing_observation(unavailable_reason="   ")


def test_measured_cannot_declare_an_unavailable_reason():
    with pytest.raises(ValidationError):
        observation(unavailable_reason="medido, mas com motivo de ausência")


def test_hypothesis_without_supporting_observation_is_rejected():
    with pytest.raises(ValidationError):
        hypothesis(observation_ids=())


def test_hypothesis_may_declare_absence_of_evidence_explicitly():
    result = hypothesis(
        support="no_evidence_declared",
        observation_ids=(),
        no_evidence_reason="Ainda não há métrica coletada para esta janela",
    )

    assert result.support == "no_evidence_declared"
    assert result.observation_ids == ()
    assert result.verification == "unverified"


def test_absence_of_evidence_requires_reason_and_no_references():
    with pytest.raises(ValidationError):
        hypothesis(support="no_evidence_declared", observation_ids=())
    with pytest.raises(ValidationError):
        hypothesis(
            support="no_evidence_declared",
            observation_ids=("obs-views",),
            no_evidence_reason="declaração contraditória",
        )


def test_supported_hypothesis_cannot_also_declare_absence_reason():
    with pytest.raises(ValidationError):
        hypothesis(no_evidence_reason="suporte e ausência ao mesmo tempo")


def test_hypothesis_cannot_claim_verification():
    with pytest.raises(ValidationError):
        hypothesis(verification="verified")


def test_hypothesis_cannot_reference_an_unavailable_observation():
    with pytest.raises(ValidationError):
        insight(
            observations=(observation(), missing_observation()),
            hypotheses=(
                hypothesis(observation_ids=("obs-ctr",)),
                hypothesis(hypothesis_id="hyp-2"),
            ),
            recommendations=(recommendation(),),
        )


def test_hypothesis_cannot_reference_an_unknown_observation():
    with pytest.raises(ValidationError):
        insight(hypotheses=(hypothesis(observation_ids=("obs-unknown",)),))


@pytest.mark.parametrize(
    "start,end",
    [
        (at(day=8), at(day=8)),
        (at(day=9), at(day=8)),
    ],
)
def test_window_must_have_start_before_end(start, end):
    with pytest.raises(ValidationError):
        window(start_at=start, end_at=end)


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 1, 1), at(day=8)),
        (at(day=1), datetime(2026, 1, 8)),
        (math.nan, at(day=8)),
        (at(day=1), math.inf),
        (-math.inf, at(day=8)),
        (None, at(day=8)),
        ("2026-01-01", at(day=8)),
    ],
)
def test_window_rejects_naive_or_non_finite_instants(start, end):
    with pytest.raises(ValidationError):
        window(start_at=start, end_at=end)


def test_collected_at_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        observation(collected_at=datetime(2026, 1, 9))
    with pytest.raises(ValidationError):
        observation(collected_at=math.nan)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1200", None])
def test_measured_values_must_be_finite_numbers(value):
    with pytest.raises(ValidationError):
        observation(value=value)


@pytest.mark.parametrize("field", ["observation_id", "metric", "unit", "source"])
@pytest.mark.parametrize("value", ["", "   "])
def test_observation_strings_must_not_be_blank(field, value):
    with pytest.raises(ValidationError):
        observation(**{field: value})


@pytest.mark.parametrize("level", ["certain", "high ", "HIGH", 0.9, None])
def test_confidence_level_must_be_declared_and_known(level):
    with pytest.raises(ValidationError):
        confidence(level=level)


@pytest.mark.parametrize("field", ["basis", "declared_by"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_confidence_requires_declared_basis_and_producer(field, value):
    with pytest.raises(ValidationError):
        confidence(**{field: value})


def test_insight_requires_at_least_one_observation():
    with pytest.raises(ValidationError):
        insight(observations=())


def test_observation_identifiers_must_be_unique():
    with pytest.raises(ValidationError):
        insight(observations=(observation(), observation(value=5.0)))


def test_hypothesis_identifiers_must_be_unique():
    with pytest.raises(ValidationError):
        insight(
            hypotheses=(
                hypothesis(),
                hypothesis(statement="Outra interpretação"),
            )
        )


def test_hypotheses_are_marked_unverified_by_default():
    assert insight().hypotheses[0].verification == "unverified"
    assert "verified" not in insight().hypotheses[0].model_dump()


def test_recommendation_is_never_automatically_applied():
    result = insight().recommendations[0]

    assert result.requires_human_review is True
    assert result.auto_applied is False
    with pytest.raises(ValidationError):
        recommendation(requires_human_review=False)
    with pytest.raises(ValidationError):
        recommendation(auto_applied=True)


def test_recommendation_must_reference_an_existing_hypothesis():
    with pytest.raises(ValidationError):
        insight(recommendations=(recommendation(hypothesis_ids=("hyp-unknown",)),))
    with pytest.raises(ValidationError):
        recommendation(hypothesis_ids=())


def test_unknowable_performance_fields_are_rejected():
    with pytest.raises(ValidationError):
        hypothesis(estimated_views=10000)
    with pytest.raises(ValidationError):
        observation(views=10)


def test_contract_is_immutable():
    result = insight()

    with pytest.raises(ValidationError):
        result.title = "outro título"
    with pytest.raises(ValidationError):
        result.observations = ()
    with pytest.raises(ValidationError):
        result.observations[0].value = 1.0
    with pytest.raises(ValidationError):
        result.observations[0].window.end_at = at(day=10)
    with pytest.raises(ValidationError):
        result.confidence.level = "high"
    with pytest.raises(ValidationError):
        result.hypotheses[0].verification = "verified"


def test_round_trip_preserves_insight_with_measured_and_unavailable_data():
    original = insight(
        observations=(
            observation(),
            missing_observation(),
        ),
        hypotheses=(
            hypothesis(),
            hypothesis(
                hypothesis_id="hyp-2",
                statement="A amostra atual ainda não permite concluir",
                support="no_evidence_declared",
                observation_ids=(),
                no_evidence_reason="A janela de CTR ainda não está disponível",
            ),
        ),
    )

    restored = LearningInsight.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.observations[1].value is None
    assert restored.observations[0].value == 1200.0


def test_round_trip_preserves_observation():
    original = observation()
    assert MetricObservation.model_validate_json(original.model_dump_json()) == original