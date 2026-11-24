from __future__ import annotations

from typing import Sequence

from app.studio.domain.captions import CaptionLine
from app.studio.domain.contracts import VideoFormat

__all__ = [
    "AssSubtitleRenderer",
]


class AssSubtitleRenderer:
    """Renderizador de legendas dinâmicas no formato Advanced SubStation Alpha (ASS v4+)."""

    @classmethod
    def ms_to_ass_time(cls, ms: int) -> str:
        """Converte milissegundos para o formato de tempo ASS H:MM:SS.cs (e.g. 0:00:01.25)."""
        total_cs = max(0, round(ms / 10))
        cs = total_cs % 100
        total_s = total_cs // 100
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @classmethod
    def render(
        cls,
        lines: list[CaptionLine] | Sequence[CaptionLine],
        format: VideoFormat | str = "short",
        style_kind: str = "highlight",
    ) -> str:
        """Gera o conteúdo textual completo de um arquivo .ass com estilos e safe margins."""
        is_short = False
        if isinstance(format, VideoFormat):
            is_short = format == VideoFormat.short
        elif isinstance(format, str):
            is_short = format.strip().lower() in ("short", "9:16")

        if is_short:
            play_res_x, play_res_y = 1080, 1920
            margin_v = 280
            font_size = 64
        else:
            play_res_x, play_res_y = 1920, 1080
            margin_v = 60
            font_size = 48

        header = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,Arial,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,0,2,10,10,{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        event_lines: list[str] = []
        for line in lines:
            start_str = cls.ms_to_ass_time(line.start_ms)
            end_str = cls.ms_to_ass_time(line.end_ms)
            if line.words and style_kind == "highlight":
                text = "".join(
                    f"{{\\k{max(1, round(w.duration_ms / 10))}}}{w.word} "
                    for w in line.words
                )
            else:
                text = line.text
            event_lines.append(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}"
            )

        all_lines = header + event_lines
        return "\n".join(all_lines) + "\n"
