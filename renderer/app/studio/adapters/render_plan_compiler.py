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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..application.render_compiler import (
    CompileError,
    LayerExecution,
    MusicTrack,
    NarrationTrack,
    PlanStructure,
    ShotPlan,
    structure_render_plan,
)
from ..domain.asset_resolver import AssetDescriptor
from ..domain.captions import CaptionLine, WordTiming
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
    concat = ConcatExecution(
        manifest_path=f"{work}/concat.txt",
        output=f"{work}/video_only.mp4",
        args=(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", f"{work}/concat.txt", "-c", "copy", f"{work}/video_only.mp4",
        ),
    )
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
    """Composição de uma camada de imagem (VE-02 / INT-03) sobre o segmento base hospedeiro.

    Suporta geometria fit (cover/contain), opacidade (colorchannelmixer), escala e coordenadas
    relativas de posicionamento x/y.
    """
    scale = getattr(layer, "scale", 1.0) or 1.0
    opacity = getattr(layer, "opacity", 1.0)
    pos_x = getattr(layer, "position_x", 0.5)
    pos_y = getattr(layer, "position_y", 0.5)

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
    return (
        f"[{number}:v]{geometry}[g{number}];"
        f"[{previous}][g{number}]overlay={x_expr}:{y_expr}:format=auto:enable='{enable}'[ov{number}]"
    )


def _zoompan(motion: Motion, frames: int, width: int, height: int, rate: str) -> str:
    """Expressões do Ken Burns legado (``index % 4``) escolhidas **explicitamente** pelo plano."""
    mode = motion
    center = "iw/2-(iw/zoom/2)"
    if mode == "zoom_in":
        zoom, x = f"1+0.10*on/{frames}", center
    elif mode == "zoom_out":
        zoom, x = f"1.10-0.10*on/{frames}", center
    elif mode == "pan_right":
        zoom, x = "1.12", f"(iw-iw/zoom)*on/{frames}"
    elif mode == "pan_left":
        zoom, x = "1.12", f"(iw-iw/zoom)*(1-on/{frames})"
    elif mode == "none":
        zoom, x = "1", center
    else:  # pragma: no cover - Motion é Literal fechado
        raise CompileError(f"unknown motion {mode!r}")
    return f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={rate}"


def _fade_filter(
    transition: Transition | None,
    seconds: float,
    tps: int,
    shot_id: str,
    schema_version: int = 2,
) -> str:
    """Filtro de fade do segmento: entrada ``FADE_S`` e saída pela ``Shot.transition``.

    Em v2 (schema_version >= 2):
    - 'cut' ou 'none' (ou ausente) produzem corte seco (retornam "")
    - 'fade' aplica fade out configurado

    Em v1 (schema_version == 1):
    - 'none' (ou ausente) preserva fade legado (entrada + saída FADE_S)
    - 'fade' aplica fade out configurado
    """
    if transition is not None and transition.kind in ("fade", "crossfade"):
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
    if transition is not None and transition.kind == "cut":
        return ""
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
