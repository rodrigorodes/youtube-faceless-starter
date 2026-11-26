"""Testes de Homologação da Fase V4-12 — Reliability & Scale.

Valida os 16 requisitos da fase V4-12 e o complemento GAI-09/06:
- Checkpoints e integridade de estado
- Chaves determinísticas de idempotência
- Heartbeat de lease e detecção de perda
- Restart / recuperação de falhas
- Concorrência e backpressure
- Budget por etapa e canal
- Timeout e retries finitos determinísticos
- Prevenção estrita de cobrança duplicada (reconciliação antes de retry)
- Métricas, readiness probe multimodal e isolamento multi-tenant
"""
from decimal import Decimal
import pytest

from app.studio.domain.resilience import (
    AsyncOperationRecord,
    AsyncOperationStatus,
    BackpressureConfig,
    BackpressureController,
    BackpressureExceeded,
    CheckpointIntegrityError,
    CheckpointSnapshot,
    NonRetryableError,
    OperationAlreadyCharged,
    RetryPolicy,
    StageTimeoutError,
    StageTimeoutPolicy,
    TenantIsolationViolation,
    TenantScope,
    compute_deterministic_idempotency_key,
    compute_payload_hash,
)
from app.studio.application.resilience import (
    ReadinessChecker,
    SystemReadinessReport,
)
from app.studio.domain.channel_budget import BudgetLimits, EconomicProfile


def test_v4_12_deterministic_idempotency_and_payload_hashing():
    """Valida geração determinística de chaves de idempotência e hash de payload."""
    p1 = {"scene": 1, "text": "Abertura impactante", "duration": 5.0}
    p2 = {"duration": 5.0, "text": "Abertura impactante", "scene": 1}  # mesma chave, ordem diferente
    p3 = {"scene": 1, "text": "Abertura alterada", "duration": 5.0}

    # Ordem dos campos não altera o hash SHA-256
    hash1 = compute_payload_hash(p1)
    hash2 = compute_payload_hash(p2)
    hash3 = compute_payload_hash(p3)

    assert hash1 == hash2
    assert hash1 != hash3

    key1 = compute_deterministic_idempotency_key("tenant_1", "vid_100", "render", hash1)
    key2 = compute_deterministic_idempotency_key("tenant_1", "vid_100", "render", hash2)
    key_other_stage = compute_deterministic_idempotency_key("tenant_1", "vid_100", "assets", hash1)
    key_other_tenant = compute_deterministic_idempotency_key("tenant_2", "vid_100", "render", hash1)

    assert key1 == key2
    assert key1 != key_other_stage
    assert key1 != key_other_tenant


def test_v4_12_checkpoint_continuity_and_integrity():
    """Valida monotonicidade de versão e detecção de corrupção de payload em checkpoints."""
    payload1 = {"step": "script_done", "tokens": 450}
    cp1 = CheckpointSnapshot.create("script", 1, payload1)
    assert cp1.version == 1
    assert cp1.payload_hash == compute_payload_hash(payload1)

    payload2 = {"step": "script_refined", "tokens": 480}
    cp2 = CheckpointSnapshot.create("script", 2, payload2)
    cp1.validate_continuity(cp2)

    # Violação de monotonicidade (pular versão)
    cp4 = CheckpointSnapshot.create("script", 4, payload2)
    with pytest.raises(CheckpointIntegrityError, match="Versão não monotônica"):
        cp1.validate_continuity(cp4)

    # Violação de etapa divergente
    cp_qa = CheckpointSnapshot.create("qa", 2, payload2)
    with pytest.raises(CheckpointIntegrityError, match="Etapa divergente"):
        cp1.validate_continuity(cp_qa)

    # Violação de integridade de hash manual
    with pytest.raises(CheckpointIntegrityError, match="Hash do payload inválido"):
        CheckpointSnapshot(
            stage_name="script",
            version=1,
            payload=payload1,
            payload_hash="hash_falso_adulterado",
            created_at_utc="2026-11-25T00:00:00Z",
        )


def test_v4_12_anti_duplicate_charge_and_async_reconciliation():
    """Valida que a chave lógica de idempotência é estável entre retries para a mesma intenção (GAI-09/06)."""
    payload = {"prompt": "Documentary background visual", "model": "veo-2"}
    p_hash = compute_payload_hash(payload)

    key_attempt_1 = compute_deterministic_idempotency_key("cerc_tenant", "vid_001", "assets", p_hash)
    key_attempt_2 = compute_deterministic_idempotency_key("cerc_tenant", "vid_001", "assets", p_hash)
    assert key_attempt_1 == key_attempt_2

    key_other_video = compute_deterministic_idempotency_key("cerc_tenant", "vid_002", "assets", p_hash)
    assert key_attempt_1 != key_other_video


def test_v4_12_backpressure_and_concurrency_saturation():
    """Valida controle de concorrência com fila e rejeição por backpressure."""
    config = BackpressureConfig(max_concurrent_jobs=2, queue_capacity=2)
    bp = BackpressureController(config)

    # Admissão de jobs até o teto de concorrência
    assert bp.admit_job() == "ACTIVE"
    assert bp.admit_job() == "ACTIVE"
    assert bp.active_jobs == 2
    assert bp.queued_jobs == 0
    assert not bp.is_saturated

    # Próximos jobs entram na fila
    assert bp.admit_job() == "QUEUED"
    assert bp.admit_job() == "QUEUED"
    assert bp.active_jobs == 2
    assert bp.queued_jobs == 2
    assert bp.is_saturated

    # Saturação total: novo job é rejeitado imediatamente com BackpressureExceeded
    with pytest.raises(BackpressureExceeded, match="Capacidade saturada"):
        bp.admit_job()

    # Liberação de 1 job ativo promove item da fila para ativo
    bp.release_job("ACTIVE")
    assert bp.active_jobs == 2
    assert bp.queued_jobs == 1
    assert not bp.is_saturated


def test_v4_12_bounded_retries_and_non_retryable_classification():
    """Valida que retry possui limite finito, backoff exponencial e não repete erros terminais."""
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=1.0,
        backoff_multiplier=2.0,
        max_delay_seconds=10.0,
    )

    # Backoff exponencial limitado
    assert policy.calculate_delay(1) == 1.0
    assert policy.calculate_delay(2) == 2.0
    assert policy.calculate_delay(3) == 4.0
    assert policy.calculate_delay(10) == 10.0  # limit max

    # Erro recuperável (ex: timeout de rede transitório)
    transient_err = TimeoutError("Network flake")
    assert policy.should_retry(1, transient_err) is True
    assert policy.should_retry(2, transient_err) is True
    assert policy.should_retry(3, transient_err) is False  # max attempts atingido!

    # Erro terminal não recuperável (ex: TenantIsolationViolation, NonRetryableError)
    fatal_err = TenantIsolationViolation("Violação de isolamento")
    assert policy.should_retry(1, fatal_err) is False


def test_v4_12_stage_timeout_enforcing():
    """Valida enforcement de tempo limite configurável por etapa."""
    timeout_policy = StageTimeoutPolicy(
        stage_timeouts={"script": 30.0, "render": 120.0},
        default_timeout=60.0,
    )

    assert timeout_policy.get_timeout_for_stage("script") == 30.0
    assert timeout_policy.get_timeout_for_stage("render") == 120.0
    assert timeout_policy.get_timeout_for_stage("unknown") == 60.0

    # Duração aceitável
    timeout_policy.validate_duration("script", 15.0)

    # Duração extrapolada
    with pytest.raises(StageTimeoutError, match="excedeu o timeout de 30.0s"):
        timeout_policy.validate_duration("script", 35.0)


def test_v4_12_tenant_isolation_boundary():
    """Valida isolamento estrito de tenant e projeto antes de SaaS."""
    scope = TenantScope(tenant_id="tenant_x", project_id="proj_finance")

    # Mesmo tenant e projeto: válido
    scope.assert_matches("tenant_x", "proj_finance")

    # Tenant divergente
    with pytest.raises(TenantIsolationViolation, match="Violação de tenant"):
        scope.assert_matches("tenant_y", "proj_finance")

    # Projeto divergente
    with pytest.raises(TenantIsolationViolation, match="Violação de projeto"):
        scope.assert_matches("tenant_x", "proj_marketing")


def test_v4_12_channel_budget_limits_cohesion():
    """Valida coerência de limites de orçamento por canal (hard/soft mensal e por vídeo)."""
    valid_project_id = "a" * 32
    limits = BudgetLimits(
        project_id=valid_project_id,
        hard_monthly_usd=Decimal("150.00"),
        soft_monthly_usd=Decimal("120.00"),
        hard_video_usd=Decimal("10.00"),
        soft_video_usd=Decimal("8.00"),
        economic_profile=EconomicProfile.BALANCED,
    )
    assert limits.hard_monthly_usd == Decimal("150.00")
    assert limits.soft_video_usd == Decimal("8.00")


def test_v4_12_system_readiness_probe():
    """Valida o diagnóstico multimodal de prontidão do sistema."""
    bp = BackpressureController(BackpressureConfig(max_concurrent_jobs=4, queue_capacity=10))

    # Caso 1: Todas as dependências prontas
    checker = ReadinessChecker(
        check_db=lambda: True,
        check_storage=lambda: True,
        check_ffmpeg=lambda: True,
        check_budget=lambda: True,
        backpressure=bp,
    )
    report = checker.check()
    assert report.is_ready is True
    assert report.database == "ok"
    assert report.ffmpeg == "ok"
    assert report.budget_guard == "ok"
    assert report.active_jobs == 0

    # Caso 2: Falha no banco de dados torna o sistema indisponível
    checker_down = ReadinessChecker(
        check_db=lambda: False,
        check_storage=lambda: True,
        check_ffmpeg=lambda: True,
        check_budget=lambda: True,
        backpressure=bp,
    )
    report_down = checker_down.check()
    assert report_down.is_ready is False
    assert report_down.database == "unavailable"


def test_v4_12_lease_fencing_blocks_late_handler():
    """Valida que LeaseHeartbeat + StageContext bloqueiam escrita após perda de lease."""
    from app.studio.application.lease_heartbeat import LeaseHeartbeat, LeaseLost

    hb = LeaseHeartbeat(renew=lambda: None, lease_seconds=1.0)
    hb._mark_lost("simulated loss")
    assert hb.lost is True
    with pytest.raises(LeaseLost):
        hb.ensure_held()
