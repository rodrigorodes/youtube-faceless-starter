"""Integração do repositório de execuções de produção (PostgreSQL descartável com prova privada).

Só roda quando `STUDIO_BUDGET_DISPOSABLE_DSN` e `STUDIO_BUDGET_TEST_PROOF_FILE` apontam para um
banco exclusivamente descartável; a fixture principal derruba o schema `studio`. Sem essas variáveis
os testes são ignorados — não há banco real nem credenciais aqui.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier

import psycopg
import pytest

from app.studio.adapters.postgres.db import migrate
from conftest import verified_test_connect, verify_disposable_connection

PROJECT, VIDEO, OTHER_VIDEO, CHANNEL = "a" * 32, "b" * 32, "c" * 32, "d" * 32
RUN, OTHER_RUN = "e" * 32, "f" * 32
OWNER, OTHER_OWNER = "worker-1", "worker-2"


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
        verify_disposable_connection(connection, proof)
        connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.close()


@pytest.fixture
def production_db(conn, dsn):
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository

    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'test')", (PROJECT,))
    for video in (VIDEO, OTHER_VIDEO):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                     (video, PROJECT))
    conn.execute("INSERT INTO studio.channel_profiles(id, project_id, name) VALUES (%s, %s, 'canal')",
                 (CHANNEL, PROJECT))
    conn.commit()
    repo = PostgresProductionRunRepository(lambda: verified_test_connect(dsn, proof))
    return repo, conn


def create(repo, run_id=RUN, key="run-1", video=VIDEO, **options):
    return repo.create_run(run_id, video, key, **options)


def claim(repo, stage, owner=OWNER, run_id=RUN, lease_seconds=300):
    from app.studio.domain.production_run import ProductionStage

    return repo.claim_stage(run_id, ProductionStage(stage) if isinstance(stage, str) else stage, owner, lease_seconds)


def complete(repo, stage, owner=OWNER, token=1, run_id=RUN, checkpoint=None):
    from app.studio.domain.production_run import ProductionStage

    return repo.complete_stage(run_id, ProductionStage(stage) if isinstance(stage, str) else stage, owner, token,
                               checkpoint=checkpoint)


def fail(repo, stage, owner=OWNER, token=1, run_id=RUN, error="boom", checkpoint=None):
    from app.studio.domain.production_run import ProductionStage

    return repo.fail_stage(run_id, ProductionStage(stage) if isinstance(stage, str) else stage, owner, token, error,
                           checkpoint=checkpoint)


def stage_row(conn, stage, run_id=RUN):
    return conn.execute(
        "SELECT state, attempt, fencing_token, lease_owner, lease_expires_at, checkpoint, checkpoint_version, error "
        "FROM studio.stage_executions WHERE run_id = %s AND stage_id = %s", (run_id, stage)).fetchone()


def run_row(conn, run_id=RUN):
    return conn.execute(
        "SELECT state, reason FROM studio.production_runs WHERE run_id = %s", (run_id,)).fetchone()


def event_types(conn):
    return [row[0] for row in conn.execute(
        "SELECT event_type FROM studio.production_outbox ORDER BY id").fetchall()]


def force_lease_expiry(conn, stage, run_id=RUN):
    conn.execute("UPDATE studio.stage_executions SET lease_expires_at = statement_timestamp() - interval '1 minute' "
                 "WHERE run_id = %s AND stage_id = %s", (run_id, stage))
    conn.commit()


def test_migration_creates_the_production_tables(conn):
    applied = migrate(conn)
    assert "0018_production_runs" in applied
    for table in ("production_runs", "stage_executions", "production_outbox"):
        assert conn.execute("SELECT to_regclass(%s)", (f"studio.{table}",)).fetchone()[0] is not None


def test_database_rejects_conflicting_idempotency_and_invalid_states(conn):
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p')", (PROJECT,))
    for video in (VIDEO, OTHER_VIDEO):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                     (video, PROJECT))
    insert = "INSERT INTO studio.production_runs(run_id, video_id, idempotency_key) VALUES (%s, %s, %s)"
    conn.execute(insert, (RUN, VIDEO, "key"))
    conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (OTHER_RUN, VIDEO, "key"))  # mesma chave: uma execução só
    conn.rollback()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (RUN, VIDEO, "other"))  # mesmo run_id: uma linha só
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.production_runs(run_id, video_id, idempotency_key, state) "
                     "VALUES (%s, %s, 'k2', 'NOPE')", (OTHER_RUN, VIDEO))
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.stage_executions(run_id, stage_id, state) VALUES (%s, 'research', 'RUNNING')",
                     (RUN,))  # RUNNING sem lease é inválido
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.stage_executions(run_id, stage_id, state, checkpoint, checkpoint_version) "
                     "VALUES (%s, 'research', 'PENDING', '{}'::jsonb, NULL)", (RUN,))
    conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.production_outbox(run_id, event_type, payload) "
                     "VALUES (%s, 'production.nope', '{}'::jsonb)", (RUN,))
    conn.rollback()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("INSERT INTO studio.production_runs(run_id, video_id, idempotency_key, channel_id) "
                     "VALUES (%s, %s, 'k3', %s)", (OTHER_RUN, VIDEO, "9" * 32))
    conn.rollback()


def test_create_run_persists_a_created_run_and_pending_stages(production_db):
    from app.studio.domain.production_run import CreateRunResult, ProductionStage, RunState, StageState

    repo, conn = production_db
    created = create(repo)
    assert created.result is CreateRunResult.CREATED
    assert created.run.state is RunState.CREATED
    assert (created.run.run_id, created.run.video_id, created.run.idempotency_key) == (RUN, VIDEO, "run-1")
    assert created.run.schema_version == 1
    states = conn.execute("SELECT stage_id, state FROM studio.stage_executions WHERE run_id = %s",
                          (RUN,)).fetchall()
    assert dict(states) == {stage.value: StageState.PENDING.value for stage in ProductionStage}
    assert event_types(conn) == ["production.run.created"]
    assert repo.get_run(RUN) == created.run


def test_replay_of_the_same_key_returns_the_existing_run_without_duplicates(production_db):
    from app.studio.domain.production_run import CreateRunResult

    repo, conn = production_db
    assert create(repo).result is CreateRunResult.CREATED
    replay = create(repo)
    assert replay.result is CreateRunResult.EXISTING
    assert replay.run.run_id == RUN
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM studio.stage_executions").fetchone()[0] == 9
    assert event_types(conn) == ["production.run.created"]


def test_replay_with_a_different_request_is_a_conflict(production_db):
    from app.studio.domain.production_run import ProductionIdempotencyConflict, ProductionStage

    repo, _ = production_db
    create(repo, channel_id=CHANNEL)
    for options in ({"video": OTHER_VIDEO}, {"channel_id": None}, {}):
        with pytest.raises(ProductionIdempotencyConflict):
            if options:
                create(repo, **options)
            else:
                create(repo, stages=[ProductionStage.RESEARCH])
    with pytest.raises(ProductionIdempotencyConflict):
        create(repo, run_id=OTHER_RUN)


def test_concurrent_replay_creates_exactly_one_run(production_db):
    from app.studio.domain.production_run import CreateRunResult

    repo, conn = production_db
    barrier = Barrier(2)

    def worker(_):
        barrier.wait()
        return create(repo).result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=30) for future in [pool.submit(worker, i) for i in range(2)]]
    assert sorted(result.value for result in results) == ["CREATED", "EXISTING"]
    assert results.count(CreateRunResult.CREATED) == 1
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1


def test_only_one_of_two_workers_claims_the_same_stage(production_db):
    repo, conn = production_db
    create(repo)
    barrier = Barrier(2)

    def worker(index):
        barrier.wait()
        return claim(repo, "research", owner=f"worker-{index}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=30) for future in [pool.submit(worker, i) for i in range(2)]]
    assert sorted(result.result.value for result in results) == ["BUSY", "CLAIMED"]
    state, attempt, token, owner, _, _, _, _ = stage_row(conn, "research")
    assert (state, attempt, token) == ("RUNNING", 1, 1)
    assert owner in ("worker-0", "worker-1")
    assert conn.execute("SELECT count(*) FROM studio.production_outbox "
                        "WHERE event_type = 'production.stage.claimed'").fetchone()[0] == 1
    assert run_row(conn)[0] == "RUNNING"


def test_dependencies_block_a_claim_without_starting_the_run(production_db):
    from app.studio.domain.production_run import (ProductionStage, RunState, StageClaimResult, StageTransitionResult)

    repo, conn = production_db
    create(repo)
    blocked = claim(repo, ProductionStage.SCRIPT)
    assert blocked.result is StageClaimResult.DEPENDENCIES_PENDING
    assert run_row(conn)[0] == "CREATED"  # a recusa não move o run
    assert stage_row(conn, "script")[0] == "PENDING"

    claimed = claim(repo, ProductionStage.RESEARCH)
    assert claimed.result is StageClaimResult.CLAIMED
    assert claimed.execution is not None and claimed.execution.fencing_token == 1
    assert run_row(conn)[0] == "RUNNING"
    assert event_types(conn) == ["production.run.created", "production.run.state_changed",
                                 "production.stage.claimed"]

    assert complete(repo, ProductionStage.RESEARCH).result is StageTransitionResult.APPLIED
    assert stage_row(conn, "research")[0] == "SUCCEEDED"
    assert stage_row(conn, "research")[4] is None  # lease liberado ao concluir
    assert claim(repo, ProductionStage.SCRIPT).result is StageClaimResult.CLAIMED
    assert claim(repo, ProductionStage.RESEARCH).result is StageClaimResult.STAGE_TERMINAL


def test_expired_lease_allows_takeover_and_fences_the_old_owner(production_db):
    from app.studio.domain.production_run import (LeaseResult, ProductionStage, StageClaimResult,
                                                  StageTransitionResult)

    repo, conn = production_db
    create(repo)
    first = claim(repo, ProductionStage.RESEARCH, owner=OWNER, lease_seconds=300)
    assert first.result is StageClaimResult.CLAIMED
    assert claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER).result is StageClaimResult.BUSY

    force_lease_expiry(conn, "research")
    takeover = claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER)
    assert takeover.result is StageClaimResult.CLAIMED
    assert takeover.execution is not None
    assert (takeover.execution.attempt, takeover.execution.fencing_token) == (2, 2)
    assert takeover.execution.lease_owner == OTHER_OWNER

    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OWNER, 1, 300) is LeaseResult.LOST
    assert complete(repo, ProductionStage.RESEARCH, owner=OWNER, token=1).result is StageTransitionResult.LOST
    assert fail(repo, ProductionStage.RESEARCH, owner=OWNER, token=1).result is StageTransitionResult.LOST
    assert stage_row(conn, "research")[0] == "RUNNING"  # o dono antigo não escreveu nada

    applied = complete(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER, token=2)
    assert applied.result is StageTransitionResult.APPLIED
    assert stage_row(conn, "research")[0] == "SUCCEEDED"


def test_renew_lease_extends_only_the_current_holder(production_db):
    from app.studio.domain.production_run import LeaseResult, ProductionStage

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH, lease_seconds=300)
    before = stage_row(conn, "research")[4]
    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OWNER, 1, 900) is LeaseResult.RENEWED
    assert stage_row(conn, "research")[4] > before
    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OWNER, 2, 900) is LeaseResult.LOST
    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OTHER_OWNER, 1, 900) is LeaseResult.LOST
    assert repo.renew_lease(OTHER_RUN, ProductionStage.RESEARCH, OWNER, 1, 900) is LeaseResult.UNKNOWN

    force_lease_expiry(conn, "research")
    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OWNER, 1, 900) is LeaseResult.LOST


def test_stale_owner_cannot_complete_or_fail_with_an_old_token(production_db):
    from app.studio.domain.production_run import (ProductionStage, StageTransitionResult)

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    assert complete(repo, ProductionStage.RESEARCH, token=2).result is StageTransitionResult.LOST
    assert fail(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER, token=1).result is StageTransitionResult.LOST
    assert stage_row(conn, "research")[0] == "RUNNING"
    assert stage_row(conn, "research")[1] == 1
    assert event_types(conn).count("production.stage.completed") == 0
    assert event_types(conn).count("production.stage.failed") == 0
    assert complete(repo, ProductionStage.RESEARCH).result is StageTransitionResult.APPLIED
    assert stage_row(conn, "research")[0] == "SUCCEEDED"
    assert complete(repo, ProductionStage.RESEARCH).result is StageTransitionResult.NOT_RUNNING


def test_pausing_a_run_releases_the_worker_and_resume_reclaims_the_stage(production_db):
    from app.studio.domain.production_run import (LeaseResult, ProductionStage, RunState, RunTransitionResult,
                                                  StageClaimResult, StageState, StageTransitionResult)

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)

    paused = repo.pause_run(RUN, "aprovação humana do roteiro")
    assert paused.result is RunTransitionResult.APPLIED
    assert paused.run is not None and paused.run.state is RunState.WAITING_HUMAN
    assert run_row(conn) == ("WAITING_HUMAN", "aprovação humana do roteiro")
    state, _, _, lease_owner, lease_expires_at, _, _, _ = stage_row(conn, "research")
    assert state == StageState.WAITING_HUMAN.value  # sem lease: nenhum worker fica ocupado
    assert (lease_owner, lease_expires_at) == (None, None)

    assert claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER).result is StageClaimResult.RUN_NOT_ACTIVE
    assert repo.renew_lease(RUN, ProductionStage.RESEARCH, OWNER, 1, 300) is LeaseResult.LOST
    assert complete(repo, ProductionStage.RESEARCH).result is StageTransitionResult.NOT_RUNNING
    assert repo.pause_run(RUN, "de novo").result is RunTransitionResult.NOT_ALLOWED

    resumed = repo.resume_run(RUN, RunState.WAITING_HUMAN)
    assert resumed.result is RunTransitionResult.APPLIED
    assert resumed.run is not None and resumed.run.state is RunState.RUNNING
    assert stage_row(conn, "research")[0] == "PENDING"
    reclaimed = claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER)
    assert reclaimed.result is StageClaimResult.CLAIMED
    assert reclaimed.execution is not None and reclaimed.execution.attempt == 2


def test_pause_from_created_is_allowed_and_resume_from_created_is_not(production_db):
    from app.studio.domain.production_run import RunState, RunTransitionResult

    repo, _ = production_db
    create(repo)
    assert repo.resume_run(RUN, RunState.CREATED).result is RunTransitionResult.NOT_ALLOWED
    assert repo.pause_run(RUN, "aguardando aprovação").result is RunTransitionResult.APPLIED
    assert repo.resume_run(RUN, RunState.WAITING_HUMAN).result is RunTransitionResult.APPLIED


def test_cancel_terminates_the_run_and_its_open_stages(production_db):
    from app.studio.domain.production_run import (ProductionStage, RunState, RunTransitionResult,
                                                  StageClaimResult, StageState)

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    cancelled = repo.cancel_run(RUN, "operador cancelou")
    assert cancelled.result is RunTransitionResult.APPLIED
    assert cancelled.run is not None and cancelled.run.state.value == "CANCELLED"
    assert run_row(conn) == ("CANCELLED", "operador cancelou")
    state, _, _, lease_owner, lease_expires_at, _, _, _ = stage_row(conn, "research")
    assert state == StageState.CANCELLED.value and (lease_owner, lease_expires_at) == (None, None)
    assert claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER).result is StageClaimResult.RUN_NOT_ACTIVE
    assert repo.resume_run(RUN, RunState.CANCELLED).result is RunTransitionResult.NOT_ALLOWED
    assert repo.cancel_run(RUN, "de novo").result is RunTransitionResult.NOT_ALLOWED


def test_failed_stage_persists_a_checkpoint_and_resume_retries_it(production_db):
    from app.studio.domain.production_run import (Checkpoint, ProductionStage, RunState, RunTransitionResult,
                                                  StageClaimResult, StageTransitionResult)

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    failed = fail(repo, ProductionStage.RESEARCH, token=1,
                  error="provedor caiu", checkpoint=Checkpoint({"cursor": 3}, 1))
    assert failed.result is StageTransitionResult.APPLIED
    state, _, _, lease_owner, _, checkpoint, version, error = stage_row(conn, "research")
    assert state == "FAILED" and lease_owner is None
    assert (checkpoint, version, error) == ({"cursor": 3}, 1, "provedor caiu")
    assert run_row(conn)[0] == "FAILED" and "research" in run_row(conn)[1]
    assert claim(repo, ProductionStage.RESEARCH).result is StageClaimResult.RUN_NOT_ACTIVE

    assert repo.resume_run(RUN, RunState.FAILED).result is RunTransitionResult.APPLIED
    assert run_row(conn)[0] == "RUNNING"
    assert stage_row(conn, "research")[0] == "FAILED"
    retried = claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER)
    assert retried.result is StageClaimResult.CLAIMED
    assert retried.execution is not None and retried.execution.attempt == 2
    assert retried.execution.checkpoint == Checkpoint({"cursor": 3}, 1)  # checkpoint sobrevive ao retry

    rejected = complete(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER, token=2,
                        checkpoint=Checkpoint({"result": "x"}, 1))
    assert rejected.result is StageTransitionResult.CHECKPOINT_REJECTED
    assert stage_row(conn, "research")[0] == "RUNNING"
    applied = complete(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER, token=2,
                       checkpoint=Checkpoint({"result": "x"}, 2))
    assert applied.result is StageTransitionResult.APPLIED
    assert stage_row(conn, "research")[5] == {"result": "x"}


def test_completing_without_a_checkpoint_keeps_the_previous_one(production_db):
    from app.studio.domain.production_run import Checkpoint, ProductionStage, RunState, StageTransitionResult

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    fail(repo, ProductionStage.RESEARCH, checkpoint=Checkpoint({"cursor": 1}, 1))
    repo.resume_run(RUN, RunState.FAILED)
    claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER)
    assert complete(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER, token=2).result is StageTransitionResult.APPLIED
    assert stage_row(conn, "research")[5] == {"cursor": 1}
    assert stage_row(conn, "research")[6] == 1


def test_the_outbox_write_and_the_state_change_are_one_transaction(production_db):
    from app.studio.domain.production_run import ProductionStage, StageTransitionResult

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    conn.execute("CREATE FUNCTION studio.reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
                 "$$ BEGIN RAISE EXCEPTION 'outbox unavailable'; END $$")
    conn.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON studio.production_outbox "
                 "FOR EACH ROW EXECUTE FUNCTION studio.reject_outbox()")
    conn.commit()
    with pytest.raises(psycopg.errors.RaiseException):
        complete(repo, ProductionStage.RESEARCH)
    assert stage_row(conn, "research")[0] == "RUNNING"  # a mudança de estado foi revertida
    assert event_types(conn).count("production.stage.completed") == 0
    conn.execute("DROP TRIGGER reject_outbox ON studio.production_outbox")
    conn.commit()
    assert complete(repo, ProductionStage.RESEARCH).result is StageTransitionResult.APPLIED
    assert event_types(conn).count("production.stage.completed") == 1


def test_run_succeeds_only_after_every_stage_completes_in_dependency_order(production_db):
    from app.studio.domain.production_run import STANDARD_DAG, RunState

    repo, conn = production_db
    create(repo)
    for stage in STANDARD_DAG.topological_order():
        claimed = claim(repo, stage)
        assert claimed.result.value == "CLAIMED", stage
        assert complete(repo, stage, token=claimed.execution.fencing_token).result.value == "APPLIED", stage
    assert run_row(conn)[0] == RunState.SUCCEEDED.value
    assert conn.execute("SELECT count(*) FROM studio.stage_executions WHERE state = 'SUCCEEDED'").fetchone()[0] == 9
    assert event_types(conn)[-1] == "production.run.state_changed"
    payload = conn.execute("SELECT payload FROM studio.production_outbox ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert payload["from"] == "RUNNING" and payload["to"] == "SUCCEEDED"


def test_read_outbox_peeks_and_ack_advances_the_cursor(production_db):
    from app.studio.domain.production_run import AckResult, ProductionStage

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    complete(repo, ProductionStage.RESEARCH)
    events = repo.read_outbox()
    assert [event.event_type.value for event in events] == [
        "production.run.created", "production.run.state_changed",
        "production.stage.claimed", "production.stage.completed"]
    assert [event.id for event in events] == sorted(event.id for event in events)
    assert all(event.event_version == 1 for event in events)
    assert repo.read_outbox(limit=2) == events[:2]
    assert repo.read_outbox(run_id=OTHER_RUN) == []

    first = events[0]
    assert repo.ack_outbox(first.id) is AckResult.ACKED
    assert repo.ack_outbox(first.id) is AckResult.ALREADY_ACKED
    assert repo.ack_outbox(999999) is AckResult.UNKNOWN
    remaining = repo.read_outbox()
    assert [event.id for event in remaining] == [event.id for event in events[1:]]
    with pytest.raises(ValueError):
        repo.read_outbox(0)
    with pytest.raises(ValueError):
        repo.read_outbox(1001)


def test_get_run_and_invalid_arguments(production_db):
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
    from app.studio.domain.ids import InvalidId
    from app.studio.domain.production_run import (ProductionStage, StageDag, StageNotInDag)

    repo, _ = production_db
    assert repo.get_run(RUN) is None
    with pytest.raises(InvalidId):
        repo.get_run("nope")
    create(repo)
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            repo.claim_stage(RUN, ProductionStage.RESEARCH, bad, 60)  # type: ignore[arg-type]
    for bad in (0, 1.5, True):
        with pytest.raises(ValueError):
            repo.claim_stage(RUN, ProductionStage.RESEARCH, OWNER, bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repo.claim_stage(RUN, "unknown", OWNER, 60)  # type: ignore[arg-type]
    narrow = PostgresProductionRunRepository(
        lambda: pytest.fail("connection must not be opened"), dag=StageDag({ProductionStage.RESEARCH: ()}))
    with pytest.raises(StageNotInDag):
        narrow.claim_stage(RUN, ProductionStage.SCRIPT, OWNER, 60)
    with pytest.raises(ValueError):
        repo.pause_run(RUN, " ")
    with pytest.raises(ValueError):
        repo.cancel_run(RUN, "")
    with pytest.raises(ValueError):
        repo.complete_stage(RUN, ProductionStage.RESEARCH, OWNER, -1)


def test_a_subset_pipeline_completes_without_the_missing_stages(production_db):
    from app.studio.domain.production_run import CreateRunResult, ProductionStage, StageClaimResult

    repo, conn = production_db
    created = create(repo, stages=[ProductionStage.RESEARCH, ProductionStage.SCRIPT])
    assert created.result is CreateRunResult.CREATED
    assert conn.execute("SELECT count(*) FROM studio.stage_executions WHERE run_id = %s",
                        (RUN,)).fetchone()[0] == 2
    assert claim(repo, ProductionStage.RESEARCH).result is StageClaimResult.CLAIMED
    complete(repo, ProductionStage.RESEARCH)
    claimed = claim(repo, ProductionStage.SCRIPT)
    assert claimed.result is StageClaimResult.CLAIMED
    complete(repo, ProductionStage.SCRIPT, token=1)
    assert run_row(conn)[0] == "SUCCEEDED"
    assert claim(repo, ProductionStage.FACTCHECK).result is StageClaimResult.UNKNOWN


def test_repository_uses_the_injected_guarded_connection(production_db, monkeypatch, tmp_path):
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository

    _, conn = production_db
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", str(wrong))
    repo = PostgresProductionRunRepository(lambda: verified_test_connect(
        os.environ["STUDIO_BUDGET_DISPOSABLE_DSN"], os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]))
    with pytest.raises(ValueError, match="proof"):
        create(repo)
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0


# -- bordas da revisão: chave canônica, tradução de erros, leases e cobertura -------------------


def fanout_repository(dsn):
    """DAG com fan-out (research → script/factcheck) para exercitar escrita concorrente real."""
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
    from app.studio.domain.production_run import ProductionStage, StageDag

    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    dag = StageDag({
        ProductionStage.RESEARCH: (),
        ProductionStage.SCRIPT: (ProductionStage.RESEARCH,),
        ProductionStage.FACTCHECK: (ProductionStage.RESEARCH,),
    })
    return PostgresProductionRunRepository(lambda: verified_test_connect(dsn, proof), dag)


def test_idempotency_key_variants_do_not_create_extra_runs(production_db):
    from app.studio.domain.production_run import CreateRunResult, InvalidIdempotencyKey

    repo, conn = production_db
    assert create(repo, key="order-42").result is CreateRunResult.CREATED
    # Padrão do gate de QA: identidade exata, sem normalização silenciosa.
    for spelling in ("order-42 ", " order-42", "ORDER-42", "Order-42"):
        with pytest.raises(InvalidIdempotencyKey):
            create(repo, run_id=OTHER_RUN, key=spelling)
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1
    assert create(repo, key="order-42").result is CreateRunResult.EXISTING


def test_create_run_with_a_missing_video_or_channel_is_a_domain_error(production_db):
    from app.studio.domain.production_run import ProductionRunReferencedEntityNotFound

    repo, conn = production_db
    with pytest.raises(ProductionRunReferencedEntityNotFound):
        create(repo, video="9" * 32)
    with pytest.raises(ProductionRunReferencedEntityNotFound):
        create(repo, channel_id="8" * 32)
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0


def test_lock_contention_is_reported_separately_from_an_outage(production_db, dsn):
    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
    from app.studio.domain.production_run import ProductionRunLockTimeout, ProductionStage, StageClaimResult

    repo, conn = production_db
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    create(repo)

    def connect():
        connection = verified_test_connect(dsn, proof)
        connection.execute("SET lock_timeout = '200ms'")
        connection.commit()
        return connection

    limited = PostgresProductionRunRepository(connect)
    holder = verified_test_connect(dsn, proof)
    try:
        with holder.transaction():
            holder.execute("SELECT 1 FROM studio.production_runs WHERE run_id = %s FOR UPDATE", (RUN,))
            with pytest.raises(ProductionRunLockTimeout):
                limited.claim_stage(RUN, ProductionStage.RESEARCH, OWNER, 60)
            assert run_row(conn)[0] == "CREATED"  # contenção não escreveu nada
    finally:
        holder.close()
    assert claim(repo, ProductionStage.RESEARCH).result is StageClaimResult.CLAIMED


def test_fan_out_stages_run_concurrently_and_the_run_succeeds(production_db, dsn):
    from app.studio.domain.production_run import (RunState, RunTransitionResult, StageClaimResult,
                                                  StageTransitionResult)

    _, conn = production_db
    repo = fanout_repository(dsn)
    create(repo)
    assert claim(repo, "research").result is StageClaimResult.CLAIMED
    assert claim(repo, "script").result is StageClaimResult.DEPENDENCIES_PENDING
    assert complete(repo, "research").result is StageTransitionResult.APPLIED
    script = claim(repo, "script")
    factcheck = claim(repo, "factcheck", owner=OTHER_OWNER)
    assert script.result is StageClaimResult.CLAIMED and factcheck.result is StageClaimResult.CLAIMED
    assert script.execution.fencing_token == 1 and factcheck.execution.fencing_token == 1
    assert conn.execute("SELECT count(*) FROM studio.stage_executions WHERE state = 'RUNNING'").fetchone()[0] == 2
    assert complete(repo, "script").result is StageTransitionResult.APPLIED
    assert run_row(conn)[0] == RunState.RUNNING.value
    assert complete(repo, "factcheck", owner=OTHER_OWNER).result is StageTransitionResult.APPLIED
    assert run_row(conn)[0] == RunState.SUCCEEDED.value
    # fan-out também é retomável quando o run não mudou de estado
    assert repo.resume_run(RUN, RunState.WAITING_HUMAN).result is RunTransitionResult.NOT_ALLOWED


def test_resume_revokes_leases_so_the_previous_generation_cannot_write(production_db, dsn):
    from app.studio.domain.production_run import (ProductionStage, RunState, RunTransitionResult,
                                                  StageClaimResult, StageTransitionResult)

    _, conn = production_db
    repo = fanout_repository(dsn)
    create(repo)
    claim(repo, "research")
    complete(repo, "research")
    claim(repo, "script")
    claim(repo, "factcheck", owner=OTHER_OWNER)
    assert fail(repo, "script").result is StageTransitionResult.APPLIED
    assert run_row(conn)[0] == RunState.FAILED.value
    state, _, token, owner, expires, _, _, _ = stage_row(conn, "factcheck")
    assert (state, owner) == ("RUNNING", OTHER_OWNER) and expires is not None

    resumed = repo.resume_run(RUN, RunState.FAILED)
    assert resumed.result is RunTransitionResult.APPLIED
    state, _, next_token, next_owner, next_expires, _, _, _ = stage_row(conn, "factcheck")
    assert (state, next_owner, next_expires) == ("PENDING", None, None)
    assert next_token == token + 1  # geração anterior invalidada, mesmo sem novo claim

    stale = repo.complete_stage(RUN, ProductionStage.FACTCHECK, OTHER_OWNER, token)
    assert stale.result is StageTransitionResult.LOST
    assert stage_row(conn, "factcheck")[0] == "PENDING"
    reclaimed = claim(repo, "factcheck", owner=OTHER_OWNER)
    assert reclaimed.result is StageClaimResult.CLAIMED
    assert reclaimed.execution.fencing_token == next_token + 1


def test_resume_refuses_a_divergent_expected_state(production_db):
    from app.studio.domain.production_run import ProductionStage, RunState, RunTransitionResult

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    fail(repo, ProductionStage.RESEARCH)
    assert run_row(conn)[0] == "FAILED"
    events_before = conn.execute("SELECT count(*) FROM studio.production_outbox").fetchone()[0]
    assert repo.resume_run(RUN, RunState.WAITING_HUMAN).result is RunTransitionResult.NOT_ALLOWED
    assert repo.resume_run(RUN, RunState.CREATED).result is RunTransitionResult.NOT_ALLOWED
    assert run_row(conn)[0] == "FAILED"
    assert conn.execute("SELECT count(*) FROM studio.production_outbox").fetchone()[0] == events_before
    with pytest.raises(TypeError):
        repo.resume_run(RUN, "FAILED")  # type: ignore[arg-type]
    assert repo.resume_run(RUN, RunState.FAILED).result is RunTransitionResult.APPLIED


def test_lease_expiry_uses_the_database_clock(production_db):
    import time

    from app.studio.domain.production_run import ProductionStage, StageClaimResult

    repo, conn = production_db
    create(repo)
    assert claim(repo, ProductionStage.RESEARCH, lease_seconds=2).result is StageClaimResult.CLAIMED
    assert claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER).result is StageClaimResult.BUSY
    time.sleep(2.2)  # lease REAL de 2 s; quem decide a expiração é o relógio do banco
    expired_in_database = conn.execute(
        "SELECT lease_expires_at <= statement_timestamp() FROM studio.stage_executions "
        "WHERE run_id = %s AND stage_id = 'research'", (RUN,)).fetchone()[0]
    assert expired_in_database is True
    assert claim(repo, ProductionStage.RESEARCH, owner=OTHER_OWNER).result is StageClaimResult.CLAIMED


def test_adapter_never_reads_the_process_clock():
    from pathlib import Path

    import app.studio.adapters.postgres.production_repo as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("datetime.now", "utcnow", "time.time", "time.monotonic"):
        assert forbidden not in source


def test_outbox_failure_rolls_back_every_state_change(production_db):
    from app.studio.domain.production_run import ProductionStage, RunState, RunTransitionResult, StageClaimResult

    repo, conn = production_db
    create(repo)
    conn.execute("CREATE FUNCTION studio.reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
                 "$$ BEGIN RAISE EXCEPTION 'outbox unavailable'; END $$")
    conn.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON studio.production_outbox "
                 "FOR EACH ROW EXECUTE FUNCTION studio.reject_outbox()")
    conn.commit()

    def reject_only(event_type):
        conn.execute("CREATE OR REPLACE FUNCTION studio.reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
                     f"$$ BEGIN IF NEW.event_type = '{event_type}' THEN RAISE EXCEPTION 'outbox unavailable'; "
                     "END IF; RETURN NEW; END $$")
        conn.commit()

    # create: run + etapas + evento, tudo ou nada
    reject_only("production.run.created")
    with pytest.raises(psycopg.errors.RaiseException):
        create(repo, run_id=OTHER_RUN, key="run-2")
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM studio.stage_executions WHERE run_id = %s",
                        (OTHER_RUN,)).fetchone()[0] == 0

    # claim: o run não pode virar RUNNING sem o evento da etapa
    reject_only("production.stage.claimed")
    with pytest.raises(psycopg.errors.RaiseException):
        claim(repo, ProductionStage.RESEARCH)
    assert run_row(conn)[0] == RunState.CREATED.value
    assert stage_row(conn, "research")[0] == "PENDING"

    # fail e complete: a etapa não muda sem o evento dela
    conn.execute("DROP TRIGGER reject_outbox ON studio.production_outbox")
    conn.commit()
    assert claim(repo, ProductionStage.RESEARCH).result is StageClaimResult.CLAIMED
    conn.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON studio.production_outbox "
                 "FOR EACH ROW EXECUTE FUNCTION studio.reject_outbox()")
    conn.commit()
    reject_only("production.stage.failed")
    with pytest.raises(psycopg.errors.RaiseException):
        fail(repo, "research")
    assert stage_row(conn, "research")[0] == "RUNNING"
    assert run_row(conn)[0] == RunState.RUNNING.value
    reject_only("production.stage.completed")
    with pytest.raises(psycopg.errors.RaiseException):
        complete(repo, "research")
    assert stage_row(conn, "research")[0] == "RUNNING"

    # pause e cancel: run e etapas não mudam sem o evento do run
    reject_only("production.run.state_changed")
    with pytest.raises(psycopg.errors.RaiseException):
        repo.pause_run(RUN, "pausa")
    assert run_row(conn)[0] == RunState.RUNNING.value
    with pytest.raises(psycopg.errors.RaiseException):
        repo.cancel_run(RUN, "cancelamento")
    assert run_row(conn)[0] == RunState.RUNNING.value
    state, _, _, owner, expires, _, _, _ = stage_row(conn, "research")
    assert state == "RUNNING" and owner == OWNER and expires is not None
    conn.execute("DROP TRIGGER reject_outbox ON studio.production_outbox")
    conn.commit()
    assert repo.pause_run(RUN, "pausa").result is RunTransitionResult.APPLIED


def test_schema_keeps_only_indexes_the_repository_uses(conn):
    migrate(conn)

    def indexes(table):
        return {row[0] for row in conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'studio' AND tablename = %s", (table,))}

    # Sem consulta por video_id nem varredura de lease: não há índice morto no schema.
    assert indexes("production_runs") == {"production_runs_pkey", "production_runs_idempotency_key_key"}
    assert indexes("stage_executions") == {"stage_executions_pkey"}
    # A outbox realmente consulta `acked_at IS NULL ORDER BY id`.
    assert indexes("production_outbox") == {"production_outbox_pkey", "production_outbox_unacked_idx"}


def test_postgres_adapter_matches_the_production_run_port(production_db):
    import inspect

    from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
    from app.studio.application.ports import ProductionRunRepository

    repo, _ = production_db

    def shape(function):
        return [(parameter.name, parameter.kind, parameter.default)
                for parameter in inspect.signature(function).parameters.values()]

    checked = 0
    for name in dir(ProductionRunRepository):
        if name.startswith("_"):
            continue
        member = getattr(ProductionRunRepository, name)
        if not inspect.isfunction(member):
            continue
        checked += 1
        assert isinstance(repo, PostgresProductionRunRepository)
        assert callable(getattr(repo, name)), name
        assert shape(getattr(PostgresProductionRunRepository, name)) == shape(member), name
    assert checked == 11

def test_database_enforces_the_canonical_idempotency_key(conn):
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'p')", (PROJECT,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                 (VIDEO, PROJECT))
    conn.commit()
    insert = "INSERT INTO studio.production_runs(run_id, video_id, idempotency_key) VALUES (%s, %s, %s)"
    # Defesa em profundidade: mesmo INSERT direto não consegue gravar chave não canônica.
    for index, bad in enumerate(("ORDER-99", "café-42", "cafe\u0301-42", "order-\uFE0F-42",
                                 "ｏｒｄｅｒ-42", "order\u201342", "оrder-42", "order 42")):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(insert, (f"{index + 1:032x}", VIDEO, bad))
        conn.rollback()
    conn.execute(insert, (RUN, VIDEO, "order-42"))
    conn.commit()
    assert conn.execute("SELECT idempotency_key FROM studio.production_runs").fetchone()[0] == "order-42"


def test_unicode_key_variants_are_rejected_without_creating_runs(production_db):
    from app.studio.domain.production_run import CreateRunResult, InvalidIdempotencyKey

    repo, conn = production_db
    for index, spelling in enumerate(("café-42", "cafe\u0301-42", "order-\uFE0F-42", "order\u201342")):
        with pytest.raises(InvalidIdempotencyKey):
            create(repo, run_id=f"{index + 1:032x}", key=spelling)
    assert conn.execute("SELECT count(*) FROM studio.production_runs").fetchone()[0] == 0
    assert create(repo, key="cafe-42").result is CreateRunResult.CREATED


def test_resume_emits_a_revoked_event_for_each_open_stage(production_db, dsn):
    from app.studio.domain.production_run import RunState, RunTransitionResult

    _, conn = production_db
    repo = fanout_repository(dsn)
    create(repo)
    claim(repo, "research")
    complete(repo, "research")
    claim(repo, "script")
    claim(repo, "factcheck", owner=OTHER_OWNER)
    fail(repo, "script")
    last_id = conn.execute("SELECT max(id) FROM studio.production_outbox").fetchone()[0]
    assert repo.resume_run(RUN, RunState.FAILED).result is RunTransitionResult.APPLIED
    events = conn.execute(
        "SELECT id, stage_id, payload FROM studio.production_outbox "
        "WHERE event_type = 'production.stage.revoked' ORDER BY id").fetchall()
    assert len(events) == 1
    event_id, stage_id, payload = events[0]
    assert event_id > last_id
    assert (stage_id, payload["from"], payload["to"], payload["fencing_token"], payload["attempt"]) == \
        ("factcheck", "RUNNING", "PENDING", 2, 1)
    run_event = conn.execute(
        "SELECT id FROM studio.production_outbox WHERE event_type = 'production.run.state_changed' "
        "ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert event_id < run_event  # revogação e mudança do run na mesma transação, nessa ordem


def test_pause_then_resume_reports_the_waited_stage_as_revoked(production_db):
    from app.studio.domain.production_run import ProductionStage, RunState, RunTransitionResult

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    assert repo.pause_run(RUN, "aguardando humano").result is RunTransitionResult.APPLIED
    assert repo.resume_run(RUN, RunState.WAITING_HUMAN).result is RunTransitionResult.APPLIED
    row = conn.execute("SELECT payload FROM studio.production_outbox "
                       "WHERE event_type = 'production.stage.revoked'").fetchone()
    assert row is not None
    payload = row[0]
    assert (payload["stage_id"], payload["from"], payload["to"], payload["fencing_token"]) == \
        ("research", "WAITING_HUMAN", "PENDING", 2)
    assert stage_row(conn, "research")[0] == "PENDING"


def test_resume_revocation_events_are_atomic(production_db):
    from app.studio.domain.production_run import ProductionStage, RunState, RunTransitionResult

    repo, conn = production_db
    create(repo)
    claim(repo, ProductionStage.RESEARCH)
    assert repo.pause_run(RUN, "aguardando humano").result is RunTransitionResult.APPLIED
    token_before = stage_row(conn, "research")[2]
    conn.execute("CREATE FUNCTION studio.reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
                 "$$ BEGIN IF NEW.event_type = 'production.stage.revoked' THEN "
                 "RAISE EXCEPTION 'outbox unavailable'; END IF; RETURN NEW; END $$")
    conn.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON studio.production_outbox "
                 "FOR EACH ROW EXECUTE FUNCTION studio.reject_outbox()")
    conn.commit()
    with pytest.raises(psycopg.errors.RaiseException):
        repo.resume_run(RUN, RunState.WAITING_HUMAN)
    assert run_row(conn)[0] == "WAITING_HUMAN"  # run e etapas voltaram juntos
    state, _, token_after, owner, expires, _, _, _ = stage_row(conn, "research")
    assert (state, owner, expires) == ("WAITING_HUMAN", None, None)
    assert token_after == token_before
    assert conn.execute("SELECT count(*) FROM studio.production_outbox "
                        "WHERE event_type = 'production.stage.revoked'").fetchone()[0] == 0
    conn.execute("DROP TRIGGER reject_outbox ON studio.production_outbox")
    conn.commit()
    assert repo.resume_run(RUN, RunState.WAITING_HUMAN).result is RunTransitionResult.APPLIED
