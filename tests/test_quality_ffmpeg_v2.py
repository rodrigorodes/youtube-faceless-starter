"""Testes das medições avançadas do FfmpegQa (Onda 5 / Task 3)."""
import subprocess
from pathlib import Path
import pytest

from app.studio.adapters.qa_ffmpeg import FfmpegQa


def test_ffmpeg_qa_analyzes_true_peak_codecs_and_freezedetect(tmp_path):
    # Gera um arquivo sintético mp4 com h264 e aac, e um tom senoidal de áudio
    mp4_file = tmp_path / "sample_v2.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2.0:r=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(mp4_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert mp4_file.is_file()

    qa = FfmpegQa()
    metrics = qa.analyze(mp4_file)

    # 1. True Peak presente e numérico
    assert "true_peak_dbtp" in metrics
    assert isinstance(metrics["true_peak_dbtp"], float)

    # 2. Codecs identificados
    assert metrics.get("video_codec") in ("h264", "avc1")
    assert metrics.get("audio_codec") == "aac"

    # 3. Freeze detect medido
    assert "frozen_ratio" in metrics
    assert isinstance(metrics["frozen_ratio"], float)
    # Como a cor é sólida azul por 2s, deve haver freeze detectado
    assert metrics["frozen_ratio"] > 0.0
