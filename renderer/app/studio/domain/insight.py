"""Contrato puro de insight de aprendizado: observação não é hipótese.

Este módulo não coleta, não persiste, não calcula confiança e não aplica nada.
Ele apenas representa, de forma versionada e imutável, o que foi medido e o que
foi interpretado, para que consumidores (dashboard, revisão humana, futuras
fatias de F9) não confundam os dois.

Fronteiras deliberadas:

- **Observação** é fato medido: métrica identificada, valor finito, unidade,
  janela temporal com início estritamente anterior ao fim, origem declarada e
  instante de coleta. ``state="measured"`` exige valor; ``state="not_yet_available"``
  exige ``value=None`` e um motivo explícito. Zero medido e ausência de dado são
  estados diferentes: zero é ``0.0`` medido, ausência é ``None`` com motivo.
- **Hipótese** é interpretação e fica sempre marcada como ``unverified``. Ou ela
  referencia observações medidas existentes no mesmo insight
  (``support="supported"``), ou declara explicitamente que não há evidência
  (``support="no_evidence_declared"`` com motivo). Observação indisponível não
  serve de suporte.
- **Confiança** é declarada pelo produtor do insight (nível, base e autor da
  declaração). O contrato nunca a calcula nem a infere de métricas.
- **Recomendação** é sugestão para revisão humana: ``requires_human_review`` é
  sempre verdadeiro e ``auto_applied`` é sempre falso; não há caminho para
  representar reconfiguração automática do canal.

Nada aqui verifica a exatidão da fonte, a legitimidade do acesso aos dados nem
a qualidade da conclusão. O contrato apenas recusa estados incoerentes e
números não finitos.
"""

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from .contracts import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
ObservationState = Literal["measured", "not_yet_available"]
EvidenceStatus = Literal["supported", "no_evidence_declared"]
ConfidenceLevel = Literal["low", "medium", "high"]


def _finite_aware_instant(value: datetime, name: str) -> datetime:
    """Exige instante com fuso e timestamp representável/finito."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    try:
        timestamp = value.timestamp()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{name} must be a representable finite instant") from exc
    if not math.isfinite(timestamp):
        raise ValueError(f"{name} must be a representable finite instant")
    return value


class MetricWindow(_Model):
    """Janela fechada de observação; início estritamente anterior ao fim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def _aware_and_finite(cls, value: datetime) -> datetime:
        return _finite_aware_instant(value, "window instant")

    @model_validator(mode="after")
    def _ordered(self):
        if self.start_at >= self.end_at:
            raise ValueError("window start_at must be before end_at")
        return self


class MetricObservation(_Model):
    """Fato medido ou estado explícito de dado ainda não disponível."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: NonBlank
    metric: NonBlank
    unit: NonBlank
    window: MetricWindow
    source: NonBlank
    collected_at: datetime
    state: ObservationState = "measured"
    value: FiniteNumber | None = None
    unavailable_reason: NonBlank | None = None

    @field_validator("collected_at")
    @classmethod
    def _collected_at_is_aware_and_finite(cls, value: datetime) -> datetime:
        return _finite_aware_instant(value, "collected_at")

    @model_validator(mode="after")
    def _state_matches_value(self):
        if self.state == "measured":
            if self.value is None:
                raise ValueError("measured observation requires a finite value")
            if self.unavailable_reason is not None:
                raise ValueError("measured observation must not declare unavailable_reason")
        else:
            if self.value is not None:
                raise ValueError(
                    "not_yet_available observation must not carry a value; "
                    "zero is a measured value, not missing data"
                )
            if self.unavailable_reason is None:
                raise ValueError("not_yet_available observation requires an unavailable_reason")
        return self

    @property
    def is_measured(self) -> bool:
        """Distingue zero medido de ausência explícita de dado."""
        return self.state == "measured"


class ConfidenceDeclaration(_Model):
    """Confiança declarada pelo produtor; o contrato não a calcula."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ConfidenceLevel
    basis: NonBlank
    declared_by: NonBlank


class InsightHypothesis(_Model):
    """Interpretação explicitamente não verificada e seu suporte observado."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: NonBlank
    statement: NonBlank
    verification: Literal["unverified"] = "unverified"
    support: EvidenceStatus
    observation_ids: tuple[NonBlank, ...] = ()
    no_evidence_reason: NonBlank | None = None

    @model_validator(mode="after")
    def _support_is_explicit(self):
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("observation_ids must be unique")
        if self.support == "supported":
            if not self.observation_ids:
                raise ValueError(
                    "supported hypothesis requires at least one observation_id, "
                    "or must declare no_evidence_declared"
                )
            if self.no_evidence_reason is not None:
                raise ValueError(
                    "supported hypothesis must not declare no_evidence_reason"
                )
        else:
            if self.observation_ids:
                raise ValueError(
                    "no_evidence_declared hypothesis must not reference observations"
                )
            if self.no_evidence_reason is None:
                raise ValueError(
                    "no_evidence_declared hypothesis requires a no_evidence_reason"
                )
        return self


class InsightRecommendation(_Model):
    """Sugestão para revisão humana; nunca aplicada automaticamente."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: NonBlank
    rationale: NonBlank
    hypothesis_ids: tuple[NonBlank, ...] = Field(min_length=1)
    requires_human_review: Literal[True] = True
    auto_applied: Literal[False] = False

    @model_validator(mode="after")
    def _identifiers_are_unique(self):
        if len(set(self.hypothesis_ids)) != len(self.hypothesis_ids):
            raise ValueError("hypothesis_ids must be unique")
        return self


class LearningInsight(_Model):
    """Conjunto coerente de observações, hipóteses e recomendações."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    insight_id: NonBlank
    title: NonBlank
    observations: tuple[MetricObservation, ...] = Field(min_length=1)
    confidence: ConfidenceDeclaration
    hypotheses: tuple[InsightHypothesis, ...] = ()
    recommendations: tuple[InsightRecommendation, ...] = ()

    @model_validator(mode="after")
    def _references_are_coherent(self):
        observed: dict[str, MetricObservation] = {}
        for item in self.observations:
            if item.observation_id in observed:
                raise ValueError(
                    f"duplicate observation_id {item.observation_id!r}"
                )
            observed[item.observation_id] = item

        hypotheses: dict[str, InsightHypothesis] = {}
        for item in self.hypotheses:
            if item.hypothesis_id in hypotheses:
                raise ValueError(
                    f"duplicate hypothesis_id {item.hypothesis_id!r}"
                )
            hypotheses[item.hypothesis_id] = item
            unknown = set(item.observation_ids) - set(observed)
            if unknown:
                raise ValueError(
                    f"hypothesis {item.hypothesis_id!r} references unknown observations "
                    f"{sorted(unknown)!r}"
                )
            unavailable = [
                observation_id
                for observation_id in item.observation_ids
                if not observed[observation_id].is_measured
            ]
            if unavailable:
                raise ValueError(
                    f"hypothesis {item.hypothesis_id!r} requires measured observations; "
                    f"not yet available: {sorted(unavailable)!r}"
                )

        for item in self.recommendations:
            unknown = set(item.hypothesis_ids) - set(hypotheses)
            if unknown:
                raise ValueError(
                    f"recommendation references unknown hypotheses {sorted(unknown)!r}"
                )
        return self