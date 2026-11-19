"""Regras puras de renderização: tempo das cenas, legendas por trecho, .srt e QA objetivo."""
import math
import re
from dataclasses import dataclass

from .contracts import QaReport, VideoFormat

FPS = 25
FADE_S = 0.25
LEAD, TAIL = 0.30, 0.50  # silêncio antes/depois de cada fala (s)
MAX_SECONDS = {VideoFormat.short: 175, VideoFormat.long: 1200}  # Shorts permitem até 180 s; folga de 5 s
SIZE = {VideoFormat.short: (1080, 1920), VideoFormat.long: (1920, 1080)}
MIN_SECONDS = 2.0
EXPECTED_TOLERANCE_S = 1.0
MIN_LUFS, MAX_LUFS = -45.0, -9.0  # abaixo: mudo; acima: estourado (o loudnorm mira -16)
MAX_SILENCE_RATIO, MAX_BLACK_RATIO = 0.6, 0.3


def scene_length(speech_seconds: float) -> float:
    """Duração da cena em quadros inteiros, para áudio e vídeo ficarem alinhados."""
    return math.ceil((LEAD + speech_seconds + TAIL) * FPS) / FPS


_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE = re.compile(r"(?<=[,;:])\s+")


def _wrap_words(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > max_chars:  # palavra maior que o limite: corta
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def split_chunks(text: str, max_chars: int = 42) -> list[str]:
    """Trechos de legenda: quebra em frases, depois em orações (vírgula etc.), depois por palavras."""
    chunks: list[str] = []
    for sentence in _SENTENCE.split(text.strip()):
        sentence = " ".join(sentence.split())
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        current = ""
        for clause in _CLAUSE.split(sentence):
            if len(clause) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(_wrap_words(clause, max_chars))
            elif current and len(current) + 1 + len(clause) <= max_chars:
                current = f"{current} {clause}"
            else:
                if current:
                    chunks.append(current)
                current = clause
        if current:
            chunks.append(current)
    return chunks


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def make_cues(text: str, start: float, speech_seconds: float, max_chars: int = 42) -> list[Cue]:
    """Tempo de cada trecho proporcional ao seu tamanho, dentro da janela da fala (sem alinhamento forçado por modelo)."""
    chunks = split_chunks(text, max_chars)
    if not chunks:
        return []
    begin, total = start + LEAD, float(sum(len(c) for c in chunks))
    cues, elapsed = [], 0
    for i, chunk in enumerate(chunks):
        cue_start = begin + speech_seconds * elapsed / total
        elapsed += len(chunk)
        cue_end = begin + speech_seconds * (elapsed / total if i < len(chunks) - 1 else 1.0)
        cues.append(Cue(cue_start, cue_end, chunk))
    return cues


def to_srt_time(seconds: float) -> str:
    ms = round(max(0.0, seconds) * 1000)
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{to_srt_time(c.start)} --> {to_srt_time(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1))


_REQUIRED = ("duration_s", "expected_s", "width", "height", "has_audio", "integrated_lufs", "silence_ratio", "black_ratio")


def evaluate_qa(metrics: dict, fmt: VideoFormat) -> QaReport:
    """Reprova vídeo mudo, estourado em duração, com resolução errada, quase todo em silêncio/preto ou sem áudio.
    Métrica ausente reprova (falha fechada)."""
    failures = [f"missing metric {key}" for key in _REQUIRED if key not in metrics]
    if not failures:
        duration, expected = metrics["duration_s"], metrics["expected_s"]
        lufs = metrics["integrated_lufs"]
        if not metrics["has_audio"]:
            failures.append("no audio stream")
        elif lufs is None or lufs < MIN_LUFS:
            failures.append(f"audio is silent (integrated loudness {lufs} LUFS)")
        elif lufs > MAX_LUFS:
            failures.append(f"audio too loud (integrated loudness {lufs} LUFS)")
        if metrics["has_audio"] and metrics["silence_ratio"] > MAX_SILENCE_RATIO:
            failures.append(f"too much silence ({metrics['silence_ratio']:.0%} of the video)")
        if metrics["black_ratio"] > MAX_BLACK_RATIO:
            failures.append(f"too much black ({metrics['black_ratio']:.0%} of the video)")
        if duration > MAX_SECONDS[fmt]:
            failures.append(f"duration {duration:.1f}s is above the {MAX_SECONDS[fmt]}s limit for {fmt.value}")
        if duration < MIN_SECONDS:
            failures.append(f"duration {duration:.1f}s is below {MIN_SECONDS}s")
        if abs(duration - expected) > EXPECTED_TOLERANCE_S:
            failures.append(f"duration {duration:.1f}s differs from the expected {expected:.1f}s")
        if (metrics["width"], metrics["height"]) != SIZE[fmt]:
            failures.append(f"resolution {metrics['width']}x{metrics['height']} is not {SIZE[fmt][0]}x{SIZE[fmt][1]} for {fmt.value}")
    clean = {k: v for k, v in metrics.items() if isinstance(v, (int, float, bool)) or v is None}
    return QaReport(passed=not failures, failures=failures, metrics=clean)
