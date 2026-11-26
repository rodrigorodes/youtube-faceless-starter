"""Utilitários compartilhados pelos pilotos observados de REC-04 (slice 60–90s e documentário 5–8min).

Centraliza helpers determinísticos de fixtures PNG/MP4, extração de frames, estatísticas RGB/PCM,
ffprobe, medição de drift áudio-legenda, versão real do pacote `piper-tts` (P2-4) e criação do
`Studio` + `TestClient` em modo estritamente offline (`$0.00`, `STUDIO_PUBLICATION_ENABLED=0`).
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.studio.api.routes import make_router
from app.studio.application.production import ProductionMode
from app.studio.composition import Settings, Studio
from app.studio.domain.captions import CaptionLine, check_audio_caption_sync

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
needs_piper = pytest.mark.skipif(
    not Path("/opt/voices/pt_BR-faber-medium.onnx").is_file() or shutil.which("piper") is None,
    reason="piper pt_BR-faber-medium not installed",
)


class SyncExecutor:
    """Executa tarefas do Studio sincronamente para determinismo total do teste."""

    def submit(self, fn, *args):
        fn(*args)

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def make_studio_client(
    dsn: str,
    storage_root: Path,
    *,
    source_allowlist: tuple[str, ...] = ("pt.wikipedia.org",),
) -> tuple[Studio, TestClient]:
    """Cria instância canônica do `Studio` + `TestClient` com orçamento $0.00 e kill switch BLOCKED."""
    storage_root.mkdir(parents=True, exist_ok=True)
    environ = {
        "STUDIO_TEXT": "demo:v4",
        "STUDIO_IMAGE": "placeholder:v4",
        "STUDIO_VOICE": "piper:pt_BR-faber-medium",
        "STUDIO_RENDERER": "ffmpeg",
        "STUDIO_PUBLICATION_ENABLED": "0",
        "STUDIO_AUTO_RESEARCH": "0",
        "STUDIO_BUDGET_GUARD": "1",
        "MAX_COST_USD_PER_VIDEO": "0",
        "MAX_COST_USD_PER_MONTH": "0",
    }
    settings = Settings(
        database_url=dsn,
        storage_root=storage_root,
        source_allowlist=source_allowlist,
        auto_research=False,
        render_plan_enabled=True,
        budget_guard=True,
        max_cost_video=0.00,
        max_cost_month=0.00,
        publication_enabled=False,
        production_mode=ProductionMode.BUDGET_GUARDED,
    )
    studio = Studio(settings, environ=environ, executor=SyncExecutor())
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(
        app,
        base_url="http://testserver",
        headers={"Authorization": "Bearer test-worker-token"},
    )
    return studio, client


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_rich_png(
    size: tuple[int, int],
    bg: tuple[int, int, int],
    grid_color: tuple[int, int, int],
    accent: tuple[int, int, int],
    shape: str = "circles",
) -> bytes:
    """Gera PNG determinístico com geometria nítida (evita quadro uniforme/congelado)."""
    w, h = size
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    for x in range(0, w, 120):
        draw.line([(x, 0), (x, h)], fill=grid_color, width=2)
    for y in range(0, h, 120):
        draw.line([(0, y), (w, y)], fill=grid_color, width=2)
    if shape == "circles":
        for r in (140, 260, 380):
            draw.ellipse((w // 2 - r, h // 2 - r, w // 2 + r, h // 2 + r), outline=accent, width=6)
        draw.rectangle((140, h - 280, 620, h - 180), fill=accent)
    elif shape == "bars":
        for i in range(6):
            x0 = 180 + i * 260
            y0 = 260 + (i % 3) * 140
            draw.rectangle((x0, y0, x0 + 160, h - 220), outline=accent, width=6)
            draw.rectangle((x0 + 24, y0 + 24, x0 + 136, y0 + 96), fill=accent)
    elif shape == "badge":
        draw.rounded_rectangle((16, 16, w - 16, h - 16), radius=28, fill=bg, outline=accent, width=12)
        draw.rectangle((64, 72, w - 64, 152), fill=accent)
        draw.rectangle((64, 192, w - 140, 248), fill=grid_color)
        draw.rectangle((64, 272, w - 220, 312), fill=grid_color)
    elif shape == "waves":
        for band in range(6):
            y_base = 180 + band * 135
            pts = []
            for x in range(100, w - 100, 60):
                y = y_base + int(38 * math.sin((x / 150.0) + band * 0.9))
                pts.append((x, y))
            draw.line(pts, fill=accent, width=6)
    elif shape == "network":
        nodes = [
            (320, 300), (760, 240), (1220, 310), (1580, 260),
            (480, 620), (960, 560), (1440, 640),
            (340, 820), (960, 820), (1560, 820),
        ]
        for i, (x0, y0) in enumerate(nodes):
            for x1, y1 in nodes[i + 1 : i + 4]:
                draw.line([(x0, y0), (x1, y1)], fill=grid_color, width=3)
        for nx, ny in nodes:
            draw.ellipse((nx - 26, ny - 26, nx + 26, ny + 26), fill=accent, outline=(255, 255, 255), width=3)
    else:  # circuit
        for i in range(5):
            y = 180 + i * 165
            draw.line([(160, y), (w - 160, y)], fill=accent, width=5)
            cx = 360 + i * 280
            draw.ellipse((cx - 32, y - 32, cx + 32, y + 32), fill=accent)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_real_mp4(
    path: Path,
    *,
    width: int,
    height: int,
    duration_s: float,
    kind: str = "base",
    hue_speed: int = 45,
) -> bytes:
    """Gera MP4 H.264 real reproduzível com movimento contínuo via FFmpeg."""
    if kind == "base":
        vf = f"testsrc2=size={width}x{height}:rate=25:duration={duration_s:.1f},hue=h=t*{hue_speed}"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
    elif kind == "mandelbrot":
        vf = (
            f"smptehdbars=size={width}x{height}:rate=25:duration={duration_s:.1f},"
            f"hue=h=t*{hue_speed},drawbox=x='mod(t*220,iw-180)':y=360:w=180:h=180:color=yellow@0.9:t=fill"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
    else:
        seg = max(0.5, duration_s / 5.0)
        colors = ("0x00E5FF", "0xFF2A85", "0xFFE600", "0x00E676", "0xFF6D00")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for c in colors:
            cmd += ["-f", "lavfi", "-i", f"color=c={c}:s={width}x{height}:r=25:d={seg:.2f}"]
        concat_in = "".join(f"[{i}:v]" for i in range(len(colors)))
        cmd += [
            "-filter_complex",
            f"{concat_in}concat=n={len(colors)}:v=1:a=0,drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white:t=10,format=yuv420p[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
    subprocess.run(cmd, check=True, timeout=60)
    return path.read_bytes()


def extract_frame(mp4: Path, time_s: float, out_png: Path, *, scale_w: int | None = None) -> Image.Image:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, time_s):.3f}", "-i", str(mp4),
        "-frames:v", "1",
    ]
    if scale_w is not None:
        cmd += ["-vf", f"scale={scale_w}:-2"]
    cmd.append(str(out_png))
    subprocess.run(cmd, check=True, timeout=30)
    with Image.open(out_png) as img:
        return img.convert("RGB")


def image_stats(img: Image.Image) -> dict[str, float]:
    small = img.resize((160, 90))
    pixels = list(small.getdata())
    n = len(pixels)
    mean_r = sum(p[0] for p in pixels) / n
    mean_g = sum(p[1] for p in pixels) / n
    mean_b = sum(p[2] for p in pixels) / n
    lumas = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in pixels]
    mean_l = sum(lumas) / n
    var_l = sum((v - mean_l) ** 2 for v in lumas) / n
    return {
        "mean_r": round(mean_r, 2),
        "mean_g": round(mean_g, 2),
        "mean_b": round(mean_b, 2),
        "mean_luma": round(mean_l, 2),
        "std_luma": round(math.sqrt(var_l), 2),
    }


def mean_abs_diff(
    img_a: Image.Image,
    img_b: Image.Image,
    box: tuple[int, int, int, int] | None = None,
) -> float:
    a = img_a.crop(box) if box else img_a
    b = img_b.crop(box) if box else img_b
    a = a.resize((160, 90))
    b = b.resize((160, 90))
    pa = list(a.getdata())
    pb = list(b.getdata())
    total = sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2]) for x, y in zip(pa, pb))
    return total / (len(pa) * 3)


def wav_rms_and_duration(wav_bytes: bytes) -> tuple[float, float, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate = w.getframerate()
        width = w.getsampwidth()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
    assert width == 2, f"expected 16-bit PCM WAV, got sample width {width}"
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    rms = math.sqrt(sum(s * s for s in samples) / max(1, len(samples)))
    peak = max((abs(s) for s in samples), default=0)
    dur = nframes / rate if rate else 0.0
    return dur, rms, peak


def audio_window_rms(mp4: Path, start_s: float, duration_s: float, tmp_wav: Path) -> float:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, start_s):.3f}", "-t", f"{duration_s:.3f}",
            "-i", str(mp4), "-vn", "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(tmp_wav),
        ],
        check=True,
        timeout=30,
    )
    _, rms, _ = wav_rms_and_duration(tmp_wav.read_bytes())
    return rms


def probe_full(mp4: Path) -> dict[str, Any]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(mp4)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(res.stdout)


def tool_version(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (res.stdout or res.stderr or "").strip().splitlines()
        return out[0] if out else "unknown"
    except Exception:
        return "unavailable"


def piper_version() -> str:
    """Retorna versão real do pacote Python `piper-tts` (corrige P2-4: `piper --version` imprime usage)."""
    for dist_name in ("piper-tts", "piper"):
        try:
            ver = importlib.metadata.version(dist_name)
            return f"{dist_name}=={ver}"
        except importlib.metadata.PackageNotFoundError:
            continue
    return "unavailable"


def git_info() -> dict[str, str]:
    info = {"sha": "unknown", "branch": "unknown"}
    try:
        info["sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=10).strip()
        info["branch"] = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, timeout=10).strip()
    except Exception:
        pass
    return info


def compute_audio_caption_drift(
    plan,
    *,
    mp4_audio_duration_s: float,
    last_narration_end_s: float,
) -> dict[str, Any]:
    """Mede drift áudio-legenda real usando `check_audio_caption_sync` sobre o `RenderPlan` e `ffprobe`."""
    tps = plan.timeline.ticks_per_second or 1000
    lines = [
        CaptionLine(
            start_ms=int(round(cue.start_tick / tps * 1000)),
            end_ms=int(round((cue.start_tick + cue.duration_ticks) / tps * 1000)),
            text=cue.text,
            words=(),
        )
        for cue in plan.timeline.subtitles
    ]
    vs_mp4_audio = check_audio_caption_sync(lines, int(round(mp4_audio_duration_s * 1000)))
    vs_narration_end = check_audio_caption_sync(lines, int(round(last_narration_end_s * 1000)))
    return {
        "cues_count": len(lines),
        "last_caption_end_ms": vs_mp4_audio["last_caption_end_ms"],
        "mp4_audio_duration_ms": vs_mp4_audio["audio_duration_ms"],
        "drift_vs_mp4_audio_ms": vs_mp4_audio["drift_ms"],
        "last_narration_end_ms": vs_narration_end["audio_duration_ms"],
        "drift_vs_last_narration_end_ms": vs_narration_end["drift_ms"],
        "note": (
            "drift_vs_mp4_audio_ms inclui a cauda fixa TAIL_S=500ms após a última fala; "
            "drift_vs_last_narration_end_ms mede o desvio direto entre o fim da fala Piper e o fim da última legenda."
        ),
    }
