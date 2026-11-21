"""Contrato F9-01..F9-06: métrica ligada à versão, origem honesta e revisão humana.

Este módulo é puro e não coleta, não persiste e não aplica nada. Ele existe para que o
dashboard e o loop de aprendizado não repitam os erros que o produto já recusa:

- **Versão**: cada observação é ligada às versões que a produziram (briefing, roteiro,
  embalagem, publicação). Versão ausente não desaparece: vira um ``MissingVersionLink`` com
  motivo explícito. Um id remoto do YouTube sem a publicação local correspondente é recusado,
  porque não há como atribuir o número a uma versão do Studio.
- **Origem**: ``youtube_analytics_api`` ou ``unknown_origin``. Não existe "Global": quando a
  origem não é confiável, ela é desconhecida, com o rótulo literal ``origem desconhecida``.
- **Ausência**: valor ausente é ``not_yet_available`` com motivo. Zero medido é ``0.0``.
- **Agregação**: métrica aditiva só soma com cobertura completa; taxa (CTR, retenção,
  duração média) não é média entre vídeos. Formatos diferentes (Short e long-form) nunca
  entram no mesmo agregado.
- **Experimento**: a API do YouTube Analytics não oferece A/B de thumbnail/título nesta
  integração; ``platform_ab_supported`` é sempre falso e o histórico registra rotação manual
  aprovada por humano, com conclusão marcada como hipótese não verificada.
- **Recomendação**: sugestão para revisão humana. ``requires_human_review`` é sempre
  verdadeiro e ``auto_applied`` sempre falso; não há construtor nem validação que aceite
  aplicação automática. A decisão registrada é ``accepted_for_review`` ou ``rejected``, nunca
  "applied": aplicar exige edição manual do perfil do canal em outra tela.

As garantias valem para instâncias construídas/validadas por este contrato. Os escapes de
runtime do pydantic (``model_construct``, ``model_copy(update=...)``, ``object.__setattr__``)
não revalidam e não devem ser usados por consumidores.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from .contracts import _Model
from .ids import check_id
from .insight import ConfidenceDeclaration, LearningInsight, MetricObservation, MetricWindow

ANALYTICS_READONLY_SCOPE = "yt-analytics.readonly"

MetricName = Literal[
    "views",
    "impressions",
    "ctr",
    "average_view_percentage",
    "average_view_duration_s",
    "estimated_minutes_watched",
    "likes",
    "comments",
    "shares",
    "subscribers_gained",
]
MetricOrigin = Literal["youtube_analytics_api", "unknown_origin"]
ObservationState = Literal["measured", "not_yet_available"]
MissingVersionKind = Literal["brief", "script", "publication", "youtube_video", "packaging"]
RecommendationKind = Literal["theme", "format", "hook", "pacing"]
ExperimentKind = Literal["thumbnail", "title"]
ExperimentStatus = Literal["planned", "running", "finished", "abandoned"]
DecisionStatus = Literal["accepted_for_review", "rejected"]

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]

# Unidade canônica por métrica: misturar "count" com "percent" produz média sem sentido.
CANONICAL_UNITS: dict[str, str] = {
    "views": "count",
    "impressions": "count",
    "ctr": "percent",
    "average_view_percentage": "percent",
    "average_view_duration_s": "seconds",
    "estimated_minutes_watched": "minutes",
    "likes": "count",
    "comments": "count",
    "shares": "count",
    "subscribers_gained": "count",
}
PERCENT_METRICS = frozenset({"ctr", "average_view_percentage"})
# Somar é válido; "média de médias" não é. A separação é o que impede agregado inventado.
ADDITIVE_METRICS = frozenset({"views", "impressions", "estimated_minutes_watched", "likes",
                              "comments", "shares", "subscribers_gained"})
RATE_METRICS = frozenset({"ctr", "average_view_percentage", "average_view_duration_s"})
COMPARISON_FORMATS = ("short", "long")

_ORIGIN_LABELS = {
    "youtube_analytics_api": "API YouTube Analytics",
    "unknown_origin": "origem desconhecida",
}
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def origin_label(origin: str) -> str:
    """Rótulo humano da origem. Qualquer valor fora do contrato — inclusive "Global" — é erro."""
    try:
        return _ORIGIN_LABELS[origin]
    except KeyError as exc:
        raise ValueError(f"unknown metric origin {origin!r}") from exc


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


class MissingVersionLink(_Model):
    """Versão que não existe (ou ainda não é persistida), com o motivo declarado."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MissingVersionKind
    reason: NonBlank


class VersionAttribution(_Model):
    """Liga uma medição às versões que produziram o vídeo.

    ``missing`` tem de cobrir exatamente os campos ausentes: nada de versão implícita. O id
    remoto do YouTube exige a publicação local, senão o número não é atribuível ao Studio.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: NonBlank
    script_version: PositiveInt | None = None
    brief_version: PositiveInt | None = None
    packaging_version: PositiveInt | None = None
    publication_id: NonBlank | None = None
    youtube_video_id: NonBlank | None = None
    missing: tuple[MissingVersionLink, ...] = ()

    @field_validator("video_id")
    @classmethod
    def _video_id(cls, value: str) -> str:
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("video_id must be a 32-character lowercase hex id") from exc

    @field_validator("publication_id")
    @classmethod
    def _publication_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("publication_id must be a 32-character lowercase hex id") from exc

    @field_validator("youtube_video_id")
    @classmethod
    def _youtube_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _YOUTUBE_ID.match(value):
            raise ValueError("youtube_video_id must have the 11-character remote format")
        return value

    @model_validator(mode="after")
    def _missing_matches_absent(self):
        absent = {
            "brief": self.brief_version is None,
            "script": self.script_version is None,
            "publication": self.publication_id is None,
            "youtube_video": self.youtube_video_id is None,
            "packaging": self.packaging_version is None,
        }
        declared = [link.kind for link in self.missing]
        if len(set(declared)) != len(declared):
            raise ValueError("missing version links must be unique")
        expected = {kind for kind, is_absent in absent.items() if is_absent}
        if set(declared) != expected:
            raise ValueError(
                "missing must explain exactly the absent versions: "
                f"declared={sorted(set(declared))!r} absent={sorted(expected)!r}"
            )
        if self.youtube_video_id is not None and self.publication_id is None:
            raise ValueError(
                "a remote youtube_video_id requires the local publication_id; "
                "otherwise the metric cannot be attributed to a Studio version"
            )
        return self

    @property
    def is_complete(self) -> bool:
        return not self.missing

    @property
    def missing_kinds(self) -> tuple[str, ...]:
        return tuple(link.kind for link in self.missing)


class MetricMeasurement(_Model):
    """Observação F9-04 com origem e atribuição de versão; não recalcula nada."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: MetricObservation
    origin: MetricOrigin
    attribution: VersionAttribution
    pillar_id: NonBlank | None = None
    experiment_id: NonBlank | None = None
    variant_id: NonBlank | None = None

    @field_validator("pillar_id")
    @classmethod
    def _pillar_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("pillar_id must be a 32-character lowercase hex id") from exc

    @model_validator(mode="after")
    def _metric_is_in_contract(self):
        metric = self.observation.metric
        if metric not in CANONICAL_UNITS:
            raise ValueError(f"metric {metric!r} is not part of the analytics contract")
        if self.observation.unit != CANONICAL_UNITS[metric]:
            raise ValueError(
                f"unit {self.observation.unit!r} is not canonical for metric {metric!r}; "
                f"expected {CANONICAL_UNITS[metric]!r}"
            )
        value = self.observation.value
        if metric in PERCENT_METRICS and value is not None and not 0.0 <= value <= 100.0:
            raise ValueError(f"{metric} must be between 0 and 100 percent")
        if (self.experiment_id is None) != (self.variant_id is None):
            raise ValueError("experiment_id and variant_id must be declared together")
        return self

    @property
    def metric(self) -> str:
        return self.observation.metric

    @property
    def is_measured(self) -> bool:
        return self.observation.is_measured


@dataclass(frozen=True)
class MetricAggregate:
    """Resultado de agregação, com cobertura e origem declaradas."""

    metric: str
    state: ObservationState
    value: float | None
    reason: str
    coverage: tuple[int, int]  # (medidos, total)
    origin: MetricOrigin


def aggregate_metric(rows: tuple[MetricMeasurement, ...] | list[MetricMeasurement],
                     metric: str, *, expected_videos: int | None = None) -> MetricAggregate:
    """Agrega uma métrica sem inventar média: aditiva soma; taxa só com um vídeo.

    A cobertura é sempre explícita. ``expected_videos`` é o número de vídeos comparáveis do
    recorte (o chamador passa o grupo inteiro, não só as linhas da métrica). Sem ele, o
    denominador vem dos vídeos presentes nas próprias linhas — mas quem tem o grupo deve
    passá-lo, para que "1 de 1" não esconda "1 de 3 vídeos". Se qualquer vídeo do grupo não
    foi medido, a soma é recusada: um parcial apresentado como total é mentira. Origem mista
    vira desconhecida.
    """
    if expected_videos is None:
        expected_videos = len({row.attribution.video_id for row in rows})
    selected = [row for row in rows if row.observation.metric == metric]
    measured_rows = [row for row in selected if row.is_measured]
    measured_videos = {row.attribution.video_id for row in measured_rows}
    total = max(expected_videos, len(measured_videos))
    single_rows = {row.attribution.video_id: row for row in measured_rows}
    coverage = (len(measured_videos), total)
    if not selected:
        return MetricAggregate(metric, "not_yet_available", None,
                               "nenhuma medição desta métrica na janela",
                               (0, total), "unknown_origin")

    origins = {row.origin for row in measured_rows}
    origin: MetricOrigin = next(iter(origins)) if len(origins) == 1 else "unknown_origin"

    if metric in RATE_METRICS:
        if len(measured_videos) == 1 and total == 1:
            return MetricAggregate(metric, "measured", next(iter(single_rows.values())).observation.value,
                                   "medição de um vídeo comparável", coverage, origin)
        return MetricAggregate(
            metric, "not_yet_available", None,
            f"taxa não é agregada entre {total} vídeos: média de médias não é medição",
            coverage, origin,
        )

    if len(measured_videos) != total:
        reasons = [row.observation.unavailable_reason for row in selected if not row.is_measured]
        if total == 1 and reasons and reasons[0]:
            # Uma única medição ausente: o motivo da própria observação é mais útil que "0 de 1".
            return MetricAggregate(metric, "not_yet_available", None, reasons[0],
                                   coverage, origin)
        return MetricAggregate(
            metric, "not_yet_available", None,
            f"cobertura incompleta: {len(measured_videos)} de {total} vídeos medidos na janela",
            coverage, origin,
        )
    return MetricAggregate(metric, "measured",
                           sum(row.observation.value or 0.0 for row in single_rows.values()),
                           "soma dos vídeos medidos na janela", coverage, origin)


class CollectionReadiness(_Model):
    """O que falta para a coleta autorizada começar. Não pronta exige motivo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channel_connected: bool
    scope_granted: bool
    publication_available: bool
    scope: Literal["yt-analytics.readonly"] = ANALYTICS_READONLY_SCOPE
    reasons: tuple[NonBlank, ...] = ()

    @model_validator(mode="after")
    def _reasons_match_state(self):
        if self.is_ready and self.reasons:
            raise ValueError("ready collection must not declare reasons")
        if not self.is_ready and not self.reasons:
            raise ValueError("not-ready collection requires at least one reason")
        return self

    @property
    def is_ready(self) -> bool:
        return self.channel_connected and self.scope_granted and self.publication_available


class AnalyticsPeriod(_Model):
    """Janela oferecida pela tela: 7, 28 ou 90 dias fechados no instante informado."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: Literal[7, 28, 90]
    end_at: datetime

    @field_validator("end_at")
    @classmethod
    def _end_at(cls, value: datetime) -> datetime:
        return _aware(value, "end_at")

    @property
    def start_at(self) -> datetime:
        return self.end_at - timedelta(days=self.days)


class DashboardQuery(_Model):
    """Recorte real do dashboard: canal, vídeo, pilar e período."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: NonBlank
    video_id: NonBlank | None = None
    pillar_id: NonBlank | None = None
    period: AnalyticsPeriod

    @field_validator("project_id")
    @classmethod
    def _project(cls, value: str) -> str:
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("project_id must be a 32-character lowercase hex id") from exc

    @field_validator("video_id", "pillar_id")
    @classmethod
    def _optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("optional ids must be 32-character lowercase hex ids") from exc


class ExperimentVariant(_Model):
    """Uma variante do experimento. Exatamente uma é controle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: NonBlank
    label: NonBlank
    is_control: bool = False


class ExperimentConclusion(_Model):
    """Conclusão do experimento: hipótese não verificada, presa às observações medidas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: NonBlank
    confidence: ConfidenceDeclaration
    observation_ids: tuple[NonBlank, ...] = Field(min_length=1)
    concluded_at: datetime

    @field_validator("concluded_at")
    @classmethod
    def _concluded_at(cls, value: datetime) -> datetime:
        return _aware(value, "concluded_at")

    @model_validator(mode="after")
    def _unique_observations(self):
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("conclusion observation_ids must be unique")
        return self


class ExperimentRecord(_Model):
    """Histórico de experimento de thumbnail/título, com os limites reais da plataforma.

    O YouTube Analytics não oferece A/B de thumbnail/título nesta integração: a rotação é
    manual e aprovada por humano. ``platform_ab_supported`` é literalmente falso — qualquer
    tentativa de registrar suporte inexistente é recusada.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: NonBlank
    project_id: NonBlank
    video_id: NonBlank
    kind: ExperimentKind
    status: ExperimentStatus
    variants: tuple[ExperimentVariant, ...] = Field(min_length=2)
    approved_by: NonBlank
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    platform_note: NonBlank
    platform_ab_supported: Literal[False] = False
    window: MetricWindow | None = None
    conclusion: ExperimentConclusion | None = None

    @field_validator("project_id", "video_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("experiment ids must be 32-character lowercase hex ids") from exc

    @field_validator("approved_at")
    @classmethod
    def _approved_at(cls, value: datetime) -> datetime:
        return _aware(value, "approved_at")

    @model_validator(mode="after")
    def _coherent(self):
        ids = [variant.variant_id for variant in self.variants]
        if len(set(ids)) != len(ids):
            raise ValueError("variant ids must be unique")
        controls = [variant for variant in self.variants if variant.is_control]
        if len(controls) != 1:
            raise ValueError("experiment requires exactly one controle variant")
        if self.status in ("running", "finished") and self.window is None:
            raise ValueError(f"{self.status} experiment requires a measurement window")
        if self.status == "finished" and self.conclusion is None:
            raise ValueError("finished experiment requires a conclusion")
        if self.status != "finished" and self.conclusion is not None:
            raise ValueError("only a finished experiment carries a conclusion")
        return self

    @property
    def control(self) -> ExperimentVariant:
        return next(variant for variant in self.variants if variant.is_control)


class ThemeFormatRecommendation(_Model):
    """Sugestão de tema/formato/hook/pacing para revisão humana; nunca aplicada sozinha."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation_id: NonBlank
    project_id: NonBlank
    kind: RecommendationKind
    statement: NonBlank
    rationale: NonBlank
    evidence: tuple[NonBlank, ...] = Field(min_length=1)
    confidence: ConfidenceDeclaration
    requires_human_review: Literal[True] = True
    auto_applied: Literal[False] = False
    target_profile_field: Literal["pillars", "target_duration_s", "narrative", "cta"] | None = None

    @field_validator("recommendation_id", "project_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("recommendation ids must be 32-character lowercase hex ids") from exc

    @field_validator("evidence")
    @classmethod
    def _unique_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("recommendation evidence ids must be unique")
        return value


class AnalyticsLearningBundle(_Model):
    """Insight F9-04 + recomendações coerentes: evidência medida, sem aplicação automática."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    insight: LearningInsight
    recommendations: tuple[ThemeFormatRecommendation, ...] = ()

    @model_validator(mode="after")
    def _recommendations_reference_measured_evidence(self):
        observed = {item.observation_id: item for item in self.insight.observations}
        for recommendation in self.recommendations:
            unknown = set(recommendation.evidence) - set(observed)
            if unknown:
                raise ValueError(
                    f"recommendation {recommendation.recommendation_id!r} references unknown "
                    f"evidence observations {sorted(unknown)!r}"
                )
            unavailable = [item for item in recommendation.evidence if not observed[item].is_measured]
            if unavailable:
                raise ValueError(
                    f"recommendation {recommendation.recommendation_id!r} requires measured evidence; "
                    f"not yet available: {sorted(unavailable)!r}"
                )
        return self


class RecommendationDecision(_Model):
    """Decisão de revisão; não existe estado "applied" porque aplicar não é desta tela."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation_id: NonBlank
    decision: DecisionStatus
    decided_by: NonBlank
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("recommendation_id")
    @classmethod
    def _recommendation_id(cls, value: str) -> str:
        try:
            return check_id(value)
        except ValueError as exc:
            raise ValueError("recommendation_id must be a 32-character lowercase hex id") from exc

    @field_validator("decided_at")
    @classmethod
    def _decided_at(cls, value: datetime) -> datetime:
        return _aware(value, "decided_at")


