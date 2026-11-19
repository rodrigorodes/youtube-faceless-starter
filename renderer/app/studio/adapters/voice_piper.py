"""Voice via Piper (porta Voice). Envolve a síntese do modo rich; entra no fluxo do estúdio na P04."""
from pathlib import Path


class PiperVoice:
    name = "piper"

    def __init__(self, model: str):
        self.model = model  # a voz instalada na imagem do renderer é a do rich.py

    def speak(self, text: str, out_path: Path) -> float:
        if not text.strip():
            raise ValueError("text to speak is empty")
        from ... import rich  # import tardio: piper/numpy só carregam quando a voz é usada

        rich.synthesize_speech(text, out_path)
        return rich.wav_duration(out_path)
