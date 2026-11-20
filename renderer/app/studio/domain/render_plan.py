"""Contrato canônico do Render Plan (RP-006) — domínio puro, sem I/O.

O ``RenderPlan`` é o documento audiovisual versionado que o renderer executa sem
conhecer o roteiro editorial, o fornecedor de um asset nem as regras do canal.
Substitui, como *contrato*, o ``RenderSpec`` de listas paralelas (que continua sendo
a entrada do renderer legado — R2).

Decisões refletidas aqui (design, §5 e §11/C1..C4):

- **Ticks inteiros + ``ticks_per_second`` explícito** (R1/RP-010). Segundos float
  continuam sendo a unidade de autoria (``VisualBeat``); a conversão é do builder.
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

Limites explícitos desta fatia (não é timeline/execução):

- A régua de sobreposição/lacunas por *track* (RP-012) **não** é aplicada aqui; mas
  cada shot tem de caber na sua cena.
- ``Scene``/``Shot`` validam somente o que é do contrato: ids únicos, referências
  existentes, ticks não negativos e duração dentro do formato de saída.
- O contrato **não** verifica veracidade de proveniência, validade real de licença,
  disponibilidade do asset nem codec (RP-020/RP-022, fatias posteriores).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .contracts import VideoFormat, _Model
from .render import FPS, MAX_SECONDS, SIZE

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Hex64 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Tick = Annotated[int, Field(ge=0, strict=True)]
DurationTick = Annotated[int, Field(ge=1, strict=True)]

AudioKind = Literal["voice", "music"]
AssetMediaType = Literal["image", "video", "graphic", "text"]
Motion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"]


class _PlanModel(BaseModel):
    """Base dos modelos internos do plano: imutável e fechado, sem ``schema_version``.

    Só a raiz (``RenderPlan``) carrega ``schema_version`` — o documento é que é
    versionado, como as entidades de ``contracts``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


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
    """Como o conteúdo do shot preenche o quadro."""

    fit: Literal["cover", "contain"] = "cover"


class Effects(_PlanModel):
    """Movimento explícito por shot (substitui o ``index % 4`` do renderer legado)."""

    motion: Motion = "none"


class Transition(_PlanModel):
    """Transição para o próximo shot; só o fade existe no renderer atual."""

    kind: Literal["none", "fade"] = "none"
    duration_ticks: Tick = 0

    @model_validator(mode="after")
    def _duration_matches_kind(self):
        if self.kind == "none" and self.duration_ticks != 0:
            raise ValueError("a 'none' transition has no duration")
        if self.kind == "fade" and self.duration_ticks < 1:
            raise ValueError("a 'fade' transition needs a positive duration")
        return self


class Shot(_PlanModel):
    """Elemento visual em uma faixa temporal, dentro de uma cena."""

    shot_id: NonBlank
    track_id: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick
    asset_ref: NonBlank
    composition: Composition | None = None
    effects: Effects = Field(default_factory=Effects)
    transition: Transition | None = None
    paid_operation_key: NonBlank | None = None


class Scene(_PlanModel):
    """Unidade narrativa: agrupa shots e referencia narração/legenda."""

    scene_id: NonBlank
    start_tick: Tick
    duration_ticks: DurationTick
    shots: list[Shot] = Field(min_length=1)
    narration_refs: list[NonBlank] = Field(default_factory=list)
    subtitle_refs: list[NonBlank] = Field(default_factory=list)
    paid_operation_key: NonBlank | None = None

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


class Timeline(_PlanModel):
    """Timebase inteira do plano e as cenas."""

    ticks_per_second: DurationTick
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def _scene_ids_are_unique(self):
        seen: set[str] = set()
        for item in self.scenes:
            if item.scene_id in seen:
                raise ValueError(f"duplicate scene_id {item.scene_id!r}")
            seen.add(item.scene_id)
        return self

    @property
    def duration_ticks(self) -> int:
        """Fim do último intervalo da timeline (derivado; não é campo persistido)."""
        return max((s.start_tick + s.duration_ticks for s in self.scenes), default=0)


class Output(_PlanModel):
    """Formato de saída e texto de disclosure (R3)."""

    format: VideoFormat
    width: DurationTick
    height: DurationTick
    fps: DurationTick = FPS
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
        known = set(asset_ids) | set(audio_ids)
        for item in self.timeline.scenes:
            for s in item.shots:
                if s.asset_ref not in asset_ids:
                    raise ValueError(f"shot {s.shot_id!r} references unknown asset {s.asset_ref!r}")
            for ref in (*item.narration_refs, *item.subtitle_refs):
                if ref not in known:
                    raise ValueError(f"scene {item.scene_id!r} references unknown media {ref!r}")
        if (self.output.width, self.output.height) != SIZE[self.output.format]:
            raise ValueError(
                f"output {self.output.width}x{self.output.height} is not "
                f"{SIZE[self.output.format][0]}x{SIZE[self.output.format][1]} for {self.output.format.value}"
            )
        limit = MAX_SECONDS[self.output.format] * self.timeline.ticks_per_second
        if self.timeline.duration_ticks > limit:
            raise ValueError(
                f"plan lasts {self.timeline.duration_ticks} ticks, above the {limit} ticks "
                f"({MAX_SECONDS[self.output.format]}s) limit for {self.output.format.value}"
            )
        return self
