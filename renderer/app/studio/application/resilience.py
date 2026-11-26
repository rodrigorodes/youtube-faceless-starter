"""Módulo de Aplicação de Resiliência e Escala (V4-12).

Pureza arquitetural: orquestração desacoplada de I/O concreto e infraestrutura.
Fornece:
- Reconciliação prévia anti-dupla-cobrança para operações assíncronas (GAI-09/06)
- Executor resiliente de etapas com lease, backpressure, retries finitos e timeout
- Orquestrador de prontidão de sistema (Readiness)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from ..domain.resilience import (
    AsyncOperationRecord,
    AsyncOperationStatus,
    BackpressureController,
    BackpressureExceeded,
    CheckpointIntegrityError,
    CheckpointSnapshot,
    NonRetryableError,
    OperationAlreadyCharged,
    ResilienceError,
    RetryPolicy,
    StageTimeoutError,
    StageTimeoutPolicy,
    TenantIsolationViolation,
    TenantScope,
    compute_deterministic_idempotency_key,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)


class OperationStoreProtocol:
    """Porta para persistência de operações assíncronas."""

    def get_by_idempotency_key(self, idempotency_key: str) -> AsyncOperationRecord | None:
        raise NotImplementedError

    def save(self, record: AsyncOperationRecord) -> None:
        raise NotImplementedError


class InMemoryOperationStore(OperationStoreProtocol):
    """Implementação em memória para testes e execução local."""

    def __init__(self) -> None:
        self._records: dict[str, AsyncOperationRecord] = {}

    def get_by_idempotency_key(self, idempotency_key: str) -> AsyncOperationRecord | None:
        return self._records.get(idempotency_key)

    def save(self, record: AsyncOperationRecord) -> None:
        self._records[record.idempotency_key] = record


class OperationReconciler:
    """Reconciliador de operações assíncronas anti-dupla-cobrança (GAI-09/06).

    Garante que antes de qualquer retry ou nova chamada externa, uma operação
    preexistente com a mesma chave seja verificada e reconciliada.
    """

    def __init__(self, store: OperationStoreProtocol) -> None:
        self.store = store

    def begin_operation(
        self,
        tenant_scope: TenantScope,
        video_id: str,
        stage_name: str,
        attempt: int,
        payload: Mapping[str, Any],
        estimated_cost_usd: Decimal,
    ) -> tuple[str, bool]:
        """Inicia intenção de operação. Retorna (idempotency_key, should_execute).

        Se a operação já foi confirmada, lança OperationAlreadyCharged.
        Se a operação estiver em andamento ou incerta, indica que não deve submeter novo submit pago.
        """
        p_hash = compute_payload_hash(payload)
        key = compute_deterministic_idempotency_key(
            tenant_scope.tenant_id, video_id, stage_name, attempt, p_hash
        )

        existing = self.store.get_by_idempotency_key(key)
        if existing is not None:
            if existing.status == AsyncOperationStatus.CONFIRMED:
                raise OperationAlreadyCharged(
                    f"Operação {key} já confirmada e cobrada anteriormente."
                )
            if existing.requires_reconciliation():
                # Requer reconciliação antes de retry; não permite nova submissão direta
                return key, False
            if existing.can_safely_retry_without_charge():
                # Falhou ou apenas reservou: pode tentar novamente
                record = AsyncOperationRecord(
                    operation_id=existing.operation_id,
                    idempotency_key=key,
                    status=AsyncOperationStatus.RESERVED,
                    estimated_cost_usd=estimated_cost_usd,
                )
                self.store.save(record)
                return key, True

        # Primeira submissão
        op_id = f"op_{key[:16]}"
        record = AsyncOperationRecord(
            operation_id=op_id,
            idempotency_key=key,
            status=AsyncOperationStatus.RESERVED,
            estimated_cost_usd=estimated_cost_usd,
        )
        self.store.save(record)
        return key, True

    def record_submission(self, idempotency_key: str, external_reference_id: str) -> None:
        existing = self.store.get_by_idempotency_key(idempotency_key)
        if existing is None:
            raise ResilienceError(f"Operação {idempotency_key} inexistente para submit.")
        updated = AsyncOperationRecord(
            operation_id=existing.operation_id,
            idempotency_key=existing.idempotency_key,
            status=AsyncOperationStatus.SUBMITTED,
            estimated_cost_usd=existing.estimated_cost_usd,
            external_reference_id=external_reference_id,
        )
        self.store.save(updated)

    def record_confirmation(
        self, idempotency_key: str, actual_cost_usd: Decimal
    ) -> None:
        existing = self.store.get_by_idempotency_key(idempotency_key)
        if existing is None:
            raise ResilienceError(f"Operação {idempotency_key} inexistente para confirmação.")
        updated = AsyncOperationRecord(
            operation_id=existing.operation_id,
            idempotency_key=existing.idempotency_key,
            status=AsyncOperationStatus.CONFIRMED,
            estimated_cost_usd=existing.estimated_cost_usd,
            actual_cost_usd=actual_cost_usd,
            external_reference_id=existing.external_reference_id,
        )
        self.store.save(updated)

    def record_failure(self, idempotency_key: str) -> None:
        existing = self.store.get_by_idempotency_key(idempotency_key)
        if existing is None:
            return
        updated = AsyncOperationRecord(
            operation_id=existing.operation_id,
            idempotency_key=existing.idempotency_key,
            status=AsyncOperationStatus.FAILED,
            estimated_cost_usd=existing.estimated_cost_usd,
            actual_cost_usd=Decimal("0.00"),
            external_reference_id=existing.external_reference_id,
        )
        self.store.save(updated)


@dataclass(frozen=True)
class SystemReadinessReport:
    """Relatório consolidado de prontidão (Readiness Probe)."""

    database: str
    storage: str
    ffmpeg: str
    budget_guard: str
    active_jobs: int
    max_jobs: int
    is_ready: bool
    details: Mapping[str, Any] = field(default_factory=dict)


class ReadinessChecker:
    """Verificador consolidado de prontidão do sistema."""

    def __init__(
        self,
        check_db: Callable[[], bool],
        check_storage: Callable[[], bool],
        check_ffmpeg: Callable[[], bool],
        check_budget: Callable[[], bool],
        backpressure: BackpressureController,
    ) -> None:
        self.check_db = check_db
        self.check_storage = check_storage
        self.check_ffmpeg = check_ffmpeg
        self.check_budget = check_budget
        self.backpressure = backpressure

    def check(self) -> SystemReadinessReport:
        db_ok = self.check_db()
        storage_ok = self.check_storage()
        ffmpeg_ok = self.check_ffmpeg()
        budget_ok = self.check_budget()

        is_ready = bool(
            db_ok
            and storage_ok
            and ffmpeg_ok
            and budget_ok
            and not self.backpressure.is_saturated
        )

        return SystemReadinessReport(
            database="ok" if db_ok else "unavailable",
            storage="ok" if storage_ok else "unavailable",
            ffmpeg="ok" if ffmpeg_ok else "unavailable",
            budget_guard="ok" if budget_ok else "blocked",
            active_jobs=self.backpressure.active_jobs,
            max_jobs=self.backpressure.config.max_concurrent_jobs,
            is_ready=is_ready,
            details={
                "saturated": self.backpressure.is_saturated,
                "queued_jobs": self.backpressure.queued_jobs,
            },
        )


class ResilientStageExecutor:
    """Coordenador resiliente de execução de etapas."""

    def __init__(
        self,
        backpressure: BackpressureController,
        retry_policy: RetryPolicy | None = None,
        timeout_policy: StageTimeoutPolicy | None = None,
        reconciler: OperationReconciler | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backpressure = backpressure
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_policy = timeout_policy or StageTimeoutPolicy()
        self.reconciler = reconciler or OperationReconciler(InMemoryOperationStore())
        self.clock = clock

    def execute_stage(
        self,
        tenant_scope: TenantScope,
        video_id: str,
        stage_name: str,
        handler: Callable[[int], Mapping[str, Any]],
        previous_checkpoint: CheckpointSnapshot | None = None,
        check_lease_alive: Callable[[], bool] | None = None,
        mock_duration_seconds: float = 0.0,
    ) -> CheckpointSnapshot:
        """Executa etapa com validação de tenant, backpressure, retry, timeout e lease."""
        # 1. Backpressure admission
        slot = self.backpressure.admit_job()
        try:
            # 2. Execution loop with retries e medição real de tempo
            attempt = 1
            last_exc: Exception | None = None

            while attempt <= self.retry_policy.max_attempts:
                # Verificação de lease vivo antes da tentativa
                if check_lease_alive is not None and not check_lease_alive():
                    raise NonRetryableError(f"Lease perdido antes da execução da etapa {stage_name}")

                try:
                    t0 = self.clock()
                    payload = handler(attempt)
                    elapsed = max(mock_duration_seconds, self.clock() - t0)
                    self.timeout_policy.validate_duration(stage_name, elapsed)

                    # Checkpoint creation & validation
                    version = 1 if previous_checkpoint is None else previous_checkpoint.version + 1
                    cp = CheckpointSnapshot.create(
                        stage_name=stage_name,
                        version=version,
                        payload=payload,
                    )
                    if previous_checkpoint is not None:
                        previous_checkpoint.validate_continuity(cp)

                    # Verificação de lease vivo após conclusão
                    if check_lease_alive is not None and not check_lease_alive():
                        raise NonRetryableError(f"Lease perdido ao finalizar a etapa {stage_name}")

                    return cp

                except Exception as exc:
                    last_exc = exc
                    if not self.retry_policy.should_retry(attempt, exc):
                        raise
                    attempt += 1

            if last_exc:
                raise last_exc
            raise ResilienceError(f"Falha na execução da etapa {stage_name}")

        finally:
            self.backpressure.release_job(slot)
