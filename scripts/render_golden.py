#!/usr/bin/env python3
"""Gera o baseline do golden de render (VE-00). Roda DENTRO do container do renderer.

    docker run --rm -v "$PWD":/w:ro -w /w -e PYTHONPATH=/w/renderer -e PYTHONDONTWRITEBYTECODE=1 \
        --entrypoint python faceless-renderer-pytest:test scripts/render_golden.py > out.json

Saída (stdout, JSON): para cada caso, o render medido **duas vezes** (determinismo) e o
envelope que vira ``tests/golden/render_baseline.json``. Não grava nada no repositório: quem
chama decide onde salvar o resultado.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import golden_render as g  # noqa: E402


def _tool_version(cmd: list[str]) -> str:
    run = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return run.stdout.splitlines()[0]


def main() -> int:
    result = {
        "ffmpeg": _tool_version(["ffmpeg", "-version"]),
        "ffprobe": _tool_version(["ffprobe", "-version"]),
        "cases": {},
    }
    for name in g.CASES:
        first, second = g.render_case(name), g.render_case(name)
        result["cases"][name] = {
            "digest": first["digest"],
            "digest_stable": first["digest"] == second["digest"],
            "signature_stable": first["media"] == second["media"],
            "mp4_byte_identical": first["mp4_sha256"] == second["mp4_sha256"],
            "shots": first["shots"],
            "format": first["format"],
            "total_ticks": first["total_ticks"],
            "envelope": g.envelope(first["media"]),
        }
    json.dump(result, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
