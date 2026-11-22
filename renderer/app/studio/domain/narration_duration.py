"""Estimativa de duração da narração: hipótese por palavras/minuto e modelo medido do TTS.

Duas camadas, de propósito:

- ``estimate_text_durations``/``estimate_narration_durations`` são a **hipótese**
  configurável (palavras × 60 / ritmo). Nada de voz, pausa ou prosódia entra aqui;
  é a mesma contagem usada pelo fluxo curto e pelo roteiro longo.
- ``estimate_voice_durations`` é a **medição** da voz do produto
  (``piper:pt_BR-faber-medium``, piper-tts 1.8.0): silêncio de borda por síntese,
  ritmo de fala medido e custo medido de cada marca de pausa. Foi derivado de
  26 sínteses reais (7 amostras, 1.403 palavras) por regressão linear; o corpus e
  os números estão em ``scripts/tts_calibration_samples.json`` e no relatório
  ``tts-calibracao-report.md``. Reproduza com ``scripts/tts_calibration.py``.

Nenhuma das duas é "duração exata": a voz é fixa, mas prosódia, números e siglas
mudam a expansão. A tolerância medida está declarada no teste
``tests/test_tts_calibration.py``.
"""

from dataclasses import dataclass
import math
import re
import unicodedata
from collections.abc import Sequence

from .contracts import Scene

# Letras e números Unicode; hífens e apóstrofos internos unem uma palavra.
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")
# Marcas que o Piper transforma em pausa. Uma sequência (``...``) conta uma vez.
_PAUSE = re.compile(r"[.,;:!?…]+|—|–")

# --- Calibração medida do Piper do produto ------------------------------------
# Medido em 2026-11-20 na imagem de testes (piper-tts 1.8.0, modelo
# pt_BR-faber-medium, sha256 75e913eb...b8ffc — o mesmo hash conferido no
# Dockerfile). Amostras: texto curto, curto pontuado, frases curtas, prosa com e
# sem pontuação, números/siglas e um roteiro de ~480 s em 20 cenas. Três execuções;
# os valores abaixo são a média delas (o Piper varia a duração entre execuções:
# até +3,8% no texto de 8 palavras, menos de 1% no roteiro longo).
# (as duas constantes de identidade da voz medida ficam em ``app.studio.tts_calibration``,
#  fora do domínio: o domínio não cita nome de fornecedor.)
# Ritmo de fala sem pausas (regressões: 0,2769 / 0,2762 / 0,2760 s por palavra).
MEASURED_SPEECH_WORDS_PER_MINUTE = 217.1
# Custo médio de cada marca de pausa (regressões: 0,4016 / 0,3943 / 0,3952 s; par
# com/sem pontuação do mesmo texto: 0,31 a 0,34 s por marca).
MEASURED_PAUSE_SECONDS = 0.40
# Silêncio de borda por síntese (regressões: 0,577 / 0,672 / 0,693 s por utterance).
MEASURED_UTTERANCE_OVERHEAD_SECONDS = 0.65
# Ritmo efetivo do corpus inteiro, com pausas: 1.403 palavras em ~489,4 s nas três
# execuções (172,0 / 172,0 / 171,8). É o padrão realista para planejar um roteiro;
# a hipótese antiga era 150.
MEASURED_EFFECTIVE_WORDS_PER_MINUTE = 172.0


@dataclass(frozen=True)
class NarrationDurationEstimate:
    scene_seconds: tuple[float, ...]
    total_seconds: float


def _validate_rate(words_per_minute: float) -> float:
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
    return words_per_minute


def _word_count(text: str) -> int:
    return len(_WORD.findall(unicodedata.normalize("NFC", text)))


def estimate_text_durations(
    texts: Sequence[str], words_per_minute: float,
) -> NarrationDurationEstimate:
    """Estima segundos por texto e no total, sem modificar as entradas.

    O ritmo é uma hipótese configurável, não uma medição de voz ou pausas. É a
    contagem única reutilizada pelo fluxo curto (``estimate_narration_durations``)
    e pelo roteiro longo. Para a voz real do produto use ``estimate_voice_durations``.
    """
    rate = _validate_rate(words_per_minute)
    durations = tuple(_word_count(text) * 60 / rate for text in texts)
    total = sum(durations)
    if not all(math.isfinite(duration) for duration in durations) or not math.isfinite(total):
        raise ValueError("estimated duration must be finite")
    return NarrationDurationEstimate(scene_seconds=durations, total_seconds=total)


def _voice_duration(text: str) -> float:
    words = _word_count(text)
    # Texto sem palavra não fala nem pausa: só o silêncio de borda da síntese.
    pauses = len(_PAUSE.findall(text)) if words else 0
    return (
        MEASURED_UTTERANCE_OVERHEAD_SECONDS
        + words * 60 / MEASURED_SPEECH_WORDS_PER_MINUTE
        + pauses * MEASURED_PAUSE_SECONDS
    )


def estimate_voice_durations(texts: Sequence[str]) -> NarrationDurationEstimate:
    """Estima a duração do WAV que o Piper do produto gera para cada texto.

    Usa a regressão medida (``MEASURED_*``): cada texto é uma síntese, então paga
    o silêncio de borda uma vez, fala no ritmo medido e para em cada marca de
    pausa. A cena do vídeo soma ainda ``LEAD``/``TAIL`` do renderer, que não estão
    aqui: esta é a duração da fala, como ``wav_duration`` no renderer.
    """
    durations = tuple(_voice_duration(text) for text in texts)
    return NarrationDurationEstimate(scene_seconds=durations, total_seconds=sum(durations))


def estimate_narration_durations(
    scenes: Sequence[Scene], words_per_minute: float,
) -> NarrationDurationEstimate:
    """Estima segundos por cena e no total, sem modificar as cenas recebidas.

    O ritmo é uma hipótese configurável, não uma medição de voz ou pausas.
    """
    return estimate_text_durations([scene.narration for scene in scenes], words_per_minute)