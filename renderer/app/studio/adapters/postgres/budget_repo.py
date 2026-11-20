"""Reserva conservadora serializada com gastos existentes no ledger e ciclo de vida da operação paga."""
from collections.abc import Callable
from decimal import Decimal

import psycopg

from ...application.budget import (BeginResult, CostConfirmation, CostConfirmationError, IdempotencyConflict,
                                   InvalidOperationTransition, PaidOperationState, ReservationResult, UnknownPaidOperation)
from ...domain.contracts import UsageEntry
from ...domain.ids import check_id
from .repo import _translated

_LOCK = 726002  # pg_advisory_xact_lock: serializa reservas e escritas do ledger


def _lock_budget(conn: psycopg.Connection) -> None:
    if conn.autocommit:
        raise ValueError("autocommit is unsafe for budget reservations")
    # Uma conexão nova precisa de snapshot atualizado após aguardar o lock.
    conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    # Lock único, adquirido antes de qualquer leitura: também serializa vídeos distintos.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK,))


def _validate_amounts(*values) -> None:
    for value in values:
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("budget values must be finite non-negative Decimal")


def _reserve_within(conn: psycopg.Connection, key: str, video_id: str, amount: Decimal,
                    monthly_limit: Decimal, video_limit: Decimal) -> ReservationResult:
    """Insere a reserva se couber no orçamento; assume que o lock da transação já foi adquirido."""
    previous = conn.execute(
        "SELECT video_id, amount_usd, monthly_limit_usd, video_limit_usd "
        "FROM studio.budget_reservations WHERE idempotency_key = %s", (key,)
    ).fetchone()
    if previous is not None:
        if previous != (video_id, amount, monthly_limit, video_limit):
            raise IdempotencyConflict("idempotency key already used")
        return ReservationResult.EXISTING
    permitted = conn.execute(
        """WITH spent AS (
            SELECT COALESCE(SUM(cost_usd) FILTER (
                WHERE created_at >= date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                  AND created_at < (date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC'
            ), 0) AS month, COALESCE(SUM(cost_usd) FILTER (WHERE video_id = %s), 0) AS video,
            COALESCE(BOOL_OR(
                (cost_usd = 'NaN'::numeric OR cost_confirmation_kind IS NULL)
                AND (video_id = %s OR
                    (created_at >= date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                     AND created_at < (date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC'))
            ), false) AS unknown
            FROM studio.usage_ledger
        ), reserved AS (
            SELECT COALESCE(SUM(amount_usd), 0) AS month,
                   COALESCE(SUM(amount_usd) FILTER (WHERE video_id = %s), 0) AS video
            FROM studio.budget_reservations
        )
        SELECT NOT spent.unknown AND spent.month + reserved.month + %s <= %s
           AND spent.video + reserved.video + %s <= %s
        FROM spent, reserved""",
        (video_id, video_id, video_id, amount, monthly_limit, amount, video_limit),
    ).fetchone()[0]
    if not permitted:
        return ReservationResult.DENIED
    conn.execute(
        "INSERT INTO studio.budget_reservations "
        "(idempotency_key, video_id, amount_usd, monthly_limit_usd, video_limit_usd) "
        "VALUES (%s, %s, %s, %s, %s)",
        (key, video_id, amount, monthly_limit, video_limit),
    )
    return ReservationResult.CREATED


class PostgresBudgetRepository:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def reserve(self, key: str, video_id: str, amount: Decimal,
                monthly_limit: Decimal, video_limit: Decimal) -> ReservationResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        check_id(video_id)
        _validate_amounts(amount, monthly_limit, video_limit)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            return _reserve_within(conn, key, video_id, amount, monthly_limit, video_limit)


class PostgresPaidOperationRepository:
    """Persiste a intenção da operação paga e mantém `budget_reservations` como o bloqueio ativo."""

    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def begin(self, key: str, video_id: str, estimate_usd: Decimal, monthly_limit_usd: Decimal,
              video_limit_usd: Decimal) -> BeginResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        check_id(video_id)
        _validate_amounts(estimate_usd, monthly_limit_usd, video_limit_usd)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            previous = conn.execute(
                "SELECT state, video_id, estimate_usd, monthly_limit_usd, video_limit_usd "
                "FROM studio.paid_operations WHERE idempotency_key = %s", (key,)
            ).fetchone()
            if previous is not None:
                if previous[1:] != (video_id, estimate_usd, monthly_limit_usd, video_limit_usd):
                    raise IdempotencyConflict("idempotency key already used")
                return _begin_result(previous[0])
            result = _reserve_within(conn, key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd)
            if result is ReservationResult.DENIED:
                return BeginResult.DENIED
            if result is ReservationResult.EXISTING:
                # Reserva órfã sem registro de operação: não executar; exige reconciliação.
                return BeginResult.IN_PROGRESS
            conn.execute(
                "INSERT INTO studio.paid_operations "
                "(idempotency_key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd, state) "
                "VALUES (%s, %s, %s, %s, %s, 'RESERVED')",
                (key, video_id, estimate_usd, monthly_limit_usd, video_limit_usd),
            )
            return BeginResult.CREATED

    def confirm(self, key: str, entry: UsageEntry, confirmation: CostConfirmation) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        if not isinstance(confirmation, CostConfirmation):
            raise TypeError("a structured cost confirmation is required")
        amount = _entry_amount(entry)
        if amount != confirmation.amount_usd:
            raise CostConfirmationError("confirmed amount does not match the recorded provider cost")
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            state, video_id = self._locked_state(conn, key)
            if state not in (PaidOperationState.RESERVED, PaidOperationState.UNCERTAIN):
                raise InvalidOperationTransition(f"cannot confirm a {state.value} operation")
            ledger_id = conn.execute(
                "INSERT INTO studio.usage_ledger(video_id, step, provider, model, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, cost_usd, cost_confirmation_kind, cost_confirmed_amount, "
                "cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) RETURNING id",
                (video_id, entry.step, entry.provider, entry.model, entry.input_tokens, entry.output_tokens,
                 entry.cache_read_tokens, entry.cache_write_tokens, amount, confirmation.kind, amount,
                 confirmation.reference, confirmation.confirmed_by),
            ).fetchone()[0]
            conn.execute(
                "UPDATE studio.paid_operations SET state = 'CONFIRMED', confirmed_kind = %s, "
                "confirmed_amount_usd = %s, ledger_id = %s, reason = NULL, updated_at = now() "
                "WHERE idempotency_key = %s",
                (confirmation.kind, amount, ledger_id, key),
            )
            conn.execute("DELETE FROM studio.budget_reservations WHERE idempotency_key = %s", (key,))

    def release(self, key: str, reason: str) -> None:
        self._settle_without_cost(key, reason, PaidOperationState.RELEASED, allow_from_uncertain=True)

    def mark_uncertain(self, key: str, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a reason is required")
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            state, _ = self._locked_state(conn, key)
            if state is PaidOperationState.UNCERTAIN:
                return
            if state is not PaidOperationState.RESERVED:
                raise InvalidOperationTransition(f"cannot mark a {state.value} operation as uncertain")
            conn.execute("UPDATE studio.paid_operations SET state = 'UNCERTAIN', reason = %s, updated_at = now() "
                         "WHERE idempotency_key = %s", (reason, key))

    def state(self, key: str) -> PaidOperationState | None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        with _translated(), self._connect() as conn:
            row = conn.execute("SELECT state FROM studio.paid_operations WHERE idempotency_key = %s", (key,)).fetchone()
            return None if row is None else PaidOperationState(row[0])

    def _settle_without_cost(self, key: str, reason: str, target: PaidOperationState, allow_from_uncertain: bool) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a reason is required")
        allowed = {PaidOperationState.RESERVED} | ({PaidOperationState.UNCERTAIN} if allow_from_uncertain else set())
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            state, _ = self._locked_state(conn, key)
            if state is target:
                return  # reconciliação idempotente
            if state not in allowed:
                raise InvalidOperationTransition(f"cannot move a {state.value} operation to {target.value}")
            conn.execute("UPDATE studio.paid_operations SET state = %s, reason = %s, updated_at = now() "
                         "WHERE idempotency_key = %s", (target.value, reason, key))
            conn.execute("DELETE FROM studio.budget_reservations WHERE idempotency_key = %s", (key,))

    @staticmethod
    def _locked_state(conn: psycopg.Connection, key: str) -> tuple[PaidOperationState, str]:
        row = conn.execute(
            "SELECT state, video_id FROM studio.paid_operations WHERE idempotency_key = %s FOR UPDATE", (key,)
        ).fetchone()
        if row is None:
            raise UnknownPaidOperation(key)
        return PaidOperationState(row[0]), row[1]


def _begin_result(state: str) -> BeginResult:
    return {"RESERVED": BeginResult.IN_PROGRESS, "CONFIRMED": BeginResult.CONFIRMED,
            "RELEASED": BeginResult.RELEASED, "UNCERTAIN": BeginResult.UNCERTAIN}[state]


def _entry_amount(entry: UsageEntry) -> Decimal:
    try:
        amount = Decimal(str(entry.cost_usd))
    except Exception as exc:  # valor ilegível nunca é tratado como zero
        raise CostConfirmationError("provider cost is not a usable number") from exc
    if not amount.is_finite() or amount < 0:
        raise CostConfirmationError("provider cost must be a finite non-negative number")
    return amount
