"""Casos de uso de providers (F10-03/F10-04).

O catálogo é montado a partir do projeto (specs configurados) e das implementações registradas pelos
adaptadores. Nada aqui executa SDK de provedor: a sonda de conexão é uma porta (`ProviderProbe`).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from ..domain.ids import check_id
from ..domain.provider import (
    Availability,
    ConnectionTestResult,
    EconomicProfile,
    ProviderCard,
    ProviderImplementation,
    ProviderKind,
    RouteRequest,
    RoutingDecision,
    card_for,
    route_provider,
)
from .config import ProjectConfig
from .errors import ProjectNotFound
from .ports import ProviderProbe, VideoRepository


class ProviderService:
    def __init__(self, videos: VideoRepository, environ: Mapping[str, str],
                 implementations: Sequence[ProviderImplementation],
                 probes: Mapping[tuple[str, str], ProviderProbe] | None = None):
        self.videos = videos
        self.environ = environ
        self.implementations = tuple(implementations)
        self.probes = dict(probes or {})

    # -- configuração ------------------------------------------------------

    def configured(self, project_id: str | None) -> dict[str, str]:
        if project_id is None:
            return ProjectConfig.resolve({}, self.environ).model_dump()
        p_id = check_id(project_id)
        project = self.videos.get_project(p_id)
        if project is None:
            raise ProjectNotFound(p_id)
        return ProjectConfig.resolve(project.config, self.environ).model_dump()

    # -- catálogo ----------------------------------------------------------

    def list(self, project_id: str | None, kind: ProviderKind | None = None) -> list[ProviderCard]:
        configured = self.configured(project_id)
        kinds = (kind,) if kind is not None else tuple(ProviderKind)
        return [card_for(k, configured[k.value], self.implementations) for k in kinds]

    def test_connection(self, project_id: str | None, kind: ProviderKind,
                        spec: str | None = None) -> ConnectionTestResult:
        configured = self.configured(project_id)
        chosen = spec if spec is not None else configured[kind.value]
        card = card_for(kind, chosen, self.implementations)
        if card.availability is not Availability.AVAILABLE:
            # sem implementação validada: UNAVAILABLE, sem executar nada e sem fingir
            return ConnectionTestResult(kind, card.spec, card.name, available=False, checked=False,
                                        reason=card.reason)
        probe = self.probes.get((kind.value, card.name))
        if probe is None:
            return ConnectionTestResult(kind, card.spec, card.name, available=False, checked=False,
                                        reason="no connection probe is implemented for this provider")
        try:
            result = probe.probe(kind, card.spec)
        except Exception as exc:  # a sonda falhou: não vaza a mensagem crua (pode conter segredo)
            return ConnectionTestResult(kind, card.spec, card.name, available=False, checked=True,
                                        reason=f"connection probe failed ({type(exc).__name__})")
        return ConnectionTestResult(kind, card.spec, card.name, available=bool(result.ok), checked=True,
                                    reason=result.detail)

    # -- roteamento --------------------------------------------------------

    def candidates(self, kind: ProviderKind) -> list[ProviderCard]:
        """Cartões de todas as implementações da porta (o configurado entra mesmo sem implementação)."""
        cards: dict[str, ProviderCard] = {}
        for impl in self.implementations:
            if impl.kind is kind:
                cards.setdefault(impl.name, card_for(kind, impl.name, self.implementations))
        return list(cards.values())

    def route(self, project_id: str | None, kind: ProviderKind, profile: EconomicProfile,
              max_cost_usd: Decimal | None = None) -> RoutingDecision:
        if not isinstance(profile, EconomicProfile):
            profile = EconomicProfile(profile)
        configured = self.configured(project_id)
        cards = self.candidates(kind)
        # o provider explicitamente configurado abaixo pode não ter implementação: ele aparece
        # UNAVAILABLE e o roteador simplesmente o ignora (nunca finge disponibilidade).
        chosen = card_for(kind, configured[kind.value], self.implementations)
        if all(c.name != chosen.name for c in cards):
            cards.append(chosen)
        return route_provider(RouteRequest(kind, profile, max_cost_usd), cards)