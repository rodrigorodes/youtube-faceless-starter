"""Testes do contrato de domínio do perfil de canal (puro, sem banco)."""
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.channel import (  # noqa: E402
    ChannelDurationInvalid,
    ChannelFieldInvalid,
    ChannelNameInvalid,
    ChannelProfile,
    ChannelVersionInvalid,
    MAX_PILLARS,
    clean_pillars,
)
from app.studio.domain.ids import InvalidId  # noqa: E402

PID = "a" * 32
CID = "b" * 32


def profile(**kw) -> ChannelProfile:
    base = {"id": CID, "project_id": PID, "name": "História"}
    base.update(kw)
    return ChannelProfile(**base)


def test_valid_profile_defaults():
    p = profile()
    assert p.name == "História"
    assert p.language == "pt-BR"
    assert p.target_duration_s == 60
    assert p.version == 1
    assert p.archived is False
    assert p.strategy == ""
    assert p.pillars == ()
    assert p.created_at is None and p.updated_at is None


def test_name_is_stripped_and_validated():
    assert profile(name="  História  ").name == "História"
    for bad in ("", "   ", "a" * 121, None, 123):
        with pytest.raises(ChannelNameInvalid):
            profile(name=bad)


def test_ids_must_be_hex32():
    with pytest.raises(InvalidId):
        profile(id="nope")
    with pytest.raises(InvalidId):
        profile(project_id="x" * 31)


def test_pillars_are_cleaned_deduped_and_capped():
    p = profile(pillars=["  IA ", "IA", "", "Robótica", "  ", "Análise"])
    assert p.pillars == ("IA", "Robótica", "Análise")
    assert isinstance(p.pillars, tuple)
    capped = profile(pillars=[f"p{i}" for i in range(30)])
    assert len(capped.pillars) == MAX_PILLARS
    assert capped.pillars == tuple(f"p{i}" for i in range(MAX_PILLARS))


def test_invalid_duration_rejected():
    for bad in (0, -1, 36001, "60", 1.5, True):
        with pytest.raises(ChannelDurationInvalid):
            profile(target_duration_s=bad)
    assert profile(target_duration_s=1).target_duration_s == 1


def test_invalid_version_rejected():
    for bad in (0, -1, "1", 1.0, True):
        with pytest.raises(ChannelVersionInvalid):
            profile(version=bad)


def test_other_fields_trimmed_and_bounded():
    assert profile(strategy="  nicho  ", cta="  compre  ").strategy == "nicho"
    with pytest.raises(ChannelFieldInvalid):
        profile(narrative="x" * 4001)
    with pytest.raises(ChannelFieldInvalid):
        profile(language="x")
    with pytest.raises(ChannelFieldInvalid):
        profile(audience=123)


def test_profile_is_immutable():
    p = profile()
    with pytest.raises(FrozenInstanceError):
        p.name = "novo"  # type: ignore[misc]


def test_pillars_are_deeply_immutable_and_hashable():
    source = ["IA", "Robótica"]
    p = profile(pillars=source)

    # a coleção do agregado é imutável: mutar falha em vez de alterar o perfil
    assert isinstance(p.pillars, tuple)
    with pytest.raises(AttributeError):
        p.pillars.append("INJETADO")  # type: ignore[attr-defined]

    # mutar a lista do chamador não vaza para o agregado
    source.append("INJETADO")
    assert p.pillars == ("IA", "Robótica")

    # e o agregado inteiro é hashable (collections imutáveis + escalares)
    assert hash(p) == hash(profile(pillars=["IA", "Robótica"]))
    assert {p: "ok"}[p] == "ok"


def test_replace_revalidates():
    p = profile()
    p2 = replace(p, version=2, name="Novo")
    assert p2.version == 2 and p2.name == "Novo"
    with pytest.raises(ChannelNameInvalid):
        replace(p, name="")


def test_clean_pillars_helper_returns_tuple():
    assert clean_pillars(None) == ()
    assert clean_pillars(["a", " a ", "b"]) == ("a", "b")
    assert clean_pillars(("a", "b")) == ("a", "b")  # aceita tupla e normaliza para tupla


def test_style_id_is_optional_but_validated_when_present():
    assert profile().style_id is None  # canal sem estilo é válido
    assert profile(style_id="c" * 32).style_id == "c" * 32
    with pytest.raises(InvalidId):
        profile(style_id="not-an-id")
    with pytest.raises(ChannelFieldInvalid):
        profile(style_id=42)
