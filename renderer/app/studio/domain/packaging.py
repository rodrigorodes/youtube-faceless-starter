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
- **Texto público: exibição x identidade.** A regra é explícita e assimétrica.
  Campos de **exibição** (título, descrição, CTA, título de capítulo, título e
  justificativa de variante, rationale de decisão, prosa de declaração de
  promessa e de estimativa) aceitam U+200D (ZWJ), necessário para emoji
  composto como ``👨‍👩‍👧`` e ``👩‍💻``, e aceitam a sequência de *tag
  characters* (U+E0020–U+E007F) de bandeira subdivisionária somente logo após
  U+1F3F4 (🏴). Campos de **identidade** (tags, ``variant_id``,
  ``thumbnail_concept``, nome/URL de fonte e ``decided_by``) recusam ZWJ e tag
  characters: caractere invisível criaria identidades visualmente iguais sem
  que a normalização canônica as una. Em todos os campos são recusados ``Cc``,
  ``Cs``, ``Zl``, ``Zp`` e os demais ``Cf`` — em especial bidi (U+202E,
  U+200E/U+200F, U+2066–U+2069) e BOM (U+FEFF). A heurística de bandeira exige
  U+1F3F4 imediatamente antes e não toca em controles bidi, então não abre
  caminho para spoofing direcional. Quebra de linha só é representável por
  ``\\n`` na descrição; U+2028/U+2029 são sempre recusados.
- **NFKC é conservador, com falso positivo declarado.** A chave de identidade
  dobra compatibilidade: ``Ⅻ``/``XII``, ``①``/``1`` e ``ﬁm``/``fim`` contam como
  duplicados. Isso é desejável em tags, mas é falso positivo para títulos de
  capítulo e de variante. O trade-off é aceito para evitar lookalikes; a
  cobertura de variantes de compatibilidade é de um único teste.
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
  com fuso. A decisão referencia o ``variant_id`` **exato** armazenado, sem
  normalização; a forma canônica serve só para detectar duplicidade. Não há
  campo ``chosen``/``auto_selected`` na variante.
- **Desempenho não é fato.** Não há campo de CTR garantido nem previsão de
  desempenho apresentada como resultado. Se houver estimativa, ela é
  ``UnverifiedPerformanceEstimate``: rótulo fixo ``unverified_estimate`` e
  ``guarantees_performance`` sempre falso.
- **Escolha é humana.** A variante não carrega estado de seleção e a decisão
  humana exige autor identificado, instante com fuso e ``automatic`` sempre
  falso; não existe caminho no contrato para marcar uma variante como escolhida
  automaticamente.
- **Schema 2 e revalidação.** ``VideoPackaging.schema_version`` é 2 porque
  ``title_claim`` passou a ser obrigatório; o validador global de ``contracts``
  continua em schema 1 para outras entidades e não é o loader deste pacote.
  Carregue com ``VideoPackaging.model_validate``/``model_validate_json``.
  ``model_construct`` e ``model_copy(update=...)`` não revalidam: podem furar
  ``Literal[False]``, a regra de zero ou três variantes, o schema 2 e as demais
  invariantes. Consumidores que recebem dados de fora devem revalidar pelo
  caminho de validação antes de publicar.
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

# Versão do contrato do pacote. Subiu para 2 quando ``title_claim`` passou a ser
# obrigatório; payloads schema 1 anteriores não têm essa declaração e portanto
# não são equivalentes. Nada persiste o pacote nesta fatia.
PACKAGING_SCHEMA_VERSION = 2


_ZWJ = "\u200d"
_FLAG_BASE = "\U0001F3F4"
_EMOJI_TAG_START = "\U000E0020"
_EMOJI_TAG_END = "\U000E007F"
_FORBIDDEN_CATEGORIES = {"Cc", "Cf", "Cs", "Zl", "Zp"}


def _reject_unsafe_characters(
    value: str,
    *,
    allow_newline: bool = False,
    allow_zwj: bool = False,
    allow_flag_tag_sequence: bool = False,
) -> str:
    """Recusa controle, format e separadores de linha invisíveis.

    ``Zl``/``Zp`` (U+2028/U+2029) quebram linha mesmo sem ``\\n`` e são sempre
    recusados; ``\\n`` só passa quando ``allow_newline``.

    ``allow_zwj`` vale apenas para texto de exibição: U+200D é legítimo em emoji
    composto. Em campos de identidade (tag, id, URL, conceito, autor) ele fica
    proibido porque um caractere invisível criaria lookalikes que a comparação
    canônica não une. Os demais ``Cf`` — bidi (U+202E, U+200E/U+200F,
    U+2066–U+2069) e BOM (U+FEFF) — continuam proibidos em qualquer campo.

    ``allow_flag_tag_sequence`` aceita U+E0020–U+E007F (``Cf``) somente enquanto
    imediatamente após U+1F3F4, como em 🏴󠁧󠁢󠁥󠁮󠁧󠁿. A heurística exige o
    caractere-base de bandeira e não cobre nenhum controle bidi.
    """
    in_flag_tag_sequence = False
    for character in value:
        if (
            allow_flag_tag_sequence
            and in_flag_tag_sequence
            and _EMOJI_TAG_START <= character <= _EMOJI_TAG_END
        ):
            continue
        if character == "\n" and allow_newline:
            in_flag_tag_sequence = False
            continue
        category = unicodedata.category(character)
        if category not in _FORBIDDEN_CATEGORIES:
            in_flag_tag_sequence = allow_flag_tag_sequence and character == _FLAG_BASE
            continue
        if category == "Cf" and allow_zwj and character == _ZWJ:
            in_flag_tag_sequence = False
            continue
        raise ValueError("text must not contain control, format or line separator characters")
    return value


def _validate_title_text(value: str) -> str:
    if not value.strip():
        raise ValueError("title must not be blank")
    if value != value.strip():
        raise ValueError("title must not have leading or trailing whitespace")
    return _reject_unsafe_characters(value, allow_zwj=True, allow_flag_tag_sequence=True)


def _validate_description_text(value: str) -> str:
    if not value.strip():
        raise ValueError("description must not be blank")
    return _reject_unsafe_characters(
        value, allow_newline=True, allow_zwj=True, allow_flag_tag_sequence=True
    )


def _validate_display_text(value: str) -> str:
    return _reject_unsafe_characters(value, allow_zwj=True, allow_flag_tag_sequence=True)


def _validate_identity_text(value: str) -> str:
    return _reject_unsafe_characters(value)


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

    Trade-off declarado: ``Ⅻ``/``XII``, ``①``/``1`` e ``ﬁm``/``fim`` contam como
    duplicados. Isso é conservador e desejável em tags, mas é falso positivo para
    títulos de capítulo e de variante. A cobertura de compatibilidade é de um
    único teste.
    """
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


TitleText = Annotated[str, AfterValidator(_validate_title_text)]
DescriptionText = Annotated[str, AfterValidator(_validate_description_text)]
DisplayText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(_validate_display_text),
]
IdentityText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(_validate_identity_text),
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

    name: IdentityText
    url: IdentityText | None = None


class Chapter(_Model):
    """Capítulo em segundos, com timestamp derivado; ordem é validada no pacote."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_seconds: Seconds
    title: DisplayText

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
    statement: DisplayText | None = None

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

    statement: DisplayText
    basis: DisplayText
    label: Literal["unverified_estimate"] = "unverified_estimate"
    guarantees_performance: Literal[False] = False


class PackagingVariant(_Model):
    """Conceito de thumbnail/título com justificativa; sem estado de seleção.

    No pacote, ``variant_id``, título e ``thumbnail_concept`` são únicos por
    comparação canônica: dois conceitos iguais não servem aos três conceitos
    distintos de F7-02.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: IdentityText
    title: TitleText
    thumbnail_concept: IdentityText
    rationale: DisplayText
    title_claim: TitleClaim
    performance_estimate: UnverifiedPerformanceEstimate | None = None


class HumanVariantDecision(_Model):
    """Aceite ou recusa registrados por revisor humano identificado.

    O ``variant_id`` é comparado exatamente com o valor armazenado na variante;
    a chave canônica serve apenas para detectar duplicidade. Uma revisão
    posterior pertence a uma nova revisão do pacote; o pacote aceita no máximo
    uma decisão por variante. Edição pós-aprovação de metadados é fluxo de F7-07
    e não é modelada aqui.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: IdentityText
    decision: DecisionKind
    rationale: DisplayText
    decided_by: IdentityText
    decided_at: datetime
    automatic: Literal[False] = False

    @field_validator("decided_at")
    @classmethod
    def _decided_at_is_aware(cls, value: datetime) -> datetime:
        return _aware_instant(value)


class VideoPackaging(_Model):
    """Pacote completo; o título publicado e cada variante declaram sua promessa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Annotated[int, Field(strict=True)] = PACKAGING_SCHEMA_VERSION
    revision: Revision = 1
    title: TitleText
    title_claim: TitleClaim
    description: DescriptionText
    tags: tuple[IdentityText, ...] = ()
    chapters: tuple[Chapter, ...] = ()
    sources: tuple[SourceCitation, ...] = Field(min_length=1)
    cta: DisplayText
    variants: tuple[PackagingVariant, ...] = ()
    decisions: tuple[HumanVariantDecision, ...] = ()

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value != PACKAGING_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {value!r}; expected {PACKAGING_SCHEMA_VERSION}"
            )
        return value

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
        known = {item.variant_id for item in self.variants}
        seen = set()
        for item in self.decisions:
            if item.variant_id not in known:
                raise ValueError(
                    f"decision references unknown variant {item.variant_id!r}; "
                    "it must match the stored variant_id exactly"
                )
            if item.variant_id in seen:
                raise ValueError(
                    f"duplicate decision for variant {item.variant_id!r}; "
                    "a later review belongs to a new packaging revision"
                )
            seen.add(item.variant_id)
        return self

    def unreviewed_sensational_variant_ids(self) -> tuple[str, ...]:
        """Variantes com afirmação sensacionalista declarada ainda sem decisão humana.

        Não é julgamento de engano: apenas exige que a declaração sensacionalista
        tenha passado por um revisor. Tratar isso como gate de publicação é
        responsabilidade de F7-04/F7-05.
        """
        decided = {item.variant_id for item in self.decisions}
        return tuple(
            item.variant_id
            for item in self.variants
            if item.title_claim.kind == "declared_sensational_claim"
            and item.variant_id not in decided
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