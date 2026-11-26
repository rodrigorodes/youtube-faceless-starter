"""Módulo de Domínio de Resiliência e Escala (V4-12).

Pureza arquitetural estrita: sem I/O, sem banco, sem dependências externas.
Implementa os contratos e regras de domínio para:
- Checkpoints e integridade de estado
- Chaves determinísticas de idempotência
- Política de retry finito com backoff exponencial e classificação de erro
- Backpressure e limites de saturação
- Ciclo de vida e reconciliação de operações assíncronas (anti-dupla-cobrança GAI-09/06)
- Isolamento de tenant antes de SaaS
- Políticas de timeout por etapa
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence


class ResilienceError(Exception):
    """Erro base de resiliência e escala."""


class CheckpointIntegrityError(ResilienceError, ValueError):
    """Checkpoint violou a monotonicidade de versão ou integridade de dados."""


class BackpressureExceeded(ResilienceError, RuntimeError):
    """Capacidade máxima de concorrência ou fila atingida."""


class TenantIsolationViolation(ResilienceError, PermissionError):
    """Tentativa de acesso ou atribuição cruzada entre tenants diferentes."""


class OperationAlreadyCharged(ResilienceError, RuntimeError):
    """Tentativa de submeter cobrança duplicada para operação já confirmada."""


class StageTimeoutError(ResilienceError, TimeoutError):
    """A etapa excedeu o tempo limite determinístico configurado."""


class NonRetryableError(ResilienceError):
    """Erro terminal que não deve sofrer nova tentativa."""


def compute_deterministic_idempotency_key(
    tenant_id: str,
    video_id: str,
    stage_name: str,
    attempt: int,
    payload_hash: str,
) -> str:
    """Gera chave de idempotência determinística via SHA-256."""
    if not tenant_id or not video_id or not stage_name:
        raise ValueError("tenant_id, video_id e stage_name são obrigatórios")
    if attempt < 0:
        raise ValueError("attempt deve ser >= 0")
    raw = f"{tenant_id}:{video_id}:{stage_name}:{attempt}:{payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_payload_hash(payload: Mapping[str, Any]) -> str:
    """Calcula hash SHA-256 estável e determinístico de um dicionário JSON."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CheckpointSnapshot:
    """Snapshot imutável de checkpoint com verificação de integridade."""

    stage_name: str
    version: int
    payload: Mapping[str, Any]
    payload_hash: str
    created_at_utc: str

    def __post_init__(self) -> None:
        if not self.stage_name or not self.stage_name.strip():
            raise ValueError("stage_name não pode ser vazio")
        if self.version < 1:
            raise ValueError("version do checkpoint deve ser >= 1")
        computed = compute_payload_hash(self.payload)
        if self.payload_hash != computed:
            raise CheckpointIntegrityError(
                f"Hash do payload inválido: declarado={self.payload_hash}, calculado={computed}"
            )

    @classmethod
    def create(cls, stage_name: str, version: int, payload: Mapping[str, Any]) -> CheckpointSnapshot:
        p_hash = compute_payload_hash(payload)
        now_str = datetime.now(timezone.utc).isoformat()
        return cls(
            stage_name=stage_name,
            version=version,
            payload=dict(payload),
            payload_hash=p_hash,
            created_at_utc=now_str,
        )

    def validate_continuity(self, next_checkpoint: CheckpointSnapshot) -> None:
        """Assegura que o próximo checkpoint é monotônico e da mesma etapa."""
        if next_checkpoint.stage_name != self.stage_name:
            raise CheckpointIntegrityError(
                f"Etapa divergente: esperado {self.stage_name}, recebido {next_checkpoint.stage_name}"
            )
        if next_checkpoint.version != self.version + 1:
            raise CheckpointIntegrityError(
                f"Versão não monotônica: atual={self.version}, próximo={next_checkpoint.version}"
            )


@dataclass(frozen=True)
class RetryPolicy:
    """Política determinística de retries finitos com backoff exponencial."""

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    retryable_error_classes: Sequence[type[Exception]] = field(
        default_factory=lambda: (TimeoutError, ConnectionError, OSError)
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1")
        if self.initial_delay_seconds <= 0:
            raise ValueError("initial_delay_seconds deve ser > 0")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier deve ser >= 1.0")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds deve ser >= initial_delay_seconds")

    def should_retry(self, current_attempt: int, exc: Exception) -> bool:
        """Determina se uma nova tentativa é permitida."""
        if current_attempt >= self.max_attempts:
            return False
        # Erros marcados explicitamente como não recuperáveis ou violações de segurança/orçamento nunca sofrem retry
        if isinstance(exc, (NonRetryableError, TenantIsolationViolation, OperationAlreadyCharged)):
            return False
        return any(isinstance(exc, err_cls) for err_cls in self.retryable_error_classes)

    def calculate_delay(self, attempt: int) -> float:
        """Calcula delay exponencial determinístico limitado ao teto."""
        if attempt <= 1:
            return self.initial_delay_seconds
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True)
class BackpressureConfig:
    """Configuração dos limites de saturação e fila."""

    max_concurrent_jobs: int = 4
    queue_capacity: int = 16

    def __post_init__(self) -> None:
        if self.max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs deve ser >= 1")
        if self.queue_capacity < 0:
            raise ValueError("queue_capacity deve ser >= 0")


class BackpressureController:
    """Controlador em memória de concorrência e admissão de jobs."""

    def __init__(self, config: BackpressureConfig | None = None) -> None:
        self.config = config or BackpressureConfig()
        self._active_jobs: int = 0
        self._queued_jobs: int = 0

    @property
    def active_jobs(self) -> int:
        return self._active_jobs

    @property
    def queued_jobs(self) -> int:
        return self._queued_jobs

    @property
    def is_saturated(self) -> bool:
        return (
            self._active_jobs >= self.config.max_concurrent_jobs
            and self._queued_jobs >= self.config.queue_capacity
        )

    def admit_job(self) -> str:
        """Tenta admitir um novo job. Retorna 'ACTIVE' ou 'QUEUED' ou lança BackpressureExceeded."""
        if self._active_jobs < self.config.max_concurrent_jobs:
            self._active_jobs += 1
            return "ACTIVE"
        if self._queued_jobs < self.config.queue_capacity:
            self._queued_jobs += 1
            return "QUEUED"
        raise BackpressureExceeded(
            f"Capacidade saturada: active={self._active_jobs}/{self.config.max_concurrent_jobs}, "
            f"queue={self._queued_jobs}/{self.config.queue_capacity}"
        )

    def release_job(self, slot_type: str = "ACTIVE") -> None:
        """Libera um slot previamente alocado e promove fila se houver vaga."""
        if slot_type == "ACTIVE":
            if self._active_jobs > 0:
                self._active_jobs -= 1
            if self._queued_jobs > 0 and self._active_jobs < self.config.max_concurrent_jobs:
                self._queued_jobs -= 1
                self._active_jobs += 1
        elif slot_type == "QUEUED":
            if self._queued_jobs > 0:
                self._queued_jobs -= 1


class AsyncOperationStatus(str, Enum):
    """Estado de ciclo de vida de uma operação assíncrona externa."""

    RESERVED = "RESERVED"
    SUBMITTED = "SUBMITTED"
    POLLING = "POLLING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class AsyncOperationRecord:
    """Registro de operação assíncrona para reconciliação anti-dupla-cobrança."""

    operation_id: str
    idempotency_key: str
    status: AsyncOperationStatus
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal | None = None
    external_reference_id: str | None = None
    updated_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def can_safely_retry_without_charge(self) -> bool:
        """Indica se é seguro tentar novamente sem risco de dupla cobrança."""
        return self.status in (AsyncOperationStatus.FAILED, AsyncOperationStatus.RESERVED)

    def requires_reconciliation(self) -> bool:
        """Indica se requer reconciliação prévia antes de qualquer ação."""
        return self.status in (
            AsyncOperationStatus.SUBMITTED,
            AsyncOperationStatus.POLLING,
            AsyncOperationStatus.UNCERTAIN,
        )


@dataclass(frozen=True)
class TenantScope:
    """Escopo de tenant para garantia de isolamento em ambiente multi-tenant/SaaS."""

    tenant_id: str
    project_id: str
    channel_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError("tenant_id não pode ser vazio")
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id não pode ser vazio")

    def assert_matches(self, target_tenant_id: str, target_project_id: str) -> None:
        """Valida que o recurso pertence ao mesmo escopo."""
        if self.tenant_id != target_tenant_id:
            raise TenantIsolationViolation(
                f"Violação de tenant: esperado {self.tenant_id}, obtido {target_tenant_id}"
            )
        if self.project_id != target_project_id:
            raise TenantIsolationViolation(
                f"Violação de projeto: esperado {self.project_id}, obtido {target_project_id}"
            )


@dataclass(frozen=True)
class StageTimeoutPolicy:
    """Política de tempo limite determinístico por etapa."""

    stage_timeouts: Mapping[str, float] = field(
        default_factory=lambda: {
            "script": 60.0,
            "factcheck": 60.0,
            "storyboard": 120.0,
            "assets": 180.0,
            "render": 600.0,
            "qa": 120.0,
            "approval": 60.0,
            "publish": 180.0,
        }
    )
    default_timeout: float = 120.0

    def get_timeout_for_stage(self, stage_name: str) -> float:
        return self.stage_timeouts.get(stage_name, self.default_timeout)

    def validate_duration(self, stage_name: str, elapsed_seconds: float) -> None:
        limit = self.get_timeout_for_stage(stage_name)
        if elapsed_seconds > limit:
            raise StageTimeoutError(
                f"Etapa {stage_name} excedeu o timeout de {limit:.1f}s (decorrido: {elapsed_seconds:.1f}s)"
            )
