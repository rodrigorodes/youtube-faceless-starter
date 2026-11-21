import math
import os
import sys
import wave
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app import rich  # noqa: E402


def write_tone(path, seconds, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(seconds * rate))


def test_scene_length_is_whole_frames():
    for speech in (1.0, 3.37, 5.123):
        total = rich.scene_length(speech)
        assert math.isclose(total * rich.FPS, round(total * rich.FPS), abs_tol=1e-9)
        assert total >= speech + rich.LEAD + rich.TAIL


def test_narration_track_matches_scene_lengths(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    write_tone(a, 2.0), write_tone(b, 3.3)
    lengths = rich.build_narration_track([a, b], tmp_path / "n.wav")
    assert len(lengths) == 2
    assert math.isclose(rich.wav_duration(tmp_path / "n.wav"), sum(lengths), abs_tol=0.01)  # áudio e vídeo alinhados


def test_music_is_original_bounded_and_nonsilent(tmp_path):
    rich.synth_music(6.0, tmp_path / "m.wav")
    with wave.open(str(tmp_path / "m.wav"), "rb") as w:
        assert w.getframerate() == rich.MUSIC_SR and math.isclose(w.getnframes() / w.getframerate(), 6.0, abs_tol=0.01)
        import numpy as np
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert 0.3 < np.abs(data).max() / 32767 <= 0.81 and data.std() > 500


def test_overlay_has_transparency_and_text(tmp_path):
    from PIL import Image
    rich.make_overlay("QUA • 21/10", "Legenda de teste bem longa " * 4, tmp_path / "o.png")
    img = Image.open(tmp_path / "o.png")
    assert img.size == (rich.W, rich.H) and img.mode == "RGBA"
    alpha = img.getchannel("A")
    assert alpha.getextrema()[0] == 0 and alpha.getextrema()[1] > 150
    assert alpha.crop((0, 1700, rich.W, rich.H)).getextrema() == (0, 0)  # área inferior da UI dos Shorts fica livre


def test_cover_image_fills_frame(tmp_path):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (768, 1344), (1, 2, 3)).save(buf, "PNG")
    rich.cover_image(buf.getvalue(), tmp_path / "c.png")
    assert Image.open(tmp_path / "c.png").size == (rich.W, rich.H)
