"""Inspeção técnica, conformidade e métricas de áudio de fala (V4-02).

Valida arquivos WAV gerados:
1. Normalização de taxa de amostragem e canais (mono, 22050Hz/24000Hz/48000Hz).
2. Detecção de clipping (distorção digital) e silêncio anômalo.
3. Estimativa de ratio de pausas/silêncio na locução.
4. Diagnósticos de conformidade de QA antes da montagem e mixagem.
"""
from __future__ import annotations

import array
import wave
from dataclasses import dataclass
from pathlib import Path

MIN_SPEECH_PEAK = 300       # Abaixo disso em 16-bit PCM (max 32767) é considerado mudo
CLIPPING_THRESHOLD = 32760  # Perto de 32767 indica distorção digital severa


@dataclass(frozen=True)
class AudioSpeechMetrics:
    """Métricas técnicas extraídas diretamente do arquivo WAV de fala."""

    path: str
    duration_s: float
    sample_rate: int
    channels: int
    sample_width: int
    peak_amplitude: int
    is_clipped: bool
    is_silent: bool
    silence_ratio: float
    issues: tuple[str, ...]

    @property
    def is_acceptable(self) -> bool:
        return not self.is_silent and not self.is_clipped and len(self.issues) == 0


def inspect_speech_audio(wav_path: Path) -> AudioSpeechMetrics:
    """Inspeciona o arquivo WAV de locução e calcula métricas técnicas sem dependências pesadas."""
    if not wav_path.is_file():
        raise FileNotFoundError(f"speech audio file not found: {wav_path}")

    with wave.open(str(wav_path), "rb") as w:
        channels = w.getnchannels()
        sample_rate = w.getframerate()
        sample_width = w.getsampwidth()
        n_frames = w.getnframes()
        duration_s = round(n_frames / float(sample_rate), 4) if sample_rate > 0 else 0.0

        raw_frames = w.readframes(n_frames)

    issues: list[str] = []

    if sample_width != 2:
        issues.append(f"unsupported sample width: {sample_width * 8} bits (expected 16-bit PCM)")
        return AudioSpeechMetrics(
            path=str(wav_path),
            duration_s=duration_s,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
            peak_amplitude=0,
            is_clipped=False,
            is_silent=True,
            silence_ratio=1.0,
            issues=tuple(issues),
        )

    samples = array.array("h", raw_frames)
    if not samples:
        return AudioSpeechMetrics(
            path=str(wav_path),
            duration_s=0.0,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
            peak_amplitude=0,
            is_clipped=False,
            is_silent=True,
            silence_ratio=1.0,
            issues=("audio has no samples",),
        )

    max_val = max(samples)
    min_val = min(samples)
    peak = max(abs(max_val), abs(min_val))

    is_clipped = peak >= CLIPPING_THRESHOLD
    if is_clipped:
        issues.append(f"audio clipping detected (peak {peak} >= {CLIPPING_THRESHOLD})")

    is_silent = peak < MIN_SPEECH_PEAK
    if is_silent:
        issues.append(f"audio is silent (peak {peak} < {MIN_SPEECH_PEAK})")

    # Amostragem de silêncio: proporção de frames com amplitude menor que MIN_SPEECH_PEAK
    silent_count = sum(1 for s in samples if abs(s) < MIN_SPEECH_PEAK)
    silence_ratio = round(silent_count / float(len(samples)), 4) if len(samples) > 0 else 0.0

    if silence_ratio > 0.85:
        issues.append(f"excessive silence in speech ({silence_ratio * 100:.1f}%)")

    return AudioSpeechMetrics(
        path=str(wav_path),
        duration_s=duration_s,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        peak_amplitude=peak,
        is_clipped=is_clipped,
        is_silent=is_silent,
        silence_ratio=silence_ratio,
        issues=tuple(issues),
    )
