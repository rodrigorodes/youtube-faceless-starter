"""Testes de Integração e Estabilização — Onda INT-04 / REC-01 (Caminho Financeiro Canônico e Coordenador Real).

Substitui o adaptador inseguro PostgresOperationStore pelo caminho transacional canônico:
- PaidOperationGuard + PostgresPaidOperationRepository (advisory lock 726002, CAS, escopo por projeto/vídeo)
- ProductionCoordinator + LeaseHeartbeat (timeout cooperativo e fencing real)
"""
from __future__ import annotations

import os
import threading
import time
from decimal import Decimal

import pytest

from app.studio.adapters.postgres.budget_repo import PostgresPaidOperationRepository
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
from app.studio.application.budget import (
    CostConfirmation,
    OperationSettled,
    PaidOperationGuard,
    PaidOperationState,
)
from app.studio.application.production import (
    COORDINATOR_DAG,
    ProductionCoordinator,
    ProductionMode,
    StageContext,
    StageOutcome,
    WorkerStepResult,
)
from app.studio.domain.contracts import UsageEntry
from app.studio.domain.production_run import ProductionStage
from app.studio.domain.resilience import (
    compute_deterministic_idempotency_key,
    compute_payload_hash,
)
from conftest import verified_test_connect


PROJECT_ID = "c" * 32
VIDEO_ID = "d" * 32


@pytest.fixture
def dsn():
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
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
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'canal')", (PROJECT_ID,))
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema valido', 'short')",
        (VIDEO_ID, PROJECT_ID),
    )
    conn.commit()
    connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    return conn, connect, PostgresPaidOperationRepository(connect)


def test_int_04_canonical_paid_operation_guard_persistence_and_anti_duplicate_charge(db_setup):
    """Caminho canônico PaidOperationGuard + PostgresPaidOperationRepository persiste estado e bloqueia dupla cobrança."""
    conn, _connect, repo = db_setup
    guard = PaidOperationGuard(
        repo,
        monthly_limit_usd=Decimal("10.00"),
        video_limit_usd=Decimal("2.00"),
    )
    payload_hash = compute_payload_hash({"scene_prompt": "Futuristic AI lab", "duration_s": 5.0})
    key = compute_deterministic_idempotency_key("tenant_01", VIDEO_ID, "render", payload_hash)

    submit_calls = 0

    def _call():
        nonlocal submit_calls
        submit_calls += 1
        guard.record_external_ref(key, "render_task_404")
        return {"ok": True}

    def _settle(_res):
        entry = UsageEntry(video_id=VIDEO_ID, step="render", provider="local", model="default", cost_usd=0.38)
        conf = CostConfirmation.actual(Decimal("0.38"), reference="render_task_404", confirmed_by="worker:int04")
        return entry, conf

    out = guard.run(key, VIDEO_ID, Decimal("0.40"), _call, _settle)
    assert out == {"ok": True}
    assert submit_calls == 1
    assert repo.state(key) is PaidOperationState.CONFIRMED
    assert repo.external_reference_id(key) == "render_task_404"

    with pytest.raises(OperationSettled):
        guard.run(key, VIDEO_ID, Decimal("0.40"), _call, _settle)

    assert submit_calls == 1
    ledger_count = conn.execute("SELECT COUNT(*) FROM studio.usage_ledger").fetchone()[0]
    assert ledger_count == 1


def test_int_04_production_coordinator_enforces_real_cooperative_timeout(db_setup):
    """ProductionCoordinator impõe timeout cooperativo real sobre handler lento e marca etapa como FAILED."""
    _conn, connect, repo = db_setup
    runs_repo = PostgresProductionRunRepository(connect, dag=COORDINATOR_DAG)

    class _SlowHandler:
        available = True
        reason = "ok"

        def __init__(self, stage: ProductionStage) -> None:
            self.stage = stage

        def execute(self, ctx: StageContext) -> StageOutcome:
            if self.stage is ProductionStage.SCRIPT:
                for _ in range(40):
                    ctx.ensure_active()
                    time.sleep(0.02)
            return StageOutcome()

    handlers = {stage: _SlowHandler(stage) for stage in ProductionStage}
    coordinator = ProductionCoordinator(
        runs_repo,
        handlers=handlers,
        mode=ProductionMode.INTERACTIVE,
        paid_ops=repo,
        stage_timeouts={ProductionStage.SCRIPT: 0.08},
    )
    created = coordinator.start(
        VIDEO_ID,
        idempotency_key="int04-timeout-run",
        channel_id=None,
        stages=(ProductionStage.SCRIPT,),
    )
    step = coordinator.step(created.run.run_id, owner="worker-timeout")
    assert step.result is WorkerStepResult.FAILED
    assert "exceeded timeout" in step.detail
