"""Rotas /studio. Só falam com casos de uso; nunca com repositório ou banco."""
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..application.use_cases import InvalidInput, ProjectNotFound, ServiceUnavailable, UseCases
from ..domain.contracts import Project, Video, VideoFormat, VideoStatus
from ..domain.ids import InvalidId, check_id
from ..domain.states import InvalidTransition


# Aprovar, rejeitar e publicar só pelos endpoints próprios (P05), que checam QA e aprovação humana.
RESERVED_TARGETS = {VideoStatus.APPROVED, VideoStatus.REJECTED, VideoStatus.PUBLISHED}


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    niche: str = Field(default="", max_length=200)
    language: str = Field(default="pt-BR", max_length=16)


class VideoIn(BaseModel):
    project_id: str
    topic: str = Field(min_length=3, max_length=300)
    format: VideoFormat = VideoFormat.short


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
        if body.new in RESERVED_TARGETS:
            raise HTTPException(403, "approve/reject/publish are reserved for the dedicated endpoints (P05)")
        if not run(lambda uc: uc.transition_video.execute(check_id(video_id), body.expected, body.new)):
            raise HTTPException(409, "video is not in the expected state")
        return {"ok": True}

    return router
