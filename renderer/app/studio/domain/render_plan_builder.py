"""Builder puro do ``RenderPlan`` (RP-015/RP-016) — domínio puro, sem I/O.

Converte o **storyboard real** — as cenas editoriais já produzidas e a duração da fala
**medida depois do TTS** (R1: é o único ponto onde a duração existe) — em um
``RenderPlan`` v1 válido, sem conhecer renderer, FFmpeg, banco ou provedor.

Decisões refletidas aqui (design §5/§11, ADR-001):

- **Ticks no plano, segundos na autoria** (R1): a cena editorial continua em segundos
  (``VisualBeat``/``scene_length``); a ponte é ``domain.ticks``, a mesma da fatia 3. As
  fronteiras de cena são as janelas contíguas do ``beat_plan`` convertidas em ticks — a
  convergência compartilhada (mesma fronteira float -> mesmo tick) preserva a cobertura
  sem reintroduzir deriva.
- **Shots explícitos** (RP-011/R3): o builder gera **um shot por cena** (R1/C4 — o
  produtor de beats é fatia separada) com ``effects.motion`` explícito. A política
  default é ``none``; o ``index % 4`` do renderer legado **não** é reintroduzido: quem
  quiser os quatro movimentos os declara por cena.
- **``style_snapshot`` por chave + versão** (R4/RP-016): a identidade do canal entra como
  ``StyleSnapshot(style_id, version)`` — nunca o objeto nem o texto livre de estilo.
- **Áudio gerado** (C2): a voz de cada cena é uma ``GeneratedAudioSource(kind="voice")``
  (unidade real de TTS) e a trilha é ``kind="music"`` com os parâmetros determinísticos
  da síntese (bpm 122, seed 7). ``music=False`` vira trilha **silenciosa** de mesmo
  comprimento — o mesmo grafo de mixagem do renderer.
- **``content_sha256`` do conteúdo** (C1): o builder **recebe** o hash do manifesto e
  nunca o deriva de ``assets.cache_key`` (que é hash de *entrada*).

Limites explícitos desta fatia: sem persistência, sem render e sem resolver assets. O
plano é construído no render (``RunRender``) por quem já tem a fala medida; a fiação
atrás de flag é da fatia do executor (RP-05).
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .channel import ChannelProfile
from .contracts import Asset, Scene as StoryboardRow, VideoFormat
from .render import FPS, LEAD, SIZE, make_cues, scene_length
from .render_plan import (
    AssetMediaType,
    AssetReference,
    Composition,
    Effects,
    GeneratedAudioSource,
    Motion,
    NarrationCue,
    Output,
    Provenance,
    RenderPlan,
    Scene as PlanScene,
    Shot,
    StyleSnapshot,
    SubtitleCue,
    Timebase,
    Timeline,
    Track,
)
from .ticks import seconds_to_ticks, tick_windows

# 25 fps com 1 000 ticks por quadro: o quadro inteiro (1/25 s) cai sempre num tick inteiro
# e a legenda/narração têm granularidade de 1 ms. A taxa de quadros continua 25 (decisão §5.2).
DEFAULT_TICKS_PER_SECOND = FPS * 1000
DEFAULT_BUILDER_VERSION = "render-plan-builder/1"
DEFAULT_DISCLOSURE = "Ilustração gerada por IA"
# Parâmetros determinísticos da trilha sintetizada por `rich.synth_music` (seed fixa = 7, bpm 122).
DEFAULT_MUSIC_PARAMS = {"bpm": 122, "seed": 7}
VISUAL_TRACK = "visual-main"
NARRATION_TRACK = "narration-main"
SUBTITLE_TRACK = "subtitle-main"
MUSIC_SOURCE = "music"


class PlanBuildError(ValueError):
    """O storyboard não pode virar um plano válido (entrada inconsistente, não I/O)."""


@dataclass(frozen=True)
class StoryboardScene:
    """Uma cena editorial já produzida, com a **fala medida** depois do TTS (R1).

    ``speech_seconds`` é a duração devolvida pela síntese de voz (``Voice.speak``); a
    duração da cena é derivada dela com ``scene_length`` (lead/tail + quadros inteiros),
    exatamente como o renderer legado faz. ``speech_seconds == 0`` representa uma cena
    silenciosa: sem cue de narração, sem legenda, com shot de duração ``scene_length(0)``.
    """

    scene_id: str
    asset_id: str
    narration: str
    speech_seconds: float
    label: str = ""
    paid_operation_key: str | None = None


def style_snapshot_for_channel(profile: ChannelProfile) -> StyleSnapshot:
    """RP-016: consome a identidade versionada do canal por **chave + versão** (R4)."""
    return StyleSnapshot(source="channel", style_id=profile.id, version=profile.version)


def storyboard_scene(
    row: StoryboardRow,
    *,
    speech_seconds: float,
    scene_id: str | None = None,
) -> StoryboardScene:
    """Projeta a cena editorial do banco no insumo do builder (RP-015).

    A duração da fala **não** está na cena (R1: `studio.scenes.duration_s` não é escrita);
    ela entra como parâmetro, medida depois do TTS. É a única parte que o storyboard não
    fornece — o resto (narração, selo, asset) vem da linha real.
    """
    if row.asset_id is None:
        raise PlanBuildError(f"scene {row.id!r} has no asset: produce the assets before building the plan")
    return StoryboardScene(
        scene_id=scene_id or row.id,
        asset_id=row.asset_id,
        narration=row.narration,
        speech_seconds=speech_seconds,
        label=row.label,
    )


def asset_reference_for(
    asset: Asset,
    *,
    content_sha256: str,
    media_type: AssetMediaType = "image",
    metadata: Mapping[str, str] | None = None,
    uri: str | None = None,
    asset_version: int = 1,
) -> AssetReference:
    """Projeta um ``Asset`` do storyboard numa referência do manifesto (RP-015/RP-020).

    O ``content_sha256`` é **obrigatório e explícito** (C1): o ``cache_key`` do asset é
    hash de entrada e o do vídeo inclui ``job.id``; quem tem os bytes (ou o descritor
    físico) informa o hash do conteúdo. Os metadados de proveniência do provedor ficam
    fora do contrato obrigatório: só o tipo editorial do asset entra por default.
    """
    base = {"asset_kind": asset.kind.value}
    if metadata:
        base.update({str(k): str(v) for k, v in metadata.items()})
    return AssetReference(
        asset_id=asset.id,
        asset_version=asset_version,
        uri=uri or asset.path,
        content_sha256=content_sha256,
        media_type=media_type,
        license=asset.license,
        attribution=asset.attribution,
        source_url=asset.source_url,
        metadata=base,
    )


def build_render_plan(
    *,
    plan_id: str,
    revision: int,
    project_id: str,
    video_id: str,
    format: VideoFormat,
    scenes: Sequence[StoryboardScene],
    assets: Sequence[AssetReference],
    style_snapshot: StyleSnapshot,
    builder_version: str = DEFAULT_BUILDER_VERSION,
    disclosure: str = DEFAULT_DISCLOSURE,
    music: bool = True,
    timebase: Timebase | None = None,
    motions: Mapping[str, Motion] | None = None,
    created_at: datetime | None = None,
) -> RenderPlan:
    """Constrói um ``RenderPlan`` v1 válido a partir do storyboard medido.

    Determinístico: a mesma entrada (e a mesma ordem de cenas) produz o **mesmo** plano.
    Levanta ``PlanBuildError`` para entrada inconsistente; o contrato (``RenderPlan``)
    levanta ``ValidationError`` para o que é de forma (duração fora do formato, ids etc.).
    """
    timebase = timebase or Timebase(ticks_per_second=DEFAULT_TICKS_PER_SECOND)
    tps = timebase.ticks_per_second
    ordered = _ordered_scenes(scenes)
    manifest = _manifest_by_id(assets)
    motion_by_scene = _motions(motions, ordered)

    lengths: list[float] = []
    offsets: list[float] = []
    cursor = 0.0
    for scene in ordered:
        speech = _speech_seconds(scene)
        length = scene_length(speech)
        offsets.append(cursor)
        lengths.append(length)
        cursor += length
    windows = tick_windows(
        [(offsets[i], offsets[i] + lengths[i]) for i in range(len(ordered))],
        tps,
        duration_s=cursor,
    )

    plan_scenes: list[PlanScene] = []
    narration: list[NarrationCue] = []
    subtitles: list[SubtitleCue] = []
    generated: list[GeneratedAudioSource] = []
    for scene, window, offset_s, _length_s in zip(ordered, windows, offsets, lengths):
        start_tick, end_tick = window
        duration_ticks = end_tick - start_tick
        reference = manifest.get(scene.asset_id)
        if reference is None:
            raise PlanBuildError(
                f"scene {scene.scene_id!r} references asset {scene.asset_id!r} that is not in the manifest"
            )
        shot = Shot(
            shot_id=f"shot:{scene.scene_id}",
            track_id=VISUAL_TRACK,
            start_tick=start_tick,
            duration_ticks=duration_ticks,
            asset_ref=scene.asset_id,
            composition=Composition(fit="cover"),
            effects=Effects(motion=motion_by_scene[scene.scene_id]),
            paid_operation_key=scene.paid_operation_key,
        )
        plan_scenes.append(
            PlanScene(
                scene_id=scene.scene_id,
                start_tick=start_tick,
                duration_ticks=duration_ticks,
                shots=[shot],
                paid_operation_key=scene.paid_operation_key,
            )
        )
        speech = float(scene.speech_seconds)
        if speech > 0:
            voice_id = f"voice:{scene.scene_id}"
            speech_ticks = seconds_to_ticks(speech, tps)
            if speech_ticks < 1:
                raise PlanBuildError(
                    f"scene {scene.scene_id!r} speech of {speech!r}s is below one tick at {tps} ticks/s; "
                    f"use a finer timebase"
                )
            narration.append(
                NarrationCue(
                    scene_id=scene.scene_id,
                    track_id=NARRATION_TRACK,
                    source_ref=voice_id,
                    start_tick=start_tick + seconds_to_ticks(LEAD, tps),
                    duration_ticks=speech_ticks,
                )
            )
            generated.append(
                GeneratedAudioSource(source_id=voice_id, kind="voice", duration_ticks=speech_ticks)
            )
            subtitles.extend(_subtitle_cues(scene, offset_s, speech, tps))

    total_ticks = windows[-1][1]
    generated.append(
        GeneratedAudioSource(
            source_id=MUSIC_SOURCE,
            kind="music",
            duration_ticks=total_ticks + tps,  # a síntese cobre a duração + 1 s (legado)
            silent=not music,
            params={} if not music else dict(DEFAULT_MUSIC_PARAMS),
        )
    )

    return RenderPlan(
        plan_id=plan_id,
        revision=revision,
        project_id=project_id,
        video_id=video_id,
        output=Output(
            format=format,
            width=SIZE[format][0],
            height=SIZE[format][1],
            disclosure=disclosure,
        ),
        timeline=Timeline(
            timebase=timebase,
            tracks=[
                Track(track_id=VISUAL_TRACK, kind="visual"),
                Track(track_id=NARRATION_TRACK, kind="narration"),
                Track(track_id=SUBTITLE_TRACK, kind="subtitle"),
            ],
            scenes=plan_scenes,
            narration=narration,
            subtitles=subtitles,
        ),
        asset_manifest=list(assets),
        generated_audio=generated,
        style_snapshot=style_snapshot,
        provenance=Provenance(builder_version=builder_version, created_at=created_at),
    )


def _ordered_scenes(scenes: Sequence[StoryboardScene]) -> tuple[StoryboardScene, ...]:
    if isinstance(scenes, (str, bytes, bytearray)):
        raise PlanBuildError("scenes must be a sequence of StoryboardScene")
    try:
        ordered = tuple(scenes)
    except TypeError as exc:
        raise PlanBuildError("scenes must be a sequence of StoryboardScene") from exc
    if not ordered:
        raise PlanBuildError("at least one scene is required to build a render plan")
    for index, scene in enumerate(ordered):
        if not isinstance(scene, StoryboardScene):
            raise PlanBuildError(f"scene {index} is not a StoryboardScene")
    seen: set[str] = set()
    for scene in ordered:
        if not scene.scene_id or not scene.scene_id.strip():
            raise PlanBuildError("every scene needs a non-blank scene_id")
        if scene.scene_id in seen:
            raise PlanBuildError(f"duplicate scene_id {scene.scene_id!r}")
        seen.add(scene.scene_id)
        if not scene.asset_id or not scene.asset_id.strip():
            raise PlanBuildError(f"scene {scene.scene_id!r} has a blank asset_id")
    return ordered


def _manifest_by_id(assets: Sequence[AssetReference]) -> dict[str, AssetReference]:
    if isinstance(assets, (str, bytes, bytearray)):
        raise PlanBuildError("assets must be a sequence of AssetReference")
    try:
        items = tuple(assets)
    except TypeError as exc:
        raise PlanBuildError("assets must be a sequence of AssetReference") from exc
    manifest: dict[str, AssetReference] = {}
    for index, reference in enumerate(items):
        if not isinstance(reference, AssetReference):
            raise PlanBuildError(f"asset {index} is not an AssetReference")
        if reference.asset_id in manifest:
            raise PlanBuildError(f"duplicate asset_id {reference.asset_id!r} in the manifest")
        manifest[reference.asset_id] = reference
    return manifest


def _motions(motions: Mapping[str, Motion] | None, scenes: Sequence[StoryboardScene]) -> dict[str, Motion]:
    if motions is None:
        return {scene.scene_id: "none" for scene in scenes}
    if not isinstance(motions, Mapping):
        raise PlanBuildError("motions must map scene ids to a motion")
    known = {scene.scene_id for scene in scenes}
    unknown = sorted(set(motions) - known)
    if unknown:
        raise PlanBuildError(f"motion declared for unknown scene(s): {unknown!r}")
    return {scene.scene_id: motions.get(scene.scene_id, "none") for scene in scenes}


def _speech_seconds(scene: StoryboardScene) -> float:
    value = scene.speech_seconds
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanBuildError(f"scene {scene.scene_id!r} speech_seconds must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise PlanBuildError(f"scene {scene.scene_id!r} speech_seconds must be a finite non-negative number")
    return float(value)


def _subtitle_cues(scene: StoryboardScene, offset_s: float, speech: float, tps: int) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    for chunk_index, cue in enumerate(make_cues(scene.narration, offset_s, speech)):
        start_tick = seconds_to_ticks(cue.start, tps)
        end_tick = seconds_to_ticks(cue.end, tps)
        duration_ticks = end_tick - start_tick
        if duration_ticks < 1:
            raise PlanBuildError(
                f"subtitle chunk {chunk_index} of scene {scene.scene_id!r} is below one tick at "
                f"{tps} ticks/s; use a finer timebase"
            )
        cues.append(
            SubtitleCue(
                scene_id=scene.scene_id,
                track_id=SUBTITLE_TRACK,
                text=cue.text,
                start_tick=start_tick,
                duration_ticks=duration_ticks,
            )
        )
    return cues