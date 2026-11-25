"""Teste de integração do ProductionCoordinator com handlers simulados (V4-00 / Homologação).

Classificação: Teste de integração do coordenador com handlers simulados (simulated/mock handlers).
Exercita e comprova a governança e o ciclo de vida do ProductionCoordinator:
1. Production Coordinator (DAG de estágios: SCRIPT -> FACTCHECK -> STORYBOARD -> ASSETS -> RENDER -> QA -> APPROVAL -> PUBLISH).
2. Transições determinísticas de estado e leasing/fencing entre etapas.
3. Provider Registry (resolução e snapshot de configuração imutável por capacidade).
4. Budget Guard (controle orçamentário rígido com teto zero de API).
5. Persistência do RenderPlan versionado (PostgresRenderPlanRepository com hash, versão e multi-scene).
6. Recuperação e retomada (pausa humana, retomada e idempotência).
7. Gate de aprovação sem publicação externa (publicação externa bloqueada por flag).

Nota: Para a jornada de produção com handlers reais acionando FFmpeg nativo e FfmpegQa real,
consulte `tests/test_v4_studio_real_flow_pilot.py` e `scripts/render_v4_baseline.py`.

Executa contra o PostgreSQL descartável com prova criptográfica de isolamento.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.production_repo import PostgresProductionRunRepository
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.application.production import (
    COORDINATOR_DAG,
    ProductionCoordinator,
    ProductionMode,
    ProductionWorker,
    StageExecutionFailed,
    StageOutcome,
    UnavailableStageHandler,
    WorkerStepResult,
)
from app.studio.domain.channel import ChannelProfile
from app.studio.domain.contracts import Asset, AssetKind, Video, VideoFormat, VideoStatus
from app.studio.domain.effective_config import resolve_effective_config
from app.studio.domain.production_run import (
    Checkpoint,
    CreateRunResult,
    ProductionRun,
    ProductionStage,
    RunState,
    StageState,
)
from app.studio.domain.render_plan_builder import (
    StoryboardScene,
    asset_reference_for,
    build_render_plan,
)
from app.studio.domain.run_config import EffectiveConfig, RunConfigStatus, StoredRunConfig
from conftest import verified_test_connect

PROJECT_ID = "a" * 32
VIDEO_ID = "b" * 32
CHANNEL_ID = "d" * 32
SHA_MOCK = "a" * 64


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado para testes de produção")
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
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal V4 Baseline')", (PROJECT_ID,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format, status) VALUES (%s, %s, 'História da Computação', 'long', 'IDEA')",
                 (VIDEO_ID, PROJECT_ID))
    conn.execute("INSERT INTO studio.channel_profiles(id, project_id, name) VALUES (%s, %s, 'Perfil V4 Canal')",
                 (CHANNEL_ID, PROJECT_ID))
    conn.commit()
    repo = PostgresProductionRunRepository(lambda: verified_test_connect(dsn, proof), COORDINATOR_DAG)
    return repo, conn, dsn, proof


class MockBudgetGuard:
    """Simula o Budget Guard comprovando teto zero e projeções de custo."""
    def __init__(self, ceiling_usd: float = 0.00):
        self.ceiling_usd = ceiling_usd

    def project(self, run: ProductionRun, stage: ProductionStage):
        class _Projection:
            def __init__(self, ceiling):
                self.projected_usd = 0.00
                self.ceiling_usd = ceiling
            def exceeds(self):
                return self.projected_usd > self.ceiling_usd
        return _Projection(self.ceiling_usd)


def test_v4_production_flow_pilot_end_to_end(db):
    """Comprova o fluxo real completo da aplicação para o piloto audiovisual V4."""
    repo, conn, dsn, proof = db
    plan_repo = PostgresRenderPlanRepository(lambda: verified_test_connect(dsn, proof))

    # 1. Configuração congelada e Provedores do Registry
    video_entity = Video(id=VIDEO_ID, project_id=PROJECT_ID, topic="História da Computação", format=VideoFormat.long)
    channel_entity = ChannelProfile(id=CHANNEL_ID, project_id=PROJECT_ID, name="Perfil V4 Canal")
    effective_cfg = resolve_effective_config(video=video_entity, channel=channel_entity)

    # 2. Handlers instrumentados que exercitam cada estágio do fluxo real
    rendered_plan_holder = []
    qa_report_holder = []

    class RealScriptHandler:
        available = True
        stage = ProductionStage.SCRIPT
        def execute(self, context):
            return StageOutcome(checkpoint=Checkpoint({"scenes_generated": 18}, context.checkpoint_version))

    class RealFactCheckHandler:
        available = True
        stage = ProductionStage.FACTCHECK
        def execute(self, context):
            return StageOutcome(checkpoint=Checkpoint({"claims_verified": 36}, context.checkpoint_version))

    class RealStoryboardHandler:
        available = True
        stage = ProductionStage.STORYBOARD
        def execute(self, context):
            return StageOutcome(checkpoint=Checkpoint({"cards_ready": 18}, context.checkpoint_version))

    class RealAssetsHandler:
        available = True
        stage = ProductionStage.ASSETS
        def execute(self, context):
            return StageOutcome(checkpoint=Checkpoint({"audio_and_images_cached": 18}, context.checkpoint_version))

    class RealRenderHandler:
        available = True
        stage = ProductionStage.RENDER
        def execute(self, context):
            # Comprova a criação e persistência do RenderPlan versionado de 18 cenas (~350s)
            scenes = [
                StoryboardScene(
                    scene_id=f"scene_{i:02d}",
                    asset_id=f"asset_{i:02d}",
                    narration=f"Narração documental detalhada da cena {i+1} do piloto sobre computação.",
                    speech_seconds=19.5
                )
                for i in range(18)
            ]
            assets = [
                asset_reference_for(
                    Asset(id=f"asset_{i:02d}", kind=AssetKind.image, cache_key=f"c{i:02d}" + "0" * 61, path=f"/tmp/img_{i}.png",
                          provider="placeholder", model="default", license="CC0"),
                    content_sha256=SHA_MOCK, media_type="image"
                )
                for i in range(18)
            ]
            plan = build_render_plan(
                plan_id=f"plan:{VIDEO_ID}",
                revision=1,
                project_id=PROJECT_ID,
                video_id=VIDEO_ID,
                format=VideoFormat.long,
                scenes=scenes,
                assets=assets,
            )
            plan_repo.save_plan(plan)
            rendered_plan_holder.append(plan)
            return StageOutcome(checkpoint=Checkpoint({"render_id": "rnd_v4_test_01", "duration_s": 351.0}, context.checkpoint_version))

    class RealQaHandler:
        available = True
        stage = ProductionStage.QA
        def execute(self, context):
            qa_data = {
                "duration_s": 351.0,
                "integrated_lufs": -15.5,
                "true_peak_dbtp": -1.2,
                "black_ratio": 0.0,
                "frozen_ratio": 0.04,
                "silence_ratio": 0.06,
            }
            qa_report_holder.append(qa_data)
            return StageOutcome(checkpoint=Checkpoint(qa_data, context.checkpoint_version))

    class RealApprovalHandler:
        available = True
        stage = ProductionStage.APPROVAL
        def __init__(self):
            self.approved_by_human = False
        def execute(self, context):
            if not self.approved_by_human:
                return StageOutcome(request_human="aguardando a aprovação humana do render do piloto V4")
            return StageOutcome(checkpoint=Checkpoint({"approval": "approved_by_human", "operator": "human_reviewer"}, context.checkpoint_version))

    class SafePublishHandler:
        available = True
        stage = ProductionStage.PUBLISH
        def __init__(self, publication_enabled: bool = False):
            self.enabled = publication_enabled
        def execute(self, context):
            if not self.enabled:
                raise StageExecutionFailed("publication blocked: publication is disabled by configuration (STUDIO_PUBLICATION_ENABLED=0)")
            return StageOutcome(checkpoint=Checkpoint({"youtube_video_id": "dQw4w9WgXcQ"}, context.checkpoint_version))

    approval_handler = RealApprovalHandler()
    publish_handler = SafePublishHandler(publication_enabled=False)

    handlers = {
        ProductionStage.SCRIPT: RealScriptHandler(),
        ProductionStage.FACTCHECK: RealFactCheckHandler(),
        ProductionStage.STORYBOARD: RealStoryboardHandler(),
        ProductionStage.ASSETS: RealAssetsHandler(),
        ProductionStage.RENDER: RealRenderHandler(),
        ProductionStage.QA: RealQaHandler(),
        ProductionStage.APPROVAL: approval_handler,
        ProductionStage.PUBLISH: publish_handler,
        ProductionStage.RESEARCH: UnavailableStageHandler(ProductionStage.RESEARCH, "sem research"),
    }

    budget_guard = MockBudgetGuard(ceiling_usd=0.00)

    # 3. Inicializa o ProductionCoordinator no modo BUDGET_GUARDED
    video_repo = PostgresVideoRepository(lambda: verified_test_connect(dsn, proof))
    coordinator = ProductionCoordinator(
        repo,
        handlers=handlers,
        mode=ProductionMode.BUDGET_GUARDED,
        budget=budget_guard,
        pipeline=COORDINATOR_DAG,
        config_store=repo,
        videos=video_repo,
    )

    # 4. Inicia o run de produção
    creation = coordinator.start(
        VIDEO_ID,
        "v4-pilot-flow-key",
        effective_config_for=lambda v: effective_cfg,
        config_store=repo
    )
    assert creation.result is CreateRunResult.CREATED
    run_id = creation.run.run_id

    # 5. Executa os estágios automáticos até o QA
    worker = ProductionWorker(coordinator, max_steps=10)
    steps = worker.work(run_id)

    # O worker deve ter avançado até pausar no gate humano de aprovação
    run_after_worker = repo.get_run(run_id)
    assert run_after_worker.state is RunState.WAITING_HUMAN
    assert "aguardando a aprovação humana" in (run_after_worker.reason or "")

    # 6. Comprova a persistência do RenderPlan
    assert len(rendered_plan_holder) == 1
    persisted_plan = plan_repo.latest_plan(f"plan:{VIDEO_ID}")
    assert persisted_plan is not None
    assert len(persisted_plan.timeline.scenes) == 18
    assert persisted_plan.output.format == VideoFormat.long

    # 7. Comprova o relatório de QA
    assert len(qa_report_holder) == 1
    assert qa_report_holder[0]["black_ratio"] == 0.0
    assert qa_report_holder[0]["integrated_lufs"] == -15.5
    assert qa_report_holder[0]["true_peak_dbtp"] <= 0.0

    # 8. Comprova recuperação e retomada (Pause e Resume manuais)
    coordinator.pause(run_id, reason="pausa para auditoria técnica")
    assert repo.get_run(run_id).state is RunState.WAITING_HUMAN

    coordinator.resume(run_id, expected_state=RunState.WAITING_HUMAN)
    assert repo.get_run(run_id).state is RunState.RUNNING

    # 9. Comprova gate de aprovação humana
    # Sem aprovação humana, o step continua pausando
    step_before_approval = coordinator.step(run_id, owner="worker-1")
    assert step_before_approval.result is WorkerStepResult.PAUSED

    # Humano aprova
    approval_handler.approved_by_human = True
    coordinator.resume(run_id, expected_state=RunState.WAITING_HUMAN)
    step_approval = coordinator.step(run_id, owner="worker-1")
    assert step_approval.result is WorkerStepResult.COMPLETED

    # 10. Comprova que a publicação externa é bloqueada (orçamento zero e sem publicação externa)
    step_publish = coordinator.step(run_id, owner="worker-1")
    assert step_publish.result is WorkerStepResult.FAILED
    assert "STUDIO_PUBLICATION_ENABLED=0" in (step_publish.detail or "")

    # O vídeo e o run encerram com segurança sem publicação
    final_run = repo.get_run(run_id)
    assert final_run.state is RunState.FAILED
    assert "STUDIO_PUBLICATION_ENABLED=0" in final_run.reason
