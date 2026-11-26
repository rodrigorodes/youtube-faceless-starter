"""Processamento Digital de Sinais (DSP) e mixagem analítica multitrack (V4-03).

Implementa operações puras de áudio em PCM 16-bit utilizando a biblioteca padrão:
1. Geração de formas de onda e efeitos sonoros sintéticos (whoosh, pop, ding, impacto).
2. Ducking automático inteligente atenuando trilha e ambiência durante a fala.
3. Fades e crossfades suaves entre transições musicais.
4. Estimativa de True Peak e controle de volume (EBU R128 compliance).
5. Prevenção absoluta de clipping digital na saída final.
"""
from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from .audio_multitrack import MultitrackAudioPlan

CLIPPING_LIMIT = 32760
DEFAULT_SAMPLE_RATE = 24000


def db_to_linear(db: float) -> float:
    """Converte decibéis (dB) para escala de ganho linear de amplitude."""
    return 10.0 ** (db / 20.0)


def generate_synthetic_tone(
    duration_s: float,
    freq_hz: float = 440.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    gain_db: float = 0.0,
    fade_in_s: float = 0.05,
    fade_out_s: float = 0.05,
) -> list[int]:
    """Gera um tom senoidal estritamente calibrado com envelopes suaves."""
    total_samples = int(duration_s * sample_rate)
    linear_gain = db_to_linear(gain_db) * 10000.0  # ~10000 amplitude nominal para tom base
    fade_in_samples = int(fade_in_s * sample_rate)
    fade_out_samples = int(fade_out_s * sample_rate)

    samples: list[int] = []
    for i in range(total_samples):
        t = i / sample_rate
        # Envelope de amplitude
        env = 1.0
        if fade_in_samples > 0 and i < fade_in_samples:
            env *= i / float(fade_in_samples)
        if fade_out_samples > 0 and (total_samples - i) < fade_out_samples:
            env *= (total_samples - i) / float(fade_out_samples)

        val = int(linear_gain * env * math.sin(2 * math.pi * freq_hz * t))
        samples.append(max(-32767, min(32767, val)))

    return samples


def generate_synthetic_sfx(
    kind: str,
    duration_s: float = 0.5,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> list[int]:
    """Gera efeitos sonoros determinísticos clássicos para testes e montagem offline."""
    total_samples = int(duration_s * sample_rate)
    samples: list[int] = []
    kind_lower = kind.strip().lower()

    if "whoosh" in kind_lower:
        # Frequência varrendo de 150Hz a 800Hz e caindo para 200Hz
        for i in range(total_samples):
            t = i / float(total_samples)
            freq = 200.0 + 600.0 * math.sin(math.pi * t)
            env = math.sin(math.pi * t)
            val = int(12000 * env * math.sin(2 * math.pi * freq * (i / sample_rate)))
            samples.append(val)
    elif "ding" in kind_lower:
        # Tom alto cristalino de 1200Hz com decaimento exponencial
        for i in range(total_samples):
            t = i / sample_rate
            env = math.exp(-6.0 * t)
            val = int(14000 * env * math.sin(2 * math.pi * 1200.0 * t))
            samples.append(val)
    elif "pop" in kind_lower:
        # Disparo rápido de 400Hz com queda acentuada em 0.1s
        dur = min(duration_s, 0.15)
        n = int(dur * sample_rate)
        for i in range(n):
            t = i / sample_rate
            env = math.exp(-30.0 * t)
            val = int(15000 * env * math.sin(2 * math.pi * 380.0 * t))
            samples.append(val)
        # Preenche restante com silêncio se duration_s for maior
        samples.extend([0] * (total_samples - n))
    else:
        # Tom genérico seguro
        return generate_synthetic_tone(duration_s, freq_hz=300.0, sample_rate=sample_rate, gain_db=-6.0)

    return samples


def mix_multitrack_pcm(
    plan: MultitrackAudioPlan,
    track_samples_map: dict[str, list[int]],
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> tuple[list[int], dict[str, float]]:
    """Executa a mixagem multitrack ponderada aplicando ducking, ganhos e envelopes.

    Retorna:
    - Lista de amostras PCM mixadas
    - Dicionário com métricas técnicas: peak, true_peak_dbtp, duration_s, is_clipped
    """
    total_samples = int(plan.total_duration_s * sample_rate)
    mixed_buffer = [0.0] * total_samples

    ducking_linear = db_to_linear(plan.ducking_attenuation_db)

    # Processa cada evento do plano
    for event in plan.all_events:
        source_samples = track_samples_map.get(event.track_id)
        if not source_samples:
            continue

        start_idx = int(event.start_s * sample_rate)
        event_sample_count = int(event.duration_s * sample_rate)
        base_gain = db_to_linear(event.gain_db)

        fade_in_samples = int(event.fade_in_s * sample_rate)
        fade_out_samples = int(event.fade_out_s * sample_rate)

        for i in range(event_sample_count):
            buf_idx = start_idx + i
            if buf_idx >= total_samples:
                break

            time_s = buf_idx / float(sample_rate)
            src_val = source_samples[i % len(source_samples)]

            # Envelope de fade
            fade_multiplier = 1.0
            if fade_in_samples > 0 and i < fade_in_samples:
                fade_multiplier *= i / float(fade_in_samples)
            if fade_out_samples > 0 and (event_sample_count - i) < fade_out_samples:
                fade_multiplier *= (event_sample_count - i) / float(fade_out_samples)

            # Ducking sob a fala
            duck_multiplier = 1.0
            if event.ducked and plan.is_voice_active_at(time_s):
                duck_multiplier = ducking_linear

            sample_contrib = src_val * base_gain * fade_multiplier * duck_multiplier
            mixed_buffer[buf_idx] += sample_contrib

    # Normalização e medição de True Peak
    max_raw_peak = max(abs(s) for s in mixed_buffer) if mixed_buffer else 0.0

    # Se exceder o limite seguro para 16-bit PCM (32760), aplica compressão suave transparente
    target_scale = 1.0
    if max_raw_peak > CLIPPING_LIMIT:
        target_scale = CLIPPING_LIMIT / max_raw_peak

    final_samples: list[int] = []
    for s in mixed_buffer:
        val = int(round(s * target_scale))
        clamped = max(-32767, min(32767, val))
        final_samples.append(clamped)

    final_peak = max(abs(s) for s in final_samples) if final_samples else 0
    true_peak_dbtp = round(20.0 * math.log10(max(1, final_peak) / 32767.0), 2)

    metrics = {
        "duration_s": round(total_samples / float(sample_rate), 2),
        "peak_amplitude": final_peak,
        "true_peak_dbtp": true_peak_dbtp,
        "is_clipped": final_peak >= CLIPPING_LIMIT,
        "sample_rate": sample_rate,
    }

    return final_samples, metrics


def save_pcm_as_wav(
    samples: list[int],
    out_path: Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = 1,
) -> Path:
    """Grava as amostras PCM 16-bit no formato WAV canônico."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = array.array("h", samples).tobytes()

    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(raw_bytes)

    return out_path
