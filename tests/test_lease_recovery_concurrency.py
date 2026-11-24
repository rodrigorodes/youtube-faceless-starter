"""Provas de concorrência do heartbeat de lease e da recuperação periódica (plano lease-recovery, Task 8).

Rodam contra o Postgres real descartável (o CAS de verdade) com handlers e uploader de mentira — nenhuma
rede. Sem as variáveis do banco descartável o módulo de DB é ignorado. Os "controles negativos" desligam
o mecanismo em questão (monkeypatch dentro do teste) e provam que a asserção correspondente falharia.
"""
import asyncio
import os
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
from app.studio.adapters.postgres.publish_repo import PostgresPublicationRepository
from app.studio.application import production as production_module
from app.studio.application.lease_heartbeat import LeaseHeartbeat
from app.studio.application.production import (
    COORDINATOR_DAG,
    ActiveRuns,
    Production,
    ProductionCoordinator,
    ProductionMode,
    ProductionWorker,
    PublishHandler,
    StageOutcome,
    UnavailableStageHandler,
    WorkerStepResult,
)
from app.studio.domain.production_run import (
    Checkpoint,
    LeaseResult,
    ProductionStage,
    RunState,
    StageClaimResult,
    StageTransitionResult,
)
from conftest import verified_test_connect

PROJECT, VIDEO, CHANNEL = "a" * 32, "b" * 32, "d" * 32
AVAILABLE = (ProductionStage.SCRIPT, ProductionStage.FACTCHECK, ProductionStage.STORYBOARD,
             ProductionStage.ASSETS, ProductionStage.RENDER, ProductionStage.QA, ProductionStage.APPROVAL,
             ProductionStage.PUBLISH)
SCRIPT = ProductionStage.SCRIPT


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
    connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    return PostgresProductionRunRepository(connect, COORDINATOR_DAG), conn, connect


class CountingHandler:
    available = True

    def __init__(self, stage, *, hold=None):
        self.stage, self.hold, self.calls = stage, hold, 0
        self._lock = threading.Lock()

    def execute(self, context):
        with self._lock:
            self.calls += 1
        if self.hold is not None:
            self.hold(context)
        return StageOutcome(checkpoint=Checkpoint({"stage": self.stage.value}, context.checkpoint_version))


def handlers(overrides=None):
    built = {stage: CountingHandler(stage) for stage in AVAILABLE}
    built.update(overrides or {})
    built[ProductionStage.RESEARCH] = UnavailableStageHandler(ProductionStage.RESEARCH, "sem research")
    return built


def coordinator_for(repo, *, lease_seconds=300, overrides=None):
    return ProductionCoordinator(repo, handlers=handlers(overrides), mode=ProductionMode.INTERACTIVE,
                                 lease_seconds=lease_seconds)


def stage_row(conn, run_id, stage):
    conn.rollback()  # fim de qualquer snapshot anterior: lê o estado mais recente
    return conn.execute(
        "SELECT state, attempt, fencing_token, lease_owner, checkpoint, checkpoint_version "
        "FROM studio.stage_executions WHERE run_id = %s AND stage_id = %s", (run_id, stage.value)).fetchone()


def expire_lease(conn, run_id, stage):
    conn.execute("UPDATE studio.stage_executions SET lease_expires_at = statement_timestamp() - interval '1 minute' "
                 "WHERE run_id = %s AND stage_id = %s", (run_id, stage.value))
    conn.commit()


def backdate(conn, run_id):
    conn.execute("UPDATE studio.production_runs SET updated_at = statement_timestamp() - interval '1 hour', "
                 "created_at = statement_timestamp() - interval '1 hour' "
                 "WHERE run_id = %s", (run_id,))
    conn.execute("UPDATE studio.stage_executions SET updated_at = statement_timestamp() - interval '1 hour' "
                 "WHERE run_id = %s", (run_id,))
    conn.commit()


def add_video(conn, number):
    video = f"{number:032x}"
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema', 'short')",
                 (video, PROJECT))
    conn.commit()
    return video


class NoRenewHeartbeat(LeaseHeartbeat):
    """Controle negativo: o mecanismo de renovação removido (a thread nunca renova)."""

    def _run(self):
        return


# -- 1. heartbeat segura a posse -------------------------------------------------------------------


def _contest_script_lease(db, monkeypatch, *, heartbeat_on):
    """A executa um handler de 8 s com lease de 3 s; B tenta `claim` a cada 0,5 s durante a execução.

    Margem de tempo: renovação a cada lease/3 = 1 s, lease de 3 s ⇒ 3 renovações por janela de lease
    (≥ 3 intervalos de folga); o handler dura ~2,7 leases, então sem renovação o lease vence com folga.
    """
    repo, conn, _ = db
    if not heartbeat_on:
        monkeypatch.setattr(production_module, "LeaseHeartbeat", NoRenewHeartbeat)
    release = threading.Event()
    in_handler = threading.Event()

    def hold(ctx):
        release.wait(8)
        in_handler.set()

    slow = CountingHandler(SCRIPT, hold=hold)
    coordinator = coordinator_for(repo, lease_seconds=3, overrides={SCRIPT: slow})
    run_id = coordinator.start(VIDEO, "hold-1").run.run_id
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("a", coordinator.step(run_id, owner="worker-a")))
    worker.start()
    time.sleep(0.3)  # A já adquiriu o lease e está dentro do handler
    seen = []
    deadline = time.monotonic() + 8.5
    while worker.is_alive() and not in_handler.is_set() and time.monotonic() < deadline:
        result = repo.claim_stage(run_id, SCRIPT, "worker-b", 3).result
        if not in_handler.is_set():  # tentativas feitas depois de o handler terminar não contam
            seen.append(result)
        time.sleep(0.5)
    worker.join(timeout=15)
    return run_id, slow, results["a"], seen


def test_heartbeat_keeps_ownership_while_a_slow_handler_runs(db, monkeypatch):
    repo, conn, _ = db
    run_id, slow, step, seen = _contest_script_lease(db, monkeypatch, heartbeat_on=True)
    assert len(seen) >= 12                                   # B tentou durante toda a execução (>2,5 leases)
    assert set(seen) == {StageClaimResult.BUSY}
    assert step.result in (WorkerStepResult.COMPLETED, WorkerStepResult.COMPLETED_PAUSED)
    assert slow.calls == 1
    state, attempt, *_ = stage_row(conn, run_id, SCRIPT)
    assert (state, attempt) == ("SUCCEEDED", 1)


def test_negative_control_without_heartbeat_the_second_worker_takes_over(db, monkeypatch):
    repo, conn, _ = db
    _, _, step, seen = _contest_script_lease(db, monkeypatch, heartbeat_on=False)
    assert StageClaimResult.CLAIMED in seen                  # sem renovação o lease vence e B assume
    assert step.result is WorkerStepResult.LOST              # A percebe a perda e não conclui


# -- 2. takeover legítimo após a morte do dono; 3. sem ressurreição --------------------------------


def _first_claim(repo, run_id, owner="worker-a", lease=300):
    claim = repo.claim_stage(run_id, SCRIPT, owner, lease)
    assert claim.result is StageClaimResult.CLAIMED
    return claim.execution


def test_takeover_after_death_fences_the_old_owner(db):
    repo, conn, _ = db
    coordinator = coordinator_for(repo)
    run_id = coordinator.start(VIDEO, "takeover-1").run.run_id
    old = _first_claim(repo, run_id)
    assert repo.claim_stage(run_id, SCRIPT, "worker-b", 300).result is StageClaimResult.BUSY  # lease ainda vivo
    expire_lease(conn, run_id, SCRIPT)  # dono morreu sem `stop`: ninguém renova
    taken = repo.claim_stage(run_id, SCRIPT, "worker-b", 300)
    assert taken.result is StageClaimResult.CLAIMED
    assert taken.execution.fencing_token > old.fencing_token
    before = stage_row(conn, run_id, SCRIPT)

    late = repo.complete_stage(run_id, SCRIPT, "worker-a", old.fencing_token,
                               checkpoint=Checkpoint({"stage": "script", "from": "zombie"}, 1))
    assert late.result is StageTransitionResult.LOST
    assert repo.fail_stage(run_id, SCRIPT, "worker-a", old.fencing_token, "zumbi").result is StageTransitionResult.LOST
    assert stage_row(conn, run_id, SCRIPT) == before         # estado, checkpoint e tentativa intactos
    assert before[0] == "RUNNING" and before[1] == 2 and before[3] == "worker-b" and before[4] is None

    # controle: o dono atual, com o token atual, conclui (o LOST acima é mesmo do fencing)
    ok = repo.complete_stage(run_id, SCRIPT, "worker-b", taken.execution.fencing_token,
                             checkpoint=Checkpoint({"stage": "script"}, 2))
    assert ok.result is StageTransitionResult.APPLIED


def test_coordinator_step_of_a_dead_owner_reports_lost_and_writes_nothing(db):
    repo, conn, _ = db
    gate, entered = threading.Event(), threading.Event()

    def hold(ctx):
        entered.set()
        gate.wait(10)

    coordinator = coordinator_for(repo, lease_seconds=300, overrides={SCRIPT: CountingHandler(SCRIPT, hold=hold)})
    run_id = coordinator.start(VIDEO, "takeover-2").run.run_id
    results = {}
    thread = threading.Thread(target=lambda: results.setdefault("a", coordinator.step(run_id, owner="worker-a")))
    thread.start()
    assert entered.wait(10)
    # o lease do dono vivo-mas-morto vence (simula travamento/partição) e B assume
    expire_lease(conn, run_id, SCRIPT)
    taken = repo.claim_stage(run_id, SCRIPT, "worker-b", 300)
    assert taken.result is StageClaimResult.CLAIMED
    gate.set()
    thread.join(10)
    assert not thread.is_alive()
    assert results["a"].result in (WorkerStepResult.LOST, WorkerStepResult.NOTHING_READY)
    state, attempt, token, owner, checkpoint, _ = stage_row(conn, run_id, SCRIPT)
    assert (state, attempt, owner, checkpoint) == ("RUNNING", 2, "worker-b", None)
    assert token == taken.execution.fencing_token


def test_no_resurrection_expired_or_stale_owner_cannot_renew(db):
    repo, conn, _ = db
    coordinator = coordinator_for(repo)
    run_id = coordinator.start(VIDEO, "resurrect-1").run.run_id
    old = _first_claim(repo, run_id)
    assert repo.renew_lease(run_id, SCRIPT, "worker-a", old.fencing_token, 300) is LeaseResult.RENEWED  # controle
    expire_lease(conn, run_id, SCRIPT)
    # dono atual (token atual) com lease já vencido: LOST, e o lease não volta a valer
    assert repo.renew_lease(run_id, SCRIPT, "worker-a", old.fencing_token, 300) is LeaseResult.LOST
    assert repo.claim_stage(run_id, SCRIPT, "worker-b", 300).result is StageClaimResult.CLAIMED
    # dono antigo, token antigo, depois do takeover: LOST
    assert repo.renew_lease(run_id, SCRIPT, "worker-a", old.fencing_token, 300) is LeaseResult.LOST
    assert stage_row(conn, run_id, SCRIPT)[3] == "worker-b"


# -- 4. duas réplicas, um claim --------------------------------------------------------------------


def _two_replicas(db, *, defeat_claim_cas=False):
    repo, conn, connect = db
    release = threading.Event()
    done = []
    steps = {}

    def hold(ctx):  # só solta quando o primeiro `submit` (necessariamente o perdedor) terminou
        release.wait(10)

    counting = CountingHandler(SCRIPT, hold=hold)
    run_id = coordinator_for(repo).start(VIDEO, "replicas-1").run.run_id
    backdate(conn, run_id)
    barrier = threading.Barrier(2)
    errors = []

    def replica(name):
        runs = repo
        if defeat_claim_cas:
            runs = _NoCasRepo(PostgresProductionRunRepository(connect, COORDINATOR_DAG), connect)
        coordinator = ProductionCoordinator(runs, handlers=handlers({SCRIPT: counting}),
                                            lease_seconds=300)
        worker = ProductionWorker(coordinator, owner=name)

        def submit(rid):
            try:
                steps[name] = worker.work(rid)
            except Exception as exc:  # `_enqueue` engoliria: o teste precisa ver
                errors.append(exc)
                raise
            finally:
                done.append(name)
                release.set()

        service = Production(coordinator=coordinator, worker=worker, submit=submit, in_flight=runs)
        active = ActiveRuns()  # um por réplica: a exclusão local não pode ser o que protege
        try:
            service = Production(coordinator=coordinator, worker=worker, submit=submit,
                                 in_flight=_ListThenWait(runs, barrier))
            service.recover_orphans(grace_seconds=30, active=active)
        except Exception as exc:  # pragma: no cover - reportado abaixo
            errors.append(exc)

    threads = [threading.Thread(target=replica, args=(name,)) for name in ("replica-a", "replica-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return run_id, counting, steps, errors


class _ListThenWait:
    """Garante que as duas réplicas já listaram o mesmo órfão antes de qualquer `submit`."""

    def __init__(self, inner, barrier):
        self._inner, self._barrier = inner, barrier

    def list_orphan_candidates(self, **kwargs):
        found = self._inner.list_orphan_candidates(**kwargs)
        self._barrier.wait(10)
        return found


class _NoCasRepo:
    """Controle negativo: claim sem exclusão (zera posse e estado antes de cada claim)."""

    _serialize = threading.Lock()  # reset+claim atômicos entre réplicas: o resultado fica determinístico

    def __init__(self, inner, connect):
        self._inner, self._connect = inner, connect

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def claim_stage(self, run_id, stage, owner, lease_seconds):
        with self._serialize:
            with self._connect() as conn:
                conn.execute("UPDATE studio.stage_executions SET state = 'PENDING', lease_owner = NULL, "
                             "lease_expires_at = NULL WHERE run_id = %s AND stage_id = %s AND state = 'RUNNING'",
                             (run_id, stage.value))
            return self._inner.claim_stage(run_id, stage, owner, lease_seconds)


def test_two_replicas_recovering_the_same_orphan_run_the_stage_once(db):
    repo, conn, _ = db
    run_id, counting, steps, errors = _two_replicas(db)
    assert errors == []
    assert counting.calls == 1
    results = sorted(step.result.value for walk in steps.values() for step in walk)
    assert WorkerStepResult.NOTHING_READY.value in results   # o perdedor viu BUSY (devolvido como NOTHING_READY)
    assert stage_row(conn, run_id, SCRIPT)[:2] == ("SUCCEEDED", 1)


def test_negative_control_without_claim_cas_both_replicas_run_the_stage(db):
    _, counting, steps, errors = _two_replicas(db, defeat_claim_cas=True)
    assert errors == [] and counting.calls == 2


# -- 5. recuperação após efeito concluído ----------------------------------------------------------


class _UploaderMustNotRun:
    def __init__(self):
        self.calls = 0

    def execute(self, *, video_id):
        self.calls += 1
        raise AssertionError("o uploader não pode ser chamado: a publicação já está confirmada")


def _orphan_publish_run(db):
    repo, conn, connect = db
    coordinator = coordinator_for(repo)
    run_id = coordinator.start(VIDEO, "publish-1").run.run_id
    conn.execute("UPDATE studio.production_runs SET state = 'RUNNING' WHERE run_id = %s", (run_id,))
    conn.execute("UPDATE studio.stage_executions SET state = 'SUCCEEDED' WHERE run_id = %s AND stage_id <> 'publish'",
                 (run_id,))
    conn.execute("UPDATE studio.stage_executions SET state = 'RUNNING', attempt = 1, fencing_token = 1, "
                 "lease_owner = 'dead-worker', lease_expires_at = statement_timestamp() - interval '1 minute' "
                 "WHERE run_id = %s AND stage_id = 'publish'", (run_id,))
    conn.execute("INSERT INTO studio.publications(id, video_id, youtube_video_id, status) "
                 "VALUES (%s, %s, 'oNQ2KN37sfQ', 'UPLOADED')", ("e" * 32, VIDEO))
    conn.commit()
    backdate(conn, run_id)
    return run_id


def _recover_publish(db, *, with_reconcile_first):
    repo, conn, connect = db
    run_id = _orphan_publish_run(db)
    uploader = _UploaderMustNotRun()
    pubs = PostgresPublicationRepository(connect) if with_reconcile_first else None
    publish = PublishHandler(uploader, pubs=pubs)
    coordinator = coordinator_for(repo, overrides={ProductionStage.PUBLISH: publish})
    worker = ProductionWorker(coordinator, owner="replica-r")
    service = Production(coordinator=coordinator, worker=worker, submit=lambda rid: worker.work(rid), in_flight=repo)
    recovered = service.recover_orphans(grace_seconds=30)
    return run_id, recovered, uploader


def test_recovery_completes_a_published_stage_without_calling_the_uploader(db):
    repo, conn, _ = db
    run_id, recovered, uploader = _recover_publish(db, with_reconcile_first=True)
    assert recovered == (run_id,)
    assert uploader.calls == 0
    state, attempt, _, owner, checkpoint, _ = stage_row(conn, run_id, ProductionStage.PUBLISH)
    assert state == "SUCCEEDED" and owner is None
    assert checkpoint["youtube_video_id"] == "oNQ2KN37sfQ" and checkpoint["publication_id"] == "e" * 32


def test_negative_control_without_reconcile_first_the_uploader_would_run(db):
    _, _, uploader = _recover_publish(db, with_reconcile_first=False)
    assert uploader.calls == 1


# -- 6. estados terminais/pausados preservados -----------------------------------------------------


def test_recover_orphans_never_redispatches_non_orphan_states(db):
    repo, conn, _ = db
    coordinator = coordinator_for(repo)
    expected = {}
    cases = [("CANCELLED", False), ("FAILED", False), ("SUCCEEDED", False), ("PAUSED", False),
             ("WAITING_HUMAN", False), ("RUNNING", True), ("CREATED", True)]
    for number, (state, orphan) in enumerate(cases, start=1):
        video = add_video(conn, number)
        run_id = coordinator.start(video, f"state-{state.lower()}").run.run_id
        conn.execute("UPDATE studio.production_runs SET state = %s, reason = %s WHERE run_id = %s",
                     (state, "motivo" if state in ("FAILED", "CANCELLED", "WAITING_HUMAN") else None, run_id))
        conn.execute("UPDATE studio.stage_executions SET state = 'RUNNING', lease_owner = 'dead-worker', "
                     "lease_expires_at = statement_timestamp() - interval '1 hour' "
                     "WHERE run_id = %s AND stage_id = 'script'", (run_id,))
        conn.commit()
        backdate(conn, run_id)
        expected[run_id] = (state, orphan)
    submitted = []
    service = Production(coordinator=coordinator, worker=ProductionWorker(coordinator),
                         submit=submitted.append, in_flight=repo)
    recovered = service.recover_orphans(grace_seconds=30)
    assert set(recovered) == set(submitted) == {rid for rid, (_, orphan) in expected.items() if orphan}
    assert {expected[rid][0] for rid in recovered} == {"RUNNING", "CREATED"}  # o filtro não é vazio por acidente


# -- 7. falha de submit e de banco -----------------------------------------------------------------


def test_submit_failure_does_not_block_other_orphans(db):
    repo, conn, _ = db
    coordinator = coordinator_for(repo)
    run_ids = []
    for number in (1, 2, 3):
        run_ids.append(coordinator.start(add_video(conn, number), f"submit-{number}").run.run_id)
        backdate(conn, run_ids[-1])
    submitted = []

    def submit(run_id):
        submitted.append(run_id)
        if run_id == run_ids[0]:
            raise RuntimeError("fila indisponível")

    service = Production(coordinator=coordinator, worker=ProductionWorker(coordinator), submit=submit, in_flight=repo)
    recovered = service.recover_orphans(grace_seconds=30)
    assert set(recovered) == set(submitted) == set(run_ids)  # o que levantou não impediu os demais


def test_reader_failure_propagates_and_the_loop_survives_the_next_round(monkeypatch):
    os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
    os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
    from app.main import _recovery_loop

    class BrokenReader:
        def list_orphan_candidates(self, **_):
            raise RuntimeError("banco caiu")

    service = Production(coordinator=SimpleNamespace(), worker=SimpleNamespace(), submit=lambda _r: None,
                         in_flight=BrokenReader())
    with pytest.raises(RuntimeError, match="banco caiu"):
        service.recover_orphans()

    calls = []

    class Studio:
        def recover_orphans(self):
            calls.append(datetime.now(timezone.utc))
            if len(calls) == 1:
                service.recover_orphans()  # a leitura do banco levanta de verdade na primeira rodada
            return ()

    async def drive():
        task = asyncio.create_task(_recovery_loop(Studio(), 0.01))
        for _ in range(300):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(drive())
    assert len(calls) >= 3  # a rodada que levantou não matou o laço
