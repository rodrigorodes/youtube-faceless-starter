"""Compilador puro ``RenderPlan`` -> plano de execução FFmpeg (RP-023) — sem I/O.

Decisão §5.4 do design/ADR-001: a transformação plano -> comandos/graph é uma **função
pura**, no núcleo; só o ``subprocess`` mora no executor (``adapters/``). Este módulo
importa apenas o domínio (``RenderPlan`` e ``AssetDescriptor``) — nada de ``ffmpeg``,
``subprocess``, `PIL`, ``numpy`` ou SDK de provedor — e é por isso que os contratos são
testáveis sem FFmpeg instalado. A guarda de arquitetura prova isso por execução
(``tests/test_architecture.py::test_render_core_has_no_media_or_provider_sdks``).

O compilador recebe os assets **já resolvidos** (RP-04: ``AssetDescriptor`` com
disponibilidade, hash e metadado técnico) e devolve ``CompiledRender``: um plano de
execução determinístico, com um segmento por shot, a trilha de narração, a trilha
gerada (música ou silêncio de mesmo comprimento) e a montagem (concat + mixagem).

Paridade com o renderer legado (``adapters/render_ffmpeg.py``), que é a régua do §11:
mesmo ``scale`` 1.5x lanczos + ``zoompan`` (Ken Burns), mesmo ``format=yuv420p``,
mesmo ``fade`` in/out por segmento, mesmo ``libx264 -preset veryfast -crf 21``, mesmo
concat ``-c copy``, mesma mixagem com ``sidechaincompress`` (ducking) e
``loudnorm=I=-16:TP=-1.5:LRA=11``. O movimento vem do plano (``Effects.motion``), não
de um ``index % 4``.

Limite explícito desta fatia: RP-023 é o esqueleto determinístico. Composição de
**camadas** (shots visuais sobrepostos em tracks diferentes) e transições não triviais
são RP-024; o compilador recusa o plano em vez de produzir um vídeo errado. O executor
(RP-05) é que materializa os overlays (Pillow), sintetiza a trilha e roda o FFmpeg.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from ..domain.asset_resolver import AssetDescriptor
from ..domain.render import FADE_S, LEAD, TAIL
from ..domain.render_plan import (
    AssetReference,
    Effects,
    GeneratedAudioSource,
    Motion,
    RenderPlan,
    Shot,
)

# Movimentos explícitos que o plano pode pedir (``Effects.motion``). O ``Literal`` do
# contrato é a fonte de verdade; a tupla é só a documentação da política do compilador.
MOTION_NAMES = ("none", "zoom_in", "zoom_out", "pan_left", "pan_right")
# Mesmo grafo de mixagem do renderer legado (rich.py/render_ffmpeg.py): a trilha é
# comprimida por sidechain com a narração e a mistura mira -16 LUFS.
MIX_FILTER = (
    "[1:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[nar][nsc];"
    "[2:a]volume=0.40,pan=stereo|c0=c0|c1=c0[mus];"
    "[mus][nsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
    "[duck][nar]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
)


class CompileError(ValueError):
    """O plano não pode ser compilado como está (asset ausente, camadas, texto sem conteúdo)."""


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


@dataclass(frozen=True)
class VoiceInput:
    """Fala de uma cena: o WAV que o executor sintetiza (ou silêncio, quando não há fala)."""

    scene_id: str
    source_id: str | None
    path: str


@dataclass(frozen=True)
class NarrationTrack:
    voices: tuple[VoiceInput, ...]
    output: str
    lead_seconds: float
    tail_seconds: float
    sample_rate: int = 44100


@dataclass(frozen=True)
class MusicTrack:
    source_id: str
    duration_ticks: int
    silent: bool
    params: dict[str, str | int | float | bool] = field(default_factory=dict)


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
    """Compila ``plan`` + assets resolvidos em comandos/graphs determinísticos.

    ``assets`` é um mapeamento ``asset_id -> AssetDescriptor`` (o resultado de
    ``ResolvePlanAssets``). ``labels`` é o selo editorial por cena: ele **não** faz parte
    do contrato do plano (é apresentação do storyboard), então entra explicitamente e
    nunca é inventado. Levanta ``CompileError`` — nunca devolve um comando que
    renderizaria algo diferente do plano.
    """
    if not isinstance(plan, RenderPlan):
        raise CompileError("plan must be a RenderPlan")
    if not isinstance(work_dir, str) or not work_dir.strip():
        raise CompileError("work_dir must be a non-blank string")
    work = work_dir.rstrip("/") or "/"
    by_id = _resolved(assets)
    label_by_scene = _labels(labels)
    manifest = {reference.asset_id: reference for reference in plan.asset_manifest}
    tps = plan.timeline.ticks_per_second
    output = plan.output
    fps_num, fps_den = plan.timeline.timebase.fps_num, plan.timeline.timebase.fps_den
    rate = str(fps_num) if fps_den == 1 else f"{fps_num}/{fps_den}"

    ordered_shots = _ordered_shots(plan)
    _require_single_layer(ordered_shots, plan.timeline.duration_ticks)

    subtitles = sorted(plan.timeline.subtitles, key=lambda c: c.start_tick)
    shots: list[ShotExecution] = []
    for index, (scene, shot) in enumerate(ordered_shots):
        reference = manifest.get(shot.asset_ref)
        if reference is None:
            raise CompileError(f"shot {shot.shot_id!r} references asset {shot.asset_ref!r} absent from the plan manifest")
        descriptor = by_id.get(shot.asset_ref)
        if descriptor is None:
            raise CompileError(f"asset {shot.asset_ref!r} was not resolved before compiling the plan")
        _check_descriptor(reference, descriptor)
        if not descriptor.available:
            raise CompileError(f"asset {shot.asset_ref!r} is unavailable at {descriptor.uri!r}")
        shots.append(
            _compile_shot(
                plan, scene, shot, reference, descriptor, index, work, tps, rate,
                (output.width, output.height), subtitles, label_by_scene.get(scene.scene_id, ""),
            )
        )

    narration = _compile_narration(plan, work)
    music = _compile_music(plan)
    music_path = f"{work}/music.wav"
    final_output = f"{work}/final.mp4"
    concat = ConcatExecution(
        manifest_path=f"{work}/concat.txt",
        output=f"{work}/video_only.mp4",
        args=(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", f"{work}/concat.txt", "-c", "copy", f"{work}/video_only.mp4",
        ),
    )
    audio = AudioMix(
        narration=narration,
        music=music,
        music_path=music_path,
        filter_complex=MIX_FILTER,
        args=(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", concat.output, "-i", narration.output, "-i", music_path,
            "-filter_complex", MIX_FILTER,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", final_output,
        ),
    )
    return CompiledRender(
        plan_id=plan.plan_id,
        revision=plan.revision,
        format=output.format.value,
        width=output.width,
        height=output.height,
        fps_num=fps_num,
        fps_den=fps_den,
        ticks_per_second=tps,
        total_ticks=plan.timeline.duration_ticks,
        shots=tuple(shots),
        concat=concat,
        audio=audio,
        final_output=final_output,
        final_args=audio.args,
    )


# --------------------------------------------------------------------------- helpers


def _resolved(assets: Mapping[str, AssetDescriptor]) -> dict[str, AssetDescriptor]:
    if not isinstance(assets, Mapping):
        raise CompileError("assets must map asset ids to AssetDescriptor")
    resolved: dict[str, AssetDescriptor] = {}
    for asset_id, descriptor in assets.items():
        if not isinstance(descriptor, AssetDescriptor):
            raise CompileError(f"asset {asset_id!r} does not carry an AssetDescriptor")
        resolved[asset_id] = descriptor
    return resolved


def _labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    if labels is None:
        return {}
    if not isinstance(labels, Mapping):
        raise CompileError("labels must map scene ids to their on-screen badge")
    return {str(scene_id): str(label) for scene_id, label in labels.items()}


def _ordered_shots(plan: RenderPlan) -> list[tuple[object, Shot]]:
    pairs = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.shots]
    return sorted(pairs, key=lambda pair: (pair[1].start_tick, pair[0].scene_id, pair[1].shot_id))


def _require_single_layer(ordered: list[tuple[object, Shot]], total_ticks: int) -> None:
    """RP-023 compila uma única trajetória visual; camadas sobrepostas são RP-024."""
    if not ordered:
        raise CompileError("the plan has no visual shots to compile")
    cursor = 0
    for scene, shot in ordered:
        if shot.start_tick > cursor:
            raise CompileError(
                f"gap at tick {cursor}: shot {shot.shot_id!r} starts at {shot.start_tick}"
            )
        if shot.start_tick < cursor:
            raise CompileError(
                f"layered/overlapping visual composition at tick {shot.start_tick} "
                f"(shot {shot.shot_id!r}, track {shot.track_id!r}): layer compositing is RP-024, "
                f"the pure compiler refuses to produce a wrong video"
            )
        cursor = shot.start_tick + shot.duration_ticks
    if cursor != total_ticks:
        raise CompileError(f"visual coverage ends at tick {cursor}, but the timeline ends at {total_ticks}")


def _check_descriptor(reference: AssetReference, descriptor: AssetDescriptor) -> None:
    if descriptor.content_sha256 != reference.content_sha256:
        raise CompileError(
            f"resolved content_sha256 of asset {reference.asset_id!r} does not match the plan manifest"
        )
    if descriptor.media_type != reference.media_type:
        raise CompileError(
            f"resolved media_type of asset {reference.asset_id!r} does not match the plan manifest"
        )


def _frames(duration_ticks: int, fps_num: int, fps_den: int, tps: int) -> int:
    frames = round(Fraction(duration_ticks * fps_num, tps * fps_den))
    if frames < 1:
        raise CompileError(
            f"a {duration_ticks}-tick shot is shorter than one frame at {fps_num}/{fps_den} fps"
        )
    return frames


def _compile_shot(
    plan: RenderPlan,
    scene,
    shot: Shot,
    reference: AssetReference,
    descriptor: AssetDescriptor,
    index: int,
    work: str,
    tps: int,
    rate: str,
    size: tuple[int, int],
    subtitles: list,
    label: str,
) -> ShotExecution:
    width, height = size
    frames = _frames(shot.duration_ticks, plan.timeline.timebase.fps_num, plan.timeline.timebase.fps_den, tps)
    seconds = shot.duration_ticks / tps
    source = descriptor.location or descriptor.uri
    text_card: OverlayImage | None = None
    parts: list[str] = []

    if descriptor.media_type in ("image", "graphic"):
        parts.append(
            f"[0:v]scale={int(width * 1.5)}:{int(height * 1.5)}:flags=lanczos,"
            f"{_zoompan(shot.effects, frames, width, height, rate)},format=yuv420p[b0]"
        )
    elif descriptor.media_type == "video":
        parts.append(
            f"[0:v]trim=start=0:duration={seconds:.6f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:flags=lanczos,fps={rate},format=yuv420p[b0]"
        )
    elif descriptor.media_type == "text":
        text = (reference.metadata.get("text") or "").strip()
        if not text:
            raise CompileError(
                f"text asset {reference.asset_id!r} has no 'text' metadata; the executor cannot render an empty card"
            )
        text_card = OverlayImage(kind="text", path=f"{work}/text_{index:03d}.png", text=text)
        source = text_card.path
        parts.append(f"[0:v]scale={width}:{height}:flags=lanczos,fps={rate},format=yuv420p[b0]")
    else:  # pragma: no cover - AssetMediaType é Literal fechado
        raise CompileError(f"unsupported media type {descriptor.media_type!r}")

    static = OverlayImage(
        kind="static",
        path=f"{work}/static_{index:03d}.png",
        label=label,
        disclosure=plan.output.disclosure,
    )
    parts.append("[b0][1:v]overlay=0:0:format=auto[o1]")
    last = "o1"

    captions: list[OverlayImage] = []
    for cue in subtitles:
        if not (shot.start_tick <= cue.start_tick < shot.start_tick + shot.duration_ticks):
            continue
        start_ticks = cue.start_tick - shot.start_tick
        end_ticks = start_ticks + cue.duration_ticks
        if end_ticks > shot.duration_ticks:
            raise CompileError(
                f"subtitle {cue.text!r} crosses the end of shot {shot.shot_id!r}; "
                f"splitting a caption across shots is RP-024"
            )
        enable = f"gte(t,{_seconds(start_ticks, tps):.3f})*lt(t,{_seconds(end_ticks, tps):.3f})"
        # inputs: 0 = mídia, 1 = selo/disclosure, 2.. = legendas (na ordem dos argumentos)
        number = len(captions) + 2
        parts.append(f"[{last}][{number}:v]overlay=0:0:format=auto:enable='{enable}'[o{number}]")
        last = f"o{number}"
        captions.append(
            OverlayImage(
                kind="caption",
                path=f"{work}/cue_{index:03d}_{len(captions):02d}.png",
                text=cue.text,
                enable=enable,
                start_ticks=start_ticks,
                end_ticks=end_ticks,
            )
        )

    fade_out = max(0.0, seconds - FADE_S)
    parts.append(f"[{last}]fade=t=in:st=0:d={FADE_S},fade=t=out:st={fade_out:.3f}:d={FADE_S}[v]")
    filter_complex = ";".join(parts)

    output = f"{work}/scene_{index:03d}.mp4"
    args: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-i", static.path]
    for caption in captions:
        args += ["-i", caption.path]
    args += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-frames:v", str(frames), "-r", rate,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", output,
    ]
    return ShotExecution(
        scene_id=scene.scene_id,
        shot_id=shot.shot_id,
        asset_id=reference.asset_id,
        media_type=descriptor.media_type,
        source=source,
        start_ticks=shot.start_tick,
        duration_ticks=shot.duration_ticks,
        frames=frames,
        motion=shot.effects.motion,
        static_overlay=static,
        captions=tuple(captions),
        text_card=text_card,
        filter_complex=filter_complex,
        output=output,
        args=tuple(args),
    )


def _zoompan(effects: Effects, frames: int, width: int, height: int, rate: str) -> str:
    """Expressões do Ken Burns legado (``index % 4``) escolhidas **explicitamente** pelo plano."""
    mode = effects.motion
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


def _compile_narration(plan: RenderPlan, work: str) -> NarrationTrack:
    generated = {source.source_id for source in plan.generated_audio if source.kind == "voice"}
    cues: dict[str, list] = {}
    for cue in plan.timeline.narration:
        cues.setdefault(cue.scene_id, []).append(cue)
    voices: list[VoiceInput] = []
    for index, scene in enumerate(sorted(plan.timeline.scenes, key=lambda s: s.start_tick)):
        scene_cues = sorted(cues.get(scene.scene_id, []), key=lambda c: c.start_tick)
        source_id = scene_cues[0].source_ref if scene_cues else None
        if source_id is not None and source_id not in generated:
            # Não há tipo de mídia de áudio em `AssetReference`; a fala real é gerada (C2).
            raise CompileError(
                f"narration cue of scene {scene.scene_id!r} references {source_id!r}, "
                f"which is not a generated voice source"
            )
        voices.append(VoiceInput(scene_id=scene.scene_id, source_id=source_id, path=f"{work}/speech_{index:03d}.wav"))
    return NarrationTrack(voices=tuple(voices), output=f"{work}/narration.wav", lead_seconds=LEAD, tail_seconds=TAIL)


def _compile_music(plan: RenderPlan) -> MusicTrack:
    sources = [source for source in plan.generated_audio if source.kind == "music"]
    if len(sources) != 1:
        raise CompileError(f"the plan must carry exactly one generated music source, found {len(sources)}")
    source: GeneratedAudioSource = sources[0]
    return MusicTrack(
        source_id=source.source_id,
        duration_ticks=source.duration_ticks,
        silent=source.silent,
        params=dict(source.params),
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