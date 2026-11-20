"""Repositório Postgres transacional de execuções de produção.

Toda transição é CAS: o estado atual (e, nas etapas, o `fencing_token` do dono) condiciona a escrita.
Cada operação abre uma conexão, trava a linha do run (`FOR UPDATE`) antes das etapas — ordem única,
sem ciclo de lock — e grava o evento de progresso na MESMA transação da mudança de estado.

Lease: `claim_stage` incrementa tentativa e fencing token; `renew_lease` exige token atual e lease
ainda válido; `complete_stage`/`fail_stage` recusam dono ou token antigos mesmo que ninguém tenha
retomado a etapa. Etapa órfã (lease vencido) só é retomada por `claim_stage`, que gera token novo.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...domain.ids import check_id
from ...domain.production_run import (
    EVENT_VERSION,
    STANDARD_DAG,
    AckResult,
    Checkpoint,
    CreateRunResult,
    LeaseResult,
    OutboxEvent,
    ProductionIdempotencyConflict,
    ProductionRun,
    ProductionStage,
    ProgressEventType,
    RunCreation,
    RunState,
    RunTransition,
    RunTransitionResult,
    StageClaim,
    StageClaimResult,
    StageDag,
    StageExecution,
    StageNotInDag,
    StageState,
    StageTransition,
    StageTransitionResult,
    assert_run_transition,
)
from .repo import _translated

_RUN_COLS = ("run_id, video_id, channel_id, state, idempotency_key, schema_version, reason, "
             "created_at, updated_at")
_STAGE_COLS = ("run_id, stage_id, state, attempt, lease_owner, lease_expires_at, fencing_token, "
               "checkpoint, checkpoint_version, error, created_at, updated_at")
_OUTBOX_COLS = "id, run_id, stage_id, event_type, event_version, payload, created_at, acked_at"

_ACTIVE_RUN_STATES = (RunState.CREATED, RunState.RUNNING)
_RESUMABLE_RUN_STATES = (RunState.WAITING_HUMAN, RunState.PAUSED, RunState.FAILED)
_CANCELLABLE_RUN_STATES = (RunState.CREATED, RunState.RUNNING, RunState.WAITING_HUMAN,
                           RunState.PAUSED, RunState.FAILED)


def _one(conn: psycopg.Connection, sql: str, params: tuple = ()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _all(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _run(row: dict) -> ProductionRun:
    return ProductionRun(
        run_id=row["run_id"], video_id=row["video_id"], idempotency_key=row["idempotency_key"],
        state=RunState(row["state"]), channel_id=row["channel_id"], schema_version=row["schema_version"],
        reason=row["reason"], created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _stage(row: dict) -> StageExecution:
    checkpoint = None
    if row["checkpoint"] is not None:
        checkpoint = Checkpoint(payload=row["checkpoint"], version=row["checkpoint_version"])
    return StageExecution(
        run_id=row["run_id"], stage_id=ProductionStage(row["stage_id"]), state=StageState(row["state"]),
        attempt=row["attempt"], lease_owner=row["lease_owner"], lease_expires_at=row["lease_expires_at"],
        fencing_token=row["fencing_token"], checkpoint=checkpoint, error=row["error"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _event(row: dict) -> OutboxEvent:
    return OutboxEvent(
        id=row["id"], run_id=row["run_id"],
        stage_id=ProductionStage(row["stage_id"]) if row["stage_id"] is not None else None,
        event_type=ProgressEventType(row["event_type"]), event_version=row["event_version"],
        payload=row["payload"], created_at=row["created_at"], acked_at=row["acked_at"],
    )


def _text(value: Any, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    if len(value) > max_length:
        raise ValueError(f"{label} is too long")
    return value


def _lease_seconds(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86_400:
        raise ValueError("lease seconds must be an integer between 1 and 86400")
    return value


def _token(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("fencing token must be an integer >= 0")
    return value


class PostgresProductionRunRepository:
    """Implementa `application.ports.ProductionRunRepository` sobre `studio.production_*`."""

    def __init__(self, connect: Callable[[], psycopg.Connection], dag: StageDag = STANDARD_DAG):
        if not isinstance(dag, StageDag):
            raise TypeError("dag must be a StageDag")
        self._connect = connect
        self._dag = dag

    # -- criação e leitura -------------------------------------------------

    def create_run(self, run_id: str, video_id: str, idempotency_key: str, *,
                   channel_id: str | None = None,
                   stages: Iterable[ProductionStage] | None = None) -> RunCreation:
        run_id = check_id(run_id)
        video_id = check_id(video_id)
        if channel_id is not None:
            channel_id = check_id(channel_id)
        idempotency_key = _text(idempotency_key, "idempotency key", 200)
        ordered = self._dag.validate_stages(self._dag.stages if stages is None else stages)
        with _translated(), self._connect() as conn, conn.transaction():
            inserted = _one(
                conn,
                f"INSERT INTO studio.production_runs(run_id, video_id, channel_id, idempotency_key, state) "
                f"VALUES (%s, %s, %s, %s, 'CREATED') ON CONFLICT DO NOTHING RETURNING {_RUN_COLS}",
                (run_id, video_id, channel_id, idempotency_key),
            )
            if inserted is None:
                return self._existing_run(conn, run_id, video_id, channel_id, idempotency_key, ordered)
            for stage in ordered:
                conn.execute("INSERT INTO studio.stage_executions(run_id, stage_id, state) "
                             "VALUES (%s, %s, 'PENDING')", (run_id, stage.value))
            self._emit(conn, run_id, ProgressEventType.RUN_CREATED, {
                "run_id": run_id, "video_id": video_id, "channel_id": channel_id,
                "state": RunState.CREATED.value, "stages": [stage.value for stage in ordered],
            })
            return RunCreation(CreateRunResult.CREATED, _run(inserted))

    def _existing_run(self, conn: psycopg.Connection, run_id: str, video_id: str, channel_id: str | None,
                      idempotency_key: str, ordered: tuple[ProductionStage, ...]) -> RunCreation:
        """Replay: a chave identifica uma única solicitação; divergência é conflito, nunca duplicação."""
        row = _one(conn, f"SELECT {_RUN_COLS} FROM studio.production_runs WHERE idempotency_key = %s",
                   (idempotency_key,))
        if row is None:
            raise ProductionIdempotencyConflict("run id is already used by another idempotency key")
        if row["run_id"] != run_id or row["video_id"] != video_id or row["channel_id"] != channel_id:
            raise ProductionIdempotencyConflict("idempotency key already used for a different run request")
        stored = {item["stage_id"] for item in _all(
            conn, "SELECT stage_id FROM studio.stage_executions WHERE run_id = %s", (run_id,))}
        if stored != {stage.value for stage in ordered}:
            raise ProductionIdempotencyConflict("idempotency key already used with a different stage set")
        return RunCreation(CreateRunResult.EXISTING, _run(row))

    def get_run(self, run_id: str) -> ProductionRun | None:
        run_id = check_id(run_id)
        with _translated(), self._connect() as conn:
            row = _one(conn, f"SELECT {_RUN_COLS} FROM studio.production_runs WHERE run_id = %s", (run_id,))
            return _run(row) if row is not None else None

    # -- etapas: claim, heartbeat, conclusão e falha -----------------------

    def claim_stage(self, run_id: str, stage_id: ProductionStage, owner: str,
                    lease_seconds: int) -> StageClaim:
        run_id = check_id(run_id)
        stage = self._stage(stage_id)
        owner = _text(owner, "lease owner", 200)
        lease_seconds = _lease_seconds(lease_seconds)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return StageClaim(StageClaimResult.UNKNOWN)
            stage_row = self._lock_stage(conn, run_id, stage)
            if stage_row is None:
                return StageClaim(StageClaimResult.UNKNOWN)
            run_state = RunState(run_row["state"])
            if run_state not in _ACTIVE_RUN_STATES:
                return StageClaim(StageClaimResult.RUN_NOT_ACTIVE)
            stage_state = StageState(stage_row["state"])
            if stage_state in (StageState.SUCCEEDED, StageState.CANCELLED, StageState.SKIPPED):
                return StageClaim(StageClaimResult.STAGE_TERMINAL)
            if stage_state is StageState.WAITING_HUMAN:
                return StageClaim(StageClaimResult.RUN_NOT_ACTIVE)
            now = _one(conn, "SELECT statement_timestamp() AS now")["now"]
            if stage_state is StageState.RUNNING:
                expires = stage_row["lease_expires_at"]
                if expires is not None and expires > now:
                    return StageClaim(StageClaimResult.BUSY)
            pending = self._pending_prerequisites(conn, run_id, stage)
            if pending:
                return StageClaim(StageClaimResult.DEPENDENCIES_PENDING)
            if run_state is RunState.CREATED:
                assert_run_transition(RunState.CREATED, RunState.RUNNING)
                conn.execute("UPDATE studio.production_runs SET state = 'RUNNING', updated_at = statement_timestamp() "
                             "WHERE run_id = %s", (run_id,))
                self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                           {"from": RunState.CREATED.value, "to": RunState.RUNNING.value, "reason": None})
            updated = _one(
                conn,
                "UPDATE studio.stage_executions SET state = 'RUNNING', attempt = attempt + 1, "
                "lease_owner = %s, lease_expires_at = statement_timestamp() + make_interval(secs => %s), "
                "fencing_token = fencing_token + 1, error = NULL, updated_at = statement_timestamp() "
                f"WHERE run_id = %s AND stage_id = %s RETURNING {_STAGE_COLS}",
                (owner, float(lease_seconds), run_id, stage.value),
            )
            execution = _stage(updated)
            self._emit(conn, run_id, ProgressEventType.STAGE_CLAIMED, {
                "run_id": run_id, "stage_id": stage.value, "attempt": execution.attempt,
                "fencing_token": execution.fencing_token, "lease_owner": execution.lease_owner,
                "lease_expires_at": execution.lease_expires_at.isoformat() if execution.lease_expires_at else None,
            }, stage_id=stage)
            return StageClaim(StageClaimResult.CLAIMED, execution)

    def renew_lease(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int,
                    lease_seconds: int) -> LeaseResult:
        run_id = check_id(run_id)
        stage = self._stage(stage_id)
        owner = _text(owner, "lease owner", 200)
        fencing_token = _token(fencing_token)
        lease_seconds = _lease_seconds(lease_seconds)
        with _translated(), self._connect() as conn, conn.transaction():
            if self._lock_run(conn, run_id) is None:
                return LeaseResult.UNKNOWN
            renewed = _one(
                conn,
                "UPDATE studio.stage_executions SET lease_expires_at = statement_timestamp() + "
                "make_interval(secs => %s), updated_at = statement_timestamp() "
                "WHERE run_id = %s AND stage_id = %s AND state = 'RUNNING' AND lease_owner = %s "
                "AND fencing_token = %s AND lease_expires_at > statement_timestamp() RETURNING stage_id",
                (float(lease_seconds), run_id, stage.value, owner, fencing_token),
            )
            if renewed is not None:
                return LeaseResult.RENEWED
            exists = _one(conn, "SELECT 1 AS ok FROM studio.stage_executions WHERE run_id = %s AND stage_id = %s",
                          (run_id, stage.value))
            return LeaseResult.LOST if exists is not None else LeaseResult.UNKNOWN

    def complete_stage(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int, *,
                       checkpoint: Checkpoint | None = None) -> StageTransition:
        run_id = check_id(run_id)
        stage = self._stage(stage_id)
        owner = _text(owner, "lease owner", 200)
        fencing_token = _token(fencing_token)
        checkpoint = self._checkpoint(checkpoint)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return StageTransition(StageTransitionResult.UNKNOWN)
            stage_row = self._lock_stage(conn, run_id, stage)
            if stage_row is None:
                return StageTransition(StageTransitionResult.UNKNOWN)
            refused = self._write_guard(conn, run_row, stage_row, owner, fencing_token)
            if refused is not None:
                return StageTransition(refused)
            if checkpoint is not None and checkpoint.version <= (stage_row["checkpoint_version"] or 0):
                return StageTransition(StageTransitionResult.CHECKPOINT_REJECTED)
            assignments = ["state = 'SUCCEEDED'", "lease_owner = NULL", "lease_expires_at = NULL",
                           "error = NULL", "updated_at = statement_timestamp()"]
            params: list[Any] = []
            if checkpoint is not None:
                assignments += ["checkpoint = %s", "checkpoint_version = %s"]
                params += [Jsonb(checkpoint.payload), checkpoint.version]
            updated = _one(
                conn,
                f"UPDATE studio.stage_executions SET {', '.join(assignments)} "
                f"WHERE run_id = %s AND stage_id = %s RETURNING {_STAGE_COLS}",
                (*params, run_id, stage.value),
            )
            execution = _stage(updated)
            self._emit(conn, run_id, ProgressEventType.STAGE_COMPLETED, {
                "run_id": run_id, "stage_id": stage.value, "attempt": execution.attempt,
                "fencing_token": execution.fencing_token,
                "checkpoint_version": execution.checkpoint.version if execution.checkpoint else None,
            }, stage_id=stage)
            open_stages = _one(
                conn, "SELECT count(*) AS open FROM studio.stage_executions "
                "WHERE run_id = %s AND state NOT IN ('SUCCEEDED', 'SKIPPED')", (run_id,))["open"]
            if open_stages == 0 and RunState(run_row["state"]) is RunState.RUNNING:
                assert_run_transition(RunState.RUNNING, RunState.SUCCEEDED)
                conn.execute("UPDATE studio.production_runs SET state = 'SUCCEEDED', reason = NULL, "
                             "updated_at = statement_timestamp() WHERE run_id = %s", (run_id,))
                self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                           {"from": RunState.RUNNING.value, "to": RunState.SUCCEEDED.value, "reason": None})
            return StageTransition(StageTransitionResult.APPLIED, execution)

    def fail_stage(self, run_id: str, stage_id: ProductionStage, owner: str, fencing_token: int,
                   error: str, *, checkpoint: Checkpoint | None = None) -> StageTransition:
        run_id = check_id(run_id)
        stage = self._stage(stage_id)
        owner = _text(owner, "lease owner", 200)
        fencing_token = _token(fencing_token)
        error = _text(error, "stage error", 2000)
        checkpoint = self._checkpoint(checkpoint)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return StageTransition(StageTransitionResult.UNKNOWN)
            stage_row = self._lock_stage(conn, run_id, stage)
            if stage_row is None:
                return StageTransition(StageTransitionResult.UNKNOWN)
            refused = self._write_guard(conn, run_row, stage_row, owner, fencing_token)
            if refused is not None:
                return StageTransition(refused)
            if checkpoint is not None and checkpoint.version <= (stage_row["checkpoint_version"] or 0):
                return StageTransition(StageTransitionResult.CHECKPOINT_REJECTED)
            assignments = ["state = 'FAILED'", "lease_owner = NULL", "lease_expires_at = NULL",
                           "error = %s", "updated_at = statement_timestamp()"]
            params: list[Any] = [error]
            if checkpoint is not None:
                assignments += ["checkpoint = %s", "checkpoint_version = %s"]
                params += [Jsonb(checkpoint.payload), checkpoint.version]
            updated = _one(
                conn,
                f"UPDATE studio.stage_executions SET {', '.join(assignments)} "
                f"WHERE run_id = %s AND stage_id = %s RETURNING {_STAGE_COLS}",
                (*params, run_id, stage.value),
            )
            execution = _stage(updated)
            self._emit(conn, run_id, ProgressEventType.STAGE_FAILED, {
                "run_id": run_id, "stage_id": stage.value, "attempt": execution.attempt,
                "fencing_token": execution.fencing_token, "error": error,
            }, stage_id=stage)
            if RunState(run_row["state"]) is RunState.RUNNING:
                assert_run_transition(RunState.RUNNING, RunState.FAILED)
                reason = f"stage {stage.value} failed: {error}"[:2000]
                conn.execute("UPDATE studio.production_runs SET state = 'FAILED', reason = %s, "
                             "updated_at = statement_timestamp() WHERE run_id = %s", (reason, run_id))
                self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                           {"from": RunState.RUNNING.value, "to": RunState.FAILED.value, "reason": reason})
            return StageTransition(StageTransitionResult.APPLIED, execution)

    # -- ciclo de vida do run ---------------------------------------------

    def pause_run(self, run_id: str, reason: str) -> RunTransition:
        run_id = check_id(run_id)
        reason = _text(reason, "pause reason", 2000)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return RunTransition(RunTransitionResult.UNKNOWN)
            state = RunState(run_row["state"])
            if state not in _ACTIVE_RUN_STATES:
                return RunTransition(RunTransitionResult.NOT_ALLOWED, _run(run_row))
            assert_run_transition(state, RunState.WAITING_HUMAN)
            updated = _one(
                conn,
                "UPDATE studio.production_runs SET state = 'WAITING_HUMAN', reason = %s, "
                f"updated_at = statement_timestamp() WHERE run_id = %s RETURNING {_RUN_COLS}",
                (reason, run_id),
            )
            # A etapa em execução vira WAITING_HUMAN sem lease: nenhum worker fica ocupado.
            conn.execute("UPDATE studio.stage_executions SET state = 'WAITING_HUMAN', lease_owner = NULL, "
                         "lease_expires_at = NULL, updated_at = statement_timestamp() "
                         "WHERE run_id = %s AND state = 'RUNNING'", (run_id,))
            self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                       {"from": state.value, "to": RunState.WAITING_HUMAN.value, "reason": reason})
            return RunTransition(RunTransitionResult.APPLIED, _run(updated))

    def resume_run(self, run_id: str) -> RunTransition:
        run_id = check_id(run_id)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return RunTransition(RunTransitionResult.UNKNOWN)
            state = RunState(run_row["state"])
            if state not in _RESUMABLE_RUN_STATES:
                return RunTransition(RunTransitionResult.NOT_ALLOWED, _run(run_row))
            assert_run_transition(state, RunState.RUNNING)
            updated = _one(
                conn,
                "UPDATE studio.production_runs SET state = 'RUNNING', reason = NULL, "
                f"updated_at = statement_timestamp() WHERE run_id = %s RETURNING {_RUN_COLS}",
                (run_id,),
            )
            conn.execute("UPDATE studio.stage_executions SET state = 'PENDING', updated_at = statement_timestamp() "
                         "WHERE run_id = %s AND state = 'WAITING_HUMAN'", (run_id,))
            self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                       {"from": state.value, "to": RunState.RUNNING.value, "reason": None})
            return RunTransition(RunTransitionResult.APPLIED, _run(updated))

    def cancel_run(self, run_id: str, reason: str) -> RunTransition:
        run_id = check_id(run_id)
        reason = _text(reason, "cancel reason", 2000)
        with _translated(), self._connect() as conn, conn.transaction():
            run_row = self._lock_run(conn, run_id)
            if run_row is None:
                return RunTransition(RunTransitionResult.UNKNOWN)
            state = RunState(run_row["state"])
            if state not in _CANCELLABLE_RUN_STATES:
                return RunTransition(RunTransitionResult.NOT_ALLOWED, _run(run_row))
            assert_run_transition(state, RunState.CANCELLED)
            updated = _one(
                conn,
                "UPDATE studio.production_runs SET state = 'CANCELLED', reason = %s, "
                f"updated_at = statement_timestamp() WHERE run_id = %s RETURNING {_RUN_COLS}",
                (reason, run_id),
            )
            conn.execute("UPDATE studio.stage_executions SET state = 'CANCELLED', lease_owner = NULL, "
                         "lease_expires_at = NULL, updated_at = statement_timestamp() "
                         "WHERE run_id = %s AND state IN ('PENDING', 'RUNNING', 'WAITING_HUMAN', 'FAILED')",
                         (run_id,))
            self._emit(conn, run_id, ProgressEventType.RUN_STATE_CHANGED,
                       {"from": state.value, "to": RunState.CANCELLED.value, "reason": reason})
            return RunTransition(RunTransitionResult.APPLIED, _run(updated))

    # -- outbox ------------------------------------------------------------

    def read_outbox(self, limit: int = 100, *, run_id: str | None = None) -> list[OutboxEvent]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("outbox read limit must be an integer between 1 and 1000")
        if run_id is not None:
            run_id = check_id(run_id)
        sql = f"SELECT {_OUTBOX_COLS} FROM studio.production_outbox WHERE acked_at IS NULL"
        params: tuple = ()
        if run_id is not None:
            sql += " AND run_id = %s"
            params += (run_id,)
        sql += " ORDER BY id LIMIT %s"
        with _translated(), self._connect() as conn:
            return [_event(row) for row in _all(conn, sql, (*params, limit))]

    def ack_outbox(self, event_id: int) -> AckResult:
        if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1:
            raise ValueError("outbox event id must be a positive integer")
        with _translated(), self._connect() as conn, conn.transaction():
            acked = _one(
                conn,
                "UPDATE studio.production_outbox SET acked_at = statement_timestamp() "
                "WHERE id = %s AND acked_at IS NULL RETURNING id",
                (event_id,),
            )
            if acked is not None:
                return AckResult.ACKED
            exists = _one(conn, "SELECT 1 AS ok FROM studio.production_outbox WHERE id = %s", (event_id,))
            return AckResult.ALREADY_ACKED if exists is not None else AckResult.UNKNOWN

    # -- internos ----------------------------------------------------------

    def _stage(self, stage_id: ProductionStage) -> ProductionStage:
        try:
            stage = stage_id if isinstance(stage_id, ProductionStage) else ProductionStage(stage_id)
        except ValueError as exc:
            raise ValueError(f"unknown production stage: {stage_id!r}") from exc
        if stage not in self._dag.stages:
            raise StageNotInDag(f"stage {stage.value} is not in this pipeline")
        return stage

    @staticmethod
    def _checkpoint(checkpoint: Checkpoint | None) -> Checkpoint | None:
        if checkpoint is not None and not isinstance(checkpoint, Checkpoint):
            raise TypeError("checkpoint must be a Checkpoint")
        return checkpoint

    @staticmethod
    def _lock_run(conn: psycopg.Connection, run_id: str) -> dict | None:
        # Trava o run antes das etapas: toda escrita do mesmo run passa por esta ordem.
        return _one(conn, f"SELECT {_RUN_COLS} FROM studio.production_runs WHERE run_id = %s FOR UPDATE",
                    (run_id,))

    @staticmethod
    def _lock_stage(conn: psycopg.Connection, run_id: str, stage: ProductionStage) -> dict | None:
        return _one(conn, f"SELECT {_STAGE_COLS} FROM studio.stage_executions "
                          f"WHERE run_id = %s AND stage_id = %s FOR UPDATE", (run_id, stage.value))

    def _pending_prerequisites(self, conn: psycopg.Connection, run_id: str,
                               stage: ProductionStage) -> tuple[str, ...]:
        """Estágios que faltam concluir para a etapa poder rodar; vazio significa pronto."""
        needs = self._dag.prerequisites(stage)
        if not needs:
            return ()
        rows = _all(conn, "SELECT stage_id, state FROM studio.stage_executions "
                          "WHERE run_id = %s AND stage_id = ANY(%s)",
                    (run_id, [need.value for need in needs]))
        done = {row["stage_id"] for row in rows if row["state"] in ("SUCCEEDED", "SKIPPED")}
        return tuple(sorted(need.value for need in needs if need.value not in done))

    def _write_guard(self, conn: psycopg.Connection, run_row: dict, stage_row: dict, owner: str,
                     fencing_token: int) -> StageTransitionResult | None:
        """CAS de escrita: estado atual, dono, token e lease válido. None significa autorizado."""
        if StageState(stage_row["state"]) is not StageState.RUNNING:
            return StageTransitionResult.NOT_RUNNING
        if RunState(run_row["state"]) is not RunState.RUNNING:
            return StageTransitionResult.LOST
        if stage_row["lease_owner"] != owner or stage_row["fencing_token"] != fencing_token:
            return StageTransitionResult.LOST
        now = _one(conn, "SELECT statement_timestamp() AS now")["now"]
        expires = stage_row["lease_expires_at"]
        if expires is None or expires <= now:
            return StageTransitionResult.LOST
        return None

    @staticmethod
    def _emit(conn: psycopg.Connection, run_id: str, event_type: ProgressEventType, payload: dict,
              stage_id: ProductionStage | None = None) -> None:
        conn.execute(
            "INSERT INTO studio.production_outbox(run_id, stage_id, event_type, event_version, payload) "
            "VALUES (%s, %s, %s, %s, %s)",
            (run_id, stage_id.value if stage_id is not None else None, event_type.value, EVENT_VERSION,
             Jsonb(payload)),
        )


def build_postgres_production_run_repository(
        connect: Callable[[], psycopg.Connection], *, dag: StageDag = STANDARD_DAG
) -> PostgresProductionRunRepository:
    """Factory para o controlador ligar em `composition.py` (esta fatia não edita a raiz de composição)."""
    return PostgresProductionRunRepository(connect, dag)