"""Catálogo de providers (F10-03) e roteamento econômico (F10-04): testes puros, sem banco.

Regra central: um provider sem implementação validada aparece UNAVAILABLE — nunca finge funcionar.
Custo é honesto: FREE, ESTIMATE (valor) ou UNKNOWN; ausência nunca vira US$ 0,00.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.provider import (  # noqa: E402
    Availability,
    CostEstimate,
    CostKind,
    EconomicProfile,
    NoProviderAvailable,
    ProviderCard,
    ProviderKind,
    ProviderImplementation,
    ProviderSpecInvalid,
    RouteRequest,
    RoutingDecision,
    card_for,
    parse_spec,
    registered_names,
    route_provider,
)

TEXT = ProviderKind.TEXT
IMAGE = ProviderKind.IMAGE
VOICE = ProviderKind.VOICE


def impl(kind, name, **kw):
    return ProviderImplementation(kind=kind, name=name, **kw)


# ---------------------------------------------------------------- CostEstimate


def test_free_cost_is_known_zero_and_labelled():
    cost = CostEstimate.free(note="execução local")
    assert cost.kind is CostKind.FREE
    assert cost.amount_usd == Decimal("0")
    assert cost.label == "Sem custo"
    assert "0,00" not in cost.label


def test_unknown_cost_is_not_zero():
    cost = CostEstimate.unknown(note="preço não confirmado")
    assert cost.kind is CostKind.UNKNOWN
    assert cost.amount_usd is None
    assert cost.label == "Desconhecido"
    with pytest.raises(ValueError):
        CostEstimate(CostKind.UNKNOWN, Decimal("0"))


def test_estimate_requires_positive_amount():
    cost = CostEstimate.estimate(Decimal("0.15"), note="por imagem")
    assert cost.kind is CostKind.ESTIMATE
    assert cost.amount_usd == Decimal("0.15")
    assert cost.label == "Estimado US$ 0,15"
    for bad in (Decimal("0"), Decimal("-1"), None):
        with pytest.raises(ValueError):
            CostEstimate.estimate(bad)


def test_free_must_be_zero():
    with pytest.raises(ValueError):
        CostEstimate(CostKind.FREE, Decimal("1"))
    assert CostEstimate(CostKind.FREE).amount_usd == Decimal("0")


# ---------------------------------------------------------------- card_for


def test_implementation_without_validation_is_unavailable_and_says_why():
    card = card_for(TEXT, "openai:gpt-4o", [impl(TEXT, "openai", validated=False, reason="sem implementação homologada")])
    assert card.availability is Availability.UNAVAILABLE
    assert card.reason == "sem implementação homologada"


def test_unknown_implementation_is_unavailable_without_pretending():
    card = card_for(TEXT, "fal-ai:whatever", [])
    assert card.availability is Availability.UNAVAILABLE
    assert "no implementation" in card.reason.lower()


def test_validated_implementation_is_available_with_metadata():
    card = card_for(
        IMAGE,
        "placeholder",
        [impl(IMAGE, "placeholder", validated=True, capabilities=("image.generate",),
              cost=CostEstimate.free(), rate_limit_per_min=60, quality=1)],
    )
    assert card.availability is Availability.AVAILABLE
    assert card.name == "placeholder" and card.model == ""
    assert card.capabilities == ("image.generate",)
    assert card.cost.kind is CostKind.FREE
    assert card.rate_limit_per_min == 60
    assert card.reason is None


def test_model_keeps_the_full_suffix_after_first_colon():
    card = card_for(
        IMAGE,
        "opencode:openrouter/recraft-v4:free",
        [impl(IMAGE, "opencode", validated=True)],
    )
    assert card.model == "openrouter/recraft-v4:free"


def test_empty_spec_is_refused():
    with pytest.raises(ValueError):
        card_for(TEXT, "", [])


def test_parse_spec_keeps_optional_model_and_never_echoes_the_raw_value():
    assert parse_spec("demo") == ("demo", "")       # modelo opcional é legítimo
    assert parse_spec("demo:") == ("demo", "")
    assert parse_spec("piper:pt_BR-faber-medium") == ("piper", "pt_BR-faber-medium")
    assert parse_spec("opencode:a/b:free") == ("opencode", "a/b:free")  # só o 1º ":" separa
    for bad in (":x-do-not-echo", "   ", ""):
        with pytest.raises(ProviderSpecInvalid) as excinfo:
            parse_spec(bad)
        assert "do-not-echo" not in str(excinfo.value)  # mensagem sem o valor ofensor


def test_registered_names_lists_only_the_port_and_dedupes():
    impls = [impl(TEXT, "demo", validated=True), impl(TEXT, "opencode", validated=False, reason="sem token"),
             impl(IMAGE, "placeholder", validated=True)]
    assert registered_names(impls, TEXT) == ("demo", "opencode")   # mesma ordem do catálogo
    assert registered_names(impls, IMAGE) == ("placeholder",)
    assert registered_names(impls, VOICE) == ()


def test_implementation_validates_metadata():
    with pytest.raises(ValueError):
        impl(TEXT, "", validated=True)  # nome vazio
    with pytest.raises(ValueError):
        impl(TEXT, "x", validated=True, quality=9)
    with pytest.raises(ValueError):
        impl(TEXT, "x", validated=True, rate_limit_per_min=0)


# ---------------------------------------------------------------- route_provider


def _cards():
    return [
        card_for(TEXT, "demo", [impl(TEXT, "demo", validated=True, quality=1, cost=CostEstimate.free())]),
        card_for(TEXT, "opencode:cheap", [impl(TEXT, "opencode", validated=True, quality=2,
                                              cost=CostEstimate.estimate(Decimal("0.01"))) ]),
        card_for(TEXT, "premium:top", [impl(TEXT, "premium", validated=True, quality=5,
                                            cost=CostEstimate.estimate(Decimal("0.50")))]),
    ]


def test_economy_prefers_free_then_cheapest():
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY), _cards())
    assert isinstance(decision, RoutingDecision)
    assert decision.primary.name == "demo"
    assert [c.name for c in decision.fallbacks] == ["opencode", "premium"]


def test_premium_prefers_quality():
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM), _cards())
    assert decision.primary.name == "premium"
    assert decision.primary.quality == 5


def test_balanced_balances_quality_without_overpaying():
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.BALANCED), _cards())
    # qualidade 5 custa 50x mais que a de qualidade 2: o equilibrado escolhe a intermediária
    assert decision.primary.name == "opencode"


def test_cost_cap_excludes_estimate_above_cap_and_unknown_costs():
    cards = _cards() + [card_for(TEXT, "misterio:x", [impl(TEXT, "misterio", validated=True, quality=5,
                                                       cost=CostEstimate.unknown())])]
    decision = route_provider(
        RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM, max_cost_usd=Decimal("0.05")), cards)
    assert decision.primary.name == "opencode"
    assert all(c.name != "premium" for c in decision.fallbacks)
    assert all(c.name != "misterio" for c in decision.fallbacks)  # custo desconhecido não é ilimitado


def test_unavailable_providers_never_enter_the_fallback_chain():
    cards = _cards() + [card_for(TEXT, "off:line", [impl(TEXT, "off", validated=False, reason="fora do ar")])]
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY), cards)
    assert all(c.availability is Availability.AVAILABLE for c in (decision.primary, *decision.fallbacks))
    assert all(c.name != "off" for c in decision.fallbacks)


def test_no_candidate_raises_instead_of_pretending():
    with pytest.raises(NoProviderAvailable):
        route_provider(RouteRequest(kind=VOICE, profile=EconomicProfile.ECONOMY), _cards())
