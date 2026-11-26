"""Catálogo de vozes registradas no Faceless Studio (V4-02).

Camada de composição: vincula os perfis vocais do domínio aos adaptadores
reais e modelos configurados na infraestrutura do Studio.
"""
from __future__ import annotations

from decimal import Decimal

from ..domain.voice_catalog import VoiceGender, VoiceProfile, VoiceStyle

# Catálogo canônico registrado no Faceless Studio
_CANONICAL_VOICES: tuple[VoiceProfile, ...] = (
    VoiceProfile(
        voice_id="piper:pt_BR-faber-medium",
        provider="piper",
        model="pt_BR-faber-medium",
        name="Faber (Piper Local)",
        language="pt-BR",
        gender=VoiceGender.MALE,
        style=VoiceStyle.DOCUMENTARY,
        is_neural=False,
        is_local=True,
        cost_per_1k_chars=Decimal("0.00"),
        description="Voz padrão local PT-BR em velocidade moderada, otimizada para documentários factuais.",
        tags=("default", "offline", "fast"),
    ),
    VoiceProfile(
        voice_id="piper:pt_BR-jeff-medium",
        provider="piper",
        model="pt_BR-jeff-medium",
        name="Jeff (Piper Local)",
        language="pt-BR",
        gender=VoiceGender.MALE,
        style=VoiceStyle.CONVERSATIONAL,
        is_neural=False,
        is_local=True,
        cost_per_1k_chars=Decimal("0.00"),
        description="Voz masculina jovem e dinâmica para vídeos em formato Short.",
        tags=("offline", "shorts"),
    ),
    VoiceProfile(
        voice_id="kokoro:pt_br-af_bella",
        provider="kokoro",
        model="pt_br-af_bella",
        name="Bella (Kokoro Local)",
        language="pt-BR",
        gender=VoiceGender.FEMALE,
        style=VoiceStyle.NARRATIVE,
        is_neural=True,
        is_local=True,
        cost_per_1k_chars=Decimal("0.00"),
        description="Síntese neural feminina local leve de alta fidelidade e entonação natural.",
        tags=("neural", "offline", "high-fidelity"),
    ),
    VoiceProfile(
        voice_id="gemini:aoede",
        provider="gemini",
        model="gemini-2.5-flash-tts",
        name="Aoede (Gemini Neural)",
        language="pt-BR",
        gender=VoiceGender.FEMALE,
        style=VoiceStyle.DRAMATIC,
        is_neural=True,
        is_local=False,
        cost_per_1k_chars=Decimal("0.015"),
        description="Voz neural expressiva de estúdio com inflexões dramáticas e modulação contextual.",
        tags=("neural", "cloud", "premium"),
    ),
    VoiceProfile(
        voice_id="elevenlabs:adam",
        provider="elevenlabs",
        model="eleven_multilingual_v2",
        name="Adam (ElevenLabs)",
        language="pt-BR",
        gender=VoiceGender.MALE,
        style=VoiceStyle.DOCUMENTARY,
        is_neural=True,
        is_local=False,
        cost_per_1k_chars=Decimal("0.030"),
        description="Voz documental consagrada com respiração natural e timbres aveludados.",
        tags=("neural", "cloud", "byok"),
    ),
)


def list_voice_catalog(language: str | None = None, is_local: bool | None = None) -> list[VoiceProfile]:
    """Lista vozes do catálogo filtradas por idioma e/ou execução local."""
    results = list(_CANONICAL_VOICES)
    if language is not None:
        lang_lower = language.strip().lower()
        results = [v for v in results if v.language.lower() == lang_lower]
    if is_local is not None:
        results = [v for v in results if v.is_local == is_local]
    return results


def find_voice_profile(voice_id: str) -> VoiceProfile | None:
    """Localiza perfil de voz por ID canônico (ex: 'piper:pt_BR-faber-medium')."""
    target = voice_id.strip()
    for v in _CANONICAL_VOICES:
        if v.voice_id == target or v.model == target:
            return v
    return None
