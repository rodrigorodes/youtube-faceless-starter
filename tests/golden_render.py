"""Suporte do golden de render (VE-00): casos fixos, medição por ffprobe/QA e assinatura comparável.

Não é um teste (sem ``test_``): é importado por ``test_render_golden.py`` e por
``scripts/render_golden.py``. Roda só no container do renderer (precisa de ffmpeg e da fonte DejaVu).

Decisão D4 do plano VE: o golden **não** congela o digest nem o hash do MP4 entre versões do
código. Ele exige (a) **determinismo na mesma versão** — o mesmo caso compilado e renderizado
duas vezes dá o mesmo digest e a mesma assinatura de mídia — e (b) **paridade audiovisual**:
duração, quadros, resolução, codecs, áudio e loudness dentro do envelope medido em
``tests/golden/render_baseline.json``.

Os arquivos de entrada ficam em ``/tmp/ve00-golden/<caso>`` (caminho fixo): o digest do compilador
carrega os caminhos dos assets e do diretório de trabalho; um caminho variável o tornaria
incomparável entre execuções.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.studio.adapters.qa_ffmpeg import FfmpegQa  # noqa: E402
from app.studio.adapters.render_plan_ffmpeg import PlanFfmpegRenderer  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from test_render_plan_executor import spec_for  # noqa: E402

GOLDEN_ROOT = Path("/tmp/ve00-golden")

# nome -> (formato, duração da fala por cena, música ligada, textos)
CASES: dict[str, dict] = {
    "short_1scene_music": {"fmt": VideoFormat.short, "scene_seconds": (2.0,), "music": True, "texts": None},
    "long_2scenes_music": {
        "fmt": VideoFormat.long, "scene_seconds": (2.0, 1.5), "music": True,
        "texts": ("Primeira narração do vídeo de teste.", "Segunda narração, menor."),
    },
    "short_1scene_silent_music": {"fmt": VideoFormat.short, "scene_seconds": (2.0,), "music": False, "texts": None},
}

# Tolerâncias do envelope de paridade (o golden não é byte a byte).
DURATION_TOLERANCE_S = 0.05
LUFS_TOLERANCE = 1.5


def build_spec(name: str):
    """Spec determinístico do caso, em diretório fixo e limpo."""
    case = CASES[name]
    root = GOLDEN_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return spec_for(root, case["fmt"], scene_seconds=case["scene_seconds"], music=case["music"], texts=case["texts"])


def _ffprobe(path: Path) -> dict:
    run = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return json.loads(run.stdout)


def media_signature(path: Path, narration: Path | None = None) -> dict:
    """Assinatura de mídia: o que o ffprobe e o QA medem. Comparável com tolerância explícita."""
    info = _ffprobe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    qa = FfmpegQa().analyze(path, narration=narration)
    return {
        "video_codec": video["codec_name"],
        "pix_fmt": video["pix_fmt"],
        "width": int(video["width"]),
        "height": int(video["height"]),
        "frame_rate": video["r_frame_rate"],
        "frames": int(video["nb_read_frames"]),
        "has_audio": audio is not None,
        "audio_codec": audio["codec_name"] if audio else None,
        "audio_sample_rate": int(audio["sample_rate"]) if audio else None,
        "audio_channels": int(audio["channels"]) if audio else None,
        "duration_s": round(float(info["format"]["duration"]), 3),
        "integrated_lufs": qa.get("integrated_lufs"),
        "narration_lufs": qa.get("narration_lufs"),
        "silence_ratio": qa["silence_ratio"],
        "black_ratio": qa["black_ratio"],
    }


def render_case(name: str) -> dict:
    """Compila e renderiza o caso; devolve digest, forma do plano e assinatura de mídia."""
    spec = build_spec(name)
    renderer = PlanFfmpegRenderer()
    compiled = renderer.compile_spec(spec)
    out = renderer.render(spec, spec.work_dir / "final.mp4")
    return {
        "digest": compiled.digest(),
        "shots": len(compiled.shots),
        "format": compiled.format,
        "total_ticks": compiled.total_ticks,
        "mp4_sha256": _sha256(out),
        "media": media_signature(out, narration=spec.work_dir / "narration.wav"),
    }


def envelope(signature: dict) -> dict:
    """Parte da assinatura que vira fixture: valores medidos + os limites usados na comparação."""
    return {**signature, "_tolerances": {"duration_s": DURATION_TOLERANCE_S, "lufs": LUFS_TOLERANCE}}


def compare(expected: dict, actual: dict) -> list[str]:
    """Diferenças entre o envelope esperado e a assinatura medida (lista vazia = paridade)."""
    problems: list[str] = []
    exact = ("video_codec", "pix_fmt", "width", "height", "frame_rate", "frames", "has_audio",
             "audio_codec", "audio_sample_rate", "audio_channels")
    for key in exact:
        if expected[key] != actual[key]:
            problems.append(f"{key}: esperado {expected[key]!r}, obtido {actual[key]!r}")
    if abs(expected["duration_s"] - actual["duration_s"]) > DURATION_TOLERANCE_S:
        problems.append(f"duration_s: esperado {expected['duration_s']}, obtido {actual['duration_s']}")
    for key in ("integrated_lufs", "narration_lufs"):
        want, got = expected.get(key), actual.get(key)
        if (want is None) != (got is None):
            problems.append(f"{key}: esperado {want!r}, obtido {got!r}")
        elif want is not None and abs(want - got) > LUFS_TOLERANCE:
            problems.append(f"{key}: esperado {want} ± {LUFS_TOLERANCE}, obtido {got}")
    if actual["black_ratio"] > max(0.05, expected["black_ratio"] + 0.05):
        problems.append(f"black_ratio subiu: esperado {expected['black_ratio']}, obtido {actual['black_ratio']}")
    if actual["silence_ratio"] > expected["silence_ratio"] + 0.10:
        problems.append(f"silence_ratio subiu: esperado {expected['silence_ratio']}, obtido {actual['silence_ratio']}")
    return problems


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
