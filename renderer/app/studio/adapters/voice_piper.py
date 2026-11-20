"""Voice via Piper (porta Voice). Envolve a síntese do modo rich; entra no fluxo do estúdio na P04."""
import array
import threading
import wave
from pathlib import Path

_LOCK = threading.Lock()  # o modelo do Piper (rich._voice) é global e o espeak pode não ser thread-safe
MIN_PEAK = 300  # de 32767: abaixo disso a fala é silêncio (voz que falhou sem erro)


class PiperVoice:
    name = "piper"

    def __init__(self, model: str):
        self.model = model  # a voz instalada na imagem do renderer é a do rich.py

    def speak(self, text: str, out_path: Path) -> float:
        if not text.strip():
            raise ValueError("text to speak is empty")
        from ... import rich  # import tardio: piper/numpy só carregam quando a voz é usada

        with _LOCK:
            rich.synthesize_speech(text, out_path)
        with wave.open(str(out_path), "rb") as w:
            samples = array.array("h", w.readframes(w.getnframes())) if w.getsampwidth() == 2 else array.array("h")
        if not samples or max(max(samples), -min(samples)) < MIN_PEAK:
            raise RuntimeError("voice produced silence")  # a trilha musical esconderia isso do QA do vídeo
        return rich.wav_duration(out_path)
