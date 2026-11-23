"""Rotas /studio. Só falam com casos de uso; nunca com repositório ou banco."""
from collections.abc import Callable
from datetime import date, datetime, timezone
import base64
import binascii
import hashlib
import hmac
import os
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..application.config import ProviderNotFound
from ..application.budget import (BudgetDenied, CostConfirmationError, IdempotencyConflict, InvalidOperationTransition,
                                  OperationInProgress, OperationSettled, OperationUncertain, UnknownPaidOperation)
from ..domain.channel import (ChannelDurationInvalid, ChannelFieldInvalid, ChannelLockTimeout, ChannelNameInvalid,
                              ChannelProjectNotFound, ChannelStyleNotFound, ChannelVersionConflict, ChannelVersionInvalid,
                              ChannelYouTubeTargetNotFound, DuplicateChannelProfile)
from ..domain.channel_budget import BudgetLimitInvalid
from ..domain.provider import (Availability, EconomicProfile, NoProviderAvailable, ProviderKind,
                               ProviderSpecInvalid)
from ..domain.youtube_channel import YouTubeChannelInvalid
from ..domain.youtube_identity import (ChannelAuthorizationInvalid, GoogleAccountInvalid, OAuthGrantInvalid,
                                       YouTubeChannelIdentityInvalid)
from ..domain.visual_style import (DuplicateVisualStyle, StylePatchInvalid, VisualStyleArchived, VisualStyleFieldInvalid,
                                   VisualStyleNameInvalid, VisualStyleParamsInvalid, VisualStyleVersionConflict,
                                   VisualStyleVersionInvalid)
from ..application.analytics import DailyMetric
from ..application.analytics_collection import (AnalyticsPillarNotFound, AnalyticsVideoNotFound,
                                                 CollectionRequest)
from ..application.analytics_dashboard import AnalyticsFilterNotFound
from ..application.analytics_learning import conclusion_from
from ..application.editorial import (ScriptRejected, SourceRefused, SourceUnavailable, StateConflict, VideoNotFound)
from ..application.longform import ScriptApprovalRefused, ScriptVersionStale
from ..application.ideas import IdeaInputRefused, IdeasRejected, MAX_TOPICS
from ..application.media import AssetRefused, SceneMediaRefused, SceneNotFound
from ..application.production import RunNotFound, StageCapabilityUnavailable
from ..application.publishing import PublicationConflict, PublicationNotFound
from ..application.publication_execution import PublicationResult
from ..application.video_style import ChannelStylePatchConflict, VideoStylePatchConflict
from ..application.youtube_oauth import ChannelNotConnected, ConsentStateInvalid, consent_project_id
from ..application.connections import AuthorizationNotFound, ConnectionNotFound
from ..application.render import RenderRefused
from ..domain.production_run import (CreateRunResult, InvalidIdempotencyKey, InvalidPipeline, InvalidProductionTransition,
                                     ProductionIdempotencyConflict, ProductionRunLockTimeout,
                                     ProductionRunReferencedEntityNotFound, ProductionStage,
                                     RunState,
                                     RunTransitionResult, canonical_idempotency_key)
from ..domain.publish import InvalidPublishData, srt_to_vtt
from ..domain.publication_policy import PublicationPolicyError, PublicConfirmationRequired
from ..domain.youtube_oauth import (OAuthConfigurationError, OAuthError, OAuthReconnectRequired,
                                    OAuthTransientError)
from ..domain.trends import TrendItem, TrendRefused
from ..domain.categories import CategoryNameInvalid, DuplicateCategoryName
from ..application.categories import MissingApiKey, YouTubeApiError
from .preview import render_preview
from .panel import render_panel, render_script, render_tendencias, render_video
from .panel_channels import render_channels
from .panel_styles import render_styles
from .panel_connections import render_connections
from .panel_oauth import render_oauth_callback
from .panel_team import render_team
from .panel_analytics import render_analytics
from .panel_production import (
    STAGE_LABELS,
    ExecutionView,
    NewVideoView,
    PipelineStage,
    render_execution,
    render_new_video,
    render_production_page,
)
from .panel_new_video import render_new_video_v3
from . import panel_settings
from .active_channel import with_channel as _with_channel
from .panel_advanced import render_advanced
from .panel_videos import render_videos
from .panel_video_workspace import render_video_workspace
from .panel_trends import render_tendencias_cartoes, render_tendencias_v3
from ..application.errors import ScriptEditIdempotencyConflict, ScriptRevisionUnavailable, VisualStyleNotFound
from ..application.panel import cost_breakdown
from ..application.ports import MediaCandidate, ModelUnavailable
from ..application.use_cases import InvalidInput, ProjectNotFound, ServiceUnavailable, UseCases
from ..domain.contracts import Approval, Publication, Asset, FactCheckReport, RenderJob, Project, ProductionMode, Scene, Script, Video, VideoFormat, VideoStatus
from ..application.channel_creation import ChannelCreationPayload, IdempotencyConflict as ChannelIdempotencyConflict
from ..domain.qa_report import QaReport
from ..domain.analytics_learning import AnalyticsPeriod, DashboardQuery, ExperimentVariant
from ..domain.insight import MetricWindow
from ..domain.policy import CostRefused
from ..domain.rubric import IdeaScores
from ..domain.ids import InvalidId, check_id
from ..domain.saas import (AuthorizationDenied, ByokStatus, DuplicateMembership, DuplicateProviderKey,
                           KeyInvalid, KeyNotFound, KeyRevoked, LastOwnerRequired, MembershipInvalid,
                           MembershipNotFound, MembershipStatus, OrganizationNotFound, Role, SaasError,
                           UnknownRole)
from ..domain.states import InvalidTransition


# Aprovar, rejeitar e publicar só pelos endpoints próprios (P05), que checam QA e aprovação humana.
RESERVED_TARGETS = {VideoStatus.APPROVED, VideoStatus.REJECTED, VideoStatus.PUBLISHED, VideoStatus.FACT_CHECKED,
                    VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY, VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL}
# Retomar de FAILED não pode saltar etapas com gate; a retomada validada é a P06.
POST_GATE = {VideoStatus.FACT_CHECKED, VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY, VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL}


def _browser_guard(request: Request) -> None:
    """Bloqueia DNS rebinding e origens de navegador diferentes; não substitui autenticação de rede."""
    allowed = {x.strip().lower() for x in os.getenv("STUDIO_ALLOWED_HOSTS", "localhost,127.0.0.1,renderer").split(",") if x.strip()}
    try:
        host = urlsplit("//" + request.headers.get("host", ""))
        if not host.hostname or host.hostname.lower() not in allowed or host.username or host.password:
            raise ValueError
        host.port
    except ValueError:
        raise HTTPException(403, "host not allowed") from None
    origin = request.headers.get("origin")
    if origin:
        expected = f"{request.url.scheme}://{request.headers['host']}"
        if origin.lower() != expected.lower():
            raise HTTPException(403, "origin not allowed")


def _same_secret(left: str, right: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest())


def _required_idempotency_key(request: Request, field: str | None) -> str:
    """Header ``Idempotency-Key`` (ou campo do corpo) obrigatório e na forma canônica."""
    key = request.headers.get("idempotency-key") or field
    if not key:
        raise HTTPException(400, "an Idempotency-Key header (or idempotency_key field) is required")
    try:
        return canonical_idempotency_key(key)
    except InvalidIdempotencyKey as exc:
        raise HTTPException(422, str(exc)) from exc


def _optional_idempotency_key(request: Request, field: str | None = None) -> str | None:
    """Header ``Idempotency-Key`` (ou campo do corpo) opcional; se presente, exige forma canônica."""
    key = request.headers.get("idempotency-key") or field
    if not key:
        return None
    try:
        return canonical_idempotency_key(key)
    except InvalidIdempotencyKey as exc:
        raise HTTPException(422, str(exc)) from exc


def _authenticate(request: Request) -> None:
    user = os.getenv("STUDIO_BROWSER_USER", "")
    password = os.getenv("STUDIO_BROWSER_PASSWORD", "")
    worker = os.getenv("STUDIO_WORKER_TOKEN", "")
    if not user or not password or not worker or ":" in user or _same_secret(password, worker):
        raise HTTPException(503, "studio authentication not configured")
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    browser = False
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
            supplied_user, separator, supplied_password = decoded.partition(":")
            browser = bool(separator) and _same_secret(supplied_user, user) and _same_secret(supplied_password, password)
        except (ValueError, UnicodeError, binascii.Error):
            pass
        if browser:
            if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("origin"):
                raise HTTPException(403, "origin required")
            return
    elif scheme.lower() == "bearer" and _same_secret(value, worker):
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "worker requests must not have origin")
        return
    raise HTTPException(401, "authentication required", headers={"WWW-Authenticate": 'Basic realm="Studio", charset="UTF-8"'})


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    niche: str = Field(default="", max_length=200)
    language: str = Field(default="pt-BR", max_length=16)


class VideoIn(BaseModel):
    project_id: str | None = None
    topic: str = Field(min_length=3, max_length=300)
    format: VideoFormat = VideoFormat.short
    # F02.T02/G15: estilo escolhido no Create; ausente = herda o do canal (comportamento antigo).
    style_id: str | None = Field(default=None, min_length=1, max_length=64)
    production_mode: ProductionMode = ProductionMode.piloto


class VideoOut(Video):
    pass


class SourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    text: str | None = Field(default=None, max_length=1_000_000)  # o caso de uso recusa acima de 200 mil


class SourceOut(BaseModel):
    id: str
    url: str
    content_sha256: str
    chars: int


class ScriptIn(BaseModel):
    scene_count: int = Field(default=6, ge=2, le=20)


class ScriptOut(BaseModel):
    script: Script
    scenes: list[Scene]


class FactCheckIn(BaseModel):
    override_reason: str | None = Field(default=None, max_length=500)

    @field_validator("override_reason")
    @classmethod
    def _not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("override_reason must not be blank")
        return value


class ScriptApproveIn(BaseModel):
    version: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class ScriptSceneEditIn(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)
    narration: str = Field(min_length=5, max_length=400)
    caption: str | None = Field(default=None, max_length=110)
    image_prompt: str | None = Field(default=None, min_length=10, max_length=500)
    claim_ids: list[str] | None = None


class ScriptSceneAddIn(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)
    position: int | None = Field(default=None, ge=0)
    narration: str = Field(min_length=5, max_length=400)
    caption: str = Field(default="", max_length=110)
    label: str = Field(default="", max_length=32)
    image_prompt: str = Field(min_length=10, max_length=500)
    claim_ids: list[str] = Field(default_factory=list)


class ScriptSceneRemoveIn(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)


class ScriptSceneReorderIn(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)
    order: list[int] = Field(min_length=1)


class ScriptRevisionRestoreIn(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)


class ScriptRevisionSceneOut(BaseModel):
    scene_id: str
    idx: int
    narration: str
    caption: str = ""
    label: str = ""
    image_prompt: str
    claim_ids: list[str] = Field(default_factory=list)
    asset_id: str | None = None
    media_review_required: bool = False
    duration_s: float | None = None


class ScriptRevisionOut(BaseModel):
    version: int
    current: bool
    approved: bool
    superseded: bool
    restorable: bool
    scene_count: int
    media_pending: int
    content_hash: str | None = None
    scenes: list[ScriptRevisionSceneOut] = Field(default_factory=list)


def _revision_out(view) -> ScriptRevisionOut:
    return ScriptRevisionOut(
        version=view.version, current=view.current, approved=view.approved, superseded=view.superseded,
        restorable=view.restorable, scene_count=view.scene_count, media_pending=view.media_pending,
        content_hash=view.content_hash,
        scenes=[ScriptRevisionSceneOut(scene_id=scene.scene_id, idx=scene.idx, narration=scene.narration,
                                       caption=scene.caption, label=scene.label, image_prompt=scene.image_prompt,
                                       claim_ids=list(scene.claim_ids), asset_id=scene.asset_id,
                                       media_review_required=scene.media_review_required,
                                       duration_s=scene.duration_s)
                for scene in view.scenes])


class MediaCandidateOut(BaseModel):
    """Candidato de mídia exposto pela busca (W4.4); licença e proveniência sempre presentes."""

    license: str
    source_url: str
    url: str
    attribution: str
    author: str = ""
    media_id: str = ""
    media_type: str = "image"
    width: int | None = None
    height: int | None = None
    cost_usd: float | None = None


class SceneCandidatesOut(BaseModel):
    scene_id: str
    query: str
    candidates: list[MediaCandidateOut]


class SceneMediaChoiceIn(BaseModel):
    """Escolha de mídia de uma cena: um asset existente **ou** um candidato (nunca os dois)."""

    asset_id: str | None = None
    candidate: MediaCandidateOut | None = None
    expected_asset_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)


class SceneMediaOut(BaseModel):
    scene_id: str
    asset: Asset | None
    changed: bool
    reason: str = ""


def _candidate_out(candidate: MediaCandidate) -> MediaCandidateOut:
    return MediaCandidateOut(
        license=candidate.license, source_url=candidate.source_url, url=candidate.url,
        attribution=candidate.attribution, author=candidate.author, media_id=candidate.media_id,
        media_type=candidate.media_type, width=candidate.width, height=candidate.height,
        cost_usd=float(candidate.cost_usd) if candidate.cost_usd is not None else None)


class SceneNarrationOut(BaseModel):
    video_id: str
    scene_id: str
    duration_s: float
    sha256: str
    voice_id: str = ""
    audio_url: str


class IdeasIn(BaseModel):
    topics: list[str] = Field(min_length=1, max_length=MAX_TOPICS)
    project_id: str | None = None


class TrendsIn(BaseModel):
    project_id: str
    items: list[TrendItem] = Field(min_length=1, max_length=50)


class RankedOut(BaseModel):
    topic: str
    score: float
    scores: IdeaScores


class IdeasOut(BaseModel):
    ranked: list[RankedOut]


class AnalyticsIdeasIn(BaseModel):
    video_id: str
    start: date
    end: date


class MetricEvidence(BaseModel):
    video_id: str
    date: date


class AnalyticsRankedOut(RankedOut):
    note: str
    evidence: list[MetricEvidence]


class AnalyticsIdeasOut(BaseModel):
    ranked: list[AnalyticsRankedOut]


class ProduceOut(BaseModel):
    generated: int
    reused: int


class SceneAssetOut(BaseModel):
    idx: int
    asset: Asset | None


class AssetsOut(BaseModel):
    scenes: list[SceneAssetOut]


class RenderStatusOut(BaseModel):
    job: RenderJob | None
    qa_report: QaReport | None


class ApproveIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=50)
    publish_at: datetime | None = None
    override_reason: str | None = Field(default=None, max_length=500)
    output_asset_id: str | None = None
    visibility: str = Field(default="private", max_length=16)  # F8-06: público exige confirmação extra
    confirm_publication: bool = False


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class DecisionOut(BaseModel):
    video: Video
    changed: bool  # False: já estava decidido (repetir é seguro)


class ClaimIn(BaseModel):
    lease_seconds: int = Field(default=1800, ge=20, le=7200)


class ClaimOut(BaseModel):
    publication: Publication
    youtube_body: dict
    file_size: int
    content_type: str
    file_path: str
    thumbnail_path: str


class ClaimResult(BaseModel):
    item: ClaimOut | None


class UploadUriIn(BaseModel):
    attempt: int = Field(ge=1)
    upload_uri: str = Field(max_length=2000)
    replace: bool = False


class UploadedIn(BaseModel):
    youtube_video_id: str = Field(max_length=64)


class FailedIn(BaseModel):
    attempt: int = Field(ge=1)
    error: str = Field(max_length=2000)
    retryable: bool


class PublishIn(BaseModel):
    lease_seconds: int = Field(default=1800, ge=20, le=7200)
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class PublicationRunOut(BaseModel):
    result: str
    publication: Publication | None = None
    youtube_video_id: str | None = None
    detail: str | None = None


class OAuthAuthorizeOut(BaseModel):
    project_id: str
    authorization_url: str
    state: str
    expires_at: datetime


class OAuthCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=256)


class TransitionIn(BaseModel):
    expected: VideoStatus
    new: VideoStatus


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    queries: list[str] = Field(default_factory=list)
    id: str | None = None


class CategoryOut(BaseModel):
    id: str
    project_id: str
    name: str
    queries: list[str]
    created_at: datetime
    updated_at: datetime


class TrendRefreshIn(BaseModel):
    queries: list[str] | None = None


class ProductionRunIn(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=200)
    channel_id: str | None = None
    stages: list[str] | None = None  # subconjunto fechado sob dependências; vazio/None usa o pipeline padrão


class ProductionActionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ChannelStylePatchIn(BaseModel):
    """F05.T04: patch tipado do canal com revisão otimista (0 = nunca personalizado)."""

    expected_revision: int = Field(default=0, ge=0)
    patch: dict | None = None


class ChannelStylePatchOut(BaseModel):
    revision: int
    patch: dict | None = None


class VideoStylePatchIn(BaseModel):
    """F05.T02: patch tipado do vídeo com revisão otimista (0 = nunca personalizado)."""

    expected_revision: int = Field(default=0, ge=0)
    patch: dict | None = None


class VideoStylePatchOut(BaseModel):
    revision: int
    patch: dict | None = None


class ProductionRegenerateIn(BaseModel):
    """Regenerar é execução nova; a revisão escolhe a chave determinística."""

    revision: int = Field(default=1, ge=1, le=20)
    reason: str | None = Field(default=None, max_length=500)


class ProductionResumeIn(BaseModel):
    expected_state: RunState | None = None  # CAS opcional; ausente usa o estado persistido atual


class ProductionRunStartOut(BaseModel):
    run_id: str
    state: str
    mode: str
    created: bool


class ProductionStageStateOut(BaseModel):
    stage: str
    state: str
    attempt: int
    fencing_token: int
    checkpoint_version: int | None = None
    error: str | None = None
    updated_at: datetime | None = None


class ProductionEventOut(BaseModel):
    id: int
    event_type: str
    event_version: int
    stage_id: str | None = None
    payload: dict
    created_at: datetime | None = None


class ProductionRunViewOut(BaseModel):
    run_id: str
    video_id: str
    state: str
    mode: str
    channel_id: str | None = None
    next_action: str | None = None
    next_stage: str | None = None
    stages: list[ProductionStageStateOut]
    available_stages: list[str]
    unavailable_stages: list[dict]
    events: list[ProductionEventOut]


# -- canais/providers/budget (F10-03..07) -----------------------------------


class ChannelProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strategy: str = Field(default="", max_length=500)
    language: str = Field(default="pt-BR", max_length=20)
    audience: str = Field(default="", max_length=500)
    pillars: list[str] = Field(default_factory=list, max_length=20)
    narrative: str = Field(default="", max_length=4000)
    target_duration_s: int = Field(default=60, ge=1, le=36000)
    visual_identity: str = Field(default="", max_length=2000)
    voice: str = Field(default="", max_length=200)
    audio: str = Field(default="", max_length=200)
    thumbnail: str = Field(default="", max_length=2000)
    cta: str = Field(default="", max_length=500)
    style_id: str | None = None
    youtube_channel_id: str | None = None
    default_mode: ProductionMode = ProductionMode.piloto
    default_format: VideoFormat = VideoFormat.short
    archived: bool = False


class ChannelUpdateIn(BaseModel):
    expected_version: int = Field(ge=1)
    changes: dict[str, object] = Field(default_factory=dict)
    default_mode: ProductionMode = ProductionMode.piloto
    default_format: VideoFormat = VideoFormat.short


class ChannelProfileOut(BaseModel):
    id: str
    project_id: str
    name: str
    strategy: str
    language: str
    audience: str
    pillars: list[str]
    narrative: str
    target_duration_s: int
    visual_identity: str
    voice: str
    audio: str
    thumbnail: str
    cta: str
    style_id: str | None = None
    youtube_channel_id: str | None = None
    default_mode: ProductionMode = ProductionMode.piloto
    default_format: VideoFormat = VideoFormat.short
    version: int
    archived: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    niche: str = ""
    language: str = "pt-BR"
    budget_usd_month: float = 15.0
    config: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None


class ChannelBudgetOut(BaseModel):
    project_id: str
    hard_monthly_usd: float
    soft_monthly_usd: float
    hard_video_usd: float
    soft_video_usd: float
    economic_profile: str


class ChannelTransactionalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    niche: str = Field(default="", max_length=200)
    language: str = Field(default="pt-BR", max_length=20)
    strategy: str = Field(default="", max_length=500)
    audience: str = Field(default="", max_length=500)
    pillars: list[str] = Field(default_factory=list, max_length=20)
    narrative: str = Field(default="", max_length=4000)
    target_duration_s: int = Field(default=60, ge=1, le=36000)
    visual_identity: str = Field(default="", max_length=2000)
    voice: str = Field(default="", max_length=200)
    audio: str = Field(default="", max_length=200)
    thumbnail: str = Field(default="", max_length=2000)
    cta: str = Field(default="", max_length=500)
    style_id: str | None = None
    youtube_channel_id: str | None = None
    default_mode: ProductionMode = ProductionMode.piloto
    default_format: VideoFormat = VideoFormat.short
    hard_monthly_usd: float = Field(default=100.0, ge=0)
    soft_monthly_usd: float | None = Field(default=None, ge=0)
    hard_video_usd: float = Field(default=10.0, ge=0)
    soft_video_usd: float | None = Field(default=None, ge=0)
    economic_profile: EconomicProfile = EconomicProfile.BALANCED
    provider_config: dict[str, str] | None = None


class ChannelTransactionalOut(BaseModel):
    project: ProjectOut
    profile: ChannelProfileOut
    budget: ChannelBudgetOut


class VisualStyleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: dict[str, object] = Field(default_factory=dict)


class VisualStyleUpdateIn(BaseModel):
    expected_version: int = Field(ge=1)
    changes: dict[str, object]


class VideoStyleIn(BaseModel):
    """Override de estilo de um vídeo (VS-05b): a chave do estilo ou ``null`` para voltar a herdar."""

    style_id: str | None = None


class VisualStyleOut(BaseModel):
    id: str
    name: str
    params: dict[str, object]
    version: int
    archived: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    channels_using: int = 0
    # VS-05c: só a resposta do arquivamento preenche; mede os vínculos de canal/vídeo soltos.
    links_cleared: int = 0


class ProviderCostOut(BaseModel):
    kind: str
    amount_usd: str | None
    label: str
    note: str


class ProviderCardOut(BaseModel):
    kind: str
    spec: str
    name: str
    model: str
    capabilities: list[str]
    cost: ProviderCostOut
    rate_limit_per_min: int | None
    quality: int
    availability: str
    reason: str | None = None


class ProviderTestIn(BaseModel):
    kind: ProviderKind
    spec: str | None = Field(default=None, max_length=200)


class ConnectionTestOut(BaseModel):
    kind: str
    spec: str
    name: str
    available: bool
    checked: bool
    reason: str | None = None


class RouteIn(BaseModel):
    kind: ProviderKind
    profile: EconomicProfile = EconomicProfile.BALANCED
    max_cost_usd: str | None = None


class RoutingOut(BaseModel):
    kind: str
    profile: str
    primary: ProviderCardOut
    fallbacks: list[ProviderCardOut]
    reason: str


class BudgetIn(BaseModel):
    hard_monthly_usd: str
    soft_monthly_usd: str
    hard_video_usd: str
    soft_video_usd: str
    economic_profile: EconomicProfile = EconomicProfile.BALANCED


class BudgetLimitsOut(BaseModel):
    project_id: str
    hard_monthly_usd: str
    soft_monthly_usd: str
    hard_video_usd: str
    soft_video_usd: str
    economic_profile: str


class BudgetDecisionOut(BaseModel):
    scope: str
    kind: str
    spent_usd: str
    projected_usd: str
    soft_usd: str
    hard_usd: str
    message: str


class CostSummaryOut(BaseModel):
    real_usd: str
    estimate_usd: str
    spent_usd: str
    free_calls: int
    unknown_calls: int
    unattributed_calls: int
    has_usage: bool
    labels: dict[str, str]


class BudgetOut(BaseModel):
    configured: bool
    limits: BudgetLimitsOut
    summary: CostSummaryOut
    monthly: BudgetDecisionOut
    video: BudgetDecisionOut


class YouTubeChannelIn(BaseModel):
    channel_id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=200)
    scopes: list[str] = Field(default_factory=list)
    access_token: str | None = Field(default=None, max_length=4000)
    refresh_token: str | None = Field(default=None, max_length=4000)
    token_expires_at: datetime | None = None


class YouTubeChannelOut(BaseModel):
    project_id: str
    channel_id: str | None = None
    title: str
    scopes: list[str]
    oauth_status: str
    connected: bool
    token_expires_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectConfigOut(BaseModel):
    project_id: str
    config: dict[str, str]


# -- conexões: conta Google → autorizações → canais do YouTube (YT-04a) ------


class ConnectionsAuthorizeOut(BaseModel):
    authorization_url: str
    state: str
    expires_at: datetime


class ConnectionsCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=320)  # reserva: quando o consentimento não a expõe


class ConnectionAccountOut(BaseModel):
    id: str
    email: str
    display_name: str


class ConnectionChannelIdentityOut(BaseModel):
    youtube_channel_id: str
    title: str


class ConnectionConsentOut(BaseModel):
    account: ConnectionAccountOut
    channel: ConnectionChannelIdentityOut
    grant_id: str
    status: str
    validated_at: datetime | None = None


class StudioChannelRefOut(BaseModel):
    id: str
    name: str
    archived: bool


class ConnectionChannelOut(BaseModel):
    youtube_channel_id: str
    title: str
    grant_id: str
    status: str
    token_expires_at: datetime | None = None
    validated_at: datetime | None = None
    studio_channels: list[StudioChannelRefOut] = Field(default_factory=list)


class ConnectionAccountConnectionsOut(BaseModel):
    id: str
    email: str
    display_name: str
    channels: list[ConnectionChannelOut] = Field(default_factory=list)


class ConnectionsOut(BaseModel):
    accounts: list[ConnectionAccountConnectionsOut] = Field(default_factory=list)


class AuthorizationRevokedOut(BaseModel):
    grant_id: str
    youtube_channel_id: str
    status: str


def _channel_out(profile) -> dict:
    return {"id": profile.id, "project_id": profile.project_id, "name": profile.name,
            "strategy": profile.strategy, "language": profile.language, "audience": profile.audience,
            "pillars": list(profile.pillars), "narrative": profile.narrative,
            "target_duration_s": profile.target_duration_s, "visual_identity": profile.visual_identity,
            "voice": profile.voice, "audio": profile.audio, "thumbnail": profile.thumbnail, "cta": profile.cta,
            "style_id": profile.style_id,
            "youtube_channel_id": profile.youtube_channel_id,
            "default_mode": profile.default_mode,
            "default_format": profile.default_format,
            "version": profile.version, "archived": profile.archived,
            "created_at": profile.created_at, "updated_at": profile.updated_at}


def _style_out(style, channels_using: int = 0) -> dict:
    return {"id": style.id, "name": style.name, "params": dict(style.params),
            "version": style.version, "archived": style.archived,
            "created_at": style.created_at, "updated_at": style.updated_at,
            "channels_using": channels_using}


def _card_out(card) -> dict:
    return {"kind": card.kind.value, "spec": card.spec, "name": card.name, "model": card.model,
            "capabilities": list(card.capabilities),
            "cost": {"kind": card.cost.kind.value,
                     "amount_usd": None if card.cost.amount_usd is None else str(card.cost.amount_usd),
                     "label": card.cost.label, "note": card.cost.note},
            "rate_limit_per_min": card.rate_limit_per_min, "quality": card.quality,
            "availability": card.availability.value, "reason": card.reason}


def _limits_out(limits) -> dict:
    return {"project_id": limits.project_id, "hard_monthly_usd": f"{limits.hard_monthly_usd:.2f}",
            "soft_monthly_usd": f"{limits.soft_monthly_usd:.2f}", "hard_video_usd": f"{limits.hard_video_usd:.2f}",
            "soft_video_usd": f"{limits.soft_video_usd:.2f}", "economic_profile": limits.economic_profile.value}


def _decision_out(decision) -> dict:
    return {"scope": decision.scope, "kind": decision.kind.value, "spent_usd": f"{decision.spent_usd:.2f}",
            "projected_usd": f"{decision.projected_usd:.2f}", "soft_usd": f"{decision.soft_usd:.2f}",
            "hard_usd": f"{decision.hard_usd:.2f}", "message": decision.message}


def _summary_out(summary) -> dict:
    return {"real_usd": f"{summary.real_usd:.2f}", "estimate_usd": f"{summary.estimate_usd:.2f}",
            "spent_usd": f"{summary.spent_usd:.2f}", "free_calls": summary.free_calls,
            "unknown_calls": summary.unknown_calls, "unattributed_calls": summary.unattributed_calls,
            "has_usage": summary.has_usage, "labels": summary.labels()}


def _budget_out(view) -> dict:
    return {"configured": view.configured, "limits": _limits_out(view.limits),
            "summary": _summary_out(view.summary), "monthly": _decision_out(view.monthly),
            "video": _decision_out(view.video)}


class AnalyticsDecisionIn(BaseModel):
    project_id: str
    decision: Literal["accepted_for_review", "rejected"]


class AnalyticsCollectIn(BaseModel):
    video_id: str
    days: int = 7
    pillar_id: str | None = None


class ExperimentVariantIn(BaseModel):
    variant_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    is_control: bool = False


class ExperimentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    video_id: str
    kind: Literal["thumbnail", "title"]
    status: Literal["planned", "running", "finished", "abandoned"] = "planned"
    variants: list[ExperimentVariantIn] = Field(min_length=2)
    window_start: datetime | None = None
    window_end: datetime | None = None
    conclusion: str | None = Field(default=None, max_length=2000)
    conclusion_confidence: Literal["low", "medium", "high"] | None = None
    conclusion_basis: str | None = Field(default=None, max_length=2000)
    conclusion_observation_ids: list[str] = Field(default_factory=list)


def _operator() -> str:
    return os.getenv("STUDIO_BROWSER_USER", "").strip() or "operador local"


def _analytics_period(days: int):
    try:
        return AnalyticsPeriod(days=days, end_at=datetime.now(timezone.utc))
    except ValidationError:
        raise HTTPException(422, "days must be 7, 28 or 90") from None
class TeamMemberIn(BaseModel):
    organization_id: str = Field(min_length=32, max_length=32)
    email: str = Field(min_length=3, max_length=320)
    role: Role
    display_name: str | None = Field(default=None, max_length=120)


class TeamMemberRoleIn(BaseModel):
    organization_id: str = Field(min_length=32, max_length=32)
    role: Role


class ByokKeyIn(BaseModel):
    # `value` sem mínimo/máximo: a validação é do domínio (`validate_byok_value`), que nunca ecoa
    # o valor numa mensagem de erro — evita a chave reaparecer no corpo de um 422.
    organization_id: str = Field(min_length=32, max_length=32)
    provider: str = Field(min_length=1, max_length=64)
    value: str


class ByokRotateIn(BaseModel):
    organization_id: str = Field(min_length=32, max_length=32)
    value: str


class MemberOut(BaseModel):
    membership_id: str
    organization_id: str
    user_id: str
    display_name: str
    email: str
    role: Role
    status: MembershipStatus


class KeyOut(BaseModel):
    id: str
    organization_id: str
    provider: str
    mask: str
    fingerprint: str
    status: ByokStatus
    created_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


def _member_out(member) -> MemberOut:
    return MemberOut(membership_id=member.membership_id, organization_id=member.organization_id,
                     user_id=member.user_id, display_name=member.display_name, email=member.email,
                     role=member.role, status=member.status)


def _key_out(key) -> KeyOut:
    return KeyOut(id=key.id, organization_id=key.organization_id, provider=key.provider, mask=key.mask,
                  fingerprint=key.fingerprint, status=key.status, created_at=key.created_at,
                  rotated_at=key.rotated_at, revoked_at=key.revoked_at)


def make_router(get_use_cases: Callable[[], UseCases | None], ping: Callable[[], bool]) -> APIRouter:
    router = APIRouter(prefix="/studio", tags=["studio"], dependencies=[Depends(_browser_guard), Depends(_authenticate)])

    def run(fn):
        uc = get_use_cases()
        if uc is None:
            raise HTTPException(503, "studio database unavailable")
        try:
            return fn(uc)
        except InvalidId as exc:
            raise HTTPException(422, "invalid id") from exc
        except ProjectNotFound as exc:
            raise HTTPException(404, "project not found") from exc
        except OrganizationNotFound as exc:
            raise HTTPException(404, "organization not found") from exc
        except (InvalidTransition, InvalidInput) as exc:
            raise HTTPException(422, str(exc)) from exc
        except ServiceUnavailable as exc:
            raise HTTPException(503, "studio database unavailable") from exc
        except VideoNotFound as exc:
            raise HTTPException(404, "video not found") from exc
        except StateConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ScriptVersionStale as exc:
            raise HTTPException(409, str(exc)) from exc
        except ScriptEditIdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ScriptRevisionUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        except SceneNotFound as exc:
            raise HTTPException(404, "scene not found") from exc
        except SceneMediaRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        except ScriptApprovalRefused as exc:
            raise HTTPException(422, str(exc)) from exc
        except (SourceRefused, ProviderNotFound, IdeaInputRefused, TrendRefused) as exc:
            raise HTTPException(422, str(exc)) from exc
        except CostRefused as exc:
            raise HTTPException(403, f"cost cap: {exc}") from exc
        except (SourceUnavailable, ModelUnavailable) as exc:
            raise HTTPException(502, str(exc)) from exc
        except (ScriptRejected, IdeasRejected) as exc:
            raise HTTPException(502, f"model output rejected: {exc}") from exc
        except InvalidPublishData as exc:
            raise HTTPException(422, str(exc)) from exc
        except (PublicConfirmationRequired, PublicationPolicyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except ConsentStateInvalid as exc:
            raise HTTPException(409, str(exc)) from exc
        except ChannelNotConnected as exc:
            raise HTTPException(409, f"YouTube channel reconnect required: {exc}") from exc
        except OAuthReconnectRequired as exc:
            raise HTTPException(409, f"YouTube channel reconnect required: {exc}") from exc
        except OAuthTransientError as exc:
            raise HTTPException(502, f"YouTube OAuth is temporarily unavailable: {exc}") from exc
        except OAuthConfigurationError as exc:
            raise HTTPException(503, f"YouTube OAuth is not configured: {exc}") from exc
        except OAuthError as exc:
            raise HTTPException(502, f"YouTube OAuth failed: {exc}") from exc
        except PublicationNotFound as exc:
            raise HTTPException(404, "publication not found") from exc
        except PublicationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (AssetRefused, RenderRefused) as exc:
            raise HTTPException(502, f"asset refused: {exc}") from exc
        except DuplicateCategoryName as exc:
            raise HTTPException(409, str(exc)) from exc
        except CategoryNameInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except MissingApiKey as exc:
            raise HTTPException(400, str(exc)) from exc
        except YouTubeApiError as exc:
            raise HTTPException(502, str(exc)) from exc
        except BudgetDenied as exc:
            # Achado 3: a recusa diz **qual** teto estourou, com os números, quando o repositório
            # sabe informar; sem detalhe, mantém a mensagem genérica (a recusa continua válida).
            detail = getattr(exc, "detail", None)
            message = ("budget denied: " + detail.describe() if detail is not None else
                       "budget denied: cost cap or unknown cost blocks the operation")
            raise HTTPException(403, message) from exc
        except IdempotencyConflict as exc:
            raise HTTPException(409, "idempotency key was already used with different parameters") from exc
        except CostConfirmationError as exc:
            raise HTTPException(422, "cost confirmation does not match the provider result") from exc
        except OperationSettled as exc:
            # mensagem por estado: CONFIRMED e RELEASED não são "in progress"/"awaiting reconciliation"
            message = {"CONFIRMED": "paid operation was already confirmed; reuse the existing result",
                       "RELEASED": "paid operation was released and cannot be retried"}.get(
                           getattr(exc, "state", None), "paid operation was already settled")
            raise HTTPException(409, message) from exc
        except OperationInProgress as exc:
            raise HTTPException(409, "paid operation is already in progress") from exc
        except (OperationUncertain, InvalidOperationTransition) as exc:
            raise HTTPException(409, "paid operation is uncertain or in an incompatible state; reconcile before retrying") from exc
        except UnknownPaidOperation as exc:
            raise HTTPException(404, "paid operation not found") from exc
        except ProductionIdempotencyConflict as exc:
            raise HTTPException(409, "idempotency key was already used for a different production run request") from exc
        except InvalidIdempotencyKey as exc:
            raise HTTPException(422, "idempotency key is not in the canonical form") from exc
        except ProductionRunLockTimeout as exc:
            raise HTTPException(409, "the production run is busy; retry the operation") from exc
        except ProductionRunReferencedEntityNotFound as exc:
            raise HTTPException(404, "video or channel not found") from exc
        except (InvalidPipeline, InvalidProductionTransition) as exc:
            raise HTTPException(422, str(exc)) from exc
        except StageCapabilityUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        except RunNotFound as exc:
            raise HTTPException(404, "production run not found") from exc
        except (AnalyticsFilterNotFound, AnalyticsVideoNotFound, AnalyticsPillarNotFound) as exc:
            raise HTTPException(404, str(exc)) from exc
        # -- canais/providers/budget (F10-03..07) --
        except ChannelProjectNotFound as exc:
            raise HTTPException(404, "project not found") from exc
        except (DuplicateChannelProfile, ChannelVersionConflict, ChannelLockTimeout) as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ChannelNameInvalid, ChannelFieldInvalid, ChannelDurationInvalid, ChannelVersionInvalid,
                ChannelStyleNotFound, ChannelYouTubeTargetNotFound, YouTubeChannelIdentityInvalid,
                GoogleAccountInvalid, OAuthGrantInvalid, ChannelAuthorizationInvalid) as exc:
            raise HTTPException(422, str(exc)) from exc
        # -- conexões: conta → autorizações → canais (YT-04a) --
        except (ConnectionNotFound, AuthorizationNotFound) as exc:
            raise HTTPException(404, str(exc)) from exc
        # -- estilos: biblioteca compartilhada (VS-05a) --
        except VisualStyleNotFound as exc:
            raise HTTPException(404, "visual style not found") from exc
        except (DuplicateVisualStyle, VisualStyleVersionConflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        except VisualStyleArchived as exc:
            raise HTTPException(422, str(exc)) from exc
        except (VisualStyleNameInvalid, VisualStyleParamsInvalid, VisualStyleFieldInvalid,
                VisualStyleVersionInvalid) as exc:
            raise HTTPException(422, str(exc)) from exc
        except ProviderSpecInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except NoProviderAvailable as exc:
            raise HTTPException(409, str(exc)) from exc
        except BudgetLimitInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except YouTubeChannelInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        # -- equipe/BYOK (L2) -- ordem importa: subclasses antes da base --
        except AuthorizationDenied as exc:
            raise HTTPException(403, "operation not permitted for this membership") from exc
        except (DuplicateMembership, DuplicateProviderKey, LastOwnerRequired) as exc:
            raise HTTPException(409, str(exc)) from exc
        except (MembershipNotFound, KeyNotFound) as exc:
            raise HTTPException(404, str(exc)) from exc
        except KeyRevoked as exc:
            raise HTTPException(409, str(exc)) from exc
        except (MembershipInvalid, KeyInvalid, UnknownRole, SaasError) as exc:
            raise HTTPException(422, str(exc)) from exc

    def editorial(uc: UseCases):
        if uc.editorial is None:
            raise HTTPException(503, "editorial services unavailable")
        return uc.editorial

    @router.post("/projects", status_code=201, response_model=Project, response_model_exclude={"config"})
    def create_project(body: ProjectIn):
        return run(lambda uc: uc.create_project.execute(body.name, body.niche, body.language))

    @router.get("/projects/{project_id}/categories", response_model=list[CategoryOut])
    def list_categories(project_id: str):
        def go(uc):
            if uc.list_categories is None:
                raise HTTPException(503, "category services unavailable")
            return uc.list_categories.execute(check_id(project_id))
        return run(go)

    @router.post("/projects/{project_id}/categories", status_code=201, response_model=CategoryOut)
    def save_category(project_id: str, body: CategoryIn):
        def go(uc):
            if uc.save_category is None:
                raise HTTPException(503, "category services unavailable")
            return uc.save_category.execute(
                check_id(project_id),
                body.name,
                body.queries,
                category_id=check_id(body.id) if body.id else None,
            )
        return run(go)

    @router.delete("/projects/{project_id}/categories/{category_id}")
    def delete_category(project_id: str, category_id: str):
        def go(uc):
            if uc.delete_category is None:
                raise HTTPException(503, "category services unavailable")
            p_id = check_id(project_id)
            c_id = check_id(category_id)
            if uc.categories_repo is not None:
                cat = uc.categories_repo.get(c_id)
                if cat is None or cat.project_id != p_id:
                    raise HTTPException(404, "category not found")
            deleted = uc.delete_category.execute(c_id)
            if not deleted:
                raise HTTPException(404, "category not found")
            return {"deleted": True}
        return run(go)

    @router.post("/projects/{project_id}/trends/refresh")
    def refresh_trends(project_id: str, body: TrendRefreshIn | None = None):
        def go(uc):
            if uc.refresh_trends is None:
                raise HTTPException(503, "trends services unavailable")
            queries = body.queries if body else None
            stored = uc.refresh_trends.execute(check_id(project_id), queries)
            return {"stored": stored}
        return run(go)

    @router.post("/videos", status_code=201, response_model=VideoOut)
    def create_video(body: VideoIn):
        if not body.project_id:
            raise HTTPException(422, "project_id is required")
        return run(lambda uc: uc.create_video.execute(check_id(body.project_id), body.topic, body.format,
                                                      body.style_id,
                                                      production_mode=body.production_mode))

    @router.post("/projects/{project_id}/videos", status_code=201, response_model=VideoOut)
    def create_project_video(project_id: str, body: VideoIn):
        return run(lambda uc: uc.create_video.execute(check_id(project_id), body.topic, body.format,
                                                      body.style_id,
                                                      production_mode=body.production_mode))

    @router.get("/videos/{video_id}", response_model=Video)
    def get_video(video_id: str):
        video = run(lambda uc: uc.get_video.execute(check_id(video_id)))
        if video is None:
            raise HTTPException(404, "video not found")
        return video

    @router.post("/videos/{video_id}/transition")
    def transition(video_id: str, body: TransitionIn):
        if body.new in RESERVED_TARGETS or (body.expected == VideoStatus.FAILED and body.new in POST_GATE):
            raise HTTPException(403, "this transition is reserved for the dedicated endpoints (fact-check, approve, reject, publish, resume)")
        if not run(lambda uc: uc.transition_video.execute(check_id(video_id), body.expected, body.new)):
            raise HTTPException(409, "video is not in the expected state")
        return {"ok": True}

    @router.post("/videos/{video_id}/sources", status_code=201, response_model=SourceOut)
    def add_source(video_id: str, body: SourceIn):
        def go(uc):
            ing = editorial(uc).ingest
            snap = ing.execute_url(check_id(video_id), body.url) if body.text is None else ing.execute_text(check_id(video_id), body.url, body.text)
            return SourceOut(id=snap.id, url=snap.url, content_sha256=snap.content_sha256, chars=len(snap.text))
        return run(go)

    @router.get("/videos/{video_id}/sources", response_model=list[SourceOut])
    def list_sources(video_id: str):
        def go(uc):
            ed = editorial(uc)
            if ed.list_sources is None:
                raise HTTPException(503, "editorial services unavailable")
            # O texto da fonte nunca sai no corpo: a lista é URL, hash e tamanho.
            return [SourceOut(id=s.id, url=s.url, content_sha256=s.content_sha256, chars=len(s.text))
                    for s in ed.list_sources.execute(check_id(video_id))]
        return run(go)

    @router.post("/videos/{video_id}/script", status_code=201, response_model=ScriptOut)
    def generate_script(video_id: str, body: ScriptIn):
        def go(uc):
            ed = editorial(uc)
            ed.generate.execute(check_id(video_id), body.scene_count)
            found = ed.get_script.execute(video_id)
            if found is None:
                raise HTTPException(409, "script disappeared while generating")
            script, scenes = found
            return ScriptOut(script=script, scenes=scenes)
        return run(go)

    @router.get("/videos/{video_id}/script", response_model=ScriptOut)
    def get_script(video_id: str):
        found = run(lambda uc: editorial(uc).get_script.execute(check_id(video_id)))
        if found is None:
            raise HTTPException(404, "script not found")
        return ScriptOut(script=found[0], scenes=found[1])

    # Reorder é registrado antes de "/scenes/{scene_idx}" para não ser capturado como índice.
    @router.post("/videos/{video_id}/script/scenes/reorder", response_model=ScriptOut)
    def reorder_script_scenes(video_id: str, body: ScriptSceneReorderIn, request: Request):
        key = _required_idempotency_key(request, body.idempotency_key)

        def go(uc):
            ed = editorial(uc)
            if ed.reorder_scenes is None:
                raise HTTPException(503, "script editing unavailable")
            result = ed.reorder_scenes.execute_idempotent(
                check_id(video_id), body.order, expected_version=body.expected_version, idempotency_key=key)
            return ScriptOut(script=result.script, scenes=list(result.scenes))
        return run(go)

    @router.post("/videos/{video_id}/script/scenes", response_model=ScriptOut)
    def add_script_scene(video_id: str, body: ScriptSceneAddIn, request: Request):
        key = _required_idempotency_key(request, body.idempotency_key)

        def go(uc):
            ed = editorial(uc)
            if ed.add_scene is None:
                raise HTTPException(503, "script editing unavailable")
            result = ed.add_scene.execute_idempotent(
                check_id(video_id), expected_version=body.expected_version, idempotency_key=key,
                narration=body.narration, image_prompt=body.image_prompt, position=body.position,
                caption=body.caption, label=body.label, claim_ids=body.claim_ids)
            return ScriptOut(script=result.script, scenes=list(result.scenes))
        return run(go)

    @router.post("/videos/{video_id}/script/scenes/{scene_idx}", response_model=ScriptOut)
    def edit_script_scene(video_id: str, scene_idx: int, body: ScriptSceneEditIn, request: Request):
        key = _required_idempotency_key(request, body.idempotency_key)

        def go(uc):
            ed = editorial(uc)
            if ed.edit_script is None:
                raise HTTPException(503, "script editing unavailable")
            result = ed.edit_script.execute_idempotent(
                check_id(video_id), scene_idx, body.narration, expected_version=body.expected_version,
                idempotency_key=key, caption=body.caption, image_prompt=body.image_prompt,
                claim_ids=body.claim_ids)
            return ScriptOut(script=result.script, scenes=list(result.scenes))
        return run(go)

    @router.delete("/videos/{video_id}/script/scenes/{scene_idx}", response_model=ScriptOut)
    def remove_script_scene(video_id: str, scene_idx: int, body: ScriptSceneRemoveIn, request: Request):
        key = _required_idempotency_key(request, body.idempotency_key)

        def go(uc):
            ed = editorial(uc)
            if ed.remove_scene is None:
                raise HTTPException(503, "script editing unavailable")
            result = ed.remove_scene.execute_idempotent(
                check_id(video_id), scene_idx, expected_version=body.expected_version, idempotency_key=key)
            return ScriptOut(script=result.script, scenes=list(result.scenes))
        return run(go)

    # W4.5 (EDIT-04): histórico recuperável. Restaurar cria uma NOVA revisão a partir da escolhida.
    @router.get("/videos/{video_id}/script/revisions", response_model=list[ScriptRevisionOut])
    def list_script_revisions(video_id: str):
        def go(uc):
            ed = editorial(uc)
            if ed.list_revisions is None:
                raise HTTPException(503, "script revisions unavailable")
            return [_revision_out(view) for view in ed.list_revisions.execute(check_id(video_id))]
        return run(go)

    @router.get("/videos/{video_id}/script/revisions/{version}", response_model=ScriptRevisionOut)
    def get_script_revision(video_id: str, version: int):
        def go(uc):
            ed = editorial(uc)
            if ed.get_revision is None:
                raise HTTPException(503, "script revisions unavailable")
            return _revision_out(ed.get_revision.execute(check_id(video_id), version))
        return run(go)

    @router.post("/videos/{video_id}/script/revisions/{version}/restore", response_model=ScriptOut)
    def restore_script_revision(video_id: str, version: int, body: ScriptRevisionRestoreIn, request: Request):
        key = _required_idempotency_key(request, body.idempotency_key)

        def go(uc):
            ed = editorial(uc)
            if ed.restore_revision is None:
                raise HTTPException(503, "script revisions unavailable")
            result = ed.restore_revision.execute_idempotent(
                check_id(video_id), version, expected_version=body.expected_version, idempotency_key=key)
            return ScriptOut(script=result.script, scenes=list(result.scenes))
        return run(go)

    @router.get("/videos/{video_id}/roteiro", response_class=HTMLResponse)
    def script_page(video_id: str):
        def get_page(uc):
            if uc.script_view is None:
                raise HTTPException(503, "script view unavailable")
            return render_script(uc.script_view.execute(check_id(video_id)),
                                 video_channel=_video_channel_name(uc, video_id))
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.post("/videos/{video_id}/script/approve")
    def approve_script(video_id: str, body: ScriptApproveIn):
        def go(uc):
            ed = editorial(uc)
            if ed.approve_script is None:
                raise HTTPException(503, "script approval unavailable")
            approved_by = os.getenv("STUDIO_BROWSER_USER") or "painel"
            approval = ed.approve_script.execute(check_id(video_id), version=body.version,
                                                 content_hash=body.content_hash, approved_by=approved_by,
                                                 decision="approved", reason=body.reason)
            return {"version": approval.script_version, "content_hash": approval.content_hash,
                    "decision": approval.decision}
        return run(go)

    @router.post("/videos/{video_id}/fact-check", response_model=FactCheckReport)
    def fact_check(video_id: str, body: FactCheckIn):
        return run(lambda uc: editorial(uc).fact_check.execute(check_id(video_id), body.override_reason))

    @router.post("/ideas/score", response_model=IdeasOut)
    def score_ideas(body: IdeasIn):
        def go(uc):
            ed = editorial(uc)
            if ed.score_ideas is None:
                raise HTTPException(503, "idea scoring unavailable")
            project = check_id(body.project_id) if body.project_id else None
            return IdeasOut(ranked=[RankedOut(topic=r.topic, score=r.score, scores=r.scores)
                                    for r in ed.score_ideas.execute(body.topics, project)])
        return run(go)

    @router.post("/ideas/from-analytics", response_model=AnalyticsIdeasOut)
    def score_analytics_idea(body: AnalyticsIdeasIn):
        if body.end < body.start or (body.end - body.start).days > 6:
            raise HTTPException(422, "report interval must be at most seven days")

        def go(uc):
            video_id = check_id(body.video_id)
            video = uc.get_video.execute(video_id)
            if video is None:
                raise VideoNotFound(video_id)
            if uc.analytics is None:
                raise HTTPException(503, "analytics services unavailable")
            scorer = editorial(uc).score_ideas
            if scorer is None:
                raise HTTPException(503, "idea scoring unavailable")
            rows = uc.analytics.weekly(body.start, body.end)
            ranked = scorer.execute_analytics(rows, video_id, video.project_id)
            return AnalyticsIdeasOut(ranked=[
                AnalyticsRankedOut(topic=r.idea.topic, score=r.idea.score, scores=r.idea.scores,
                                   note=r.note, evidence=r.evidence) for r in ranked
            ])
        return run(go)

    def media(uc: UseCases):
        if uc.media is None:
            raise HTTPException(503, "media services unavailable")
        return uc.media

    @router.post("/videos/{video_id}/storyboard")
    def storyboard(video_id: str):
        run(lambda uc: media(uc).storyboard.execute(check_id(video_id)))
        return {"ok": True, "status": VideoStatus.STORYBOARDED.value}

    @router.post("/videos/{video_id}/assets", response_model=ProduceOut)
    def produce_assets(video_id: str):
        result = run(lambda uc: media(uc).produce.execute(check_id(video_id)))
        return ProduceOut(generated=result.generated, reused=result.reused)

    @router.get("/videos/{video_id}/assets", response_model=AssetsOut)
    def list_assets(video_id: str):
        listed = run(lambda uc: media(uc).list_assets.execute(check_id(video_id)))
        return AssetsOut(scenes=[SceneAssetOut(idx=x.idx, asset=x.asset) for x in listed])

    def scene_candidates(uc: UseCases):
        if uc.media is None or uc.media.list_candidates is None:
            raise HTTPException(503, "media search unavailable")
        return uc.media.list_candidates

    def scene_swap(uc: UseCases):
        if uc.media is None or uc.media.swap is None:
            raise HTTPException(503, "media swap unavailable")
        return uc.media.swap

    @router.get("/videos/{video_id}/scenes/{scene_id}/media/candidates", response_model=SceneCandidatesOut)
    def list_scene_candidates(video_id: str, scene_id: str):
        found = run(lambda uc: scene_candidates(uc).execute(check_id(video_id), check_id(scene_id)))
        return SceneCandidatesOut(scene_id=found.scene_id, query=found.query,
                                  candidates=[_candidate_out(c) for c in found.candidates])

    @router.post("/videos/{video_id}/scenes/{scene_id}/media", response_model=SceneMediaOut)
    def swap_scene_media(video_id: str, scene_id: str, body: SceneMediaChoiceIn):
        def go(uc: UseCases):
            try:
                candidate = MediaCandidate(**body.candidate.model_dump()) if body.candidate is not None else None
            except ValueError as exc:
                # candidato inválido (licença/proveniência em branco): erro de negócio, nunca 500
                raise SceneMediaRefused(f"invalid media candidate: {exc}") from exc
            return scene_swap(uc).execute(
                check_id(video_id), check_id(scene_id),
                asset_id=check_id(body.asset_id) if body.asset_id else None,
                candidate=candidate,
                expected_asset_id=check_id(body.expected_asset_id) if body.expected_asset_id else None,
                expected_version=body.expected_version)

        result = run(go)
        return SceneMediaOut(scene_id=result.scene_id, asset=result.asset, changed=result.changed, reason=result.reason)

    def rendering(uc: UseCases):
        if uc.rendering is None:
            raise HTTPException(503, "render services unavailable")
        return uc.rendering

    def scene_narration(uc: UseCases):
        if uc.editorial is None or uc.editorial.scene_narration is None:
            raise HTTPException(503, "scene narration unavailable")
        return uc.editorial.scene_narration

    def regenerate_narration(uc: UseCases):
        if uc.editorial is None or uc.editorial.regenerate_narration is None:
            raise HTTPException(503, "scene narration unavailable")
        return uc.editorial.regenerate_narration

    @router.post("/videos/{video_id}/render", status_code=202, response_model=RenderJob)
    def start_render(video_id: str):
        return run(lambda uc: rendering(uc).start.execute(check_id(video_id)))

    @router.post("/videos/{video_id}/resume", status_code=202, response_model=RenderJob)
    def resume_video(video_id: str):
        def resume(uc):
            if uc.resume is None:
                raise HTTPException(503, "recovery services unavailable")
            return uc.resume.execute(check_id(video_id))
        return run(resume)

    @router.post("/analytics/metrics", status_code=204)
    def upsert_metric(body: DailyMetric):
        def upsert(uc):
            if uc.analytics is None:
                raise HTTPException(503, "analytics services unavailable")
            if uc.get_video.execute(body.video_id) is None:
                raise VideoNotFound(body.video_id)
            uc.analytics.upsert(body)
        run(upsert)
        return Response(status_code=204)

    @router.get("/analytics/weekly")
    def weekly_analytics(start: date, end: date):
        if end < start or (end - start).days > 6:
            raise HTTPException(422, "report interval must be at most seven days")
        def weekly(uc):
            if uc.analytics is None:
                raise HTTPException(503, "analytics services unavailable")
            return uc.analytics.weekly(start, end)
        return run(weekly)

    @router.post("/trends", status_code=202)
    def ingest_trends(body: TrendsIn, request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(403, "worker authentication required")
        def ingest(uc):
            if uc.ingest_trends is None:
                raise HTTPException(503, "trends services unavailable")
            return {"stored": uc.ingest_trends.execute(check_id(body.project_id), body.items)}
        return run(ingest)

    @router.get("/panel/data")
    def panel_data(days: int = 7, project_id: str | None = None):
        def get_data(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = check_id(project_id) if project_id else None
            return uc.panel.execute(days=days, project_id=p_id)
        return run(get_data)

    @router.get("/panel/videos/{video_id}/data")
    def panel_video_detail_data(video_id: str):
        def get_detail(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            return uc.panel.detail(check_id(video_id))
        return run(get_detail)

    @router.get("/panel", response_class=HTMLResponse)
    def panel_html(days: int = 7, project_id: str | None = None, topic: str = ""):
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = _active_channel(uc, project_id)
            view = uc.panel.execute(days=days, project_id=p_id)
            # `topic` pré-preenche o tema (vindo de "Criar Vídeo deste Tema" na tela Tendências).
            return render_panel(view, topic=(topic or "")[:300])
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    # IA-01: Início/Produção/Tendências são telas separadas (rotas reais), não âncoras de uma só.
    @router.get("/panel/producao", response_class=HTMLResponse)
    def panel_producao_html(days: int = 7, project_id: str | None = None):
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = _active_channel(uc, project_id)
            return render_production_page(uc.panel.execute(days=days, project_id=p_id))
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/tendencias", response_class=HTMLResponse)
    def panel_tendencias_html(days: int = 7, project_id: str | None = None,
                              filtro: str = "todas"):
        """O filtro vem da URL (link compartilhável); a lista cresce por scroll infinito."""
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = _active_channel(uc, project_id)
            return render_tendencias_v3(uc.panel.execute(days=days, project_id=p_id), filtro=filtro)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/tendencias/cartoes", response_class=HTMLResponse)
    def panel_tendencias_cartoes_html(days: int = 7, project_id: str | None = None,
                                      filtro: str = "todas", offset: int = 0,
                                      limite: int = 24):
        """Próximo lote do scroll infinito (fragmento HTML, sem casca).

        É aditivo: a página completa continua sendo a fonte da verdade e o botão
        "Carregar mais" usa este mesmo caminho quando o observer não dispara.
        """
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = _active_channel(uc, project_id)
            return render_tendencias_cartoes(uc.panel.execute(days=days, project_id=p_id),
                                             filtro=filtro, offset=offset, limite=limite)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/videos", response_class=HTMLResponse)
    def panel_videos_html(project_id: str | None = None, days: int = 7):
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = _active_channel(uc, project_id)
            return render_videos(uc.panel.execute(days=days, project_id=p_id))
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    # UX-02: Configurações como área de rotas reais. Cada seção leva à tela que já existe; a
    # tela continua sendo a rota canônica (seus formulários publicam nela), sem duplicar página.
    # W1.5: sete seções, com os rótulos do protótipo. `estrategia`, `marca` e `producao` passaram a
    # ter **página própria** (`panel_settings`), que reusa os cartões da tela de Canais — mesmo
    # formulário, mesmo endpoint. `estilos` e `identidade` continuam aceitos como apelidos antigos.
    _SETTINGS_SECTIONS = {
        "canais": "/studio/canais",
        "estrategia": "/studio/configuracoes/estrategia",
        "marca": "/studio/configuracoes/marca",
        "producao": "/studio/configuracoes/producao",
        "conexoes": "/studio/panel/conexoes",
        "equipe": "/studio/panel/equipe",
        "avancado": "/studio/panel/avancado",
        # apelidos legados (não aparecem no menu): o endereço antigo não pode virar 404.
        "estilos": "/studio/panel/estilos",
        "identidade": "/studio/configuracoes/marca",
    }

    @router.get("/configuracoes")
    def settings_root_redirect(project_id: str | None = None):
        # F02.T01/G11: o redirect não pode trocar o canal ativo.
        # A primeira aba de Configurações é a lista de canais (`pgSettings` → Canais).
        target = _with_channel("/studio/configuracoes/canais", project_id)
        return RedirectResponse(url=target, status_code=302)

    @router.get("/configuracoes/{section}")
    def settings_section_redirect(section: str, project_id: str | None = None):
        if section == "canais":
            def channel_list(uc):
                if uc.channels_page is None:
                    raise HTTPException(503, "channel services unavailable")
                view = uc.channels_page.execute(_active_channel(uc, project_id))
                profiles = {}
                for pid, _name in view.projects:
                    try:
                        profiles[pid] = uc.channels_page.get_profile.execute(pid)
                    except Exception:  # canal sem perfil legível: o cartão diz isso em vez de inventar
                        profiles[pid] = None
                return panel_settings.render_channel_list(view, profiles)
            page, headers = run(channel_list)
            return HTMLResponse(page, headers=headers)
        if section in panel_settings.SECTIONS:
            def get_page(uc):
                if uc.channels_page is None:
                    raise HTTPException(503, "channel services unavailable")
                _, p_id = _topbar(uc, project_id)
                view = uc.channels_page.execute(p_id)
                style_view = None
                if uc.channel_style_page is not None and view.profile is not None:
                    style_view = uc.channel_style_page.execute(view.profile.id)
                return panel_settings.render_settings_section(section, view, channel_style=style_view)
            page, headers = run(get_page)
            return HTMLResponse(page, headers=headers)
        target = _SETTINGS_SECTIONS.get(section)
        if target is None:
            raise HTTPException(404, "unknown settings section")
        return RedirectResponse(url=_with_channel(target, project_id), status_code=302)

    @router.get("/panel/avancado", response_class=HTMLResponse)
    def panel_advanced_html(project_id: str | None = None):
        """F02.T03: diagnóstico read-only do Estúdio (saúde, providers, configuração efetiva)."""
        def get_page(uc):
            if uc.advanced_page is None:
                raise HTTPException(503, "diagnostic services unavailable")
            _, p_id = _topbar(uc, project_id)
            view = uc.advanced_page.execute(p_id, database_ok=bool(ping()))
            return render_advanced(view)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/equipe", response_class=HTMLResponse)
    def panel_team_html(org_id: str | None = None, project_id: str | None = None):
        def get_page(uc):
            if uc.team_view is None:
                raise HTTPException(503, "team services unavailable")
            view = uc.team_view.execute(org_id=org_id)
            month = uc.panel.month_cost() if uc.panel is not None else None
            projects, p_id = _topbar(uc, project_id)
            return render_team(view, month=month, projects=projects, project_id=p_id or "")
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    # -- L2: mutações de Equipe. O ator é o operador autenticado do painel (Basic auth), resolvido
    # no vínculo dele com a organização; o papel do vínculo aplica o RBAC do domínio. Nenhuma
    # resposta devolve valor de chave — só máscara, impressão e metadados. --
    def _team_services(uc: UseCases, *names: str):
        for name in names:
            if getattr(uc, name) is None:
                raise HTTPException(503, "team services unavailable")
        if uc.resolve_actor is None:
            raise HTTPException(503, "team services unavailable")

    def _team_actor(uc: UseCases, organization_id: str):
        return uc.resolve_actor.execute(organization_id=organization_id,
                                        principal=os.getenv("STUDIO_BROWSER_USER", "").strip())

    @router.post("/panel/equipe/members", status_code=201, response_model=MemberOut)
    def invite_team_member(body: TeamMemberIn):
        def go(uc):
            _team_services(uc, "invite_member")
            actor = _team_actor(uc, body.organization_id)
            member = uc.invite_member.execute(actor_role=actor.role, organization_id=body.organization_id,
                                              email=body.email, role=body.role, display_name=body.display_name,
                                              actor_user_id=actor.user_id)
            return _member_out(member)
        return run(go)

    @router.patch("/panel/equipe/members/{membership_id}", response_model=MemberOut)
    def change_team_member_role(membership_id: str, body: TeamMemberRoleIn):
        def go(uc):
            _team_services(uc, "change_member_role")
            actor = _team_actor(uc, body.organization_id)
            member = uc.change_member_role.execute(actor_role=actor.role, organization_id=body.organization_id,
                                                   membership_id=membership_id, role=body.role,
                                                   actor_user_id=actor.user_id)
            return _member_out(member)
        return run(go)

    @router.delete("/panel/equipe/members/{membership_id}", response_model=MemberOut)
    def remove_team_member(membership_id: str, organization_id: str):
        def go(uc):
            _team_services(uc, "remove_member")
            actor = _team_actor(uc, organization_id)
            member = uc.remove_member.execute(actor_role=actor.role, organization_id=organization_id,
                                              membership_id=membership_id, actor_user_id=actor.user_id)
            return _member_out(member)
        return run(go)

    @router.post("/panel/equipe/keys", status_code=201, response_model=KeyOut)
    def register_team_key(body: ByokKeyIn):
        def go(uc):
            _team_services(uc, "register_byok_key")
            actor = _team_actor(uc, body.organization_id)
            key = uc.register_byok_key.execute(actor_role=actor.role, organization_id=body.organization_id,
                                               provider=body.provider, value=body.value,
                                               actor_user_id=actor.user_id)
            return _key_out(key)
        return run(go)

    @router.post("/panel/equipe/keys/{key_id}/rotate", response_model=KeyOut)
    def rotate_team_key(key_id: str, body: ByokRotateIn):
        def go(uc):
            _team_services(uc, "rotate_byok_key")
            actor = _team_actor(uc, body.organization_id)
            key = uc.rotate_byok_key.execute(actor_role=actor.role, organization_id=body.organization_id,
                                             key_id=key_id, value=body.value, actor_user_id=actor.user_id)
            return _key_out(key)
        return run(go)

    @router.delete("/panel/equipe/keys/{key_id}", response_model=KeyOut)
    def revoke_team_key(key_id: str, organization_id: str):
        def go(uc):
            _team_services(uc, "revoke_byok_key")
            actor = _team_actor(uc, organization_id)
            key = uc.revoke_byok_key.execute(actor_role=actor.role, organization_id=organization_id,
                                             key_id=key_id, actor_user_id=actor.user_id)
            return _key_out(key)
        return run(go)

    @router.get("/panel/videos/{video_id}", response_class=HTMLResponse)
    def panel_video_detail_html(video_id: str):
        def get_detail_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            detail = uc.panel.detail(check_id(video_id))
            style_view = (uc.video_style_view.execute(check_id(video_id))
                          if uc.video_style_view is not None else None)
            return render_video(detail, style_view=style_view,
                                video_channel=_channel_name(uc, detail.video.project_id),
                                free_providers=uc.panel.free_providers)
        page, headers = run(get_detail_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/videos/{video_id}/{area}", response_class=HTMLResponse)
    def panel_video_area_html(video_id: str, area: str):
        """W1.4 (UX-03): as áreas do vídeo como **rotas**, com links e `aria-current="page"`.

        Cada área é uma leitura sobre o que o core já tem (nada de SPA nem segundo coordenador);
        o gate de aprovação continua na prévia e a produção nas rotas de execução. Área desconhecida
        cai na Visão geral. As rotas antigas (`/panel/videos/{id}`, `/roteiro`, `/preview`,
        `production-runs`) continuam valendo.
        """
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            detail = uc.panel.detail(check_id(video_id))
            style_view = (uc.video_style_view.execute(check_id(video_id))
                          if uc.video_style_view is not None else None)
            script_view = (uc.script_view.execute(check_id(video_id))
                           if uc.script_view is not None else None)
            # W2.3: a aba Composição lê o plano persistido (última revisão) pela porta; as
            # outras áreas não pagam a consulta.
            composition_view = None
            if area == "composicao" and uc.composition_view is not None:
                composition_view = uc.composition_view.execute(check_id(video_id))
            # W5.1 (PUB-01): a aba Publicação renderiza o formulário de aprovação da prévia.
            preview = (uc.publishing.preview.execute(check_id(video_id))
                       if area == "publicacao" and uc.publishing is not None else None)
            scenes = None
            script = None
            if uc.editorial is not None and getattr(uc.editorial, "get_script", None) is not None:
                try:
                    found = uc.editorial.get_script.execute(check_id(video_id))
                    if found:
                        script, scenes = found[0], list(found[1])
                except Exception:
                    scenes = None
            return render_video_workspace(detail, area, style_view=style_view,
                                          script_view=script_view,
                                          composition_view=composition_view,
                                          preview=preview,
                                          scenes=scenes,
                                          script=script,
                                          projects=_topbar(uc, detail.video.project_id)[0],
                                          project_id=detail.video.project_id,
                                          channel_voice=_channel_voice(uc, detail.video.project_id),
                                          channel_name=_channel_name(uc, detail.video.project_id))
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/canais/novo", response_class=HTMLResponse)
    def new_channel_page_html(project_id: str | None = None):
        from .panel_channel_create import render_channel_create
        def get_page(uc):
            if uc.channels_page is None:
                raise HTTPException(503, "channel services unavailable")
            return render_channel_create(uc.channels_page.execute(_active_channel(uc, project_id)))
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/canais", response_class=HTMLResponse)
    def channels_page_html(project_id: str | None = None):
        def get_page(uc):
            if uc.channels_page is None:
                raise HTTPException(503, "channel services unavailable")
            view = uc.channels_page.execute(_active_channel(uc, project_id))
            style_view = None
            if uc.channel_style_page is not None and view.profile is not None:
                style_view = uc.channel_style_page.execute(view.profile.id)
            return render_channels(view, channel_style=style_view)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/oauth/callback", response_class=HTMLResponse)
    def oauth_callback_page(state: str = "", error: str = ""):
        """Retorno do Google: o `state` carrega o projeto; a página conclui o consentimento.

        O `code` chega na query string e é lido pelo browser na própria página; o servidor não o
        precisa para renderizar e não o grava em lugar nenhum. Sem `state` reconhecido, a página
        explica que a conexão precisa ser refeita — não é um beco sem saída.
        """
        project_id = consent_project_id(state) if state else None
        page, headers = render_oauth_callback(project_id, provider_error=error or None)
        return HTMLResponse(page, headers=headers)

    # -- analytics e loop de aprendizado (F9-01/02/03/05/06) ----------------------------

    @router.get("/panel/analytics", response_class=HTMLResponse)
    def panel_analytics_html(project: str | None = None, video: str | None = None,
                             pillar: str | None = None, days: int = 7):
        period = _analytics_period(days)

        def get_page(uc):
            if uc.analytics_repo is None or uc.analytics_dashboard is None:
                raise HTTPException(503, "analytics services unavailable")
            project_id = check_id(project) if project else None
            video_id = check_id(video) if video else None
            pillar_id = check_id(pillar) if pillar else None
            chosen = project_id
            if chosen is None:
                projects = uc.analytics_repo.projects()
                if not projects:
                    raise ProjectNotFound("no project registered")
                chosen = projects[0][0]
            view = uc.analytics_dashboard.execute(DashboardQuery(
                project_id=chosen, video_id=video_id, pillar_id=pillar_id, period=period))
            month = uc.panel.month_cost() if uc.panel is not None else None
            return render_analytics(view, month)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.post("/panel/analytics/recommendations/{recommendation_id}/decision")
    def decide_recommendation(recommendation_id: str, body: AnalyticsDecisionIn):
        def decide(uc):
            if uc.analytics_decide is None:
                raise HTTPException(503, "analytics services unavailable")
            record = uc.analytics_decide.execute(check_id(body.project_id),
                                                 check_id(recommendation_id),
                                                 body.decision, _operator())
            return {"recommendation_id": record.recommendation_id, "decision": record.decision,
                    "applied": False,
                    "message": "registro de revisão; nenhuma configuração do canal foi alterada"}
        return run(decide)

    @router.post("/analytics/collect")
    def collect_analytics(body: AnalyticsCollectIn):
        period = _analytics_period(body.days)

        def collect(uc):
            if uc.analytics_collection is None:
                raise HTTPException(503, "analytics services unavailable")
            outcome = uc.analytics_collection.execute(CollectionRequest(
                video_id=check_id(body.video_id), period=period,
                pillar_id=check_id(body.pillar_id) if body.pillar_id else None))
            return {
                "collected": outcome.collected,
                "saved": outcome.saved,
                "reason": outcome.reason,
                "readiness": {
                    "ready": outcome.readiness.is_ready,
                    "scope": outcome.readiness.scope,
                    "channel_connected": outcome.readiness.channel_connected,
                    "scope_granted": outcome.readiness.scope_granted,
                    "publication_available": outcome.readiness.publication_available,
                    "reasons": list(outcome.readiness.reasons),
                },
            }
        return run(collect)

    @router.post("/analytics/experiments", status_code=201)
    def register_experiment(body: ExperimentIn):
        if (body.window_start is None) != (body.window_end is None):
            raise HTTPException(422, "window_start and window_end must be provided together")
        try:
            window = (MetricWindow(start_at=body.window_start, end_at=body.window_end)
                      if body.window_start is not None else None)
        except ValidationError:
            raise HTTPException(422, "invalid experiment window") from None
        variants = tuple(ExperimentVariant(variant_id=item.variant_id, label=item.label,
                                           is_control=item.is_control) for item in body.variants)
        operator = _operator()

        def register(uc):
            if uc.analytics_register_experiment is None:
                raise HTTPException(503, "analytics services unavailable")
            project_id, video_id = check_id(body.project_id), check_id(body.video_id)
            conclusion = conclusion_from(
                statement=body.conclusion, level=body.conclusion_confidence,
                basis=body.conclusion_basis,
                observation_ids=[check_id(item) for item in body.conclusion_observation_ids],
                declared_by=operator)
            try:
                record = uc.analytics_register_experiment.execute(
                    project_id=project_id, video_id=video_id, kind=body.kind,
                    status=body.status, variants=variants, approved_by=operator,
                    window=window, conclusion=conclusion)
            except ValidationError:
                raise HTTPException(422, "invalid experiment") from None
            return {"experiment_id": record.experiment_id, "applied": False,
                    "message": "histórico de rotação manual; nenhum A/B de plataforma foi declarado"}
        return run(register)

    @router.get("/videos/{video_id}/render", response_model=RenderStatusOut)
    def render_status(video_id: str):
        job, qa = run(lambda uc: rendering(uc).get.execute(check_id(video_id)))
        return RenderStatusOut(job=job, qa_report=qa)

    def served(video_id: str, kind: str, media_type: str, filename: str, output_asset_id: str | None = None):
        path = run(lambda uc: rendering(uc).file.execute(check_id(video_id), kind, check_id(output_asset_id) if output_asset_id else None))
        if path is None:
            raise HTTPException(404, "rendered file not available")
        return FileResponse(path, media_type=media_type, filename=filename)

    @router.get("/videos/{video_id}/file")
    def video_file(video_id: str, output_asset_id: str | None = None):
        return served(video_id, "mp4", "video/mp4", f"{video_id}.mp4", output_asset_id)

    @router.get("/videos/{video_id}/subtitles")
    def video_subtitles(video_id: str):
        return served(video_id, "srt", "text/plain; charset=utf-8", f"{video_id}.srt")

    @router.get("/videos/{video_id}/subtitles.vtt")
    def video_subtitles_vtt(video_id: str):
        path = run(lambda uc: rendering(uc).file.execute(check_id(video_id), "srt"))
        if path is None:
            raise HTTPException(404, "rendered file not available")
        return PlainTextResponse(srt_to_vtt(path.read_text(encoding="utf-8")), media_type="text/vtt; charset=utf-8")

    def _narration_out(video_id: str, scene_id: str, artifact) -> SceneNarrationOut:
        return SceneNarrationOut(
            video_id=artifact.video_id, scene_id=artifact.scene_id,
            duration_s=artifact.duration_s, sha256=artifact.sha256,
            voice_id=artifact.voice_id,
            audio_url=f"/studio/videos/{video_id}/scenes/{scene_id}/narration.wav")

    @router.get("/videos/{video_id}/scenes/{scene_id}/narration", response_model=SceneNarrationOut)
    def scene_narration_status(video_id: str, scene_id: str):
        artifact = run(lambda uc: scene_narration(uc).find(check_id(video_id), check_id(scene_id)))
        if artifact is None:
            raise HTTPException(404, "scene narration not available")
        return _narration_out(video_id, scene_id, artifact)

    @router.get("/videos/{video_id}/scenes/{scene_id}/narration.wav")
    def scene_narration_file(video_id: str, scene_id: str):
        artifact = run(lambda uc: scene_narration(uc).find(check_id(video_id), check_id(scene_id)))
        if artifact is None:
            raise HTTPException(404, "scene narration not available")
        return FileResponse(artifact.path, media_type="audio/wav", filename=f"{scene_id}.wav")

    @router.post("/videos/{video_id}/scenes/{scene_id}/narration/regenerate", response_model=SceneNarrationOut)
    def regenerate_scene_narration(video_id: str, scene_id: str):
        artifact = run(lambda uc: regenerate_narration(uc).execute(check_id(video_id), check_id(scene_id)))
        return _narration_out(video_id, scene_id, artifact)

    def publishing(uc: UseCases):
        if uc.publishing is None:
            raise HTTPException(503, "publishing services unavailable")
        return uc.publishing

    @router.post("/videos/{video_id}/approve", response_model=DecisionOut)
    def approve(video_id: str, body: ApproveIn | None = None):
        body = body or ApproveIn()
        video, changed = run(lambda uc: publishing(uc).approve.execute(
            check_id(video_id), title=body.title, description=body.description, tags=body.tags, publish_at=body.publish_at,
            override_reason=body.override_reason, output_asset_id=check_id(body.output_asset_id) if body.output_asset_id else None,
            visibility=body.visibility, confirm_public=body.confirm_publication))
        return DecisionOut(video=video, changed=changed)

    @router.post("/videos/{video_id}/reject", response_model=DecisionOut)
    def reject(video_id: str, body: RejectIn | None = None):
        video, changed = run(lambda uc: publishing(uc).reject.execute(check_id(video_id), (body or RejectIn()).reason))
        return DecisionOut(video=video, changed=changed)

    @router.get("/videos/{video_id}/preview", response_class=HTMLResponse)
    def preview(video_id: str):
        page, headers = render_preview(
            run(lambda uc: publishing(uc).preview.execute(check_id(video_id))),
            video_channel=run(lambda uc: _video_channel_name(uc, video_id)))
        return HTMLResponse(page, headers=headers)

    @router.get("/videos/{video_id}/thumbnail")
    def thumbnail(video_id: str):
        data = run(lambda uc: publishing(uc).thumbnail.execute(check_id(video_id)))
        if data is None:
            raise HTTPException(404, "thumbnail not available")
        return Response(data, media_type="image/jpeg")

    @router.get("/videos/{video_id}/publication", response_model=Publication | None, response_model_exclude={"upload_uri"})
    def get_publication(video_id: str):
        return run(lambda uc: publishing(uc).get.execute(check_id(video_id)))

    @router.post("/videos/{video_id}/publication/retry", response_model=Publication, response_model_exclude={"upload_uri"})
    def retry_publication(video_id: str):
        return run(lambda uc: publishing(uc).retry.execute(check_id(video_id)))

    @router.post("/publications/execute", response_model=PublicationRunOut,
                 response_model_exclude={"publication": {"upload_uri"}})
    def execute_publication(body: PublishIn | None = None):
        """F01.T02/W5.2: executa a publicação no Core (claim + token do grant + upload + settle).

        É este o **caminho efetivo** de upload: o workflow n8n `workflows/03-publish-approved.json`
        está **inativo** (`"active": false`) e, quando reativado, só orquestra — não carrega
        credencial do YouTube nem faz PUT. Devolve IDLE quando não há nada devido e nunca presume
        sucesso de resultado ambíguo (idempotência do retry em `application/publication_execution.py`).
        """
        body = body or PublishIn()

        def go(uc):
            executor = publishing(uc).publish
            if executor is None:
                raise HTTPException(503, "publication executor unavailable")
            outcome = executor.execute(body.lease_seconds, body.max_attempts)
            return PublicationRunOut(result=outcome.result.value, publication=outcome.publication,
                                     youtube_video_id=outcome.youtube_video_id, detail=outcome.detail)
        return run(go)

    @router.post("/publications/claim", response_model=ClaimResult)
    def claim(body: ClaimIn | None = None):
        # W5.2 — achado registrado, NÃO corrigido aqui: este é o caminho legado que servia o workflow
        # n8n. Ele entrega arquivo + `youtube_body` ao chamador e **não** passa pelo gate de identidade
        # do canal (`verify_publication_gate`), enquanto `/publications/execute` passa. Como o workflow
        # `03-publish-approved.json` está inativo ("active": false) e não faz upload, o caminho não
        # está exposto; se for reativado, precisa entrar no gate. Não se "conserta" o n8n nesta tarefa.
        item = run(lambda uc: publishing(uc).claim.execute((body or ClaimIn()).lease_seconds))
        return ClaimResult(item=None if item is None else ClaimOut(
            publication=item.publication, youtube_body=item.youtube_body, file_size=item.file_size, content_type=item.content_type,
            file_path=item.file_path, thumbnail_path=item.thumbnail_path))

    @router.post("/publications/{publication_id}/upload-uri", response_model=Publication, response_model_exclude={"upload_uri"})
    def set_upload_uri(publication_id: str, body: UploadUriIn):
        return run(lambda uc: publishing(uc).set_uri.execute(check_id(publication_id), body.attempt, body.upload_uri, body.replace))

    @router.post("/publications/{publication_id}/uploaded", response_model=Publication, response_model_exclude={"upload_uri"})
    def uploaded(publication_id: str, body: UploadedIn):
        return run(lambda uc: publishing(uc).uploaded.execute(check_id(publication_id), body.youtube_video_id))

    @router.post("/publications/{publication_id}/failed", response_model=Publication, response_model_exclude={"upload_uri"})
    def failed(publication_id: str, body: FailedIn):
        return run(lambda uc: publishing(uc).failed.execute(check_id(publication_id), body.attempt, body.error, body.retryable))

    @router.post("/publications/{publication_id}/thumbnail-set", response_model=Publication, response_model_exclude={"upload_uri"})
    def thumbnail_set(publication_id: str):
        return run(lambda uc: publishing(uc).thumbnail_set.execute(check_id(publication_id)))

    @router.post("/videos/{video_id}/publication/publish", response_model=PublicationRunOut,
                 response_model_exclude={"publication": {"upload_uri"}})
    def publish_publication(video_id: str, body: PublishIn | None = None):
        """Executa um passo do caminho nativo de publicação (F8) para ESTE vídeo."""
        body = body or PublishIn()

        def go(uc):
            executor = publishing(uc).publish
            if executor is None:
                raise HTTPException(503, "publication executor unavailable")
            outcome = executor.execute(body.lease_seconds, body.max_attempts, video_id=check_id(video_id))
            return PublicationRunOut(result=outcome.result.value, publication=outcome.publication,
                                     youtube_video_id=outcome.youtube_video_id, detail=outcome.detail)
        return run(go)

    @router.post("/publications/{publication_id}/reconcile", response_model=PublicationRunOut,
                 response_model_exclude={"publication": {"upload_uri"}})
    def reconcile_publication(publication_id: str):
        """Reconcilia um resultado externo desconhecido; nunca presume sucesso."""
        uuid = check_id(publication_id)
        def go(uc):
            service = publishing(uc).reconcile
            if service is None:
                raise HTTPException(503, "publication reconciliation unavailable")
            outcome = service.execute(uuid)
            return PublicationRunOut(result=outcome.result.value, publication=outcome.publication,
                                     youtube_video_id=outcome.youtube_video_id, detail=outcome.detail)
        return run(go)

    # -- produção (D2): iniciar, acompanhar e agir por estado -------------------

    def production_service(uc: UseCases):
        if uc.production is None:
            raise HTTPException(503, "production services unavailable")
        return uc.production

    def _stage(value: str) -> ProductionStage:
        try:
            return ProductionStage(value)
        except ValueError:
            raise HTTPException(422, f"unknown production stage {value!r}") from None

    def _owned(uc: UseCases, video_id: str, run_id: str):
        projection = production_service(uc).coordinator.get(check_id(run_id))
        if projection is None or projection.run.video_id != check_id(video_id):
            raise HTTPException(404, "production run not found")
        return projection

    def _view(projection, events) -> ProductionRunViewOut:
        return ProductionRunViewOut(
            run_id=projection.run.run_id, video_id=projection.run.video_id, state=projection.run.state.value,
            mode=projection.mode.value, channel_id=projection.run.channel_id,
            next_action=projection.next_action, next_stage=projection.next_stage.value if projection.next_stage else None,
            stages=[ProductionStageStateOut(stage=e.stage_id.value, state=e.state.value, attempt=e.attempt,
                                            fencing_token=e.fencing_token,
                                            checkpoint_version=e.checkpoint.version if e.checkpoint else None,
                                            error=e.error, updated_at=e.updated_at) for e in projection.stages],
            available_stages=[stage.value for stage in projection.available_stages],
            unavailable_stages=[{"stage": stage.value, "reason": reason} for stage, reason in projection.unavailable_stages],
            events=[ProductionEventOut(id=event.id, event_type=event.event_type.value, event_version=event.event_version,
                                       stage_id=event.stage_id.value if event.stage_id else None, payload=event.payload,
                                       created_at=event.created_at) for event in events])

    @router.post("/videos/{video_id}/production-runs", status_code=202, response_model=ProductionRunStartOut)
    def start_production_run(video_id: str, body: ProductionRunIn | None = None, request: Request = None):
        body = body or ProductionRunIn()
        key = request.headers.get("idempotency-key") or body.idempotency_key
        if not key:
            raise HTTPException(400, "an Idempotency-Key header (or idempotency_key field) is required")

        def go(uc):
            service = production_service(uc)
            stages = [_stage(item) for item in body.stages] if body.stages is not None else None
            creation = service.start(check_id(video_id), key,
                                     channel_id=check_id(body.channel_id) if body.channel_id else None, stages=stages)
            return ProductionRunStartOut(run_id=creation.run.run_id, state=creation.run.state.value,
                                         mode=service.coordinator.mode.value,
                                         created=creation.result.value == "CREATED")
        return run(go)

    @router.get("/videos/{video_id}/production-runs/{run_id}", response_model=ProductionRunViewOut)
    def get_production_run(video_id: str, run_id: str):
        def go(uc):
            projection = _owned(uc, video_id, run_id)
            return _view(projection, production_service(uc).coordinator.events(check_id(run_id)))
        return run(go)

    @router.post("/videos/{video_id}/production-runs/{run_id}/pause")
    def pause_production_run(video_id: str, run_id: str, body: ProductionActionIn | None = None):
        def go(uc):
            _owned(uc, video_id, run_id)
            reason = (body.reason if body and body.reason else "pausado pelo operador").strip()
            transition = production_service(uc).coordinator.pause(check_id(run_id), reason)
            if transition.result is not RunTransitionResult.APPLIED:
                raise HTTPException(409, "the production run cannot be paused in its current state")
            return {"run_id": run_id, "state": transition.run.state.value}
        return run(go)

    @router.post("/videos/{video_id}/production-runs/{run_id}/resume")
    def resume_production_run(video_id: str, run_id: str, body: ProductionResumeIn | None = None):
        def go(uc):
            projection = _owned(uc, video_id, run_id)
            expected = (body.expected_state if body else None) or projection.run.state
            transition = production_service(uc).resume(check_id(run_id), expected_state=expected)
            if transition.result is not RunTransitionResult.APPLIED:
                raise HTTPException(409, "the production run cannot be resumed from this state")
            return {"run_id": run_id, "state": transition.run.state.value}
        return run(go)

    @router.post("/videos/{video_id}/production-runs/{run_id}/cancel")
    def cancel_production_run(video_id: str, run_id: str, body: ProductionActionIn | None = None):
        def go(uc):
            _owned(uc, video_id, run_id)
            reason = (body.reason if body and body.reason else "cancelado pelo operador").strip()
            transition = production_service(uc).coordinator.cancel(check_id(run_id), reason)
            if transition.result is not RunTransitionResult.APPLIED:
                raise HTTPException(409, "the production run cannot be cancelled in its current state")
            return {"run_id": run_id, "state": transition.run.state.value}
        return run(go)

    @router.post("/videos/{video_id}/production-runs/{run_id}/retry")
    def retry_production_run(video_id: str, run_id: str):
        def go(uc):
            _owned(uc, video_id, run_id)
            transition = production_service(uc).retry(check_id(run_id))
            if transition.result is not RunTransitionResult.APPLIED:
                raise HTTPException(409, "retry is available only for a FAILED production run")
            return {"run_id": run_id, "state": transition.run.state.value}
        return run(go)

    # -- páginas do fluxo único (F2-02..F2-05): wizard e execução ----------------

    def _wizard_pipeline(uc: UseCases) -> tuple[PipelineStage, ...]:
        coordinator = production_service(uc).coordinator
        available = set(coordinator.available_stages())
        reasons = dict(coordinator.unavailable_stages())
        pipeline = []
        for stage in ProductionStage:
            label = STAGE_LABELS.get(stage, stage.value)
            if stage in available:
                pipeline.append(PipelineStage(stage, label, True))
            elif stage in reasons:
                pipeline.append(PipelineStage(stage, label, False, reasons[stage]))
        return tuple(pipeline)

    @router.post("/videos/{video_id}/production-runs/{run_id}/regenerate", status_code=202,
                 response_model=ProductionRunStartOut)
    def regenerate_production_run(video_id: str, run_id: str, body: ProductionRegenerateIn | None = None):
        """F03.T04: execução **nova** a partir de um run existente (nunca resume disfarçado)."""
        body = body or ProductionRegenerateIn()

        def go(uc):
            _owned(uc, video_id, run_id)
            creation = production_service(uc).regenerate(check_id(run_id), revision=body.revision,
                                                        reason=(body.reason or "").strip() or None)
            return ProductionRunStartOut(run_id=creation.run.run_id, state=creation.run.state.value,
                                         mode=uc.production.coordinator.mode.value,
                                         created=creation.result is CreateRunResult.CREATED)
        return run(go)

    @router.get("/panel/novo-video", response_class=HTMLResponse)
    def panel_new_video_html(project_id: str | None = None):
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            if uc.production is None:
                raise HTTPException(503, "production services unavailable")
            # Sem `project_id` a tela usa o primeiro canal — o mesmo que a topbar mostra. Sem
            # isso a predefinição dizia "canal sem perfil" enquanto o canal real estava ativo.
            _, p_id = _topbar(uc, project_id)
            p_id = p_id or ""
            # F02.T02/G15: estilos reais da biblioteca + o nome que o canal selecionado herda.
            styles: list[tuple[str, str]] = []
            inherited = None
            channel_language = None
            channel_voice = None
            channel_profile = None
            has_profile = False
            if uc.list_visual_styles is not None:
                styles = [(s.id, s.name) for s in uc.list_visual_styles.execute()]
            if p_id and uc.get_channel_profile is not None:
                profile = uc.get_channel_profile.execute(p_id)
                if profile is not None:
                    has_profile = True
                    channel_profile = profile
                    channel_language, channel_voice = profile.language, profile.voice
                    if profile.style_id:
                        inherited = next((name for sid, name in styles if sid == profile.style_id), None)
            view = NewVideoView(
                projects=uc.panel.repo.projects(),
                month=uc.panel.month_cost(),
                pipeline=_wizard_pipeline(uc),
                selected_project_id=p_id,
                styles=tuple(styles),
                inherited_style_name=inherited,
                channel_language=channel_language,
                channel_voice=channel_voice,
                has_profile=has_profile,
                channel_profile=channel_profile,
            )
            return render_new_video_v3(view)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/videos/{video_id}/production-runs/{run_id}", response_class=HTMLResponse)
    def panel_production_run_html(video_id: str, run_id: str):
        def get_page(uc):
            if uc.panel is None or uc.production is None:
                raise HTTPException(503, "panel/production services unavailable")
            projection = _owned(uc, video_id, run_id)
            detail = uc.panel.detail(check_id(video_id))
            usage_rows = (
                [(u.provider, u.model, u.cost_usd, u.cost_confirmation_kind) for u in detail.usage]
                if detail.usage else detail.video.cost_rows
            )
            view = ExecutionView(
                topic=detail.video.topic,
                run=projection.run,
                stages=projection.stages,
                next_action=projection.next_action,
                next_stage=projection.next_stage,
                mode=projection.mode.value,
                month=uc.panel.month_cost(),
                unavailable_stages=projection.unavailable_stages,
                cost=cost_breakdown(usage_rows, uc.panel.free_providers),
                usage=tuple(detail.usage),
                events=tuple(production_service(uc).coordinator.events(check_id(run_id))),
            )
            return render_execution(view, video_channel=_channel_name(uc, detail.video.project_id),
                                    free_providers=uc.panel.free_providers)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    # -- canais: CRUD de perfil (F10-01/F10-02) -------------------------------

    def _need(uc, attr: str, message: str):
        service = getattr(uc, attr, None)
        if service is None:
            raise HTTPException(503, message)
        return service

    def _topbar(uc, project_id: str | None) -> tuple[list[tuple[str, str]], str]:
        """Canal ativo + lista real de canais para a topbar das Configurações.

        Sem `project_id` a tela assume o primeiro canal (mesma regra das demais telas), em vez de
        mostrar "nenhum canal cadastrado" e perder o seletor.
        """
        repo = getattr(getattr(uc, "panel", None), "repo", None)
        projects = list(repo.projects()) if repo is not None else []
        p_id = _active_channel(uc, project_id)
        if p_id is None and projects:
            p_id = projects[0][0]
        return projects, p_id

    def _active_channel(uc, project_id: str | None) -> str | None:
        """Canal ativo da página (F02.T01/G11), validado no Core.

        - ausente: sem canal ativo (comportamento antigo, primeiro canal);
        - id malformado: `check_id` → 422;
        - id válido que não existe: 404 explícito, em vez de trocar de canal em silêncio.
        """
        if not project_id:
            return None
        p_id = check_id(project_id)
        repo = getattr(getattr(uc, "panel", None), "repo", None)
        existing = repo.projects() if repo is not None else []
        if all(pid != p_id for pid, _ in existing):
            raise ProjectNotFound(p_id)
        return p_id

    def _channel_name(uc, project_id: str | None) -> str:
        """W1.2 (R6): nome do canal **dono** do vídeo, em leitura, para a casca das páginas de vídeo.

        A lista de canais vem do mesmo repositório que alimenta o seletor do topo. Sem
        correspondência devolve "" e a casca mantém o comportamento anterior — nunca inventa nome.
        """
        if not project_id:
            return ""
        repo = getattr(getattr(uc, "panel", None), "repo", None)
        for pid, name in (repo.projects() if repo is not None else []):
            if pid == project_id:
                return name
        return ""

    def _channel_voice(uc, project_id: str | None) -> str | None:
        """Voz do perfil do canal dono do vídeo (leitura); sem perfil, None — nunca inventa."""
        if not project_id or getattr(uc, "get_channel_profile", None) is None:
            return None
        profile = uc.get_channel_profile.execute(project_id)
        return getattr(profile, "voice", None) or None

    def _video_channel_name(uc, video_id: str) -> str:
        """Canal dono do vídeo a partir do próprio vídeo (sem depender da página já ter o projeto)."""
        video = uc.get_video.execute(check_id(video_id)) if uc.get_video is not None else None
        return _channel_name(uc, getattr(video, "project_id", None))

    @router.post("/projects/{project_id}/channels", status_code=201, response_model=ChannelProfileOut)
    def create_channel(project_id: str, body: ChannelProfileIn):
        def go(uc):
            options = body.model_dump()
            name = options.pop("name")
            return _channel_out(_need(uc, "create_channel_profile", "channel services unavailable").execute(
                check_id(project_id), name, **options))
        return run(go)

    @router.get("/projects/{project_id}/channels", response_model=ChannelProfileOut)
    def get_channel(project_id: str):
        def go(uc):
            profile = _need(uc, "get_channel_profile", "channel services unavailable").execute(check_id(project_id))
            if profile is None:
                raise HTTPException(404, "channel profile not found")
            return _channel_out(profile)
        return run(go)

    @router.get("/channels", response_model=list[ChannelProfileOut])
    def list_channels(include_archived: bool = False):
        return run(lambda uc: [_channel_out(p) for p in _need(
            uc, "list_channel_profiles", "channel services unavailable").execute(include_archived)])

    @router.patch("/channels/{profile_id}", response_model=ChannelProfileOut)
    def update_channel(profile_id: str, body: ChannelUpdateIn):
        def go(uc):
            changes = dict(body.changes)
            if "default_mode" not in changes and "default_mode" in body.model_fields_set:
                changes["default_mode"] = body.default_mode.value if isinstance(body.default_mode, ProductionMode) else str(body.default_mode)
            if "default_format" not in changes and "default_format" in body.model_fields_set:
                changes["default_format"] = body.default_format.value if isinstance(body.default_format, VideoFormat) else str(body.default_format)
            profile = _need(uc, "update_channel_profile", "channel services unavailable").execute(
                check_id(profile_id), changes, body.expected_version)
            if profile is None:
                raise HTTPException(404, "channel profile not found")
            return _channel_out(profile)
        return run(go)

    @router.post("/channels/transactional", status_code=201, response_model=ChannelTransactionalOut)
    def create_channel_transactional(request: Request, body: ChannelTransactionalIn):
        key = _optional_idempotency_key(request)

        def go(uc):
            payload = ChannelCreationPayload(
                name=body.name,
                niche=body.niche,
                language=body.language,
                strategy=body.strategy,
                audience=body.audience,
                pillars=tuple(body.pillars),
                narrative=body.narrative,
                target_duration_s=body.target_duration_s,
                visual_identity=body.visual_identity,
                voice=body.voice,
                audio=body.audio,
                thumbnail=body.thumbnail,
                cta=body.cta,
                style_id=body.style_id,
                youtube_channel_id=body.youtube_channel_id,
                default_mode=body.default_mode,
                default_format=body.default_format,
                hard_monthly_usd=body.hard_monthly_usd,
                soft_monthly_usd=body.soft_monthly_usd,
                hard_video_usd=body.hard_video_usd,
                soft_video_usd=body.soft_video_usd,
                economic_profile=body.economic_profile,
                provider_config=body.provider_config,
            )
            try:
                res = _need(uc, "create_channel_transactional", "channel services unavailable").execute(
                    payload, idempotency_key=key
                )
            except ChannelIdempotencyConflict as exc:
                raise HTTPException(409, detail="Idempotency conflict") from exc
            return {
                "project": res.project,
                "profile": _channel_out(res.profile),
                "budget": {
                    "project_id": res.budget.project_id,
                    "hard_monthly_usd": float(res.budget.hard_monthly_usd),
                    "soft_monthly_usd": float(res.budget.soft_monthly_usd),
                    "hard_video_usd": float(res.budget.hard_video_usd),
                    "soft_video_usd": float(res.budget.soft_video_usd),
                    "economic_profile": res.budget.economic_profile.value,
                },
            }

        return run(go)

    # -- estilos: biblioteca compartilhada (VS-05a) ---------------------------

    def _style_usage(uc) -> dict:
        return _need(uc, "visual_style_usage", "style services unavailable").execute()

    @router.get("/styles", response_model=list[VisualStyleOut])
    def list_styles(include_archived: bool = False):
        def go(uc):
            styles = _need(uc, "list_visual_styles", "style services unavailable").execute(include_archived)
            usage = _style_usage(uc)
            return [_style_out(style, usage.get(style.id, 0)) for style in styles]
        return run(go)

    @router.post("/styles", status_code=201, response_model=VisualStyleOut)
    def create_style(body: VisualStyleIn):
        def go(uc):
            style = _need(uc, "create_visual_style", "style services unavailable").execute(body.name, body.params)
            return _style_out(style)
        return run(go)

    @router.get("/styles/{style_id}", response_model=VisualStyleOut)
    def get_style(style_id: str):
        def go(uc):
            style = _need(uc, "get_visual_style", "style services unavailable").execute(style_id)
            if style is None:
                raise VisualStyleNotFound(f"visual style {style_id!r} does not exist")
            return _style_out(style, _style_usage(uc).get(style.id, 0))
        return run(go)

    @router.patch("/styles/{style_id}", response_model=VisualStyleOut)
    def update_style(style_id: str, body: VisualStyleUpdateIn):
        def go(uc):
            style = _need(uc, "update_visual_style", "style services unavailable").execute(
                style_id, body.changes, body.expected_version)
            if style is None:
                raise VisualStyleNotFound(f"visual style {style_id!r} does not exist")
            return _style_out(style)
        return run(go)

    @router.post("/styles/{style_id}/archive", response_model=VisualStyleOut)
    def archive_style(style_id: str):
        def go(uc):
            result = _need(uc, "archive_visual_style", "style services unavailable").execute(style_id)
            if result is None:
                raise VisualStyleNotFound(f"visual style {style_id!r} does not exist")
            out = _style_out(result.style)
            # VS-05c: quantos vínculos de canal/vídeo foram soltos ao arquivar — medição real.
            out["links_cleared"] = result.cleared_links
            return out
        return run(go)

    @router.get("/panel/estilos", response_class=HTMLResponse)
    def styles_page_html(project_id: str | None = None):
        def get_page(uc):
            if uc.styles_page is None:
                raise HTTPException(503, "style services unavailable")
            projects, p_id = _topbar(uc, project_id)
            profile = (uc.get_channel_profile.execute(p_id)
                       if p_id and getattr(uc, "get_channel_profile", None) is not None else None)
            return render_styles(uc.styles_page.execute(), projects=projects, project_id=p_id or "",
                                 channel_name=profile.name if profile else "",
                                 channel_style_id=profile.style_id if profile else None,
                                 channel_version=profile.version if profile else None,
                                 channel_voice=(profile.voice or "") if profile else "")
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/conexoes", response_class=HTMLResponse)
    def connections_page_html(project_id: str | None = None):
        """YT-04b: a tela de Conexões (conta → canais) reusa os casos de uso da YT-04a.

        A projeção é o próprio `list_connections` (mesma fonte do `GET /connections`) somado à
        lista de canais do estúdio — que já existe (`list_channel_profiles`) — para o seletor de
        vínculo. Nenhuma rota ou caso de uso novo: só a página.
        """
        def get_page(uc):
            if uc.list_connections is None:
                raise HTTPException(503, "connection services unavailable")
            board = uc.list_connections.execute()
            profiles = uc.list_channel_profiles.execute(True) if uc.list_channel_profiles else []
            projects, p_id = _topbar(uc, project_id)
            return render_connections(board, profiles, projects=projects, project_id=p_id or "")
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.patch("/videos/{video_id}/style", response_model=Video)
    def set_video_style(video_id: str, body: VideoStyleIn):
        """VS-05b: o canal herda, o vídeo pode sobrepor. `style_id` nulo volta a herdar.

        Vídeo inexistente → 404; estilo inexistente → 422 com a mensagem do domínio (o guard
        global mapeia `VisualStyleNotFound` para 404 na biblioteca, mas aqui o alvo é o vídeo).
        """
        def go(uc):
            service = _need(uc, "set_video_style", "style services unavailable")
            try:
                video = service.execute(check_id(video_id), body.style_id)
            except VisualStyleNotFound as exc:
                raise HTTPException(422, str(exc)) from exc
            if video is None:
                raise HTTPException(404, "video not found")
            return video
        return run(go)

    @router.patch("/videos/{video_id}/style-patch", response_model=VideoStylePatchOut)
    def set_video_style_patch(video_id: str, body: VideoStylePatchIn):
        """F05.T02: grava/remove o override tipado do vídeo, com controle otimista.

        `patch` vazio/ausente remove o override (o vídeo volta a herdar do canal, nunca `{}`).
        Revisão divergente é 409 e nada é gravado; patch fora da allowlist é 422 com a chave nomeada.
        """
        def go(uc):
            service = _need(uc, "set_video_style_patch", "style services unavailable")
            try:
                stored = service.execute(video_id, body.expected_revision, body.patch)
            except VideoStylePatchConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except (StylePatchInvalid, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
            if stored is None:
                raise HTTPException(404, "video not found")
            return VideoStylePatchOut(revision=stored.revision,
                                      patch=stored.patch.to_mapping() if stored.patch else None)
        return run(go)

    @router.patch("/channels/{profile_id}/style-patch", response_model=ChannelStylePatchOut)
    def set_channel_style_patch(profile_id: str, body: ChannelStylePatchIn):
        """F05.T04: grava/remove o override tipado do canal, com controle otimista.

        `patch` vazio/ausente remove o override (o canal volta a herdar, nunca `{}`). Revisão
        divergente é 409 e nada é gravado; patch fora da allowlist é 422 com a chave nomeada.
        """
        def go(uc):
            service = _need(uc, "set_channel_style_patch", "style services unavailable")
            try:
                stored = service.execute(profile_id, body.expected_revision, body.patch)
            except ChannelStylePatchConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if stored is None:
                raise HTTPException(404, "channel not found")
            return ChannelStylePatchOut(revision=stored.revision,
                                        patch=stored.patch.to_mapping() if stored.patch else None)
        return run(go)

    # -- providers (F10-03/F10-04) -------------------------------------------

    @router.get("/projects/{project_id}/providers", response_model=list[ProviderCardOut])
    def list_providers(project_id: str, kind: ProviderKind | None = None):
        return run(lambda uc: [_card_out(c) for c in _need(
            uc, "providers", "provider services unavailable").list(check_id(project_id), kind)])

    @router.post("/projects/{project_id}/providers/test", response_model=ConnectionTestOut)
    def test_provider(project_id: str, body: ProviderTestIn):
        def go(uc):
            result = _need(uc, "providers", "provider services unavailable").test_connection(
                check_id(project_id), body.kind, body.spec)
            return {"kind": result.kind.value, "spec": result.spec, "name": result.name,
                    "available": result.available, "checked": result.checked, "reason": result.reason}
        return run(go)

    @router.post("/projects/{project_id}/providers/route", response_model=RoutingOut)
    def route_provider_endpoint(project_id: str, body: RouteIn):
        def go(uc):
            decision = _need(uc, "providers", "provider services unavailable").route(
                check_id(project_id), body.kind, body.profile, body.max_cost_usd)
            return {"kind": decision.kind.value, "profile": decision.profile.value,
                    "primary": _card_out(decision.primary),
                    "fallbacks": [_card_out(c) for c in decision.fallbacks], "reason": decision.reason}
        return run(go)

    # -- budget por canal (F10-05) -------------------------------------------

    @router.get("/projects/{project_id}/budget", response_model=BudgetOut)
    def get_channel_budget(project_id: str):
        return run(lambda uc: _budget_out(_need(
            uc, "get_channel_budget", "budget services unavailable").execute(check_id(project_id))))

    @router.put("/projects/{project_id}/budget", response_model=BudgetOut)
    def put_channel_budget(project_id: str, body: BudgetIn):
        def go(uc):
            p_id = check_id(project_id)
            _need(uc, "set_channel_budget", "budget services unavailable").execute(
                p_id, hard_monthly_usd=body.hard_monthly_usd, soft_monthly_usd=body.soft_monthly_usd,
                hard_video_usd=body.hard_video_usd, soft_video_usd=body.soft_video_usd,
                economic_profile=body.economic_profile)
            return _budget_out(_need(uc, "get_channel_budget", "budget services unavailable").execute(p_id))
        return run(go)

    # -- canal YouTube e status OAuth (F10-06) -------------------------------

    @router.get("/projects/{project_id}/youtube-channel", response_model=YouTubeChannelOut)
    def get_youtube_channel(project_id: str):
        return run(lambda uc: _need(uc, "get_youtube_channel", "youtube services unavailable").execute(
            check_id(project_id)))

    @router.put("/projects/{project_id}/youtube-channel", response_model=YouTubeChannelOut)
    def put_youtube_channel(project_id: str, body: YouTubeChannelIn):
        def go(uc):
            return _need(uc, "associate_youtube_channel", "youtube services unavailable").execute(
                check_id(project_id), channel_id=body.channel_id, title=body.title, scopes=body.scopes,
                access_token=body.access_token, refresh_token=body.refresh_token,
                token_expires_at=body.token_expires_at)
        return run(go)

    @router.delete("/projects/{project_id}/youtube-channel")
    def delete_youtube_channel(project_id: str):
        return run(lambda uc: {"deleted": _need(
            uc, "disconnect_youtube_channel", "youtube services unavailable").execute(check_id(project_id))})

    # -- OAuth real: consentimento, callback, refresh e revogação (F8-05) -----

    @router.post("/projects/{project_id}/youtube-oauth/authorize", response_model=OAuthAuthorizeOut)
    def begin_youtube_oauth(project_id: str):
        return run(lambda uc: _need(uc, "begin_youtube_oauth", "youtube OAuth is not configured").execute(
            check_id(project_id)))

    @router.post("/projects/{project_id}/youtube-oauth/callback", response_model=YouTubeChannelOut)
    def complete_youtube_oauth(project_id: str, body: OAuthCallbackIn):
        return run(lambda uc: _need(uc, "complete_youtube_oauth", "youtube OAuth is not configured").execute(
            check_id(project_id), body.code, body.state))

    @router.post("/projects/{project_id}/youtube-oauth/refresh", response_model=YouTubeChannelOut)
    def refresh_youtube_oauth(project_id: str):
        return run(lambda uc: _need(uc, "refresh_youtube_channel", "youtube OAuth is not configured").execute(
            check_id(project_id)))

    @router.post("/projects/{project_id}/youtube-oauth/revoke", response_model=YouTubeChannelOut)
    def revoke_youtube_oauth(project_id: str):
        return run(lambda uc: _need(uc, "revoke_youtube_channel", "youtube OAuth is not configured").execute(
            check_id(project_id)))

    # -- Conexões: conta Google → autorizações → canais do YouTube (YT-04a) ---
    #
    # O vínculo do canal do estúdio a um canal do YouTube reusa o `PATCH /channels/{profile_id}`
    # (já aceita `youtube_channel_id`): nenhuma rota redundante é criada aqui.

    @router.get("/connections", response_model=ConnectionsOut)
    def list_connections():
        return run(lambda uc: _need(uc, "list_connections", "connection services unavailable").execute())

    @router.post("/connections/oauth/start", response_model=ConnectionsAuthorizeOut)
    def begin_connection_oauth():
        return run(lambda uc: _need(uc, "begin_account_consent", "youtube OAuth is not configured").execute())

    @router.post("/connections/oauth/callback", response_model=ConnectionConsentOut)
    def complete_connection_oauth(body: ConnectionsCallbackIn):
        return run(lambda uc: _need(uc, "complete_account_consent", "youtube OAuth is not configured").execute(
            body.code, body.state, email=body.email))

    @router.post("/connections/authorizations/{grant_id}/{youtube_channel_id}/revoke",
                 response_model=AuthorizationRevokedOut)
    def revoke_connection_authorization(grant_id: str, youtube_channel_id: str):
        return run(lambda uc: _need(uc, "revoke_authorization", "connection services unavailable").execute(
            check_id(grant_id), youtube_channel_id))

    # -- configuração pública do projeto (F10-07) ----------------------------

    @router.get("/projects/{project_id}/config", response_model=ProjectConfigOut)
    def get_project_config(project_id: str):
        return run(lambda uc: _need(uc, "get_project_config", "config services unavailable").execute(
            check_id(project_id)))

    @router.put("/projects/{project_id}/config", response_model=ProjectConfigOut)
    def set_project_config(project_id: str, body: dict):
        # Corpo cru (`dict`): a validação mora no caso de uso para recusar chave desconhecida sem
        # ecoar o valor ofensor — o handler 422 padrão do FastAPI incluiria `input` (o valor cru).
        return run(lambda uc: _need(uc, "set_project_config", "config services unavailable").execute(
            check_id(project_id), body))

    return router
