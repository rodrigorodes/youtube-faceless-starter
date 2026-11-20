"""Testes do domínio puro de execução de produção: DAG, estados, entidades e resultados explícitos.

Sem I/O: só `app.studio.domain.production_run`. O comportamento transacional (CAS, lease, outbox)
é coberto em `tests/test_production_repo.py`.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.domain.ids import InvalidId  # noqa: E402
from app.studio.domain.production_run import (  # noqa: E402
    STANDARD_DAG,
    Checkpoint,
    CreateRunResult,
    ExplicitResult,
    IncompleteStageSet,
    InvalidIdempotencyKey,
    InvalidPipeline,
    InvalidProductionTransition,
    ProductionError,
    ProductionRun,
    ProductionRunLockTimeout,
    ProductionRunReferencedEntityNotFound,
    ProductionStage,
    ProgressEventType,
    RunState,
    StageClaimResult,
    StageCycleError,
    StageDag,
    StageExecution,
    StageNotInDag,
    StageState,
    StageTransitionResult,
    UnknownStageDependency,
    assert_run_transition,
    assert_stage_transition,
    canonical_idempotency_key,
    can_run_transition,
    can_stage_transition,
)

S = ProductionStage


def test_standard_dag_orders_the_canonical_pipeline():
    assert STANDARD_DAG.topological_order() == (
        S.RESEARCH, S.SCRIPT, S.FACTCHECK, S.STORYBOARD, S.ASSETS, S.RENDER, S.QA, S.APPROVAL, S.PUBLISH,
    )
    assert tuple(ProductionStage) == STANDARD_DAG.topological_order()


def test_topological_order_uses_declared_dependencies_not_declaration_order():
    dag = StageDag({
        S.PUBLISH: (S.RENDER, S.QA),
        S.QA: (S.RENDER,),
        S.RENDER: (),
    })
    assert dag.stages == (S.PUBLISH, S.QA, S.RENDER)
    assert dag.topological_order() == (S.RENDER, S.QA, S.PUBLISH)
    assert dag.prerequisites(S.PUBLISH) == frozenset({S.RENDER, S.QA})


def test_cycle_is_rejected():
    with pytest.raises(StageCycleError):
        StageDag({S.SCRIPT: (S.RENDER,), S.RENDER: (S.SCRIPT,)})


def test_self_dependency_is_a_cycle():
    with pytest.raises(StageCycleError):
        StageDag({S.ASSETS: (S.ASSETS,)})


def test_unknown_dependency_is_rejected():
    with pytest.raises(UnknownStageDependency):
        StageDag({S.SCRIPT: (S.RESEARCH,)})
    with pytest.raises(UnknownStageDependency):
        StageDag({S.SCRIPT: (S.RESEARCH,), S.RESEARCH: (S.FACTCHECK,)})


def test_empty_pipeline_is_rejected():
    with pytest.raises(InvalidPipeline):
        StageDag({})


def test_can_run_requires_every_prerequisite():
    assert STANDARD_DAG.can_run(S.RESEARCH, set())
    assert not STANDARD_DAG.can_run(S.SCRIPT, set())
    assert STANDARD_DAG.can_run(S.SCRIPT, {S.RESEARCH})
    assert not STANDARD_DAG.can_run(S.QA, {S.RESEARCH, S.SCRIPT, S.FACTCHECK, S.STORYBOARD, S.ASSETS, S.RENDER} - {S.RENDER})


def test_validate_stages_accepts_a_closed_subset_and_rejects_an_open_one():
    assert STANDARD_DAG.validate_stages([S.SCRIPT, S.RESEARCH]) == (S.RESEARCH, S.SCRIPT)
    with pytest.raises(IncompleteStageSet):
        STANDARD_DAG.validate_stages([S.SCRIPT])
    with pytest.raises(IncompleteStageSet):
        STANDARD_DAG.validate_stages([])
    with pytest.raises(InvalidPipeline):
        STANDARD_DAG.validate_stages([S.RESEARCH, S.RESEARCH])
    with pytest.raises(StageNotInDag):
        StageDag({S.RESEARCH: ()}).validate_stages([S.SCRIPT])


def test_run_transitions_are_explicit():
    assert can_run_transition(RunState.CREATED, RunState.RUNNING)
    assert can_run_transition(RunState.RUNNING, RunState.WAITING_HUMAN)
    assert can_run_transition(RunState.WAITING_HUMAN, RunState.RUNNING)
    assert can_run_transition(RunState.FAILED, RunState.RUNNING)
    assert not can_run_transition(RunState.SUCCEEDED, RunState.RUNNING)
    assert not can_run_transition(RunState.CANCELLED, RunState.RUNNING)
    assert_run_transition(RunState.CREATED, RunState.CANCELLED)
    with pytest.raises(InvalidProductionTransition):
        assert_run_transition(RunState.CANCELLED, RunState.RUNNING)


def test_stage_transitions_are_explicit():
    assert can_stage_transition(StageState.PENDING, StageState.RUNNING)
    assert can_stage_transition(StageState.RUNNING, StageState.RUNNING)  # retomada de etapa órfã
    assert can_stage_transition(StageState.RUNNING, StageState.SUCCEEDED)
    assert can_stage_transition(StageState.FAILED, StageState.RUNNING)
    assert can_stage_transition(StageState.WAITING_HUMAN, StageState.PENDING)
    assert not can_stage_transition(StageState.SUCCEEDED, StageState.RUNNING)
    assert_stage_transition(StageState.PENDING, StageState.CANCELLED)
    with pytest.raises(InvalidProductionTransition):
        assert_stage_transition(StageState.SUCCEEDED, StageState.RUNNING)


def test_result_enums_refuse_truthiness():
    assert issubclass(StageClaimResult, ExplicitResult)
    for result in (StageClaimResult.CLAIMED, StageTransitionResult.APPLIED, CreateRunResult.EXISTING):
        with pytest.raises(TypeError):
            bool(result)


def test_checkpoint_requires_an_object_payload_and_positive_version():
    assert Checkpoint({"artifact": "x"}, 1).version == 1
    for payload, version in ((["x"], 1), ({"x": 1}, 0), ({"x": 1}, True), ({"x": 1}, "1")):
        with pytest.raises(ValueError):
            Checkpoint(payload, version)


def test_stage_execution_enforces_the_lease_invariant():
    running = StageExecution("a" * 32, S.RESEARCH, StageState.RUNNING, 1, lease_owner="w1",
                             lease_expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fencing_token=1)
    assert running.lease_owner == "w1"
    with pytest.raises(ValueError):
        StageExecution("a" * 32, S.RESEARCH, StageState.RUNNING, 1, fencing_token=1)  # sem dono
    with pytest.raises(ValueError):
        StageExecution("a" * 32, S.RESEARCH, StageState.RUNNING, 1, lease_owner="w1", fencing_token=1)  # sem expiração
    with pytest.raises(ValueError):
        StageExecution("a" * 32, S.RESEARCH, StageState.PENDING, 0, lease_owner="w1")  # dono sem RUNNING
    with pytest.raises(ValueError):
        StageExecution("a" * 32, S.RESEARCH, StageState.PENDING, -1)
    with pytest.raises(ValueError):
        StageExecution("a" * 32, S.RESEARCH, StageState.PENDING, 0, fencing_token=-1)


def test_production_run_validates_ids_and_key():
    run = ProductionRun("a" * 32, "b" * 32, "key-1")
    assert run.state is RunState.CREATED and run.schema_version == 1
    with pytest.raises(InvalidId):
        ProductionRun("not-an-id", "b" * 32, "key-1")
    with pytest.raises(InvalidId):
        ProductionRun("a" * 32, "b" * 32, "key-1", channel_id="nope")
    for key in ("", "   ", None):
        with pytest.raises(ValueError):
            ProductionRun("a" * 32, "b" * 32, key)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProductionRun("a" * 32, "b" * 32, "key-1", schema_version=0)


def test_progress_event_names_are_versioned_strings():
    assert ProgressEventType.RUN_STATE_CHANGED.value == "production.run.state_changed"
    assert ProgressEventType.STAGE_COMPLETED.value == "production.stage.completed"


def test_idempotency_key_is_canonical_and_is_not_normalized():
    """Identidade byte-a-byte: só a forma canônica (minúscula, sem espaço/invisível) é aceita."""
    assert canonical_idempotency_key("order-42") == "order-42"
    assert ProductionRun("a" * 32, "b" * 32, "order-42").idempotency_key == "order-42"
    for spelling in ("order-42 ", " order-42", "ORDER-42", "Order-42", "order 42", "order\t42",
                     "order\u200b42", "order\u00a042"):
        with pytest.raises(InvalidIdempotencyKey):
            canonical_idempotency_key(spelling)
    for bad in ("", "x" * 201, None, 42):
        with pytest.raises(InvalidIdempotencyKey):
            canonical_idempotency_key(bad)
    with pytest.raises(InvalidIdempotencyKey):
        ProductionRun("a" * 32, "b" * 32, "ORDER-42")


def test_database_contention_and_missing_references_have_domain_errors():
    assert issubclass(ProductionRunLockTimeout, ProductionError)
    assert issubclass(ProductionRunReferencedEntityNotFound, ProductionError)