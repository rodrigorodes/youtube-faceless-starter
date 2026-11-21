"""E2E de QA (RP-030/RP-031) — vídeo bom aprova, vídeo com defeito é bloqueado.

Ponta a ponta e offline: clipes curtos e sintéticos. O caminho bom renderiza pelo
``PlanFfmpegRenderer`` (o único caminho), mede com ``FfmpegQualityEvaluator``
(ffprobe/ebur128) e aprova pelo gate da F6 (``approve``). Os clipes com defeito (curto
demais, silêncio, preto, resolução errada) são sintetizados com FFmpeg e a evidência é
medida pelo mesmo avaliador — eles têm de produzir achado **blocking** e **não** aprovar.

Prova de mutação, então: o avaliador **distingue** o vídeo bom do defeituoso de verdade,
com números medidos, não com um score inventado.
"""
import hashlib
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.ports import RenderSpec  # noqa: E402
from app.studio.domain.asset_resolver import AssetDescriptor  # noqa: E402
from app.studio.domain.contracts import Scene, VideoFormat  # noqa: E402
from app.studio.domain.qa_report import BlockingFindings, CoverageNotVerified, approve, RenderVersion  # noqa: E402
from app.studio.domain.render import SIZE, make_cues, scene_length  # noqa: E402
from app.studio.domain.render_plan import AssetReference, StyleSnapshot  # noqa: E402
from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SCENE = "a" * 32
VIDEO = "v" * 32
SHA = "a" * 64


def tone_wav(path, seconds=3.0, amplitude=0.4, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate))) for i in range(n)))


def spec_for(tmp, seconds=3.0):
    size = SIZE[VideoFormat.short]
    img = tmp / "img0.png"
    Image.new("RGB", size, (40, 80, 160)).save(img)
    wav = tmp / "s0.wav"
    tone_wav(wav, seconds)
    text = "Narração do teste automatizado de qualidade."
    length = scene_length(seconds)
    scene = Scene(id=SCENE, video_id=VIDEO, idx=0, narration=text, label="QUA", caption="x",
                  image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id=SCENE)
    work = tmp / "work"
    work.mkdir(exist_ok=True)
    return RenderSpec(scenes=[scene], images=[img], speech_wavs=[wav], scene_seconds=[length],
                      cues=make_cues(text, 0.0, seconds), format=VideoFormat.short, music=True, work_dir=work)


def qa_plan(seconds=3.0):
    asset = AssetReference(asset_id="asset0", asset_version=1, uri="assets/0.png", content_sha256=SHA,
                           media_type="image", license="CC0")
    scene = StoryboardScene(scene_id="scene0", asset_id="asset0", narration="Narração do teste automatizado.",
                            speech_seconds=seconds - 0.8, label="SELO")
    plan = build_render_plan(plan_id="plan:qa", revision=1, project_id="p", video_id="v",
                             format=VideoFormat.short, scenes=[scene], assets=[asset],
                             style_snapshot=StyleSnapshot(style_id="s", version=1))
    descriptor = AssetDescriptor(asset_id="asset0", asset_version=1, uri="assets/0.png", content_sha256=SHA,
                                 media_type="image", license="CC0", available=True, codec="png",
                                 width=1080, height=1920)
    return plan, (descriptor,)


def synth_clip(path, *, seconds, color="red", audio="sine", size=(1080, 1920)):
    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", f"color=c={color}:s={size[0]}x{size[1]}:r=25:d={seconds}"]
    if audio == "sine":
        args += ["-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}"]
    elif audio == "silent":
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio != "none":
        args += ["-c:a", "aac", "-shortest"]
    args += [str(path)]
    subprocess.run(args, check=True, capture_output=True)


def evaluate(clip, narration, *, plan, descriptors, seconds=3.0):
    checksum = hashlib.sha256(Path(clip).read_bytes()).hexdigest()
    report = FfmpegQualityEvaluator().evaluate(plan, media_path=Path(clip), narration_path=narration,
                                               descriptors=descriptors, render_id="job:test", checksum=checksum)
    return report, RenderVersion(render_id="job:test", checksum=checksum)


# ------------------------------------------------------------------ caminho bom

@needs_ffmpeg
def test_the_plan_render_passes_its_own_quality_gate_and_approves(tmp_path):
    spec = spec_for(tmp_path)
    renderer = PlanFfmpegRenderer()
    plan = renderer._build_plan(spec)
    descriptors = tuple(renderer._descriptors(plan, spec).values())
    out = renderer.render(spec, spec.work_dir / "final.mp4")
    report, version = evaluate(out, spec.work_dir / "narration.wav", plan=plan, descriptors=descriptors)
    assert report.coverage.status == "verified", report.coverage.reason
    assert report.is_publishable, [f.evidence for f in report.blocking_findings]
    assert approve(report=report, latest=version, requested=version).checksum == version.checksum


@needs_ffmpeg
def test_a_good_clip_without_a_narration_track_cannot_claim_verified_coverage(tmp_path):
    narration = tmp_path / "narration.wav"
    tone_wav(narration, 3.0)
    clip = tmp_path / "good.mp4"
    synth_clip(clip, seconds=3.0, color="red", audio="sine")
    plan, descriptors = qa_plan(3.0)
    report, version = evaluate(clip, None, plan=plan, descriptors=descriptors)
    assert report.coverage.status == "not_verified"
    with pytest.raises(CoverageNotVerified):
        approve(report=report, latest=version, requested=version)


# ------------------------------------------------------------------ mutação: vídeos com defeito

@needs_ffmpeg
@pytest.mark.parametrize("name,seconds,color,audio", [
    ("too-short", 1.0, "red", "sine"),
    ("silent", 3.0, "blue", "silent"),
    ("black", 3.0, "black", "sine"),
])
def test_a_defective_clip_is_blocked_and_never_approves(tmp_path, name, seconds, color, audio):
    narration = tmp_path / "narration.wav"
    tone_wav(narration, 3.0)
    clip = tmp_path / f"{name}.mp4"
    synth_clip(clip, seconds=seconds, color=color, audio=audio)
    plan, descriptors = qa_plan(3.0)
    report, version = evaluate(clip, narration, plan=plan, descriptors=descriptors)
    assert report.coverage.status == "verified", report.coverage.reason  # medido; o defeito é real
    blocking = report.blocking_findings
    assert blocking, "um clipe defeituoso tem de produzir achado blocking"
    with pytest.raises(BlockingFindings):
        approve(report=report, latest=version, requested=version)


@needs_ffmpeg
def test_a_low_resolution_clip_is_blocked(tmp_path):
    narration = tmp_path / "narration.wav"
    tone_wav(narration, 3.0)
    clip = tmp_path / "small.mp4"
    synth_clip(clip, seconds=3.0, color="red", audio="sine", size=(640, 360))
    plan, descriptors = qa_plan(3.0)
    report, version = evaluate(clip, narration, plan=plan, descriptors=descriptors)
    assert any(f.check_id == "render.resolution" for f in report.blocking_findings)
    with pytest.raises(BlockingFindings):
        approve(report=report, latest=version, requested=version)
