"""Suíte de Segurança Financeira e Resiliência — REC-01 (R01, R02, R03).

Executa contra PostgreSQL descartável real via `./scripts/test-container.sh`:
- REC-01.01: Eliminação de PostgresOperationStore, identidade real projeto/vídeo, teto $0.00.
- REC-01.02: Admissão transacional concorrente, CAS monotônico, chave lógica estável,
  external_reference_id durável após restart, settlement idempotente (1 linha no ledger),
  custo desconhecido nunca vira $0.00, falha pré vs pós-efeito.
- REC-01.03: Reconciliação pré-retry, timeout cooperativo, fencing pós-perda de lease no
  ProductionCoordinator canônico e kill switch de publicação.
"""
from __future__ import annotations

import importlib
import os
import threading
import time
from decimal import Decimal

import pytest

from app.studio.adapters.postgres.budget_repo import PostgresPaidOperationRepository
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
from app.studio.application.budget import (
    BeginResult,
    BudgetDenied,
    CostConfirmation,
    IdempotencyConflict,
    InvalidOperationTransition,
    OperationInProgress,
    OperationSettled,
    OperationUncertain,
    PaidOperationGuard,
    PaidOperationState,
    PreEffectFailure,
)
from app.studio.application.lease_heartbeat import LeaseLost
from app.studio.application.production import (
    COORDINATOR_DAG,
    ProductionCoordinator,
    ProductionMode,
    StageContext,
    StageOutcome,
    WorkerStepResult,
)
from app.studio.application.publication_execution import PublicationResult, RunPublication
from app.studio.domain.contracts import Publication, PublicationStatus, UsageEntry
from app.studio.domain.production_run import (
    ProductionStage,
    StageTransitionResult,
)
from app.studio.domain.resilience import (
    StageTimeoutError,
    compute_deterministic_idempotency_key,
    compute_payload_hash,
)
from conftest import verified_test_connect


PROJECT_A = "1" * 32
PROJECT_B = "2" * 32
VIDEO_A = "a" * 32
VIDEO_B = "b" * 32


@pytest.fixture
def dsn():
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def db(dsn):
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    conn = verified_test_connect(dsn, proof)
    try:
        conn.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        conn.commit()
        migrate(conn)
        conn.execute(
            "INSERT INTO studio.projects(id, name) VALUES (%s, 'Projeto A'), (%s, 'Projeto B')",
            (PROJECT_A, PROJECT_B),
        )
        conn.execute(
            "INSERT INTO studio.videos(id, project_id, topic, format) "
            "VALUES (%s, %s, 'Video Projeto A', 'short'), (%s, %s, 'Video Projeto B', 'short')",
            (VIDEO_A, PROJECT_A, VIDEO_B, PROJECT_B),
        )
        conn.commit()
        connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
        yield conn, connect
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REC-01.01 — Remoção do caminho inseguro & identidade/limites reais
# ---------------------------------------------------------------------------


def test_rec_01_01_unsafe_operation_store_and_parallel_executor_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.studio.adapters.postgres.operation_store")

    resilience = importlib.import_module("app.studio.application.resilience")
    for forbidden in ("OperationReconciler", "InMemoryOperationStore", "OperationStoreProtocol", "ResilientStageExecutor"):
        assert not hasattr(resilience, forbidden), f"{forbidden} ainda exposto em application.resilience"


def test_rec_01_01_project_video_isolation_and_zero_ceiling(db):
    conn, connect = db
    repo = PostgresPaidOperationRepository(connect)
    zero_guard = PaidOperationGuard(
        repo,
        monthly_limit_usd=Decimal("0.00"),
        video_limit_usd=Decimal("0.00"),
    )

    # Teto $0.00 bloqueia qualquer operação paga antes de chamar o provedor
    called = 0

    def _paid_call():
        nonlocal called
        called += 1
        return "should-not-run"

    with pytest.raises(BudgetDenied) as exc_info:
        zero_guard.run(
            "op-zero-block",
            VIDEO_B,
            Decimal("0.01"),
            _paid_call,
            lambda _r: (
                UsageEntry(video_id=VIDEO_B, step="render", provider="mock", model="m1", cost_usd=0.01),
                CostConfirmation.actual(Decimal("0.01"), reference="ref-1", confirmed_by="test"),
            ),
        )
    assert called == 0
    assert exc_info.value.detail is not None
    assert exc_info.value.detail.ceiling_usd == Decimal("0.00")
    assert conn.execute("SELECT COUNT(*) FROM studio.usage_ledger").fetchone()[0] == 0

    # Operação gratuita ($0.00) atribui exatamente a VIDEO_B / PROJECT_B (nunca VIDEO_A)
    zero_guard.run(
        "op-free-b",
        VIDEO_B,
        Decimal("0.00"),
        lambda: "ok-free",
        lambda _r: (
            UsageEntry(video_id=VIDEO_B, step="script", provider="local", model="ollama", cost_usd=0.0),
            CostConfirmation.free(reference="local:ollama", confirmed_by="test"),
        ),
    )
    row = conn.execute(
        "SELECT video_id, project_id, state, monthly_limit_usd, video_limit_usd "
        "FROM studio.paid_operations WHERE idempotency_key = 'op-free-b'"
    ).fetchone()
    assert row == (VIDEO_B, PROJECT_B, "CONFIRMED", Decimal("0.00"), Decimal("0.00"))

    # Vídeo inexistente falha fechado
    with pytest.raises(ValueError, match="unknown video"):
        zero_guard.reserve("op-missing-vid", "f" * 32, Decimal("0.00"))

    # Reuso de chave entre vídeos distintos falha com IdempotencyConflict
    with pytest.raises(IdempotencyConflict):
        zero_guard.reserve("op-free-b", VIDEO_A, Decimal("0.00"))


# ---------------------------------------------------------------------------
# REC-01.02 — Concorrência PG, CAS, ref externa durável, restart, 1 ledger
# ---------------------------------------------------------------------------


def test_rec_01_02_concurrent_connections_exclusive_admission_and_budget_race(db):
    _conn, connect = db
    barrier = threading.Barrier(2)
    results_same_key: list[BeginResult] = []
    errors: list[Exception] = []

    def _race_same_key():
        repo = PostgresPaidOperationRepository(connect)
        try:
            barrier.wait(timeout=5)
            res = repo.begin("concurrent-key-1", VIDEO_A, Decimal("0.50"), Decimal("5.00"), Decimal("2.00"))
            results_same_key.append(res)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=_race_same_key)
    t2 = threading.Thread(target=_race_same_key)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors
    assert sorted(r.value for r in results_same_key) == ["CREATED", "IN_PROGRESS"]

    # Competição pelo mesmo teto global ($1.00) entre dois vídeos distintos ($0.60 cada)
    barrier2 = threading.Barrier(2)
    results_budget: list[BeginResult] = []

    def _race_budget(key: str, video_id: str):
        repo = PostgresPaidOperationRepository(connect)
        barrier2.wait(timeout=5)
        res = repo.begin(
            key, video_id, Decimal("0.60"),
            monthly_limit_usd=Decimal("1.00"),
            video_limit_usd=Decimal("1.00"),
            global_monthly_limit_usd=Decimal("1.00"),
        )
        results_budget.append(res)

    # Primeiro libera concurrent-key-1 para não ocupar o teto global
    PostgresPaidOperationRepository(connect).release("concurrent-key-1", "cleanup before budget race")

    tb1 = threading.Thread(target=_race_budget, args=("race-a", VIDEO_A))
    tb2 = threading.Thread(target=_race_budget, args=("race-b", VIDEO_B))
    tb1.start()
    tb2.start()
    tb1.join(timeout=10)
    tb2.join(timeout=10)

    assert sorted(r.value for r in results_budget) == ["CREATED", "DENIED"]


def test_rec_01_02_durable_external_ref_restart_idempotent_confirm_and_stale_cas(db):
    conn, connect = db
    p_hash = compute_payload_hash({"prompt": "Doc", "duration": 8})
    logical_key = compute_deterministic_idempotency_key("tenant-1", VIDEO_A, "assets", p_hash)

    # Instância 1 antes de crash/restart: reserva e persiste external_reference_id
    repo1 = PostgresPaidOperationRepository(connect)
    guard1 = PaidOperationGuard(repo1, Decimal("10.00"), Decimal("5.00"))
    assert guard1.reserve(logical_key, VIDEO_A, Decimal("1.20")) is BeginResult.CREATED
    guard1.record_external_ref(logical_key, "provider-job-777")
    # Replay idempotente da mesma ref externa funciona; ref divergente falha
    guard1.record_external_ref(logical_key, "provider-job-777")
    with pytest.raises(IdempotencyConflict):
        guard1.record_external_ref(logical_key, "provider-job-999")

    # Simula restart completo: nova instância de repositório e guard reconectam ao Postgres
    repo2 = PostgresPaidOperationRepository(connect)
    guard2 = PaidOperationGuard(repo2, Decimal("10.00"), Decimal("5.00"))
    assert guard2.external_reference_id(logical_key) == "provider-job-777"
    with pytest.raises(OperationInProgress):
        guard2.reserve(logical_key, VIDEO_A, Decimal("1.20"))

    # Confirmação duplicada (replay) grava EXATAMENTE 1 linha em studio.usage_ledger
    entry = UsageEntry(video_id=VIDEO_A, step="assets", provider="offline-dbl", model="v1", cost_usd=1.15)
    conf = CostConfirmation.actual(Decimal("1.15"), reference="provider-job-777", confirmed_by="worker:rec01")
    guard2.confirm(logical_key, entry, conf)
    guard2.confirm(logical_key, entry, conf)  # replay idempotente

    assert conn.execute("SELECT COUNT(*) FROM studio.usage_ledger WHERE video_id = %s", (VIDEO_A,)).fetchone()[0] == 1

    # Confirmação divergente ou transição stale após CONFIRMED é rejeitada
    with pytest.raises(InvalidOperationTransition):
        guard2.confirm(
            logical_key,
            UsageEntry(video_id=VIDEO_A, step="assets", provider="offline-dbl", model="v1", cost_usd=2.00),
            CostConfirmation.actual(Decimal("2.00"), reference="provider-job-777", confirmed_by="worker:rec01"),
        )
    with pytest.raises(InvalidOperationTransition):
        guard2.release(logical_key, "stale release")
    with pytest.raises(InvalidOperationTransition):
        guard2.mark_uncertain(logical_key, "stale uncertain")
    with pytest.raises(InvalidOperationTransition):
        guard2.record_external_ref(logical_key, "provider-job-777")


def test_rec_01_02_unknown_cost_never_becomes_zero_and_pre_vs_post_effect_failures(db):
    conn, connect = db
    repo = PostgresPaidOperationRepository(connect)
    guard = PaidOperationGuard(repo, Decimal("10.00"), Decimal("5.00"))

    # 1. Custo desconhecido (settle retorna None) -> UNCERTAIN, nunca $0.00 FREE
    with pytest.raises(OperationUncertain):
        guard.run(
            "op-unknown-cost",
            VIDEO_A,
            Decimal("0.50"),
            lambda: {"ok": True},
            lambda _r: None,
        )
    assert repo.state("op-unknown-cost") is PaidOperationState.UNCERTAIN
    assert conn.execute("SELECT COUNT(*) FROM studio.usage_ledger").fetchone()[0] == 0

    # 2. Falha pré-efeito libera (RELEASED) e permite reabertura segura com mesma chave lógica
    attempts = 0

    def _pre_then_ok():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PreEffectFailure("offline validation before submit")
        guard.record_external_ref("op-pre-then-ok", "ext-ok-1")
        return "done"

    with pytest.raises(PreEffectFailure):
        guard.run(
            "op-pre-then-ok",
            VIDEO_A,
            Decimal("0.50"),
            _pre_then_ok,
            lambda _r: (
                UsageEntry(video_id=VIDEO_A, step="render", provider="mock", model="m1", cost_usd=0.5),
                CostConfirmation.actual(Decimal("0.50"), reference="ext-ok-1", confirmed_by="test"),
            ),
        )
    assert repo.state("op-pre-then-ok") is PaidOperationState.RELEASED
    assert repo.external_reference_id("op-pre-then-ok") is None

    # Reabre mesma chave (attempt passa a 2 no banco) e conclui com 1 submit externo efetivo
    out = guard.run(
        "op-pre-then-ok",
        VIDEO_A,
        Decimal("0.50"),
        _pre_then_ok,
        lambda _r: (
            UsageEntry(video_id=VIDEO_A, step="render", provider="mock", model="m1", cost_usd=0.5),
            CostConfirmation.actual(Decimal("0.50"), reference="ext-ok-1", confirmed_by="test"),
        ),
    )
    assert out == "done"
    assert attempts == 2
    assert conn.execute(
        "SELECT attempt FROM studio.paid_operations WHERE idempotency_key = 'op-pre-then-ok'"
    ).fetchone()[0] == 2

    # 3. Falha pós-efeito (ambígua) move para UNCERTAIN e bloqueia re-submit cego
    double_submit_count = 0

    def _post_effect_crash():
        nonlocal double_submit_count
        double_submit_count += 1
        guard.record_external_ref("op-post-crash", "ext-ambig-1")
        raise ConnectionError("network drop after submit")

    with pytest.raises(ConnectionError):
        guard.run(
            "op-post-crash",
            VIDEO_B,
            Decimal("0.80"),
            _post_effect_crash,
            lambda _r: None,
        )
    assert repo.state("op-post-crash") is PaidOperationState.UNCERTAIN
    assert repo.external_reference_id("op-post-crash") == "ext-ambig-1"

    with pytest.raises(OperationUncertain):
        guard.run("op-post-crash", VIDEO_B, Decimal("0.80"), _post_effect_crash, lambda _r: None)
    assert double_submit_count == 1  # nunca re-submete cegamente!


# ---------------------------------------------------------------------------
# REC-01.03 — Reconciliação pré-retry, timeout cooperativo, lease fencing e kill switch
# ---------------------------------------------------------------------------


def test_rec_01_03_pre_retry_reconciliation_blocks_uncertain_paid_op(db):
    _conn, connect = db
    runs_repo = PostgresProductionRunRepository(connect, dag=COORDINATOR_DAG)
    paid_repo = PostgresPaidOperationRepository(connect)
    guard = PaidOperationGuard(paid_repo, Decimal("10.00"), Decimal("5.00"))

    external_submits = 0
    op_key = "stage-script-op-1"

    class _PaidScriptHandler:
        available = True
        reason = "ok"
        stage = ProductionStage.SCRIPT

        def execute(self, ctx: StageContext) -> StageOutcome:
            nonlocal external_submits

            def _call():
                nonlocal external_submits
                external_submits += 1
                guard.record_external_ref(op_key, "ext-script-1")
                raise ConnectionError("socket reset after remote submit")

            guard.run(op_key, ctx.run.video_id, Decimal("0.50"), _call, lambda _r: None)
            return StageOutcome()

    class _NoopHandler:
        available = True
        reason = "ok"

        def __init__(self, stage: ProductionStage) -> None:
            self.stage = stage

        def execute(self, _ctx: StageContext) -> StageOutcome:
            return StageOutcome()

    handlers = {s: (_PaidScriptHandler() if s is ProductionStage.SCRIPT else _NoopHandler(s)) for s in ProductionStage}
    coordinator = ProductionCoordinator(
        runs_repo,
        handlers=handlers,
        mode=ProductionMode.INTERACTIVE,
        paid_ops=paid_repo,
        operation_key_for=lambda _run, ex: op_key if ex.stage_id is ProductionStage.SCRIPT else None,
    )
    created = coordinator.start(
        VIDEO_A,
        idempotency_key="run-reconcile-block",
        channel_id=None,
        stages=(ProductionStage.SCRIPT,),
    )
    step1 = coordinator.step(created.run.run_id, owner="worker-1")
    assert step1.result is WorkerStepResult.FAILED
    assert external_submits == 1
    assert paid_repo.state(op_key) is PaidOperationState.UNCERTAIN

    # Retry sem reconciliação deve falhar fechado ANTES de chamar o handler novamente
    coordinator.retry(created.run.run_id, reason="operator retry")
    step2 = coordinator.step(created.run.run_id, owner="worker-1")
    assert step2.result is WorkerStepResult.FAILED
    assert "requires reconciliation" in step2.detail
    assert external_submits == 1  # NUNCA 2!


def test_rec_01_03_late_handler_fenced_after_lease_loss_and_timeout(db):
    conn, connect = db
    runs_repo = PostgresProductionRunRepository(connect, dag=COORDINATOR_DAG)
    paid_repo = PostgresPaidOperationRepository(connect)
    guard = PaidOperationGuard(paid_repo, Decimal("10.00"), Decimal("5.00"))

    entered = threading.Event()
    proceed = threading.Event()
    late_done = threading.Event()
    late_errors: list[Exception] = []
    captured_ctx: list[StageContext] = []

    class _SlowFencedHandler:
        available = True
        reason = "ok"
        stage = ProductionStage.SCRIPT

        def execute(self, ctx: StageContext) -> StageOutcome:
            captured_ctx.append(ctx)
            entered.set()
            proceed.wait(timeout=5)
            # Handler tardio tenta confirmar que ainda é dono antes de escrever/confirmar
            try:
                ctx.ensure_active()
                guard.run(
                    "late-op-should-not-settle",
                    ctx.run.video_id,
                    Decimal("0.50"),
                    lambda: "late",
                    lambda _r: (
                        UsageEntry(video_id=ctx.run.video_id, step="script", provider="mock", model="m1", cost_usd=0.5),
                        CostConfirmation.actual(Decimal("0.50"), reference="late-ref", confirmed_by="late"),
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                late_errors.append(exc)
                raise
            finally:
                late_done.set()
            return StageOutcome()

    class _NoopHandler:
        available = True
        reason = "ok"

        def __init__(self, stage: ProductionStage) -> None:
            self.stage = stage

        def execute(self, _ctx: StageContext) -> StageOutcome:
            return StageOutcome()

    handlers = {s: (_SlowFencedHandler() if s is ProductionStage.SCRIPT else _NoopHandler(s)) for s in ProductionStage}
    coordinator = ProductionCoordinator(
        runs_repo,
        handlers=handlers,
        mode=ProductionMode.INTERACTIVE,
        paid_ops=paid_repo,
        stage_timeouts={ProductionStage.SCRIPT: 0.08},
    )
    created = coordinator.start(
        VIDEO_A,
        idempotency_key="run-fenced-timeout",
        channel_id=None,
        stages=(ProductionStage.SCRIPT,),
    )
    step = coordinator.step(created.run.run_id, owner="worker-slow")
    assert entered.is_set()
    assert step.result is WorkerStepResult.FAILED
    assert "exceeded timeout" in step.detail

    # Lease foi revogado imediatamente após timeout: ensure_held() deve levantar LeaseLost
    assert captured_ctx[0].lease is not None
    with pytest.raises(LeaseLost):
        captured_ctx[0].lease.ensure_held()

    # Libera o handler tardio e aguarda conclusão determinística via Event (sem sleep)
    proceed.set()
    assert late_done.wait(timeout=5)
    assert len(late_errors) == 1
    assert isinstance(late_errors[0], StageTimeoutError)
    assert conn.execute("SELECT COUNT(*) FROM studio.usage_ledger").fetchone()[0] == 0

    # Tentativa tardia de complete_stage com o fencing_token antigo é rejeitada pelo Postgres (NOT_RUNNING/LOST)
    late_complete = runs_repo.complete_stage(
        created.run.run_id,
        ProductionStage.SCRIPT,
        owner="worker-slow",
        fencing_token=step.execution.fencing_token,
    )
    assert late_complete.result in (StageTransitionResult.LOST, StageTransitionResult.NOT_RUNNING)


def test_rec_01_03_wiring_default_pre_retry_blocks_uncertain_without_operation_key_for(db):
    """Caminho padrão do wiring.py (operation_key_for=None) bloqueia retry em attempt > 1 se houver op UNCERTAIN."""
    _conn, connect = db
    runs_repo = PostgresProductionRunRepository(connect, dag=COORDINATOR_DAG)
    paid_repo = PostgresPaidOperationRepository(connect)
    guard = PaidOperationGuard(paid_repo, Decimal("10.00"), Decimal("5.00"))

    submits = 0

    class _ScriptHandler:
        available = True
        reason = "ok"
        stage = ProductionStage.SCRIPT

        def execute(self, ctx: StageContext) -> StageOutcome:
            nonlocal submits

            def _call():
                nonlocal submits
                submits += 1
                raise ConnectionError("ambiguous post-submit failure")

            guard.run("default-wiring-op", ctx.run.video_id, Decimal("0.50"), _call, lambda _r: None)
            return StageOutcome()

    class _NoopHandler:
        available = True
        reason = "ok"

        def __init__(self, stage: ProductionStage) -> None:
            self.stage = stage

        def execute(self, _ctx: StageContext) -> StageOutcome:
            return StageOutcome()

    handlers = {s: (_ScriptHandler() if s is ProductionStage.SCRIPT else _NoopHandler(s)) for s in ProductionStage}
    # Sem operation_key_for (exatamente como wiring.py:744)
    coordinator = ProductionCoordinator(
        runs_repo,
        handlers=handlers,
        mode=ProductionMode.INTERACTIVE,
        paid_ops=paid_repo,
    )
    created = coordinator.start(
        VIDEO_A,
        idempotency_key="run-wiring-default-reconcile",
        channel_id=None,
        stages=(ProductionStage.SCRIPT,),
    )
    step1 = coordinator.step(created.run.run_id, owner="worker-w1")
    assert step1.result is WorkerStepResult.FAILED
    assert submits == 1

    coordinator.retry(created.run.run_id, reason="retry without reconciliation")
    step2 = coordinator.step(created.run.run_id, owner="worker-w1")
    assert step2.result is WorkerStepResult.FAILED
    assert "requires reconciliation" in step2.detail
    assert submits == 1


def test_rec_01_03_publication_kill_switch_blocks_before_token_or_upload():
    token_calls = 0
    upload_calls = 0

    class _FailIfCalledTokens:
        def get_token(self, *_args, **_kwargs):
            nonlocal token_calls
            token_calls += 1
            raise AssertionError("token lookup não pode ocorrer com kill switch desligado")

    class _FailIfCalledUploader:
        def upload(self, *_args, **_kwargs):
            nonlocal upload_calls
            upload_calls += 1
            raise AssertionError("upload não pode ocorrer com kill switch desligado")

    class _StubPubRepo:
        def get(self, _pub_id):
            raise AssertionError("get não deve rodar antes do kill switch")

    class _StubVideoRepo:
        def get(self, _vid):
            return None

    pub = RunPublication(
        videos=_StubVideoRepo(),
        scripts=None,  # type: ignore[arg-type]
        assets=None,  # type: ignore[arg-type]
        jobs=None,  # type: ignore[arg-type]
        snaps=None,  # type: ignore[arg-type]
        approvals=None,  # type: ignore[arg-type]
        intents=None,  # type: ignore[arg-type]
        pubs=_StubPubRepo(),
        files=None,  # type: ignore[arg-type]
        uploads=_FailIfCalledUploader(),
        tokens=_FailIfCalledTokens(),
        enabled=False,
    )
    res = pub.execute()
    assert res.result is PublicationResult.BLOCKED
    assert token_calls == 0
    assert upload_calls == 0
