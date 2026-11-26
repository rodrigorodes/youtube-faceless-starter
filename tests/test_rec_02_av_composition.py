"""Testes de recuperação REC-02.01 e REC-02.02 — Composição Audiovisual e Multitrack Real.

Prova comportamento observável em container FFmpeg 7.1.5 + ffprobe + Pillow (zero mocks):
- REC-02.01:
  - Transições reais inter-segmento via ``xfade`` (crossfade, slide_left, wipe_left) sem fade-to-black.
  - Rejeição explícita (``CompileError``) para duração >= shot adjacente ou transição inválida.
  - Overlays de vídeo (PiP) + múltiplos overlays com limites finitos de opacidade/escala/posição.
  - Invalidação determinística de digest/fingerprint ao alterar overlay, PiP ou transição.
- REC-02.02:
  - Remoção do alias enganoso ``true_peak_dbtp`` em ``audio_dsp.mix_multitrack_pcm``.
  - Mixagem multitrack canônica (voz + 2 músicas + ambiência + SFX + fades + ducking + licença)
    medida com EBU R128 real via ``FfmpegQa`` (``true_peak_dbtp <= -1.0``, LUFS, duração).
  - Efeitos de movimento (``motion_effects`` / Ken Burns) com deslocamento observável de pixels.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from app.studio.adapters.qa_ffmpeg import FfmpegQa
from app.studio.adapters.render_plan_compiler import _fade_filter, compile_render_plan
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from app.studio.application.ports import OverlayLayer, RenderSpec
from app.studio.application.render_compiler import CompileError, structure_render_plan
from app.studio.domain.audio_catalog import AudioCatalog, AudioCategory, AudioTrack
from app.studio.domain.audio_dsp import generate_synthetic_sfx, generate_synthetic_tone, mix_multitrack_pcm, save_pcm_as_wav
from app.studio.domain.audio_multitrack import AudioEvent, MultitrackAudioPlan, build_multitrack_plan
from app.studio.domain.contracts import Scene as StoryboardRow, VideoFormat
from app.studio.domain.render import LEAD, TAIL
from app.studio.domain.render_plan import (
    AssetReference,
    Composition,
    Effects,
    GeneratedAudioSource,
    NarrationCue,
    Output,
    Provenance,
    RenderPlan,
    Scene as PlanScene,
    Shot,
    StyleSnapshot,
    Timebase,
    Timeline,
    Track,
    Transition,
)
from app.studio.domain.render_cache import NodeId, plan_graph, selective_invalidation
from app.studio.domain.render_plan_builder import DEFAULT_TICKS_PER_SECOND, StoryboardScene, build_render_plan
from app.studio.domain.asset_resolver import AssetDescriptor

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

TPS = DEFAULT_TICKS_PER_SECOND  # 25000 ticks/s (25 fps)


def _solid_png(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (320, 240)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(path)
    return path


def _grid_png(path: Path, size: tuple[int, int] = (640, 360)) -> Path:
    img = Image.new("RGB", size, (20, 30, 50))
    draw = ImageDraw.Draw(img)
    for x in range(0, size[0], 40):
        draw.line([(x, 0), (x, size[1])], fill=(220, 220, 220), width=3)
    for y in range(0, size[1], 40):
        draw.line([(0, y), (size[0], y)], fill=(220, 180, 60), width=3)
    img.save(path)
    return path


def _silence_wav(path: Path, seconds: float, rate: int = 24000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(round(seconds * rate)))
    return path


def _sample_frame(mp4_path: Path, time_s: float, out_png: Path) -> Image.Image:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{time_s:.3f}", "-i", str(mp4_path),
            "-frames:v", "1", str(out_png),
        ],
        check=True,
        timeout=30,
    )
    with Image.open(out_png) as img:
        return img.convert("RGB")


def _make_moving_pip_mp4(path: Path, size: tuple[int, int] = (160, 120)) -> Path:
    """Gera um MP4 real de 2.4s: [0..1.2s] verde puro (0,255,0), [1.2..2.4s] amarelo puro (255,255,0)."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=0x00FF00:s={size[0]}x{size[1]}:r=25:d=1.2",
            "-f", "lavfi", "-i", f"color=c=0xFFFF00:s={size[0]}x{size[1]}:r=25:d=1.2",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        timeout=30,
    )
    return path


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _two_color_plan(tmp_path: Path, transition: Transition) -> tuple[RenderPlan, dict[str, AssetDescriptor], list[Path]]:
    red_png = _solid_png(tmp_path / "red.png", (255, 0, 0), size=(320, 240))
    blue_png = _solid_png(tmp_path / "blue.png", (0, 0, 255), size=(320, 240))
    wav1 = _silence_wav(tmp_path / "s1.wav", 1.5)
    wav2 = _silence_wav(tmp_path / "s2.wav", 1.5)

    dur = 2 * TPS  # 2.0s each -> 4.0s total
    assets = [
        AssetReference(asset_id="a-red", asset_version=1, uri=str(red_png), content_sha256=_sha256(red_png), media_type="image", license="cc0"),
        AssetReference(asset_id="a-blue", asset_version=1, uri=str(blue_png), content_sha256=_sha256(blue_png), media_type="image", license="cc0"),
    ]
    descriptors = {
        "a-red": AssetDescriptor(asset_id="a-red", asset_version=1, uri=str(red_png), content_sha256=_sha256(red_png), media_type="image", license="cc0", location=str(red_png), available=True, codec="png", width=320, height=240, byte_size=red_png.stat().st_size),
        "a-blue": AssetDescriptor(asset_id="a-blue", asset_version=1, uri=str(blue_png), content_sha256=_sha256(blue_png), media_type="image", license="cc0", location=str(blue_png), available=True, codec="png", width=320, height=240, byte_size=blue_png.stat().st_size),
    }
    plan = RenderPlan(
        schema_version=2,
        plan_id="plan:rec02-trans",
        revision=1,
        project_id="proj-1",
        video_id="vid-1",
        output=Output(format=VideoFormat.long, width=1920, height=1080, disclosure="Teste"),
        timeline=Timeline(
            timebase=Timebase(ticks_per_second=TPS),
            tracks=[Track(track_id="v1", kind="visual"), Track(track_id="n1", kind="narration")],
            scenes=[
                PlanScene(
                    scene_id="sc-1",
                    start_tick=0,
                    duration_ticks=dur,
                    shots=[Shot(shot_id="sh-1", track_id="v1", start_tick=0, duration_ticks=dur, asset_ref="a-red", transition=transition)],
                ),
                PlanScene(
                    scene_id="sc-2",
                    start_tick=dur,
                    duration_ticks=dur,
                    shots=[Shot(shot_id="sh-2", track_id="v1", start_tick=dur, duration_ticks=dur, asset_ref="a-blue")],
                ),
            ],
            narration=[
                NarrationCue(scene_id="sc-1", track_id="n1", source_ref="v-1", start_tick=0, duration_ticks=dur),
                NarrationCue(scene_id="sc-2", track_id="n1", source_ref="v-2", start_tick=dur, duration_ticks=dur),
            ],
        ),
        asset_manifest=assets,
        generated_audio=[
            GeneratedAudioSource(source_id="v-1", kind="voice", duration_ticks=dur),
            GeneratedAudioSource(source_id="v-2", kind="voice", duration_ticks=dur),
            GeneratedAudioSource(source_id="music", kind="music", duration_ticks=2 * dur, silent=True),
        ],
        style_snapshot=StyleSnapshot(style_id="default", version=1),
        provenance=Provenance(builder_version="test/1"),
    )
    return plan, descriptors, [wav1, wav2]


# --------------------------------------------------------------------------- REC-02.01: Transitions


def test_rec02_fade_filter_does_not_fake_crossfade_as_fade_to_black():
    trans = Transition(kind="crossfade", duration_ticks=12500)
    flt = _fade_filter(trans, seconds=2.0, tps=TPS, shot_id="sh-1")
    assert "fade=t=in" not in flt
    assert "fade=t=out" not in flt


@needs_ffmpeg
def test_rec02_crossfade_real_xfade_blends_red_and_blue_without_black(tmp_path):
    plan, descriptors, wavs = _two_color_plan(tmp_path, Transition(kind="crossfade", duration_ticks=12500))  # 0.5s
    work = tmp_path / "work"
    work.mkdir()
    compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir=str(work))
    out_mp4 = tmp_path / "out_crossfade.mp4"
    renderer = PlanFfmpegRenderer()
    renderer.execute(compiled, wavs, out_mp4)

    qa = FfmpegQa().analyze(out_mp4)
    assert qa["has_audio"] is True
    assert abs(qa["duration_s"] - 4.0) <= 0.12

    f_start = _sample_frame(out_mp4, 0.5, tmp_path / "f_start.png").getpixel((960, 540))
    f_mid = _sample_frame(out_mp4, 2.0, tmp_path / "f_mid.png").getpixel((960, 540))
    f_end = _sample_frame(out_mp4, 3.5, tmp_path / "f_end.png").getpixel((960, 540))

    assert f_start[0] > 200 and f_start[2] < 40, f"expected red at t=0.5s, got {f_start}"
    assert f_end[2] > 200 and f_end[0] < 40, f"expected blue at t=3.5s, got {f_end}"
    # Midpoint must be blended purple (both R and B significant, NOT black (0,0,0)!)
    assert f_mid[0] > 70 and f_mid[2] > 70, f"expected blended red+blue at t=2.0s, got {f_mid}"


@needs_ffmpeg
@pytest.mark.parametrize("kind", ["slide_left", "wipe_left"])
def test_rec02_slide_and_wipe_produce_spatial_transition_pixels(tmp_path, kind):
    plan, descriptors, wavs = _two_color_plan(tmp_path, Transition(kind=kind, duration_ticks=12500))
    work = tmp_path / "work"
    work.mkdir()
    compiled = compile_render_plan(plan=plan, assets=descriptors, work_dir=str(work))
    out_mp4 = tmp_path / f"out_{kind}.mp4"
    PlanFfmpegRenderer().execute(compiled, wavs, out_mp4)

    qa = FfmpegQa().analyze(out_mp4)
    assert abs(qa["duration_s"] - 4.0) <= 0.12

    mid_img = _sample_frame(out_mp4, 2.0, tmp_path / f"mid_{kind}.png")
    left_px = mid_img.getpixel((200, 540))
    right_px = mid_img.getpixel((1720, 540))
    # One side is red-dominant and the other is blue-dominant at the 50% spatial boundary
    assert (left_px[0] > 180 and right_px[2] > 180) or (left_px[2] > 180 and right_px[0] > 180), (
        f"{kind} midpoint should split red and blue spatially, got left={left_px}, right={right_px}"
    )


def test_rec02_transition_edge_cases_fail_closed_with_compile_error(tmp_path):
    # 1. Transition duration >= adjacent shot duration
    plan, descriptors, _ = _two_color_plan(tmp_path, Transition(kind="crossfade", duration_ticks=2 * TPS))
    with pytest.raises(CompileError):
        compile_render_plan(plan=plan, assets=descriptors, work_dir=str(tmp_path / "w1"))

    # 2. Inter-shot transition on last shot (no following shot)
    plan_last, descriptors, _ = _two_color_plan(tmp_path, Transition(kind="none"))
    bad_scene2 = plan_last.timeline.scenes[1].model_copy(
        update={"shots": [plan_last.timeline.scenes[1].shots[0].model_copy(update={"transition": Transition(kind="crossfade", duration_ticks=5000)})]}
    )
    plan_last = plan_last.model_copy(update={"timeline": plan_last.timeline.model_copy(update={"scenes": [plan_last.timeline.scenes[0], bad_scene2]})})
    with pytest.raises(CompileError):
        compile_render_plan(plan=plan_last, assets=descriptors, work_dir=str(tmp_path / "w2"))

    # 3. Unsupported transition kind via model_construct
    bad_trans = Transition.model_construct(kind="star_wipe", duration_ticks=5000)
    bad_scene1 = plan_last.timeline.scenes[0].model_copy(
        update={"shots": [plan_last.timeline.scenes[0].shots[0].model_copy(update={"transition": bad_trans})]}
    )
    plan_bad = plan_last.model_copy(update={"timeline": plan_last.timeline.model_copy(update={"scenes": [bad_scene1, plan_last.timeline.scenes[1]]})})
    with pytest.raises(CompileError):
        compile_render_plan(plan=plan_bad, assets=descriptors, work_dir=str(tmp_path / "w3"))


# --------------------------------------------------------------------------- REC-02.01: Video PiP & Bounds


@pytest.mark.parametrize("kwargs", [
    {"opacity": -0.1},
    {"opacity": 1.1},
    {"opacity": float("nan")},
    {"opacity": float("inf")},
    {"scale": 0.0},
    {"scale": -1.0},
    {"scale": 4.1},
    {"scale": float("nan")},
    {"position_x": -0.01},
    {"position_x": 1.01},
    {"position_y": float("nan")},
    {"position_y": 1.5},
])
def test_rec02_composition_rejects_invalid_and_non_finite_bounds(kwargs):
    with pytest.raises((ValidationError, ValueError)):
        Composition(**kwargs)


def test_rec02_overlay_accepts_video_and_rejects_text_or_audio(tmp_path):
    bg = _solid_png(tmp_path / "bg.png", (10, 20, 80))
    pip = _make_moving_pip_mp4(tmp_path / "pip.mp4")

    for bad_type in ("text", "audio"):
        ref_bg = AssetReference(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0")
        ref_bad = AssetReference.model_construct(
            asset_id="ov", asset_version=1, uri=str(bg), content_sha256=_sha256(bg),
            media_type=bad_type, license="cc0", attribution="", source_url="", metadata={},
        )
        plan = RenderPlan.model_construct(
            schema_version=2,
            plan_id="p1",
            revision=1,
            project_id="proj",
            video_id="vid",
            output=Output(format=VideoFormat.long, width=1920, height=1080, disclosure="Teste"),
            timeline=Timeline(
                timebase=Timebase(ticks_per_second=TPS),
                tracks=[Track(track_id="v1", kind="visual"), Track(track_id="v2", kind="visual"), Track(track_id="n1", kind="narration")],
                scenes=[PlanScene(
                    scene_id="s1", start_tick=0, duration_ticks=2 * TPS,
                    shots=[
                        Shot(shot_id="sh1", track_id="v1", start_tick=0, duration_ticks=2 * TPS, asset_ref="bg"),
                        Shot(shot_id="ov1", track_id="v2", start_tick=0, duration_ticks=TPS, asset_ref="ov", role="overlay", z_index=1),
                    ],
                )],
                narration=[NarrationCue(scene_id="s1", track_id="n1", source_ref="v1", start_tick=0, duration_ticks=2 * TPS)],
            ),
            asset_manifest=[ref_bg, ref_bad],
            generated_audio=[
                GeneratedAudioSource(source_id="v1", kind="voice", duration_ticks=2 * TPS),
                GeneratedAudioSource(source_id="music", kind="music", duration_ticks=2 * TPS, silent=True),
            ],
            style_snapshot=StyleSnapshot(style_id="default", version=1),
            provenance=Provenance(builder_version="test/1"),
        )
        descs = {
            "bg": AssetDescriptor(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0", location=str(bg), available=True, codec="png", width=320, height=240, byte_size=bg.stat().st_size),
            "ov": AssetDescriptor.model_construct(asset_id="ov", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type=bad_type, license="cc0", location="", available=True, codec=None, width=None, height=None, byte_size=bg.stat().st_size),
        }
        with pytest.raises(CompileError):
            structure_render_plan(plan=plan, assets=descs, work_dir=str(tmp_path / f"w_{bad_type}"))

    # Video PiP must succeed
    ref_bg = AssetReference(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0")
    ref_pip = AssetReference(asset_id="pip", asset_version=1, uri=str(pip), content_sha256=_sha256(pip), media_type="video", license="cc0")
    plan_ok = RenderPlan(
        schema_version=2,
        plan_id="p-ok",
        revision=1,
        project_id="proj",
        video_id="vid",
        output=Output(format=VideoFormat.long, width=1920, height=1080, disclosure="Teste"),
        timeline=Timeline(
            timebase=Timebase(ticks_per_second=TPS),
            tracks=[Track(track_id="v1", kind="visual"), Track(track_id="v2", kind="visual"), Track(track_id="n1", kind="narration")],
            scenes=[PlanScene(
                scene_id="s1", start_tick=0, duration_ticks=2 * TPS,
                shots=[
                    Shot(shot_id="sh1", track_id="v1", start_tick=0, duration_ticks=2 * TPS, asset_ref="bg"),
                    Shot(shot_id="ov1", track_id="v2", start_tick=0, duration_ticks=TPS, asset_ref="pip", role="overlay", z_index=1),
                ],
            )],
            narration=[NarrationCue(scene_id="s1", track_id="n1", source_ref="v1", start_tick=0, duration_ticks=2 * TPS)],
        ),
        asset_manifest=[ref_bg, ref_pip],
        generated_audio=[
            GeneratedAudioSource(source_id="v1", kind="voice", duration_ticks=2 * TPS),
            GeneratedAudioSource(source_id="music", kind="music", duration_ticks=2 * TPS, silent=True),
        ],
        style_snapshot=StyleSnapshot(style_id="default", version=1),
        provenance=Provenance(builder_version="test/1"),
    )
    descs_ok = {
        "bg": AssetDescriptor(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0", location=str(bg), available=True, codec="png", width=320, height=240, byte_size=bg.stat().st_size),
        "pip": AssetDescriptor(asset_id="pip", asset_version=1, uri=str(pip), content_sha256=_sha256(pip), media_type="video", license="cc0", location=str(pip), available=True, codec="h264", width=160, height=120, duration_ticks=2 * TPS, byte_size=pip.stat().st_size),
    }
    structure = structure_render_plan(plan=plan_ok, assets=descs_ok, work_dir=str(tmp_path / "w_ok"))
    assert structure.shots[0].overlays[0].media_type == "video"


@needs_ffmpeg
def test_rec02_video_pip_and_multi_overlay_render_and_pixel_sampling(tmp_path):
    # Use RenderSpec + PlanFfmpegRenderer.render() to prove OverlayLayer transform propagation
    bg = _solid_png(tmp_path / "bg.png", (10, 20, 120), size=(1920, 1080))
    pip = _make_moving_pip_mp4(tmp_path / "pip.mp4", size=(320, 180))
    cyan = _solid_png(tmp_path / "cyan.png", (0, 255, 255), size=(320, 180))
    speech = save_pcm_as_wav(generate_synthetic_tone(2.2, freq_hz=200.0, gain_db=-35.0), tmp_path / "speech.wav")

    row = StoryboardRow(id="sc-1", video_id="vid-pip", idx=0, narration="Cena com PiP e overlay.", image_prompt="Fundo azul escuro sólido.", asset_id="a-bg", label="")
    layers = (
        OverlayLayer(
            scene_id="sc-1", asset_id="a-pip", image=pip, license="cc0",
            start_s=0.2, duration_s=2.4, z_index=1, fit="contain",
            opacity=1.0, scale=0.35, position_x=1.0, position_y=0.0,
        ),
        OverlayLayer(
            scene_id="sc-1", asset_id="a-cyan", image=cyan, license="cc0",
            start_s=0.0, duration_s=2.8, z_index=2, fit="contain",
            opacity=0.6, scale=0.25, position_x=0.0, position_y=1.0,
        ),
    )
    work = tmp_path / "work"
    work.mkdir()
    spec = RenderSpec(
        scenes=[row],
        images=[bg],
        speech_wavs=[speech],
        scene_seconds=[3.0],
        cues=[],
        format=VideoFormat.long,
        music=False,
        disclosure="Teste",
        work_dir=work,
        layers=layers,
    )
    out_mp4 = tmp_path / "pip_out.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec, out_mp4)

    img_early = _sample_frame(out_mp4, 0.7, tmp_path / "pip_early.png")
    img_late = _sample_frame(out_mp4, 2.0, tmp_path / "pip_late.png")

    # Top-right PiP quadrant: x ~ 1920 - 336 = 1584, y ~ 189
    pip_early_px = img_early.getpixel((1700, 180))
    pip_late_px = img_late.getpixel((1700, 180))
    assert pip_early_px[1] > 180 and pip_early_px[0] < 60, f"expected green PiP at t=0.7s, got {pip_early_px}"
    assert pip_late_px[0] > 180 and pip_late_px[1] > 180, f"expected yellow PiP at t=2.0s, got {pip_late_px}"

    # Bottom-left alpha-blended cyan overlay: x ~ 240, y ~ 945
    cyan_px = img_early.getpixel((240, 945))
    assert cyan_px[1] > 100 and cyan_px[2] > 120, f"expected blended cyan at bottom-left, got {cyan_px}"

    # Background center stays dark navy
    bg_px = img_early.getpixel((960, 540))
    assert bg_px[0] < 40 and bg_px[1] < 45 and bg_px[2] > 80, f"expected intact navy background, got {bg_px}"


def test_rec02_cache_fingerprint_changes_on_transform_and_transition(tmp_path):
    plan1, descs, _ = _two_color_plan(tmp_path, Transition(kind="crossfade", duration_ticks=12500))
    d1 = compile_render_plan(plan=plan1, assets=descs, work_dir=str(tmp_path / "w1")).digest()

    plan2, _, _ = _two_color_plan(tmp_path, Transition(kind="slide_left", duration_ticks=12500))
    d2 = compile_render_plan(plan=plan2, assets=descs, work_dir=str(tmp_path / "w1")).digest()
    assert d1 != d2

    # P1-1: plan_graph + selective_invalidation also invalidate on transition, overlay transform, and PiP offset
    g1 = plan_graph(plan1)
    g2 = plan_graph(plan2)
    inv_trans = selective_invalidation(g1, g2)
    assert NodeId("visual", "sh-1") in inv_trans.invalidated
    assert NodeId("concat", "video") in inv_trans.invalidated

    bg = _solid_png(tmp_path / "bg_fp.png", (10, 20, 80))
    pip = _make_moving_pip_mp4(tmp_path / "pip_fp.mp4")
    ref_bg = AssetReference(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0")
    ref_pip = AssetReference(asset_id="pip", asset_version=1, uri=str(pip), content_sha256=_sha256(pip), media_type="video", license="cc0")
    descs_ov = {
        "bg": AssetDescriptor(asset_id="bg", asset_version=1, uri=str(bg), content_sha256=_sha256(bg), media_type="image", license="cc0", location=str(bg), available=True, codec="png", width=320, height=240, byte_size=bg.stat().st_size),
        "pip": AssetDescriptor(asset_id="pip", asset_version=1, uri=str(pip), content_sha256=_sha256(pip), media_type="video", license="cc0", location=str(pip), available=True, codec="h264", width=160, height=120, duration_ticks=2 * TPS, byte_size=pip.stat().st_size),
    }

    def _ov_plan(opacity: float, offset_ticks: int) -> RenderPlan:
        return RenderPlan(
            schema_version=2,
            plan_id="p-fp",
            revision=1,
            project_id="proj",
            video_id="vid",
            output=Output(format=VideoFormat.long, width=1920, height=1080, disclosure="Teste"),
            timeline=Timeline(
                timebase=Timebase(ticks_per_second=TPS),
                tracks=[Track(track_id="v1", kind="visual"), Track(track_id="v2", kind="visual"), Track(track_id="n1", kind="narration")],
                scenes=[PlanScene(
                    scene_id="s1", start_tick=0, duration_ticks=2 * TPS,
                    shots=[
                        Shot(shot_id="sh1", track_id="v1", start_tick=0, duration_ticks=2 * TPS, asset_ref="bg"),
                        Shot(
                            shot_id="ov1", track_id="v2", start_tick=0, duration_ticks=TPS,
                            asset_ref="pip", role="overlay", z_index=1, asset_offset_ticks=offset_ticks,
                            composition=Composition(fit="contain", opacity=opacity, scale=0.4, position_x=0.8, position_y=0.2),
                        ),
                    ],
                )],
                narration=[NarrationCue(scene_id="s1", track_id="n1", source_ref="v1", start_tick=0, duration_ticks=2 * TPS)],
            ),
            asset_manifest=[ref_bg, ref_pip],
            generated_audio=[
                GeneratedAudioSource(source_id="v1", kind="voice", duration_ticks=2 * TPS),
                GeneratedAudioSource(source_id="music", kind="music", duration_ticks=2 * TPS, silent=True),
            ],
            style_snapshot=StyleSnapshot(style_id="default", version=1),
            provenance=Provenance(builder_version="test/1"),
        )

    p_base = _ov_plan(opacity=0.8, offset_ticks=0)
    p_op = _ov_plan(opacity=0.4, offset_ticks=0)
    p_off = _ov_plan(opacity=0.8, offset_ticks=5000)

    assert compile_render_plan(plan=p_base, assets=descs_ov, work_dir=str(tmp_path / "wb")).digest() != compile_render_plan(plan=p_op, assets=descs_ov, work_dir=str(tmp_path / "wb")).digest()
    assert NodeId("visual", "sh1") in selective_invalidation(plan_graph(p_base), plan_graph(p_op)).invalidated
    assert NodeId("visual", "sh1") in selective_invalidation(plan_graph(p_base), plan_graph(p_off)).invalidated


# --------------------------------------------------------------------------- REC-02.02: True Peak, Multitrack & Motion


def test_rec02_audio_dsp_removes_fake_true_peak_alias():
    tone = generate_synthetic_tone(duration_s=1.0, freq_hz=440.0, gain_db=-6.0)
    plan = MultitrackAudioPlan(
        total_duration_s=1.0,
        sfx_events=(AudioEvent(id="e1", track_id="t1", category=AudioCategory.SFX, start_s=0.0, duration_s=1.0),),
    )
    _, metrics = mix_multitrack_pcm(plan, {"t1": tone})
    assert "sample_peak_dbfs" in metrics
    assert "true_peak_dbtp" not in metrics


def test_rec02_multitrack_rejects_unknown_license_before_ffmpeg(tmp_path):
    bg = _solid_png(tmp_path / "bg.png", (10, 20, 80), size=(320, 240))
    speech = save_pcm_as_wav(generate_synthetic_tone(1.2, freq_hz=200.0, gain_db=-35.0), tmp_path / "speech.wav")
    mus_wav = tmp_path / "mus.wav"
    save_pcm_as_wav(generate_synthetic_tone(2.0, 330.0), mus_wav)

    row = StoryboardRow(id="sc-1", video_id="vid-lic", idx=0, narration="Cena de teste licença.", image_prompt="Fundo azul escuro sólido.", asset_id="a-bg", label="")
    mt = build_multitrack_plan(total_duration_s=2.0, music_tracks=[("bad_mus", 0.0, 2.0)])
    cat = AudioCatalog(tracks=(AudioTrack(id="bad_mus", category=AudioCategory.MUSIC, title="Bad", license="unknown", file_path=str(mus_wav)),))
    spec = RenderSpec(
        scenes=[row], images=[bg], speech_wavs=[speech], scene_seconds=[2.0], cues=[],
        format=VideoFormat.long, music=False, disclosure="Teste", work_dir=tmp_path / "work",
        multitrack=mt, audio_catalog=cat,
    )
    with pytest.raises((CompileError, ValueError), match="license"):
        PlanFfmpegRenderer(cycle=("none",)).render(spec, tmp_path / "out.mp4")


def _decode_pcm_mono(mp4_path: Path, start_s: float, duration_s: float, sr: int = 24000) -> list[int]:
    import array
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(mp4_path), "-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}",
            "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    arr = array.array("h")
    arr.frombytes(proc.stdout)
    return list(arr)


def _rms_db(samples: list[int]) -> float:
    if not samples:
        return -120.0
    mean_sq = sum(s * s for s in samples) / float(len(samples))
    return 10.0 * math.log10(max(1e-12, mean_sq / (32767.0 ** 2)))


@needs_ffmpeg
def test_rec02_multitrack_voice_2music_ambience_sfx_ducking_ebur128(tmp_path):
    bg = _solid_png(tmp_path / "bg.png", (20, 40, 90), size=(1920, 1080))
    # Speech active in [0.4s, 2.0s], then silent in [2.0s, 4.6s] -> total scene 5.0s
    sr = 24000
    speech_samples = (
        [0] * int(0.4 * sr)
        + generate_synthetic_tone(1.6, freq_hz=240.0, sample_rate=sr, gain_db=-10.0)
        + [0] * int(2.6 * sr)
    )
    speech_wav = save_pcm_as_wav(speech_samples, tmp_path / "speech.wav", sample_rate=sr)

    mus1_wav = save_pcm_as_wav(generate_synthetic_tone(2.8, freq_hz=330.0, sample_rate=sr, gain_db=0.0), tmp_path / "mus1.wav", sample_rate=sr)
    mus2_wav = save_pcm_as_wav(generate_synthetic_tone(2.8, freq_hz=440.0, sample_rate=sr, gain_db=0.0), tmp_path / "mus2.wav", sample_rate=sr)
    amb_wav = save_pcm_as_wav(generate_synthetic_tone(5.0, freq_hz=110.0, sample_rate=sr, gain_db=-12.0), tmp_path / "amb.wav", sample_rate=sr)
    sfx_wav = save_pcm_as_wav(generate_synthetic_sfx("ding", duration_s=0.4, sample_rate=sr), tmp_path / "sfx.wav", sample_rate=sr)

    cat = AudioCatalog(tracks=(
        AudioTrack(id="m1", category=AudioCategory.MUSIC, title="M1", license="cc0", file_path=str(mus1_wav), duration_s=2.8),
        AudioTrack(id="m2", category=AudioCategory.MUSIC, title="M2", license="cc-by", file_path=str(mus2_wav), duration_s=2.8),
        AudioTrack(id="amb", category=AudioCategory.AMBIENCE, title="Amb", license="cc0", file_path=str(amb_wav), duration_s=5.0),
        AudioTrack(id="ding", category=AudioCategory.SFX, title="Ding", license="cc0", file_path=str(sfx_wav), duration_s=0.4),
    ))
    mt = build_multitrack_plan(
        total_duration_s=5.0,
        voice_events=[AudioEvent(id="v0", track_id="voice", category=AudioCategory.VOICE, start_s=0.4, duration_s=1.6)],
        music_tracks=[("m1", 0.0, 2.8), ("m2", 2.2, 2.8)],
        ambience_track_id="amb",
        sfx_cues=[("ding", 3.5)],
        catalog=cat,
    )

    row = StoryboardRow(id="sc-1", video_id="vid-mt", idx=0, narration="Teste multitrack completo.", image_prompt="Fundo azul escuro sólido.", asset_id="a-bg", label="")
    work = tmp_path / "work"
    work.mkdir()
    spec = RenderSpec(
        scenes=[row], images=[bg], speech_wavs=[speech_wav], scene_seconds=[5.0], cues=[],
        format=VideoFormat.long, music=True, disclosure="Teste", work_dir=work,
        multitrack=mt, audio_catalog=cat,
    )
    out_mp4 = tmp_path / "mt_out.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec, out_mp4)

    qa = FfmpegQa().analyze(out_mp4)
    assert qa["has_audio"] is True
    assert abs(qa["duration_s"] - 5.0) <= 0.15
    assert qa["true_peak_dbtp"] is not None
    assert qa["true_peak_dbtp"] <= -1.0, f"clipping risk: true_peak_dbtp={qa['true_peak_dbtp']}"
    assert qa["integrated_lufs"] is not None
    assert -22.0 <= qa["integrated_lufs"] <= -11.0

    # P1-2: Observable ducking proof on real rendered MP4 vs unducked control
    mt_unducked = MultitrackAudioPlan(
        total_duration_s=mt.total_duration_s,
        voice_events=mt.voice_events,
        music_events=tuple(
            AudioEvent(id=e.id, track_id=e.track_id, category=e.category, start_s=e.start_s, duration_s=e.duration_s, gain_db=e.gain_db, fade_in_s=e.fade_in_s, fade_out_s=e.fade_out_s, ducked=False)
            for e in mt.music_events
        ),
        ambience_events=tuple(
            AudioEvent(id=e.id, track_id=e.track_id, category=e.category, start_s=e.start_s, duration_s=e.duration_s, gain_db=e.gain_db, fade_in_s=e.fade_in_s, fade_out_s=e.fade_out_s, ducked=False)
            for e in mt.ambience_events
        ),
        sfx_events=mt.sfx_events,
    )
    work_unducked = tmp_path / "work_unducked"
    work_unducked.mkdir()
    spec_unducked = RenderSpec(
        scenes=[row], images=[bg], speech_wavs=[speech_wav], scene_seconds=[5.0], cues=[],
        format=VideoFormat.long, music=True, disclosure="Teste", work_dir=work_unducked,
        multitrack=mt_unducked, audio_catalog=cat,
    )
    out_unducked = tmp_path / "mt_unducked.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec_unducked, out_unducked)

    ducked_speech_db = _rms_db(_decode_pcm_mono(out_mp4, 0.7, 1.0))
    ducked_pause_db = _rms_db(_decode_pcm_mono(out_mp4, 2.4, 0.8))
    unducked_speech_db = _rms_db(_decode_pcm_mono(out_unducked, 0.7, 1.0))
    unducked_pause_db = _rms_db(_decode_pcm_mono(out_unducked, 2.4, 0.8))
    # Compare relative speech-vs-pause ratio within each render to cancel loudnorm global gain
    ducked_delta = ducked_speech_db - ducked_pause_db
    unducked_delta = unducked_speech_db - unducked_pause_db
    assert ducked_delta < unducked_delta - 1.5, (
        f"expected observable ducking attenuation during speech: "
        f"ducked_delta={ducked_delta:.2f}dB vs unducked_delta={unducked_delta:.2f}dB"
    )


@needs_ffmpeg
def test_rec02_multitrack_preserves_stereo_right_channel_and_trailing_audio(tmp_path):
    import array
    bg = _solid_png(tmp_path / "bg.png", (10, 20, 40), size=(320, 240))
    sr = 24000
    # Short narration (0.5s), total video 2.5s
    speech_wav = save_pcm_as_wav(generate_synthetic_tone(0.5, freq_hz=240.0, sample_rate=sr, gain_db=-6.0), tmp_path / "short_speech.wav", sample_rate=sr)

    # Stereo music WAV with SILENT left channel and -6dB 440Hz tone on RIGHT channel
    right_samples = generate_synthetic_tone(2.5, freq_hz=440.0, sample_rate=sr, gain_db=-6.0)
    interleaved = []
    for s in right_samples:
        interleaved.extend([0, s])
    stereo_wav = tmp_path / "stereo_right.wav"
    with wave.open(str(stereo_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(array.array("h", interleaved).tobytes())

    cat = AudioCatalog(tracks=(
        AudioTrack(id="m_stereo", category=AudioCategory.MUSIC, title="StereoR", license="cc0", file_path=str(stereo_wav), duration_s=2.5),
    ))
    mt = build_multitrack_plan(total_duration_s=2.5, music_tracks=[("m_stereo", 0.0, 2.5)], catalog=cat)
    row = StoryboardRow(id="sc-1", video_id="vid-st", idx=0, narration="Fala curta.", image_prompt="Fundo azul escuro sólido.", asset_id="a-bg", label="")
    work = tmp_path / "work"
    work.mkdir()
    spec = RenderSpec(
        scenes=[row], images=[bg], speech_wavs=[speech_wav], scene_seconds=[2.5], cues=[],
        format=VideoFormat.long, music=True, disclosure="Teste", work_dir=work,
        multitrack=mt, audio_catalog=cat,
    )
    out_mp4 = tmp_path / "stereo_out.mp4"
    PlanFfmpegRenderer(cycle=("none",)).render(spec, out_mp4)

    qa_st = FfmpegQa().analyze(out_mp4)
    assert abs(qa_st["duration_s"] - 2.5) <= 0.15, f"unexpected duration: {qa_st}"
    pcm_path = tmp_path / "stereo.pcm"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(out_mp4),
            "-vn", "-ac", "2", "-ar", str(sr), "-f", "s16le", str(pcm_path),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    arr = array.array("h")
    arr.frombytes(pcm_path.read_bytes())
    start_idx = int(1.5 * sr) * 2
    end_idx = int(2.2 * sr) * 2
    trailing = arr[start_idx:end_idx]
    right_ch = list(trailing[1::2])
    assert len(right_ch) > 1000, f"expected trailing PCM samples, got len(arr)={len(arr)}, qa={qa_st}"
    assert _rms_db(right_ch) > -35.0, f"expected stereo right-channel trailing audio preserved, got {_rms_db(right_ch):.2f}dB (len={len(right_ch)}, qa={qa_st})"


@needs_ffmpeg
def test_rec02_multitrack_does_not_poison_non_multitrack_final_cache(tmp_path):
    class _MemPlans:
        def __init__(self):
            self.plans = {}
            self.entries_map = {}

        def latest_plan(self, plan_id):
            return self.plans.get(plan_id)

        def entries(self, plan_id):
            return self.entries_map.get(plan_id, {})

        def save_plan(self, plan):
            self.plans[plan.plan_id] = plan

        def record_entries(self, entries):
            for e in entries:
                self.entries_map.setdefault(e.plan_id, {})[e.node] = e

        def record_artifacts(self, artifacts):
            pass

    bg = _solid_png(tmp_path / "bg.png", (10, 20, 40), size=(320, 240))
    speech_wav = save_pcm_as_wav(generate_synthetic_tone(1.2, freq_hz=240.0, gain_db=-10.0), tmp_path / "speech.wav")
    mus_wav = save_pcm_as_wav(generate_synthetic_tone(2.0, freq_hz=330.0, gain_db=-6.0), tmp_path / "mus.wav")
    cat = AudioCatalog(tracks=(AudioTrack(id="m1", category=AudioCategory.MUSIC, title="M1", license="cc0", file_path=str(mus_wav), duration_s=2.0),))
    mt = build_multitrack_plan(total_duration_s=2.0, music_tracks=[("m1", 0.0, 2.0)], catalog=cat)

    row = StoryboardRow(id="sc-1", video_id="vid-cache", idx=0, narration="Teste cache.", image_prompt="Fundo azul escuro sólido.", asset_id="a-bg", label="")
    work = tmp_path / "work"
    work.mkdir()
    plans_repo = _MemPlans()
    renderer = PlanFfmpegRenderer(cycle=("none",), plans=plans_repo, cache_root=tmp_path / "cache")

    spec_mt = RenderSpec(
        scenes=[row], images=[bg], speech_wavs=[speech_wav], scene_seconds=[2.0], cues=[],
        format=VideoFormat.long, music=True, disclosure="Teste", work_dir=work,
        multitrack=mt, audio_catalog=cat,
    )
    renderer.render(spec_mt, tmp_path / "mt.mp4")
    assert NodeId("final", "video") not in plans_repo.entries("plan:vid-cache")


@needs_ffmpeg
def test_rec02_motion_effects_produce_observable_frame_diff(tmp_path):
    grid = _grid_png(tmp_path / "grid.png")
    speech = save_pcm_as_wav(generate_synthetic_tone(1.2, freq_hz=200.0, gain_db=-35.0), tmp_path / "speech.wav")
    row = StoryboardRow(id="sc-1", video_id="vid-mot", idx=0, narration="Cena com movimento Ken Burns.", image_prompt="Grade geométrica de teste.", asset_id="a-grid", label="")

    def _render_and_diff(motion: str) -> float:
        work = tmp_path / f"work_{motion}"
        work.mkdir()
        spec = RenderSpec(
            scenes=[row], images=[grid], speech_wavs=[speech], scene_seconds=[2.0], cues=[],
            format=VideoFormat.long, music=False, disclosure="Teste", work_dir=work,
        )
        out_mp4 = tmp_path / f"out_{motion}.mp4"
        PlanFfmpegRenderer(cycle=(motion,)).render(spec, out_mp4)
        f1 = _sample_frame(out_mp4, 0.2, tmp_path / f"{motion}_1.png")
        f2 = _sample_frame(out_mp4, 1.5, tmp_path / f"{motion}_2.png")
        b1, b2 = f1.tobytes(), f2.tobytes()
        return sum(abs(a - b) for a, b in zip(b1, b2)) / len(b1)

    diff_zoom = _render_and_diff("zoom_in")
    diff_none = _render_and_diff("none")
    assert diff_zoom > 5.0, f"expected observable pixel motion for zoom_in, got {diff_zoom}"
    assert diff_none < 1.0, f"expected static frame for none, got {diff_none}"
