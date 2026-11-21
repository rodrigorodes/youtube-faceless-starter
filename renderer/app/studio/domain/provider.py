"""Catálogo de providers e roteamento econômico (F10-03/F10-04). Puro: sem I/O, sem SDK.

Um provider só é AVAILABLE quando há uma implementação validada registrada; qualquer outra coisa é
UNAVAILABLE com motivo explícito — nunca finjo que funciona. Custo é honesto: FREE, ESTIMATE (com
valor) ou UNKNOWN; ausência de preço nunca é decimal zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum



class ProviderKind(str, Enum):
    """Portas de provider, iguais às chaves de `Project.config`."""

    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    RENDERER = "renderer"


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


# No perfil equilibrado, um provider que custa mais de N vezes o mais barato pago é "degrau caro"
# demais: fica fora enquanto houver opção mais em conta com qualidade comparável.
BALANCED_COST_FACTOR = Decimal("10")


class ProviderError(Exception):
    """Erro base de provider."""


class ProviderSpecInvalid(ProviderError, ValueError):
    """Especificação "<provedor>[:<modelo>]" vazia ou mal formada (o modelo é opcional)."""


class NoProviderAvailable(ProviderError, LookupError):
    """Nenhum candidato disponível satisfaz o perfil e o teto de custo."""


def _amount(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid monetary value: {value!r}") from exc


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
        if not isinstance(self.quality, int) or isinstance(self.quality, bool) or not (1 <= self.quality <= 5):
            raise ValueError("quality must be an integer between 1 and 5")
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
                            Availability.UNAVAILABLE, f"no implementation for {kind.value}:{name!r}")
    if not found.validated:
        return ProviderCard(kind, spec, name, model, found.capabilities, found.cost,
                            found.rate_limit_per_min, found.quality, Availability.UNAVAILABLE,
                            found.reason or "implementation not validated")
    return ProviderCard(kind, spec, name, model, found.capabilities, found.cost,
                        found.rate_limit_per_min, found.quality, Availability.AVAILABLE, None)


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
class RouteRequest:
    kind: ProviderKind
    profile: EconomicProfile = EconomicProfile.BALANCED
    max_cost_usd: Decimal | None = None

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


def _rank(profile: EconomicProfile, cards: list[ProviderCard]) -> list[ProviderCard]:
    if profile is EconomicProfile.ECONOMY:
        return sorted(cards, key=lambda c: (_cost_key(c), -c.quality, c.name))
    if profile is EconomicProfile.PREMIUM:
        return sorted(cards, key=lambda c: (-c.quality, _cost_key(c), c.name))
    # BALANCED: melhor qualidade entre opções que não pagam um múltiplo exagerado pelo degrau.
    paid = [_cost_key(c) for c in cards if _cost_key(c) > 0]
    ceiling = min(paid) * BALANCED_COST_FACTOR if paid else None
    affordable = [c for c in cards if ceiling is None or _cost_key(c) <= ceiling]
    return sorted(affordable, key=lambda c: (-c.quality, _cost_key(c), c.name))


def route_provider(request: RouteRequest, cards: object) -> RoutingDecision:
    """Escolhe o provider primário e a cadeia de fallback controlada.

    Só entram candidatos AVAILABLE dentro do teto. Desconhecido não é ilimitado: fica de fora quando
    há teto. Sem candidato, `NoProviderAvailable` (nunca devolve um provider inventado).
    """
    candidates = [c for c in cards if c.kind is request.kind and c.availability is Availability.AVAILABLE
                  and _within_cap(c, request.max_cost_usd)]
    if not candidates:
        cap = "" if request.max_cost_usd is None else f" sob o teto US$ {request.max_cost_usd}"
        raise NoProviderAvailable(f"no available {request.kind.value} provider for {request.profile.value}{cap}")
    ordered = _rank(request.profile, candidates)
    return RoutingDecision(request.kind, request.profile, ordered[0], tuple(ordered[1:]),
                           f"{request.profile.value}: {ordered[0].name} "
                           f"(custo {ordered[0].cost.label}, qualidade {ordered[0].quality})")
