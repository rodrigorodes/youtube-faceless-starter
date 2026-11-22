"""Coordenador/worker (D2): laço com lease/fencing/checkpoint e os dois modos de produção.

Roda contra o repositório Postgres real (descartável, com prova) e handlers-stub — exercita o CAS
de verdade sem depender de provedores externos. Sem as variáveis do banco descartável é ignorado.
"""
import os

import pytest

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
from app.studio.application.production import (
    COORDINATOR_DAG,
    BudgetProjection,
    Production,
    ProductionCoordinator,
    ProductionMode,
    ProductionWorker,
    StageCapabilityUnavailable,
    StageExecutionFailed,
    StageOutcome,
    UnavailableStageHandler,
    WorkerStepResult,
)
from app.studio.domain.production_run import (
    Checkpoint,
    CreateRunResult,
    ProductionRun,
    ProductionStage,
    RunState,
    RunTransitionResult,
    StageClaim,
    StageClaimResult,
    StageDag,
    StageExecution,
    StageState,
    StageTransition,
    StageTransitionResult,
)
from conftest import verified_test_connect

PROJECT, VIDEO, CHANNEL = "a" * 32, "b" * 32, "d" * 32
AVAILABLE = (ProductionStage.SCRIPT, ProductionStage.FACTCHECK, ProductionStage.STORYBOARD,
             ProductionStage.ASSETS, ProductionStage.RENDER, ProductionStage.QA, ProductionStage.APPROVAL,
             ProductionStage.PUBLISH)


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável de produção não configurado")
    return value


@pytest.fixture
def conn(dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    connection = verified_test_connect(dsn, proof)
    try:
        connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.close()


@pytest.fixture
def db(conn, dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'canal')", (PROJECT,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema', 'short')",
                 (VIDEO, PROJECT))
    conn.execute("INSERT INTO studio.channel_profiles(id, project_id, name) VALUES (%s, %s, 'canal')",
                 (CHANNEL, PROJECT))
    conn.commit()
    repo = PostgresProductionRunRepository(lambda: verified_test_connect(dsn, proof), COORDINATOR_DAG)
    return repo, conn


class _StubHandler:
    available = True

    def __init__(self, stage, *, request_human=None, error=None):
        self.stage, self._request_human, self._error = stage, request_human, error
        self.calls = 0

    def execute(self, context):
        self.calls += 1
        if self._error is not None:
            raise StageExecutionFailed(self._error)
        return StageOutcome(
            checkpoint=Checkpoint({"stage": self.stage.value}, context.checkpoint_version),
            request_human=self._request_human)


def handlers(**overrides):
    built = {stage: _StubHandler(stage) for stage in AVAILABLE}
    built.update(overrides)
    built[ProductionStage.RESEARCH] = UnavailableStageHandler(ProductionStage.RESEARCH, "sem research")
    return built


def _coordinator(db, *, mode=ProductionMode.INTERACTIVE, budget=None, overrides=None):
    repo, _ = db
    return ProductionCoordinator(repo, handlers=handlers(**(overrides or {})), mode=mode, budget=budget)


def _stages(conn, run_id):
    rows = conn.execute("SELECT stage_id, state FROM studio.stage_executions WHERE run_id = %s", (run_id,)).fetchall()
    return dict(rows)


def _run_state(conn, run_id):
    return conn.execute("SELECT state FROM studio.production_runs WHERE run_id = %s", (run_id,)).fetchone()[0]


def test_default_pipeline_excludes_unavailable_stages(db):
    coordinator = _coordinator(db)
    assert coordinator.default_pipeline() == AVAILABLE
    unavailable = dict(coordinator.unavailable_stages())
    assert set(unavailable) == {ProductionStage.RESEARCH}


def test_start_is_idempotent_and_persists_the_available_stages(db):
    repo, conn = db
    coordinator = _coordinator(db)
    first = coordinator.start(VIDEO, "run-key-1")
    assert first.result is CreateRunResult.CREATED
    assert _stages(conn, first.run.run_id) == {stage.value: "PENDING" for stage in AVAILABLE}
    replay = coordinator.start(VIDEO, "run-key-1")
    assert replay.result is CreateRunResult.EXISTING
    assert replay.run.run_id == first.run.run_id
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1


def test_start_refuses_unavailable_and_unknown_stages(db):
    coordinator = _coordinator(db)
    with pytest.raises(StageCapabilityUnavailable):
        coordinator.start(VIDEO, "run-key-3", stages=[ProductionStage.RESEARCH])
    with pytest.raises(StageCapabilityUnavailable):
        coordinator.start(VIDEO, "run-key-4", stages=["nope"])  # type: ignore[list-item]
    _, conn = db
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0


def test_interactive_worker_pauses_after_script_and_resumes(db):
    repo, conn = db
    coordinator = _coordinator(db, mode=ProductionMode.INTERACTIVE)
    run_id = coordinator.start(VIDEO, "run-key-5").run.run_id
    worker = ProductionWorker(coordinator, owner="worker-1")

    steps = worker.work(run_id)
    assert steps[-1].result is WorkerStepResult.COMPLETED_PAUSED
    assert _run_state(conn, run_id) == RunState.WAITING_HUMAN.value
    assert _stages(conn, run_id)["script"] == StageState.SUCCEEDED.value
    assert _stages(conn, run_id)["factcheck"] == StageState.PENDING.value

    # A pausa libera o worker: novo passo não pega nada e não bloqueia.
    assert coordinator.step(run_id, owner="worker-1").result is WorkerStepResult.TERMINAL
    assert coordinator.resume(run_id).result is RunTransitionResult.APPLIED

    steps = worker.work(run_id)
    assert steps[-1].result is WorkerStepResult.TERMINAL
    assert _run_state(conn, run_id) == RunState.SUCCEEDED.value
    assert set(_stages(conn, run_id).values()) == {"SUCCEEDED"}


def test_gate_after_script_is_crossed_when_the_service_resumes(db):
    """O teste que teria pegado o bug: retomar pelo serviço tem de relançar o worker.

    O `POST .../resume` chamava o coordenador direto: o estado virava RUNNING e o run morria
    parado (a etapa seguinte nunca saía de PENDING). Aqui o `submit` roda o worker de verdade.
    """
    repo, conn = db
    coordinator = _coordinator(db)
    worker = ProductionWorker(coordinator, owner="w")
    service = Production(coordinator=coordinator, worker=worker, submit=lambda run_id: worker.work(run_id))

    run_id = service.start(VIDEO, "run-key-gate").run.run_id
    assert _run_state(conn, run_id) == RunState.WAITING_HUMAN.value
    assert _stages(conn, run_id)["factcheck"] == StageState.PENDING.value

    transition = service.resume(run_id)
    assert transition.result is RunTransitionResult.APPLIED
    assert _stages(conn, run_id)["factcheck"] == StageState.SUCCEEDED.value
    assert _run_state(conn, run_id) == RunState.SUCCEEDED.value


def test_orphan_running_with_an_expired_lease_is_recovered_by_the_service(db):
    """RUNNING órfão (thread morta, lease expirado) é re-lançado sem escrever estado."""
    repo, conn = db
    coordinator = _coordinator(db)
    worker = ProductionWorker(coordinator, owner="w")
    submitted = []

    def submit(run_id):
        submitted.append(run_id)
        worker.work(run_id)

    service = Production(coordinator=coordinator, worker=worker, submit=submit)
    run_id = service.start(VIDEO, "run-key-orphan").run.run_id  # pausa após o roteiro
    assert _run_state(conn, run_id) == RunState.WAITING_HUMAN.value
    submitted.clear()  # o start já relançou; aqui interessa só o re-drive do resume

    # Simula a thread morta: run RUNNING com lease de etapa já expirado (nenhum dono vivo).
    conn.execute("UPDATE studio.production_runs SET state = 'RUNNING' WHERE run_id = %s", (run_id,))
    conn.execute("UPDATE studio.stage_executions SET state = 'RUNNING', lease_owner = 'dead-worker', "
                 "lease_expires_at = statement_timestamp() - interval '1 minute' "
                 "WHERE run_id = %s AND stage_id = 'factcheck'", (run_id,))
    conn.commit()
    assert coordinator.get(run_id).run.state is RunState.RUNNING

    transition = service.resume(run_id, expected_state=RunState.RUNNING)
    assert transition.result is RunTransitionResult.APPLIED
    assert submitted == [run_id]
    assert _run_state(conn, run_id) == RunState.SUCCEEDED.value


def test_budget_guarded_auto_continues_only_within_the_ceiling(db):
    class Budget:
        def __init__(self, projection):
            self.projection = projection

        def project(self, run, next_stage):
            return self.projection

    from decimal import Decimal

    repo, conn = db
    within = _coordinator(db, mode=ProductionMode.BUDGET_GUARDED,
                          budget=Budget(BudgetProjection(Decimal("1"), Decimal("10"))))
    run_id = within.start(VIDEO, "run-key-6").run.run_id
    steps = ProductionWorker(within, owner="w").work(run_id)
    assert all(step.result is not WorkerStepResult.COMPLETED_PAUSED for step in steps)
    assert _run_state(conn, run_id) == RunState.SUCCEEDED.value

    # Projeção desconhecida ou acima do teto volta a exigir humano (falha fechada).
    for index, projection in enumerate((None, BudgetProjection(Decimal("11"), Decimal("10")))):
        repo2 = PostgresProductionRunRepository(
            lambda: verified_test_connect(os.environ["STUDIO_BUDGET_DISPOSABLE_DSN"],
                                          os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]), COORDINATOR_DAG)
        guarded = ProductionCoordinator(repo2, handlers=handlers(), mode=ProductionMode.BUDGET_GUARDED,
                                        budget=Budget(projection))
        rid = guarded.start(VIDEO, f"run-key-guard-{index}").run.run_id
        assert ProductionWorker(guarded, owner="w").work(rid)[-1].result is WorkerStepResult.COMPLETED_PAUSED
        assert _run_state(conn, rid) == RunState.WAITING_HUMAN.value


def test_approval_stage_pauses_without_human_decision(db):
    repo, conn = db
    approval = _StubHandler(ProductionStage.APPROVAL, request_human="aguardando humano")
    coordinator = _coordinator(db, overrides={ProductionStage.APPROVAL: approval})
    run_id = coordinator.start(VIDEO, "run-key-7").run.run_id
    worker = ProductionWorker(coordinator, owner="w")

    assert worker.work(run_id)[-1].result is WorkerStepResult.COMPLETED_PAUSED  # pausa após o roteiro
    assert coordinator.resume(run_id).result is RunTransitionResult.APPLIED
    # Chega ao approval, que pede humano e NÃO conclui (publicação nunca auto-aprova).
    assert worker.work(run_id)[-1].result is WorkerStepResult.PAUSED
    assert _stages(conn, run_id)["approval"] == StageState.WAITING_HUMAN.value
    assert _run_state(conn, run_id) == RunState.WAITING_HUMAN.value
    assert _stages(conn, run_id)["script"] == StageState.SUCCEEDED.value


def test_failed_stage_blocks_and_retry_resumes(db):
    repo, conn = db
    broken = _StubHandler(ProductionStage.FACTCHECK, error="provedor caiu")
    coordinator = _coordinator(db, overrides={ProductionStage.FACTCHECK: broken})
    run_id = coordinator.start(VIDEO, "run-key-8").run.run_id
    assert ProductionWorker(coordinator, owner="w").work(run_id)[-1].result is WorkerStepResult.COMPLETED_PAUSED
    coordinator.resume(run_id)
    assert ProductionWorker(coordinator, owner="w").work(run_id)[-1].result is WorkerStepResult.FAILED
    assert _run_state(conn, run_id) == RunState.FAILED.value
    assert _stages(conn, run_id)["factcheck"] == StageState.FAILED.value

    assert coordinator.pause(run_id, "x").result is RunTransitionResult.NOT_ALLOWED
    assert coordinator.retry(run_id).result is RunTransitionResult.APPLIED
    assert _run_state(conn, run_id) == RunState.RUNNING.value


def test_cancel_terminates_the_run_and_actions_are_state_validated(db):
    repo, conn = db
    coordinator = _coordinator(db)
    run_id = coordinator.start(VIDEO, "run-key-9").run.run_id
    assert coordinator.cancel(run_id, "operador").result is RunTransitionResult.APPLIED
    assert _run_state(conn, run_id) == RunState.CANCELLED.value
    assert coordinator.resume(run_id).result is RunTransitionResult.NOT_ALLOWED
    assert coordinator.cancel(run_id, "de novo").result is RunTransitionResult.NOT_ALLOWED
    assert coordinator.step(run_id, owner="w").result is WorkerStepResult.TERMINAL


def test_status_projection_reports_next_action_and_events(db):
    repo, conn = db
    coordinator = _coordinator(db)
    run_id = coordinator.start(VIDEO, "run-key-10").run.run_id
    projection = coordinator.get(run_id)
    assert projection is not None
    assert projection.next_action == "run" and projection.next_stage is ProductionStage.SCRIPT
    assert len(projection.stages) == len(AVAILABLE)
    assert projection.mode is ProductionMode.INTERACTIVE
    assert [event.event_type.value for event in coordinator.events(run_id)] == ["production.run.created"]

    ProductionWorker(coordinator, owner="w").work(run_id)
    waiting = coordinator.get(run_id)
    assert waiting.next_action == "resume" and waiting.next_stage is ProductionStage.FACTCHECK
    assert "production.stage.completed" in [e.event_type.value for e in coordinator.events(run_id)]


def test_get_returns_none_for_unknown_run(db):
    coordinator = _coordinator(db)
    assert coordinator.get("0" * 32) is None


def test_list_stages_returns_the_dag_order_and_unknown_run_is_empty(db):
    repo, conn = db
    coordinator = _coordinator(db)
    run_id = coordinator.start(VIDEO, "run-key-11").run.run_id
    assert [stage.stage_id for stage in repo.list_stages(run_id)] == list(AVAILABLE)
    assert repo.list_stages("0" * 32) == ()


def test_worker_reports_lost_when_the_fence_rejects_the_completion():
    from datetime import datetime, timezone

    run = ProductionRun(run_id="1" * 32, video_id=VIDEO, idempotency_key="req-1")
    execution = StageExecution(run_id="1" * 32, stage_id=ProductionStage.SCRIPT, state=StageState.RUNNING,
                               attempt=1, fencing_token=1, lease_owner="w",
                               lease_expires_at=datetime.now(timezone.utc))

    class Runs:
        def get_run(self, run_id):
            return run

        def claim_stage(self, run_id, stage, owner, lease_seconds):
            return StageClaim(StageClaimResult.CLAIMED, execution)

        def complete_stage(self, *args, **kwargs):
            return StageTransition(StageTransitionResult.LOST)

        def list_stages(self, run_id):
            return ()

    handler = _StubHandler(ProductionStage.SCRIPT)
    coordinator = ProductionCoordinator(Runs(), handlers={ProductionStage.SCRIPT: handler},
                                        pipeline=StageDag({ProductionStage.SCRIPT: ()}))
    step = coordinator.step(run.run_id, owner="w")
    assert step.result is WorkerStepResult.LOST
    assert handler.calls == 1


# -- PROD-03: recuperação de boot ---------------------------------------------


def test_list_in_flight_returns_only_active_runs_with_their_stages(db):
    """A leitura de boot traz os runs em voo com as etapas numa chamada; terminais ficam de fora."""
    repo, conn = db
    run_id = repo.create_run("e" * 32, VIDEO, "key-in-flight").run.run_id

    in_flight = repo.list_in_flight()
    assert [run.run_id for run, _ in in_flight] == [run_id]
    assert len(in_flight[0][1]) == len(COORDINATOR_DAG.stages)  # todas as etapas, sem N+1

    conn.execute("UPDATE studio.production_runs SET state = 'SUCCEEDED' WHERE run_id = %s", (run_id,))
    conn.commit()
    assert repo.list_in_flight() == ()


def test_boot_recovery_redrives_a_running_run_left_without_any_lease(db):
    """A prova do deploy: um run RUNNING sem lease (thread morta) **avança** após a recuperação.

    Sem varredor, o run ficava parado para sempre; com a porta + a regra + o submit, a etapa sai
    de PENDING e o run volta a andar. Handlers-stub: sem rede.
    """
    repo, conn = db
    coordinator = _coordinator(db)
    worker = ProductionWorker(coordinator, owner="w")
    submitted = []

    def submit(run_id):
        submitted.append(run_id)
        worker.work(run_id)

    service = Production(coordinator=coordinator, worker=worker, submit=submit, in_flight=repo)
    run_id = service.start(VIDEO, "run-key-boot").run.run_id  # INTERACTIVE: pausa após o roteiro
    assert _stages(conn, run_id)["script"] == StageState.SUCCEEDED.value

    # Simula o restart no meio: o run segue RUNNING e nenhuma etapa tem lease (a thread morreu).
    conn.execute("UPDATE studio.production_runs SET state = 'RUNNING' WHERE run_id = %s", (run_id,))
    conn.execute("UPDATE studio.stage_executions SET state = 'PENDING', lease_owner = NULL, "
                 "lease_expires_at = NULL WHERE run_id = %s", (run_id,))
    conn.commit()
    assert _stages(conn, run_id)["script"] == StageState.PENDING.value
    submitted.clear()

    recovered = service.recover_in_flight()

    assert recovered == (run_id,)
    assert submitted == [run_id]
    # A etapa saiu de PENDING: o run não ficou mais abandonado.
    assert _stages(conn, run_id)["script"] == StageState.SUCCEEDED.value
    assert _run_state(conn, run_id) == RunState.WAITING_HUMAN.value


def test_boot_recovery_is_idempotent_and_skips_a_run_with_a_live_lease(db):
    """Rodar a recuperação duas vezes não faz mal; run com lease vivo não é re-dirigido."""
    repo, conn = db
    coordinator = _coordinator(db)
    worker = ProductionWorker(coordinator, owner="w")
    submitted = []
    service = Production(coordinator=coordinator, worker=worker,
                         submit=lambda run_id: (submitted.append(run_id), worker.work(run_id)),
                         in_flight=repo)
    run_id = service.start(VIDEO, "run-key-idem").run.run_id  # WAITING_HUMAN (sem lease vivo)

    # Um WAITING_HUMAN não entra na leitura de em voo (a porta só traz CREATED/RUNNING).
    assert repo.list_in_flight() == ()

    # Deixa-o RUNNING com lease vivo: nem a regra nem o submit o tocam.
    conn.execute("UPDATE studio.production_runs SET state = 'RUNNING' WHERE run_id = %s", (run_id,))
    conn.execute("UPDATE studio.stage_executions SET state = 'RUNNING', lease_owner = 'alive', "
                 "lease_expires_at = statement_timestamp() + interval '5 minutes' "
                 "WHERE run_id = %s AND stage_id = 'factcheck'", (run_id,))
    conn.commit()
    submitted.clear()

    assert service.recover_in_flight() == ()
    assert submitted == []
    assert service.recover_in_flight() == ()  # idempotente
    assert submitted == []


# -- F03.T02: resolução antes do efeito e snapshot imutável do run ---------------


class _Videos:
    """Leitura de vídeo injetada no coordenador (a resolução recebe o agregado já carregado)."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0

    def get_video(self, video_id):
        self.calls += 1
        return self.mapping.get(video_id)


def _video(video_id=VIDEO, project_id=PROJECT):
    from app.studio.domain.contracts import Video, VideoFormat

    return Video(id=video_id, project_id=project_id, topic="tema", format=VideoFormat.short)


def _config(video_id=VIDEO, **options):
    from app.studio.domain.effective_config import resolve_effective_config

    return resolve_effective_config(video=_video(video_id), **options)


def _resolving_coordinator(db, *, config=None):
    repo, _ = db
    videos = _Videos({VIDEO: _video()})
    coordinator = ProductionCoordinator(repo, handlers=handlers(), videos=videos, config_store=repo)
    frozen = config or _config()
    calls = []

    def resolver(video):
        calls.append(video.id)
        return frozen

    return coordinator, repo, resolver, calls, frozen


def test_start_resolves_the_config_and_persists_the_snapshot_before_any_effect(db):
    from app.studio.domain.run_config import RunConfigStatus

    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    creation = coordinator.start(VIDEO, "run-config-1", effective_config_for=resolver, config_store=repo)
    assert creation.result is CreateRunResult.CREATED
    assert calls == [VIDEO]

    stored = coordinator.config_for(creation.run.run_id)
    assert stored is not None and stored.status is RunConfigStatus.RESOLVED
    assert stored.config is not None and stored.config.content_hash == frozen.content_hash
    # Nada executou: as etapas continuam PENDING e a config já está congelada.
    repo2, conn = db
    assert set(_stages(conn, creation.run.run_id).values()) == {"PENDING"}


def test_replay_with_the_same_key_returns_the_same_run_and_snapshot(db):
    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    first = coordinator.start(VIDEO, "run-config-2", effective_config_for=resolver, config_store=repo)
    replay = coordinator.start(VIDEO, "run-config-2", effective_config_for=resolver, config_store=repo)
    assert replay.result is CreateRunResult.EXISTING
    assert replay.run.run_id == first.run.run_id
    assert len(calls) == 2  # a segunda chamada resolve só para comparar; não sobrescreve
    stored = coordinator.config_for(first.run.run_id)
    assert stored.config.content_hash == frozen.content_hash
    _, conn = db
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1


def test_replay_with_a_divergent_config_is_a_conflict_without_a_second_run(db):
    from app.studio.domain.run_config import RunConfigConflict

    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    first = coordinator.start(VIDEO, "run-config-3", effective_config_for=resolver, config_store=repo)
    divergent = _config(provider_profile="PREMIUM")
    with pytest.raises(RunConfigConflict):
        coordinator.start(VIDEO, "run-config-3",
                          effective_config_for=lambda video: divergent, config_store=repo)
    _, conn = db
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1
    assert coordinator.config_for(first.run.run_id).config.content_hash == frozen.content_hash


def test_a_legacy_run_is_marked_and_is_never_silently_re_resolved(db):
    from app.studio.domain.run_config import RunConfigConflict, RunConfigStatus

    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    legacy = coordinator.start(VIDEO, "run-config-4")  # sem resolvedor: comportamento preservado
    stored = coordinator.config_for(legacy.run.run_id)
    assert stored is not None and stored.status is RunConfigStatus.LEGACY and stored.config is None
    with pytest.raises(RunConfigConflict):
        coordinator.start(VIDEO, "run-config-4", effective_config_for=resolver, config_store=repo)
    assert coordinator.config_for(legacy.run.run_id).status is RunConfigStatus.LEGACY
    assert calls == [VIDEO]  # resolveu só para comparar; nada foi adotado nem sobrescrito
    _, conn = db
    assert conn.execute("SELECT config_snapshot FROM studio.production_runs "
                        "WHERE run_id = %s", (legacy.run.run_id,)).fetchone()[0] is None


def test_resume_and_retry_read_the_persisted_snapshot_and_never_re_resolve(db):
    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    run_id = coordinator.start(VIDEO, "run-config-5",
                               effective_config_for=resolver, config_store=repo).run.run_id
    before = coordinator.config_for(run_id).config.content_hash
    ProductionWorker(coordinator, owner="w").work(run_id)  # pausa após o roteiro
    assert coordinator.resume(run_id).result is RunTransitionResult.APPLIED
    _, conn = db
    conn.execute("UPDATE studio.production_runs SET state = 'FAILED', reason = 'x' WHERE run_id = %s",
                 (run_id,))
    conn.commit()
    assert coordinator.retry(run_id).result is RunTransitionResult.APPLIED
    assert coordinator.config_for(run_id).config.content_hash == before
    assert calls == [VIDEO]  # resolver rodou só no start; retomada/retry só leem


def test_start_with_a_resolver_requires_an_existing_video(db):
    from app.studio.domain.production_run import ProductionRunReferencedEntityNotFound

    repo, conn = db
    coordinator = ProductionCoordinator(repo, handlers=handlers(), videos=_Videos({}), config_store=repo)
    with pytest.raises(ProductionRunReferencedEntityNotFound):
        coordinator.start(VIDEO, "run-config-6", effective_config_for=lambda video: _config(),
                          config_store=repo)
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0


def test_start_with_a_resolver_requires_a_video_reader(db):
    repo, conn = db
    coordinator = ProductionCoordinator(repo, handlers=handlers())
    with pytest.raises(ValueError):
        coordinator.start(VIDEO, "run-config-7", effective_config_for=lambda video: _config())
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0


def test_the_service_forwards_the_resolver_and_exposes_the_stored_config(db):
    from app.studio.domain.run_config import RunConfigStatus

    coordinator, repo, resolver, calls, frozen = _resolving_coordinator(db)
    service = Production(coordinator=coordinator, worker=ProductionWorker(coordinator, owner="w"),
                         effective_config_for=resolver, config_store=repo)
    creation = service.start(VIDEO, "run-config-8")
    stored = service.config_for(creation.run.run_id)
    assert stored.status is RunConfigStatus.RESOLVED
    assert stored.config.content_hash == frozen.content_hash
    assert calls == [VIDEO]
