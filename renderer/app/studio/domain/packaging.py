"""Contrato puro do pacote editorial de apresentação e das suas variantes.

Este módulo é a fatia de domínio de F7-01/F7-02: ele representa, de forma
versionada e imutável, título, descrição, tags, capítulos, fontes citadas, CTA e
três conceitos de thumbnail/título com justificativa. Não lê nem grava nada,
não chama a API do YouTube, não gera imagens e não escolhe variante.

Fronteiras deliberadas:

- **Limites são configurados, não verificados.** As constantes ``CONFIGURED_*``
  e o modelo ``PackagingLimits`` representam política local de tamanho. Não
  foram conferidos contra a API nem contra a documentação vigente do YouTube e
  podem mudar com o tempo; a conferência real é F7-06. O contrato exige apenas
  invariantes estruturais (título não vazio, sem espaço/controle inválido,
  capítulos ordenados etc.) e aplica limites somente quando o chamador passa um
  ``PackagingLimits`` explícito para ``limit_violations``.
- **Fontes são declaradas, não certificadas.** Toda afirmação factual exige
  fonte, então o pacote sempre tem pelo menos uma fonte declarada. O contrato
  não consegue julgar se uma afirmação é factual nem se as fontes bastam ou são
  legítimas: a suficiência não é verificada aqui.
- **Anti-clickbait é declaração, não julgamento.** Cada variante declara se o
  título traz uma promessa verificável, uma afirmação sensacionalista
  explicitamente assumida ou nenhuma das duas. O contrato recusa variante sem
  declaração ou com declaração vazia, mas NÃO decide se a afirmação é enganosa;
  um revisor humano registra aceite ou recusa em ``HumanVariantDecision``.
- **Desempenho não é fato.** Não há campo de CTR garantido nem previsão de
  desempenho apresentada como resultado. Se houver estimativa, ela é
  ``UnverifiedPerformanceEstimate``: rótulo fixo ``unverified_estimate`` e
  ``guarantees_performance`` sempre falso.
- **Escolha é humana.** A variante não carrega estado de seleção e a decisão
  humana exige autor identificado, instante com fuso e ``automatic`` sempre
  falso; não existe caminho no contrato para marcar uma variante como escolhida
  automaticamente.
"""

import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .contracts import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Seconds = Annotated[int, Field(strict=True, ge=0)]
Revision = Annotated[int, Field(strict=True, ge=1)]
ClaimKind = Literal["verifiable_promise", "declared_sensational_claim", "no_claim"]
DecisionKind = Literal["accept", "reject"]

# Limites configurados localmente pelo produto. NÃO foram verificados contra a
# API nem contra a documentação vigente do YouTube: são política editável, não
# fato da plataforma. A atualização/verificação é F7-06. A contagem é em code
# points, não em grafemas percebidos.
CONFIGURED_TITLE_MAX_CHARS = 100
CONFIGURED_DESCRIPTION_MAX_CHARS = 5000
CONFIGURED_TAG_MAX_CHARS = 100
CONFIGURED_MAX_TAGS = 500
CONFIGURED_TOTAL_TAG_CHARS = 500


def _reject_control_characters(value: str, *, allow_newline: bool) -> None:
    for character in value:
        if character == "\n" and allow_newline:
            continue
        if unicodedata.category(character) in {"Cc", "Cs"}:
            raise ValueError("text must not contain control characters")


def _validate_title_text(value: str) -> str:
    if not value.strip():
        raise ValueError("title must not be blank")
    if value != value.strip():
        raise ValueError("title must not have leading or trailing whitespace")
    _reject_control_characters(value, allow_newline=False)
    return value


def _validate_description_text(value: str) -> str:
    if not value.strip():
        raise ValueError("description must not be blank")
    _reject_control_characters(value, allow_newline=True)
    return value


def _aware_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decided_at must be timezone-aware")
    return value


def _canonical_key(value: str) -> str:
    """Chave de comparação para duplicidade declarada (espaços e caixa)."""
    return " ".join(value.split()).casefold()


TitleText = Annotated[str, AfterValidator(_validate_title_text)]
DescriptionText = Annotated[str, AfterValidator(_validate_description_text)]


class PackagingLimits(BaseModel):
    """Limites declarados pelo chamador; não são verdade da API do YouTube."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title_max_chars: Annotated[int, Field(strict=True, gt=0)] = CONFIGURED_TITLE_MAX_CHARS
    description_max_chars: Annotated[int, Field(strict=True, gt=0)] = CONFIGURED_DESCRIPTION_MAX_CHARS
    tag_max_chars: Annotated[int, Field(strict=True, gt=0)] = CONFIGURED_TAG_MAX_CHARS
    max_tags: Annotated[int, Field(strict=True, gt=0)] = CONFIGURED_MAX_TAGS
    total_tag_chars: Annotated[int, Field(strict=True, gt=0)] = CONFIGURED_TOTAL_TAG_CHARS


class SourceCitation(_Model):
    """Fonte declarada; existência e suficiência não são verificadas aqui."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: NonBlank
    url: NonBlank | None = None


class Chapter(_Model):
    """Capítulo em segundos, com timestamp derivado; ordem é validada no pacote."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_seconds: Seconds
    title: NonBlank

    @property
    def timestamp(self) -> str:
        """Formato de exibição derivado, não persistido nem revalidado."""
        hours, remainder = divmod(self.start_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


class TitleClaim(_Model):
    """Declaração explícita do tipo de promessa do título; não é julgamento."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ClaimKind
    statement: NonBlank | None = None

    @model_validator(mode="after")
    def _statement_matches_kind(self):
        if self.kind == "no_claim":
            if self.statement is not None:
                raise ValueError("no_claim must not carry a statement")
        elif self.statement is None:
            raise ValueError(f"{self.kind} requires a statement")
        return self


class UnverifiedPerformanceEstimate(_Model):
    """Estimativa editorial rotulada; nunca resultado nem garantia de desempenho."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: NonBlank
    basis: NonBlank
    label: Literal["unverified_estimate"] = "unverified_estimate"
    guarantees_performance: Literal[False] = False


class PackagingVariant(_Model):
    """Conceito de thumbnail/título com justificativa; sem estado de seleção."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: NonBlank
    title: TitleText
    thumbnail_concept: NonBlank
    rationale: NonBlank
    title_claim: TitleClaim
    performance_estimate: UnverifiedPerformanceEstimate | None = None


class HumanVariantDecision(_Model):
    """Aceite ou recusa registrados por revisor humano identificado."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: NonBlank
    decision: DecisionKind
    rationale: NonBlank
    decided_by: NonBlank
    decided_at: datetime
    automatic: Literal[False] = False

    @field_validator("decided_at")
    @classmethod
    def _decided_at_is_aware(cls, value: datetime) -> datetime:
        return _aware_instant(value)


class VideoPackaging(_Model):
    """Pacote editorial completo, imutável e versionado por schema/revisão."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: Revision = 1
    title: TitleText
    description: DescriptionText
    tags: tuple[NonBlank, ...] = ()
    chapters: tuple[Chapter, ...] = ()
    sources: tuple[SourceCitation, ...] = Field(min_length=1)
    cta: NonBlank
    variants: tuple[PackagingVariant, ...] = ()

    @field_validator("tags")
    @classmethod
    def _tags_are_canonical_and_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = []
        seen = set()
        for tag in values:
            if "#" in tag:
                raise ValueError("tags must not contain '#'")
            normalized = " ".join(tag.split())
            key = normalized.casefold()
            if key in seen:
                raise ValueError(f"duplicate tag after normalization: {normalized!r}")
            seen.add(key)
            canonical.append(normalized)
        return tuple(canonical)

    @field_validator("chapters")
    @classmethod
    def _chapters_start_at_zero_and_strictly_increase(cls, values: tuple[Chapter, ...]) -> tuple[Chapter, ...]:
        if not values:
            return values
        if values[0].start_seconds != 0:
            raise ValueError("first chapter must start at zero")
        seen_starts = set()
        seen_titles = set()
        previous = -1
        for chapter in values:
            if chapter.start_seconds in seen_starts:
                raise ValueError(f"duplicate chapter start_seconds {chapter.start_seconds!r}")
            if chapter.start_seconds <= previous:
                raise ValueError("chapters must be strictly increasing")
            title_key = _canonical_key(chapter.title)
            if title_key in seen_titles:
                raise ValueError(f"duplicate chapter title: {chapter.title!r}")
            seen_starts.add(chapter.start_seconds)
            seen_titles.add(title_key)
            previous = chapter.start_seconds
        return values

    @field_validator("variants")
    @classmethod
    def _variants_are_three_concepts_with_stable_ids(cls, values: tuple[PackagingVariant, ...]) -> tuple[PackagingVariant, ...]:
        if len(values) not in (0, 3):
            raise ValueError("variants must be absent or contain exactly three concepts")
        seen_ids = set()
        seen_titles = set()
        for item in values:
            if item.variant_id in seen_ids:
                raise ValueError(f"duplicate variant_id {item.variant_id!r}")
            title_key = _canonical_key(item.title)
            if title_key in seen_titles:
                raise ValueError(f"duplicate variant title: {item.title!r}")
            seen_ids.add(item.variant_id)
            seen_titles.add(title_key)
        return values

    def limit_violations(self, limits: PackagingLimits | None = None) -> tuple[str, ...]:
        """Compara com limites declarados; não consulta a API nem os verifica."""
        effective = limits or PackagingLimits()
        violations: list[str] = []
        if len(self.title) > effective.title_max_chars:
            violations.append(
                f"title has {len(self.title)} chars; configured max is {effective.title_max_chars}"
            )
        if len(self.description) > effective.description_max_chars:
            violations.append(
                f"description has {len(self.description)} chars; "
                f"configured max is {effective.description_max_chars}"
            )
        if len(self.tags) > effective.max_tags:
            violations.append(
                f"package has {len(self.tags)} tags; configured max is {effective.max_tags}"
            )
        for tag in self.tags:
            if len(tag) > effective.tag_max_chars:
                violations.append(
                    f"tag {tag!r} has {len(tag)} chars; configured max is {effective.tag_max_chars}"
                )
        total = sum(len(tag) for tag in self.tags)
        if total > effective.total_tag_chars:
            violations.append(
                f"tags total {total} chars; configured max is {effective.total_tag_chars}"
            )
        return tuple(violations)