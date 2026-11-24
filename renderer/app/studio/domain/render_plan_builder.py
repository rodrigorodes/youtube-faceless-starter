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
from typing import Any, Literal

from pydantic import Field

from .channel import ChannelProfile
from .contracts import Asset, Scene as StoryboardRow, VideoFormat
from .pacing import PacingEngine, PacingPreset
from .render import FPS, LEAD, SIZE, make_cues, scene_length
from .render_plan import (
    AssetMediaType,
    AssetReference,
    AudioMix,
    Composition,
    ConfigSnapshot,
    Effects,
    GeneratedAudioSource,
    Motion,
    NarrationCue,
    NonBlank,
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
    Transition,
    _PlanModel,
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
OVERLAY_TRACK = "visual-overlay"
NARRATION_TRACK = "narration-main"
SUBTITLE_TRACK = "subtitle-main"
MUSIC_SOURCE = "music"


class PlanBuildError(ValueError):
    """O storyboard não pode virar um plano válido (entrada inconsistente, não I/O)."""


class StoryboardShot(_PlanModel):
    """Shot base individual dentro de uma cena do storyboard (VE-02).

    Permite múltiplos cortes/ângulos por cena editorial mantendo a timeline contígua
    e fechada.
    """

    shot_id: NonBlank
    asset_id: NonBlank
    duration_s: float = Field(gt=0.0)
    asset_offset_s: float = Field(default=0.0, ge=0.0)
    motion: Motion = "none"
    transition: Transition | None = None


@dataclass(frozen=True)
class StoryboardScene:
    """Uma cena editorial já produzida, com a **fala medida** depois do TTS (R1).

    ``speech_seconds`` é a duração devolvida pela síntese de voz (``Voice.speak``); a
    duração da cena é derivada dela com ``scene_length`` (lead/tail + quadros inteiros),
    exatamente como o renderer legado faz. ``speech_seconds == 0`` representa uma cena
    silenciosa: sem cue de narração, sem legenda, com shot de duração ``scene_length(0)``.

    ``voice_id`` identifica a voz (nome+modelo) que sintetiza a fala. Ele entra nos ``params``
    da fonte de voz gerada para que o fingerprint da narração (RP-06c) invalide quando a voz
    muda, mesmo com o texto idêntico — sem ele, trocar a voz reusaria um WAV de outra voz.

    ``shots`` é a lista de shots base sequenciais que cobrem a cena (VE-02). Quando ausente
    ou vazia, preserva o comportamento legado de 1 shot base cobrindo toda a cena.
    """

    scene_id: str
    asset_id: str
    narration: str
    speech_seconds: float
    label: str = ""
    paid_operation_key: str | None = None
    voice_id: str = ""
    shots: list[StoryboardShot] | None = None


@dataclass(frozen=True)
class StoryboardOverlay:
    """Overlay de imagem relativo à cena, sem caminho de arquivo (VE-01).

    ``start_s``/``duration_s`` são relativos ao início da cena. O asset já deve estar no
    manifesto (o builder não resolve arquivos); ``z_index`` ordena camadas e ``fit`` é a
    composição dentro do quadro.
    """

    scene_id: str
    asset_id: str
    start_s: float
    duration_s: float
    z_index: int = 1
    fit: Literal["cover", "contain"] = "contain"


def style_snapshot_for_channel(profile: ChannelProfile) -> StyleSnapshot:
    """RP-016: consome a identidade versionada do canal por **chave + versão** (R4)."""
    return StyleSnapshot(source="channel", style_id=profile.id, version=profile.version)


def storyboard_scene(
    row: StoryboardRow,
    *,
    speech_seconds: float,
    scene_id: str | None = None,
    shots: list[StoryboardShot] | None = None,
) -> StoryboardScene:
    """Projeta a cena editorial do banco no insumo do builder (RP-015).

    A duração da fala **não** está na cena (R1: `studio.scenes.duration_s` não é escrita);
    ela entra como parâmetro, medida depois do TTS. É a única parte que o storyboard não
    fornece — o resto (narração, selo, asset) vem da linha real.
    """
    if row.asset_id is None and not shots:
        raise PlanBuildError(f"scene {row.id!r} has no asset: produce the assets before building the plan")
    return StoryboardScene(
        scene_id=scene_id or row.id,
        asset_id=row.asset_id or "",
        narration=row.narration,
        speech_seconds=speech_seconds,
        label=row.label,
        shots=shots,
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
    style_snapshot: StyleSnapshot | None = None,
    style: Any = None,
    transition: Mapping[str, Any] | Transition | None = None,
    builder_version: str = DEFAULT_BUILDER_VERSION,
    disclosure: str = DEFAULT_DISCLOSURE,
    music: bool = True,
    timebase: Timebase | None = None,
    motions: Mapping[str, Motion] | None = None,
    music_params: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
    config_snapshot: ConfigSnapshot | None = None,
    overlays: Sequence[StoryboardOverlay] = (),
    pacing_preset: PacingPreset | str | None = None,
    audio_mix: AudioMix | None = None,
) -> RenderPlan:
    """Constrói um ``RenderPlan`` v1 válido a partir do storyboard medido.

    Determinístico: a mesma entrada (e a mesma ordem de cenas) produz o **mesmo** plano.
    Levanta ``PlanBuildError`` para entrada inconsistente; o contrato (``RenderPlan``)
    levanta ``ValidationError`` para o que é de forma (duração fora do formato, ids etc.).

    ``music_params`` são os parâmetros **do estilo** para a trilha (bpm/seed): quando
    presentes, sobrepõem o default do sistema (``DEFAULT_MUSIC_PARAMS`` — bpm 122, seed 7);
    ausentes/parciais caem no default por chave (o executor lê cada chave com fallback).

    ``config_snapshot`` é a identidade da configuração efetiva congelada (F03.T03) que governou
    voz e render. É opcional e não entra em nenhum fingerprint de cache: um plano antigo, sem a
    referência, continua válido e reusável.
    """
    timebase = timebase or Timebase(ticks_per_second=DEFAULT_TICKS_PER_SECOND)
    tps = timebase.ticks_per_second
    ordered = _ordered_scenes(scenes)
    manifest = _manifest_by_id(assets)
    motion_by_scene = _motions(motions, ordered)
    overlays_by_scene = _overlays_by_scene(overlays, ordered, manifest)

    if style_snapshot is None:
        if style is not None and hasattr(style, "snapshot") and style.snapshot is not None:
            style_snapshot = style.snapshot
        else:
            style_snapshot = StyleSnapshot(style_id="default", version=1)

    if pacing_preset is None and style is not None:
        if hasattr(style, "pacing") and style.pacing:
            pacing_preset = style.pacing
        elif hasattr(style, "params") and isinstance(style.params, Mapping):
            pacing_preset = style.params.get("pacing")
        elif isinstance(style, Mapping) and "pacing" in style:
            pacing_preset = style.get("pacing")

    if isinstance(pacing_preset, str) and pacing_preset.strip().lower() in ("none", ""):
        pacing_preset = None

    if audio_mix is None and style is not None:
        if hasattr(style, "audio_mix") and style.audio_mix:
            audio_mix = style.audio_mix
        elif hasattr(style, "params") and isinstance(style.params, Mapping):
            audio_mix = style.params.get("audio_mix")
        elif isinstance(style, Mapping) and "audio_mix" in style:
            audio_mix = style.get("audio_mix")
        if isinstance(audio_mix, Mapping):
            audio_mix = AudioMix(**audio_mix)

    if music_params is None and style is not None:
        if hasattr(style, "music") and style.music:
            music_params = style.music
        elif hasattr(style, "params") and isinstance(style.params, Mapping):
            music_params = style.params.get("music")
        elif isinstance(style, Mapping) and "music" in style:
            music_params = style.get("music")

    raw_transition = transition
    if raw_transition is None and style is not None:
        if hasattr(style, "transition"):
            raw_transition = style.transition
        elif hasattr(style, "params") and isinstance(style.params, Mapping):
            raw_transition = style.params.get("transition")
        elif isinstance(style, Mapping):
            raw_transition = style.get("transition")

    shot_transition: Transition | None = None
    if isinstance(raw_transition, Transition):
        if raw_transition.kind == "fade" and raw_transition.duration_ticks > 0:
            shot_transition = raw_transition
    elif isinstance(raw_transition, Mapping):
        kind = raw_transition.get("kind", "none")
        duration = int(raw_transition.get("duration_ticks", 0))
        if kind == "fade" and duration > 0:
            shot_transition = Transition(kind="fade", duration_ticks=duration)

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
    num_scenes = len(ordered)
    for index, (scene, window, offset_s, _length_s) in enumerate(zip(ordered, windows, offsets, lengths)):
        start_tick, end_tick = window
        duration_ticks = end_tick - start_tick

        base_transition: Transition | None = None
        if (
            shot_transition is not None
            and index < num_scenes - 1
            and shot_transition.duration_ticks < duration_ticks
        ):
            base_transition = shot_transition

        if scene.shots:
            shot_durations = [seconds_to_ticks(s.duration_s, tps) for s in scene.shots]
            for s_idx, s in enumerate(scene.shots):
                if shot_durations[s_idx] < 1:
                    raise PlanBuildError(
                        f"shot {s.shot_id!r} of scene {scene.scene_id!r} duration "
                        f"{s.duration_s!r}s is below one tick at {tps} ticks/s; use a finer timebase"
                    )
            residue = duration_ticks - sum(shot_durations)
            max_allowed = max(2, int(0.2 * tps))
            if abs(residue) > max_allowed:
                raise PlanBuildError(
                    f"shots duration sum diverges from scene duration by {residue/tps:.3f}s; ensure shots sum matches scene duration"
                )
            if residue != 0:
                shot_durations[-1] += residue
            if shot_durations[-1] < 1:
                raise PlanBuildError(
                    f"shots of scene {scene.scene_id!r} do not fit scene duration: "
                    f"last shot duration became {shot_durations[-1]} ticks"
                )

            curr_tick = start_tick
            num_shots = len(scene.shots)
            base_shots: list[Shot] = []
            for s_idx, (sb_shot, dur) in enumerate(zip(scene.shots, shot_durations)):
                if sb_shot.asset_id not in manifest:
                    raise PlanBuildError(
                        f"shot {sb_shot.shot_id!r} of scene {scene.scene_id!r} references asset "
                        f"{sb_shot.asset_id!r} that is not in the manifest"
                    )

                transition_for_shot = sb_shot.transition
                if transition_for_shot is None and s_idx == num_shots - 1:
                    if base_transition is not None and base_transition.duration_ticks < dur:
                        transition_for_shot = base_transition

                shot_motion = sb_shot.motion
                if shot_motion == "none" and motion_by_scene.get(scene.scene_id, "none") != "none":
                    shot_motion = motion_by_scene[scene.scene_id]

                base_shots.append(
                    Shot(
                        shot_id=sb_shot.shot_id,
                        track_id=VISUAL_TRACK,
                        start_tick=curr_tick,
                        duration_ticks=dur,
                        asset_ref=sb_shot.asset_id,
                        asset_offset_ticks=seconds_to_ticks(sb_shot.asset_offset_s, tps),
                        role="base",
                        z_index=0,
                        composition=Composition(fit="cover"),
                        effects=Effects(motion=shot_motion),
                        transition=transition_for_shot,
                        paid_operation_key=scene.paid_operation_key,
                    )
                )
                curr_tick += dur

            scene_shots = base_shots
        else:
            reference = manifest.get(scene.asset_id)
            if reference is None:
                raise PlanBuildError(
                    f"scene {scene.scene_id!r} references asset {scene.asset_id!r} that is not in the manifest"
                )

            pacing_plan = None
            if pacing_preset is not None:
                kind = getattr(reference, "kind", None) or reference.metadata.get("asset_kind") or reference.media_type
                is_video = kind in ("clip", "video")
                pacing_plan = PacingEngine.calculate(
                    scene_id=scene.scene_id,
                    total_duration_ticks=duration_ticks,
                    ticks_per_second=tps,
                    asset_count=1,
                    preset=pacing_preset,
                    is_video_asset=is_video,
                )

            if pacing_plan is not None and len(pacing_plan.shots) > 1:
                base_shots: list[Shot] = []
                num_pacing = len(pacing_plan.shots)
                for s_idx, st in enumerate(pacing_plan.shots):
                    if s_idx == num_pacing - 1:
                        shot_tr = (
                            base_transition
                            if (base_transition is not None and base_transition.duration_ticks < st.duration_ticks)
                            else None
                        )
                    else:
                        shot_tr = Transition(kind="cut")

                    base_shots.append(
                        Shot(
                            shot_id=f"{scene.scene_id}-shot-{st.shot_index}",
                            track_id=VISUAL_TRACK,
                            start_tick=start_tick + st.start_tick,
                            duration_ticks=st.duration_ticks,
                            asset_ref=scene.asset_id,
                            role="base",
                            z_index=0,
                            composition=Composition(fit="cover"),
                            effects=Effects(motion=st.motion),
                            transition=shot_tr,
                            paid_operation_key=scene.paid_operation_key,
                        )
                    )
                scene_shots = base_shots
            else:
                shot_motion = motion_by_scene[scene.scene_id]
                if shot_motion == "none" and pacing_plan is not None and pacing_plan.shots:
                    shot_motion = pacing_plan.shots[0].motion

                shot = Shot(
                    shot_id=f"shot:{scene.scene_id}",
                    track_id=VISUAL_TRACK,
                    start_tick=start_tick,
                    duration_ticks=duration_ticks,
                    asset_ref=scene.asset_id,
                    composition=Composition(fit="cover"),
                    effects=Effects(motion=shot_motion),
                    transition=base_transition,
                    paid_operation_key=scene.paid_operation_key,
                )
                scene_shots = [shot]

        scene_shots.extend(
            _overlay_shots(
                scene.scene_id, start_tick, end_tick,
                overlays_by_scene.get(scene.scene_id, ()), tps,
            )
        )
        plan_scenes.append(
            PlanScene(
                scene_id=scene.scene_id,
                start_tick=start_tick,
                duration_ticks=duration_ticks,
                shots=scene_shots,
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
                GeneratedAudioSource(source_id=voice_id, kind="voice", duration_ticks=speech_ticks,
                                     params={"voice": scene.voice_id} if scene.voice_id else {})
            )
            subtitles.extend(_subtitle_cues(scene, offset_s, speech, tps))

    total_ticks = windows[-1][1]
    generated.append(
        GeneratedAudioSource(
            source_id=MUSIC_SOURCE,
            kind="music",
            duration_ticks=total_ticks + tps,  # a síntese cobre a duração + 1 s (legado)
            silent=not music,
            params={} if not music else dict(music_params or DEFAULT_MUSIC_PARAMS),
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
            tracks=_tracks(overlays_by_scene),
            scenes=plan_scenes,
            narration=narration,
            subtitles=subtitles,
        ),
        asset_manifest=list(assets),
        generated_audio=generated,
        style_snapshot=style_snapshot,
        provenance=Provenance(builder_version=builder_version, created_at=created_at),
        config_snapshot=config_snapshot,
        audio_mix=audio_mix or AudioMix(),
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
        if not scene.shots and (not scene.asset_id or not scene.asset_id.strip()):
            raise PlanBuildError(f"scene {scene.scene_id!r} has a blank asset_id")
        if scene.shots:
            for s_idx, shot in enumerate(scene.shots):
                if not isinstance(shot, StoryboardShot):
                    raise PlanBuildError(f"shot {s_idx} of scene {scene.scene_id!r} is not a StoryboardShot")
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


def _tracks(overlays_by_scene: Mapping[str, Sequence[StoryboardOverlay]]) -> list[Track]:
    """Tracks do plano; a faixa de overlay só existe quando há overlay."""
    tracks = [Track(track_id=VISUAL_TRACK, kind="visual")]
    if any(overlays_by_scene.values()):
        tracks.append(Track(track_id=OVERLAY_TRACK, kind="visual"))
    tracks.extend([
        Track(track_id=NARRATION_TRACK, kind="narration"),
        Track(track_id=SUBTITLE_TRACK, kind="subtitle"),
    ])
    return tracks


def _overlays_by_scene(
    overlays: Sequence[StoryboardOverlay],
    scenes: Sequence[StoryboardScene],
    manifest: Mapping[str, AssetReference],
) -> dict[str, list[StoryboardOverlay]]:
    """Agrupa e valida os overlays por cena (I15) antes de converter para ticks."""
    if isinstance(overlays, (str, bytes, bytearray)):
        raise PlanBuildError("overlays must be a sequence of StoryboardOverlay")
    try:
        items = tuple(overlays)
    except TypeError as exc:
        raise PlanBuildError("overlays must be a sequence of StoryboardOverlay") from exc
    known = {scene.scene_id for scene in scenes}
    grouped: dict[str, list[StoryboardOverlay]] = {}
    for index, overlay in enumerate(items):
        if not isinstance(overlay, StoryboardOverlay):
            raise PlanBuildError(f"overlay {index} is not a StoryboardOverlay")
        if overlay.scene_id not in known:
            raise PlanBuildError(f"overlay {index} references unknown scene {overlay.scene_id!r}")
        if overlay.asset_id not in manifest:
            raise PlanBuildError(
                f"overlay {index} references asset {overlay.asset_id!r} that is not in the manifest"
            )
        grouped.setdefault(overlay.scene_id, []).append(overlay)
    return grouped


def _overlay_shots(
    scene_id: str,
    start_tick: int,
    end_tick: int,
    overlays: Sequence[StoryboardOverlay],
    tps: int,
) -> list[Shot]:
    """Converte os overlays da cena em shots relativos, ordenados por ``(z_index, start_s, asset_id)``."""
    scene_duration = end_tick - start_tick
    ordered = sorted(overlays, key=lambda overlay: (overlay.z_index, overlay.start_s, overlay.asset_id))
    shots: list[Shot] = []
    for index, overlay in enumerate(ordered):
        start_s = _finite_number(overlay.start_s, "start_s", scene_id)
        duration_s = _finite_number(overlay.duration_s, "duration_s", scene_id)
        if start_s < 0:
            raise PlanBuildError(f"overlay {index} of scene {scene_id!r} has a negative start_s")
        if duration_s <= 0:
            raise PlanBuildError(f"overlay {index} of scene {scene_id!r} needs a positive duration_s")
        relative_start = seconds_to_ticks(start_s, tps)
        relative_duration = seconds_to_ticks(duration_s, tps)
        if relative_duration < 1:
            raise PlanBuildError(
                f"overlay {index} of scene {scene_id!r} is below one tick at {tps} ticks/s"
            )
        if relative_start + relative_duration > scene_duration:
            raise PlanBuildError(
                f"overlay {index} of scene {scene_id!r} ends outside its scene: "
                f"{start_s!r}s + {duration_s!r}s exceeds {scene_duration / tps!r}s"
            )
        shots.append(
            Shot(
                shot_id=f"overlay:{scene_id}:{index}",
                track_id=OVERLAY_TRACK,
                start_tick=start_tick + relative_start,
                duration_ticks=relative_duration,
                asset_ref=overlay.asset_id,
                role="overlay",
                z_index=overlay.z_index,
                composition=Composition(fit=overlay.fit),
            )
        )
    return shots


def _finite_number(value: object, name: str, scene_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanBuildError(f"overlay of scene {scene_id!r} has a non-numeric {name}")
    if not math.isfinite(value):
        raise PlanBuildError(f"overlay of scene {scene_id!r} has a non-finite {name}")
    return float(value)


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