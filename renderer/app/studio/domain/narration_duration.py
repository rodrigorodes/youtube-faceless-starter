"""Estimativa de narração por cena, sem síntese de voz nem calibração de TTS."""

from dataclasses import dataclass
import math
import re
import unicodedata
from collections.abc import Sequence

from .contracts import Scene

# Letras e números Unicode; hífens e apóstrofos internos unem uma palavra.
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


@dataclass(frozen=True)
class NarrationDurationEstimate:
    scene_seconds: tuple[float, ...]
    total_seconds: float


def estimate_narration_durations(
    scenes: Sequence[Scene], words_per_minute: float,
) -> NarrationDurationEstimate:
    """Estima segundos por cena e no total, sem modificar as cenas recebidas.

    O ritmo é uma hipótese configurável, não uma medição de voz ou pausas.
    """
    try:
        valid_rate = (
            not isinstance(words_per_minute, bool)
            and isinstance(words_per_minute, (int, float))
            and math.isfinite(words_per_minute)
            and words_per_minute > 0
        )
    except OverflowError:
        valid_rate = False
    if not valid_rate:
        raise ValueError("words_per_minute must be a finite positive number")

    durations = tuple(
        len(_WORD.findall(unicodedata.normalize("NFC", scene.narration))) * 60 / words_per_minute
        for scene in scenes
    )
    total = sum(durations)
    if not all(math.isfinite(duration) for duration in durations) or not math.isfinite(total):
        raise ValueError("estimated duration must be finite")
    return NarrationDurationEstimate(scene_seconds=durations, total_seconds=total)
