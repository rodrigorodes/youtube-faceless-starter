from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing_extensions import Self

__all__ = [
    "WordTiming",
    "CaptionLine",
]


class WordTiming(BaseModel):
    """Marcação temporal de uma única palavra."""

    model_config = ConfigDict(frozen=True)

    word: str
    start_ms: int
    duration_ms: int

    @field_validator("word")
    @classmethod
    def _validate_word(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("word must be non-blank")
        return v

    @field_validator("start_ms", "duration_ms")
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("time in ms must be >= 0")
        return v


class CaptionLine(BaseModel):
    """Linha ou frase de legenda com limites temporais e timing opcional por palavra."""

    model_config = ConfigDict(frozen=True)

    start_ms: int
    end_ms: int
    text: str
    words: tuple[WordTiming, ...] = ()

    @field_validator("start_ms", "end_ms")
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("time in ms must be >= 0")
        return v

    @model_validator(mode="after")
    def _validate_interval(self) -> Self:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")
        return self
