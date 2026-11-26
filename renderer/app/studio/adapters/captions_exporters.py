from __future__ import annotations

from typing import Literal, Sequence

from app.studio.adapters.captions_ass import AssSubtitleRenderer
from app.studio.domain.captions import CaptionLine, CaptionStyleConfig
from app.studio.domain.contracts import VideoFormat

__all__ = [
    "SrtSubtitleRenderer",
    "VttSubtitleRenderer",
    "export_captions",
]


class SrtSubtitleRenderer:
    """Renderizador de legendas no formato SubRip (.srt)."""

    @classmethod
    def ms_to_srt_time(cls, ms: int) -> str:
        """Converte milissegundos para o formato de tempo SRT HH:MM:SS,mmm."""
        total_ms = max(0, ms)
        milli = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    @classmethod
    def render(cls, lines: Sequence[CaptionLine]) -> str:
        """Gera o arquivo de texto .srt padrão a partir de uma sequência de CaptionLine."""
        blocks: list[str] = []
        for i, line in enumerate(lines, start=1):
            start_str = cls.ms_to_srt_time(line.start_ms)
            end_str = cls.ms_to_srt_time(line.end_ms)
            blocks.append(f"{i}\n{start_str} --> {end_str}\n{line.text}")
        if not blocks:
            return ""
        return "\n\n".join(blocks) + "\n"


class VttSubtitleRenderer:
    """Renderizador de legendas no formato WebVTT (.vtt)."""

    @classmethod
    def ms_to_vtt_time(cls, ms: int) -> str:
        """Converte milissegundos para o formato de tempo WebVTT HH:MM:SS.mmm."""
        total_ms = max(0, ms)
        milli = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"

    @classmethod
    def render(cls, lines: Sequence[CaptionLine]) -> str:
        """Gera o arquivo de texto WebVTT (.vtt) com cabeçalho canônico."""
        blocks: list[str] = ["WEBVTT\n"]
        for i, line in enumerate(lines, start=1):
            start_str = cls.ms_to_vtt_time(line.start_ms)
            end_str = cls.ms_to_vtt_time(line.end_ms)
            blocks.append(f"{i}\n{start_str} --> {end_str}\n{line.text}\n")
        return "\n".join(blocks)


def export_captions(
    lines: Sequence[CaptionLine],
    format_type: Literal["ass", "srt", "vtt"] = "ass",
    video_format: VideoFormat | str = "short",
    style_kind: str = "highlight",
    style: CaptionStyleConfig | None = None,
) -> str:
    """Exportador polimórfico de legendas para formatos ASS, SRT ou WebVTT."""
    fmt = format_type.strip().lower()
    if fmt == "ass":
        return AssSubtitleRenderer.render(
            lines=lines,
            format=video_format,
            style_kind=style_kind,
            style=style,
        )
    elif fmt == "srt":
        return SrtSubtitleRenderer.render(lines=lines)
    elif fmt == "vtt":
        return VttSubtitleRenderer.render(lines=lines)
    else:
        raise ValueError(f"Unsupported caption export format: {format_type!r}")
