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
    PROFILE_POLICIES,
    REQUIRED_CAPABILITY,
    Availability,
    Capability,
    CostEstimate,
    CostKind,
    EconomicProfile,
    NoProviderAvailable,
    ProviderCard,
    ProviderKind,
    ProviderImplementation,
    ProviderSpecInvalid,
    ProviderStanding,
    RankingOrder,
    RouteRequest,
    RoutingDecision,
    capability_gaps,
    card_for,
    parse_spec,
    policy_for,
    provider_standing,
    registered_names,
    route_provider,
    satisfies_capability,
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
    # `min_quality=1` isola a regra do teto: o piso do perfil PREMIUM é coberto em
    # `test_profile_quality_floor_is_enforced` e o custo desconhecido em
    # `test_unknown_cost_is_refused_by_economy_and_balanced`.
    decision = route_provider(
        RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM, max_cost_usd=Decimal("0.05"),
                     min_quality=1), cards)
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


# ---------------------------------------------------------------- capabilities (F06.T01)


def test_every_port_declares_the_capability_it_requires():
    assert set(REQUIRED_CAPABILITY) == set(ProviderKind)
    assert REQUIRED_CAPABILITY[TEXT] is Capability.TEXT_GENERATE
    assert REQUIRED_CAPABILITY[IMAGE] is Capability.IMAGE_GENERATE
    assert REQUIRED_CAPABILITY[VOICE] is Capability.VOICE_SPEAK
    assert REQUIRED_CAPABILITY[ProviderKind.RENDERER] is Capability.RENDER_VIDEO


def test_a_declared_capability_set_must_include_the_port_capability():
    assert satisfies_capability(TEXT, ("text.generate", "text.json"))
    assert satisfies_capability(TEXT, (Capability.TEXT_GENERATE.value,))
    assert not satisfies_capability(TEXT, ("text.json",))          # declarou, mas não a da porta
    assert not satisfies_capability(IMAGE, ("text.generate",))
    # Metadados ausentes são legado (o adaptador ainda não declarou): não bloqueiam.
    assert satisfies_capability(TEXT, ())


def test_capability_gaps_reports_only_declared_divergences():
    impls = [
        impl(TEXT, "ok", validated=True, capabilities=("text.generate",)),
        impl(TEXT, "wrong", validated=True, capabilities=("image.generate",)),
        impl(IMAGE, "legacy", validated=True),  # sem metadados: legado, não é divergência
    ]
    assert capability_gaps(impls) == (("text", "wrong"),)


def test_a_card_without_the_port_capability_never_routes():
    cards = [
        card_for(TEXT, "sojson", [impl(TEXT, "sojson", validated=True, quality=5,
                                       capabilities=("text.json",), cost=CostEstimate.free())]),
        card_for(TEXT, "bom", [impl(TEXT, "bom", validated=True, quality=3,
                                    capabilities=("text.generate",), cost=CostEstimate.free())]),
    ]
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY), cards)
    assert decision.primary.name == "bom"
    assert all(c.name != "sojson" for c in decision.chain)


# ---------------------------------------------------------------- demo/placeholder (F06.T01)


def test_standing_comes_from_the_canonical_names_or_an_explicit_declaration():
    assert provider_standing("demo") is ProviderStanding.DEMO
    assert provider_standing("Placeholder") is ProviderStanding.PLACEHOLDER
    assert provider_standing("opencode") is ProviderStanding.PRODUCTION
    assert impl(TEXT, "demo", validated=True).standing is ProviderStanding.DEMO
    explicit = impl(TEXT, "acme", validated=True, standing=ProviderStanding.PLACEHOLDER)
    assert explicit.standing is ProviderStanding.PLACEHOLDER
    # o cartão carrega o mesmo veredito do catálogo
    assert card_for(TEXT, "demo", [impl(TEXT, "demo", validated=True)]).standing is ProviderStanding.DEMO


def _stand_in_cards():
    return [
        card_for(TEXT, "demo", [impl(TEXT, "demo", validated=True, quality=5, cost=CostEstimate.free())]),
        card_for(TEXT, "placeholder", [impl(TEXT, "placeholder", validated=True, quality=5,
                                            cost=CostEstimate.free())]),
        card_for(TEXT, "serio:top", [impl(TEXT, "serio", validated=True, quality=4,
                                          cost=CostEstimate.estimate(Decimal("0.30")))]),
    ]


def test_production_never_chooses_demo_or_placeholder():
    # Qualidade propositalmente alta nos stand-ins: a exclusão é por origem, não por nota.
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY, production=True),
                              _stand_in_cards())
    assert decision.primary.name == "serio"
    assert all(c.standing is ProviderStanding.PRODUCTION for c in decision.chain)
    assert "produção" in decision.reason


def test_production_with_only_stand_ins_fails_instead_of_pretending():
    cards = [card_for(TEXT, "demo", [impl(TEXT, "demo", validated=True, quality=5,
                                          cost=CostEstimate.free())])]
    with pytest.raises(NoProviderAvailable) as excinfo:
        route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY, production=True), cards)
    assert "production" in str(excinfo.value)


def test_development_keeps_stand_ins_available_until_the_wiring_says_otherwise():
    decision = route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY), _stand_in_cards())
    assert decision.primary.name == "demo"


# ---------------------------------------------------------------- política por perfil (F06.T01)


def test_each_profile_has_a_declared_and_coherent_policy():
    assert set(PROFILE_POLICIES) == set(EconomicProfile)
    for profile, policy in PROFILE_POLICIES.items():
        assert policy.profile is profile
        assert isinstance(policy.min_quality, int) and 1 <= policy.min_quality <= 5
        assert isinstance(policy.allows_unknown_cost, bool)
        assert isinstance(policy.ranking, RankingOrder)
    assert policy_for("ECONOMY") is PROFILE_POLICIES[EconomicProfile.ECONOMY]  # aceita o valor do enum
    assert PROFILE_POLICIES[EconomicProfile.ECONOMY].ranking is RankingOrder.COST_FIRST
    assert PROFILE_POLICIES[EconomicProfile.BALANCED].ranking is RankingOrder.COST_SWEET_SPOT
    assert PROFILE_POLICIES[EconomicProfile.PREMIUM].ranking is RankingOrder.QUALITY_FIRST
    # o perfil mais caro nunca aceita menos qualidade que o mais barato
    floors = [PROFILE_POLICIES[p].min_quality
              for p in (EconomicProfile.ECONOMY, EconomicProfile.BALANCED, EconomicProfile.PREMIUM)]
    assert floors == sorted(floors)
    assert [PROFILE_POLICIES[p].allows_unknown_cost
            for p in (EconomicProfile.ECONOMY, EconomicProfile.BALANCED)] == [False, False]


def _basic_only():
    return [card_for(TEXT, "basico", [impl(TEXT, "basico", validated=True, quality=1,
                                            cost=CostEstimate.free())])]


def test_profile_quality_floor_is_enforced():
    # ECONOMY aceita o básico; BALANCED e PREMIUM recusam catálogo só de nota 1.
    assert route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.ECONOMY),
                          _basic_only()).primary.name == "basico"
    for profile in (EconomicProfile.BALANCED, EconomicProfile.PREMIUM):
        with pytest.raises(NoProviderAvailable) as excinfo:
            route_provider(RouteRequest(kind=TEXT, profile=profile), _basic_only())
        assert "quality" in str(excinfo.value).lower()


def test_quality_floor_override_is_explicit_and_validated():
    decision = route_provider(
        RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM, min_quality=1), _basic_only())
    assert decision.primary.name == "basico"
    for bad in (0, 6, True, 2.5):
        with pytest.raises(ValueError):
            RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM, min_quality=bad)


def test_unknown_cost_is_refused_by_economy_and_balanced_but_allowed_in_premium():
    cards = [
        card_for(TEXT, "conhecido", [impl(TEXT, "conhecido", validated=True, quality=2,
                                           cost=CostEstimate.estimate(Decimal("0.01")))]),
        card_for(TEXT, "misterio", [impl(TEXT, "misterio", validated=True, quality=5,
                                          cost=CostEstimate.unknown())]),
    ]
    for profile in (EconomicProfile.ECONOMY, EconomicProfile.BALANCED):
        decision = route_provider(RouteRequest(kind=TEXT, profile=profile), cards)
        assert [c.name for c in decision.chain] == ["conhecido"]
    assert route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM),
                          cards).primary.name == "misterio"


def test_unknown_cost_can_be_allowed_explicitly_but_never_above_a_cap():
    unknown = [card_for(TEXT, "misterio", [impl(TEXT, "misterio", validated=True, quality=5,
                                                 cost=CostEstimate.unknown())])]
    assert route_provider(
        RouteRequest(kind=TEXT, profile=EconomicProfile.BALANCED, allow_unknown_cost=True),
        unknown).primary.name == "misterio"

    cards = unknown + [card_for(TEXT, "solido", [impl(TEXT, "solido", validated=True, quality=3,
                                                      cost=CostEstimate.estimate(Decimal("0.01")))])]
    decision = route_provider(
        RouteRequest(kind=TEXT, profile=EconomicProfile.PREMIUM, max_cost_usd=Decimal("0.05")), cards)
    assert decision.primary.name == "solido"
    assert all(c.name != "misterio" for c in decision.chain)  # desconhecido não é ilimitado


def test_no_candidate_reason_names_the_rule_that_excluded_the_catalog():
    unknown = [card_for(TEXT, "misterio", [impl(TEXT, "misterio", validated=True, quality=4,
                                                 cost=CostEstimate.unknown())])]
    with pytest.raises(NoProviderAvailable) as excinfo:
        route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.BALANCED), unknown)
    assert "unknown cost" in str(excinfo.value).lower()

    stand_ins = [card_for(TEXT, "demo", [impl(TEXT, "demo", validated=True, quality=4,
                                              cost=CostEstimate.free())])]
    with pytest.raises(NoProviderAvailable) as excinfo:
        route_provider(RouteRequest(kind=TEXT, profile=EconomicProfile.BALANCED, production=True),
                       stand_ins)
    message = str(excinfo.value)
    assert "non-production" in message
    assert "demo" not in message  # o motivo é a regra, não o nome de um candidato
