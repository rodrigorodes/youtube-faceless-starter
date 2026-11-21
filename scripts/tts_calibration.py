#!/usr/bin/env python3
"""Calibração real da voz de narração: mede o Piper pt_BR-faber-medium e compara com a estimativa.

Uso (imagem com `piper-tts` 1.8.0 e a voz do produto):

    PIPER_VOICE=/opt/voices/pt_BR-faber-medium.onnx PYTHONPATH=renderer \
        python3 scripts/tts_calibration.py --out .superpowers/.../tts-calibracao-evidence-run1.json

O script sintetiza cada texto do corpus (`scripts/tts_calibration_samples.json`)
separadamente, do mesmo jeito que o renderer faz por cena (`PiperVoice.speak` por
`Scene.narration`), e mede os quadros do WAV. Não usa rede e não altera nada.

Saída: por amostra, palavras (mesma contagem do domínio), duração real, estimativa
a 150 palavras/minuto, erro relativo, palavras/minuto efetivas; e a regressão
`segundos = intercepto + palavras * b + pausas * c`. A regressão alimenta as
constantes de `app/studio/domain/narration_duration.py`.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
import wave
from importlib.metadata import PackageNotFoundError, version as dist_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.domain.narration_duration import (  # noqa: E402
    _WORD,  # a contagem tem de ser a mesma do domínio, não uma segunda regra
    _word_count,
    estimate_text_durations,
)

SAMPLES = ROOT / "scripts" / "tts_calibration_samples.json"
# Mesma regra do domínio: marcas que o TTS costuma transformar em pausa.
PAUSE = re.compile(r"[.,;:!?…]+|—|–")
MIN_PEAK = 300  # de 32767, a mesma guarda de silêncio do PiperVoice


def require_texts(value: object) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(t, str) for t in value):
        raise SystemExit(f"campo de textos inválido: {value!r}")
    return value


def count_words(texts: list[str]) -> int:
    return sum(_word_count(text) for text in texts)


def count_pauses(texts: list[str]) -> int:
    return sum(len(PAUSE.findall(text)) for text in texts)


def measured_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() == 2:
            samples = array.array("h", wav.readframes(wav.getnframes()))
        else:
            samples = array.array("h")
        seconds = wav.getnframes() / wav.getframerate()
    if not samples or max(max(samples), -min(samples)) < MIN_PEAK:
        raise SystemExit(f"voz produziu silêncio em {path}")
    return seconds


def synthesize(voice, texts: list[str], workdir: Path) -> tuple[list[float], float]:
    """Sintetiza cada texto num WAV próprio e devolve as durações e o relógio de parede."""
    durations, started = [], None
    for idx, text in enumerate(texts):
        out = workdir / f"utterance-{idx}.wav"
        began = time.monotonic()
        if started is None:
            started = began
        with wave.open(str(out), "wb") as wav:
            voice.synthesize_wav(text, wav)
        durations.append(measured_seconds(out))
    return durations, (time.monotonic() - started if started is not None else 0.0)


def ols(observations: list[dict]) -> dict:
    """Regressão por mínimos quadrados de segundos ~ 1 + palavras + pausas."""
    if len(observations) < 4:
        raise SystemExit("poucas observações para a regressão")
    rows = [[1.0, float(o["words"]), float(o["pauses"])] for o in observations]
    target = [float(o["seconds"]) for o in observations]
    size = 3
    normal = [[sum(row[i] * row[j] for row in rows) for j in range(size)] for i in range(size)]
    rhs = [sum(row[i] * y for row, y in zip(rows, target)) for i in range(size)]
    # Eliminação de Gauss com pivô parcial.
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(normal[r][col]))
        if abs(normal[pivot][col]) < 1e-12:
            raise SystemExit("sistema singular na regressão")
        normal[col], normal[pivot] = normal[pivot], normal[col]
        rhs[col], rhs[pivot] = rhs[pivot], rhs[col]
        for row in range(col + 1, size):
            factor = normal[row][col] / normal[col][col]
            for k in range(col, size):
                normal[row][k] -= factor * normal[col][k]
            rhs[row] -= factor * rhs[col]
    solution = [0.0] * size
    for row in reversed(range(size)):
        solution[row] = (rhs[row] - sum(normal[row][k] * solution[k] for k in range(row + 1, size))) / normal[row][row]
    intercept, per_word, per_pause = solution
    return {
        "intercept_seconds": intercept,
        "seconds_per_word": per_word,
        "seconds_per_pause": per_pause,
        "words_per_minute": 60.0 / per_word if per_word > 0 else math.inf,
        "pause_marks": ".,;:!?… — –",
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="grava o JSON de evidência")
    parser.add_argument("--samples", type=Path, default=SAMPLES)
    parser.add_argument("--voice", default=os.getenv("PIPER_VOICE", "/opt/voices/pt_BR-faber-medium.onnx"))
    args = parser.parse_args(argv)

    try:
        import piper  # noqa: F401
    except ImportError:
        print("piper-tts não instalado neste Python; rode na imagem do renderer.", file=sys.stderr)
        return 2
    voice_path = Path(args.voice)
    if not voice_path.exists():
        print(f"voz ausente: {voice_path} (defina PIPER_VOICE)", file=sys.stderr)
        return 2
    corpus = json.loads(args.samples.read_text(encoding="utf-8"))
    expected_sha = corpus.get("model_sha256")
    digest = hashlib.sha256(voice_path.read_bytes()).hexdigest()
    if expected_sha and digest != expected_sha:
        print(f"voz {voice_path} tem sha256 {digest}; a calibração exige {expected_sha}", file=sys.stderr)
        return 2
    try:
        piper_version = dist_version("piper-tts")
    except PackageNotFoundError:  # distribuição sem metadados instalados
        piper_version = getattr(piper, "__version__", corpus.get("piper_version"))
    reference = float(corpus["words_per_minute_reference"])
    from piper import PiperVoice
    voice = PiperVoice.load(str(voice_path))

    report: dict = {
        "voice": corpus["voice"],
        "voice_path": str(voice_path),
        "piper_version": piper_version,
        "python_version": platform.python_version(),
        "reference_words_per_minute": reference,
        "model_sha256": digest,
        "config_sha256": hashlib.sha256(Path(f"{voice_path}.json").read_bytes()).hexdigest()
        if Path(f"{voice_path}.json").exists() else None,
        "samples": [],
        "observations": [],
    }
    with tempfile.TemporaryDirectory(prefix="tts-calibration-") as tmp:
        for sample in corpus["samples"]:
            texts = require_texts(sample["texts"])
            durations, synth_seconds = synthesize(voice, texts, Path(tmp))
            words = count_words(texts)
            pauses = count_pauses(texts)
            estimate = estimate_text_durations(texts, reference).total_seconds
            real = sum(durations)
            entry = {
                "id": sample["id"],
                "kind": sample["kind"],
                "description": sample["description"],
                "utterances": len(texts),
                "words": words,
                "pause_marks": pauses,
                "estimated_seconds_at_reference": estimate,
                "measured_seconds": real,
                "measured_utterance_seconds": durations,
                "relative_error_estimate_vs_real": (estimate - real) / real,
                "effective_words_per_minute": words * 60.0 / real,
                "ratio_real_over_estimate": real / estimate,
                "synthesis_wall_seconds": synth_seconds,
            }
            report["samples"].append(entry)
            for text, seconds in zip(texts, durations):
                report["observations"].append({
                    "sample": sample["id"],
                    "words": _word_count(text),
                    "pauses": len(PAUSE.findall(text)),
                    "seconds": seconds,
                    "chars": len(text),
                })

    observations = report["observations"]
    total_words = sum(o["words"] for o in observations)
    total_seconds = sum(o["seconds"] for o in observations)
    report["pooled"] = {
        "observations": len(observations),
        "words": total_words,
        "seconds": total_seconds,
        "effective_words_per_minute": total_words * 60.0 / total_seconds,
    }
    report["regression"] = ols(observations)

    # Erro do modelo calibrado (intercepto + palavras + pausas) nas amostras.
    regression = report["regression"]
    for entry, sample in zip(report["samples"], corpus["samples"]):
        texts = sample["texts"]
        words, pauses = count_words(texts), count_pauses(texts)
        model = (regression["intercept_seconds"] + words * regression["seconds_per_word"]
                 + pauses * regression["seconds_per_pause"])
        entry["calibrated_model_seconds"] = model
        entry["relative_error_calibrated_vs_real"] = (model - entry["measured_seconds"]) / entry["measured_seconds"]

    worst = max(abs(e["relative_error_calibrated_vs_real"]) for e in report["samples"])
    worst_pure = max(abs(e["relative_error_estimate_vs_real"]) for e in report["samples"])
    report["summary"] = {
        "max_abs_relative_error_estimate_at_reference": worst_pure,
        "max_abs_relative_error_calibrated": worst,
        "samples": len(report["samples"]),
        "utterances": len(observations),
    }

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))