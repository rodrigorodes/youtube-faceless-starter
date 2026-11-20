"""Pacote editorial: declaração obrigatória, escolha e julgamento humanos.

O contrato recusa estados incoerentes (título vazio, capítulos fora de ordem,
tags duplicadas, variante sem justificativa), mas NÃO decide se um título é
enganoso, se uma promessa é verdadeira ou se as fontes bastam. Essas decisões
permanecem humanas e são representadas como declarações explícitas.
"""

import ast
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.studio.domain import packaging
from app.studio.domain.contracts import load_versioned
from app.studio.domain.packaging import (
    CONFIGURED_DESCRIPTION_MAX_CHARS,
    CONFIGURED_MAX_TAGS,
    CONFIGURED_TAG_MAX_CHARS,
    CONFIGURED_TITLE_MAX_CHARS,
    CONFIGURED_TOTAL_TAG_CHARS,
    Chapter,
    HumanVariantDecision,
    PackagingLimits,
    PackagingVariant,
    SourceCitation,
    TitleClaim,
    UnverifiedPerformanceEstimate,
    VideoPackaging,
)


def claim(kind="verifiable_promise", statement="O custo declarado no relatório anual"):
    return TitleClaim(kind=kind, statement=statement)


def variant(variant_id="v1", title=None, **changes):
    values = {
        "variant_id": variant_id,
        "title": f"Conceito editorial {variant_id}" if title is None else title,
        "thumbnail_concept": f"Máquina parada sobre faixas de custo ({variant_id})",
        "rationale": "Contrasta a expectativa do operador com o custo citado na fonte",
        "title_claim": claim(),
    }
    values.update(changes)
    return PackagingVariant(**values)


def variants():
    return (
        variant("v1", "O custo real de uma máquina parada"),
        variant("v2", "O que o relatório anual declara sobre a parada"),
        variant("v3", "Três números que explicam a parada"),
    )


def package(**changes):
    values = {
        "title": "O custo real de manter uma máquina parada",
        "title_claim": claim(),
        "description": "Descrição editorial com a referência declarada.",
        "tags": ("manutenção", "custo industrial"),
        "chapters": (
            Chapter(start_seconds=0, title="Abertura"),
            Chapter(start_seconds=45, title="O problema"),
            Chapter(start_seconds=180, title="O que os números mostram"),
        ),
        "sources": (
            SourceCitation(name="Relatório anual de manutenção", url="https://example.org/relatorio"),
        ),
        "cta": "Inscreva-se para acompanhar a série",
        "variants": variants(),
    }
    values.update(changes)
    return VideoPackaging(**values)


def decision(**changes):
    values = {
        "variant_id": "v2",
        "decision": "accept",
        "rationale": "A promessa é verificável na fonte citada e o título é legível",
        "decided_by": "revisor-humano",
        "decided_at": datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
    }
    values.update(changes)
    return HumanVariantDecision(**values)


# --- pacote válido ---------------------------------------------------------


def test_valid_package_round_trips_with_every_part():
    original = package()

    restored = VideoPackaging.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.schema_version == 1
    assert restored.revision == 1
    assert restored.title == "O custo real de manter uma máquina parada"
    assert restored.tags == ("manutenção", "custo industrial")
    assert [chapter.start_seconds for chapter in restored.chapters] == [0, 45, 180]
    assert restored.sources[0].name == "Relatório anual de manutenção"
    assert restored.cta == "Inscreva-se para acompanhar a série"
    assert [item.variant_id for item in restored.variants] == ["v1", "v2", "v3"]


def test_package_is_deeply_immutable():
    original = package()

    with pytest.raises(ValidationError):
        original.title = "Outro título"
    with pytest.raises(ValidationError):
        original.chapters[0].title = "Outra abertura"
    with pytest.raises(ValidationError):
        original.variants[0].rationale = "Outra justificativa"

    assert isinstance(original.tags, tuple)
    assert isinstance(original.chapters, tuple)
    assert isinstance(original.sources, tuple)
    assert isinstance(original.variants, tuple)
    assert isinstance(original.variants[0].title_claim, TitleClaim)


def test_round_trip_preserves_unverified_estimate_and_declared_claim():
    original = package(
        variants=(
            variant(
                "v1",
                "O que o relatório declara",
                title_claim=claim(
                    kind="declared_sensational_claim",
                    statement="Promete resolver toda parada em uma semana",
                ),
                performance_estimate=UnverifiedPerformanceEstimate(
                    statement="Estimativa editorial de maior retenção nos primeiros segundos",
                    basis="Comparação informal com dois vídeos anteriores do canal",
                ),
            ),
            variant("v2", "O custo citado na fonte"),
            variant("v3", "Três números da parada"),
        )
    )

    restored = VideoPackaging.model_validate_json(original.model_dump_json())

    estimate = restored.variants[0].performance_estimate
    assert restored == original
    assert estimate is not None
    assert estimate.label == "unverified_estimate"
    assert estimate.guarantees_performance is False
    assert restored.variants[0].title_claim.kind == "declared_sensational_claim"


# --- título e descrição ----------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        " Título com espaço inicial",
        "Título com espaço final ",
        "Título\ncom quebra",
        "Título\tcom tabulação",
        "Título\x00com nulo",
        "Título\x07com sino",
    ],
)
def test_title_rejects_blank_surrounding_whitespace_and_control_characters(value):
    with pytest.raises(ValidationError):
        package(title=value)


def test_description_accepts_multiline_but_rejects_blank_and_nul():
    assert package(description="Primeira linha.\nSegunda linha.").description.endswith("linha.")

    with pytest.raises(ValidationError):
        package(description="   ")
    with pytest.raises(ValidationError):
        package(description="Texto\x00com nulo")
    with pytest.raises(ValidationError):
        package(description="Texto\u202ecom override bidi")


@pytest.mark.parametrize(
    "value",
    [
        "Título\u202ecom override bidi",
        "Título\u200dcom ZWJ",
        "Título\u200ccom ZWNJ",
    ],
)
def test_title_rejects_bidi_override_and_format_joiners(value):
    with pytest.raises(ValidationError):
        package(title=value)


@pytest.mark.parametrize(
    "build",
    [
        lambda: package(tags=("tag\x00",)),
        lambda: package(tags=("tag\u202e",)),
        lambda: package(sources=(SourceCitation(name="Fonte\x00"),)),
        lambda: package(sources=(SourceCitation(name="Fonte\u200d"),)),
        lambda: package(sources=(SourceCitation(name="Fonte", url="https://example.org/\x00"),)),
        lambda: package(cta="Inscreva-se\x07"),
        lambda: package(cta="Inscreva-se\u200d"),
        lambda: package(chapters=(Chapter(start_seconds=0, title="Abertura\x00"),)),
        lambda: package(chapters=(Chapter(start_seconds=0, title="Abertura\u202e"),)),
        lambda: variant("v1", rationale="Justificativa\x00"),
        lambda: variant("v1", rationale="Justificativa\u202e"),
        lambda: variant("v1", thumbnail_concept="Conceito\u200d"),
        lambda: variant(variant_id="v\x001"),
        lambda: TitleClaim(kind="verifiable_promise", statement="Promessa\x00"),
        lambda: TitleClaim(kind="verifiable_promise", statement="Promessa\u202e"),
        lambda: decision(decided_by="revisor\x00"),
        lambda: decision(rationale="Decisão\u202e"),
        lambda: UnverifiedPerformanceEstimate(statement="Estimativa\x00", basis="Base"),
        lambda: UnverifiedPerformanceEstimate(statement="Estimativa", basis="Base\u202e"),
    ],
)
def test_control_and_format_characters_are_rejected_in_every_public_text(build):
    with pytest.raises(ValidationError):
        build()


# --- limites configurados, não verificados ---------------------------------


def test_limits_are_configured_constants_and_documented_as_not_api_verified():
    limits = PackagingLimits()

    assert limits.title_max_chars == CONFIGURED_TITLE_MAX_CHARS
    assert limits.description_max_chars == CONFIGURED_DESCRIPTION_MAX_CHARS
    assert limits.tag_max_chars == CONFIGURED_TAG_MAX_CHARS
    assert limits.max_tags == CONFIGURED_MAX_TAGS
    assert limits.total_tag_chars == CONFIGURED_TOTAL_TAG_CHARS
    assert "não verific" in (packaging.__doc__ or "").lower()
    assert "api" in (packaging.__doc__ or "").lower()


def test_default_limits_do_not_reject_a_normal_package():
    assert package().limit_violations() == ()


def test_limit_violations_documents_that_configured_defaults_are_used():
    doc = (VideoPackaging.limit_violations.__doc__ or "").lower()

    assert "configurado" in doc
    assert "somente quando" not in (packaging.__doc__ or "").lower()


def test_contract_documents_that_consumers_must_revalidate():
    doc = (packaging.__doc__ or "").lower()

    assert "revalid" in doc
    assert "model_construct" in doc


def test_limit_violations_uses_the_explicit_limits_passed_in():
    item = package(title="T" * 20)

    violations = item.limit_violations(PackagingLimits(title_max_chars=10))

    assert any("title" in violation for violation in violations)
    assert item.limit_violations(PackagingLimits(title_max_chars=20)) == ()


def test_limit_violations_cover_description_tags_and_per_tag_length():
    item = package(
        description="D" * 30,
        tags=("a" * 12, "b" * 12),
    )
    limits = PackagingLimits(
        description_max_chars=10,
        tag_max_chars=5,
        max_tags=1,
        total_tag_chars=20,
    )

    violations = item.limit_violations(limits)

    assert any("description" in violation for violation in violations)
    assert any("tag" in violation for violation in violations)
    assert len(violations) >= 3


# --- tags ------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags",
    [
        ("manutenção", "manutenção"),
        ("Manutenção", "manutenção"),
        ("custo  industrial", "custo industrial"),
        ("#manutenção",),
        ("manutenção #industrial",),
        ("",),
        ("   ",),
    ],
)
def test_tags_reject_duplicates_after_normalization_hash_and_blanks(tags):
    with pytest.raises(ValidationError):
        package(tags=tags)


def test_tags_are_stored_normalized_without_surrounding_whitespace():
    item = package(tags=(" manutenção ", "custo industrial"))

    assert item.tags == ("manutenção", "custo industrial")


NFC_CAFE = unicodedata.normalize("NFC", "café")
NFD_CAFE = unicodedata.normalize("NFD", "café")


def test_tags_reject_nfc_nfd_duplicates_and_store_canonical_nfc():
    with pytest.raises(ValidationError):
        package(tags=(NFC_CAFE, NFD_CAFE))

    item = package(tags=(NFD_CAFE, "outra tag"))

    assert item.tags[0] == NFC_CAFE
    assert unicodedata.is_normalized("NFC", item.tags[0])


def test_tags_reject_compatibility_variants_after_nfkc_normalization():
    with pytest.raises(ValidationError):
        package(tags=("ABC", "\uff21\uff22\uff23"))


def test_chapter_titles_reject_nfc_nfd_duplicates():
    with pytest.raises(ValidationError):
        package(
            chapters=(
                Chapter(start_seconds=0, title=NFC_CAFE),
                Chapter(start_seconds=45, title=NFD_CAFE),
            )
        )


def test_variant_ids_are_unique_after_unicode_and_case_normalization():
    with pytest.raises(ValidationError):
        package(
            variants=(
                variant("v1", "Primeiro"),
                variant("V1", "Segundo"),
                variant("v3", "Terceiro"),
            )
        )

    with pytest.raises(ValidationError):
        package(
            variants=(
                variant(NFC_CAFE, "Primeiro"),
                variant(NFD_CAFE, "Segundo"),
                variant("v3", "Terceiro"),
            )
        )


def test_variant_thumbnail_concepts_must_be_distinct_after_normalization():
    with pytest.raises(ValidationError):
        package(
            variants=(
                variant("v1", "Primeiro", thumbnail_concept=NFC_CAFE),
                variant("v2", "Segundo", thumbnail_concept=NFD_CAFE),
                variant("v3", "Terceiro"),
            )
        )


# --- capítulos -------------------------------------------------------------


def test_valid_chapters_are_strictly_increasing_and_start_at_zero():
    item = package()

    starts = [chapter.start_seconds for chapter in item.chapters]
    assert starts == sorted(starts)
    assert starts[0] == 0
    assert item.chapters[2].timestamp == "03:00"


@pytest.mark.parametrize(
    "chapters",
    [
        (Chapter(start_seconds=45, title="Abertura"), Chapter(start_seconds=90, title="Problema")),
        (
            Chapter(start_seconds=0, title="Abertura"),
            Chapter(start_seconds=90, title="Problema"),
            Chapter(start_seconds=45, title="Volta"),
        ),
        (
            Chapter(start_seconds=0, title="Abertura"),
            Chapter(start_seconds=0, title="Problema"),
        ),
        (
            Chapter(start_seconds=0, title="Abertura"),
            Chapter(start_seconds=45, title="Abertura"),
        ),
        (
            Chapter(start_seconds=0, title="Abertura"),
            Chapter(start_seconds=45, title="ABERTURA"),
        ),
    ],
)
def test_chapters_reject_non_zero_first_out_of_order_and_duplicates(chapters):
    with pytest.raises(ValidationError):
        package(chapters=chapters)


def test_chapter_timestamp_is_derived_and_handles_hours():
    assert Chapter(start_seconds=0, title="Abertura").timestamp == "00:00"
    assert Chapter(start_seconds=45, title="Problema").timestamp == "00:45"
    assert Chapter(start_seconds=3723, title="Fecho").timestamp == "1:02:03"


def test_chapter_seconds_reject_negative_float_bool_and_string():
    for value in (-1, 1.5, True, "0"):
        with pytest.raises(ValidationError):
            Chapter(start_seconds=value, title="Abertura")


# --- fontes e CTA ----------------------------------------------------------


def test_sources_are_always_declared_because_sufficiency_is_not_verified():
    assert package(sources=(SourceCitation(name="Nota editorial declarada"),)).sources[0].url is None

    with pytest.raises(ValidationError):
        package(sources=())
    with pytest.raises(ValidationError):
        package(sources=(SourceCitation(name="   "),))
    with pytest.raises(ValidationError):
        package(sources=(SourceCitation(name="Fonte", url="  "),))


@pytest.mark.parametrize("value", ["", "   "])
def test_cta_must_be_present(value):
    with pytest.raises(ValidationError):
        package(cta=value)


# --- variantes -------------------------------------------------------------


def test_three_variants_are_accepted_and_none_is_marked_as_chosen():
    item = package()

    assert len(item.variants) == 3
    dumped = item.model_dump()

    for variant_dump in dumped["variants"]:
        assert "chosen" not in variant_dump
        assert "auto_selected" not in variant_dump
        assert "selected" not in variant_dump


def test_variants_are_optional_because_concepts_are_only_generated_when_applicable():
    assert package(variants=()).variants == ()


@pytest.mark.parametrize("count", [1, 2, 4, 5])
def test_variant_count_other_than_zero_or_three_is_rejected(count):
    with pytest.raises(ValidationError):
        package(variants=tuple(variant(f"v{index}", f"Título {index}") for index in range(count)))


def test_variants_require_stable_unique_ids_and_distinct_titles():
    with pytest.raises(ValidationError):
        package(variants=(variant("v1"), variant("v1", "Outro título"), variant("v3", "Terceiro título")))
    with pytest.raises(ValidationError):
        package(variants=(variant("v1"), variant("v2", "CONCEITO EDITORIAL V1"), variant("v3")))


@pytest.mark.parametrize(
    "changes",
    [
        {"rationale": "   "},
        {"title": "   "},
        {"thumbnail_concept": "   "},
        {"variant_id": "   "},
    ],
)
def test_variant_rejects_blank_identity_title_concept_and_rationale(changes):
    with pytest.raises(ValidationError):
        variant(**changes)


def test_variant_requires_an_explicit_title_claim():
    with pytest.raises(ValidationError):
        PackagingVariant(
            variant_id="v1",
            title="Sem declaração",
            thumbnail_concept="Conceito",
            rationale="Justificativa",
        )


def test_published_title_carries_its_own_claim():
    original = package(
        title_claim=claim(
            kind="declared_sensational_claim",
            statement="Promete eliminar todas as paradas",
        )
    )

    restored = VideoPackaging.model_validate_json(original.model_dump_json())

    assert restored.title_claim.kind == "declared_sensational_claim"


def test_published_title_claim_is_required():
    data = package(title_claim=claim()).model_dump()
    data.pop("title_claim")

    with pytest.raises(ValidationError):
        VideoPackaging.model_validate(data)


def test_sensational_variant_is_flagged_for_human_review_until_decided():
    sensational = variant(
        "v1",
        "Título sensacionalista",
        title_claim=claim(
            kind="declared_sensational_claim",
            statement="Promete resolver toda parada em uma semana",
        ),
    )

    pending = package(variants=(sensational, variant("v2"), variant("v3")))
    assert pending.unreviewed_sensational_variant_ids() == ("v1",)

    decided = package(
        variants=(sensational, variant("v2"), variant("v3")),
        decisions=(
            decision(
                variant_id="v1",
                decision="reject",
                rationale="A promessa declarada exagera a fonte",
            ),
        ),
    )
    assert decided.unreviewed_sensational_variant_ids() == ()


def test_decisions_must_reference_an_existing_variant_once():
    with pytest.raises(ValidationError):
        package(decisions=(decision(variant_id="v9"),))

    with pytest.raises(ValidationError):
        package(decisions=(decision(), decision(decision="reject")))


# --- declaração de promessa versus afirmação sensacionalista ---------------


def test_verifiable_promise_requires_a_statement():
    assert claim().statement == "O custo declarado no relatório anual"

    with pytest.raises(ValidationError):
        TitleClaim(kind="verifiable_promise", statement="   ")
    with pytest.raises(ValidationError):
        TitleClaim(kind="verifiable_promise", statement=None)


def test_sensational_claim_is_declared_and_not_judged_by_the_contract():
    declared = TitleClaim(
        kind="declared_sensational_claim",
        statement="Promete que a máquina nunca mais para",
    )

    assert declared.kind == "declared_sensational_claim"
    assert declared.statement == "Promete que a máquina nunca mais para"

    with pytest.raises(ValidationError):
        TitleClaim(kind="declared_sensational_claim", statement=None)


def test_no_claim_carries_no_statement():
    assert TitleClaim(kind="no_claim").statement is None

    with pytest.raises(ValidationError):
        TitleClaim(kind="no_claim", statement="Alguma promessa")
    with pytest.raises(ValidationError):
        TitleClaim(kind="guaranteed", statement="CTR garantido")


# --- estimativa de desempenho não é fato -----------------------------------


def test_performance_estimate_is_always_labelled_unverified_and_never_guaranteed():
    estimate = UnverifiedPerformanceEstimate(
        statement="Estimativa de maior retenção inicial",
        basis="Observação informal do canal",
    )

    assert estimate.label == "unverified_estimate"
    assert estimate.guarantees_performance is False

    with pytest.raises(ValidationError):
        UnverifiedPerformanceEstimate(
            statement="Retenção garantida",
            basis="Suposição",
            guarantees_performance=True,
        )
    with pytest.raises(ValidationError):
        UnverifiedPerformanceEstimate(
            statement="CTR garantido de 12%",
            basis="Suposição",
            label="guaranteed",
        )
    with pytest.raises(ValidationError):
        UnverifiedPerformanceEstimate(
            statement="Estimativa",
            basis="Suposição",
            guaranteed_ctr=0.12,
        )


def test_variant_has_no_field_for_performance_as_fact():
    with pytest.raises(ValidationError):
        variant(guaranteed_ctr=0.12)


# --- escolha humana, nunca automática --------------------------------------


def test_a_human_reviewer_can_accept_or_reject_a_variant():
    accepted = decision()
    rejected = decision(decision="reject", rationale="A afirmação declarada exagera a fonte")

    assert accepted.automatic is False
    assert rejected.decision == "reject"

    with pytest.raises(ValidationError):
        decision(automatic=True)
    with pytest.raises(ValidationError):
        decision(decision="auto")
    with pytest.raises(ValidationError):
        decision(decided_by="   ")
    with pytest.raises(ValidationError):
        decision(decided_at=datetime(2026, 11, 20, 12, 0))


def test_variant_itself_cannot_be_marked_as_chosen_automatically():
    with pytest.raises(ValidationError):
        variant(chosen=True)
    with pytest.raises(ValidationError):
        variant(auto_selected=True)


# --- versão ----------------------------------------------------------------


@pytest.mark.parametrize("value", [2, 0, 99])
def test_unknown_schema_version_is_rejected(value):
    with pytest.raises(ValidationError):
        package(schema_version=value)


def test_load_versioned_refuses_missing_schema_version():
    data = package().model_dump()
    data.pop("schema_version")

    with pytest.raises(ValueError):
        load_versioned(VideoPackaging, data)


def test_revision_must_be_a_positive_integer():
    assert package(revision=3).revision == 3

    for value in (0, -1, True, 1.5, "1"):
        with pytest.raises(ValidationError):
            package(revision=value)


# --- arquitetura -----------------------------------------------------------


def test_packaging_module_has_no_io_or_outward_imports():
    path = Path(packaging.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = (
        "app.studio.application",
        "app.studio.adapters",
        "app.studio.api",
        "app.studio.composition",
        "fastapi",
        "psycopg",
        "httpx",
        "subprocess",
        "requests",
        "os",
        "socket",
        "urllib.request",
        "http.client",
        "sqlalchemy",
    )

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)

    violations = {
        name
        for name in found
        if any(name == item or name.startswith(item + ".") for item in forbidden)
    }
    assert violations == set()