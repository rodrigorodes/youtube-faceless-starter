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
  capítulos ordenados etc.) e ``limit_violations`` usa os defaults
  ``CONFIGURED_*`` ou um ``PackagingLimits`` explícito, sem consultar a API.
- **Texto público é canônico e sem spoofing.** Título, descrição, tags, fontes,
  CTA, capítulos, justificativas e nomes recusam caracteres de controle e de
  formato (``Cc``/``Cf``/``Cs``). Isso inclui override bidirecional (U+202E) e
  joiners (U+200C/U+200D): não há lista de ``Cf`` legítimo, então sequências de
  emoji que dependem de ZWJ são recusadas no título. Comparações de
  duplicidade aplicam NFKC (dobra variantes de compatibilidade, largura total e
  ligaduras usadas em spoofing), colapso de espaços e *casefold*; tags são
  armazenadas em NFC.
- **Fontes são declaradas, não certificadas.** Toda afirmação factual exige
  fonte, então o pacote sempre tem pelo menos uma fonte declarada. O contrato
  não consegue julgar se uma afirmação é factual nem se as fontes bastam ou são
  legítimas: a suficiência não é verificada aqui.
- **Anti-clickbait é declaração, não julgamento.** O título publicado e cada
  variante declaram, em ``TitleClaim``, se trazem uma promessa verificável, uma
  afirmação sensacionalista explicitamente assumida ou nenhuma das duas. O
  contrato recusa título/variante sem declaração ou com declaração vazia, mas
  NÃO decide se a afirmação é enganosa. Ele também expõe
  ``unreviewed_sensational_variant_ids``: afirmação sensacionalista declarada só
  é considerada revisada quando existe ``HumanVariantDecision`` humana para a
  variante (o gate de publicação pertence a F7-04/F7-05). A recusa é registrada
  em ``HumanVariantDecision(decision="reject")``, com autor humano e instante
  com fuso. Não há campo ``chosen``/``auto_selected`` na variante.
- **Desempenho não é fato.** Não há campo de CTR garantido nem previsão de
  desempenho apresentada como resultado. Se houver estimativa, ela é
  ``UnverifiedPerformanceEstimate``: rótulo fixo ``unverified_estimate`` e
  ``guarantees_performance`` sempre falso.
- **Escolha é humana.** A variante não carrega estado de seleção e a decisão
  humana exige autor identificado, instante com fuso e ``automatic`` sempre
  falso; não existe caminho no contrato para marcar uma variante como escolhida
  automaticamente.
- **Garantia de validação, não de runtime.** ``model_validate``,
  ``model_validate_json`` e ``load_versioned`` aplicam todas as invariantes.
  Atalhos do Pydantic como ``model_construct`` e ``model_copy(update=...)`` não
  revalidam: podem furar ``Literal[False]``, a regra de zero ou três variantes e
  as demais checagens. Consumidores que recebem dados de fora devem revalidar
  pelo caminho de validação antes de publicar.
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


def _reject_unsafe_characters(value: str, *, allow_newline: bool = False) -> str:
    """Recusa controle e formato que quebram ou disfarçam texto público.

    ``Cf`` inclui override bidirecional (U+202E) e joiners (U+200C/U+200D); não
    há ``Cf`` considerado legítimo neste contrato. ``Cs`` cobre surrogates
    isolados e ``Cc`` cobre nulos, sino e tabulações. Apenas ``\\n`` é permitido
    na descrição.
    """
    for character in value:
        if character == "\n" and allow_newline:
            continue
        if unicodedata.category(character) in {"Cc", "Cf", "Cs"}:
            raise ValueError("text must not contain control or format characters")
    return value


def _validate_title_text(value: str) -> str:
    if not value.strip():
        raise ValueError("title must not be blank")
    if value != value.strip():
        raise ValueError("title must not have leading or trailing whitespace")
    return _reject_unsafe_characters(value)


def _validate_description_text(value: str) -> str:
    if not value.strip():
        raise ValueError("description must not be blank")
    return _reject_unsafe_characters(value, allow_newline=True)


def _aware_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decided_at must be timezone-aware")
    return value


def _canonical_key(value: str) -> str:
    """Identidade textual: NFKC, espaços colapsados e *casefold*.

    NFKC é escolhido em vez de NFC porque também dobra variantes de
    compatibilidade (largura total, ligaduras, formas circuladas) usadas para
    parecer diferente sendo a mesma identidade. A normalização é só para
    comparação; o valor armazenado preserva a forma editorial escolhida (tags em
    NFC).
    """
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


TitleText = Annotated[str, AfterValidator(_validate_title_text)]
DescriptionText = Annotated[str, AfterValidator(_validate_description_text)]
SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(_reject_unsafe_characters),
]


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

    name: SafeText
    url: SafeText | None = None


class Chapter(_Model):
    """Capítulo em segundos, com timestamp derivado; ordem é validada no pacote."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_seconds: Seconds
    title: SafeText

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
    statement: SafeText | None = None

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

    statement: SafeText
    basis: SafeText
    label: Literal["unverified_estimate"] = "unverified_estimate"
    guarantees_performance: Literal[False] = False


class PackagingVariant(_Model):
    """Conceito de thumbnail/título com justificativa; sem estado de seleção.

    No pacote, ``variant_id``, título e ``thumbnail_concept`` são únicos por
    comparação canônica: dois conceitos iguais não servem aos três conceitos
    distintos de F7-02.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: SafeText
    title: TitleText
    thumbnail_concept: SafeText
    rationale: SafeText
    title_claim: TitleClaim
    performance_estimate: UnverifiedPerformanceEstimate | None = None


class HumanVariantDecision(_Model):
    """Aceite ou recusa registrados por revisor humano identificado.

    Uma revisão posterior pertence a uma nova revisão do pacote; o pacote aceita
    no máximo uma decisão por variante. Edição pós-aprovação de metadados é
    fluxo de F7-07 e não é modelada aqui.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: SafeText
    decision: DecisionKind
    rationale: SafeText
    decided_by: SafeText
    decided_at: datetime
    automatic: Literal[False] = False

    @field_validator("decided_at")
    @classmethod
    def _decided_at_is_aware(cls, value: datetime) -> datetime:
        return _aware_instant(value)


class VideoPackaging(_Model):
    """Pacote completo; o título publicado e cada variante declaram sua promessa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: Revision = 1
    title: TitleText
    title_claim: TitleClaim
    description: DescriptionText
    tags: tuple[SafeText, ...] = ()
    chapters: tuple[Chapter, ...] = ()
    sources: tuple[SourceCitation, ...] = Field(min_length=1)
    cta: SafeText
    variants: tuple[PackagingVariant, ...] = ()
    decisions: tuple[HumanVariantDecision, ...] = ()

    @field_validator("tags")
    @classmethod
    def _tags_are_canonical_and_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        canonical = []
        seen = set()
        for tag in values:
            if "#" in tag:
                raise ValueError("tags must not contain '#'")
            normalized = unicodedata.normalize("NFC", " ".join(tag.split()))
            key = _canonical_key(normalized)
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
        seen_concepts = set()
        for item in values:
            id_key = _canonical_key(item.variant_id)
            if id_key in seen_ids:
                raise ValueError(f"duplicate variant_id after normalization: {item.variant_id!r}")
            title_key = _canonical_key(item.title)
            if title_key in seen_titles:
                raise ValueError(f"duplicate variant title: {item.title!r}")
            concept_key = _canonical_key(item.thumbnail_concept)
            if concept_key in seen_concepts:
                raise ValueError(
                    f"duplicate thumbnail concept after normalization: {item.thumbnail_concept!r}"
                )
            seen_ids.add(id_key)
            seen_titles.add(title_key)
            seen_concepts.add(concept_key)
        return values

    @model_validator(mode="after")
    def _decisions_reference_existing_variants_once(self):
        if not self.decisions:
            return self
        known = {_canonical_key(item.variant_id) for item in self.variants}
        seen = set()
        for item in self.decisions:
            key = _canonical_key(item.variant_id)
            if key not in known:
                raise ValueError(
                    f"decision references unknown variant {item.variant_id!r}"
                )
            if key in seen:
                raise ValueError(
                    f"duplicate decision for variant {item.variant_id!r}; "
                    "a later review belongs to a new packaging revision"
                )
            seen.add(key)
        return self

    def unreviewed_sensational_variant_ids(self) -> tuple[str, ...]:
        """Variantes com afirmação sensacionalista declarada ainda sem decisão humana.

        Não é julgamento de engano: apenas exige que a declaração sensacionalista
        tenha passado por um revisor. Tratar isso como gate de publicação é
        responsabilidade de F7-04/F7-05.
        """
        decided = {_canonical_key(item.variant_id) for item in self.decisions}
        return tuple(
            item.variant_id
            for item in self.variants
            if item.title_claim.kind == "declared_sensational_claim"
            and _canonical_key(item.variant_id) not in decided
        )

    def limit_violations(self, limits: PackagingLimits | None = None) -> tuple[str, ...]:
        """Compara com limites locais; usa os ``CONFIGURED_*`` se ``limits`` for omitido.

        Não consulta a API e não verifica se os limites configurados continuam
        válidos na plataforma.
        """
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