"""Contrato de domínio do Diretor Criativo (CreativeBrief).

Define a visão criativa e diretrizes de produção audiovisual de forma pura e imutável.
Sem I/O, sem dependência de banco de dados ou provedores externos.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from .schema import _Model

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

MediaType = Literal["image", "video", "graphic", "text"]


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
