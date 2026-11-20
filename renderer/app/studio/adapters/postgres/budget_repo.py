"""Reserva conservadora serializada com gastos existentes no ledger."""
from collections.abc import Callable
from decimal import Decimal

import psycopg

from ...application.budget import IdempotencyConflict, ReservationResult
from ...domain.ids import check_id
from .repo import _translated


class PostgresBudgetRepository:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    def reserve(self, key: str, video_id: str, amount: Decimal,
                monthly_limit: Decimal, video_limit: Decimal) -> ReservationResult:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        check_id(video_id)
        for value in (amount, monthly_limit, video_limit):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("budget values must be finite non-negative Decimal")
        with _translated(), self._connect() as conn:
            if conn.autocommit:
                raise ValueError("autocommit is unsafe for budget reservations")
            # Uma conexão nova precisa de snapshot atualizado após aguardar o lock.
            conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            # Lock único, adquirido antes de qualquer leitura: também serializa vídeos distintos.
            conn.execute("SELECT pg_advisory_xact_lock(726002)")
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
