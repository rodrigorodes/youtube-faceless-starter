"""Compilador FFmpeg do Render Plan (RP-023) — traduz a estrutura neutra em comandos.

Consome a estrutura neutra de ``application/render_compiler.py`` (validação e geometria
temporal em ticks, sem string de fornecedor) e emite ``CompiledRender``: os ``args`` de
linha de comando e o ``filter_complex`` de cada segmento, além do digest determinístico.

Toda a sintaxe de FFmpeg vive **aqui**; o núcleo (``domain``/``application``) não conhece
o binário (S3 do guia de isolamento do core). O ``subprocess`` continua no executor
(``adapters/render_plan_ffmpeg.py``): este módulo é puro e testável sem FFmpeg instalado.

Paridade com o renderer legado (``adapters/render_ffmpeg.py``), que é a régua do §11:
mesmo ``scale`` 1.5x lanczos + ``zoompan`` (Ken Burns), mesmo ``format=yuv420p``,
mesmo ``fade`` in/out por segmento, mesmo ``libx264 -preset veryfast -crf 21``, mesmo
concat ``-c copy``, mesma mixagem com ``sidechaincompress`` (ducking) e
``loudnorm=I=-16:TP=-1.5:LRA=11``. O movimento vem do plano (``Effects.motion``), não
de um ``index % 4``.

A VE-02 estende o grafo para compor o overlay de imagem **dentro** do segmento base
hospedeiro (entrada extra + ``overlay`` com ``enable``), sem criar segmento novo.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..application.render_compiler import (
    INTER_SHOT_TRANSITIONS,
    CompileError,
    LayerExecution,
    MusicTrack,
    NarrationTrack,
    PlanStructure,
    ShotPlan,
    structure_render_plan,
)
from ..domain.asset_resolver import AssetDescriptor
from ..domain.audio_catalog import AudioCatalog
from ..domain.audio_multitrack import MultitrackAudioPlan, verify_audio_licenses
from ..domain.captions import CaptionLine, WordTiming
from ..domain.motion_effects import calculate_motion_curve
from ..domain.render import FADE_S
from ..domain.render_plan import AudioMix as DomainAudioMix, Motion, RenderPlan, Transition
from .alignment import WordAlignmentService
from .captions_ass import AssSubtitleRenderer

# Mesmo grafo de mixagem do renderer legado (rich.py/render_ffmpeg.py): a trilha é
# comprimida por sidechain com a narração e a mistura mira -16 LUFS.
MIX_FILTER = (
    "[1:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[nar][nsc];"
    "[2:a]volume=0.40,pan=stereo|c0=c0|c1=c0[mus];"
    "[mus][nsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
    "[duck][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
)


def _mix_filter(
    audio_mix: DomainAudioMix | RenderPlan | None = None,
    total_s: float = 0.0,
) -> str:
    """Compila o grafo de mixagem de áudio consumindo os parâmetros do AudioMix."""
    if isinstance(audio_mix, RenderPlan):
        plan = audio_mix
        mix = plan.audio_mix or DomainAudioMix()
        if total_s <= 0 and hasattr(plan, "timeline") and plan.timeline.ticks_per_second:
            total_s = plan.timeline.duration_ticks / plan.timeline.ticks_per_second
    else:
        mix = audio_mix or DomainAudioMix()

    vol = f"{mix.music_gain:.2f}"
    thresh = f"{mix.ducking_threshold:.2f}"
    ratio = f"{int(mix.ducking_ratio)}" if mix.ducking_ratio.is_integer() else f"{mix.ducking_ratio}"
    norm_i = f"{int(mix.loudnorm_i)}" if mix.loudnorm_i.is_integer() else f"{mix.loudnorm_i}"
    norm_tp = f"{int(mix.loudnorm_tp)}" if mix.loudnorm_tp.is_integer() else f"{mix.loudnorm_tp}"
    norm_lra = f"{int(mix.loudnorm_lra)}" if mix.loudnorm_lra.is_integer() else f"{mix.loudnorm_lra}"
    fade_filter = ""
    if getattr(mix, "afade_out_s", 0.0) > 0 and total_s > 0:
        start_fade = max(0.0, total_s - mix.afade_out_s)
        fade_filter = f",afade=t=out:st={start_fade:.2f}:d={mix.afade_out_s:.2f}"
    return (
        f"[1:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[nar][nsc];"
        f"[2:a]volume={vol},pan=stereo|c0=c0|c1=c0{fade_filter}[mus];"
        f"[mus][nsc]sidechaincompress=threshold={thresh}:ratio={ratio}:attack=15:release=350[duck];"
        f"[duck][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I={norm_i}:TP={norm_tp}:LRA={norm_lra}[a]"
    )


@dataclass(frozen=True)
class OverlayImage:
    """Overlay que o executor precisa materializar antes de rodar o segmento.

    ``captions``/``text`` trazem o conteúdo e a janela (ticks **relativos ao segmento**);
    ``enable`` é a expressão do filtro ``overlay`` no mesmo formato do renderer legado.
    """

    kind: Literal["static", "caption", "text"]
    path: str
    text: str = ""
    label: str = ""
    disclosure: str = ""
    enable: str | None = None
    start_ticks: int = 0
    end_ticks: int = 0


@dataclass(frozen=True)
class ShotExecution:
    """Um segmento de vídeo: a mídia do shot com selo, legendas e fade já compilados."""

    scene_id: str
    shot_id: str
    asset_id: str
    media_type: str
    source: str
    start_ticks: int
    duration_ticks: int
    frames: int
    motion: Motion
    static_overlay: OverlayImage
    captions: tuple[OverlayImage, ...]
    text_card: OverlayImage | None
    filter_complex: str
    output: str
    args: tuple[str, ...]
    overlays: tuple[LayerExecution, ...] = ()


@dataclass(frozen=True)
class AudioMix:
    narration: NarrationTrack
    music: MusicTrack
    music_path: str
    filter_complex: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class ConcatExecution:
    manifest_path: str
    output: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class CompiledRender:
    """Plano de execução determinístico (dado o plano e os assets resolvidos)."""

    plan_id: str
    revision: int
    format: str
    width: int
    height: int
    fps_num: int
    fps_den: int
    ticks_per_second: int
    total_ticks: int
    shots: tuple[ShotExecution, ...]
    concat: ConcatExecution
    audio: AudioMix
    final_output: str
    final_args: tuple[str, ...]
    subtitles_ass_path: str | None = None
    subtitles_ass_content: str | None = None

    def _body(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "revision": self.revision,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "fps_num": self.fps_num,
            "fps_den": self.fps_den,
            "ticks_per_second": self.ticks_per_second,
            "total_ticks": self.total_ticks,
            "shots": [_shot_dict(s) for s in self.shots],
            "concat": {"manifest_path": self.concat.manifest_path, "output": self.concat.output, "args": list(self.concat.args)},
            "audio": {
                "narration": {
                    "voices": [{"scene_id": v.scene_id, "source_id": v.source_id, "path": v.path} for v in self.audio.narration.voices],
                    "output": self.audio.narration.output,
                    "lead_seconds": self.audio.narration.lead_seconds,
                    "tail_seconds": self.audio.narration.tail_seconds,
                    "sample_rate": self.audio.narration.sample_rate,
                },
                "music": {
                    "source_id": self.audio.music.source_id,
                    "duration_ticks": self.audio.music.duration_ticks,
                    "silent": self.audio.music.silent,
                    "params": dict(self.audio.music.params),
                },
                "music_path": self.audio.music_path,
                "filter_complex": self.audio.filter_complex,
                "args": list(self.audio.args),
            },
            "final_output": self.final_output,
            "final_args": list(self.final_args),
            "subtitles_ass_path": self.subtitles_ass_path,
            "subtitles_ass_content": self.subtitles_ass_content,
        }

    def to_dict(self) -> dict:
        """Plano de execução com o digest canônico (estável, ``sort_keys``)."""
        body = self._body()
        return {**body, "digest": _digest(body)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def digest(self) -> str:
        """sha256 do plano de execução canônico: mesma entrada, mesmo digest."""
        return _digest(self._body())


def compile_render_plan(
    *,
    plan: RenderPlan,
    assets: Mapping[str, AssetDescriptor],
    work_dir: str,
    labels: Mapping[str, str] | None = None,
) -> CompiledRender:
    """Compila a estrutura neutra do plano em comandos/graphs FFmpeg determinísticos.

    A validação e a geometria temporal vêm de ``structure_render_plan``
    (``application/render_compiler.py``); aqui só se traduz a estrutura neutra na sintaxe
    do FFmpeg. ``CompileError`` continua sendo o erro do núcleo — nunca devolve um comando
    que renderizaria algo diferente do plano.
    """
    structure = structure_render_plan(plan=plan, assets=assets, work_dir=work_dir, labels=labels)
    work = structure.work
    shots = tuple(_compile_shot(shot, structure) for shot in structure.shots)
    concat = _compile_concat(structure, work)
    subtitles_ass_path: str | None = None
    subtitles_ass_content: str | None = None

    if plan.timeline.subtitles:
        tps = plan.timeline.ticks_per_second
        alignment_service = WordAlignmentService()
        caption_lines: list[CaptionLine] = []

        for cue in plan.timeline.subtitles:
            start_ms = int(round(cue.start_tick / tps * 1000))
            dur_ms = int(round(cue.duration_ticks / tps * 1000))
            raw_words = alignment_service.align_words(cue.text, dur_ms)
            words = tuple(
                WordTiming(
                    word=w.word,
                    start_ms=start_ms + w.start_ms,
                    duration_ms=w.duration_ms,
                )
                for w in raw_words
            )
            caption_lines.append(
                CaptionLine(
                    start_ms=start_ms,
                    end_ms=start_ms + dur_ms,
                    text=cue.text,
                    words=words,
                )
            )

        ass_content = AssSubtitleRenderer.render(caption_lines, format=plan.output.format)
        subtitles_ass_content = ass_content
        ass_path = Path(work) / "subtitles.ass"
        subtitles_ass_path = str(ass_path)
        try:
            if Path(work).is_dir():
                ass_path.write_text(ass_content, encoding="utf-8")
        except OSError:
            pass

    total_s = (
        plan.timeline.duration_ticks / plan.timeline.ticks_per_second
        if hasattr(plan, "timeline") and plan.timeline.ticks_per_second
        else 0.0
    )
    mix_filter = _mix_filter(getattr(plan, "audio_mix", None), total_s=total_s)

    if subtitles_ass_path:
        escaped_sub_path = (
            subtitles_ass_path.replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
        )
        video_codec_args = (
            "-vf", f"subtitles='{escaped_sub_path}'",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
        )
    else:
        video_codec_args = ("-c:v", "copy")

    audio_args = (
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", concat.output, "-i", structure.narration.output, "-i", f"{work}/music.wav",
        "-filter_complex", mix_filter,
        "-map", "0:v", "-map", "[a]",
        *video_codec_args,
        "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", f"{work}/final.mp4",
    )
    audio = AudioMix(
        narration=structure.narration,
        music=structure.music,
        music_path=f"{work}/music.wav",
        filter_complex=mix_filter,
        args=audio_args,
    )

    return CompiledRender(
        plan_id=structure.plan_id,
        revision=structure.revision,
        format=structure.format,
        width=structure.width,
        height=structure.height,
        fps_num=structure.fps_num,
        fps_den=structure.fps_den,
        ticks_per_second=structure.ticks_per_second,
        total_ticks=structure.total_ticks,
        shots=shots,
        concat=concat,
        audio=audio,
        final_output=f"{work}/final.mp4",
        final_args=audio.args,
        subtitles_ass_path=subtitles_ass_path,
        subtitles_ass_content=subtitles_ass_content,
    )


# --------------------------------------------------------------------------- helpers


def _compile_shot(shot: ShotPlan, structure: PlanStructure) -> ShotExecution:
    width, height = structure.width, structure.height
    rate = structure.rate
    tps = structure.ticks_per_second
    frames = shot.frames
    seconds = shot.seconds
    source = shot.source
    parts: list[str] = []

    if shot.media_type in ("image", "graphic"):
        parts.append(
            f"[0:v]scale={int(width * 1.5)}:{int(height * 1.5)}:flags=lanczos,"
            f"{_zoompan(shot.motion, frames, width, height, rate)},format=yuv420p[b0]"
        )
    elif shot.media_type == "video":
        offset_s = shot.asset_offset_ticks / tps
        parts.append(
            f"[0:v]trim=start={offset_s:.6f}:duration={seconds:.6f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:flags=lanczos,fps={rate},format=yuv420p[b0]"
        )
    elif shot.media_type == "text":
        parts.append(f"[0:v]scale={width}:{height}:flags=lanczos,fps={rate},format=yuv420p[b0]")
    else:  # pragma: no cover - AssetMediaType é Literal fechado
        raise CompileError(f"unsupported media type {shot.media_type!r}")

    text_card = (
        OverlayImage(kind="text", path=shot.text_card.path, text=shot.text_card.text)
        if shot.text_card is not None else None
    )
    static = OverlayImage(
        kind="static",
        path=shot.static_path,
        label=shot.label,
        disclosure=shot.disclosure,
    )
    captions = tuple(
        OverlayImage(
            kind="caption",
            path=caption.path,
            text=caption.text,
            enable=f"gte(t,{_seconds(caption.start_ticks, tps):.3f})*lt(t,{_seconds(caption.end_ticks, tps):.3f})",
            start_ticks=caption.start_ticks,
            end_ticks=caption.end_ticks,
        )
        for caption in shot.captions
    )

    # VE-02: as camadas de imagem são entradas extras (depois das legendas) e entram no
    # grafo **abaixo** do selo/disclosure e das legendas, só na janela relativa ao segmento
    # base. Sem overlay, ``parts``/``args`` são exatamente os de antes (I13).
    overlay_args: list[str] = []
    last = "b0"
    for offset, layer in enumerate(shot.overlays):
        # inputs: 0 = mídia, 1 = selo/disclosure, 2.. = legendas, depois as camadas
        number = len(captions) + 2 + offset
        parts.append(_overlay_filter(layer, number, width, height, tps, last))
        last = f"ov{number}"
        if layer.media_type == "video":
            overlay_args += ["-i", layer.source]
        else:
            overlay_args += ["-loop", "1", "-i", layer.source]
    parts.append(f"[{last}][1:v]overlay=0:0:format=auto[o1]")
    last = "o1"

    for number, caption in enumerate(captions, start=2):
        parts.append(f"[{last}][{number}:v]overlay=0:0:format=auto:enable='{caption.enable}'[o{number}]")
        last = f"o{number}"

    fade = _fade_filter(
        shot.transition,
        seconds,
        tps,
        shot.shot_id,
        schema_version=structure.schema_version,
    )
    if fade:
        parts.append(f"[{last}]{fade}[v]")
    else:
        parts.append(f"[{last}]format=yuv420p[v]")
    filter_complex = ";".join(parts)

    output = shot.output
    args: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-i", static.path]
    for caption in captions:
        args += ["-i", caption.path]
    args += overlay_args
    args += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames), "-r", rate,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", output,
    ]
    return ShotExecution(
        scene_id=shot.scene_id,
        shot_id=shot.shot_id,
        asset_id=shot.asset_id,
        media_type=shot.media_type,
        source=source,
        start_ticks=shot.start_ticks,
        duration_ticks=shot.duration_ticks,
        frames=frames,
        motion=shot.motion,
        static_overlay=static,
        captions=captions,
        text_card=text_card,
        filter_complex=filter_complex,
        output=output,
        args=tuple(args),
        overlays=shot.overlays,
    )


def _overlay_filter(layer: LayerExecution, number: int, width: int, height: int,
                    tps: int, previous: str) -> str:
    """Composição de uma camada (imagem/gráfico/PiP vídeo) sobre o segmento base hospedeiro.

    Suporta geometria fit (cover/contain), opacidade (colorchannelmixer), escala e coordenadas
    relativas de posicionamento x/y com limites finitos explícitos.
    """
    scale = getattr(layer, "scale", 1.0)
    opacity = getattr(layer, "opacity", 1.0)
    pos_x = getattr(layer, "position_x", 0.5)
    pos_y = getattr(layer, "position_y", 0.5)

    for name, val in (("scale", scale), ("opacity", opacity), ("position_x", pos_x), ("position_y", pos_y)):
        if not math.isfinite(val):
            raise CompileError(f"overlay {layer.shot_id!r} has non-finite {name}={val!r}")
    if not (0.0 < scale <= 4.0):
        raise CompileError(f"overlay {layer.shot_id!r} scale {scale!r} out of (0.0, 4.0]")
    if not (0.0 <= opacity <= 1.0):
        raise CompileError(f"overlay {layer.shot_id!r} opacity {opacity!r} out of [0.0, 1.0]")
    if not (0.0 <= pos_x <= 1.0) or not (0.0 <= pos_y <= 1.0):
        raise CompileError(f"overlay {layer.shot_id!r} position ({pos_x!r}, {pos_y!r}) out of [0.0, 1.0]")

    target_w = max(16, int(width * scale))
    target_h = max(16, int(height * scale))

    if layer.fit == "cover":
        geometry = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={target_w}:{target_h},format=rgba"
        )
    elif layer.fit == "contain":
        if scale == 1.0:
            geometry = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"format=rgba,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0"
            )
        else:
            geometry = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"format=rgba"
            )
    else:  # pragma: no cover - Composition.fit é Literal fechado
        raise CompileError(f"overlay {layer.shot_id!r} has unsupported fit {layer.fit!r}")

    if opacity < 1.0:
        aa = max(0.0, min(1.0, opacity))
        geometry += f",colorchannelmixer=aa={aa:.2f}"

    if scale == 1.0 and pos_x == 0.5 and pos_y == 0.5:
        x_expr, y_expr = "0", "0"
    else:
        x_val = int((width - target_w) * pos_x)
        y_val = int((height - target_h) * pos_y)
        x_expr, y_expr = str(x_val), str(y_val)

    start = _seconds(layer.start_ticks, tps)
    end = _seconds(layer.start_ticks + layer.duration_ticks, tps)
    enable = f"gte(t,{start:.3f})*lt(t,{end:.3f})"

    prefix = ""
    extra_overlay = ""
    if layer.media_type == "video":
        offset_ticks = getattr(layer, "asset_offset_ticks", 0)
        offset_s = offset_ticks / tps if offset_ticks > 0 else 0.0
        if offset_s > 0.0:
            prefix = f"trim=start={offset_s:.6f},setpts=PTS-STARTPTS+{start:.3f}/TB,"
        else:
            prefix = f"setpts=PTS-STARTPTS+{start:.3f}/TB,"
        extra_overlay = ":eof_action=pass"

    return (
        f"[{number}:v]{prefix}{geometry}[g{number}];"
        f"[{previous}][g{number}]overlay={x_expr}:{y_expr}:format=auto{extra_overlay}:enable='{enable}'[ov{number}]"
    )


def _zoompan(motion: Motion, frames: int, width: int, height: int, rate: str) -> str:
    """Expressões Ken Burns derivadas de ``motion_effects.calculate_motion_curve``."""
    curve = calculate_motion_curve(motion, zoom_factor=1.10)
    mode = curve.motion
    center = "iw/2-(iw/zoom/2)"
    if mode == "zoom_in":
        delta = curve.end.scale - curve.start.scale
        zoom, x = f"{curve.start.scale:.0f}+{delta:.2f}*on/{frames}", center
    elif mode == "zoom_out":
        delta = curve.start.scale - curve.end.scale
        zoom, x = f"{curve.start.scale:.2f}-{delta:.2f}*on/{frames}", center
    elif mode == "pan_right":
        zoom, x = "1.12", f"(iw-iw/zoom)*on/{frames}"
    elif mode == "pan_left":
        zoom, x = "1.12", f"(iw-iw/zoom)*(1-on/{frames})"
    elif mode == "none":
        zoom, x = "1", center
    else:  # pragma: no cover - Motion é Literal fechado
        raise CompileError(f"unknown motion {mode!r}")
    return f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={rate}"


_XFADE_MAP: dict[str, str] = {
    "crossfade": "fade",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
}


def _compile_concat(structure: PlanStructure, work: str) -> ConcatExecution:
    """Compila a montagem entre shots: concat demuxer rápido ou ``xfade`` real inter-segmento."""
    has_xfade = any(
        shot.transition is not None and shot.transition.kind in INTER_SHOT_TRANSITIONS
        for shot in structure.shots
    )
    output = f"{work}/video_only.mp4"
    manifest_path = f"{work}/concat.txt"
    if not has_xfade:
        return ConcatExecution(
            manifest_path=manifest_path,
            output=output,
            args=(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", manifest_path, "-c", "copy", output,
            ),
        )

    args: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for shot in structure.shots:
        args += ["-i", shot.output]

    parts: list[str] = []
    for i in range(len(structure.shots)):
        parts.append(f"[{i}:v]settb=AVTB,fps={structure.rate},format=yuv420p[s{i}]")

    acc = "s0"
    cursor = structure.shots[0].seconds
    tps = structure.ticks_per_second
    for i in range(len(structure.shots) - 1):
        shot = structure.shots[i]
        next_shot = structure.shots[i + 1]
        tr = shot.transition
        if tr is not None and tr.kind in _XFADE_MAP:
            d = tr.duration_ticks / tps
            half_d = d / 2.0
            offset = cursor - half_d
            xfade_kind = _XFADE_MAP[tr.kind]
            parts.append(f"[{acc}]tpad=stop_duration={half_d:.6f}:stop_mode=clone[p{i}a]")
            parts.append(f"[s{i + 1}]tpad=start_duration={half_d:.6f}:start_mode=clone[p{i}b]")
            parts.append(
                f"[p{i}a][p{i}b]xfade=transition={xfade_kind}:duration={d:.6f}:offset={offset:.6f}[x{i}]"
            )
            acc = f"x{i}"
            cursor += next_shot.seconds
        else:
            parts.append(f"[{acc}][s{i + 1}]concat=n=2:v=1:a=0[x{i}]")
            acc = f"x{i}"
            cursor += next_shot.seconds

    args += [
        "-filter_complex", ";".join(parts),
        "-map", f"[{acc}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        output,
    ]
    return ConcatExecution(
        manifest_path=manifest_path,
        output=output,
        args=tuple(args),
    )


def compile_multitrack_audio_args(
    *,
    multitrack: MultitrackAudioPlan,
    audio_catalog: AudioCatalog,
    video_input: str,
    narration_input: str,
    output_path: str,
    video_codec_args: tuple[str, ...] = ("-c:v", "copy"),
) -> tuple[str, ...]:
    """Compila grafo FFmpeg multitrack (voz + músicas + ambiência + SFX + ducking + loudnorm).

    Valida licenças via ``verify_audio_licenses`` antes de gerar qualquer comando FFmpeg.
    """
    violations = verify_audio_licenses(multitrack, audio_catalog)
    if violations:
        raise CompileError(f"audio license violation: {'; '.join(violations)}")

    events = [
        *multitrack.music_events,
        *multitrack.ambience_events,
        *multitrack.sfx_events,
    ]
    args: list[str] = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", video_input,
        "-i", narration_input,
    ]
    ducked_labels: list[str] = []
    fg_labels: list[str] = ["[nar]"]
    parts: list[str] = []
    for idx, ev in enumerate(events, start=2):
        track = audio_catalog.get_track(ev.track_id)
        if track is None or not track.file_path:
            raise CompileError(f"audio track {ev.track_id!r} has no file_path in catalog")
        args += ["-i", track.file_path]
        chain = [
            f"[{idx}:a]aresample=44100",
            "aformat=channel_layouts=stereo",
            f"atrim=start=0:duration={ev.duration_s:.3f}",
            "asetpts=PTS-STARTPTS",
            f"volume={ev.gain_db:.2f}dB",
        ]
        if ev.fade_in_s > 0.0:
            chain.append(f"afade=t=in:st=0:d={ev.fade_in_s:.3f}")
        if ev.fade_out_s > 0.0:
            fade_st = max(0.0, ev.duration_s - ev.fade_out_s)
            chain.append(f"afade=t=out:st={fade_st:.3f}:d={ev.fade_out_s:.3f}")
        if ev.start_s > 0.0:
            delay_ms = int(round(ev.start_s * 1000))
            chain.append(f"adelay={delay_ms}|{delay_ms}")
        lbl = f"ev{idx}"
        parts.append(f"{','.join(chain)}[{lbl}]")
        if ev.ducked:
            ducked_labels.append(f"[{lbl}]")
        else:
            fg_labels.append(f"[{lbl}]")

    if ducked_labels:
        parts.insert(
            0,
            f"[1:a]aresample=44100,aformat=channel_layouts=stereo,highpass=f={multitrack.highpass_voice_hz:.0f},"
            f"apad=whole_dur={multitrack.total_duration_s:.3f},asplit=2[nar][nsc]",
        )
        if len(ducked_labels) == 1:
            bed_lbl = ducked_labels[0]
        else:
            parts.append(f"{''.join(ducked_labels)}amix=inputs={len(ducked_labels)}:duration=longest:normalize=0[bed]")
            bed_lbl = "[bed]"
        ratio = max(1.0, min(20.0, abs(multitrack.ducking_attenuation_db)))
        parts.append(f"{bed_lbl}[nsc]sidechaincompress=threshold=0.02:ratio={ratio:.1f}:attack=15:release=350[duck]")
        fg_labels.append("[duck]")
    else:
        parts.insert(
            0,
            f"[1:a]aresample=44100,aformat=channel_layouts=stereo,highpass=f={multitrack.highpass_voice_hz:.0f},"
            f"apad=whole_dur={multitrack.total_duration_s:.3f}[nar]",
        )

    parts.append(
        f"{''.join(fg_labels)}amix=inputs={len(fg_labels)}:duration=longest:normalize=0,"
        f"loudnorm=I={multitrack.target_lufs:.1f}:TP={multitrack.target_true_peak_dbtp:.1f}:LRA=11[a]"
    )
    args += [
        "-filter_complex", ";".join(parts),
        "-map", "0:v", "-map", "[a]",
        *video_codec_args,
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{multitrack.total_duration_s:.3f}",
        "-movflags", "+faststart", output_path,
    ]
    return tuple(args)


def _fade_filter(
    transition: Transition | None,
    seconds: float,
    tps: int,
    shot_id: str,
    schema_version: int = 2,
) -> str:
    """Filtro de fade do segmento: entrada ``FADE_S`` e saída pela ``Shot.transition``.

    Transições inter-segmento (``crossfade``, ``slide_*``, ``wipe_*``) NÃO aplicam fade-to-black
    individual: são compiladas via ``xfade`` em ``_compile_concat``.
    """
    if transition is not None:
        if transition.kind == "fade":
            fade = transition.duration_ticks / tps
            if fade > seconds:
                raise CompileError(
                    f"shot {shot_id!r} declares a {transition.duration_ticks}-tick {transition.kind} "
                    f"({fade:.3f}s) longer than the shot ({seconds:.3f}s)"
                )
            return (
                f"fade=t=in:st=0:d={FADE_S},"
                f"fade=t=out:st={max(0.0, seconds - fade):.3f}:d={fade:.3f}"
            )
        if transition.kind in ("cut", *_XFADE_MAP):
            return ""
        if transition.kind != "none":
            raise CompileError(f"shot {shot_id!r} uses unsupported transition kind {transition.kind!r}")

    # transition.kind == "none" ou transition is None
    if schema_version >= 2:
        return ""
    return (
        f"fade=t=in:st=0:d={FADE_S},"
        f"fade=t=out:st={max(0.0, seconds - FADE_S):.3f}:d={FADE_S}"
    )


def _seconds(ticks: int, tps: int) -> float:
    return ticks / tps


def _shot_dict(shot: ShotExecution) -> dict:
    return {
        "scene_id": shot.scene_id,
        "shot_id": shot.shot_id,
        "asset_id": shot.asset_id,
        "media_type": shot.media_type,
        "source": shot.source,
        "start_ticks": shot.start_ticks,
        "duration_ticks": shot.duration_ticks,
        "frames": shot.frames,
        "motion": shot.motion,
        "static_overlay": _overlay_dict(shot.static_overlay),
        "captions": [_overlay_dict(c) for c in shot.captions],
        "text_card": _overlay_dict(shot.text_card) if shot.text_card is not None else None,
        "filter_complex": shot.filter_complex,
        "output": shot.output,
        "args": list(shot.args),
        "overlays": [_layer_dict(layer) for layer in shot.overlays],
    }


def _layer_dict(layer: LayerExecution) -> dict:
    return {
        "shot_id": layer.shot_id,
        "asset_id": layer.asset_id,
        "media_type": layer.media_type,
        "source": layer.source,
        "z_index": layer.z_index,
        "start_ticks": layer.start_ticks,
        "duration_ticks": layer.duration_ticks,
        "fit": layer.fit,
        "opacity": getattr(layer, "opacity", 1.0),
        "scale": getattr(layer, "scale", 1.0),
        "position_x": getattr(layer, "position_x", 0.5),
        "position_y": getattr(layer, "position_y", 0.5),
    }


def _overlay_dict(overlay: OverlayImage) -> dict:
    return {
        "kind": overlay.kind,
        "path": overlay.path,
        "text": overlay.text,
        "label": overlay.label,
        "disclosure": overlay.disclosure,
        "enable": overlay.enable,
        "start_ticks": overlay.start_ticks,
        "end_ticks": overlay.end_ticks,
    }


def _digest(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
