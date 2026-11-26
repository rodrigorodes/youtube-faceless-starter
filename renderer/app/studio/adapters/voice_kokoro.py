"""Adaptador para síntese neural Kokoro (V4-02 / INT-02 / REC-02.05).

Provedor neural local de alta fidelidade e custo zero ($0.00).
Implementa a porta NeuralVoice.

Conforme auditoria A01 (INT-02) e saneamento R09 (REC-02.05):
- find_spec("kokoro") isolado NÃO homologa o provedor: exige pesos locais offline
  verificáveis (diretório/arquivos binários válidos via KOKORO_WEIGHTS_DIR ou /opt/kokoro).
  Extensões permitidas: .onnx, .pth, .pt, .bin, .safetensors (.json não é peso).
- Nunca dispara downloads automáticos da rede / HuggingFace (HF_HUB_OFFLINE=1).
- Context manager offline restaura estritamente os.environ sem vazamento de estado.
- Se pacote ou pesos não estiverem presentes, Kokoro falha fechado (validated=False
  no catálogo e ModelUnavailable em speak()).
- Em _synthesize_native, decodifica chunks (numpy, torch-like, list, bytes, 2D),
  normaliza uniformemente, aplica headroom seguro (-0.8 dBFS, <= 30000), rejeita
  silêncio anômalo (peak < 300) antes de criar o arquivo, e escreve WAV 16-bit mono 24kHz.
- O tom sintético só é permitido se explicitamente habilitado via
  allow_synthetic_fixture=True para isolamento exclusivo em fixtures unitárias.
"""
from __future__ import annotations

import array
import importlib.util
import logging
import math
import os
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..application.ports import ModelUnavailable, NeuralVoice

logger = logging.getLogger(__name__)

KOKORO_DEFAULT_WEIGHTS_DIR = Path("/opt/kokoro")
KOKORO_WEIGHTS_EXTENSIONS = {".onnx", ".pth", ".pt", ".bin", ".safetensors"}
MIN_PEAK = 300  # Limiar mínimo de amplitude de fala (16-bit PCM de 32767)


@contextmanager
def offline_environment_guard():
    """Garante isolamento offline estrito para huggingface e transformers sem vazar os.environ."""
    keys = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    prior = {k: os.environ.get(k) for k in keys}
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def get_kokoro_weights_path(custom_dir: Path | str | None = None) -> Path | None:
    """Verifica e retorna o caminho de pesos locais offline do Kokoro, se presente.

    Procura em:
    1. custom_dir explícito (se fornecido)
    2. Variável de ambiente KOKORO_WEIGHTS_DIR ou KOKORO_MODEL_PATH
    3. Diretório padrão /opt/kokoro

    Exige arquivo ou diretório existente e não vazio com arquivos de pesos binários válidos.
    Arquivos não-binários (.json, .txt) NÃO qualificam como pesos de inferência.
    """
    candidates: list[Path] = []
    if custom_dir:
        candidates.append(Path(custom_dir))
    env_dir = os.getenv("KOKORO_WEIGHTS_DIR") or os.getenv("KOKORO_MODEL_PATH")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(KOKORO_DEFAULT_WEIGHTS_DIR)

    for p in candidates:
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() in KOKORO_WEIGHTS_EXTENSIONS and p.stat().st_size > 0:
                return p
            continue
        if p.is_dir():
            files = [
                f for f in p.rglob("*")
                if f.is_file() and f.stat().st_size > 0 and f.suffix.lower() in KOKORO_WEIGHTS_EXTENSIONS
            ]
            if files:
                return p
    return None


def is_kokoro_installed() -> bool:
    """Verifica se o pacote kokoro está disponível no ambiente Python."""
    return importlib.util.find_spec("kokoro") is not None


def is_kokoro_offline_ready(custom_dir: Path | str | None = None) -> tuple[bool, str | None]:
    """Verifica se o pacote kokoro E os pesos locais offline verificáveis estão presentes.

    Retorna (pronto: bool, motivo_se_não_pronto: str | None).
    """
    if not is_kokoro_installed():
        return False, "pacote kokoro não instalado no ambiente local; use piper para síntese offline validada"
    weights = get_kokoro_weights_path(custom_dir)
    if weights is None:
        return False, "pesos locais offline do kokoro não encontrados no ambiente local; configure KOKORO_WEIGHTS_DIR ou use piper para síntese offline validada"
    return True, None


class KokoroVoice:
    name = "kokoro"

    def __init__(
        self,
        model: str = "pt_br-af_bella",
        speed: float = 1.0,
        allow_synthetic_fixture: bool = False,
        pipeline_factory: Callable[..., Any] | None = None,
        weights_dir: str | Path | None = None,
    ) -> None:
        self.model = model
        self.speed = max(0.5, min(2.0, speed))
        self.allow_synthetic_fixture = allow_synthetic_fixture
        self.pipeline_factory = pipeline_factory
        self.weights_dir = Path(weights_dir) if weights_dir else None

    def supported_voices(self) -> tuple[str, ...]:
        return ("pt_br-af_bella", "pt_br-am_adam", "en_af_heart")

    def cost_estimate(self, text: str) -> float:
        return 0.0  # Provedor local offline gratuito ($0.00)

    def speak(self, text: str, out_path: Path) -> float:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text to speak is empty")

        # Verifica se pesos e pacote estão disponíveis
        ready, reason = is_kokoro_offline_ready(custom_dir=self.weights_dir)

        # Se houver pipeline_factory injetado (teste unitário determinístico com dublê),
        # verifica se pesos locais offline foram fornecidos
        has_mock_pipeline_with_weights = (
            self.pipeline_factory is not None
            and get_kokoro_weights_path(self.weights_dir) is not None
        )

        if not ready and not has_mock_pipeline_with_weights:
            # Se pipeline_factory foi fornecido MAS sem pesos locais válidos, detalha erro de pesos
            if self.pipeline_factory is not None and get_kokoro_weights_path(self.weights_dir) is None:
                reason = "pesos locais offline do kokoro não encontrados no ambiente local; configure KOKORO_WEIGHTS_DIR ou use piper para síntese offline validada"
            if not self.allow_synthetic_fixture:
                raise ModelUnavailable(
                    f"{reason}; instale os pesos/pacote ou selecione o provedor validado piper"
                )
            logger.warning(
                "Kokoro indisponível offline (%s); gerando tom sintético EXCLUSIVAMENTE para fixture de teste autorizada",
                reason,
            )
            return self._synthesize_deterministic_pcm(cleaned, out_path)

        # Executa síntese nativa com isolamento offline garantido
        try:
            return self._synthesize_native(cleaned, out_path)
        except Exception as exc:
            logger.warning("Falha na síntese nativa do Kokoro: %s", exc)
            if not self.allow_synthetic_fixture:
                raise ModelUnavailable(
                    f"Falha na síntese nativa do Kokoro ({exc}); "
                    "use o provedor validado piper para síntese local garantida"
                ) from exc
            return self._synthesize_deterministic_pcm(cleaned, out_path)

    def _synthesize_native(self, text: str, out_path: Path) -> float:
        # Garante modo 100% offline para bibliotecas de inferência com restauração de ambiente
        with offline_environment_guard():
            if self.pipeline_factory is not None:
                pipeline = self.pipeline_factory(lang_code="b")
            else:
                import kokoro  # type: ignore
                weights = get_kokoro_weights_path(self.weights_dir)
                if weights is None:
                    raise RuntimeError("Pesos locais offline do Kokoro ausentes para síntese nativa")
                pipeline = kokoro.KPipeline(lang_code="b")

            generator = pipeline(text, voice=self.model, speed=self.speed)

            # R09: Concatena TODOS os chunks gerados pelo KPipeline (nunca retorna apenas o primeiro!)
            chunks: list[np.ndarray] = []
            for item in generator:
                if isinstance(item, tuple) and len(item) >= 3:
                    audio = item[2]
                else:
                    audio = item
                if audio is None:
                    continue

                # 1. Trata bytes / bytearray / memoryview como PCM 16-bit little-endian
                if isinstance(audio, (bytes, bytearray, memoryview)):
                    raw_bytes = bytes(audio)
                    if len(raw_bytes) % 2 != 0:
                        raise ValueError(f"Chunk de bytes PCM com comprimento ímpar: {len(raw_bytes)}")
                    arr = np.frombuffer(raw_bytes, dtype="<i2").astype(np.float32) / 32768.0
                else:
                    # 2. PyTorch tensor ou similar com .detach()
                    if hasattr(audio, "detach"):
                        audio = audio.detach().cpu().numpy()
                    arr = np.asarray(audio)

                # 3. Achata dimensões extras (ex: (N, 1) -> (N,))
                arr = arr.reshape(-1)

                # 4. Rejeita valores não-finitos (NaN ou Inf)
                if not np.all(np.isfinite(arr)):
                    raise ValueError("Chunk de áudio contém valores não-finitos (NaN ou Inf)")

                # 5. Normaliza inteiros vs ponto flutuante uniformemente para [-1.0, 1.0] float32
                if np.issubdtype(arr.dtype, np.integer):
                    arr = arr.astype(np.float32) / 32768.0
                else:
                    arr = arr.astype(np.float32)

                if arr.size > 0:
                    chunks.append(arr)

            if not chunks:
                raise RuntimeError("Kokoro nativo não retornou frames de áudio")

            full_audio = np.concatenate(chunks, axis=0)
            if full_audio.size == 0:
                raise RuntimeError("Kokoro nativo retornou áudio vazio após concatenação")

            # Normalização de headroom seguro (-0.8 dBFS, max ~30000)
            max_abs = float(np.max(np.abs(full_audio))) if full_audio.size > 0 else 0.0
            target_max_float = 30000.0 / 32767.0
            if max_abs > target_max_float:
                normalized = full_audio * (target_max_float / max_abs)
            else:
                normalized = full_audio

            int16_samples = np.clip(normalized * 32767.0, -32768, 32767).astype(np.int16)
            peak_pcm = int(np.max(np.abs(int16_samples))) if int16_samples.size > 0 else 0

            # Rejeita silêncio anômalo ANTES de criar ou escrever o arquivo out_path
            if peak_pcm < MIN_PEAK:
                raise RuntimeError(f"Kokoro nativo produziu silêncio anômalo (peak {peak_pcm} < {MIN_PEAK})")

            # Escreve WAV 16-bit mono 24kHz determinístico via stdlib wave
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(int16_samples.tobytes())

            return round(len(int16_samples) / 24000.0, 2)

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
