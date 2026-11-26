"""Estrutura neutra do Render Plan (RP-023) — validação pura, sem I/O nem fornecedor.

Este módulo é a fronteira **neutra** entre o contrato audiovisual (``RenderPlan``, no
domínio) e o compilador concreto de um renderer. Recebe os assets **já resolvidos**
(RP-04: ``AssetDescriptor`` com disponibilidade, hash e metadado técnico), valida o plano
e devolve uma estrutura de execução **sem nenhuma string de fornecedor**: caminhos de
artefato, geometria temporal em ticks, legendas, camadas e as trilhas de narração/música.

A tradução dessa estrutura no plano de execução de um renderer concreto — os ``args`` de
linha de comando, o grafo de filtros e o digest — mora no adaptador
(``adapters/render_plan_compiler.py``). É o que permite conectar outro renderer sem
reescrever a validação do núcleo (S3 do guia de isolamento do core).

Este módulo importa apenas o domínio (``RenderPlan`` e ``AssetDescriptor``) — nada de
``subprocess``, mídia (``PIL``, ``numpy``) ou SDK de provedor — e é por isso que os
contratos são testáveis sem um renderer instalado. A guarda de arquitetura prova isso por
execução (``tests/test_architecture.py::test_render_core_has_no_media_or_provider_sdks``).

Limite explícito desta fatia: RP-023 é o esqueleto determinístico. Composição de
**camadas** (shots visuais sobrepostos em tracks diferentes) e transições não triviais
são RP-024; a estrutura recusa o plano em vez de produzir um vídeo errado. O executor
(RP-05) é que materializa os overlays (Pillow), sintetiza a trilha e roda o renderer.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction

from ..domain.asset_resolver import AssetDescriptor
from ..domain.render import LEAD, TAIL
from ..domain.render_plan import (
    AssetReference,
    GeneratedAudioSource,
    Motion,
    RenderPlan,
    Shot,
    Transition,
)

# Movimentos explícitos que o plano pode pedir (``Effects.motion``). O ``Literal`` do
# contrato é a fonte de verdade; a tupla é só a documentação da política do compilador.
MOTION_NAMES = ("none", "zoom_in", "zoom_out", "pan_left", "pan_right")
# V4-04 / INT-03: suporte a múltiplas camadas simultâneas (imagem, gráfico, PiP) com limite explícito de 8
MAX_OVERLAYS_PER_SCENE = 8


class CompileError(ValueError):
    """O plano não pode ser compilado como está (asset ausente, camadas, texto sem conteúdo)."""


@dataclass(frozen=True)
class LayerExecution:
    """Overlay de imagem hospedado por um segmento base (VE-01/VE-02 / INT-03).

    ``start_ticks`` é **relativo ao início do segmento base** que hospeda a camada. A
    janela semiaberta ``[start_ticks, start_ticks+duration_ticks)`` é composta no grafo
    do segmento base (VE-02), com ``fit``, ``z_index`` e transformações geométricas
    (opacidade, escala, posição).
    """

    shot_id: str
    asset_id: str
    media_type: str
    source: str
    z_index: int
    start_ticks: int
    duration_ticks: int
    fit: str
    opacity: float = 1.0
    scale: float = 1.0
    position_x: float = 0.5
    position_y: float = 0.5


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
class CaptionPlan:
    """Legenda de um segmento: texto, PNG e janela em ticks relativos ao shot."""

    text: str
    path: str
    start_ticks: int
    end_ticks: int


@dataclass(frozen=True)
class TextCardPlan:
    """Card local de um asset de texto (RP-021): conteúdo e o PNG que o executor desenha."""

    text: str
    path: str


@dataclass(frozen=True)
class ShotPlan:
    """Um segmento neutro: o que o compilador do renderer precisa, sem string de fornecedor."""

    scene_id: str
    shot_id: str
    asset_id: str
    media_type: str
    source: str
    start_ticks: int
    duration_ticks: int
    frames: int
    motion: Motion
    transition: Transition | None
    seconds: float
    static_path: str
    label: str
    disclosure: str
    captions: tuple[CaptionPlan, ...]
    text_card: TextCardPlan | None
    overlays: tuple[LayerExecution, ...]
    output: str
    asset_offset_ticks: int = 0


@dataclass(frozen=True)
class PlanStructure:
    """Estrutura de execução neutra (dado o plano e os assets resolvidos)."""

    plan_id: str
    revision: int
    format: str
    width: int
    height: int
    fps_num: int
    fps_den: int
    ticks_per_second: int
    total_ticks: int
    rate: str
    work: str
    shots: tuple[ShotPlan, ...]
    narration: NarrationTrack
    music: MusicTrack
    schema_version: int = 2


def structure_render_plan(
    *,
    plan: RenderPlan,
    assets: Mapping[str, AssetDescriptor],
    work_dir: str,
    labels: Mapping[str, str] | None = None,
) -> PlanStructure:
    """Valida ``plan`` + assets resolvidos e devolve a estrutura neutra de execução.

    ``assets`` é um mapeamento ``asset_id -> AssetDescriptor`` (o resultado de
    ``ResolvePlanAssets``). ``labels`` é o selo editorial por cena: ele **não** faz parte
    do contrato do plano (é apresentação do storyboard), então entra explicitamente e
    nunca é inventado. Levanta ``CompileError`` — nunca devolve uma estrutura que
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

    ordered_bases = _ordered_bases(plan)
    _require_base_trajectory(ordered_bases, plan.timeline.duration_ticks)
    _validate_overlays(plan, manifest, by_id)

    subtitles = sorted(plan.timeline.subtitles, key=lambda c: c.start_tick)
    shots: list[ShotPlan] = []
    for index, (scene, shot) in enumerate(ordered_bases):
        reference = manifest.get(shot.asset_ref)
        if reference is None:
            raise CompileError(f"shot {shot.shot_id!r} references asset {shot.asset_ref!r} absent from the plan manifest")
        descriptor = by_id.get(shot.asset_ref)
        if descriptor is None:
            raise CompileError(f"asset {shot.asset_ref!r} was not resolved before compiling the plan")
        _check_descriptor(reference, descriptor)
        if not descriptor.available:
            raise CompileError(f"asset {shot.asset_ref!r} is unavailable at {descriptor.uri!r}")
        layers = _compile_layers(scene, shot, manifest, by_id)
        # Subtitles em cenas com múltiplos cortes de base (pacing) cruzam cortes
        # e são renderizadas globalmente via ASS no compilador v2; cenas com apenas
        # 1 base shot preservam os overlays por shot (incluindo cenas com overlays).
        shot_subtitles = subtitles if len(scene.base_shots) == 1 else []
        shots.append(
            _shot_plan(
                plan, scene, shot, reference, descriptor, index, work, tps,
                shot_subtitles, label_by_scene.get(scene.scene_id, ""),
                overlays=layers,
            )
        )

    narration = _compile_narration(plan, work)
    music = _compile_music(plan)
    return PlanStructure(
        plan_id=plan.plan_id,
        revision=plan.revision,
        format=output.format.value,
        width=output.width,
        height=output.height,
        fps_num=fps_num,
        fps_den=fps_den,
        ticks_per_second=tps,
        total_ticks=plan.timeline.duration_ticks,
        rate=rate,
        work=work,
        shots=tuple(shots),
        narration=narration,
        music=music,
        schema_version=plan.schema_version,
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


def _ordered_bases(plan: RenderPlan) -> list[tuple[object, Shot]]:
    pairs = [(scene, shot) for scene in plan.timeline.scenes for shot in scene.shots if shot.role == "base"]
    return sorted(pairs, key=lambda pair: (pair[1].start_tick, pair[0].scene_id, pair[1].shot_id))


def _ordered_overlays(scene) -> list[Shot]:
    return sorted(scene.overlay_shots, key=lambda overlay: (overlay.z_index, overlay.start_tick, overlay.shot_id))


def _require_base_trajectory(ordered: list[tuple[object, Shot]], total_ticks: int) -> None:
    """RP-023 compila uma única trajetória de **base**; overlays são camadas hospedadas."""
    if not ordered:
        raise CompileError("the plan has no visual base shots to compile")
    cursor = 0
    for scene, shot in ordered:
        if shot.start_tick > cursor:
            raise CompileError(
                f"gap at tick {cursor}: base shot {shot.shot_id!r} starts at {shot.start_tick}"
            )
        if shot.start_tick < cursor:
            raise CompileError(
                f"layered/overlapping visual composition at tick {shot.start_tick} "
                f"(shot {shot.shot_id!r}, track {shot.track_id!r}): layer compositing is RP-024, "
                f"the pure compiler refuses to produce a wrong video"
            )
        cursor = shot.start_tick + shot.duration_ticks
    if cursor != total_ticks:
        raise CompileError(
            f"gap at tick {cursor}: base coverage ends at tick {cursor}, but the timeline ends at tick {total_ticks}"
        )


def _validate_overlays(plan: RenderPlan, manifest: dict[str, AssetReference], by_id: dict[str, AssetDescriptor]) -> None:
    for scene in plan.timeline.scenes:
        overlays = scene.overlay_shots
        if len(overlays) > MAX_OVERLAYS_PER_SCENE:
            raise CompileError(
                f"scene {scene.scene_id!r} declares {len(overlays)} overlays; "
                f"at most {MAX_OVERLAYS_PER_SCENE} overlay per scene is supported in VE-01"
            )
        for overlay in overlays:
            reference = manifest.get(overlay.asset_ref)
            if reference is None:
                raise CompileError(
                    f"overlay {overlay.shot_id!r} references unknown asset {overlay.asset_ref!r}"
                )
            if reference.media_type not in ("image", "graphic"):
                raise CompileError(
                    f"overlay {overlay.shot_id!r} uses {reference.media_type!r} media; "
                    f"VE-01 supports image/graphic overlays only (video/text arrive in VE-02)"
                )
            descriptor = by_id.get(overlay.asset_ref)
            if descriptor is None:
                raise CompileError(
                    f"asset {overlay.asset_ref!r} was not resolved before compiling the plan"
                )
            _check_descriptor(reference, descriptor)
            if not descriptor.available:
                raise CompileError(f"asset {overlay.asset_ref!r} is unavailable at {descriptor.uri!r}")
            if scene.host_base_for(overlay) is None:
                raise CompileError(
                    f"overlay {overlay.shot_id!r} crosses a base segment boundary; "
                    f"an overlay must fit entirely inside one base shot"
                )


def _compile_layers(scene, base: Shot, manifest: dict[str, AssetReference],
                    by_id: dict[str, AssetDescriptor]) -> tuple[LayerExecution, ...]:
    layers: list[LayerExecution] = []
    for overlay in _ordered_overlays(scene):
        host = scene.host_base_for(overlay)
        if host is None or host.shot_id != base.shot_id:
            continue
        reference = manifest[overlay.asset_ref]
        descriptor = by_id[overlay.asset_ref]
        comp = overlay.composition
        fit = comp.fit if comp is not None else "cover"
        opacity = comp.opacity if comp is not None else 1.0
        scale = comp.scale if comp is not None else 1.0
        pos_x = comp.position_x if comp is not None else 0.5
        pos_y = comp.position_y if comp is not None else 0.5
        layers.append(
            LayerExecution(
                shot_id=overlay.shot_id,
                asset_id=overlay.asset_ref,
                media_type=reference.media_type,
                source=descriptor.location or descriptor.uri,
                z_index=overlay.z_index,
                start_ticks=overlay.start_tick - base.start_tick,
                duration_ticks=overlay.duration_ticks,
                fit=fit,
                opacity=opacity,
                scale=scale,
                position_x=pos_x,
                position_y=pos_y,
            )
        )
    return tuple(layers)


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


def _shot_plan(
    plan: RenderPlan,
    scene,
    shot: Shot,
    reference: AssetReference,
    descriptor: AssetDescriptor,
    index: int,
    work: str,
    tps: int,
    subtitles: list,
    label: str,
    *,
    overlays: tuple[LayerExecution, ...] = (),
) -> ShotPlan:
    frames = _frames(shot.duration_ticks, plan.timeline.timebase.fps_num, plan.timeline.timebase.fps_den, tps)
    seconds = shot.duration_ticks / tps
    source = descriptor.location or descriptor.uri
    text_card: TextCardPlan | None = None

    if descriptor.media_type == "text":
        text = (reference.metadata.get("text") or "").strip()
        if not text:
            raise CompileError(
                f"text asset {reference.asset_id!r} has no 'text' metadata; the executor cannot render an empty card"
            )
        text_card = TextCardPlan(text=text, path=f"{work}/text_{index:03d}.png")
        source = text_card.path
    elif descriptor.media_type not in ("image", "graphic", "video"):
        # pragma: no cover - AssetMediaType é Literal fechado
        raise CompileError(f"unsupported media type {descriptor.media_type!r}")

    if descriptor.media_type == "video" and descriptor.duration_ticks is not None:
        if shot.asset_offset_ticks + shot.duration_ticks > descriptor.duration_ticks:
            raise CompileError(
                f"shot {shot.shot_id!r} requires {shot.asset_offset_ticks + shot.duration_ticks} ticks "
                f"(offset {shot.asset_offset_ticks} + duration {shot.duration_ticks}), "
                f"exceeding video asset duration {descriptor.duration_ticks} ticks"
            )

    return ShotPlan(
        scene_id=scene.scene_id,
        shot_id=shot.shot_id,
        asset_id=reference.asset_id,
        media_type=descriptor.media_type,
        source=source,
        start_ticks=shot.start_tick,
        duration_ticks=shot.duration_ticks,
        frames=frames,
        motion=shot.effects.motion,
        transition=shot.transition,
        seconds=seconds,
        static_path=f"{work}/static_{index:03d}.png",
        label=label,
        disclosure=plan.output.disclosure,
        captions=_caption_plans(shot, subtitles, index, work),
        text_card=text_card,
        overlays=overlays,
        output=f"{work}/scene_{index:03d}.mp4",
        asset_offset_ticks=shot.asset_offset_ticks,
    )


def _caption_plans(shot: Shot, subtitles: list, index: int, work: str) -> tuple[CaptionPlan, ...]:
    captions: list[CaptionPlan] = []
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
        captions.append(
            CaptionPlan(
                text=cue.text,
                path=f"{work}/cue_{index:03d}_{len(captions):02d}.png",
                start_ticks=start_ticks,
                end_ticks=end_ticks,
            )
        )
    return tuple(captions)


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
