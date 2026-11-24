#!/usr/bin/env python3
"""Script de amostragem visual e inspeção de frames do vídeo piloto (Onda 6).

Extrai N quadros em intervalos regulares ao longo do vídeo renderizado,
valida dimensões, canais e integridade de arquivo, e reporta evidência.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


def get_video_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    return float(data["format"]["duration"])


def sample_frames(video_path: Path, out_dir: Path, count: int = 6,
                  expected_size: tuple[int, int] = (1920, 1080)) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = get_video_duration(video_path)
    if duration <= 0:
        raise ValueError("Duração do vídeo deve ser positiva")

    # Calcula intervalos regulares (ex: 5%, 20%, 40%, 60%, 80%, 95%)
    ratios = [0.05, 0.20, 0.40, 0.60, 0.80, 0.95] if count == 6 else [
        (i + 0.5) / count for i in range(count)
    ]
    timestamps = [round(r * duration, 2) for r in ratios]

    sampled = []
    for idx, ts in enumerate(timestamps):
        frame_name = f"frame_{idx:02d}_{ts:.1f}s.png"
        frame_path = out_dir / frame_name
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(ts),
            "-i", str(video_path),
            "-vframes", "1",
            str(frame_path),
        ]
        subprocess.run(cmd, check=True)
        assert frame_path.is_file(), f"Falha ao extrair frame em {ts}s"

        # Validação do frame extraído
        with Image.open(frame_path) as img:
            w, h = img.size
            mode = img.mode
            fmt = img.format

        if (w, h) != expected_size:
            raise ValueError(f"Dimensões do frame {frame_path.name} ({w}x{h}) diferem de {expected_size}")

        size_bytes = frame_path.stat().st_size
        if size_bytes < 1000:
            raise ValueError(f"Frame {frame_path.name} excessivamente pequeno ({size_bytes} bytes)")

        sampled.append({
            "index": idx,
            "timestamp_s": ts,
            "path": str(frame_path),
            "width": w,
            "height": h,
            "format": fmt,
            "size_bytes": size_bytes,
        })

    return sampled


def main() -> int:
    parser = argparse.ArgumentParser(description="Amostragem de frames do vídeo piloto")
    parser.add_argument("--video", type=Path, required=True, help="Caminho do vídeo MP4")
    parser.add_argument("--out-dir", type=Path, default=Path("storage/pilot-frames"), help="Pasta de saída")
    parser.add_argument("--count", type=int, default=6, help="Número de frames a extrair")
    parser.add_argument("--width", type=int, default=1920, help="Largura esperada")
    parser.add_argument("--height", type=int, default=1080, help="Altura esperada")
    parser.add_argument("--json", action="store_true", help="Saída em formato JSON")

    args = parser.parse_args()
    if not args.video.is_file():
        print(f"Erro: arquivo de vídeo não encontrado: {args.video}", file=sys.stderr)
        return 1

    try:
        results = sample_frames(args.video, args.out_dir, count=args.count, expected_size=(args.width, args.height))
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"✓ {len(results)} frames amostrados com sucesso em {args.out_dir}:")
            for f in results:
                print(f"  - [{f['index']}] {f['timestamp_s']}s: {f['width']}x{f['height']} ({f['size_bytes']} bytes) -> {f['path']}")
        return 0
    except Exception as exc:
        print(f"Erro na amostragem: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
