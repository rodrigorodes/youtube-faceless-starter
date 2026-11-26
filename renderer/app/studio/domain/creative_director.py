"""Contrato de domínio do Diretor Criativo e Direção Narrativa (V4-06 / Creative Intelligence).

Define a visão criativa, arquitetura narrativa em atos e direção de cena de forma pura e imutável:
- Estrutura de narrativa em atos (Hook, Desenvolvimento, Clímax, Resolução).
- Brief estruturado por cena com intenção emocional (intensidade 1-5), objetivo e enquadramento.
- Planejamento de shots, ritmo (pacing), música e efeitos sonoros (SFX).
- Sanitização rigorosa: rejeição explícita de comandos shell/FFmpeg injetados na saída do LLM.
- Suporte a overrides manuais do operador com preservação da identidade congelada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from .schema import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MediaType = Literal["image", "video", "graphic", "text"]

# Padrões proibidos na saída de inteligência criativa (rejeição de injeção de comandos no Core).
# Exige fronteiras de comando/flag CLI para não bloquear prosa legítima em português
# (ex.: "auto-afirmação", "pré-afirmação", "color-preset", "tutorial de bash/curl/FFmpeg").
FORBIDDEN_COMMAND_PATTERNS = re.compile(
    r"(?:"
    r"(?:^|[\s;|&`\"'(=])-(?:filter_complex|vf|af|c:v|c:a|preset|crf)(?:$|[\s;|&`\"'=])"
    r"|\bffmpeg\s+-"
    r"|\b(?:sh|bash)\s+-[a-z]*c\b"
    r"|\b(?:curl|wget)\s+(?:-[a-zA-Z]|https?://)"
    r"|\brm\s+-[a-z]*r[a-z]*f\b|\brm\s+-[a-z]*f[a-z]*r\b"
    r"|;\s*(?:rm|sh|bash|curl|wget|ffmpeg|python3?|nc)\b"
    r"|\|\s*(?:sh|bash|ffmpeg)\b"
    r"|\$\([^)]+\)"
    r"|`[^`]+`"
    r")",
    re.IGNORECASE,
)


class CreativeSecurityViolation(ValueError):
    """Lançada quando a saída do LLM tenta injetar comandos de baixo nível ou FFmpeg."""


class ActKind(str, Enum):
    """Classificação dramática do ato narrativo na estrutura do roteiro."""

    ACT_1_HOOK = "hook"
    ACT_2_DEVELOPMENT = "development"
    ACT_3_CLIMAX = "climax"
    ACT_4_RESOLUTION = "resolution"


class ShotIntent(_Model):
    """Diretriz de intenção visual e enquadramento para um shot específico."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_index: int = Field(ge=0)
    visual_intent: NonBlank
    framing: Literal["close_up", "medium", "wide", "extreme_wide"] = "medium"
    lighting: Literal["dramatic", "natural", "high_key", "dark_moody"] = "natural"
    suggested_motion: Literal["zoom_in", "zoom_out", "pan_right", "pan_left", "none"] = "none"


class SceneCreativeDirection(_Model):
    """Direção criativa detalhada por cena individual."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_idx: int = Field(ge=0)
    act: ActKind = ActKind.ACT_2_DEVELOPMENT
    scene_goal: NonBlank
    emotional_intensity: int = Field(ge=1, le=5)  # Escala de intensidade de 1 a 5
    visual_prompt_guide: NonBlank
    suggested_shots: tuple[ShotIntent, ...] = ()
    music_mood: str = ""
    sfx_cue: str | None = None
    pacing: Literal["fast", "moderate", "slow"] = "moderate"

    @field_validator("visual_prompt_guide", "scene_goal")
    @classmethod
    def _validate_no_forbidden_syntax(cls, value: str) -> str:
        if FORBIDDEN_COMMAND_PATTERNS.search(value):
            raise CreativeSecurityViolation("LLM creative output attempted to inject FFmpeg commands or shell syntax")
        return value


class CreativeBrief(_Model):
    """Briefing criativo de alto nível gerado pelo Diretor Criativo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    topic: NonBlank
    narrative_goal: NonBlank
    hook: NonBlank
    content_structure: tuple[NonBlank, ...]
    tone: NonBlank
    pacing: NonBlank
    visual_direction: NonBlank
    recommended_media_types: tuple[MediaType, ...] = ("image", "video")
    caption_strategy: NonBlank
    audio_guidance: NonBlank
    max_budget_usd: float | None = Field(default=None, ge=0.0)
    quality_criteria: tuple[NonBlank, ...] = ()

    @field_validator("content_structure")
    @classmethod
    def _validate_content_structure(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) < 2:
            raise ValueError("content_structure must contain at least 2 sections")
        return value

    @field_validator("visual_direction", "narrative_goal", "hook", "audio_guidance")
    @classmethod
    def _validate_clean_prose(cls, value: str) -> str:
        if FORBIDDEN_COMMAND_PATTERNS.search(value):
            raise CreativeSecurityViolation("CreativeBrief contains forbidden low-level command syntax")
        return value


@dataclass(frozen=True)
class CreativeDirectorPlan:
    """Plano criativo estruturado completo agregando brief geral e direções de cena."""

    topic: str
    high_level_brief: CreativeBrief
    scene_directions: tuple[SceneCreativeDirection, ...] = ()
    target_audience: str = "general"
    channel_identity_digest: str = ""
    overrides: dict[int, dict[str, Any]] = field(default_factory=dict)

    def with_override(self, scene_idx: int, override_dict: dict[str, Any]) -> CreativeDirectorPlan:
        """Aplica overrides do operador sobre a cena preservando imutabilidade."""
        new_overrides = dict(self.overrides)
        current = dict(new_overrides.get(scene_idx, {}))
        current.update(override_dict)
        new_overrides[scene_idx] = current
        return CreativeDirectorPlan(
            topic=self.topic,
            high_level_brief=self.high_level_brief,
            scene_directions=self.scene_directions,
            target_audience=self.target_audience,
            channel_identity_digest=self.channel_identity_digest,
            overrides=new_overrides,
        )

    def get_effective_scene_direction(self, scene_idx: int) -> SceneCreativeDirection | None:
        """Obtém a direção criativa da cena com os overrides aplicados."""
        found = None
        for sd in self.scene_directions:
            if sd.scene_idx == scene_idx:
                found = sd
                break
        if found is None:
            return None

        ov = self.overrides.get(scene_idx)
        if not ov:
            return found

        data = found.model_dump()
        data.update(ov)
        return SceneCreativeDirection.model_validate(data)
