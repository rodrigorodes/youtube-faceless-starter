"""Budget por canal/produção (F10-05): limites hard e soft distintos, custo honesto. Puro.

Hard bloqueia a operação; soft apenas sinaliza que a próxima etapa pede revisão humana. O guard da
fatia A não é hard limit por si: ele recebe os limites do chamador. Aqui o canal define os limites e
`guard_limits()` é o que liga o hard ao guard. O painel nunca funde Real com Estimado e nunca mostra
US$ 0,00 para ausência de uso.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum

from .ids import check_id
from .provider import EconomicProfile


class BudgetError(Exception):
    """Erro base de orçamento de canal."""


class BudgetLimitInvalid(BudgetError, ValueError):
    """Limite hard/soft inválido (negativo, não finito ou soft acima do hard)."""


def _amount(value: object, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise BudgetLimitInvalid(f"{field_name} must be a monetary value") from exc
    if not amount.is_finite() or amount < 0:
        raise BudgetLimitInvalid(f"{field_name} must be a finite non-negative Decimal")
    return amount


@dataclass(frozen=True)
class BudgetLimits:
    """Limites por canal (mensal e por produção/vídeo). Soft nunca passa do hard."""

    project_id: str
    hard_monthly_usd: Decimal
    soft_monthly_usd: Decimal
    hard_video_usd: Decimal
    soft_video_usd: Decimal
    economic_profile: EconomicProfile = EconomicProfile.BALANCED
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", check_id(self.project_id))
        hard_m = _amount(self.hard_monthly_usd, "hard_monthly_usd")
        soft_m = _amount(self.soft_monthly_usd, "soft_monthly_usd")
        hard_v = _amount(self.hard_video_usd, "hard_video_usd")
        soft_v = _amount(self.soft_video_usd, "soft_video_usd")
        if soft_m > hard_m:
            raise BudgetLimitInvalid("soft_monthly_usd must not exceed hard_monthly_usd")
        if soft_v > hard_v:
            raise BudgetLimitInvalid("soft_video_usd must not exceed hard_video_usd")
        if not isinstance(self.economic_profile, EconomicProfile):
            object.__setattr__(self, "economic_profile", EconomicProfile(self.economic_profile))
        object.__setattr__(self, "hard_monthly_usd", hard_m)
        object.__setattr__(self, "soft_monthly_usd", soft_m)
        object.__setattr__(self, "hard_video_usd", hard_v)
        object.__setattr__(self, "soft_video_usd", soft_v)

    def guard_limits(self) -> tuple[Decimal, Decimal]:
        """(teto mensal hard, teto por vídeo hard) para o guard de operação paga."""
        return (self.hard_monthly_usd, self.hard_video_usd)

    def is_blocked(self, estimate_usd: object) -> bool:
        estimate = _amount(estimate_usd, "estimate_usd")
        return estimate > self.hard_monthly_usd or estimate > self.hard_video_usd


class BudgetDecisionKind(str, Enum):
    WITHIN = "WITHIN"
    SOFT_LIMIT = "SOFT_LIMIT"
    HARD_BLOCKED = "HARD_BLOCKED"


@dataclass(frozen=True)
class BudgetDecision:
    scope: str
    kind: BudgetDecisionKind
    spent_usd: Decimal
    projected_usd: Decimal
    soft_usd: Decimal
    hard_usd: Decimal
    message: str


def evaluate_budget(spent_usd: object, estimate_usd: object, soft_usd: object, hard_usd: object,
                    *, scope: str) -> BudgetDecision:
    """Classifica o gasto projetado (gasto + estimativa) contra soft/hard do escopo."""
    spent = _amount(spent_usd, "spent_usd")
    estimate = _amount(estimate_usd, "estimate_usd")
    soft = _amount(soft_usd, "soft_usd")
    hard = _amount(hard_usd, "hard_usd")
    projected = spent + estimate
    if projected > hard:
        kind = BudgetDecisionKind.HARD_BLOCKED
        message = (f"{scope}: gasto projetado US$ {projected:.2f} passa do teto hard "
                   f"US$ {hard:.2f}: operação bloqueada")
    elif projected > soft:
        kind = BudgetDecisionKind.SOFT_LIMIT
        message = (f"{scope}: gasto projetado US$ {projected:.2f} passa do limite soft "
                   f"US$ {soft:.2f}: revisão humana recomendada")
    else:
        kind = BudgetDecisionKind.WITHIN
        message = f"{scope}: dentro do limite (projetado US$ {projected:.2f})"
    return BudgetDecision(scope, kind, spent, projected, soft, hard, message)


@dataclass(frozen=True)
class CostSummary:
    """Painel de custo honesto de um canal: Real/Estimado/Sem custo/Desconhecido, nunca fundidos.

    `spent_usd` (real + estimado) é o que consome o teto; estimado conta até ser reconciliado. As
    chamadas sem confirmação (legado) e as sem vínculo de vídeo não entram no gasto — são visibilidade.
    """

    real_usd: Decimal
    estimate_usd: Decimal
    free_calls: int
    unknown_calls: int
    unattributed_calls: int

    def __post_init__(self) -> None:
        for name in ("real_usd", "estimate_usd"):
            object.__setattr__(self, name, _amount(getattr(self, name), name))
        for name in ("free_calls", "unknown_calls", "unattributed_calls"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise BudgetLimitInvalid(f"{name} must be a non-negative integer")

    @property
    def spent_usd(self) -> Decimal:
        return self.real_usd + self.estimate_usd

    @property
    def has_usage(self) -> bool:
        return (self.real_usd > 0 or self.estimate_usd > 0
                or self.free_calls > 0 or self.unknown_calls > 0 or self.unattributed_calls > 0)

    def labels(self) -> dict[str, str]:
        def money(value: Decimal, prefix: str) -> str:
            return f"{prefix} US$ {value:.2f}".replace(".", ",") if value > 0 else "Sem registro de uso"

        return {
            "real": money(self.real_usd, "Real"),
            "estimate": money(self.estimate_usd, "Estimado"),
            "free": f"Sem custo em {self.free_calls} chamada(s)" if self.free_calls else "Sem registro de uso",
            "unknown": (f"Desconhecido em {self.unknown_calls} chamada(s)" if self.unknown_calls
                        else "Sem registro de uso"),
        }
