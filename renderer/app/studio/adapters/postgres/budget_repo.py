"""Reserva conservadora serializada com gastos existentes no ledger e ciclo de vida da operação paga."""
from collections.abc import Callable
from decimal import Decimal

import psycopg

from ...application.budget import (BeginResult, CostConfirmation, CostConfirmationError, IdempotencyConflict,
                                   InvalidOperationTransition, PaidOperationState, PendingReconciliation,
                                   ReservationResult, UnknownPaidOperation)
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


def _reserve_within(conn: psycopg.Connection, key: str, video_id: str | None, amount: Decimal,
                    monthly_limit: Decimal, video_limit: Decimal) -> ReservationResult:
    """Insere a reserva se couber no orçamento; assume que o lock da transação já foi adquirido.

    O teto mensal soma gasto confirmado/estimado do mês corrente e reservas do mês corrente. Reservas
    de meses anteriores não consomem o mês atual (ficam em `pending_reconciliation`). Só custo `NaN`
    torna o valor realmente desconhecido; linha legada finita conta pelo valor gravado. Reserva sem
    vídeo (None) só é limitada pelo teto mensal.
    """
    previous = conn.execute(
        "SELECT video_id, amount_usd, monthly_limit_usd, video_limit_usd "
        "FROM studio.budget_reservations WHERE idempotency_key = %s", (key,)
    ).fetchone()
    if previous is not None:
        if previous != (video_id, amount, monthly_limit, video_limit):
            raise IdempotencyConflict("idempotency key already used")
        return ReservationResult.EXISTING
    permitted = conn.execute(
        """WITH bounds AS (
            SELECT date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start,
                   (date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC' AS finish
        ), spent AS (
            SELECT COALESCE(SUM(cost_usd) FILTER (WHERE created_at >= b.start AND created_at < b.finish), 0) AS month,
                   COALESCE(SUM(cost_usd) FILTER (WHERE video_id = %(video)s), 0) AS video,
                   COALESCE(BOOL_OR(
                       cost_usd = 'NaN'::numeric
                       AND (video_id = %(video)s OR (created_at >= b.start AND created_at < b.finish))
                   ), false) AS unknown
            FROM studio.usage_ledger, bounds b
        ), reserved AS (
            SELECT COALESCE(SUM(amount_usd) FILTER (WHERE created_at >= b.start AND created_at < b.finish), 0) AS month,
                   COALESCE(SUM(amount_usd) FILTER (WHERE video_id = %(video)s), 0) AS video
            FROM studio.budget_reservations, bounds b
        )
        SELECT NOT spent.unknown
           AND spent.month + reserved.month + %(amount)s <= %(monthly)s
           AND (%(video)s::text IS NULL OR spent.video + reserved.video + %(amount)s <= %(video_limit)s)
        FROM spent, reserved""",
        {"video": video_id, "amount": amount, "monthly": monthly_limit, "video_limit": video_limit},
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

    def begin(self, key: str, video_id: str | None, estimate_usd: Decimal, monthly_limit_usd: Decimal,
              video_limit_usd: Decimal) -> BeginResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        if video_id is not None:
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

    def settlement(self, key: str) -> CostConfirmation | None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        with _translated(), self._connect() as conn:
            row = conn.execute(
                "SELECT confirmed_kind, confirmed_amount_usd, cost_confirmation_reference, cost_confirmed_by "
                "FROM studio.paid_operations po JOIN studio.usage_ledger ul ON ul.id = po.ledger_id "
                "WHERE po.idempotency_key = %s AND po.state = 'CONFIRMED'", (key,)
            ).fetchone()
            if row is None or row[0] is None:
                return None
            return CostConfirmation(row[0], row[1], row[2], row[3])

    def reconcile_actual(self, key: str, charged_usd: Decimal, *, reference: str, confirmed_by: str) -> None:
        """Troca o ESTIMATE gravado por ACTUAL com a cobrança comprovada, numa transação."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        _validate_amounts(charged_usd)
        if charged_usd == 0:
            raise CostConfirmationError("ACTUAL reconciliation requires a positive charged amount")
        confirmation = CostConfirmation.actual(charged_usd, reference=reference, confirmed_by=confirmed_by)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            row = conn.execute(
                "SELECT state, confirmed_kind, ledger_id FROM studio.paid_operations "
                "WHERE idempotency_key = %s FOR UPDATE", (key,)
            ).fetchone()
            if row is None:
                raise UnknownPaidOperation(key)
            state, kind, ledger_id = row
            if state != "CONFIRMED" or kind != "ESTIMATE" or ledger_id is None:
                raise InvalidOperationTransition("only an ESTIMATE confirmation can be reconciled to ACTUAL")
            updated = conn.execute(
                "UPDATE studio.usage_ledger SET cost_usd = %s, cost_confirmation_kind = 'ACTUAL', "
                "cost_confirmed_amount = %s, cost_confirmation_reference = %s, cost_confirmed_by = %s, cost_confirmed_at = now() "
                "WHERE id = %s AND cost_confirmation_kind = 'ESTIMATE'",
                (confirmation.amount_usd, confirmation.amount_usd, confirmation.reference, confirmation.confirmed_by, ledger_id),
            )
            if updated.rowcount != 1:
                raise InvalidOperationTransition("estimate ledger row changed during reconciliation")
            conn.execute(
                "UPDATE studio.paid_operations SET confirmed_kind = 'ACTUAL', confirmed_amount_usd = %s, updated_at = now() "
                "WHERE idempotency_key = %s", (confirmation.amount_usd, key),
            )

    def pending_reconciliation(self) -> list[PendingReconciliation]:
        """Reservas de meses anteriores, operações UNCERTAIN e lançamentos legados não confirmados.

        Nada disso bloqueia o mês corrente por si só (exceto NaN, que continua desconhecido); é a lista
        que exige decisão explícita.
        """
        with _translated(), self._connect() as conn:
            rows = conn.execute(
                """WITH bounds AS (
                       SELECT date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start
                   )
                   SELECT br.idempotency_key, br.video_id, br.amount_usd, 'stale_reservation', br.created_at
                   FROM studio.budget_reservations br, bounds b WHERE br.created_at < b.start
                   UNION ALL
                   SELECT po.idempotency_key, po.video_id, po.estimate_usd, 'uncertain_operation', po.created_at
                   FROM studio.paid_operations po, bounds b
                   WHERE po.state = 'UNCERTAIN'
                     AND NOT EXISTS (SELECT 1 FROM studio.budget_reservations br2, bounds b2
                                     WHERE br2.idempotency_key = po.idempotency_key AND br2.created_at < b2.start)
                   UNION ALL
                   SELECT 'ledger:' || ul.id::text, ul.video_id, ul.cost_usd,
                          CASE WHEN ul.cost_usd = 'NaN'::numeric THEN 'unknown_ledger_cost'
                               ELSE 'legacy_unconfirmed_ledger' END, ul.created_at
                   FROM studio.usage_ledger ul
                   WHERE ul.cost_confirmation_kind IS NULL
                   ORDER BY 5""").fetchall()
        return [PendingReconciliation(row[0], row[1], row[2], row[3], row[4]) for row in rows]

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
