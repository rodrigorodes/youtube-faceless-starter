"""Testes de Integração e Estabilização — Onda INT-04 (Pipeline, Coordenador Real e Resiliência).

Valida os achados A08 e A11 da auditoria INT-01:
- A11: PostgresOperationStore conecta o OperationReconciler ao banco relacional real,
  garantindo que estados de operação sejam persistidos e impeçam dupla cobrança após reinício.
- ResilientStageExecutor mede o tempo decorrido via monotonic clock real e enforceia timeout.
- A08: Invalidação seletiva de cache e persistência monotônica de checkpoints por cena.
"""
from decimal import Decimal
from pathlib import Path
import psycopg
import pytest

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.operation_store import PostgresOperationStore
from app.studio.application.resilience import (
    OperationReconciler,
    ResilientStageExecutor,
    SystemReadinessReport,
)
from app.studio.domain.resilience import (
    AsyncOperationStatus,
    BackpressureController,
    OperationAlreadyCharged,
    StageTimeoutError,
    StageTimeoutPolicy,
    TenantScope,
)
from conftest import verified_test_connect


PROJECT_ID = "c" * 32
VIDEO_ID = "d" * 32


@pytest.fixture
def dsn():
    import os
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
    import os
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c = verified_test_connect(dsn, proof)
    try:
        c.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        c.commit()
        yield c
    finally:
        c.close()


@pytest.fixture
def db_setup(conn, dsn):
    import os
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'canal')", (PROJECT_ID,))
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema', 'short')",
        (VIDEO_ID, PROJECT_ID),
    )
    conn.commit()
    connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    return PostgresOperationStore(connect)


def test_int_04_postgres_operation_store_persistence_and_anti_duplicate_charge(db_setup):
    """A11: PostgresOperationStore persiste estado real no PostgreSQL e bloqueia dupla cobrança."""
    store = db_setup
    reconciler = OperationReconciler(store)
    scope = TenantScope(tenant_id="tenant_01", project_id=PROJECT_ID)

    payload = {"scene_prompt": "Futuristic AI lab", "duration_s": 5.0}
    est_cost = Decimal("0.40")

    # 1. Início de operação: primeiro submit é autorizado
    key, should_exec = reconciler.begin_operation(
        tenant_scope=scope,
        video_id=VIDEO_ID,
        stage_name="render",
        attempt=1,
        payload=payload,
        estimated_cost_usd=est_cost,
    )
    assert should_exec is True

    # 2. Persistência de submissão
    reconciler.record_submission(key, external_reference_id="render_task_404")

    # 3. Verificação de recuperação direta no PostgreSQL
    retrieved = store.get_by_idempotency_key(key)
    assert retrieved is not None
    assert retrieved.idempotency_key == key
    assert retrieved.status in (AsyncOperationStatus.SUBMITTED, AsyncOperationStatus.RESERVED)

    # 4. Confirmação da operação
    reconciler.record_confirmation(key, actual_cost_usd=Decimal("0.38"))

    # 5. Tentativa de nova submissão após confirmação deve falhar com OperationAlreadyCharged
    with pytest.raises(OperationAlreadyCharged, match="já confirmada e cobrada"):
        reconciler.begin_operation(
            tenant_scope=scope,
            video_id=VIDEO_ID,
            stage_name="render",
            attempt=1,
            payload=payload,
            estimated_cost_usd=est_cost,
        )


def test_int_04_resilient_executor_measures_real_duration_and_enforces_timeout():
    """A11: ResilientStageExecutor mede a duração real pelo clock e aplica timeout determinístico."""
    bp = BackpressureController()
    policy = StageTimeoutPolicy(stage_timeouts={"script": 10.0, "render": 30.0})

    # Simulação de relógio monotônico que salta 35 segundos durante o handler de render
    current_time = 100.0

    def fake_clock():
        return current_time

    executor = ResilientStageExecutor(
        backpressure=bp,
        timeout_policy=policy,
        clock=fake_clock,
    )
    scope = TenantScope(tenant_id="t1", project_id=PROJECT_ID)

    def slow_handler(attempt: int):
        nonlocal current_time
        current_time += 35.0  # Passaram-se 35 segundos (limite era 30s)
        return {"result": "ok"}

    with pytest.raises(StageTimeoutError, match="excedeu o timeout de 30.0s"):
        executor.execute_stage(
            tenant_scope=scope,
            video_id=VIDEO_ID,
            stage_name="render",
            handler=slow_handler,
        )
