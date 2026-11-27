"""Perfis vocais e contratos tipados de voz no domínio (V4-02).

Define os tipos do domínio para caracterização e identidade vocal:
- Gênero, estilo narrativo, metadados de fidelidade e custos abstratos.
- Totalmente desacoplado de fornecedores concretos ou SDKs externos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoiceStyle(str, Enum):
    DOCUMENTARY = "documentary"
    NARRATIVE = "narrative"
    CONVERSATIONAL = "conversational"
    DRAMATIC = "dramatic"
    CORPORATE = "corporate"


@dataclass(frozen=True)
class VoiceProfile:
    """Perfil tipado de uma voz no domínio audiovisual."""

    voice_id: str                   # ex: "local:narrator-pt-m1", "cloud:studio-f1"
    provider: str                   # identificador abstrato de provedor
    model: str                      # identificador do modelo de síntese
    name: str                       # Nome amigável de exibição (ex: "Faber", "Bella")
    language: str = "pt-BR"         # BCP-47 (ex: "pt-BR", "en-US")
    gender: VoiceGender = VoiceGender.MALE
    style: VoiceStyle = VoiceStyle.DOCUMENTARY
    is_neural: bool = False
    is_local: bool = True
    supports_emotion: bool = False
    supports_pacing: bool = True
    is_demo: bool = False
    available: bool = True
    cost_per_1k_chars: Decimal = Decimal("0.00")
    description: str = ""
    tags: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        neural_tag = "Neural" if self.is_neural else "Local"
        return f"{self.name} ({self.language} · {self.gender.value} · {neural_tag})"
