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
    parse_spec,
    registered_names,
    route_provider,
)
from .config import ProjectConfig
from .errors import ProjectNotFound
from .ports import ProviderProbe, VideoRepository


class ProviderService:
    def __init__(self, videos: VideoRepository, environ: Mapping[str, str],
                 implementations: Sequence[ProviderImplementation],
                 probes: Mapping[tuple[str, str], ProviderProbe] | None = None,
                 production: bool = False):
        """`production=True` exclui demo/placeholder do roteamento (F06.T01).

        O padrão preserva o uso consultivo atual: a fiação de produção (F06.T02) é quem passa
        `production=True` — sem esse sinal, um stand-in continua aparecendo no painel de dev.
        """
        self.videos = videos
        self.environ = environ
        self.implementations = tuple(implementations)
        self.probes = dict(probes or {})
        self.production = bool(production)

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

    def _spec_for(self, configured: Mapping[str, str], kind: ProviderKind) -> str | None:
        """Spec do projeto para a porta; capacidades sem config (ex.: ``search``) usam o
        primeiro nome registrado no catálogo (preferindo uma implementação validada/disponível).
        ``None`` quando não há implementação."""
        spec = configured.get(kind.value)
        if spec:
            return spec
        validated_names = [impl.name for impl in self.implementations if impl.kind == kind and impl.validated]
        if validated_names:
            return f"{validated_names[0]}:"
        names = registered_names(self.implementations, kind)
        return f"{names[0]}:" if names else None

    def list(self, project_id: str | None, kind: ProviderKind | None = None) -> list[ProviderCard]:
        configured = self.configured(project_id)
        kinds = (kind,) if kind is not None else tuple(ProviderKind)
        cards: list[ProviderCard] = []
        for k in kinds:
            spec = self._spec_for(configured, k)
            if spec is not None:
                cards.append(card_for(k, spec, self.implementations))
        return cards

    def test_connection(self, project_id: str | None, kind: ProviderKind,
                        spec: str | None = None) -> ConnectionTestResult:
        configured = self.configured(project_id)
        chosen = spec if spec is not None else self._spec_for(configured, kind)
        if chosen is None:
            return ConnectionTestResult(kind, "", "", available=False, checked=False,
                                        reason="no provider configured for this port")
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

    def candidates(self, kind: ProviderKind, *, configured: str | None = None) -> list[ProviderCard]:
        """Cartões de todas as implementações da porta (o configurado entra mesmo sem implementação).

        Quando `configured` é o spec efetivo do projeto, a implementação de mesmo nome herda o
        modelo/versão configurado — a decisão roteada executa exatamente a versão que o projeto
        escolheu, não um nome solto que o registro não consegue construir.
        """
        configured_name = parse_spec(configured)[0] if configured else None
        cards: dict[str, ProviderCard] = {}
        for impl in self.implementations:
            if impl.kind is kind:
                spec = configured if configured is not None and impl.name == configured_name else impl.name
                cards.setdefault(impl.name, card_for(kind, spec, self.implementations))
        return list(cards.values())

    def route(self, project_id: str | None, kind: ProviderKind, profile: EconomicProfile,
              max_cost_usd: Decimal | None = None,
              production: bool | None = None,
              exclude: Sequence[str] = ()) -> RoutingDecision:
        """Roteia sob a política do perfil; `production=None` usa o modo do serviço.

        `exclude` nomeia candidatos que uma reavaliação explícita já descartou (provider decidido
        que não construiu). A exclusão é aplicada ao catálogo, nunca como downgrade silencioso:
        sem candidato restante, `NoProviderAvailable` explica a política.
        """
        if not isinstance(profile, EconomicProfile):
            profile = EconomicProfile(profile)
        configured = self.configured(project_id)
        excluded = frozenset(exclude)
        spec = self._spec_for(configured, kind)
        cards = [card for card in self.candidates(kind, configured=spec)
                 if card.name not in excluded]
        # o provider explicitamente configurado abaixo pode não ter implementação: ele aparece
        # UNAVAILABLE e o roteador simplesmente o ignora (nunca finge disponibilidade).
        if spec is not None:
            chosen = card_for(kind, spec, self.implementations)
            if chosen.name not in excluded and all(c.name != chosen.name for c in cards):
                cards.append(chosen)
        request = RouteRequest(kind, profile, max_cost_usd,
                               production=self.production if production is None else production)
        return route_provider(request, cards)
