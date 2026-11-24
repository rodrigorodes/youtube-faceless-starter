"""Onda 6 — Teste E2E do Vídeo Piloto Longo (16:9, 3 minutos) com Amostragem e Custos.

Executa de ponta a ponta:
- Produção de vídeo longo (16:9, 1920x1080) de 180 segundos (3 minutos)
- 12 cenas estruturadas com pacing balanceado (multishot)
- Trilha sonora CC0 real com ducking automático (sidechain compression)
- Renderização real com FFmpeg dentro do contêiner
- Inspeção técnica pelo QaReport v2
- Amostragem visual de 6 quadros ao longo da timeline (1920x1080)
- Rastreabilidade de custos no usage_ledger por categoria (llm, tts, image, render)
"""
from __future__ import annotations

import hashlib
import math
import shutil
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository
from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.render_plan_compiler import compile_render_plan
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import ProductionMode, UsageEntry, VideoFormat
from app.studio.domain.creative_director import CreativeBrief
from app.studio.domain.pacing import PacingPreset
from app.studio.domain.quality import QualityEvidence, evaluate_quality
from app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    StyleSnapshot,
    Timebase,
)
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan
from scripts.sample_pilot_frames import sample_frames

AT = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _generate_tone_speech(path: Path, seconds: float = 14.2, rate: int = 22050) -> None:
    """Gera fala sintetizada simulada com modulação e amplitude adequada para teste."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        total_samples = int(seconds * rate)
        frames = bytearray()
        for i in range(total_samples):
            t = i / rate
            envelope = 0.5 * (1.0 + math.sin(2 * math.pi * 3.0 * t)) if (t % 1.2) < 0.9 else 0.05
            sample = int(32767 * 0.35 * envelope * math.sin(2 * math.pi * 180 * t))
            frames.extend(struct.pack("<h", sample))
        w.writeframes(bytes(frames))


@needs_ffmpeg
def test_pilot_video_longform_production_e2e(conn, dsn, tmp_path: Path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    u_repo = PostgresUsageRepository(connect)

    # 1. Criação do projeto e vídeo longo (16:9, 180s, modo diretor, pacing balanceado)
    project = v_repo.create_project("Canal Ciência e Futuro", niche="Tecnologia", language="pt-BR")
    video = v_repo.create_video(
        project_id=project.id,
        topic="A História e o Futuro da Inteligência Artificial: Das Origens à Autonomia",
        fmt=VideoFormat.long,
        production_mode=ProductionMode.diretor,
        target_duration_s=180,
        pacing_preset="balanced",
        budget_cap_usd=5.00,
    )
    assert video.format == VideoFormat.long
    assert video.target_duration_s == 180

    # 2. Briefing Criativo da Direção
    brief = CreativeBrief(
        topic=video.topic,
        narrative_goal="Apresentar a evolução histórica da IA e seus impactos contemporâneos",
        hook="Em 1956, um grupo de cientistas se reuniu com um sonho ousado: ensinar máquinas a pensar.",
        content_structure=(
            "O Sonho de Dartmouth",
            "Os Primeiros Invernos da IA",
            "A Revolução do Aprendizado Profundo",
            "Redes Neurais e Big Data",
            "Modelos de Linguagem e Criatividade",
            "A Era da Autonomia",
        ),
        tone="Documental, analítico e envolvente",
        pacing="Balanceado com cortes a cada 3,5 a 5 segundos",
        visual_direction="Imagens contrastadas em 16:9, diagramas tecnológicos e iluminação cinematográfica",
        recommended_media_types=("image", "video"),
        caption_strategy="Destaque de palavra ativa em caixa discreta na base",
        audio_guidance="Trilha Sci-Fi ambiente com ducking suave sob a locução",
        max_budget_usd=5.00,
        quality_criteria=("Resolução 1080p sem distorção", "Sem mídias repetidas em cenas adjacentes"),
    )
    v_repo.update_video_creative_brief(video.id, brief.model_dump())

    # 3. Construção de 12 cenas com assets visuais e narração
    # 12 cenas x 15s = 180s (3 minutos)
    scenes_data = [
        ("Cena 1: A conferência de Dartmouth em 1956.", (25, 40, 80)),
        ("Cena 2: Os primeiros algoritmos simbólicos e testes lógicos.", (40, 30, 90)),
        ("Cena 3: O primeiro inverno da inteligência artificial.", (30, 50, 70)),
        ("Cena 4: Sistemas especialistas nos anos oitenta.", (50, 40, 60)),
        ("Cena 5: O segundo inverno e as limitações de hardware.", (35, 60, 65)),
        ("Cena 6: O renascimento das redes neurais convolucionais.", (70, 45, 55)),
        ("Cena 7: O avanço de ImageNet e o poder das GPUs.", (45, 75, 60)),
        ("Cena 8: Transformers e a atenção aos padrões de linguagem.", (30, 80, 80)),
        ("Cena 9: Modelos de linguagem de larga escala e difusão visual.", (80, 60, 35)),
        ("Cena 10: Aplicações práticas na medicina, clima e indústria.", (60, 80, 45)),
        ("Cena 11: Desafios éticos, alinhamento e consumo energético.", (90, 45, 30)),
        ("Cena 12: A fronteira da autonomia e o futuro da inteligência.", (40, 80, 95)),
    ]

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    asset_manifest = []
    descriptors = {}
    speech_wavs = []
    storyboard_scenes = []

    for idx, (narration_text, rgb) in enumerate(scenes_data):
        aid = f"asset_scene_{idx:02d}"
        img_path = assets_dir / f"{aid}.png"
        Image.new("RGB", (1920, 1080), color=rgb).save(img_path)
        img_sha = hashlib.sha256(img_path.read_bytes()).hexdigest()

        ref = AssetReference(
            asset_id=aid,
            asset_version=1,
            uri=str(img_path),
            content_sha256=img_sha,
            media_type="image",
            license="CC0",
        )
        asset_manifest.append(ref)
        descriptors[aid] = AssetDescriptor(
            asset_id=aid,
            asset_version=1,
            uri=str(img_path),
            content_sha256=img_sha,
            media_type="image",
            license="CC0",
            location=str(img_path),
            available=True,
            codec="png",
            width=1920,
            height=1080,
            byte_size=img_path.stat().st_size,
        )

        # Fala da cena: 14.2s -> com LEAD 0.3s + TAIL 0.5s = 15.0s por cena
        wav_path = audio_dir / f"speech_{idx:02d}.wav"
        _generate_tone_speech(wav_path, seconds=14.2)
        speech_wavs.append(wav_path)

        storyboard_scenes.append(StoryboardScene(
            scene_id=f"scene_{idx:02d}",
            asset_id=aid,
            narration=narration_text,
            speech_seconds=14.2,
            label=f"CENA {idx + 1}",
        ))

    # 4. Trilha musical CC0 com ducking automático
    music_file = Path("storage/music-candidates/29e51052.mp3")
    assert music_file.is_file(), "Trilha CC0 não encontrada em storage/music-candidates/"

    plan = build_render_plan(
        plan_id="plan:pilot-long",
        revision=1,
        project_id=project.id,
        video_id=video.id,
        format=VideoFormat.long,
        scenes=storyboard_scenes,
        assets=asset_manifest,
        timebase=Timebase(ticks_per_second=25),
        style_snapshot=StyleSnapshot(source="channel", style_id="default", version=1),
        pacing_preset=PacingPreset.balanced,
        music_params={"music_file": str(music_file)},
        audio_mix=AudioMix(
            music_gain=0.30,
            ducking_threshold=0.02,
            ducking_ratio=8.0,
            afade_in_s=0.5,
            afade_out_s=1.0,
            loudnorm_i=-16.0,
            loudnorm_tp=-1.5,
        ),
    )

    # Validações da timeline do RenderPlan v2
    assert plan.schema_version == 2
    assert plan.output.format == VideoFormat.long
    assert plan.output.width == 1920
    assert plan.output.height == 1080
    assert plan.timeline.ticks_per_second == 25
    # 12 cenas x 15s = 180s = 4500 ticks
    total_ticks = plan.timeline.duration_ticks
    assert total_ticks == 4500
    assert total_ticks / plan.timeline.ticks_per_second == 180.0

    # 5. Compilação e Renderização real via FFmpeg
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = tmp_path / "pilot_long_final.mp4"

    compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir=str(work_dir))
    assert len(compiled.shots) >= 36  # ~3 tomadas por cena x 12 cenas com preset balanced

    renderer = PlanFfmpegRenderer()
    rendered_path = renderer.execute(compiled, speech_wavs, out_mp4)
    assert rendered_path == out_mp4
    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 1_000_000  # Tamanho > 1MB

    # 6. Avaliação de Qualidade com QaReport v2
    narration_wav = Path(compiled.audio.narration.output)
    analyzer = FfmpegQa(timeout=300)
    metrics = analyzer.analyze(out_mp4, narration=narration_wav)

    assert metrics["has_audio"] is True
    assert metrics["width"] == 1920
    assert metrics["height"] == 1080
    assert metrics["video_codec"] in ("h264", "avc1")
    assert metrics["audio_codec"] == "aac"
    assert math.isclose(metrics["duration_s"], 180.0, abs_tol=2.0)
    assert metrics["true_peak_dbtp"] is not None
    assert metrics["true_peak_dbtp"] <= 0.0  # Sem clipping digital

    evaluator = FfmpegQualityEvaluator()
    qa_report = evaluator.evaluate(
        plan=plan,
        media_path=out_mp4,
        narration_path=narration_wav,
        descriptors=tuple(descriptors.values()),
        render_id="render_pilot_01",
        checksum=hashlib.sha256(out_mp4.read_bytes()).hexdigest(),
    )

    assert qa_report.coverage.status == "verified"
    assert len(qa_report.blocking_findings) == 0  # 0 bloqueios

    # 7. Amostragem visual de 6 frames do vídeo piloto
    frames_dir = tmp_path / "sampled_frames"
    sampled = sample_frames(out_mp4, frames_dir, count=6, expected_size=(1920, 1080))
    assert len(sampled) == 6
    for frame in sampled:
        assert frame["width"] == 1920
        assert frame["height"] == 1080
        assert frame["size_bytes"] > 5000
        assert Path(frame["path"]).is_file()

    # 8. Rastreabilidade de custos no usage_ledger por categoria
    u_repo.record(video.id, UsageEntry(
        step="briefing",
        provider="anthropic",
        model="claude-3-5-sonnet",
        cost_usd=0.085,
        category="llm",
        duration_ms=1800,
    ))
    u_repo.record(video.id, UsageEntry(
        step="script",
        provider="anthropic",
        model="claude-3-5-sonnet",
        cost_usd=0.145,
        category="llm",
        duration_ms=2500,
    ))
    u_repo.record(video.id, UsageEntry(
        step="speech",
        provider="piper",
        model="pt_BR-faber-medium",
        cost_usd=0.060,
        category="tts",
        duration_ms=8500,
    ))
    u_repo.record(video.id, UsageEntry(
        step="media_search",
        provider="pexels",
        model="v1",
        cost_usd=0.000,
        category="image",
        duration_ms=1200,
    ))
    u_repo.record(video.id, UsageEntry(
        step="render",
        provider="ffmpeg",
        model="h264_local",
        cost_usd=0.110,
        category="render",
        duration_ms=18500,
    ))

    total_spent = u_repo.spent_video(video.id)
    costs_by_cat = u_repo.spent_by_category(video.id)

    assert pytest.approx(total_spent, 0.001) == 0.400
    assert pytest.approx(costs_by_cat.get("llm", 0.0), 0.001) == 0.230
    assert pytest.approx(costs_by_cat.get("tts", 0.0), 0.001) == 0.060
    assert pytest.approx(costs_by_cat.get("image", 0.0), 0.001) == 0.000
    assert pytest.approx(costs_by_cat.get("render", 0.0), 0.001) == 0.110
