import json
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

from app.studio.adapters.qa_ffmpeg import FfmpegQa  # noqa: E402
from app.studio.adapters.render_ffmpeg import FfmpegRenderer  # noqa: E402
from app.studio.adapters.storage import FileRenderStorage  # noqa: E402
from app.studio.application.ports import RenderSpec  # noqa: E402
from app.studio.domain.contracts import Scene, VideoFormat  # noqa: E402
from app.studio.domain.render import SIZE, evaluate_qa, make_cues, scene_length  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
pytestmark = needs_ffmpeg


def tone_wav(path, seconds=1.0, amplitude=0.4, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / rate) * (0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / rate)))) for i in range(n)))


def spec_for(tmp, fmt=VideoFormat.short, amplitude=0.4, texts=("Primeira cena do teste automatizado.", "Segunda cena, com legenda um pouco maior que a primeira."), music=True):
    size = SIZE[fmt]
    scenes, images, wavs, lengths, cues, offset = [], [], [], [], [], 0.0
    for i, text in enumerate(texts):
        img = tmp / f"img{i}.png"
        Image.new("RGB", size, (30 + 60 * i, 80, 160 - 40 * i)).save(img)
        wav = tmp / f"s{i}.wav"
        tone_wav(wav, 1.0, amplitude)
        length = scene_length(1.0)
        scenes.append(Scene(id=f"{i:032x}", video_id="v" * 32, idx=i, narration=text, label="QUA", image_prompt="prompt de imagem válido"))
        images.append(img), wavs.append(wav), lengths.append(length)
        cues += make_cues(text, offset, 1.0)
        offset += length
    work = tmp / "work"
    work.mkdir(exist_ok=True)
    return RenderSpec(scenes=scenes, images=images, speech_wavs=wavs, scene_seconds=lengths, cues=cues, format=fmt, music=music, work_dir=work)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.parametrize("fmt", [VideoFormat.short, VideoFormat.long])
def test_renders_mp4_with_audio_video_and_the_format_size(tmp_path, fmt):
    spec = spec_for(tmp_path, fmt)
    out = FfmpegRenderer("rich").render(spec, tmp_path / "work" / "final.mp4")
    info = probe(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == SIZE[fmt] and any(s["codec_type"] == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(sum(spec.scene_seconds), abs=0.35)


def test_subtitles_are_burned_into_the_frames(tmp_path):
    spec = spec_for(tmp_path)
    out = FfmpegRenderer("rich").render(spec, tmp_path / "work" / "final.mp4")
    cue = spec.cues[0]
    frame_with, frame_without = tmp_path / "with.png", tmp_path / "without.png"
    for t, dst in (((cue.start + cue.end) / 2, frame_with), (spec.scene_seconds[0] + spec.scene_seconds[1] - 0.05, frame_without)):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(out), "-frames:v", "1", str(dst)], check=True)
    box = (50, 1250, 1030, 1570)  # região da legenda no short
    a, b = Image.open(frame_with).convert("L").crop(box), Image.open(frame_without).convert("L").crop(box)
    assert sum(a.getdata()) != sum(b.getdata())
    assert max(a.getdata()) > 200  # texto branco presente


def test_no_leftovers_other_than_the_output_are_required_and_ffmpeg_failure_has_a_clear_message(tmp_path):
    spec = spec_for(tmp_path)
    spec.images[0].write_bytes(b"nao e imagem")
    with pytest.raises(RuntimeError, match="ffmpeg|image"):
        FfmpegRenderer("rich").render(spec, tmp_path / "work" / "final.mp4")


def lavfi(tmp_path, name, video, audio):
    out = tmp_path / name
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", video]
    if audio:
        cmd += ["-f", "lavfi", "-i", audio]
    cmd += ["-t", "3", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return out


def test_qa_measures_a_normal_video(tmp_path):
    metrics = FfmpegQa().analyze(lavfi(tmp_path, "ok.mp4", "testsrc=size=1080x1920:rate=25", "sine=frequency=440:sample_rate=44100,volume=0.5"))
    assert metrics["width"] == 1080 and metrics["height"] == 1920 and metrics["has_audio"] is True
    assert metrics["duration_s"] == pytest.approx(3.0, abs=0.2) and -40 < metrics["integrated_lufs"] < -5
    assert metrics["silence_ratio"] < 0.1 and metrics["black_ratio"] < 0.1


def test_qa_detects_mute_black_and_missing_audio(tmp_path):
    mute = FfmpegQa().analyze(lavfi(tmp_path, "mute.mp4", "testsrc=size=1080x1920:rate=25", "anullsrc=r=44100:cl=mono"))
    assert mute["has_audio"] and (mute["integrated_lufs"] is None or mute["integrated_lufs"] < -45) and mute["silence_ratio"] > 0.9
    black = FfmpegQa().analyze(lavfi(tmp_path, "black.mp4", "color=c=black:size=1080x1920:rate=25", "sine=frequency=440:sample_rate=44100"))
    assert black["black_ratio"] > 0.9
    noaudio = FfmpegQa().analyze(lavfi(tmp_path, "na.mp4", "testsrc=size=1080x1920:rate=25", None))
    assert noaudio["has_audio"] is False and noaudio["integrated_lufs"] is None


def test_qa_rejects_unreadable_files(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"nada")
    with pytest.raises(RuntimeError):
        FfmpegQa().analyze(bad)


def test_end_to_end_rendered_video_passes_qa_and_a_mute_one_fails(tmp_path):
    fmt = VideoFormat.short
    good = tmp_path / "good"
    good.mkdir()
    spec = spec_for(good)
    out = FfmpegRenderer("rich").render(spec, good / "work" / "final.mp4")
    total = sum(spec.scene_seconds)
    qa = evaluate_qa({**FfmpegQa().analyze(out), "expected_s": total}, fmt)
    assert qa.passed, qa.failures
    mute = tmp_path / "mute"
    mute.mkdir()
    spec2 = spec_for(mute, amplitude=0.0, music=False)
    out2 = FfmpegRenderer("rich").render(spec2, mute / "work" / "final.mp4")
    qa2 = evaluate_qa({**FfmpegQa().analyze(out2), "expected_s": sum(spec2.scene_seconds)}, fmt)
    assert not qa2.passed and any("silent" in f for f in qa2.failures)


# ---------- storage ----------
PID, VID = "1" * 32, "2" * 32


def test_storage_publish_is_atomic_relative_and_cleanup_removes_only_the_work_dir(tmp_path):
    storage = FileRenderStorage(tmp_path)
    work = storage.work_dir(PID, VID, "a" * 32)
    mp4 = work / "final.mp4"
    mp4.write_bytes(b"MP4")
    rel = storage.publish(PID, VID, mp4, "1\n00:00:00,000 --> 00:00:01,000\nOlá\n")
    assert rel == f"projects/{PID}/videos/{VID}/final.mp4" and (tmp_path / rel).read_bytes() == b"MP4"
    assert (tmp_path / rel).with_suffix(".srt").read_text(encoding="utf-8").startswith("1\n")
    storage.cleanup(work)
    assert not work.exists() and (tmp_path / rel).exists()
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"NEW")
    storage.publish(PID, VID, mp4, "x")
    assert (tmp_path / rel).read_bytes() == b"NEW" and not [p for p in (tmp_path / rel).parent.iterdir() if p.suffix == ".tmp"]


def test_storage_refuses_traversal_and_foreign_cleanup(tmp_path):
    storage = FileRenderStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.image_path("../../etc/passwd")
    with pytest.raises(ValueError):
        storage.image_path("/etc/passwd")
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)
    storage.cleanup(outside)
    assert outside.exists()
    assert storage.image_path("cache/ab/x.png") == tmp_path / "cache" / "ab" / "x.png"
