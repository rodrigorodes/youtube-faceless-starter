"""Contratos puros (sem I/O) da execução de produção: run, etapas, DAG e resultados de CAS.

`ProductionRun` é a execução pedida uma única vez por `idempotency_key`; `StageExecution` é uma
etapa com tentativa, lease e `fencing_token` — só o dono do token atual escreve. O DAG declara
dependências e a ordem topológica é derivada, nunca digitada à mão.

Os enums de resultado existem para que nenhuma operação seja confundida com um booleano: compare
sempre explicitamente (`result is ClaimResult.CLAIMED`). `Checkpoint` guarda o estado necessário
para retomar uma etapa sem repetir trabalho já feito.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import unicodedata

from .ids import check_id

SCHEMA_VERSION = 1
EVENT_VERSION = 1
MAX_IDEMPOTENCY_KEY_LENGTH = 200
INVISIBLE_IDENTITY_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


class ExplicitResult(str, Enum):
    """Resultado de operação: usar como booleano é ambíguo e falha de propósito."""

    def __bool__(self) -> bool:
        raise TypeError("compare the result explicitly")


class ProductionStage(str, Enum):
    """Estágios canônicos da F1-05. Handlers e efeitos externos não fazem parte deste módulo."""

    RESEARCH = "research"
    SCRIPT = "script"
    FACTCHECK = "factcheck"
    STORYBOARD = "storyboard"
    ASSETS = "assets"
    RENDER = "render"
    QA = "qa"
    APPROVAL = "approval"
    PUBLISH = "publish"


class RunState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"  # pausa humana persistida: nenhum worker fica preso
    PAUSED = "PAUSED"                # reservado para pausa operacional (D2); `resume_run` aceita
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"


class StageState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class ProgressEventType(str, Enum):
    """Tipos de evento da outbox (`event_version` 1). O payload é um objeto JSON sem segredos.

    `production.run.created`: run_id, video_id, channel_id, state, stages
    `production.run.state_changed`: from, to, reason
    `production.stage.claimed`: run_id, stage_id, attempt, fencing_token, lease_owner, lease_expires_at
    `production.stage.completed`: run_id, stage_id, attempt, fencing_token, checkpoint_version
    `production.stage.failed`: run_id, stage_id, attempt, fencing_token, error
    """

    RUN_CREATED = "production.run.created"
    RUN_STATE_CHANGED = "production.run.state_changed"
    STAGE_CLAIMED = "production.stage.claimed"
    STAGE_COMPLETED = "production.stage.completed"
    STAGE_FAILED = "production.stage.failed"


class StageClaimResult(ExplicitResult):
    CLAIMED = "CLAIMED"
    BUSY = "BUSY"                        # outro dono tem lease válido
    RUN_NOT_ACTIVE = "RUN_NOT_ACTIVE"     # run pausado, aguardando humano, falho ou terminal
    DEPENDENCIES_PENDING = "DEPENDENCIES_PENDING"
    STAGE_TERMINAL = "STAGE_TERMINAL"
    UNKNOWN = "UNKNOWN"                   # run ou etapa inexistente


class StageTransitionResult(ExplicitResult):
    APPLIED = "APPLIED"
    LOST = "LOST"                        # dono/token antigos ou lease expirado: nada foi escrito
    NOT_RUNNING = "NOT_RUNNING"          # a etapa já não está RUNNING
    CHECKPOINT_REJECTED = "CHECKPOINT_REJECTED"
    UNKNOWN = "UNKNOWN"


class LeaseResult(ExplicitResult):
    RENEWED = "RENEWED"
    LOST = "LOST"                        # token/dono antigos, lease expirado ou etapa fora de RUNNING
    UNKNOWN = "UNKNOWN"


class RunTransitionResult(ExplicitResult):
    APPLIED = "APPLIED"
    NOT_ALLOWED = "NOT_ALLOWED"          # estado atual não admite a transição; nada foi escrito
    UNKNOWN = "UNKNOWN"


class CreateRunResult(ExplicitResult):
    CREATED = "CREATED"
    EXISTING = "EXISTING"                # replay da mesma idempotency_key


class AckResult(ExplicitResult):
    ACKED = "ACKED"
    ALREADY_ACKED = "ALREADY_ACKED"
    UNKNOWN = "UNKNOWN"


class ProductionError(RuntimeError):
    """Base das falhas de execução de produção."""


class ProductionRunLockTimeout(ProductionError):
    """Outra transação mantém o run travado além do `lock_timeout`: contend, não indisponibilidade.

    Repetir depois é seguro: nenhuma escrita foi confirmada por esta operação.
    """


class ProductionRunReferencedEntityNotFound(ProductionError):
    """O vídeo ou o perfil de canal referenciado pelo run não existe (FK recusada pelo banco)."""


class InvalidIdempotencyKey(ValueError):
    """A chave de idempotência não está na forma canônica aceita."""


def canonical_idempotency_key(value: object) -> str:
    """Valida e devolve a chave canônica: byte-a-byte, minúscula, sem espaço ou invisível.

    A identidade é a string canônica exata. Variantes com padding, caixa diferente ou caracteres
    invisíveis são **recusadas**, nunca normalizadas: uma variante pode ser um retry acidental do
    mesmo pedido ou um pedido diferente — e os dois não podem colidir silenciosamente. O cliente
    deve enviar a chave já canônica; comparação e unicidade no banco são byte-a-byte.
    """
    if not isinstance(value, str):
        raise InvalidIdempotencyKey("idempotency key must be a string")
    if not value:
        raise InvalidIdempotencyKey("idempotency key is required")
    if len(value) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise InvalidIdempotencyKey("idempotency key is too long")
    if value != value.strip():
        raise InvalidIdempotencyKey("idempotency key must not have leading or trailing whitespace")
    if any(character.isspace() for character in value):
        raise InvalidIdempotencyKey("idempotency key must not contain whitespace")
    if any(unicodedata.category(character) in INVISIBLE_IDENTITY_CATEGORIES for character in value):
        raise InvalidIdempotencyKey("idempotency key must not contain control or invisible characters")
    if value != value.casefold():
        raise InvalidIdempotencyKey("idempotency key must be lowercase canonical; case variants are refused")
    return value


class ProductionIdempotencyConflict(ValueError):
    """A chave de idempotência já foi usada para uma solicitação diferente."""


class InvalidProductionTransition(ValueError):
    """Transição de estado incompatível com o grafo de estados."""


class InvalidPipeline(ValueError):
    """Configuração de DAG inválida."""


class UnknownStageDependency(InvalidPipeline):
    """Uma dependência declarada não é um estágio do próprio DAG."""


class StageCycleError(InvalidPipeline):
    """O DAG declarado tem ciclo e não admite ordem topológica."""


class StageNotInDag(InvalidPipeline):
    """Estágio pedido não pertence ao DAG do repositório."""


class IncompleteStageSet(InvalidPipeline):
    """O conjunto de estágios de uma execução não é fechado sob as dependências."""


RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.RUNNING, RunState.WAITING_HUMAN, RunState.CANCELLED}),
    RunState.RUNNING: frozenset({RunState.WAITING_HUMAN, RunState.PAUSED, RunState.FAILED,
                                 RunState.CANCELLED, RunState.SUCCEEDED}),
    RunState.WAITING_HUMAN: frozenset({RunState.RUNNING, RunState.PAUSED, RunState.CANCELLED}),
    RunState.PAUSED: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.FAILED: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.CANCELLED: frozenset(),
    RunState.SUCCEEDED: frozenset(),
}

STAGE_TRANSITIONS: dict[StageState, frozenset[StageState]] = {
    StageState.PENDING: frozenset({StageState.RUNNING, StageState.CANCELLED, StageState.SKIPPED}),
    # RUNNING → RUNNING é a retomada por novo dono quando o lease expira (novo fencing token).
    StageState.RUNNING: frozenset({StageState.RUNNING, StageState.SUCCEEDED, StageState.FAILED,
                                   StageState.WAITING_HUMAN, StageState.CANCELLED}),
    StageState.WAITING_HUMAN: frozenset({StageState.PENDING, StageState.RUNNING, StageState.CANCELLED}),
    StageState.FAILED: frozenset({StageState.RUNNING, StageState.CANCELLED}),
    StageState.SUCCEEDED: frozenset(),
    StageState.CANCELLED: frozenset(),
    StageState.SKIPPED: frozenset(),
}


def can_run_transition(old: RunState, new: RunState) -> bool:
    return new in RUN_TRANSITIONS[old]


def assert_run_transition(old: RunState, new: RunState) -> None:
    if not can_run_transition(old, new):
        raise InvalidProductionTransition(f"{old.value} -> {new.value} is not allowed")


def can_stage_transition(old: StageState, new: StageState) -> bool:
    return new in STAGE_TRANSITIONS[old]


def assert_stage_transition(old: StageState, new: StageState) -> None:
    if not can_stage_transition(old, new):
        raise InvalidProductionTransition(f"{old.value} -> {new.value} is not allowed")


class StageDag:
    """Dependências declarativas entre estágios, com validação topológica na construção."""

    def __init__(self, dependencies: Mapping[ProductionStage, Iterable[ProductionStage]]):
        if not isinstance(dependencies, Mapping) or not dependencies:
            raise InvalidPipeline("a pipeline needs at least one stage")
        declared = tuple(dependencies)
        for stage in declared:
            if not isinstance(stage, ProductionStage):
                raise InvalidPipeline(f"unknown stage in pipeline: {stage!r}")
        normalized: dict[ProductionStage, frozenset[ProductionStage]] = {}
        for stage in declared:
            needs = frozenset(dependencies[stage])
            for dependency in needs:
                if not isinstance(dependency, ProductionStage) or dependency not in dependencies:
                    raise UnknownStageDependency(f"stage {stage.value} depends on an undeclared stage")
                if dependency is stage:
                    raise StageCycleError(f"stage {stage.value} depends on itself")
            normalized[stage] = needs
        self._dependencies = normalized
        self._stages = declared
        self._topological = self._sort(declared, normalized)

    @staticmethod
    def _sort(declared: tuple[ProductionStage, ...],
              dependencies: Mapping[ProductionStage, frozenset[ProductionStage]]) -> tuple[ProductionStage, ...]:
        ordered: list[ProductionStage] = []
        remaining = {stage: set(dependencies[stage]) for stage in declared}
        while remaining:
            ready = [stage for stage in declared if stage in remaining and not remaining[stage]]
            if not ready:
                raise StageCycleError("stage dependencies contain a cycle")
            for stage in ready:
                ordered.append(stage)
                del remaining[stage]
            for needs in remaining.values():
                needs.difference_update(ready)
        return tuple(ordered)

    @property
    def stages(self) -> tuple[ProductionStage, ...]:
        """Estágios na ordem de declaração (não é a ordem de execução)."""
        return self._stages

    def prerequisites(self, stage: ProductionStage) -> frozenset[ProductionStage]:
        try:
            return self._dependencies[stage]
        except KeyError as exc:
            raise StageNotInDag(f"stage {stage!r} is not in this pipeline") from exc

    def topological_order(self) -> tuple[ProductionStage, ...]:
        return self._topological

    def can_run(self, stage: ProductionStage, completed: Iterable[ProductionStage]) -> bool:
        return self.prerequisites(stage) <= set(completed)

    def validate_stages(self, stages: Iterable[ProductionStage]) -> tuple[ProductionStage, ...]:
        """Aceita só um conjunto não vazio, sem repetição e fechado sob dependências.

        Devolve os estágios na ordem topológica do DAG, para a criação ser determinística.
        """
        requested = tuple(stages)
        if not requested:
            raise IncompleteStageSet("a production run needs at least one stage")
        if len(set(requested)) != len(requested):
            raise InvalidPipeline("duplicate stage in the production run")
        for stage in requested:
            if not isinstance(stage, ProductionStage) or stage not in self._dependencies:
                raise StageNotInDag(f"stage {stage!r} is not in this pipeline")
        wanted = set(requested)
        missing = {need for stage in requested for need in self._dependencies[stage]} - wanted
        if missing:
            raise IncompleteStageSet(
                "stage set is not dependency-closed; missing: " + ", ".join(sorted(s.value for s in missing)))
        return tuple(stage for stage in self._topological if stage in wanted)


STANDARD_DAG = StageDag({
    ProductionStage.RESEARCH: (),
    ProductionStage.SCRIPT: (ProductionStage.RESEARCH,),
    ProductionStage.FACTCHECK: (ProductionStage.SCRIPT,),
    ProductionStage.STORYBOARD: (ProductionStage.FACTCHECK,),
    ProductionStage.ASSETS: (ProductionStage.STORYBOARD,),
    ProductionStage.RENDER: (ProductionStage.ASSETS,),
    ProductionStage.QA: (ProductionStage.RENDER,),
    ProductionStage.APPROVAL: (ProductionStage.QA,),
    ProductionStage.PUBLISH: (ProductionStage.APPROVAL,),
})


@dataclass(frozen=True)
class Checkpoint:
    """Payload JSON + versão monotônica de uma etapa; permite retomar sem refazer o trabalho."""

    payload: dict
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise ValueError("checkpoint payload must be a JSON object")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("checkpoint version must be an integer >= 1")


@dataclass(frozen=True)
class StageExecution:
    run_id: str
    stage_id: ProductionStage
    state: StageState
    attempt: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    fencing_token: int = 0
    checkpoint: Checkpoint | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.run_id)
        if not isinstance(self.stage_id, ProductionStage):
            raise TypeError("stage_id must be a ProductionStage")
        if not isinstance(self.state, StageState):
            raise TypeError("state must be a StageState")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 0:
            raise ValueError("attempt must be an integer >= 0")
        if isinstance(self.fencing_token, bool) or not isinstance(self.fencing_token, int) or self.fencing_token < 0:
            raise ValueError("fencing token must be an integer >= 0")
        if self.state is StageState.RUNNING:
            if not self.lease_owner or self.lease_expires_at is None:
                raise ValueError("a RUNNING stage requires a lease owner and expiry")
        elif self.lease_owner is not None or self.lease_expires_at is not None:
            raise ValueError("only a RUNNING stage may hold a lease")
        if self.checkpoint is not None and not isinstance(self.checkpoint, Checkpoint):
            raise TypeError("checkpoint must be a Checkpoint")
        if self.error is not None and (not isinstance(self.error, str) or not self.error.strip()):
            raise ValueError("error must be a non-empty string when present")


@dataclass(frozen=True)
class ProductionRun:
    run_id: str
    video_id: str
    idempotency_key: str
    state: RunState = RunState.CREATED
    channel_id: str | None = None
    schema_version: int = SCHEMA_VERSION
    reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.run_id)
        check_id(self.video_id)
        if self.channel_id is not None:
            check_id(self.channel_id)
        canonical_idempotency_key(self.idempotency_key)
        if not isinstance(self.state, RunState):
            raise TypeError("state must be a RunState")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ValueError("schema version must be an integer >= 1")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason.strip()):
            raise ValueError("reason must be a non-empty string when present")


@dataclass(frozen=True)
class OutboxEvent:
    """Evento de progresso gravado na mesma transação da mudança de estado."""

    id: int
    run_id: str
    event_type: ProgressEventType
    payload: dict
    event_version: int = EVENT_VERSION
    stage_id: ProductionStage | None = None
    created_at: datetime | None = None
    acked_at: datetime | None = None


@dataclass(frozen=True)
class StageClaim:
    result: StageClaimResult
    execution: StageExecution | None = None


@dataclass(frozen=True)
class StageTransition:
    result: StageTransitionResult
    execution: StageExecution | None = None


@dataclass(frozen=True)
class RunTransition:
    result: RunTransitionResult
    run: ProductionRun | None = None


@dataclass(frozen=True)
class RunCreation:
    result: CreateRunResult
    run: ProductionRun