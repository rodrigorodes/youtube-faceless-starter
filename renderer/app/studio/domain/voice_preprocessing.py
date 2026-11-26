"""Pré-processamento de texto e fonética para síntese de voz (V4-02).

Fornece:
1. Dicionário de pronúncia para termos técnicos, estrangeiros e siglas.
2. Normalização de pausas e ritmo (pacing) para evitar narração corrida.
3. Modulação de intenção emocional contextual.
4. Geração de fingerprint determinístico para cache e invalidação seletiva de cena.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum


class EmotionalIntention(str, Enum):
    """Intenção emocional para ajuste de ritmo e ênfase da narração."""

    NEUTRAL = "neutral"
    DOCUMENTARY = "documentary"      # Tom sério, pausas medidas e reflexivas
    DRAMATIC = "dramatic"            # Clímax narrativo, pausas suspensivas
    ENERGETIC = "energetic"          # Ágil, cortes rápidos, ritmo elevado
    CONVERSATIONAL = "conversational"# Espontâneo, respirações naturais


# Dicionário canônico PT-BR para termos comuns em tecnologia e documentários
DEFAULT_PRONUNCIATION_RULES: dict[str, str] = {
    # Siglas comuns que sintetizadores tendem a pronunciar como palavras ou errar
    r"\bIA\b": "I A",
    r"\bAI\b": "A I",
    r"\bCPU\b": "C P U",
    r"\bGPU\b": "G P U",
    r"\bRAM\b": "RÃM",
    r"\bROM\b": "RÓM",
    r"\bSQL\b": "S Q L",
    r"\bLLM\b": "L L M",
    r"\bTTS\b": "T T S",
    r"\bAPI\b": "A P I",
    r"\bFPS\b": "F P S",
    r"\bUI\b": "U I",
    r"\bUX\b": "U X",
    # Termos e nomes históricos com fonética não-óbvia em PT-BR
    r"\bAlan Turing\b": "Álan Tchúring",
    r"\bTuring\b": "Tchúring",
    r"\bAda Lovelace\b": "Eida Lôvelêice",
    r"\bLovelace\b": "Lôvelêice",
    r"\bvon Neumann\b": "von Nôiman",
    r"\bNeumann\b": "Nôiman",
    r"\bENIAC\b": "Éni-ák",
    r"\bJacquard\b": "Jacár",
    r"\bSilicon Valley\b": "Sílicon Válêi",
    r"\bWorld Wide Web\b": "Uorld Uaide Uéb",
}


@dataclass(frozen=True)
class PronunciationDictionary:
    """Mecanismo de substituição léxica para pronúncia precisa."""

    rules: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PRONUNCIATION_RULES))

    def apply(self, text: str) -> str:
        """Aplica as substituições fonéticas no texto preservando maiúsculas e pontuação."""
        if not text:
            return ""
        result = text
        for pattern, replacement in self.rules.items():
            result = re.sub(pattern, replacement, result)
        return result


def apply_pacing_and_pauses(text: str, intention: EmotionalIntention = EmotionalIntention.DOCUMENTARY) -> str:
    """Insere respirações e pausas rítmicas adequadas à intenção narrativa."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text.strip())

    if intention in (EmotionalIntention.DOCUMENTARY, EmotionalIntention.DRAMATIC):
        # Em documentários, vírgulas antes de conjunções explicativas ganham pausa deliberada
        cleaned = re.sub(r"\b(mas|porém|contudo|todavia|portanto|logo)\b", r", \1", cleaned)
        cleaned = re.sub(r",\s*,", ",", cleaned)
        # Dois pontos e travessões recebem pausa
        cleaned = cleaned.replace(" — ", ", ")

    return cleaned


def narration_fingerprint(
    text: str,
    voice_id: str,
    pronunciation_dict: dict[str, str] | None = None,
    intention: EmotionalIntention = EmotionalIntention.DOCUMENTARY,
) -> str:
    """Gera hash estável SHA-256 da síntese para cache determinístico e invalidação seletiva."""
    payload = {
        "text": text.strip(),
        "voice_id": voice_id.strip(),
        "pronunciation": pronunciation_dict or DEFAULT_PRONUNCIATION_RULES,
        "intention": intention.value,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
