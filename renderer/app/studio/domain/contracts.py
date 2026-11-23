"""Entidades e contratos do Faceless Studio (camada de domínio: sem I/O)."""
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, TypeVar

from pydantic import Field, StringConstraints, model_validator

# A base versionada mora em ``schema`` para não criar ciclo com ``qa_report`` (o
# ``Video`` referencia o QA versionado da F6). Reexportada aqui para os demais contratos.
from .schema import SCHEMA_VERSION, _Model  # noqa: F401  (reexportado)
from .qa_report import QaReport

Cost = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Tokens = Annotated[int | None, Field(ge=0)]
Privacy = Literal["private", "unlisted", "public"]
License = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]  # licença em branco não é licença


class VideoStatus(str, Enum):
    IDEA = "IDEA"
    SCRIPTED = "SCRIPTED"
    FACT_CHECKED = "FACT_CHECKED"
    STORYBOARDED = "STORYBOARDED"
    ASSETS_READY = "ASSETS_READY"
    RENDERED = "RENDERED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class VideoFormat(str, Enum):
    short = "short"
    long = "long"


class ProductionMode(str, Enum):
    piloto = "piloto"
    diretor = "diretor"


class AssetKind(str, Enum):
    image = "image"
    voice = "voice"
    music = "music"
    clip = "clip"
    video = "video"
    thumbnail = "thumbnail"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PublicationStatus(str, Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


class Project(_Model):
    id: str
    name: str = Field(min_length=1, max_length=120)
    niche: str = ""
    language: str = "pt-BR"
    budget_usd_month: Cost = 15.0
    config: dict[str, str] = Field(default_factory=dict)  # "<provedor>:<modelo>" por porta
    created_at: datetime | None = None


class Video(_Model):
    id: str
    project_id: str
    topic: str = Field(min_length=3, max_length=300)
    format: VideoFormat
    status: VideoStatus = VideoStatus.IDEA
    production_mode: ProductionMode = ProductionMode.piloto
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: Privacy = "private"
    # VS-02b: estilo que **sobrepõe** o do canal neste vídeo. Nulo (o normal) = herda o do canal.
    style_id: str | None = None
    qa_report: QaReport | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Script(_Model):
    id: str
    video_id: str
    version: int = Field(ge=1)
    text: str
    claim_ids: list[str] = Field(default_factory=list)


class Scene(_Model):
    id: str
    video_id: str
    idx: int = Field(ge=0)
    narration: str = Field(min_length=5, max_length=400)
    caption: str = Field(default="", max_length=110)
    label: str = Field(default="", max_length=32)
    image_prompt: str = Field(min_length=10, max_length=500)
    claim_ids: list[str] = Field(default_factory=list)
    asset_id: str | None = None
    duration_s: float | None = Field(default=None, ge=0)


class Asset(_Model):
    id: str
    kind: AssetKind
    cache_key: str
    path: str
    provider: str
    model: str
    license: License
    attribution: str = ""
    source_url: str = ""
    cost_usd: Cost = 0.0


class RenderJob(_Model):
    id: str
    video_id: str
    status: JobStatus = JobStatus.QUEUED
    attempt: int = Field(default=1, ge=1)
    input_hash: str = ""
    output_asset_id: str | None = None
    error: str | None = None


class Publication(_Model):
    id: str
    video_id: str
    youtube_video_id: str | None = None
    upload_uri: str | None = None
    status: PublicationStatus = PublicationStatus.PENDING
    publish_at: datetime | None = None
    privacy: Privacy = "private"
    thumbnail_set: bool = False
    attempt: int = 0                 # quantas vezes foi reivindicada (teto 5)
    error: str | None = None


class Approval(_Model):
    video_id: str
    decision: Literal["approved", "rejected"]
    reason: str = ""
    qa_override: bool = False        # aprovado mesmo com o QA reprovado (exige motivo)
    publish_at: datetime | None = None
    created_at: datetime | None = None
    output_asset_id: str | None = None


class UsageEntry(_Model):
    step: str
    provider: str
    model: str
    video_id: str | None = None
    input_tokens: Tokens = None
    output_tokens: Tokens = None
    cache_read_tokens: Tokens = None
    cache_write_tokens: Tokens = None
    cost_usd: Cost = 0.0


class SourceSnapshot(_Model):
    id: str
    video_id: str
    url: str
    content_sha256: str
    text: str
    fetched_at: datetime | None = None


class Claim(_Model):
    id: str
    snapshot_id: str
    text: str


class UnsupportedItem(_Model):
    kind: Literal["number", "name"]
    value: str


class SceneFactCheck(_Model):
    idx: int = Field(ge=0)
    unsupported: list[UnsupportedItem] = Field(default_factory=list)


class FactCheckReport(_Model):
    passed: bool
    overridden: bool = False
    override_reason: str | None = None
    scenes: list[SceneFactCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def _override_needs_reason(self):
        if self.overridden and not (self.override_reason or "").strip():
            raise ValueError("override requires a non-empty reason")
        return self


T = TypeVar("T", bound=_Model)


def load_versioned(model: type[T], data: dict) -> T:
    """Carrega JSON persistido; recusa versão de schema desconhecida ou ausente."""
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {data.get('schema_version')!r}; expected {SCHEMA_VERSION}")
    return model.model_validate(data)
