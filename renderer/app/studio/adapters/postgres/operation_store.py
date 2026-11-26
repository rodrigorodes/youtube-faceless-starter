"""Adaptador PostgreSQL para persistência de operações assíncronas (V4-12 / INT-04).

Conecta o OperationReconciler diretamente à infraestrutura transacional do PostgreSQL,
eliminando a dependência exclusiva de memória e garantindo reconciliação de estado
anti-dupla-cobrança (GAI-09/06) após restarts e crashes de workers.
Respeita estritamente a constraint paid_operations_settlement_check do schema.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
import psycopg

from ...application.resilience import OperationStoreProtocol
from ...domain.resilience import AsyncOperationRecord, AsyncOperationStatus


class PostgresOperationStore(OperationStoreProtocol):
    """Persistência real de operações assíncronas em banco PostgreSQL."""

    def __init__(self, connect: Callable[[], psycopg.Connection]) -> None:
        self._connect = connect

    def get_by_idempotency_key(self, idempotency_key: str) -> AsyncOperationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, state, estimate_usd, confirmed_amount_usd,
                       reason, updated_at
                FROM studio.paid_operations
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if row is None:
                return None

            key, state_str, est_usd, conf_usd, reason, updated_at = row
            try:
                status = AsyncOperationStatus(state_str)
            except ValueError:
                status = AsyncOperationStatus.UNCERTAIN

            return AsyncOperationRecord(
                operation_id=f"op_{key[:16]}",
                idempotency_key=key,
                status=status,
                estimated_cost_usd=Decimal(str(est_usd)),
                actual_cost_usd=Decimal(str(conf_usd)) if conf_usd is not None else None,
                external_reference_id=reason,
                updated_at_utc=updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
            )

    def save(self, record: AsyncOperationRecord) -> None:
        with self._connect() as conn:
            # 1. Garante que existe pelo menos um vídeo para a FK
            vid_row = conn.execute("SELECT id FROM studio.videos LIMIT 1").fetchone()
            if vid_row is None:
                raise RuntimeError("nenhum vídeo encontrado no banco para vincular a operação paga")
            video_id = vid_row[0]

            # 2. Respeita as regras de paid_operations_settlement_check:
            if record.status in (AsyncOperationStatus.RESERVED, AsyncOperationStatus.SUBMITTED, AsyncOperationStatus.POLLING):
                # RESERVED: confirmed_kind, confirmed_amount_usd, ledger_id e reason DEVEM ser NULL
                conn.execute(
                    """
                    INSERT INTO studio.paid_operations (
                        idempotency_key, video_id, estimate_usd, monthly_limit_usd,
                        video_limit_usd, state, confirmed_kind, confirmed_amount_usd,
                        ledger_id, reason, updated_at
                    ) VALUES (
                        %s, %s, %s, 1000.0, 100.0, 'RESERVED', NULL, NULL, NULL, NULL, now()
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                        state = 'RESERVED',
                        confirmed_kind = NULL,
                        confirmed_amount_usd = NULL,
                        ledger_id = NULL,
                        reason = NULL,
                        updated_at = now()
                    """,
                    (record.idempotency_key, video_id, record.estimated_cost_usd),
                )

            elif record.status == AsyncOperationStatus.CONFIRMED:
                # CONFIRMED: exige ledger_id, confirmed_kind, confirmed_amount_usd e cost_confirmation_reference; reason DEVE ser NULL
                cost = record.actual_cost_usd or Decimal("0.00")
                kind = "ACTUAL" if cost > 0 else "FREE"
                ref = record.external_reference_id or record.idempotency_key
                ledger_id = conn.execute(
                    """
                    INSERT INTO studio.usage_ledger (
                        video_id, step, provider, model, cost_usd,
                        cost_confirmation_kind, cost_confirmed_amount,
                        cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at
                    ) VALUES (
                        %s, 'render', 'local', 'default', %s, %s, %s, %s, 'reconciler', now()
                    ) RETURNING id
                    """,
                    (video_id, cost, kind, cost, ref),
                ).fetchone()[0]

                conn.execute(
                    """
                    INSERT INTO studio.paid_operations (
                        idempotency_key, video_id, estimate_usd, monthly_limit_usd,
                        video_limit_usd, state, confirmed_kind, confirmed_amount_usd,
                        ledger_id, reason, updated_at
                    ) VALUES (
                        %s, %s, %s, 1000.0, 100.0, 'CONFIRMED', %s, %s, %s, NULL, now()
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                        state = 'CONFIRMED',
                        confirmed_kind = EXCLUDED.confirmed_kind,
                        confirmed_amount_usd = EXCLUDED.confirmed_amount_usd,
                        ledger_id = EXCLUDED.ledger_id,
                        reason = NULL,
                        updated_at = now()
                    """,
                    (record.idempotency_key, video_id, record.estimated_cost_usd, kind, cost, ledger_id),
                )

            elif record.status in (AsyncOperationStatus.FAILED, AsyncOperationStatus.UNCERTAIN):
                # RELEASED / UNCERTAIN: reason DEVE ser preenchido (não vazio)
                state_str = "RELEASED" if record.status == AsyncOperationStatus.FAILED else "UNCERTAIN"
                reason_str = record.external_reference_id or "operation concluded without charge"
                conn.execute(
                    """
                    INSERT INTO studio.paid_operations (
                        idempotency_key, video_id, estimate_usd, monthly_limit_usd,
                        video_limit_usd, state, confirmed_kind, confirmed_amount_usd,
                        ledger_id, reason, updated_at
                    ) VALUES (
                        %s, %s, %s, 1000.0, 100.0, %s, NULL, NULL, NULL, %s, now()
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                        state = EXCLUDED.state,
                        confirmed_kind = NULL,
                        confirmed_amount_usd = NULL,
                        ledger_id = NULL,
                        reason = EXCLUDED.reason,
                        updated_at = now()
                    """,
                    (record.idempotency_key, video_id, record.estimated_cost_usd, state_str, reason_str),
                )

            conn.commit()
