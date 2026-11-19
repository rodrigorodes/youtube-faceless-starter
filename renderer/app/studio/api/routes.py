"""Rotas /studio. Só falam com casos de uso; nunca com repositório ou banco."""
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..application.config import ProviderNotFound
from ..application.editorial import (ScriptRejected, SourceRefused, SourceUnavailable, StateConflict, VideoNotFound)
from ..application.ideas import IdeaInputRefused, IdeasRejected, MAX_TOPICS
from ..application.media import AssetRefused
from ..application.ports import ModelUnavailable
from ..application.use_cases import InvalidInput, ProjectNotFound, ServiceUnavailable, UseCases
from ..domain.contracts import Asset, FactCheckReport, Project, Scene, Script, Video, VideoFormat, VideoStatus
from ..domain.policy import CostRefused
from ..domain.rubric import IdeaScores
from ..domain.ids import InvalidId, check_id
from ..domain.states import InvalidTransition


# Aprovar, rejeitar e publicar só pelos endpoints próprios (P05), que checam QA e aprovação humana.
RESERVED_TARGETS = {VideoStatus.APPROVED, VideoStatus.REJECTED, VideoStatus.PUBLISHED, VideoStatus.FACT_CHECKED,
                    VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY}
# Retomar de FAILED não pode saltar etapas com gate; a retomada validada é a P06.
POST_GATE = {VideoStatus.FACT_CHECKED, VideoStatus.STORYBOARDED, VideoStatus.ASSETS_READY, VideoStatus.RENDERED, VideoStatus.AWAITING_APPROVAL}


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


class RankedOut(BaseModel):
    topic: str
    score: float
    scores: IdeaScores


class IdeasOut(BaseModel):
    ranked: list[RankedOut]


class ProduceOut(BaseModel):
    generated: int
    reused: int


class SceneAssetOut(BaseModel):
    idx: int
    asset: Asset | None


class AssetsOut(BaseModel):
    scenes: list[SceneAssetOut]


class TransitionIn(BaseModel):
    expected: VideoStatus
    new: VideoStatus


def make_router(get_use_cases: Callable[[], UseCases | None], ping: Callable[[], bool]) -> APIRouter:
    router = APIRouter(prefix="/studio", tags=["studio"])

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
        except (SourceRefused, ProviderNotFound, IdeaInputRefused) as exc:
            raise HTTPException(422, str(exc)) from exc
        except CostRefused as exc:
            raise HTTPException(403, f"cost cap: {exc}") from exc
        except (SourceUnavailable, ModelUnavailable) as exc:
            raise HTTPException(502, str(exc)) from exc
        except (ScriptRejected, IdeasRejected, AssetRefused) as exc:
            raise HTTPException(502, f"model output rejected: {exc}") from exc

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

    return router
