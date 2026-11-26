"""Adaptador para síntese neural ElevenLabs (V4-02).

Provedor neural em nuvem de altíssima fidelidade (BYOK / Opt-in).
Implementa a porta NeuralVoice. Exige chave de API explícita e respeita tetos
de orçamento. Em ausência de chave ou em testes sem rede, recusa com erro
semântico claro de provedor.
"""
from __future__ import annotations

from pathlib import Path

from ..application.ports import NeuralVoice
from ..domain.provider import ProviderMissingCredential


class ElevenLabsVoice:
    name = "elevenlabs"

    def __init__(
        self,
        model: str = "eleven_multilingual_v2",
        voice_id: str = "adam",
        api_key: str | None = None,
        cost_per_char: float = 0.00003,
    ) -> None:
        self.model = model
        self.voice_id = voice_id
        self.api_key = api_key
        self.cost_per_char = cost_per_char

    def supported_voices(self) -> tuple[str, ...]:
        return ("adam", "rachel", "antoni", "bella", "josh")

    def cost_estimate(self, text: str) -> float:
        return round(len(text) * self.cost_per_char, 4)

    def speak(self, text: str, out_path: Path) -> float:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text to speak is empty")
        if not self.api_key:
            raise ProviderMissingCredential("elevenlabs", "ELEVENLABS_API_KEY ausente")

        raise NotImplementedError("ElevenLabs network execution requires explicit remote authorization")
