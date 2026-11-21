#!/usr/bin/env python3
"""Benchmark audiovisual do render baseado em plano (RP-031).

Mede, em clipes curtos **sintéticos e offline**, o **tempo de render por minuto de
vídeo** e a **taxa de falhas** (Real) via ``application.benchmark``. O custo de provedor e
o cache hit **não** são medidos neste caminho (o cache de render é RP-06): saem como
**Estimado** com valor ausente — nunca um número inventado. Design §9: as metas
(§10 do pedido) são **alvo a medir**, não promessa; o que sai aqui é o medido, rotulado.

Uso: PYTHONPATH=renderer python3 scripts/render_benchmark.py [--scene-seconds 3.0] [--runs 1] [--json OUT]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.adapters.quality_ffmpeg import FfmpegQualityEvaluator  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.application.benchmark import BenchmarkSample, summarize  # noqa: E402
from app.studio.application.ports import RenderSpec  # noqa: E402
from app.studio.domain.contracts import Scene, VideoFormat  # noqa: E402
from app.studio.domain.render import SIZE, make_cues, scene_length  # noqa: E402

# Meta do pedido (§10), registrada como **alvo** — não como resultado medido.
TARGET = "render de um vídeo de 8 minutos em 1080p (§10 do pedido; alvo a medir, não promessa)"


def tone_wav(path: Path, seconds: float, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        frames = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(0.4 * 32767 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(frames)))


def build_spec(work: Path, seconds: float) -> RenderSpec:
    from PIL import Image

    size = SIZE[VideoFormat.short]
    image = work / "scene0.png"
    Image.new("RGB", size, (40, 80, 160)).save(image)
    speech = work / "scene0.wav"
    tone_wav(speech, seconds)
    text = "Narração do benchmark audiovisual automatizado."
    length = scene_length(seconds)
    scene = Scene(id="a" * 32, video_id="v" * 32, idx=0, narration=text, label="QUA", caption="x",
                  image_prompt="prompt de imagem válido", claim_ids=["c"], asset_id="a" * 32)
    return RenderSpec(scenes=[scene], images=[image], speech_wavs=[speech], scene_seconds=[length],
                      cues=make_cues(text, 0.0, seconds), format=VideoFormat.short, music=True,
                      work_dir=work)


def run_once(seconds: float) -> BenchmarkSample:
    with TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        work.mkdir(parents=True)
        spec = build_spec(work, seconds)
        renderer = PlanFfmpegRenderer()
        plan = renderer._build_plan(spec)
        descriptors = tuple(renderer._descriptors(plan, spec).values())
        started = time.perf_counter()
        out = renderer.render(spec, work / "final.mp4")
        elapsed = time.perf_counter() - started
        checksum = hashlib.sha256(out.read_bytes()).hexdigest()
        report = FfmpegQualityEvaluator().evaluate(plan, media_path=out, narration_path=work / "narration.wav",
                                                   descriptors=descriptors, render_id="bench", checksum=checksum)
        return BenchmarkSample(video_seconds=sum(spec.scene_seconds), render_seconds=elapsed,
                               qa_passed=report.is_publishable)


def markdown(samples) -> str:
    lines = ["| Métrica | Unidade | Rótulo | Valor medido | Nota |", "|---|---|---|---|---|"]
    for metric in samples:
        value = "—" if metric.value is None else f"{metric.value:.3f}"
        lines.append(f"| `{metric.name}` | {metric.unit} | **{metric.label}** | {value} | {metric.note or '—'} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-seconds", type=float, default=3.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    samples = [run_once(args.scene_seconds) for _ in range(max(1, args.runs))]
    metrics = summarize(samples)
    payload = {
        "scene_seconds": args.scene_seconds,
        "runs": len(samples),
        "target": TARGET,
        "samples": [{"video_seconds": s.video_seconds, "render_seconds": round(s.render_seconds, 3),
                     "qa_passed": s.qa_passed} for s in samples],
        "metrics": [{"name": m.name, "unit": m.unit, "label": m.label, "value": m.value, "note": m.note}
                    for m in metrics],
    }
    print(markdown(metrics))
    print(f"\nAlvo (não medido): {TARGET}")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
