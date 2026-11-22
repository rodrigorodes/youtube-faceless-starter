"""Reserva conservadora serializada com gastos existentes no ledger e ciclo de vida da operação paga."""
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import psycopg

from ...application.budget import (BeginResult, BudgetDenial, CostConfirmation, CostConfirmationError,
                                   IdempotencyConflict, InvalidOperationTransition, PaidOperationState,
                                   PendingReconciliation, ReservationResult, STALLED_AFTER,
                                   UNKNOWN_COST_SCOPE, UnknownPaidOperation)
from ...domain.contracts import UsageEntry
from ...domain.ids import check_id
from .repo import _translated

_LOCK = 726002  # pg_advisory_xact_lock: serializa reservas e escritas do ledger


def _lock_budget(conn: psycopg.Connection) -> None:
    """Serializa reservas e escritas do ledger. Ordem de locks (estável, F01.T03):

    1. `pg_advisory_xact_lock(726002)` — sempre o primeiro, antes de qualquer leitura de orçamento;
    2. `studio.paid_operations` pela PK (`FOR UPDATE`), quando a chave existe;
    3. `studio.budget_reservations` pela PK (leitura, INSERT, DELETE);
    4. `studio.usage_ledger` em INSERT (o trigger `usage_ledger_budget_lock` retoma o MESMO advisory
       lock; dentro da transação a reaquisição do lock de transação é no-op).

    Como o lock 726002 é único e tomado antes de qualquer linha, duas transações de orçamento nunca
    seguram linha em ordem inversa — não há ciclo possível. Não adquirir outro lock antes dele.
    """
    if conn.autocommit:
        raise ValueError("autocommit is unsafe for budget reservations")
    # Uma conexão nova precisa de snapshot atualizado após aguardar o lock.
    conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    # Lock único, adquirido antes de qualquer leitura: também serializa vídeos distintos.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK,))


def _scope_project(conn: psycopg.Connection, video_id: str | None) -> str | None:
    """Projeto (canal) dono da operação; `None` é o escopo GLOBAL explícito.

    O vídeo é autoritativo: o projeto nunca vem do chamador. Operação sem vídeo (ex.: pontuar ideias)
    pertence ao escopo global e consome só o teto global — decisão registrada no ADR-002/F01.T03.
    """
    if video_id is None:
        return None
    row = conn.execute("SELECT project_id FROM studio.videos WHERE id = %s", (video_id,)).fetchone()
    if row is None:
        raise ValueError("unknown video for budget reservation")
    return row[0]


def _validate_amounts(*values) -> None:
    for value in values:
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("budget values must be finite non-negative Decimal")


def _reserve_within(conn: psycopg.Connection, key: str, video_id: str | None, project_id: str | None,
                    amount: Decimal, monthly_limit: Decimal, video_limit: Decimal,
                    global_monthly_limit: Decimal | None = None) -> ReservationResult:
    """Insere a reserva se couber nos tetos; pressupõe o lock de `_lock_budget` já adquirido.

    Três escopos independentes, todos verificados:
    - GLOBAL: gasto + reservas do mês corrente (todas as linhas) contra `global_monthly_limit`;
    - CANAL: gasto + reservas do mês do projeto do vídeo contra `monthly_limit`;
    - VÍDEO: gasto + reservas vitalícios do vídeo contra `video_limit`.

    Reservas de meses anteriores não consomem o mês atual (ficam em `pending_reconciliation`). Só custo
    `NaN` torna o valor realmente desconhecido; linha legada finita conta pelo valor gravado. Operação
    sem vídeo é escopo global explícito (`project_id IS NULL`): só o teto global a limita.
    `global_monthly_limit=None` recai em `monthly_limit` (compatível e nunca mais frouxo).
    """
    global_limit = monthly_limit if global_monthly_limit is None else global_monthly_limit
    previous = conn.execute(
        "SELECT video_id, amount_usd, monthly_limit_usd, video_limit_usd, project_id "
        "FROM studio.budget_reservations WHERE idempotency_key = %s", (key,)
    ).fetchone()
    if previous is not None:
        if tuple(previous) != (video_id, amount, monthly_limit, video_limit, project_id):
            raise IdempotencyConflict("idempotency key already used")
        return ReservationResult.EXISTING
    permitted = conn.execute(
        """WITH bounds AS (
            SELECT date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start,
                   (date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC' AS finish
        ), spent AS (
            SELECT COALESCE(SUM(ul.cost_usd) FILTER (
                       WHERE ul.created_at >= b.start AND ul.created_at < b.finish), 0) AS month,
                   COALESCE(SUM(ul.cost_usd) FILTER (
                       WHERE ul.project_id = %(project)s
                         AND ul.created_at >= b.start AND ul.created_at < b.finish), 0) AS project,
                   COALESCE(SUM(ul.cost_usd) FILTER (WHERE ul.video_id = %(video)s), 0) AS video,
                   COALESCE(BOOL_OR(
                       ul.cost_usd = 'NaN'::numeric
                       AND ((ul.created_at >= b.start AND ul.created_at < b.finish)
                            OR ul.video_id = %(video)s)
                   ), false) AS unknown
            FROM studio.usage_ledger ul, bounds b
        ), reserved AS (
            SELECT COALESCE(SUM(amount_usd) FILTER (
                       WHERE created_at >= b.start AND created_at < b.finish), 0) AS month,
                   COALESCE(SUM(amount_usd) FILTER (
                       WHERE project_id = %(project)s
                         AND created_at >= b.start AND created_at < b.finish), 0) AS project,
                   COALESCE(SUM(amount_usd) FILTER (WHERE video_id = %(video)s), 0) AS video
            FROM studio.budget_reservations, bounds b
        )
        SELECT NOT spent.unknown
           AND spent.month + reserved.month + %(amount)s <= %(global)s
           AND (%(project)s::text IS NULL
                OR spent.project + reserved.project + %(amount)s <= %(monthly)s)
           AND (%(video)s::text IS NULL
                OR spent.video + reserved.video + %(amount)s <= %(video_limit)s)
        FROM spent, reserved""",
        {"video": video_id, "project": project_id, "amount": amount, "global": global_limit,
         "monthly": monthly_limit, "video_limit": video_limit},
    ).fetchone()[0]
    if not permitted:
        return ReservationResult.DENIED
    conn.execute(
        "INSERT INTO studio.budget_reservations "
        "(idempotency_key, video_id, project_id, amount_usd, monthly_limit_usd, video_limit_usd) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (key, video_id, project_id, amount, monthly_limit, video_limit),
    )
    return ReservationResult.CREATED


class PostgresBudgetRepository:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def reserve(self, key: str, video_id: str | None, amount: Decimal,
                monthly_limit: Decimal, video_limit: Decimal,
                *, global_monthly_limit_usd: Decimal | None = None) -> ReservationResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        if video_id is not None:
            check_id(video_id)
        _validate_amounts(amount, monthly_limit, video_limit)
        if global_monthly_limit_usd is not None:
            _validate_amounts(global_monthly_limit_usd)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            project_id = _scope_project(conn, video_id)
            return _reserve_within(conn, key, video_id, project_id, amount, monthly_limit, video_limit,
                                   global_monthly_limit_usd)


class PostgresPaidOperationRepository:
    """Persiste a intenção da operação paga e mantém `budget_reservations` como o bloqueio ativo."""

    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def begin(self, key: str, video_id: str | None, estimate_usd: Decimal, monthly_limit_usd: Decimal,
              video_limit_usd: Decimal, *, global_monthly_limit_usd: Decimal | None = None) -> BeginResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        if video_id is not None:
            check_id(video_id)
        _validate_amounts(estimate_usd, monthly_limit_usd, video_limit_usd)
        if global_monthly_limit_usd is not None:
            _validate_amounts(global_monthly_limit_usd)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            project_id = _scope_project(conn, video_id)
            previous = conn.execute(
                "SELECT state, video_id, estimate_usd, monthly_limit_usd, video_limit_usd, project_id "
                "FROM studio.paid_operations WHERE idempotency_key = %s FOR UPDATE", (key,)
            ).fetchone()
            if previous is not None:
                if previous[1:] != (video_id, estimate_usd, monthly_limit_usd, video_limit_usd, project_id):
                    raise IdempotencyConflict("idempotency key already used")
                state = previous[0]
                if state == "RELEASED":
                    # Nenhum efeito externo comprovado: seguro repetir. Reabre como nova tentativa,
                    # com nova reserva, preservando as mesmas entradas (a chave é por conteúdo).
                    result = _reserve_within(conn, key, video_id, project_id, estimate_usd, monthly_limit_usd,
                                             video_limit_usd, global_monthly_limit_usd)
                    if result is ReservationResult.DENIED:
                        return BeginResult.DENIED
                    if result is ReservationResult.EXISTING:
                        return BeginResult.IN_PROGRESS  # reserva órfã: exige reconciliação
                    conn.execute(
                        "UPDATE studio.paid_operations SET state = 'RESERVED', attempt = attempt + 1, "
                        "reason = NULL, updated_at = now() WHERE idempotency_key = %s", (key,)
                    )
                    return BeginResult.CREATED
                return _begin_result(state)
            result = _reserve_within(conn, key, video_id, project_id, estimate_usd, monthly_limit_usd,
                                     video_limit_usd, global_monthly_limit_usd)
            if result is ReservationResult.DENIED:
                return BeginResult.DENIED
            if result is ReservationResult.EXISTING:
                # Reserva órfã sem registro de operação: não executar; exige reconciliação.
                return BeginResult.IN_PROGRESS
            conn.execute(
                "INSERT INTO studio.paid_operations "
                "(idempotency_key, video_id, project_id, estimate_usd, monthly_limit_usd, video_limit_usd, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'RESERVED')",
                (key, video_id, project_id, estimate_usd, monthly_limit_usd, video_limit_usd),
            )
            return BeginResult.CREATED

    def denial(self, video_id: str | None, estimate_usd: Decimal, monthly_limit_usd: Decimal,
               video_limit_usd: Decimal, *, global_monthly_limit_usd: Decimal | None = None) -> BudgetDenial:
        """Leitura pura: qual escopo estourou o teto, com os números (achado 3).

        Mesmos três escopos de `_reserve_within` (GLOBAL, CANAL, VÍDEO), na mesma ordem de
        precedência. Não escreve, não adquire o advisory lock e não altera estado.
        """
        if video_id is not None:
            check_id(video_id)
        _validate_amounts(estimate_usd, monthly_limit_usd, video_limit_usd)
        global_limit = monthly_limit_usd if global_monthly_limit_usd is None else global_monthly_limit_usd
        _validate_amounts(global_limit)
        with self._connect() as conn:
            project_id = _scope_project(conn, video_id)
            row = conn.execute(
                """WITH bounds AS (
                    SELECT date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start,
                           (date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC' AS finish
                ), spent AS (
                    SELECT COALESCE(SUM(ul.cost_usd) FILTER (
                               WHERE ul.created_at >= b.start AND ul.created_at < b.finish), 0) AS month,
                           COALESCE(SUM(ul.cost_usd) FILTER (
                               WHERE ul.project_id = %(project)s
                                 AND ul.created_at >= b.start AND ul.created_at < b.finish), 0) AS project,
                           COALESCE(SUM(ul.cost_usd) FILTER (WHERE ul.video_id = %(video)s), 0) AS video,
                           COALESCE(BOOL_OR(
                               ul.cost_usd = 'NaN'::numeric
                               AND ((ul.created_at >= b.start AND ul.created_at < b.finish)
                                    OR ul.video_id = %(video)s)
                           ), false) AS unknown
                    FROM studio.usage_ledger ul, bounds b
                ), reserved AS (
                    SELECT COALESCE(SUM(amount_usd) FILTER (
                               WHERE created_at >= b.start AND created_at < b.finish), 0) AS month,
                           COALESCE(SUM(amount_usd) FILTER (
                               WHERE project_id = %(project)s
                                 AND created_at >= b.start AND created_at < b.finish), 0) AS project,
                           COALESCE(SUM(amount_usd) FILTER (WHERE video_id = %(video)s), 0) AS video
                    FROM studio.budget_reservations, bounds b
                )
                SELECT spent.unknown, spent.month + reserved.month,
                       spent.project + reserved.project, spent.video + reserved.video
                FROM spent, reserved""",
                {"video": video_id, "project": project_id},
            ).fetchone()
        unknown, month, project, video = row
        if unknown:
            return BudgetDenial(UNKNOWN_COST_SCOPE, Decimal(0), Decimal(0), estimate_usd)
        if month + estimate_usd > global_limit:
            return BudgetDenial("GLOBAL (mês)", global_limit, month, estimate_usd)
        if project_id is not None and project + estimate_usd > monthly_limit_usd:
            return BudgetDenial("CANAL (mês)", monthly_limit_usd, project, estimate_usd)
        if video_id is not None and video + estimate_usd > video_limit_usd:
            return BudgetDenial("VÍDEO", video_limit_usd, video, estimate_usd)
        return BudgetDenial("política de orçamento", global_limit, month, estimate_usd)

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
        """Reconcilia com a cobrança comprovada, numa transação.

        `UNCERTAIN` fecha inserindo o lançamento (o resultado pago não tinha custo gravado);
        `CONFIRMED` + `ESTIMATE` troca o lançamento existente, sem duplicar. `0` converte para `FREE`.
        """
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        _validate_amounts(charged_usd)
        if charged_usd == 0:
            confirmation = CostConfirmation.free(reference=reference, confirmed_by=confirmed_by)
        else:
            confirmation = CostConfirmation.actual(charged_usd, reference=reference, confirmed_by=confirmed_by)
        with _translated(), self._connect() as conn:
            _lock_budget(conn)
            row = conn.execute(
                "SELECT state, confirmed_kind, ledger_id, video_id FROM studio.paid_operations "
                "WHERE idempotency_key = %s FOR UPDATE", (key,)
            ).fetchone()
            if row is None:
                raise UnknownPaidOperation(key)
            state, kind, ledger_id, video_id = row
            if state == PaidOperationState.CONFIRMED.value and kind == "ESTIMATE" and ledger_id is not None:
                updated = conn.execute(
                    "UPDATE studio.usage_ledger SET cost_usd = %s, cost_confirmation_kind = %s, "
                    "cost_confirmed_amount = %s, cost_confirmation_reference = %s, cost_confirmed_by = %s, "
                    "cost_confirmed_at = now() WHERE id = %s AND cost_confirmation_kind = 'ESTIMATE'",
                    (confirmation.amount_usd, confirmation.kind, confirmation.amount_usd,
                     confirmation.reference, confirmation.confirmed_by, ledger_id),
                )
                if updated.rowcount != 1:
                    raise InvalidOperationTransition("estimate ledger row changed during reconciliation")
                conn.execute(
                    "UPDATE studio.paid_operations SET confirmed_kind = %s, confirmed_amount_usd = %s, "
                    "updated_at = now() WHERE idempotency_key = %s",
                    (confirmation.kind, confirmation.amount_usd, key),
                )
                return
            if state == PaidOperationState.UNCERTAIN.value:
                new_ledger = conn.execute(
                    "INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, "
                    "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, "
                    "cost_confirmed_by, cost_confirmed_at) "
                    "VALUES (%s, 'reconciliation', 'manual', 'reconciliation', %s, %s, %s, %s, %s, now()) "
                    "RETURNING id",
                    (video_id, confirmation.amount_usd, confirmation.kind, confirmation.amount_usd,
                     confirmation.reference, confirmation.confirmed_by),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE studio.paid_operations SET state = 'CONFIRMED', confirmed_kind = %s, "
                    "confirmed_amount_usd = %s, ledger_id = %s, reason = NULL, updated_at = now() "
                    "WHERE idempotency_key = %s",
                    (confirmation.kind, confirmation.amount_usd, new_ledger, key),
                )
                conn.execute("DELETE FROM studio.budget_reservations WHERE idempotency_key = %s", (key,))
                return
            raise InvalidOperationTransition(
                "only an ESTIMATE confirmation or an UNCERTAIN operation can be reconciled")

    def pending_reconciliation(self, *, stale_after: timedelta = STALLED_AFTER) -> list[PendingReconciliation]:
        """Reservas de meses anteriores, operações UNCERTAIN, RESERVED paradas e legado não confirmado.

        `stalled_after` (padrão 15 min) é injetável para teste. Sem heartbeat, uma chamada legítima
        mais longa que o limiar também aparece: a lista é visibilidade, não encerramento automático.
        Nada disso bloqueia o mês corrente por si só (exceto NaN, que continua desconhecido).
        """
        if not isinstance(stale_after, timedelta) or stale_after < timedelta(0):
            raise ValueError("stale_after must be a non-negative timedelta")
        with _translated(), self._connect() as conn:
            rows = conn.execute(
                """WITH bounds AS (
                       SELECT date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start
                   )
                   SELECT br.idempotency_key, br.video_id, br.amount_usd, 'stale_reservation', br.created_at,
                          NULL::double precision
                   FROM studio.budget_reservations br, bounds b WHERE br.created_at < b.start
                   UNION ALL
                   SELECT po.idempotency_key, po.video_id, po.estimate_usd, 'uncertain_operation', po.created_at,
                          NULL::double precision
                   FROM studio.paid_operations po, bounds b
                   WHERE po.state = 'UNCERTAIN'
                     AND NOT EXISTS (SELECT 1 FROM studio.budget_reservations br2, bounds b2
                                     WHERE br2.idempotency_key = po.idempotency_key AND br2.created_at < b2.start)
                   UNION ALL
                   SELECT po.idempotency_key, po.video_id, po.estimate_usd, 'stalled_operation', po.created_at,
                          EXTRACT(EPOCH FROM (statement_timestamp() - po.updated_at))
                   FROM studio.paid_operations po
                   WHERE po.state = 'RESERVED'
                     AND po.updated_at < statement_timestamp() - %(stale)s::interval
                   UNION ALL
                   SELECT 'ledger:' || ul.id::text, ul.video_id, ul.cost_usd,
                          CASE WHEN ul.cost_usd = 'NaN'::numeric THEN 'unknown_ledger_cost'
                               ELSE 'legacy_unconfirmed_ledger' END, ul.created_at,
                          NULL::double precision
                   FROM studio.usage_ledger ul
                   WHERE ul.cost_confirmation_kind IS NULL
                   ORDER BY 5""", {"stale": stale_after}).fetchall()
        return [PendingReconciliation(row[0], row[1], row[2], row[3], row[4],
                                      timedelta(seconds=float(row[5])) if row[5] is not None else None)
                for row in rows]

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
