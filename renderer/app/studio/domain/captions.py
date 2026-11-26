from __future__ import annotations

from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

__all__ = [
    "WordTiming",
    "CaptionLine",
    "CaptionStyleConfig",
    "CaptionOverlapError",
    "CaptionSyncError",
    "validate_no_overlaps",
    "resolve_overlaps",
    "check_audio_caption_sync",
    "recalculate_caption_timeline",
    "apply_manual_caption_edits",
]


class CaptionOverlapError(ValueError):
    """Lançada quando é detectada sobreposição temporal indevida entre legendas."""


class CaptionSyncError(ValueError):
    """Lançada quando a perda de sincronismo (drift) excede o teto tolerado."""


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


class CaptionStyleConfig(BaseModel):
    """Configuração visual de estilo de legenda por canal ou formato (V4-07.06/07)."""

    model_config = ConfigDict(frozen=True)

    font_name: str = "Arial"
    font_size: int | None = Field(default=None, ge=12, le=120)
    primary_color: str = "&H00FFFFFF"    # Branco
    secondary_color: str = "&H0000FFFF"  # Amarelo / Destaque de karaoke
    outline_color: str = "&H00000000"    # Preto
    back_color: str = "&H00000000"       # Transparente ou sombra
    bold: bool = True
    italic: bool = False
    outline_width: int = Field(default=4, ge=0, le=20)
    shadow_depth: int = Field(default=0, ge=0, le=20)
    margin_v: int | None = Field(default=None, ge=0)
    alignment: int = Field(default=2, ge=1, le=9)  # 2 = inferior central


def validate_no_overlaps(lines: Sequence[CaptionLine]) -> None:
    """Valida ausência estrita de sobreposição temporal entre linhas consecutivas."""
    for i in range(len(lines) - 1):
        if lines[i].end_ms > lines[i + 1].start_ms:
            raise CaptionOverlapError(
                f"Overlap detected between caption {i} (end {lines[i].end_ms}ms) "
                f"and caption {i+1} (start {lines[i+1].start_ms}ms)"
            )


def resolve_overlaps(lines: Sequence[CaptionLine]) -> list[CaptionLine]:
    """Resolve sobreposições ajustando deterministicamente os limites sem inverter intervalos."""
    if not lines:
        return []
    resolved: list[CaptionLine] = []
    for i, line in enumerate(lines):
        if i == 0:
            resolved.append(line)
            continue
        prev = resolved[-1]
        if prev.end_ms > line.start_ms:
            if prev.start_ms < line.start_ms:
                new_prev = prev.model_copy(update={"end_ms": line.start_ms})
                resolved[-1] = new_prev
            else:
                new_start = max(line.start_ms, prev.end_ms)
                new_end = max(line.end_ms, new_start)
                line = line.model_copy(update={"start_ms": new_start, "end_ms": new_end})
        resolved.append(line)
    return resolved


def check_audio_caption_sync(
    lines: Sequence[CaptionLine],
    audio_duration_ms: int,
    max_drift_ms: int = 500,
) -> dict[str, Any]:
    """Mede e avalia o drift entre a última legenda e a duração total da narração de áudio."""
    if not lines:
        return {
            "synced": True,
            "drift_ms": 0,
            "audio_duration_ms": audio_duration_ms,
            "last_caption_end_ms": 0,
        }
    last_end = max(l.end_ms for l in lines)
    drift = abs(audio_duration_ms - last_end)
    return {
        "synced": drift <= max_drift_ms,
        "drift_ms": drift,
        "audio_duration_ms": audio_duration_ms,
        "last_caption_end_ms": last_end,
    }


def recalculate_caption_timeline(
    lines: Sequence[CaptionLine],
    original_duration_ms: int,
    target_duration_ms: int,
) -> list[CaptionLine]:
    """Recalcula proporcionalmente os tempos de início, fim e palavras ao mudar a duração da voz."""
    if original_duration_ms <= 0 or target_duration_ms <= 0:
        raise ValueError("Durations must be positive")
    if not lines:
        return []
    factor = target_duration_ms / original_duration_ms
    recalculated: list[CaptionLine] = []
    for line in lines:
        new_start = round(line.start_ms * factor)
        new_end = round(line.end_ms * factor)
        if new_end < new_start:
            new_end = new_start
        new_words: list[WordTiming] = []
        for w in line.words:
            w_start = round(w.start_ms * factor)
            w_dur = max(1, round(w.duration_ms * factor))
            new_words.append(WordTiming(word=w.word, start_ms=w_start, duration_ms=w_dur))
        recalculated.append(
            CaptionLine(
                start_ms=new_start,
                end_ms=new_end,
                text=line.text,
                words=tuple(new_words),
            )
        )
    return recalculated


def apply_manual_caption_edits(
    lines: Sequence[CaptionLine],
    edits: dict[int, dict[str, Any]],
) -> list[CaptionLine]:
    """Aplica correções manuais do operador sobre linhas de legenda preservando imutabilidade."""
    result = list(lines)
    for idx, edit_data in edits.items():
        if 0 <= idx < len(result):
            curr_dict = result[idx].model_dump()
            curr_dict.update(edit_data)
            result[idx] = CaptionLine.model_validate(curr_dict)
    return result
