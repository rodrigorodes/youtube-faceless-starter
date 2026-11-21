"""Resolução de assets do Render Plan (RP-019..RP-022) — domínio puro, sem I/O.

A porta ``AssetResolver`` (em ``application/ports.py``) recebe um ``AssetReference``
— a entrada do **manifesto** do plano, com URI, versão, ``content_sha256`` e licença
(RP-020) — e devolve um ``AssetDescriptor``: a visão resolvida do asset, com o
metadado técnico que o compilador/executor precisa (codec, resolução, duração) e a
disponibilidade comprovada.

Correção **C1** do design: o ``content_sha256`` é do **conteúdo**, não o
``assets.cache_key`` (que é hash de *entrada*; o do vídeo inclui ``job.id`` em
``application/render.py:157``). Ele é a identidade física do asset; o resolver real o
confere contra os bytes — não se inventa hash.

RP-021 — quatro tipos de mídia, com regras distintas:

- ``image`` / ``graphic``: raster com codec e resolução; sem duração.
- ``video``: codec, resolução **e** duração.
- ``text``: animação **local** (``text_animation``), isenta de mídia externa — sem
  codec, resolução, duração nem localização.

RP-022 — o ``check_fit`` valida o que é de *política*: a resolução cobre o quadro de
saída quando a composição é ``cover`` (sem upscale) e a duração do vídeo cobre o shot.
O que é de *forma* (codec permitido, metadado obrigatório, licença) é validado na
construção do ``AssetDescriptor`` — não há como fabricar um descriptor incompleto.

Limites explícitos desta fatia (fatia 5, RP-04): sem FFmpeg/subprocess e sem render. A
sondagem de **vídeo** (ffprobe) é do executor (RP-05); aqui o metadado de vídeo vem
**declarado** no manifesto e é validado — nunca inventado. Imagem/gráfico podem ser
sondados pelo adapter (Pillow), que é quem toca disco.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .render_plan import (
    AssetMediaType,
    AssetReference,
    DurationTick,
    Hex64,
    NonBlank,
    Output,
    RenderPlan,
)

# Codecs aceitos por tipo de mídia (minúsculos). A lista é pequena de propósito: um
# codec desconhecido falha claro em vez de passar por omissão.
IMAGE_CODECS = frozenset({"png", "jpeg", "jpg", "webp", "gif", "bmp", "tiff"})
VIDEO_CODECS = frozenset({"h264", "hevc", "vp9", "av1", "mpeg4", "prores"})

Fit = Literal["cover", "contain"]
PositiveInt = Annotated[int, Field(ge=1, strict=True)]
ByteSize = Annotated[int, Field(ge=0, strict=True)]


class AssetResolutionError(ValueError):
    """Asset indisponível, inconsistente com o manifesto ou inadequado ao shot.

    Falha **clara**: nunca devolve um descriptor inventado — ou o asset existe e
    confere, ou a resolução levanta com o motivo.
    """


class AssetDescriptor(BaseModel):
    """Visão resolvida de um asset: identidade do manifesto + metadado técnico.

    ``available=False`` representa um asset declarado no manifesto cujo arquivo ainda
    não está no storage: o metadado técnico pode ficar ausente (desconhecido) e o
    ``verify_descriptor`` recusa — mas a falha é explícita, não silenciosa.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: NonBlank
    asset_version: DurationTick
    uri: NonBlank
    content_sha256: Hex64
    media_type: AssetMediaType
    license: NonBlank | None = None
    attribution: str = ""
    source_url: str = ""
    location: str = ""
    available: bool
    codec: str | None = None
    width: PositiveInt | None = None
    height: PositiveInt | None = None
    duration_ticks: PositiveInt | None = None
    byte_size: ByteSize | None = None

    @model_validator(mode="after")
    def _technical_metadata_matches_media_type(self):
        if self.media_type == "text":  # animação local: sem mídia externa (RP-021)
            if self.location:
                raise ValueError("a local text asset has no external location")
            if any(v is not None for v in (self.codec, self.width, self.height, self.duration_ticks)):
                raise ValueError("a local text asset carries no codec, resolution or duration")
            return self
        if not self.available:
            return self  # desconhecido: o verify_descriptor recusa por indisponibilidade
        if self.license is None:
            raise ValueError(f"a {self.media_type} asset requires a non-blank license")
        if self.media_type in ("image", "graphic"):
            if self.codec not in IMAGE_CODECS:
                raise ValueError(
                    f"unsupported {self.media_type} codec {self.codec!r}; expected one of {sorted(IMAGE_CODECS)}"
                )
            if self.width is None or self.height is None:
                raise ValueError(f"a {self.media_type} asset requires width and height")
            if self.duration_ticks is not None:
                raise ValueError(f"a {self.media_type} asset has no duration")
        else:  # video
            if self.codec not in VIDEO_CODECS:
                raise ValueError(f"unsupported video codec {self.codec!r}; expected one of {sorted(VIDEO_CODECS)}")
            if self.width is None or self.height is None:
                raise ValueError("a video asset requires width and height")
            if self.duration_ticks is None:
                raise ValueError("a video asset requires duration_ticks")
        return self


class AssetManifest(BaseModel):
    """Índice do manifesto do plano (RP-020): AssetReferences por ``asset_id``.

    Derivado de ``RenderPlan.asset_manifest`` (``of``): não é uma segunda verdade, só
    a leitura indexada da mesma lista, com unicidade garantida.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    references: tuple[AssetReference, ...] = ()

    @model_validator(mode="after")
    def _unique_asset_ids(self):
        ids = [r.asset_id for r in self.references]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate asset_id in the manifest")
        return self

    @classmethod
    def of(cls, plan: RenderPlan) -> "AssetManifest":
        return cls(references=tuple(plan.asset_manifest))

    @property
    def by_id(self) -> dict[str, AssetReference]:
        return {r.asset_id: r for r in self.references}

    def get(self, asset_id: str) -> AssetReference | None:
        return self.by_id.get(asset_id)

    def __contains__(self, asset_id: object) -> bool:
        return asset_id in self.by_id

    def __len__(self) -> int:
        return len(self.references)


def verify_descriptor(manifest: AssetManifest, descriptor: AssetDescriptor) -> None:
    """RP-019/RP-020: o descriptor confere com o manifesto — identidade, licença e disponibilidade.

    Garante que o resolver devolveu o asset do manifesto (versão, URI, ``content_sha256``
    e tipo) com licença registrada e arquivo disponível. Levanta ``AssetResolutionError``
    com o motivo exato; nada é inferido.
    """
    reference = manifest.get(descriptor.asset_id)
    if reference is None:
        raise AssetResolutionError(f"asset {descriptor.asset_id!r} is not declared in the plan manifest")
    for field in ("asset_version", "uri", "content_sha256", "media_type"):
        if getattr(descriptor, field) != getattr(reference, field):
            raise AssetResolutionError(
                f"resolved {field} for asset {descriptor.asset_id!r} does not match the manifest"
            )
    if descriptor.media_type != "text" and not (descriptor.license or "").strip():
        raise AssetResolutionError(f"asset {descriptor.asset_id!r} has no registered license")
    if reference.license is not None and descriptor.license != reference.license:
        raise AssetResolutionError(
            f"resolved license for asset {descriptor.asset_id!r} does not match the manifest"
        )
    if not descriptor.available:
        raise AssetResolutionError(f"asset {descriptor.asset_id!r} is not available at {descriptor.uri!r}")


def check_fit(
    descriptor: AssetDescriptor,
    output: Output,
    *,
    fit: Fit = "cover",
    shot_duration_ticks: int | None = None,
) -> None:
    """RP-022: o asset serve o quadro de saída e o shot que o usa.

    ``cover`` exige resolução suficiente para preencher a saída sem upscale; ``contain``
    aceita qualquer resolução positiva (letterbox). Um vídeo tem de durar ao menos o
    shot que o consome — não se inventam quadros que não existem no clipe.
    """
    if descriptor.media_type == "text":
        return
    if descriptor.width is None or descriptor.height is None:  # só um descriptor indisponível cai aqui
        raise AssetResolutionError(
            f"asset {descriptor.asset_id!r} has no resolution to check against {output.width}x{output.height}"
        )
    if fit == "cover" and (descriptor.width < output.width or descriptor.height < output.height):
        raise AssetResolutionError(
            f"asset {descriptor.asset_id!r} is {descriptor.width}x{descriptor.height}, smaller than the "
            f"{output.width}x{output.height} output: cover would upscale it"
        )
    if descriptor.media_type == "video" and shot_duration_ticks is not None:
        if descriptor.duration_ticks is None or descriptor.duration_ticks < shot_duration_ticks:
            raise AssetResolutionError(
                f"video asset {descriptor.asset_id!r} lasts {descriptor.duration_ticks} ticks, shorter than "
                f"the {shot_duration_ticks}-tick shot"
            )
