"""Contrato canônico do Render Plan (RP-006) — domínio puro, sem I/O.

O ``RenderPlan`` é o documento audiovisual versionado que o renderer executa sem
conhecer o roteiro editorial, o fornecedor de um asset nem as regras do canal.
Substitui, como *contrato*, o ``RenderSpec`` de listas paralelas (que continua sendo
a entrada do renderer legado — R2).

Decisões refletidas aqui (design, §5 e §11/C1..C4):

- **Timebase racional + ticks inteiros** (RP-010): ``Timeline.timebase`` carrega
  ``fps_num``/``fps_den`` e ``ticks_per_second`` explícito. Toda fronteira de quadro
  tem de cair num tick inteiro, ou a timebase é rejeitada — é o que torna a
  duração reproduzível. Segundos float continuam sendo a unidade de autoria
  (``VisualBeat``); a ponte exata é ``domain.ticks``.
- **``content_sha256`` próprio em ``AssetReference``** (C1): ``assets.cache_key`` é
  hash de *entrada* e o do vídeo inclui ``job.id``; o único precedente de hash de
  conteúdo no domínio é ``SourceSnapshot.content_sha256``.
- **Efeitos, disclosure e trilha no plano** (R3/C2): modo de movimento explícito por
  shot (sem ``index % 4``), ``disclosure`` no output e a música como **fonte de áudio
  gerada** (``GeneratedAudioSource``), distinta de ``AssetReference``. ``music=False``
  grava trilha silenciosa de mesmo comprimento — o contrato representa os dois modos.
- **``style_snapshot`` referencia o canal por chave + versão** (R4), não carrega objeto.
- **Custo por cena/shot por chave** (R5): ``paid_operation_key``; a tabela lateral de
  custo é de outra fatia.

Timeline e sincronização (RP-011..RP-014):

- **Cenas, shots e tracks** (RP-011): todo conteúdo temporal vive numa ``Track``
  (``visual``/``narration``/``subtitle``); shots exigem faixa visual declarada.
- **Sobreposição, contiguidade e lacunas por track** (RP-012): shots da mesma faixa
  não se sobrepõem; as cenas tilegam a timeline sem lacuna/sobreposição; e cada cena
  é coberta ponta a ponta pelo **conjunto** de shots visuais (camadas podem se
  sobrepor, buracos não).
- **Narração e legendas na timeline** (RP-013): ``NarrationCue``/``SubtitleCue``
  ancoram mídia a uma cena e a um intervalo em ticks, sobre a faixa certa.
- **Duração, lacunas e alinhamento** (RP-014): a duração respeita os limites do
  formato de saída; a narração pode exceder a cena em até um quadro (a fala é
  arredondada a quadros) e a legenda é sincronizada com a narração da cena dentro da
  tolerância por tipo de mídia (``SUBTITLE_ALIGNMENT_S``).

Limites explícitos desta fatia:

- O contrato **não** verifica veracidade de proveniência, validade real de licença,
  disponibilidade do asset nem codec (RP-020/RP-022, fatias posteriores).
- A **calibração** da legenda por TTS não é feita aqui: o contrato *representa* e
  valida o alinhamento; produzir cue a cue é do builder (RP-015/RP-025).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .contracts import VideoFormat, _Model
from .render import FPS, MAX_SECONDS, MIN_SECONDS, SIZE
from .ticks import seconds_to_ticks

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Hex64 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Tick = Annotated[int, Field(ge=0, strict=True)]
DurationTick = Annotated[int, Field(ge=1, strict=True)]

AudioKind = Literal["voice", "music"]
AssetMediaType = Literal["image", "video", "graphic", "text"]
Motion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"]
TrackKind = Literal["visual", "narration", "subtitle"]

# Tolerância de sincronização de legenda com a narração da cena (RP-014), em segundos.
# A narração não usa esta constante: seu limite é um quadro (``ticks_per_frame``).
SUBTITLE_ALIGNMENT_S = 0.5


class _PlanModel(BaseModel):
    """Base dos modelos internos do plano: imutável e fechado, sem ``schema_version``.

    Só a raiz (``RenderPlan``) carrega ``schema_version`` — o documento é que é
    versionado, como as entidades de ``contracts``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class Timebase(_PlanModel):
    """Timebase racional do plano: fps como fração e resolução inteira em ticks.

    ``fps_num``/``fps_den`` representam exatamente taxas como ``30000/1001``.
    ``ticks_per_second`` é explícito. A grade de ticks tem de conter toda fronteira
    de quadro: reduzido, ``fps_num`` precisa dividir ``ticks_per_second``, senão um
    quadro cai entre dois ticks e a duração deixa de ser reproduzível.
    """

    ticks_per_second: DurationTick
    fps_num: DurationTick = FPS
    fps_den: DurationTick = 1

    @property
    def fps(self) -> float:
        """Taxa de quadros em ponto flutuante, só para exibição/comparação."""
        return self.fps_num / self.fps_den

    @property
    def ticks_per_frame(self) -> int:
        """Ticks exatos de um quadro (inteiro: garantido pela validação)."""
        factor = math.gcd(self.fps_num, self.fps_den)
        return (self.ticks_per_second // (self.fps_num // factor)) * (self.fps_den // factor)

    @model_validator(mode="after")
    def _frames_land_on_integer_ticks(self):
        factor = math.gcd(self.fps_num, self.fps_den)
        frame_units = self.fps_num // factor
        if self.ticks_per_second % frame_units != 0:
            raise ValueError(
                f"ticks_per_second {self.ticks_per_second} cannot represent frame rate "
                f"{self.fps_num}/{self.fps_den}: a frame boundary must be a whole tick "
                f"(fps_num/{factor} = {frame_units} must divide ticks_per_second)"
            )
        return self


class Track(_PlanModel):
    """Faixa da timeline; shots exigem faixa ``visual``, cues exigem a faixa do seu tipo."""

    track_id: NonBlank
    kind: TrackKind


class AssetReference(_PlanModel):
    """Referência a conteúdo previamente gerado ou obtido (imagem, vídeo, gráfico, texto)."""

    asset_id: NonBlank
    asset_version: DurationTick
    uri: NonBlank
    content_sha256: Hex64
    media_type: AssetMediaType
    license: NonBlank | None = None
    attribution: str = ""
    source_url: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class GeneratedAudioSource(_PlanModel):
    """Fonte de áudio **gerada** pelo render (voz sintetizada ou trilha musical).

    Distinta de ``AssetReference`` (C2): não é ``Asset`` persistido nem tem
    ``content_sha256``. A trilha musical é determinística pelos ``params`` (bpm,
    seed). ``silent=True`` representa o modo ``music=False`` do renderer, que grava
    uma trilha silenciosa de mesmo comprimento para manter o grafo de mixagem.
    """

    source_id: NonBlank
    kind: AudioKind
    duration_ticks: DurationTick
    silent: bool = False
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _silent_mode(self):
        if self.silent and self.kind != "music":
            raise ValueError("only music may be silent")
        if self.silent and self.params:
            raise ValueError("a silent track carries no synthesis params")
        return self


class Composition(_PlanModel):
    """Como o conteúdo do shot preenche o quadro e suas transformações geométricas."""

    fit: Literal["cover", "contain"] = "cover"
    opacity: float = 1.0
    scale: float = 1.0
    position_x: float = 0.5
    position_y: float = 0.5

    @model_validator(mode="after")
    def _validate_finite_bounds(self):
        for name, val in (
            ("opacity", self.opacity),
            ("scale", self.scale),
            ("position_x", self.position_x),
            ("position_y", self.position_y),
        ):
            if not math.isfinite(val):
                raise ValueError(f"composition {name} must be finite, got {val!r}")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError(f"composition opacity must be in [0.0, 1.0], got {self.opacity!r}")
        if not (0.0 < self.scale <= 4.0):
            raise ValueError(f"composition scale must be in (0.0, 4.0], got {self.scale!r}")
        if not (0.0 <= self.position_x <= 1.0):
            raise ValueError(f"composition position_x must be in [0.0, 1.0], got {self.position_x!r}")
        if not (0.0 <= self.position_y <= 1.0):
            raise ValueError(f"composition position_y must be in [0.0, 1.0], got {self.position_y!r}")
        return self


class Effects(_PlanModel):
    """Movimento explícito por shot (substitui o ``index % 4`` do renderer legado)."""

    motion: Motion = "none"


class AudioMix(_PlanModel):
    """Parâmetros declarativos da mixagem de áudio do plano."""

    music_gain: float = 0.40
    ducking_threshold: float = 0.02
    ducking_ratio: float = 10.0
    afade_in_s: float = 0.25
    afade_out_s: float = 0.25
    loudnorm_i: float = -16.0
    loudnorm_tp: float = -1.5
    loudnorm_lra: float = 11.0


class Transition(_PlanModel):
    """Transição para o próximo shot."""

    kind: Literal[
        "none", "fade", "crossfade", "cut",
        "slide_left", "slide_right", "wipe_left", "wipe_right"
    ] = "none"
    duration_ticks: Tick = 0

    @model_validator(mode="after")
    def _duration_matches_kind(self):
        if self.kind in ("none", "cut") and self.duration_ticks != 0:
            raise ValueError(f"a {self.kind!r} transition has no duration")
        if self.kind not in ("none", "cut") and self.duration_ticks < 1:
            raise ValueError(f"a {self.kind!r} transition needs a positive duration")
        return self


class Shot(_PlanModel):
    """Elemento visual em uma faixa temporal, dentro de uma cena.

    ``role`` distingue a base (que cobre a cena) do overlay de imagem (VE-01): o overlay
    vive dentro de um segmento base e não fecha lacuna. ``z_index`` ordena camadas; a base
    fica em 0 e o overlay em 1+.
    """

    shot_id: NonBlank
    track_id: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick
    asset_ref: NonBlank
    asset_offset_ticks: Tick = 0
    asset_trim_start_s: float | None = None
    asset_trim_end_s: float | None = None
    role: Literal["base", "overlay"] = "base"
    z_index: Annotated[int, Field(ge=0, strict=True)] = 0
    composition: Composition | None = None
    effects: Effects = Field(default_factory=Effects)
    transition: Transition | None = None
    paid_operation_key: NonBlank | None = None

    @model_validator(mode="after")
    def _role_and_z_index(self):
        if self.role == "base" and self.z_index != 0:
            raise ValueError("a base shot must keep z_index 0")
        if self.role == "overlay" and self.z_index < 1:
            raise ValueError("an overlay shot needs a positive z_index")
        if self.role == "overlay" and self.transition is not None:
            raise ValueError(
                "an overlay shot carries no transition; the transition belongs to the base segment"
            )
        return self


class Scene(_PlanModel):
    """Unidade narrativa: agrupa shots visuais."""

    scene_id: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick
    shots: list[Shot] = Field(min_length=1)
    paid_operation_key: NonBlank | None = None

    @property
    def base_shots(self) -> list[Shot]:
        """Shots que compõem a trajetória visual contínua da cena."""
        return [shot for shot in self.shots if shot.role == "base"]

    @property
    def overlay_shots(self) -> list[Shot]:
        """Camadas de imagem hospedadas dentro de um segmento base."""
        return [shot for shot in self.shots if shot.role == "overlay"]

    def host_base_for(self, overlay: Shot) -> Shot | None:
        """Base que contém o overlay inteiro (evita dividir a camada entre segmentos)."""
        end = overlay.start_tick + overlay.duration_ticks
        for base in self.base_shots:
            if base.start_tick <= overlay.start_tick and end <= base.start_tick + base.duration_ticks:
                return base
        return None

    @model_validator(mode="after")
    def _shots_fit_inside_scene(self):
        end = self.start_tick + self.duration_ticks
        seen: set[str] = set()
        for item in self.shots:
            if item.shot_id in seen:
                raise ValueError(f"duplicate shot_id {item.shot_id!r} in scene {self.scene_id!r}")
            seen.add(item.shot_id)
            if item.start_tick < self.start_tick:
                raise ValueError(f"shot {item.shot_id!r} starts before its scene")
            if item.start_tick + item.duration_ticks > end:
                raise ValueError(f"shot {item.shot_id!r} ends after its scene")
        return self


class NarrationCue(_PlanModel):
    """Narração associada a uma cena e a um intervalo da timeline (RP-013)."""

    scene_id: NonBlank
    track_id: NonBlank
    source_ref: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick


class SubtitleCue(_PlanModel):
    """Legenda associada a uma cena e a um intervalo da timeline (RP-013)."""

    scene_id: NonBlank
    track_id: NonBlank
    text: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick


def alignment_tolerance_ticks(kind: TrackKind, timebase: Timebase) -> int:
    """Tolerância de sincronização em ticks por tipo de faixa (RP-014).

    Visual é exato (0). A narração admite um quadro — a duração da fala é
    arredondada para quadros em ``scene_length``. A legenda admite
    ``SUBTITLE_ALIGNMENT_S`` segundos.
    """
    if kind == "visual":
        return 0
    if kind == "narration":
        return timebase.ticks_per_frame
    return seconds_to_ticks(SUBTITLE_ALIGNMENT_S, timebase.ticks_per_second)


class Timeline(_PlanModel):
    """Timebase, tracks, cenas e as cues de narração/legenda da timeline."""

    timebase: Timebase
    tracks: list[Track] = Field(min_length=1)
    scenes: list[Scene] = Field(min_length=1)
    narration: list[NarrationCue] = Field(default_factory=list)
    subtitles: list[SubtitleCue] = Field(default_factory=list)

    @property
    def ticks_per_second(self) -> int:
        return self.timebase.ticks_per_second

    @property
    def duration_ticks(self) -> int:
        """Fim do último intervalo da timeline (derivado; não é campo persistido)."""
        return max((s.start_tick + s.duration_ticks for s in self.scenes), default=0)

    @model_validator(mode="after")
    def _ids_are_unique(self):
        seen_scene: set[str] = set()
        for item in self.scenes:
            if item.scene_id in seen_scene:
                raise ValueError(f"duplicate scene_id {item.scene_id!r}")
            seen_scene.add(item.scene_id)
        seen_track: set[str] = set()
        for item in self.tracks:
            if item.track_id in seen_track:
                raise ValueError(f"duplicate track_id {item.track_id!r}")
            seen_track.add(item.track_id)
        return self

    @model_validator(mode="after")
    def _scenes_tile_the_timeline(self):
        cursor = 0
        for item in sorted(self.scenes, key=lambda s: s.start_tick):
            if item.start_tick != cursor:
                raise ValueError(
                    f"scene {item.scene_id!r} starts at tick {item.start_tick} but the "
                    f"timeline is covered until tick {cursor}: gaps and overlaps are not "
                    f"allowed (scenes must be contiguous from 0)"
                )
            cursor = item.start_tick + item.duration_ticks
        return self

    @model_validator(mode="after")
    def _shots_live_on_declared_visual_tracks(self):
        by_id = {t.track_id: t for t in self.tracks}
        grouped: dict[str, list[Shot]] = {}
        for item in self.scenes:
            for shot in item.shots:
                track = by_id.get(shot.track_id)
                if track is None:
                    raise ValueError(f"shot {shot.shot_id!r} references undeclared track {shot.track_id!r}")
                if track.kind != "visual":
                    raise ValueError(
                        f"shot {shot.shot_id!r} lives on a {track.kind!r} track "
                        f"{track.track_id!r}; shots require a visual track"
                    )
                grouped.setdefault(shot.track_id, []).append(shot)
        for track_id, shots in grouped.items():
            previous: Shot | None = None
            for shot in sorted(shots, key=lambda s: s.start_tick):
                if previous is not None:
                    end = previous.start_tick + previous.duration_ticks
                    if shot.start_tick < end:
                        raise ValueError(
                            f"overlap on track {track_id!r}: shot {shot.shot_id!r} starts at "
                            f"tick {shot.start_tick} but shot {previous.shot_id!r} ends at tick {end}"
                        )
                previous = shot
        return self

    @model_validator(mode="after")
    def _every_scene_is_fully_covered(self):
        for item in self.scenes:
            end = item.start_tick + item.duration_ticks
            cursor = item.start_tick
            # VE-01: só a base fecha a cobertura; o overlay nunca tapa lacuna.
            for start, stop in sorted(
                (s.start_tick, s.start_tick + s.duration_ticks)
                for s in item.shots
                if s.role == "base"
            ):
                if start > cursor:
                    raise ValueError(
                        f"gap in visual coverage of scene {item.scene_id!r}: no shot covers tick {cursor}"
                    )
                cursor = max(cursor, stop)
            if cursor < end:
                raise ValueError(
                    f"scene {item.scene_id!r} is not fully covered: coverage ends at tick "
                    f"{cursor}, scene ends at tick {end}"
                )
        return self

    @model_validator(mode="after")
    def _overlays_need_distinct_z_index_when_they_overlap(self):
        for scene in self.scenes:
            overlays = sorted(scene.overlay_shots, key=lambda s: (s.start_tick, s.shot_id))
            for index, first in enumerate(overlays):
                first_end = first.start_tick + first.duration_ticks
                for second in overlays[index + 1:]:
                    if second.start_tick >= first_end:
                        break
                    if first.z_index == second.z_index:
                        raise ValueError(
                            f"overlays {first.shot_id!r} and {second.shot_id!r} of scene "
                            f"{scene.scene_id!r} overlap in time and share z_index {first.z_index}"
                        )
        return self

    @model_validator(mode="after")
    def _narration_and_subtitles_are_timed(self):
        by_id = {t.track_id: t for t in self.tracks}
        scenes = {s.scene_id: s for s in self.scenes}
        for cue in self.narration:
            self._check_cue(cue, "narration", by_id, scenes)
        for cue in self.subtitles:
            self._check_cue(cue, "subtitle", by_id, scenes)
        self._check_no_overlap(self.narration, "narration")
        self._check_no_overlap(self.subtitles, "subtitle")
        self._check_subtitles_follow_narration()
        return self

    def _check_cue(self, cue, kind: TrackKind, tracks: dict[str, Track], scenes: dict[str, Scene]) -> None:
        track = tracks.get(cue.track_id)
        if track is None:
            raise ValueError(f"{kind} cue references undeclared track {cue.track_id!r}")
        if track.kind != kind:
            raise ValueError(
                f"{kind} cue lives on a {track.kind!r} track {track.track_id!r}; "
                f"it requires a {kind} track"
            )
        scene = scenes.get(cue.scene_id)
        if scene is None:
            raise ValueError(f"{kind} cue references unknown scene {cue.scene_id!r}")
        tolerance = alignment_tolerance_ticks(kind, self.timebase)
        scene_end = scene.start_tick + scene.duration_ticks
        cue_end = cue.start_tick + cue.duration_ticks
        if cue.start_tick < scene.start_tick - tolerance or cue_end > scene_end + tolerance:
            raise ValueError(
                f"{kind} cue of scene {cue.scene_id!r} is outside the scene beyond the "
                f"alignment tolerance ({tolerance} ticks)"
            )

    def _check_no_overlap(self, cues, kind: str) -> None:
        grouped: dict[str, list] = {}
        for cue in cues:
            grouped.setdefault(cue.track_id, []).append(cue)
        for track_id, items in grouped.items():
            previous = None
            for cue in sorted(items, key=lambda c: c.start_tick):
                if previous is not None:
                    end = previous.start_tick + previous.duration_ticks
                    if cue.start_tick < end:
                        raise ValueError(
                            f"overlap on {kind} track {track_id!r}: a cue starts at tick "
                            f"{cue.start_tick} but the previous ends at tick {end}"
                        )
                previous = cue

    def _check_subtitles_follow_narration(self) -> None:
        by_scene: dict[str, list[NarrationCue]] = {}
        for cue in self.narration:
            by_scene.setdefault(cue.scene_id, []).append(cue)
        tolerance = alignment_tolerance_ticks("subtitle", self.timebase)
        for cue in self.subtitles:
            narration = by_scene.get(cue.scene_id)
            if not narration:
                continue
            start = min(c.start_tick for c in narration)
            end = max(c.start_tick + c.duration_ticks for c in narration)
            cue_end = cue.start_tick + cue.duration_ticks
            if cue.start_tick < start - tolerance or cue_end > end + tolerance:
                raise ValueError(
                    f"subtitle cue of scene {cue.scene_id!r} is out of sync with the "
                    f"narration beyond the alignment tolerance ({tolerance} ticks)"
                )


class Output(_PlanModel):
    """Formato de saída e texto de disclosure (R3). A taxa de quadros é da ``Timebase``."""

    format: VideoFormat
    width: DurationTick
    height: DurationTick
    disclosure: NonBlank = "Ilustração gerada por IA"


class StyleSnapshot(_PlanModel):
    """Referência por chave + versão ao perfil de canal (R4); não carrega o objeto."""

    source: Literal["channel"] = "channel"
    style_id: NonBlank
    version: DurationTick


class Provenance(_PlanModel):
    """Proveniência do documento (quem construiu o plano)."""

    builder_version: NonBlank
    created_at: datetime | None = None


class ConfigSnapshot(_PlanModel):
    """Referência da **configuração efetiva congelada** que governou voz e render (F03.T03).

    O plano grava a identidade (`content_hash` + `schema_version`) e a proveniência criativa
    relevante ao render (``style`` e ``audiovisual.*``). O documento completo da configuração
    continua sendo o snapshot do run (F03.T02); aqui só entra a prova de qual revisão foi usada,
    para auditar um plano sem copiar nem credencial nem política operacional.

    Campo **aditivo**: planos persistidos antes desta fatia não o têm e continuam válidos
    (``None``). Ele não participa dos fingerprints do cache (``domain.render_cache``), então
    também não invalida artefatos já registrados.
    """

    content_hash: Hex64
    schema_version: DurationTick
    provenance: dict[str, str] = Field(default_factory=dict)


class RenderPlan(_Model):
    """Raiz do documento audiovisual canônico, versionado por ``schema_version``."""

    model_config = ConfigDict(frozen=True)

    plan_id: NonBlank
    revision: DurationTick
    project_id: NonBlank
    video_id: NonBlank
    output: Output
    timeline: Timeline
    asset_manifest: list[AssetReference] = Field(default_factory=list)
    generated_audio: list[GeneratedAudioSource] = Field(default_factory=list)
    style_snapshot: StyleSnapshot
    provenance: Provenance
    # F03.T03: identidade da configuração efetiva lida no início do render. Opcional para que
    # documentos versionados antes da fatia continuem legíveis (o campo tem default).
    config_snapshot: ConfigSnapshot | None = None
    audio_mix: AudioMix = Field(default_factory=AudioMix)
    schema_version: int = 2

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value not in (1, 2):
            raise ValueError(f"unsupported schema_version {value!r}; expected 1 or 2")
        return value

    @model_validator(mode="after")
    def _references_and_output(self):
        asset_ids = [a.asset_id for a in self.asset_manifest]
        audio_ids = [g.source_id for g in self.generated_audio]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("duplicate asset_id in asset_manifest")
        if len(set(audio_ids)) != len(audio_ids):
            raise ValueError("duplicate source_id in generated_audio")
        overlap = set(asset_ids) & set(audio_ids)
        if overlap:
            raise ValueError(f"ids shared between assets and generated audio: {sorted(overlap)!r}")
        for item in self.timeline.scenes:
            for s in item.shots:
                if s.asset_ref not in asset_ids:
                    raise ValueError(f"shot {s.shot_id!r} references unknown asset {s.asset_ref!r}")
        known = set(asset_ids) | set(audio_ids)
        for cue in self.timeline.narration:
            if cue.source_ref not in known:
                raise ValueError(f"narration cue references unknown media {cue.source_ref!r}")
        if (self.output.width, self.output.height) != SIZE[self.output.format]:
            raise ValueError(
                f"output {self.output.width}x{self.output.height} is not "
                f"{SIZE[self.output.format][0]}x{SIZE[self.output.format][1]} for {self.output.format.value}"
            )
        tps = self.timeline.ticks_per_second
        duration = self.timeline.duration_ticks
        limit = MAX_SECONDS[self.output.format] * tps
        if duration > limit:
            raise ValueError(
                f"plan lasts {duration} ticks, above the {limit} ticks "
                f"({MAX_SECONDS[self.output.format]}s) limit for {self.output.format.value}"
            )
        minimum = seconds_to_ticks(MIN_SECONDS, tps)
        if duration < minimum:
            raise ValueError(
                f"plan lasts {duration} ticks, below the {MIN_SECONDS}s minimum "
                f"({minimum} ticks)"
            )
        return self


def upconvert_v1_to_v2(data: dict) -> dict:
    """Converte dicionário de plano v1 para v2.

    Adiciona audio_mix default se ausente e define schema_version = 2.
    """
    version = data.get("schema_version", 1)
    if version not in (1, 2):
        raise ValueError(f"unsupported schema_version {version!r} for upconversion; expected 1 or 2")
    converted = dict(data)
    converted["schema_version"] = 2
    if "audio_mix" not in converted or converted["audio_mix"] is None:
        converted["audio_mix"] = AudioMix().model_dump(mode="json")
    return converted

