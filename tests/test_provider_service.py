"""Providers via aplicação (F10-03/F10-04): catálogo, teste de conexão e roteamento.

Usa projeto falso; sem banco. Prova que provider não validado aparece UNAVAILABLE e que o teste de
conexão nunca finge sucesso sem sonda.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.errors import ProjectNotFound  # noqa: E402
from app.studio.application.providers import ProviderService  # noqa: E402
from app.studio.domain.provider import (  # noqa: E402
    Availability,
    CostEstimate,
    EconomicProfile,
    ProviderImplementation,
    ProviderKind,
    ProviderProbeResult,
)

PID = "a" * 32
TEXT = ProviderKind.TEXT
IMAGE = ProviderKind.IMAGE


class FakeVideoRepo:
    def __init__(self, config=None):
        self.config = config or {}

    def get_project(self, project_id):
        if project_id != PID:
            return None
        return type("P", (), {"id": PID, "config": self.config})()


def implementations():
    return [
        ProviderImplementation(TEXT, "demo", capabilities=("text.generate",), cost=CostEstimate.free(),
                               quality=1, validated=True),
        ProviderImplementation(TEXT, "opencode", capabilities=("text.generate", "text.json"),
                               cost=CostEstimate.estimate(Decimal("0.02")), quality=4, validated=False,
                               reason="token do bridge ausente"),
        ProviderImplementation(IMAGE, "placeholder", cost=CostEstimate.free(), quality=1, validated=True),
    ]


class FakeProbe:
    def __init__(self, ok=True, detail="ok"):
        self.ok, self.detail, self.calls = ok, detail, []

    def probe(self, kind, spec):
        self.calls.append((kind, spec))
        return ProviderProbeResult(ok=self.ok, detail=self.detail)


def service(config=None, probes=None, environ=None):
    return ProviderService(FakeVideoRepo(config), environ or {}, implementations(), probes=probes)


def test_catalog_lists_configured_provider_with_availability():
    svc = service(environ={"STUDIO_TEXT": "demo", "STUDIO_IMAGE": "placeholder"})
    cards = {c.kind: c for c in svc.list(PID)}
    assert cards[TEXT].availability is Availability.AVAILABLE
    assert cards[TEXT].name == "demo"
    assert cards[IMAGE].availability is Availability.AVAILABLE


def test_catalog_marks_unvalidated_provider_unavailable():
    svc = service(environ={"STUDIO_TEXT": "opencode:gpt", "STUDIO_IMAGE": "placeholder"})
    cards = {c.kind: c for c in svc.list(PID)}
    assert cards[TEXT].availability is Availability.UNAVAILABLE
    assert "token" in cards[TEXT].reason


def test_catalog_unknown_provider_is_unavailable():
    svc = service(environ={"STUDIO_TEXT": "openai:gpt-4o"})
    card = [c for c in svc.list(PID) if c.kind is TEXT][0]
    assert card.availability is Availability.UNAVAILABLE
    assert "no implementation" in card.reason.lower()


def test_list_rejects_missing_project():
    with pytest.raises(ProjectNotFound):
        service().list("b" * 32)


def test_connection_test_runs_probe_and_reports_ok():
    probe = FakeProbe(ok=True, detail="respondeu")
    svc = service(environ={"STUDIO_TEXT": "demo"}, probes={(TEXT.value, "demo"): probe})
    result = svc.test_connection(PID, TEXT)
    assert result.available is True and result.checked is True
    assert result.reason == "respondeu"
    assert probe.calls == [(TEXT, "demo")]


def test_connection_test_refuses_unvalidated_without_probing():
    probe = FakeProbe(ok=True)
    svc = service(environ={"STUDIO_TEXT": "opencode:gpt"}, probes={(TEXT.value, "opencode"): probe})
    result = svc.test_connection(PID, TEXT)
    assert result.available is False and result.checked is False
    assert probe.calls == []
    assert "token" in result.reason


def test_connection_test_without_probe_does_not_pretend():
    svc = service(environ={"STUDIO_TEXT": "demo"})
    result = svc.test_connection(PID, TEXT)
    assert result.available is False and result.checked is False
    assert "sonda" in result.reason.lower() or "probe" in result.reason.lower()


def test_route_selects_by_profile_and_returns_fallbacks():
    # dois candidatos disponíveis: o configured e um extra injetado
    svc = ProviderService(FakeVideoRepo(), {}, implementations() + [
        ProviderImplementation(TEXT, "premium", cost=CostEstimate.estimate(Decimal("0.90")),
                              quality=5, validated=True),
    ])
    decision = svc.route(PID, TEXT, EconomicProfile.PREMIUM)
    assert decision.primary.name == "premium"
    assert any(c.name == "demo" for c in decision.fallbacks)
