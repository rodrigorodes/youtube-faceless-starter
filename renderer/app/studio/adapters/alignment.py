from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..domain.captions import WordTiming

__all__ = [
    "WordAlignmentService",
]

logger = logging.getLogger(__name__)


class WordAlignmentService:
    """Serviço híbrido de alinhamento temporal de palavras (determinístico e Whisper sidecar)."""

    def __init__(
        self,
        whisper_url: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.whisper_url = whisper_url.rstrip("/") if whisper_url else None
        self.http_client = http_client
        self.timeout = timeout

    def align_words(
        self,
        text: str,
        audio_duration_ms: int,
        audio_path: Path | str | None = None,
    ) -> list[WordTiming]:
        """Calcula as marcações temporais de cada palavra normalizadas pela duração do áudio."""
        clean_text = text.strip()
        if not clean_text or audio_duration_ms <= 0:
            return []

        words = clean_text.split()
        if not words:
            return []

        path = Path(audio_path) if audio_path is not None else None

        if self.whisper_url and path and path.exists() and path.is_file():
            whisper_timings = self._try_whisper_align(words=words, text=clean_text, audio_path=path)
            if whisper_timings is not None:
                return whisper_timings

        return self._align_native(words, audio_duration_ms)

    def _try_whisper_align(
        self,
        words: list[str],
        text: str,
        audio_path: Path,
    ) -> list[WordTiming] | None:
        url = f"{self.whisper_url}/align"
        try:
            with open(audio_path, "rb") as f:
                files = {"audio": (audio_path.name, f.read(), "audio/wav")}
            data = {"text": text}

            if self.http_client is not None:
                resp = self.http_client.post(
                    url,
                    files=files,
                    data=data,
                    timeout=self.timeout,
                )
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        url,
                        files=files,
                        data=data,
                    )

            if resp.status_code != 200:
                logger.warning(
                    "Whisper sidecar returned non-200 status code: %s",
                    resp.status_code,
                )
                return None

            raw_data = resp.json()
            items: list = []
            if isinstance(raw_data, list):
                items = raw_data
            elif isinstance(raw_data, dict) and "words" in raw_data and isinstance(raw_data["words"], list):
                items = raw_data["words"]
            else:
                logger.warning("Whisper sidecar response format unrecognized: %r", raw_data)
                return None

            if not items:
                return None

            # Divergência de texto / contagem de palavras: fallback para o determinístico
            if len(items) != len(words):
                logger.warning(
                    "Whisper word count mismatch: expected %d, got %d",
                    len(words),
                    len(items),
                )
                return None

            timings: list[WordTiming] = []
            for item in items:
                if not isinstance(item, dict):
                    return None
                w = str(item.get("word", "")).strip()
                if not w:
                    return None
                start_sec = float(item.get("start", 0.0))
                end_sec = float(item.get("end", start_sec))
                start_ms = max(0, int(round(start_sec * 1000)))
                end_ms = max(start_ms, int(round(end_sec * 1000)))
                duration_ms = max(0, end_ms - start_ms)
                timings.append(WordTiming(word=w, start_ms=start_ms, duration_ms=duration_ms))

            return timings
        except Exception as exc:
            logger.warning("Whisper alignment failed, falling back to native mode: %s", exc)
            return None

    def _align_native(self, words: list[str], audio_duration_ms: int) -> list[WordTiming]:
        weights: list[int] = []
        for word in words:
            weight = len(word)
            if word.endswith((".", "!", "?", "...")):
                weight += 6
            elif word.endswith((",", ";")):
                weight += 3
            weight = max(2, weight)
            weights.append(weight)

        total_weight = sum(weights)
        if total_weight <= 0:
            return []

        # Cálculo da duração proporcional por palavra
        durations = [int(round(audio_duration_ms * (w / total_weight))) for w in weights]

        if audio_duration_ms >= len(words):
            for i in range(len(durations)):
                if durations[i] < 1:
                    durations[i] = 1

        # Ajusta a última palavra para a soma bater exatamente audio_duration_ms
        diff = audio_duration_ms - sum(durations)
        durations[-1] += diff

        # Se a última palavra ficou <= 0 por ajuste negativo, redistribui de trás para frente
        if durations[-1] <= 0 and audio_duration_ms >= len(words):
            needed = 1 - durations[-1]
            durations[-1] = 1
            for i in range(len(durations) - 2, -1, -1):
                can_reduce = durations[i] - 1
                reduction = min(can_reduce, needed)
                durations[i] -= reduction
                needed -= reduction
                if needed == 0:
                    break

        result: list[WordTiming] = []
        current_start = 0
        for word, dur in zip(words, durations):
            result.append(WordTiming(word=word, start_ms=current_start, duration_ms=dur))
            current_start += dur

        return result
