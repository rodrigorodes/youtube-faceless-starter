"""Porta agnóstica para reserva preventiva de orçamento em USD e ciclo de vida da operação paga.

A reserva (tabela `budget_reservations`) bloqueia orçamento enquanto activa. Uma operação paga é a
intenção persistida ligada a essa reserva; só o chamador que obtém `CREATED` executa o provedor.
Confirmar (com custo real declarado) ou liberar remove a reserva; um resultado ambíguo mantém a
reserva e exige reconciliação explícita antes de nova execução da mesma chave.
"""
import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol

from ..domain.contracts import UsageEntry
from .ports import ModelUnavailable


class IdempotencyConflict(ValueError):
    """Uma chave já foi usada para uma solicitação diferente."""


class ReservationResult(str, Enum):
    CREATED = "CREATED"
    EXISTING = "EXISTING"
    DENIED = "DENIED"

    def __bool__(self) -> bool:
        raise TypeError("compare the reservation result explicitly")


class PaidOperationState(str, Enum):
    """Estado persistido da intenção de operação paga."""

    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    UNCERTAIN = "UNCERTAIN"


class BeginResult(str, Enum):
    """Decisão de `begin`: só `CREATED` autoriza executar o provedor."""

    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    UNCERTAIN = "UNCERTAIN"
    DENIED = "DENIED"

    def __bool__(self) -> bool:
        raise TypeError("compare the begin result explicitly")


class BudgetOperationError(RuntimeError):
    """A operação paga não pode prosseguir sob o estado persistido atual."""


class BudgetDenied(BudgetOperationError):
    """A reserva foi recusada pela política de orçamento."""


class OperationInProgress(BudgetOperationError):
    """Já existe uma operação reservada para a chave: não reexecutar."""


class OperationUncertain(BudgetOperationError):
    """O resultado anterior é ambíguo: reconciliar antes de tentar de novo."""


class OperationSettled(BudgetOperationError):
    """A operação já foi confirmada ou liberada: não reexecutar."""


class InvalidOperationTransition(BudgetOperationError):
    """Transição de estado incompatível com o estado persistido."""


class UnknownPaidOperation(LookupError):
    """Não existe operação paga registrada para a chave informada."""


class CostConfirmationError(ValueError):
    """A confirmação de custo não corresponde ao lançamento do provedor."""


class PreEffectFailure(ModelUnavailable):
    """Falha comprovadamente anterior a qualquer efeito externo pago; a reserva pode ser liberada."""


@dataclass(frozen=True)
class CostConfirmation:
    """Declaração estruturada do custo: `ACTUAL` positivo ou `FREE` zero, com evidência e responsável."""

    kind: str
    amount_usd: Decimal
    reference: str
    confirmed_by: str

    def __post_init__(self) -> None:
        if self.kind not in ("ACTUAL", "FREE"):
            raise ValueError("confirmation kind must be ACTUAL or FREE")
        if not isinstance(self.amount_usd, Decimal) or not self.amount_usd.is_finite() or self.amount_usd < 0:
            raise ValueError("confirmed amount must be a finite non-negative Decimal")
        if self.kind == "ACTUAL" and self.amount_usd <= 0:
            raise ValueError("ACTUAL confirmation requires a positive amount")
        if self.kind == "FREE" and self.amount_usd != 0:
            raise ValueError("FREE confirmation requires a zero amount")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("confirmation reference is required")
        if not isinstance(self.confirmed_by, str) or not self.confirmed_by.strip():
            raise ValueError("confirmation author is required")

    @classmethod
    def actual(cls, amount_usd: Decimal, *, reference: str, confirmed_by: str) -> "CostConfirmation":
        return cls("ACTUAL", _as_amount(amount_usd), reference, confirmed_by)

    @classmethod
    def free(cls, *, reference: str, confirmed_by: str) -> "CostConfirmation":
        return cls("FREE", Decimal("0"), reference, confirmed_by)


def _as_amount(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid monetary value: {value!r}") from exc


def _require_amount(value, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be a finite non-negative Decimal")
    return value


def paid_key(kind: str, *parts: object) -> str:
    """Chave de idempotência determinística: mesmas entradas, mesma operação."""
    payload = "|".join([kind, *[str(p) for p in parts]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provider_settlement(entry: UsageEntry, *, actor: str = "studio:provider-reported") -> tuple[UsageEntry, CostConfirmation]:
    """Confirma o custo declarado pelo próprio provedor no `UsageEntry` (ACTUAL se positivo, FREE se zero)."""
    amount = _as_amount(entry.cost_usd)
    reference = f"provider:{entry.provider}:{entry.model}"
    if amount == 0:
        return entry, CostConfirmation.free(reference=reference, confirmed_by=actor)
    return entry, CostConfirmation.actual(amount, reference=reference, confirmed_by=actor)


class PaidOperationRepository(Protocol):
    def begin(self, key: str, video_id: str, estimate_usd: Decimal, monthly_limit_usd: Decimal,
              video_limit_usd: Decimal) -> BeginResult:
        """Reserva + registra a intenção atomicamente. Só `CREATED` autoriza a execução externa."""
        ...

    def confirm(self, key: str, entry: UsageEntry, confirmation: CostConfirmation) -> None:
        """Numa transação: grava o lançamento confirmado no ledger, confirma a operação e libera a reserva."""
        ...

    def release(self, key: str, reason: str) -> None:
        """Libera a reserva sem gasto conhecido; registra o motivo."""
        ...

    def mark_uncertain(self, key: str, reason: str) -> None:
        """Mantém a reserva bloqueando e marca a operação como incerta, pendente de reconciliação."""
        ...

    def state(self, key: str) -> PaidOperationState | None:
        ...


class BudgetReservationRepository(Protocol):
    def reserve(
        self, key: str, video_id: str, amount: Decimal,
        monthly_limit: Decimal, video_limit: Decimal,
    ) -> ReservationResult:
        """Reserva atomicamente; DENIED indica limite ou custo desconhecido.

        Uma repetição idêntica retorna EXISTING; reutilização divergente falha.
        CREATED não garante exclusividade nem estado da operação externa:
        execução, retry e reconciliação exigem o protocolo de operação paga.
        """
        ...


class PaidOperationGuard:
    """Executa no máximo uma chamada paga por chave, atrás da reserva persistida.

    Sem reserva (`CREATED`) nada é executado. Falha conhecida sem efeito externo libera; falha
    ambígua mantém a reserva e exige reconciliação; sucesso só encerra com custo confirmado.
    """

    def __init__(self, repo: PaidOperationRepository, monthly_limit_usd: Decimal, video_limit_usd: Decimal):
        self.repo = repo
        self.monthly_limit_usd = _require_amount(monthly_limit_usd, "monthly limit")
        self.video_limit_usd = _require_amount(video_limit_usd, "video limit")

    def reserve(self, key: str, video_id: str, estimate_usd: Decimal) -> BeginResult:
        estimate_usd = _require_amount(estimate_usd, "estimate")
        result = self.repo.begin(key, video_id, estimate_usd, self.monthly_limit_usd, self.video_limit_usd)
        if result is BeginResult.CREATED:
            return result
        if result is BeginResult.DENIED:
            raise BudgetDenied(f"budget denied for paid operation {key}")
        if result is BeginResult.IN_PROGRESS:
            raise OperationInProgress(f"paid operation {key} is already in progress")
        if result is BeginResult.UNCERTAIN:
            raise OperationUncertain(f"paid operation {key} is uncertain: reconcile before retrying")
        if result is BeginResult.CONFIRMED:
            raise OperationSettled(f"paid operation {key} was already confirmed")
        if result is BeginResult.RELEASED:
            raise OperationSettled(f"paid operation {key} was already released")
        raise BudgetOperationError(f"unexpected begin result {result!r}")

    def confirm(self, key: str, entry: UsageEntry, confirmation: CostConfirmation) -> None:
        self.repo.confirm(key, entry, confirmation)

    def release(self, key: str, reason: str) -> None:
        self.repo.release(key, reason)

    def mark_uncertain(self, key: str, reason: str) -> None:
        self.repo.mark_uncertain(key, reason)

    def run(self, key: str, video_id: str, estimate_usd: Decimal, call, settle):
        """Reserva, executa `call` uma única vez e encerra o estado conforme o resultado.

        `settle(result)` devolve `(UsageEntry, CostConfirmation)` ou `None` quando o custo não é
        confirmável — nesse caso a operação fica incerta e bloqueada.
        """
        self.reserve(key, video_id, estimate_usd)
        try:
            result = call()
        except PreEffectFailure as exc:
            self.repo.release(key, f"pre-effect failure: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        except BaseException as exc:  # resultado ambíguo: pode ter havido efeito externo pago
            self.repo.mark_uncertain(key, f"ambiguous failure: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        try:
            settlement = settle(result)
        except PreEffectFailure:
            raise
        except BaseException as exc:  # custo ilegível/não confirmável: manter incerto, nunca presumir zero
            self.repo.mark_uncertain(key, f"unconfirmable result: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        if settlement is None:
            self.repo.mark_uncertain(key, "provider result has no confirmable cost")
            raise OperationUncertain(f"paid operation {key} has no confirmable cost")
        entry, confirmation = settlement
        self.repo.confirm(key, entry, confirmation)
        return result
