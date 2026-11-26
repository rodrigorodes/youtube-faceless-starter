"""Catálogo de providers e roteamento econômico (F10-03/F10-04, F06.T01). Puro: sem I/O, sem SDK.

Um provider só é AVAILABLE quando há uma implementação validada registrada; qualquer outra coisa é
UNAVAILABLE com motivo explícito — nunca finjo que funciona. Custo é honesto: FREE, ESTIMATE (com
valor) ou UNKNOWN; ausência de preço nunca é decimal zero.

A política de roteamento (F06.T01) é declarada aqui, em dados testáveis:

- cada porta declara a capability que exige (`REQUIRED_CAPABILITY`); um cartão que declara
  capabilities sem a da porta não é elegível (metadados ausentes são legado e não bloqueiam);
- `demo`/`placeholder` são stand-ins (`ProviderStanding`) e nunca são escolhidos em produção;
- cada perfil econômico tem um `ProfilePolicy` com piso de qualidade, ordem de ranking e
  tolerância a custo desconhecido. Sem candidato elegível, `NoProviderAvailable` — nunca um
  provider inventado nem downgrade silencioso.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType



class ProviderKind(str, Enum):
    """Portas de provider. As chaves de ``Project.config`` são as portas de geração; ``SEARCH``
    é uma capacidade de catálogo que não exige configuração por projeto."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    RENDERER = "renderer"
    SEARCH = "search"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CostKind(str, Enum):
    FREE = "FREE"        # gratuito comprovado
    ESTIMATE = "ESTIMATE"  # valor aproximado declarado
    UNKNOWN = "UNKNOWN"  # preço não confirmado


class EconomicProfile(str, Enum):
    ECONOMY = "ECONOMY"
    BALANCED = "BALANCED"
    PREMIUM = "PREMIUM"


class ProviderStanding(str, Enum):
    """Origem declarada de uma implementação: só `PRODUCTION` executa em produção."""

    PRODUCTION = "PRODUCTION"
    DEMO = "DEMO"                # resposta determinística/local, não é um provedor real
    PLACEHOLDER = "PLACEHOLDER"  # mídia de enchimento, não é um provedor real


class Capability(str, Enum):
    """Capability base que cada porta exige de uma implementação."""

    TEXT_GENERATE = "text.generate"
    TEXT_JSON = "text.json"
    TEXT_REASONING = "text.reasoning"
    IMAGE_GENERATE = "image.generate"
    VIDEO_GENERATE = "video.generate"
    VOICE_SPEAK = "voice.speak"
    VOICE_NEURAL = "voice.neural"
    RENDER_VIDEO = "render.video"
    SEARCH_MEDIA = "search.media"


REQUIRED_CAPABILITY: Mapping[ProviderKind, Capability] = MappingProxyType({
    ProviderKind.TEXT: Capability.TEXT_GENERATE,
    ProviderKind.IMAGE: Capability.IMAGE_GENERATE,
    ProviderKind.VIDEO: Capability.VIDEO_GENERATE,
    ProviderKind.VOICE: Capability.VOICE_SPEAK,
    ProviderKind.RENDERER: Capability.RENDER_VIDEO,
    ProviderKind.SEARCH: Capability.SEARCH_MEDIA,
})

# Nomes canônicos de stand-ins: um adaptador que registra demo/placeholder usa estes nomes (ou
# declara `standing` explicitamente em `ProviderImplementation`). Classificar por nome evita
# duplicar a decisão em cada composição e mantém o catálogo auditável.
_NON_PRODUCTION_NAMES: Mapping[str, ProviderStanding] = MappingProxyType({
    "demo": ProviderStanding.DEMO,
    "mock": ProviderStanding.DEMO,
    "fake": ProviderStanding.DEMO,
    "sample": ProviderStanding.DEMO,
    "fixture": ProviderStanding.DEMO,
    "placeholder": ProviderStanding.PLACEHOLDER,
    "stub": ProviderStanding.PLACEHOLDER,
})


def provider_standing(name: object) -> ProviderStanding:
    """Origem padrão de um provider pelo nome canônico; desconhecido é PRODUCTION."""
    if not isinstance(name, str):
        raise ValueError("provider name must be a string")
    return _NON_PRODUCTION_NAMES.get(name.strip().lower(), ProviderStanding.PRODUCTION)


def satisfies_capability(kind: ProviderKind, capabilities: object) -> bool:
    """A implementação declara a capability da porta?

    Metadados ausentes representam adaptador legado que ainda não declarou nada: não bloqueiam
    (seria uma mudança de contrato silenciosa). Metadados declarados que não incluem a capability
    da porta bloqueiam — o cartão não pode prometer o que não faz.
    """
    declared = tuple(capabilities or ())
    if not declared:
        return True
    return REQUIRED_CAPABILITY[kind].value in declared


def capability_gaps(implementations: object) -> tuple[tuple[str, str], ...]:
    """(porta, nome) das implementações que declaram capabilities sem a da sua porta."""
    return tuple((impl.kind.value, impl.name) for impl in implementations
                 if not satisfies_capability(impl.kind, impl.capabilities))


# No perfil equilibrado, um provider que custa mais de N vezes o mais barato pago é "degrau caro"
# demais: fica fora enquanto houver opção mais em conta com qualidade comparável.
BALANCED_COST_FACTOR = Decimal("10")


class RankingOrder(str, Enum):
    """Como um perfil ordena os candidatos elegíveis."""

    COST_FIRST = "COST_FIRST"            # ECONOMY: o mais barato conhecido, depois qualidade
    COST_SWEET_SPOT = "COST_SWEET_SPOT"  # BALANCED: qualidade, sem pagar degrau exagerado
    QUALITY_FIRST = "QUALITY_FIRST"      # PREMIUM: maior qualidade, depois custo


class ProviderError(Exception):
    """Erro base de provider."""


class ProviderSpecInvalid(ProviderError, ValueError):
    """Especificação "<provedor>[:<modelo>]" vazia ou mal formada (o modelo é opcional)."""


class NoProviderAvailable(ProviderError, LookupError):
    """Nenhum candidato disponível satisfaz o perfil e o teto de custo."""


class ProviderTransientError(ProviderError):
    """Falha transitória (timeout, rede, erro 503 com retry viável)."""


class ProviderQuotaExceeded(ProviderError):
    """Limite de taxa (429) ou quota do provedor excedida."""


class ProviderBudgetBlocked(ProviderError):
    """Operação bloqueada preventivamente pelo BudgetGuard devido a teto de custo."""


class ProviderPermanentError(ProviderError):
    """Falha permanente (parâmetros inválidos, prompt bloqueado ou credencial rejeitada)."""


class ProviderMissingCredential(ProviderPermanentError):
    """Credencial necessária não configurada para o provedor."""


def _amount(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid monetary value: {value!r}") from exc


def _quality(value: object) -> int:
    """Nota de qualidade inteira de 1 (básico) a 5 (melhor); `True` não é nota."""
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 5):
        raise ValueError("quality must be an integer between 1 and 5")
    return value


@dataclass(frozen=True)
class CostEstimate:
    """Custo declarado de um provider. Nunca representa ausência como US$ 0,00.

    - `FREE` exige valor zero (ou ausente, que vira zero);
    - `ESTIMATE` exige valor positivo;
    - `UNKNOWN` exige valor ausente.
    """

    kind: CostKind
    amount_usd: Decimal | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CostKind):
            raise ValueError("cost kind must be a CostKind")
        if self.amount_usd is not None:
            amount = _amount(self.amount_usd)
            if not amount.is_finite() or amount < 0:
                raise ValueError("cost amount must be a finite non-negative Decimal")
            object.__setattr__(self, "amount_usd", amount)
        if self.kind is CostKind.UNKNOWN:
            if self.amount_usd is not None:
                raise ValueError("UNKNOWN cost must not carry an amount")
        elif self.kind is CostKind.FREE:
            if self.amount_usd is None:
                object.__setattr__(self, "amount_usd", Decimal("0"))
            elif self.amount_usd != 0:
                raise ValueError("FREE cost must be zero")
        elif self.kind is CostKind.ESTIMATE:
            if self.amount_usd is None or self.amount_usd <= 0:
                raise ValueError("ESTIMATE cost requires a positive amount")

    @classmethod
    def free(cls, note: str = "") -> "CostEstimate":
        return cls(CostKind.FREE, note=note)

    @classmethod
    def estimate(cls, amount_usd: object, note: str = "") -> "CostEstimate":
        return cls(CostKind.ESTIMATE, _amount(amount_usd), note)

    @classmethod
    def unknown(cls, note: str = "") -> "CostEstimate":
        return cls(CostKind.UNKNOWN, note=note)

    @property
    def label(self) -> str:
        if self.kind is CostKind.FREE:
            return "Sem custo"
        if self.kind is CostKind.UNKNOWN:
            return "Desconhecido"
        return f"Estimado US$ {self.amount_usd:.2f}".replace(".", ",")


@dataclass(frozen=True)
class ProviderLimits:
    """Formatos e limites técnicos declarados por um provedor (V4-01.04)."""

    max_duration_s: float | None = None
    min_duration_s: float | None = None
    supported_aspects: tuple[str, ...] = ("16:9", "9:16")
    supported_formats: tuple[str, ...] = ()
    max_chars: int | None = None


@dataclass(frozen=True)
class ProviderImplementation:
    """Metadados de uma implementação registrada por um adaptador (não executa nada)."""

    kind: ProviderKind
    name: str
    capabilities: tuple[str, ...] = ()
    cost: CostEstimate = field(default_factory=CostEstimate.unknown)
    rate_limit_per_min: int | None = None
    quality: int = 3  # 1 (básico) a 5 (melhor)
    validated: bool = False
    reason: str | None = None  # obrigatório quando `validated` é False
    standing: ProviderStanding | None = None  # ausente: derivado do nome canônico
    limits: ProviderLimits = field(default_factory=ProviderLimits)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProviderKind):
            raise ValueError("kind must be a ProviderKind")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("provider name is required")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        for cap in self.capabilities:
            if not isinstance(cap, str) or not cap.strip():
                raise ValueError("capabilities must be non-empty strings")
        _quality(self.quality)
        if self.standing is None:
            object.__setattr__(self, "standing", provider_standing(self.name))
        elif not isinstance(self.standing, ProviderStanding):
            raise ValueError("standing must be a ProviderStanding")
        if self.rate_limit_per_min is not None and (
            not isinstance(self.rate_limit_per_min, int) or isinstance(self.rate_limit_per_min, bool)
            or self.rate_limit_per_min <= 0
        ):
            raise ValueError("rate_limit_per_min must be a positive integer")
        if not self.validated and not (self.reason and self.reason.strip()):
            raise ValueError("an unvalidated provider must explain why")


@dataclass(frozen=True)
class ProviderCard:
    """Visão pública de um provider configurado para uma porta."""

    kind: ProviderKind
    spec: str
    name: str
    model: str
    capabilities: tuple[str, ...]
    cost: CostEstimate
    rate_limit_per_min: int | None
    quality: int
    availability: Availability
    reason: str | None = None
    standing: ProviderStanding | None = None  # ausente: derivado do nome canônico
    limits: ProviderLimits = field(default_factory=ProviderLimits)

    def __post_init__(self) -> None:
        if self.standing is None:
            object.__setattr__(self, "standing", provider_standing(self.name))
        elif not isinstance(self.standing, ProviderStanding):
            raise ValueError("standing must be a ProviderStanding")


def parse_spec(spec: object) -> tuple[str, str]:
    """Separa o spec em (provedor, modelo). O modelo é opcional: `demo:` é legítimo.

    Recusa só spec não-string, vazia, ou sem nome de provedor — nunca ecoa o valor cru de volta.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ProviderSpecInvalid("provider spec is required")
    name, _, model = spec.strip().partition(":")
    if not name:
        raise ProviderSpecInvalid("invalid provider spec: provider name is required")
    return name, model


def registered_names(implementations: object, kind: ProviderKind) -> tuple[str, ...]:
    """Nomes de implementações registradas para uma porta, na ordem do catálogo.

    É a fonte de verdade para aceitar/recusar um spec na escrita: um nome ausente aqui nunca
    vai construir — `provider_for` levantaria `ProviderNotFound` só em tempo de render.
    """
    names: list[str] = []
    for impl in implementations:
        if impl.kind is kind and impl.name not in names:
            names.append(impl.name)
    return tuple(names)


def card_for(kind: ProviderKind, spec: str, implementations: object) -> ProviderCard:
    """Monta o cartão de um spec contra as implementações registradas.

    Sem implementação, ou com implementação não validada, o cartão é UNAVAILABLE com o motivo.
    """
    name, model = parse_spec(spec)
    found = next((impl for impl in implementations if impl.kind is kind and impl.name == name), None)
    if found is None:
        return ProviderCard(kind, spec, name, model, (), CostEstimate.unknown(), None, 0,
                            Availability.UNAVAILABLE, f"no implementation for {kind.value}:{name!r}",
                            provider_standing(name))
    if not found.validated:
        return ProviderCard(kind, spec, name, model, found.capabilities, found.cost,
                            found.rate_limit_per_min, found.quality, Availability.UNAVAILABLE,
                            found.reason or "implementation not validated",
                            found.standing or ProviderStanding.PRODUCTION,
                            limits=found.limits)
    return ProviderCard(kind, spec, name, model, found.capabilities, found.cost,
                        found.rate_limit_per_min, found.quality, Availability.AVAILABLE, None,
                        found.standing or ProviderStanding.PRODUCTION,
                        limits=found.limits)


@dataclass(frozen=True)
class ProviderProbeResult:
    ok: bool
    detail: str


@dataclass(frozen=True)
class ConnectionTestResult:
    kind: ProviderKind
    spec: str
    name: str
    available: bool
    checked: bool  # True só quando uma sonda realmente rodou
    reason: str | None = None


@dataclass(frozen=True)
class ProfilePolicy:
    """Política declarada de um perfil econômico, em dados (testável, sem I/O).

    `min_quality` é o piso: candidato abaixo dele nunca entra, nem como fallback — rebaixar em
    silêncio seria mentir sobre o perfil. `allows_unknown_cost` diz se preço não confirmado pode
    ser escolhido quando não há teto; com teto, desconhecido nunca passa (`Infinity`).
    """

    profile: EconomicProfile
    min_quality: int
    ranking: RankingOrder
    allows_unknown_cost: bool
    balanced_cost_factor: Decimal = BALANCED_COST_FACTOR

    def __post_init__(self) -> None:
        if not isinstance(self.profile, EconomicProfile):
            raise ValueError("profile must be an EconomicProfile")
        _quality(self.min_quality)
        if not isinstance(self.ranking, RankingOrder):
            raise ValueError("ranking must be a RankingOrder")
        if not isinstance(self.allows_unknown_cost, bool):
            raise ValueError("allows_unknown_cost must be a bool")
        factor = _amount(self.balanced_cost_factor)
        if not factor.is_finite() or factor <= 0:
            raise ValueError("balanced_cost_factor must be a positive Decimal")
        object.__setattr__(self, "balanced_cost_factor", factor)


# Tabela da F06.T01. ECONOMY: sempre há uma opção (piso 1), preço tem de ser conhecido para ser
# "econômico". BALANCED: recusa o básico (nota 1) e o custo desconhecido, que estouraria o teto.
# PREMIUM: qualidade manda e tolera preço desconhecido quando não há teto; qualquer operação real
# passa um teto de orçamento, então desconhecido segue fora do caminho pago.
PROFILE_POLICIES: Mapping[EconomicProfile, ProfilePolicy] = MappingProxyType({
    EconomicProfile.ECONOMY: ProfilePolicy(
        EconomicProfile.ECONOMY, min_quality=1, ranking=RankingOrder.COST_FIRST,
        allows_unknown_cost=False),
    EconomicProfile.BALANCED: ProfilePolicy(
        EconomicProfile.BALANCED, min_quality=2, ranking=RankingOrder.COST_SWEET_SPOT,
        allows_unknown_cost=False),
    EconomicProfile.PREMIUM: ProfilePolicy(
        EconomicProfile.PREMIUM, min_quality=3, ranking=RankingOrder.QUALITY_FIRST,
        allows_unknown_cost=True),
})


def policy_for(profile: EconomicProfile | str) -> ProfilePolicy:
    """Política do perfil; aceita o valor do enum (`"ECONOMY"`) para bordas de API."""
    if not isinstance(profile, EconomicProfile):
        profile = EconomicProfile(profile)
    return PROFILE_POLICIES[profile]


@dataclass(frozen=True)
class RouteRequest:
    """Pedido de roteamento. Os padrões preservam o uso consultivo atual (dev, sem produção)."""

    kind: ProviderKind
    profile: EconomicProfile = EconomicProfile.BALANCED
    max_cost_usd: Decimal | None = None
    min_quality: int | None = None            # ausente: piso do perfil
    allow_unknown_cost: bool | None = None    # ausente: tolerância do perfil
    production: bool = False                  # True: exclui demo/placeholder e sinaliza no motivo

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProviderKind):
            raise ValueError("kind must be a ProviderKind")
        if not isinstance(self.profile, EconomicProfile):
            raise ValueError("profile must be an EconomicProfile")
        if self.max_cost_usd is not None:
            amount = _amount(self.max_cost_usd)
            if not amount.is_finite() or amount < 0:
                raise ValueError("max_cost_usd must be a finite non-negative Decimal")
            object.__setattr__(self, "max_cost_usd", amount)
        if self.min_quality is not None:
            _quality(self.min_quality)
        if self.allow_unknown_cost is not None and not isinstance(self.allow_unknown_cost, bool):
            raise ValueError("allow_unknown_cost must be a bool")
        if not isinstance(self.production, bool):
            raise ValueError("production must be a bool")


@dataclass(frozen=True)
class RoutingDecision:
    kind: ProviderKind
    profile: EconomicProfile
    primary: ProviderCard
    fallbacks: tuple[ProviderCard, ...]
    reason: str

    @property
    def chain(self) -> tuple[ProviderCard, ...]:
        return (self.primary, *self.fallbacks)


def _cost_key(card: ProviderCard) -> Decimal:
    """Chave de custo crescente. Desconhecido é o mais caro (não se pode limitar o gasto)."""
    if card.cost.kind is CostKind.FREE:
        return Decimal("0")
    if card.cost.kind is CostKind.ESTIMATE and card.cost.amount_usd is not None:
        return card.cost.amount_usd
    return Decimal("Infinity")


def _within_cap(card: ProviderCard, max_cost_usd: Decimal | None) -> bool:
    if max_cost_usd is None:
        return True
    return _cost_key(card) <= max_cost_usd


def _rank(policy: ProfilePolicy, cards: list[ProviderCard]) -> list[ProviderCard]:
    if policy.ranking is RankingOrder.COST_FIRST:
        return sorted(cards, key=lambda c: (_cost_key(c), -c.quality, c.name))
    if policy.ranking is RankingOrder.QUALITY_FIRST:
        return sorted(cards, key=lambda c: (-c.quality, _cost_key(c), c.name))
    # COST_SWEET_SPOT: melhor qualidade entre opções que não pagam um múltiplo exagerado pelo degrau.
    paid = [_cost_key(c) for c in cards if _cost_key(c) > 0]
    ceiling = min(paid) * policy.balanced_cost_factor if paid else None
    affordable = [c for c in cards if ceiling is None or _cost_key(c) <= ceiling]
    return sorted(affordable, key=lambda c: (-c.quality, _cost_key(c), c.name))


def _exclusion_reason(card: ProviderCard, *, min_quality: int, allow_unknown_cost: bool,
                      production: bool, max_cost_usd: Decimal | None) -> str | None:
    """Por que o cartão não é elegível; None quando é. Motivo é categoria, nunca o nome cru."""
    if production and card.standing is not ProviderStanding.PRODUCTION:
        return "non-production provider"
    if card.quality < min_quality:
        return f"quality {card.quality} below the profile floor {min_quality}"
    if not satisfies_capability(card.kind, card.capabilities):
        return "missing the port capability"
    if card.cost.kind is CostKind.UNKNOWN and not allow_unknown_cost:
        return "unknown cost"
    if not _within_cap(card, max_cost_usd):
        return "cost above the cap"
    return None


def route_provider(request: RouteRequest, cards: object) -> RoutingDecision:
    """Escolhe o provider primário e a cadeia de fallback controlada, sob a política do perfil.

    Filtros, nesta ordem: porta, AVAILABLE, origem (produção), piso de qualidade, capability,
    custo desconhecido e teto. Sem candidato, `NoProviderAvailable` — nunca devolve um provider
    inventado nem rebaixa o perfil em silêncio.
    """
    policy = policy_for(request.profile)
    min_quality = policy.min_quality if request.min_quality is None else request.min_quality
    allow_unknown = (policy.allows_unknown_cost if request.allow_unknown_cost is None
                     else request.allow_unknown_cost)

    candidates: list[ProviderCard] = []
    excluded: set[str] = set()
    for card in cards:
        if card.kind is not request.kind or card.availability is not Availability.AVAILABLE:
            continue
        reason = _exclusion_reason(card, min_quality=min_quality, allow_unknown_cost=allow_unknown,
                                   production=request.production, max_cost_usd=request.max_cost_usd)
        if reason is None:
            candidates.append(card)
        else:
            excluded.add(reason)
    if not candidates:
        detail = f"; excluded: {', '.join(sorted(excluded))}" if excluded else ""
        raise NoProviderAvailable(
            f"no available {request.kind.value} provider for {request.profile.value}{detail}")

    ordered = _rank(policy, candidates)
    primary = ordered[0]
    production_marker = " · produção" if request.production else ""
    return RoutingDecision(request.kind, request.profile, primary, tuple(ordered[1:]),
                           f"{request.profile.value}: {primary.name} "
                           f"(custo {primary.cost.label}, qualidade {primary.quality}){production_marker}")
