"""Testes da Renderização Audiovisual no FFmpeg (Onda 3 - Tarefa 6).

Cobre:
- Mixagem de áudio com filtro afade para encerramento musical suave (afade_out_s).
- Geração de trilha musical com arquivo real de música de storage/music-candidates via loop FFmpeg.
- Substituição de -c:v copy por queima de legendas ASS (-vf subtitles=...) quando subtitles_ass_path estiver presente.
- Materialização e escrita do arquivo de legendas ASS no disco durante execute().
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.render_plan_compiler import (
    _mix_filter,
    compile_render_plan,
)
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.domain.asset_resolver import AssetDescriptor
from app.studio.domain.contracts import VideoFormat
from app.studio.domain.render_plan import (
    AssetReference,
    AudioMix,
    RenderPlan,
    StyleSnapshot,
)
from app.studio.domain.render_plan_builder import (
    DEFAULT_TICKS_PER_SECOND,
    StoryboardScene,
    build_render_plan,
)

SHA_A = "a" * 64


def asset_ref(asset_id: str = "asset-01") -> AssetReference:
    return AssetReference(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/img/{asset_id}.png",
        content_sha256=SHA_A,
        media_type="image",
        license="Imagem de teste",
    )


def descriptor(asset_id: str = "asset-01") -> AssetDescriptor:
    return AssetDescriptor(
        asset_id=asset_id,
        asset_version=1,
        uri=f"storage/img/{asset_id}.png",
        content_sha256=SHA_A,
        media_type="image",
        location=f"/storage/{asset_id}.png",
        available=True,
        codec="png",
        width=1080,
        height=1920,
        license="Imagem de teste",
    )


def test_audio_mix_filter_includes_afade_out_when_configured():
    # AudioMix com afade_out_s de 0.5s e duração total de 4.0s
    custom_mix = AudioMix(
        music_gain=0.30,
        ducking_threshold=0.03,
        ducking_ratio=8.0,
        afade_out_s=0.50,
    )
    # Total de 4.0s: o fade deve iniciar em 3.50s e durar 0.50s
    mix_str = _mix_filter(custom_mix, total_s=4.0)
    assert "afade=t=out:st=3.50:d=0.50" in mix_str
    assert "[mus]" in mix_str
    # Verifica que afade está inserido no stream de música [mus]
    assert "volume=0.30,pan=stereo|c0=c0|c1=c0,afade=t=out:st=3.50:d=0.50[mus]" in mix_str


def test_audio_mix_filter_omits_afade_when_afade_out_zero():
    custom_mix = AudioMix(
        music_gain=0.30,
        afade_out_s=0.0,
    )
    mix_str = _mix_filter(custom_mix, total_s=4.0)
    assert "afade=t=out" not in mix_str
    assert "volume=0.30,pan=stereo|c0=c0|c1=c0[mus]" in mix_str


def test_compile_render_plan_computes_music_fade_out_from_timeline(tmp_path):
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Narração com encerramento musical suave.",
        speech_seconds=2.0,  # com LEAD 0.3 + TAIL 0.5 = 2.8s
    )
    custom_mix = AudioMix(
        music_gain=0.25,
        afade_out_s=0.60,
    )
    plan = build_render_plan(
        plan_id="plan-fade-check",
        revision=1,
        project_id="p-1",
        video_id="v-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        audio_mix=custom_mix,
    )
    work_dir = str(tmp_path / "job-fade")
    (tmp_path / "job-fade").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    total_s = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    expected_st = max(0.0, total_s - 0.60)
    expected_fade = f"afade=t=out:st={expected_st:.2f}:d=0.60"
    assert expected_fade in compiled.audio.filter_complex
    assert compiled.audio.filter_complex in compiled.audio.args


def test_audio_args_switches_to_subtitles_filter_when_subtitles_present(tmp_path):
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Legendas ASS queimadas no vídeo final.",
        speech_seconds=2.0,
    )
    plan = build_render_plan(
        plan_id="plan-sub-burn",
        revision=1,
        project_id="p-1",
        video_id="v-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
    )
    work_dir = str(tmp_path / "job-sub-burn")
    (tmp_path / "job-sub-burn").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    assert compiled.subtitles_ass_path is not None
    args = compiled.audio.args
    assert "-vf" in args
    vf_idx = args.index("-vf")
    escaped = compiled.subtitles_ass_path.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:")
    assert args[vf_idx + 1] == f"subtitles='{escaped}'"
    assert "-c:v" in args
    cv_idx = args.index("-c:v")
    assert args[cv_idx + 1] == "libx264"
    assert "-preset" in args
    preset_idx = args.index("-preset")
    assert args[preset_idx + 1] == "ultrafast"
    assert "-pix_fmt" in args
    pix_idx = args.index("-pix_fmt")
    assert args[pix_idx + 1] == "yuv420p"
    # Não deve ter o copy simples de vídeo
    assert ("-c:v", "copy") not in zip(args[:-1], args[1:])


def test_audio_args_keeps_copy_when_subtitles_absent(tmp_path):
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="",
        speech_seconds=2.0,
    )
    plan = build_render_plan(
        plan_id="plan-no-sub",
        revision=1,
        project_id="p-1",
        video_id="v-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
    )
    work_dir = str(tmp_path / "job-no-sub")
    (tmp_path / "job-no-sub").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    assert compiled.subtitles_ass_path is None
    args = compiled.audio.args
    assert "-vf" not in args
    assert ("-c:v", "copy") in zip(args[:-1], args[1:])


def test_write_music_with_music_file_creates_valid_wav(tmp_path):
    candidates = list(Path("storage/music-candidates").glob("*.mp3"))
    if not candidates:
        pytest.skip("Nenhum arquivo de música encontrado em storage/music-candidates")
    music_file = candidates[0].resolve()

    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Cena com trilha de arquivo real.",
        speech_seconds=2.0,
    )
    plan = build_render_plan(
        plan_id="plan-music-file",
        revision=1,
        project_id="p-1",
        video_id="v-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
        music_params={"music_file": str(music_file)},
    )
    work_dir = str(tmp_path / "job-music")
    (tmp_path / "job-music").mkdir(parents=True, exist_ok=True)

    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=work_dir,
    )

    renderer = PlanFfmpegRenderer()
    renderer._write_music(compiled)

    music_out = Path(compiled.audio.music_path)
    assert music_out.is_file()
    assert music_out.stat().st_size > 0

    with wave.open(str(music_out), "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 44100
        assert w.getnframes() > 0


def test_execute_writes_subtitles_ass_content_to_disk(tmp_path):
    scene = StoryboardScene(
        scene_id="scene-01",
        asset_id="asset-01",
        narration="Legenda para teste de escrita no execute.",
        speech_seconds=2.0,
    )
    plan = build_render_plan(
        plan_id="plan-exec-sub",
        revision=1,
        project_id="p-1",
        video_id="v-1",
        format=VideoFormat.short,
        scenes=[scene],
        assets=[asset_ref()],
    )
    work_dir = tmp_path / "job-exec-sub"
    compiled = compile_render_plan(
        plan=plan,
        assets={"asset-01": descriptor("asset-01")},
        work_dir=str(work_dir),
    )

    assert compiled.subtitles_ass_path is not None
    assert compiled.subtitles_ass_content is not None
    ass_path = Path(compiled.subtitles_ass_path)
    if ass_path.exists():
        ass_path.unlink()

    # Executa com um runner simulado para não rodar todo o pipeline de vídeo
    executed_cmds = []

    def mock_runner(cmd, timeout=600):
        executed_cmds.append(cmd)
        # se comando for gerar final.mp4 ou shot, cria o arquivo
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        if not out_file.exists():
            out_file.write_bytes(b"dummy mp4")

    # Cria speech_wav dummy
    speech_wav = tmp_path / "speech.wav"
    with wave.open(str(speech_wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 48000)

    renderer = PlanFfmpegRenderer(runner=mock_runner)
    out_mp4 = tmp_path / "out.mp4"
    renderer.execute(compiled, [speech_wav], out_mp4)

    assert ass_path.is_file()
    assert ass_path.read_text(encoding="utf-8") == compiled.subtitles_ass_content
