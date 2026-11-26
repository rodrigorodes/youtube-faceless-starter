"""Adaptador para síntese neural Kokoro (V4-02 / INT-02).

Provedor neural local de alta fidelidade e custo zero ($0.00).
Implementa a porta NeuralVoice.

Conforme auditoria A01 (INT-02):
- Se o pacote nativo ou pesos não estiverem instalados, lança ModelUnavailable
  com erro semântico explícito, recusando gerar ondas senoidais como fala neural.
- O tom sintético de teste só é permitido se explicitamente habilitado via
  allow_synthetic_fixture=True para isolamento exclusivo em fixtures unitárias.
"""
from __future__ import annotations

import array
import importlib.util
import logging
import math
import wave
from pathlib import Path

from ..application.ports import ModelUnavailable, NeuralVoice

logger = logging.getLogger(__name__)


def is_kokoro_installed() -> bool:
    """Verifica se o pacote kokoro está disponível no ambiente Python."""
    return importlib.util.find_spec("kokoro") is not None


class KokoroVoice:
    name = "kokoro"

    def __init__(
        self,
        model: str = "pt_br-af_bella",
        speed: float = 1.0,
        allow_synthetic_fixture: bool = False,
    ) -> None:
        self.model = model
        self.speed = max(0.5, min(2.0, speed))
        self.allow_synthetic_fixture = allow_synthetic_fixture

    def supported_voices(self) -> tuple[str, ...]:
        return ("pt_br-af_bella", "pt_br-am_adam", "en_af_heart")

    def cost_estimate(self, text: str) -> float:
        return 0.0  # Provedor local offline gratuito

    def speak(self, text: str, out_path: Path) -> float:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text to speak is empty")

        if is_kokoro_installed():
            try:
                import kokoro  # type: ignore
                return self._synthesize_native(cleaned, out_path)
            except Exception as exc:
                logger.warning("Falha na síntese nativa do Kokoro: %s", exc)
                if not self.allow_synthetic_fixture:
                    raise ModelUnavailable(
                        f"Falha na síntese nativa do Kokoro ({exc}); "
                        "use o provedor validado piper para síntese local garantida"
                    ) from exc
                return self._synthesize_deterministic_pcm(cleaned, out_path)

        # Kokoro não instalado
        if not self.allow_synthetic_fixture:
            raise ModelUnavailable(
                "pacote kokoro não instalado no ambiente local; "
                "instale os pesos/pacote ou selecione o provedor validado piper"
            )

        logger.warning(
            "Kokoro não instalado; gerando tom sintético EXCLUSIVAMENTE para fixture de teste autorizada"
        )
        return self._synthesize_deterministic_pcm(cleaned, out_path)

    def _synthesize_native(self, text: str, out_path: Path) -> float:
        import kokoro  # type: ignore
        # Quando a biblioteca nativa estiver instalada, invoca o pipeline real
        # Caso falhe a inicialização interna, o tratamento de exceção em speak() atua
        pipeline = kokoro.KPipeline(lang_code="b")  # pt-BR
        generator = pipeline(text, voice=self.model, speed=self.speed)
        # Salva áudio gerado real
        for _, _, audio in generator:
            import soundfile as sf  # type: ignore
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out_path), audio, 24000)
            return round(len(audio) / 24000.0, 2)
        raise RuntimeError("Kokoro nativo não retornou frames de áudio")

    def _synthesize_deterministic_pcm(self, text: str, out_path: Path) -> float:
        """Gera áudio PCM 16-bit 24kHz válido determinístico estritamente para fixtures."""
        words = text.split()
        duration_s = max(0.6, len(words) / (3.5 * self.speed))
        sample_rate = 24000
        total_samples = int(duration_s * sample_rate)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)

            freq = 220.0
            samples = array.array("h")
            for i in range(total_samples):
                t = i / sample_rate
                env = min(1.0, t * 10.0) * min(1.0, (duration_s - t) * 10.0)
                val = int(8000 * env * math.sin(2 * math.pi * freq * t))
                samples.append(val)
            w.writeframes(samples.tobytes())

        return round(duration_s, 2)
