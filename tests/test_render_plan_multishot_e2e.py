"""RP-024..RP-026 / VE-Onda1 — Teste de integração E2E FFmpeg real com assets sintéticos (Multi-shot E2E).

Valida a compilação e renderização ponta a ponta com FFmpeg real de um RenderPlan v2 contendo:
- Cena 1: multi-shot com 2 shots (imagem com corte seco -> vídeo com trim de offset)
- Cena 2: cena com shot único (imagem com transição fade)
- Áudio: narração montada de 2 vozes + música sintetizada com ducking e loudnorm
- Verificação técnica no MP4 via ffprobe e evaluate_qa do domínio
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator
from app.studio.adapters.render_plan_compiler import compile_render_plan
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.render import SIZE, evaluate_qa
from app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    RenderPlan,
    StyleSnapshot,
    SubtitleCue,
    Timebase,
    Transition,
)
from app.studio.domain.render_plan_builder import (
    StoryboardScene,
    StoryboardShot,
    build_render_plan,
)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

# Aliases de compatibilidade para contratos de interface
compile_render = compile_render_plan


class RenderPlanExecutor(PlanFfmpegRenderer):
    """Executor compatível com o contrato de execução do plano de renderização."""

    def render(self, *args, **kwargs):
        if len(args) >= 3 and hasattr(args[0], "shots"):
            return self.execute(args[0], args[1], args[2], **kwargs)
        return super().render(*args, **kwargs)


def tone_wav(path: Path, seconds: float = 3.2, amplitude: float = 0.4, rate: int = 22050) -> None:
    """Gera arquivo WAV senoidal com tom audível e sem silêncio excessivo."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate)))
                for i in range(n)
            )
        )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@needs_ffmpeg
def test_render_plan_multishot_real_ffmpeg_e2e(tmp_path: Path):
    # ------------------------------------------------------------------ 1. Assets sintéticos
    img1_path = tmp_path / "img1.png"
    Image.new("RGB", (1080, 1920), color=(30, 80, 160)).save(img1_path)

    img2_path = tmp_path / "img2.png"
    Image.new("RGB", (1080, 1920), color=(160, 80, 30)).save(img2_path)

    video_path = tmp_path / "video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=1080x1920:rate=25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path),
        ],
        check=True,
    )

    # 3.2s e 2.2s com LEAD=0.3 e TAIL=0.5 totalizam exatamente 4.0s e 3.0s de cena
    wav1_path = tmp_path / "speech1.wav"
    tone_wav(wav1_path, seconds=3.2)

    wav2_path = tmp_path / "speech2.wav"
    tone_wav(wav2_path, seconds=2.2)

    speech_wavs = [wav1_path, wav2_path]

    # ------------------------------------------------------------------ 2. Manifest & Descriptors
    img1_sha = sha256_file(img1_path)
    img2_sha = sha256_file(img2_path)
    video_sha = sha256_file(video_path)

    asset_manifest = [
        AssetReference(
            asset_id="asset-img-1",
            asset_version=1,
            uri=str(img1_path),
            content_sha256=img1_sha,
            media_type="image",
            license="CC0",
        ),
        AssetReference(
            asset_id="asset-vid-1",
            asset_version=1,
            uri=str(video_path),
            content_sha256=video_sha,
            media_type="video",
            license="CC0",
            metadata={"codec": "h264", "width": "1080", "height": "1920", "duration_ticks": "100"},
        ),
        AssetReference(
            asset_id="asset-img-2",
            asset_version=1,
            uri=str(img2_path),
            content_sha256=img2_sha,
            media_type="image",
            license="CC0",
        ),
    ]

    descriptors = {
        "asset-img-1": AssetDescriptor(
            asset_id="asset-img-1",
            asset_version=1,
            uri=str(img1_path),
            content_sha256=img1_sha,
            media_type="image",
            license="CC0",
            location=str(img1_path),
            available=True,
            codec="png",
            width=1080,
            height=1920,
            byte_size=img1_path.stat().st_size,
        ),
        "asset-vid-1": AssetDescriptor(
            asset_id="asset-vid-1",
            asset_version=1,
            uri=str(video_path),
            content_sha256=video_sha,
            media_type="video",
            license="CC0",
            location=str(video_path),
            available=True,
            codec="h264",
            width=1080,
            height=1920,
            duration_ticks=100,
            byte_size=video_path.stat().st_size,
        ),
        "asset-img-2": AssetDescriptor(
            asset_id="asset-img-2",
            asset_version=1,
            uri=str(img2_path),
            content_sha256=img2_sha,
            media_type="image",
            license="CC0",
            location=str(img2_path),
            available=True,
            codec="png",
            width=1080,
            height=1920,
            byte_size=img2_path.stat().st_size,
        ),
    }

    # ------------------------------------------------------------------ 3. RenderPlan v2
    scene1 = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-img-1",
        narration="Cena com múltiplos shots e corte seco.",
        speech_seconds=3.2,
        label="CENA 1",
        shots=[
            StoryboardShot(
                shot_id="shot-01",
                asset_id="asset-img-1",
                duration_s=2.0,
                transition=Transition(kind="cut", duration_ticks=0),
            ),
            StoryboardShot(
                shot_id="shot-02",
                asset_id="asset-vid-1",
                duration_s=2.0,
                asset_offset_s=1.0,
            ),
        ],
    )
    scene2 = StoryboardScene(
        scene_id="scene-02",
        asset_id="asset-img-2",
        narration="Cena final com imagem única e transição suave.",
        speech_seconds=2.2,
        label="CENA 2",
        shots=[
            StoryboardShot(
                shot_id="shot-03",
                asset_id="asset-img-2",
                duration_s=3.0,
                transition=Transition(kind="fade", duration_ticks=10),
            ),
        ],
    )

    plan = build_render_plan(
        plan_id="plan:e2e-multishot",
        revision=1,
        project_id="proj-e2e",
        video_id="video-e2e",
        format=VideoFormat.short,
        scenes=[scene1, scene2],
        assets=asset_manifest,
        timebase=Timebase(ticks_per_second=25),
        style_snapshot=StyleSnapshot(style_id="default", version=1),
    )

    # Ajusta legendas para que fiquem confinadas dentro de cada shot base individual
    # Shot 1: ticks 0..50 (cue 8..45) | Shot 2: ticks 50..100 (cue 58..95) | Shot 3: ticks 100..175 (cue 108..165)
    adjusted_subtitles = [
        SubtitleCue(scene_id="scene-01", track_id="subtitles", text="Primeiro plano com imagem", start_tick=8, duration_ticks=37),
        SubtitleCue(scene_id="scene-01", track_id="subtitles", text="Segundo plano com vídeo", start_tick=55, duration_ticks=38),
        SubtitleCue(scene_id="scene-02", track_id="subtitles", text="Cena dois com imagem e fade", start_tick=108, duration_ticks=55),
    ]
    plan = plan.model_copy(
        update={
            "schema_version": 2,
            "timeline": plan.timeline.model_copy(update={"subtitles": adjusted_subtitles}),
        }
    )

    # Asserções de conformidade do contrato do RenderPlan v2
    assert plan.schema_version == 2
    assert plan.output.format == VideoFormat.short
    assert (plan.output.width, plan.output.height) == SIZE[VideoFormat.short]
    assert plan.timeline.ticks_per_second == 25
    assert plan.timeline.duration_ticks == 175  # 7.0s em 25 ticks/s

    s1_shots = plan.timeline.scenes[0].base_shots
    assert len(s1_shots) == 2
    assert s1_shots[0].duration_ticks == 50
    assert s1_shots[0].transition == Transition(kind="cut", duration_ticks=0)
    assert s1_shots[1].duration_ticks == 50
    assert s1_shots[1].asset_offset_ticks == 25  # 1s offset em 25 tps

    s2_shots = plan.timeline.scenes[1].base_shots
    assert len(s2_shots) == 1
    assert s2_shots[0].duration_ticks == 75
    assert s2_shots[0].transition == Transition(kind="fade", duration_ticks=10)

    # ------------------------------------------------------------------ 4. Compilação e Render
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / "final_multishot.mp4"

    compiled = compile_render(plan=plan, assets=descriptors, work_dir=str(work_dir))
    assert len(compiled.shots) == 3

    executor = RenderPlanExecutor()
    rendered_file = executor.render(compiled, speech_wavs, out_path)
    assert rendered_file == out_path

    # ------------------------------------------------------------------ 5. Verificação ffprobe
    assert out_path.exists()
    assert out_path.stat().st_size > 0

    probe_cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(out_path),
    ]
    probe_run = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    media_info = json.loads(probe_run.stdout)

    video_stream = next(s for s in media_info["streams"] if s["codec_type"] == "video")
    assert video_stream["codec_name"] == "h264"
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920

    audio_stream = next(s for s in media_info["streams"] if s["codec_type"] == "audio")
    assert audio_stream["codec_name"] == "aac"

    duration_s = float(media_info["format"]["duration"])
    assert duration_s == pytest.approx(7.0, abs=0.1)

    # ------------------------------------------------------------------ 6. QA de Mídia
    metrics = FfmpegQa().analyze(out_path, narration=work_dir / "narration.wav")
    qa_result = evaluate_qa({**metrics, "expected_s": 7.0}, VideoFormat.short)
    assert qa_result.passed, f"QA técnico reprovou: {qa_result.failures}"
    assert not qa_result.failures
    assert (metrics["width"], metrics["height"]) == (1080, 1920)
    assert metrics["has_audio"] is True
    assert metrics["silence_ratio"] < 0.6
    assert metrics["black_ratio"] < 0.3
    assert -45 < metrics["integrated_lufs"] < -9
    assert metrics["narration_lufs"] is not None and metrics["narration_lufs"] > -45

    # Avaliação adicional pelo FfmpegQualityEvaluator (gate F6 / blocking findings)
    evaluator = FfmpegQualityEvaluator()
    qa_report = evaluator.evaluate(
        plan=plan,
        media_path=out_path,
        narration_path=work_dir / "narration.wav",
        descriptors=tuple(descriptors.values()),
        render_id="render-e2e-multishot",
        checksum=sha256_file(out_path),
    )
    assert len(qa_report.blocking_findings) == 0, [f.evidence for f in qa_report.blocking_findings]
    assert qa_report.is_publishable


def test_render_plan_multishot_persistence_roundtrip(conn, dsn):
    """Verifica que o RenderPlan v2 multi-shot persiste e recupera via PostgresRenderPlanRepository."""
    import psycopg
    from app.studio.adapters.postgres.db import migrate
    from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
    from app.studio.adapters.postgres.repo import PostgresVideoRepository

    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("canal-e2e")
    video = videos.create_video(project.id, "E2E Multishot Video", VideoFormat.short)
    repo = PostgresRenderPlanRepository(connect)

    scene1 = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-img-1",
        narration="Primeira cena com dois shots.",
        speech_seconds=3.2,
        shots=[
            StoryboardShot(
                shot_id="shot-01",
                asset_id="asset-img-1",
                duration_s=2.0,
                transition=Transition(kind="cut", duration_ticks=0),
            ),
            StoryboardShot(
                shot_id="shot-02",
                asset_id="asset-vid-1",
                duration_s=2.0,
                asset_offset_s=1.0,
            ),
        ],
    )
    scene2 = StoryboardScene(
        scene_id="scene-02",
        asset_id="asset-img-2",
        narration="Segunda cena com imagem e fade.",
        speech_seconds=2.2,
        shots=[
            StoryboardShot(
                shot_id="shot-03",
                asset_id="asset-img-2",
                duration_s=3.0,
                transition=Transition(kind="fade", duration_ticks=10),
            ),
        ],
    )

    plan = build_render_plan(
        plan_id=f"plan:{video.id}",
        revision=1,
        project_id=project.id,
        video_id=video.id,
        format=VideoFormat.short,
        scenes=[scene1, scene2],
        assets=[
            AssetReference(
                asset_id="asset-img-1",
                asset_version=1,
                uri="storage/img1.png",
                content_sha256="a" * 64,
                media_type="image",
                license="CC0",
            ),
            AssetReference(
                asset_id="asset-vid-1",
                asset_version=1,
                uri="storage/vid1.mp4",
                content_sha256="b" * 64,
                media_type="video",
                license="CC0",
            ),
            AssetReference(
                asset_id="asset-img-2",
                asset_version=1,
                uri="storage/img2.png",
                content_sha256="c" * 64,
                media_type="image",
                license="CC0",
            ),
        ],
        timebase=Timebase(ticks_per_second=25),
        style_snapshot=StyleSnapshot(style_id="default", version=1),
    )

    repo.save_plan(plan)
    loaded = repo.latest_plan(plan.plan_id)

    assert loaded is not None
    assert loaded.plan_id == plan.plan_id
    assert loaded.revision == 1
    assert loaded.schema_version == 2
    assert loaded.timeline.duration_ticks == 175
    assert len(loaded.timeline.scenes) == 2

    loaded_s1_shots = loaded.timeline.scenes[0].base_shots
    assert len(loaded_s1_shots) == 2
    assert loaded_s1_shots[0].shot_id == "shot-01"
    assert loaded_s1_shots[0].transition == Transition(kind="cut", duration_ticks=0)
    assert loaded_s1_shots[1].shot_id == "shot-02"
    assert loaded_s1_shots[1].asset_offset_ticks == 25

    loaded_s2_shots = loaded.timeline.scenes[1].base_shots
    assert len(loaded_s2_shots) == 1
    assert loaded_s2_shots[0].shot_id == "shot-03"
    assert loaded_s2_shots[0].transition == Transition(kind="fade", duration_ticks=10)

