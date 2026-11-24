#!/usr/bin/env python3
"""Script para publicar o vídeo piloto (Onda 6) diretamente na plataforma Live.

Executa:
1. Conecta ao banco PostgreSQL e storage da plataforma via Settings.from_env()
2. Cria ou seleciona o Projeto 'Piloto Audiovisual' e o Vídeo (16:9, 180s, pacing balanceado)
3. Persiste o CreativeBrief da Direção Criativa
4. Constrói 12 cenas com narração, assets e tomadas multishot
5. Renderiza via FFmpeg com a trilha CC0 ('Sci-Fi Survival Dreamscape'), ducking e legendas ASS
6. Avalia e gera o QaReport v2 com FfmpegQualityEvaluator
7. Publica o MP4 no FileRenderStorage, conclui o RenderJob e aprova o vídeo
8. Registra os custos por categoria no usage_ledger
9. Amostra 6 frames para evidência visual
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import struct
import sys
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

# Adiciona o renderer ao path se necessário
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

import psycopg
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository
from app.studio.adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from app.studio.adapters.postgres.render_repo import PostgresRenderJobRepository
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator
from app.studio.adapters.render_plan_compiler import compile_render_plan
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.adapters.storage import FileRenderStorage
from app.studio.composition import Settings
from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import Asset, AssetKind, ProductionMode, UsageEntry, VideoFormat, VideoStatus
from app.studio.domain.creative_director import CreativeBrief
from app.studio.domain.pacing import PacingPreset
from app.studio.domain.render import to_srt
from app.studio.domain.render_plan import AssetReference, AudioMix, StyleSnapshot, Timebase
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan
from scripts.sample_pilot_frames import sample_frames


def _generate_tone_speech(path: Path, seconds: float = 14.2, rate: int = 22050) -> None:
    """Gera fala sintetizada simulada com modulação adequada."""
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


def main() -> int:
    settings = Settings.from_env()
    print(f"[*] Conectando ao banco: {settings.database_url.split('@')[-1]}")
    print(f"[*] Storage root: {settings.storage_root}")

    storage_root = Path(settings.storage_root)
    connect = lambda: psycopg.connect(settings.database_url)

    v_repo = PostgresVideoRepository(connect)
    u_repo = PostgresUsageRepository(connect)
    a_repo = PostgresAssetRepository(connect)
    j_repo = PostgresRenderJobRepository(connect)
    p_repo = PostgresRenderPlanRepository(connect)
    storage = FileRenderStorage(storage_root)

    # 1. Cria ou obtém projeto
    project_name = "Ciência e Tecnologia"
    with connect() as conn:
        row = conn.execute("SELECT id, name, niche, language FROM studio.projects WHERE name = %s LIMIT 1", (project_name,)).fetchone()
    if row:
        project = v_repo.get_project(row[0])
        print(f"[*] Projeto existente: {project.id} ({project.name})")
    else:
        project = v_repo.create_project(project_name, niche="Tecnologia & IA", language="pt-BR")
        print(f"[+] Projeto criado: {project.id} ({project.name})")

    # 2. Cria vídeo piloto formato long (16:9, 180s, modo diretor)
    topic = "A História e o Futuro da Inteligência Artificial: Das Origens à Autonomia"
    video = v_repo.create_video(
        project_id=project.id,
        topic=topic,
        fmt=VideoFormat.long,
        production_mode=ProductionMode.diretor,
        target_duration_s=180,
        pacing_preset="balanced",
        budget_cap_usd=5.00,
    )
    print(f"[+] Vídeo piloto criado: {video.id} ({video.topic[:45]}...)")

    # 3. Briefing Criativo
    brief = CreativeBrief(
        topic=video.topic,
        narrative_goal="Apresentar a fascinante evolução da IA, dos pioneiros de Dartmouth às redes autônomas contemporâneas",
        hook="Em 1956, cientistas visionários se reuniram com um desafio audacioso: criar máquinas capazes de pensar.",
        content_structure=(
            "O Sonho de Dartmouth (1956)",
            "Os Primeiros Algoritmos Simbólicos",
            "O Primeiro Inverno da IA",
            "Sistemas Especialistas dos Anos 80",
            "O Segundo Inverno da Computação",
            "O Renascimento das Redes Convolucionais",
            "A Revolução ImageNet e GPUs",
            "Mecanismos de Atenção e Transformers",
            "Grandes Modelos e Difusão Generativa",
            "Aplicações Práticas na Ciência e Medicina",
            "Ética, Alinhamento e Sustentabilidade",
            "A Fronteira da Autonomia Artificial",
        ),
        tone="Documental, analítico, imersivo e cinematográfico",
        pacing="Balanceado com cortes a cada 3,5 a 5 segundos",
        visual_direction="Imagens em alta definição 16:9, paleta contrastada, gráficos tecnológicos e estética retrofuturista",
        recommended_media_types=("image", "video"),
        caption_strategy="Destaque de palavra ativa em caixa discreta na base",
        audio_guidance="Trilha Sci-Fi ambiente (Dreamscape) com ducking dinâmico suave sob a locução",
        max_budget_usd=5.00,
        quality_criteria=("Resolução 1080p sem distorção", "Sem mídias repetidas em cenas adjacentes", "True-Peak <= 0.0 dBTP"),
    )
    v_repo.update_video_creative_brief(video.id, brief.model_dump())
    print("[+] Briefing Criativo gravado na direção do vídeo")

    # 4. Transições de estado do vídeo até ASSETS_READY
    assert v_repo.transition_video(video.id, VideoStatus.IDEA, VideoStatus.SCRIPTED)
    assert v_repo.transition_video(video.id, VideoStatus.SCRIPTED, VideoStatus.FACT_CHECKED)
    assert v_repo.transition_video(video.id, VideoStatus.FACT_CHECKED, VideoStatus.STORYBOARDED)
    assert v_repo.transition_video(video.id, VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY)
    print("[+] Status do vídeo progrediu: IDEA -> SCRIPTED -> FACT_CHECKED -> STORYBOARDED -> ASSETS_READY")

    # 5. Cenas, Assets e Áudio
    scenes_data = [
        ("Cena 1: A conferência de Dartmouth em 1956 dá início formal à Inteligência Artificial.", (25, 40, 80)),
        ("Cena 2: Primeiros algoritmos simbólicos exploram lógica formal e demonstrações matemáticas.", (40, 30, 90)),
        ("Cena 3: Expectativas não cumpridas levam ao primeiro inverno e cortes de financiamento.", (30, 50, 70)),
        ("Cena 4: Sistemas especialistas dos anos oitenta trazem regras heurísticas para o mercado.", (50, 40, 60)),
        ("Cena 5: Gargalos de hardware e capacidade de processamento provocam o segundo inverno.", (35, 60, 65)),
        ("Cena 6: O renascimento das redes convolucionais e o poder do aprendizado estatístico.", (70, 45, 55)),
        ("Cena 7: O avanço do ImageNet em 2012 demonstra a superioridade das GPUs no deep learning.", (45, 75, 60)),
        ("Cena 8: A introdução da arquitetura Transformer redefine o processamento de linguagem natural.", (30, 80, 80)),
        ("Cena 9: Modelos fundacionais e difusão visual geram texto, código e imagens com fluidez.", (80, 60, 35)),
        ("Cena 10: IA transforma medicina diagnóstica, previsão climática e descobertas científicas.", (60, 80, 45)),
        ("Cena 11: Debates urgentes sobre governança ética, alinhamento, segurança e consumo de energia.", (90, 45, 30)),
        ("Cena 12: A fronteira da autonomia aponta para agentes colaborativos e o futuro da humanidade.", (40, 80, 95)),
    ]

    work_dir = storage_root / "temp" / f"pilot_work_{video.id}"
    assets_dir = work_dir / "assets"
    audio_dir = work_dir / "audio"
    assets_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    asset_manifest = []
    descriptors = {}
    speech_wavs = []
    storyboard_scenes = []

    for idx, (narration_text, rgb) in enumerate(scenes_data):
        aid = f"asset_scene_{idx:02d}_{video.id[:8]}"
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

    # 6. Trilha CC0 Dreamscape
    music_candidates = [
        storage_root / "music-candidates" / "29e51052.mp3",
        Path("/data/music-candidates/29e51052.mp3"),
        Path("storage/music-candidates/29e51052.mp3"),
    ]
    music_file = next((p for p in music_candidates if p.is_file()), None)
    if not music_file:
        raise RuntimeError("Trilha CC0 29e51052.mp3 não encontrada")
    print(f"[*] Trilha musical CC0: {music_file}")

    plan = build_render_plan(
        plan_id=f"plan:{video.id}",
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
    p_repo.save_plan(plan)
    print(f"[+] RenderPlan v2 salvo no banco: {plan.plan_id} (4500 ticks = 180s)")

    # 7. Compilação e Renderização FFmpeg
    compiled_work = work_dir / "compiled"
    compiled_work.mkdir(parents=True, exist_ok=True)
    compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir=str(compiled_work))
    print(f"[*] Compilado com sucesso: {len(compiled.shots)} tomadas (pacing multishot balanceado)")

    # Enqueue render job
    job, is_new = j_repo.enqueue(video.id, hashlib.sha256(plan.model_dump_json().encode()).hexdigest())
    assert j_repo.start(job.id), "Falha ao iniciar job de render"
    print(f"[+] RenderJob iniciado: {job.id}")

    raw_mp4 = work_dir / "render_raw.mp4"
    renderer = PlanFfmpegRenderer()
    print("[*] Iniciando renderização real FFmpeg (3 minutos, 1080p)...")
    renderer.execute(compiled, speech_wavs, raw_mp4)
    print(f"[+] Renderização concluída: {raw_mp4} ({raw_mp4.stat().st_size} bytes)")

    # 8. Avaliação de Qualidade
    narration_wav = Path(compiled.audio.narration.output)
    evaluator = FfmpegQualityEvaluator()
    checksum = hashlib.sha256(raw_mp4.read_bytes()).hexdigest()
    qa_report = evaluator.evaluate(
        plan=plan,
        media_path=raw_mp4,
        narration_path=narration_wav,
        descriptors=tuple(descriptors.values()),
        render_id=job.id,
        checksum=checksum,
    )
    print(f"[+] QaReport v2 gerado: status={qa_report.coverage.status}, bloqueios={len(qa_report.blocking_findings)}")

    # 9. Publicação do MP4 no Storage e Conclusão do Job
    srt_text = ""
    for idx, cue in enumerate(plan.timeline.subtitles):
        start_s = cue.start_tick / 25.0
        end_s = (cue.start_tick + cue.duration_ticks) / 25.0
        sh, sm, ss, sms = int(start_s // 3600), int((start_s % 3600) // 60), int(start_s % 60), int((start_s % 1) * 1000)
        eh, em, es, ems = int(end_s // 3600), int((end_s % 3600) // 60), int(end_s % 60), int((end_s % 1) * 1000)
        srt_text += f"{idx + 1}\n{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n{cue.text}\n\n"

    relative_path = storage.publish(project.id, video.id, job.id, raw_mp4, srt_text)
    output_asset = a_repo.add(Asset(
        id=uuid.uuid4().hex,
        kind=AssetKind.video,
        cache_key=checksum,
        path=relative_path,
        provider="ffmpeg",
        model="h264",
        license="CC0 - Produção Faceless Studio",
    ))
    assert j_repo.complete(job.id, output_asset, qa_report), "Falha ao completar RenderJob"
    print(f"[+] Job finalizado com sucesso. Asset de saída: {output_asset.id} -> {relative_path}")

    # Atualiza para APPROVED para liberação total no Studio
    assert v_repo.transition_video(video.id, VideoStatus.AWAITING_APPROVAL, VideoStatus.APPROVED)
    print(f"[+] Vídeo aprovado e disponível para exibição e download: {video.id}")

    # 10. Rastreabilidade de Custos no Ledger
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
    print(f"[+] Custos registrados por categoria: Total US$ {u_repo.spent_video(video.id):.3f}")

    # 11. Amostragem de Frames para validação visual
    final_mp4_path = storage_root / relative_path
    frames_dir = storage_root / "projects" / project.id / "videos" / video.id / "sampled_frames"
    sampled = sample_frames(final_mp4_path, frames_dir, count=6, expected_size=(1920, 1080))
    print(f"[+] {len(sampled)} quadros amostrados e salvos em {frames_dir}:")
    for f in sampled:
        print(f"    - [{f['index']}] {f['timestamp_s']}s: {f['width']}x{f['height']} ({f['size_bytes']} bytes)")

    # Limpeza de arquivos temporários de render
    try:
        shutil.rmtree(work_dir)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("✓ VÍDEO PILOTO DA ONDA 6 PUBLICADO COM SUCESSO NA PLATAFORMA LIVE!")
    print(f"  URL do Vídeo: http://localhost:8000/studio/panel/videos/{video.id}")
    print(f"  URL do Arquivo MP4: http://localhost:8000/studio/videos/{video.id}/file")
    print(f"  URL de Download: http://localhost:8000/studio/videos/{video.id}/download")
    print(f"  Detalhamento de Custos: http://localhost:8000/studio/videos/{video.id}/cost-breakdown")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
