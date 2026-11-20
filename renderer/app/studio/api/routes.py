"""Rotas /studio. Só falam com casos de uso; nunca com repositório ou banco."""
from collections.abc import Callable
from datetime import date, datetime
import base64
import binascii
import hashlib
import hmac
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, field_validator

from ..application.config import ProviderNotFound
from ..application.analytics import DailyMetric
from ..application.editorial import (ScriptRejected, SourceRefused, SourceUnavailable, StateConflict, VideoNotFound)
from ..application.ideas import IdeaInputRefused, IdeasRejected, MAX_TOPICS
from ..application.media import AssetRefused
from ..application.publishing import PublicationConflict, PublicationNotFound
from ..application.render import RenderRefused
from ..domain.publish import InvalidPublishData, srt_to_vtt
from ..domain.trends import TrendItem, TrendRefused
from .preview import render_preview
from .panel import render_panel, render_video
from ..application.ports import ModelUnavailable
from ..application.use_cases import InvalidInput, ProjectNotFound, ServiceUnavailable, UseCases
from ..domain.contracts import Approval, Publication, Asset, FactCheckReport, QaReport, RenderJob, Project, Scene, Script, Video, VideoFormat, VideoStatus
from ..domain.policy import CostRefused
from ..domain.rubric import IdeaScores
from ..domain.ids import InvalidId, check_id
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
    project_id: str
    topic: str = Field(min_length=3, max_length=300)
    format: VideoFormat = VideoFormat.short


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


class TransitionIn(BaseModel):
    expected: VideoStatus
    new: VideoStatus


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
        except (InvalidTransition, InvalidInput) as exc:
            raise HTTPException(422, str(exc)) from exc
        except ServiceUnavailable as exc:
            raise HTTPException(503, "studio database unavailable") from exc
        except VideoNotFound as exc:
            raise HTTPException(404, "video not found") from exc
        except StateConflict as exc:
            raise HTTPException(409, str(exc)) from exc
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
        except PublicationNotFound as exc:
            raise HTTPException(404, "publication not found") from exc
        except PublicationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (AssetRefused, RenderRefused) as exc:
            raise HTTPException(502, f"asset refused: {exc}") from exc

    def editorial(uc: UseCases):
        if uc.editorial is None:
            raise HTTPException(503, "editorial services unavailable")
        return uc.editorial

    @router.post("/projects", status_code=201, response_model=Project)
    def create_project(body: ProjectIn):
        return run(lambda uc: uc.create_project.execute(body.name, body.niche, body.language))

    @router.post("/videos", status_code=201, response_model=Video)
    def create_video(body: VideoIn):
        return run(lambda uc: uc.create_video.execute(check_id(body.project_id), body.topic, body.format))

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

    def rendering(uc: UseCases):
        if uc.rendering is None:
            raise HTTPException(503, "render services unavailable")
        return uc.rendering

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
    def panel_html(days: int = 7, project_id: str | None = None):
        def get_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            p_id = check_id(project_id) if project_id else None
            view = uc.panel.execute(days=days, project_id=p_id)
            return render_panel(view)
        page, headers = run(get_page)
        return HTMLResponse(page, headers=headers)

    @router.get("/panel/videos/{video_id}", response_class=HTMLResponse)
    def panel_video_detail_html(video_id: str):
        def get_detail_page(uc):
            if uc.panel is None:
                raise HTTPException(503, "panel services unavailable")
            detail = uc.panel.detail(check_id(video_id))
            return render_video(detail)
        page, headers = run(get_detail_page)
        return HTMLResponse(page, headers=headers)

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

    def publishing(uc: UseCases):
        if uc.publishing is None:
            raise HTTPException(503, "publishing services unavailable")
        return uc.publishing

    @router.post("/videos/{video_id}/approve", response_model=DecisionOut)
    def approve(video_id: str, body: ApproveIn | None = None):
        body = body or ApproveIn()
        video, changed = run(lambda uc: publishing(uc).approve.execute(
            check_id(video_id), title=body.title, description=body.description, tags=body.tags, publish_at=body.publish_at,
            override_reason=body.override_reason, output_asset_id=check_id(body.output_asset_id) if body.output_asset_id else None))
        return DecisionOut(video=video, changed=changed)

    @router.post("/videos/{video_id}/reject", response_model=DecisionOut)
    def reject(video_id: str, body: RejectIn | None = None):
        video, changed = run(lambda uc: publishing(uc).reject.execute(check_id(video_id), (body or RejectIn()).reason))
        return DecisionOut(video=video, changed=changed)

    @router.get("/videos/{video_id}/preview", response_class=HTMLResponse)
    def preview(video_id: str):
        page, headers = render_preview(run(lambda uc: publishing(uc).preview.execute(check_id(video_id))))
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

    @router.post("/publications/claim", response_model=ClaimResult)
    def claim(body: ClaimIn | None = None):
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

    return router
