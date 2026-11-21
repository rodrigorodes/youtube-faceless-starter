"""Porta agnóstica para reserva preventiva de orçamento em USD e ciclo de vida da operação paga.

A reserva (tabela `budget_reservations`) bloqueia orçamento enquanto activa. Uma operação paga é a
intenção persistida ligada a essa reserva; só o chamador que obtém `CREATED` executa o provedor.
Confirmar remove a reserva registrando `ACTUAL` (cobrança comprovada), `ESTIMATE` (valor aproximado,
sujeito a reconciliação) ou `FREE` (zero); liberar remove a reserva sem gasto e marca a operação como
segura para repetir (`begin` reabre como nova tentativa). Um resultado ambíguo mantém a reserva e exige
reconciliação explícita antes de nova execução da mesma chave.
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol

from ..domain.contracts import UsageEntry
from .ports import ModelUnavailable

# Operação RESERVED sem atualização por este tempo é reportada como parada (não é encerrada sozinha:
# não há heartbeat, então uma chamada legítima mais longa também aparece — é visibilidade, não mutação).
STALLED_AFTER = timedelta(minutes=15)


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
    """A operação já foi confirmada: o resultado existe e não deve ser reexecutado.

    `state` diz qual estado terminal foi encontrado (`CONFIRMED` é o normal; `RELEASED` é defensivo).
    """

    def __init__(self, message: str, *, state: str | None = None):
        super().__init__(message)
        self.state = state


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
    """Declaração estruturada do custo: `ACTUAL` (cobrança comprovada), `ESTIMATE` (valor aproximado) ou `FREE`.

    `ACTUAL` só deve ser emitido com evidência de cobrança; a porta `provider_settlement` exige
    `ChargeEvidence` para isso. `ESTIMATE` conta como gasto aproximado e exige reconciliação.
    """

    kind: str
    amount_usd: Decimal
    reference: str
    confirmed_by: str

    def __post_init__(self) -> None:
        if self.kind not in ("ACTUAL", "ESTIMATE", "FREE"):
            raise ValueError("confirmation kind must be ACTUAL, ESTIMATE or FREE")
        if not isinstance(self.amount_usd, Decimal) or not self.amount_usd.is_finite() or self.amount_usd < 0:
            raise ValueError("confirmed amount must be a finite non-negative Decimal")
        if self.kind in ("ACTUAL", "ESTIMATE") and self.amount_usd <= 0:
            raise ValueError(f"{self.kind} confirmation requires a positive amount")
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
    def estimate(cls, amount_usd: Decimal, *, reference: str, confirmed_by: str) -> "CostConfirmation":
        return cls("ESTIMATE", _as_amount(amount_usd), reference, confirmed_by)

    @classmethod
    def free(cls, *, reference: str, confirmed_by: str) -> "CostConfirmation":
        return cls("FREE", Decimal("0"), reference, confirmed_by)


@dataclass(frozen=True)
class ChargeEvidence:
    """Evidência de cobrança declarada pelo adapter: valor cobrado, referência e quem declara."""

    amount_usd: Decimal
    reference: str
    declared_by: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_usd, Decimal) or not self.amount_usd.is_finite() or self.amount_usd <= 0:
            raise ValueError("charge evidence amount must be a positive finite Decimal")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("charge evidence reference is required")
        if not isinstance(self.declared_by, str) or not self.declared_by.strip():
            raise ValueError("charge evidence author is required")


@dataclass(frozen=True)
class PendingReconciliation:
    """Operação antiga, incerta ou parada que precisa de decisão humana; não bloqueia sozinha por si só."""

    idempotency_key: str
    video_id: str | None
    amount_usd: Decimal
    reason: str  # "stale_reservation" | "uncertain_operation" | "stalled_operation" | "legacy_unconfirmed_ledger" | "unknown_ledger_cost"
    created_at: datetime
    stalled_for: timedelta | None = None  # preenchido em "stalled_operation": tempo desde a última atualização


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


def provider_settlement(entry: UsageEntry, *, settled_by: str, charge: ChargeEvidence | None = None) -> tuple[UsageEntry, CostConfirmation]:
    """Encerra o custo declarado pelo provedor no `UsageEntry`.

    Com `charge` (evidência de cobrança do adapter) é `ACTUAL` e vale o valor cobrado; sem evidência,
    zero é `FREE` e positivo é `ESTIMATE` (valor aproximado, sujeito a reconciliação).
    `settled_by` nomeia explicitamente o ator/processo que encerra a operação (não um literal sintético).
    """
    if not isinstance(settled_by, str) or not settled_by.strip():
        raise ValueError("settled_by must name the process that settles the operation")
    if charge is not None:
        amount = _as_amount(charge.amount_usd)
        charged_entry = entry.model_copy(update={"cost_usd": float(amount)})
        return charged_entry, CostConfirmation.actual(amount, reference=charge.reference, confirmed_by=charge.declared_by)
    amount = _as_amount(entry.cost_usd)
    reference = f"provider:{entry.provider}:{entry.model}"
    if amount == 0:
        return entry, CostConfirmation.free(reference=reference, confirmed_by=settled_by)
    return entry, CostConfirmation.estimate(amount, reference=reference, confirmed_by=settled_by)


class PaidOperationRepository(Protocol):
    def begin(self, key: str, video_id: str | None, estimate_usd: Decimal, monthly_limit_usd: Decimal,
              video_limit_usd: Decimal) -> BeginResult:
        """Reserva + registra a intenção atomicamente. Só `CREATED` autoriza a execução externa.

        `video_id` pode ser `None` (operação de projeto, ex.: pontuar ideias): só o teto mensal se aplica.
        """
        ...

    def confirm(self, key: str, entry: UsageEntry, confirmation: CostConfirmation) -> None:
        """Numa transação: grava o lançamento (ACTUAL/ESTIMATE/FREE) no ledger, confirma e libera a reserva."""
        ...

    def reconcile_actual(self, key: str, charged_usd: Decimal, *, reference: str, confirmed_by: str) -> None:
        """Reconcilia uma operação com a cobrança comprovada (humano).

        Aceita `CONFIRMED` com `ESTIMATE` (troca o lançamento) e `UNCERTAIN` (fecha a operação
        inserindo o lançamento). `charged_usd = 0` converte para `FREE`; positivo vira `ACTUAL`.
        """
        ...

    def release(self, key: str, reason: str) -> None:
        """Libera a reserva sem gasto conhecido; registra o motivo.

        `RELEASED` significa "nenhum efeito externo, seguro repetir": `begin` reabre a mesma chave
        como nova tentativa (`attempt + 1`), com nova reserva.
        """
        ...

    def mark_uncertain(self, key: str, reason: str) -> None:
        """Mantém a reserva bloqueando e marca a operação como incerta, pendente de reconciliação."""
        ...

    def state(self, key: str) -> PaidOperationState | None:
        ...

    def settlement(self, key: str) -> CostConfirmation | None:
        """Confirmação registrada de uma operação CONFIRMED, ou None."""
        ...

    def pending_reconciliation(self, *, stale_after: timedelta = STALLED_AFTER) -> list[PendingReconciliation]:
        """Reservas antigas, operações incertas/paradas e lançamentos legados que exigem decisão explícita.

        `stale_after` define há quanto tempo uma operação `RESERVED` conta como parada.
        """
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

    def __init__(self, repo: PaidOperationRepository, monthly_limit_usd: Decimal, video_limit_usd: Decimal,
                 *, limits_for=None):
        self.repo = repo
        self.monthly_limit_usd = _require_amount(monthly_limit_usd, "monthly limit")
        self.video_limit_usd = _require_amount(video_limit_usd, "video limit")
        # `limits_for(video_id)` devolve (teto mensal, teto por vídeo) do canal, ou None para usar
        # os padrões da composição. É assim que o limite hard definido por canal chega ao guard.
        self.limits_for = limits_for

    def reserve(self, key: str, video_id: str | None, estimate_usd: Decimal) -> BeginResult:
        estimate_usd = _require_amount(estimate_usd, "estimate")
        monthly, video = self.monthly_limit_usd, self.video_limit_usd
        if self.limits_for is not None:
            override = self.limits_for(video_id)
            if override is not None:
                monthly = _require_amount(override[0], "monthly limit")
                video = _require_amount(override[1], "video limit")
        result = self.repo.begin(key, video_id, estimate_usd, monthly, video)
        if result is BeginResult.CREATED:
            return result
        if result is BeginResult.DENIED:
            raise BudgetDenied(f"budget denied for paid operation {key}")
        if result is BeginResult.IN_PROGRESS:
            raise OperationInProgress(f"paid operation {key} is already in progress")
        if result is BeginResult.UNCERTAIN:
            raise OperationUncertain(f"paid operation {key} is uncertain: reconcile before retrying")
        if result is BeginResult.CONFIRMED:
            raise OperationSettled(f"paid operation {key} was already confirmed", state="CONFIRMED")
        if result is BeginResult.RELEASED:
            # Defensivo: o repositório reabre RELEASED; se chegar aqui, não executar sem reconciliação.
            raise OperationSettled(f"paid operation {key} was already released", state="RELEASED")
        raise BudgetOperationError(f"unexpected begin result {result!r}")

    def confirm(self, key: str, entry: UsageEntry, confirmation: CostConfirmation) -> None:
        self.repo.confirm(key, entry, confirmation)

    def reconcile_actual(self, key: str, charged_usd: Decimal, *, reference: str, confirmed_by: str) -> None:
        self.repo.reconcile_actual(key, charged_usd, reference=reference, confirmed_by=confirmed_by)

    def release(self, key: str, reason: str) -> None:
        self.repo.release(key, reason)

    def mark_uncertain(self, key: str, reason: str) -> None:
        self.repo.mark_uncertain(key, reason)

    def pending_reconciliation(self, *, stale_after: timedelta = STALLED_AFTER) -> list[PendingReconciliation]:
        return self.repo.pending_reconciliation(stale_after=stale_after)

    def run(self, key: str, video_id: str | None, estimate_usd: Decimal, call, settle, *,
            validate=None, allow_free_replay: bool = False):
        """Reserva, executa `call` uma única vez e encerra o estado conforme o resultado.

        `validate(result)` roda depois da chamada paga e antes de encerrar o custo; se levantar, a
        operação fica UNCERTAIN (dinheiro pago, saída inutilizável). `settle(result)` devolve
        `(UsageEntry, CostConfirmation)`; `None` também fica UNCERTAIN. Falha ambígua mantém a reserva.
        `RELEASED` (falha pré-efeito) é reaberta como nova tentativa no próximo `begin`; `CONFIRMED` é
        terminal e `UNCERTAIN` exige reconciliação. Com `allow_free_replay`, uma operação já CONFIRMED
        como FREE é reexecutada sem nova cobrança.
        """
        try:
            self.reserve(key, video_id, estimate_usd)
        except OperationSettled:
            if allow_free_replay and self._confirmed_free(key):
                return call()  # gratuidade já comprovada: reexecutar não cobra
            raise
        try:
            result = call()
        except PreEffectFailure as exc:
            self.repo.release(key, f"pre-effect failure: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        except (KeyboardInterrupt, SystemExit):
            raise  # não engolir: a reserva fica RESERVED e exige reconciliação explícita
        except Exception as exc:  # resultado ambíguo: pode ter havido efeito externo pago
            self.repo.mark_uncertain(key, f"ambiguous failure: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        if validate is None:
            output = result
        else:
            try:
                output = validate(result)
            except PreEffectFailure as exc:
                self.repo.release(key, f"pre-effect validation failure: {type(exc).__name__}: {str(exc)[:200]}")
                raise
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:  # pago, mas a saída não serve: exige reconciliação, nunca ACTUAL silencioso
                self.repo.mark_uncertain(key, f"paid result rejected: {type(exc).__name__}: {str(exc)[:200]}")
                raise
        try:
            settlement = settle(result)
        except PreEffectFailure as exc:
            self.repo.release(key, f"pre-effect settlement failure: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:  # custo ilegível/não confirmável: manter incerto, nunca presumir zero
            self.repo.mark_uncertain(key, f"unconfirmable result: {type(exc).__name__}: {str(exc)[:200]}")
            raise
        if settlement is None:
            self.repo.mark_uncertain(key, "provider result has no confirmable cost")
            raise OperationUncertain(f"paid operation {key} has no confirmable cost")
        entry, confirmation = settlement
        try:
            self.repo.confirm(key, entry, confirmation)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            # a chamada externa aconteceu (dinheiro pode ter sido gasto), mas o custo não foi gravado:
            # não deixar RESERVED órfão; marca incerto para reconciliação e relança o erro original.
            reason = f"confirmation failed: {type(exc).__name__}: {str(exc)[:200]}"
            try:
                self.repo.mark_uncertain(key, reason)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as mark_exc:
                raise mark_exc from exc  # banco fora: preserva a exceção original como causa
            raise
        return output

    def _confirmed_free(self, key: str) -> bool:
        settlement = self.repo.settlement(key)
        return settlement is not None and settlement.kind == "FREE"
