"""Casos de uso. Dependem das portas, nunca de adaptadores."""
from dataclasses import dataclass

from ..domain.contracts import Project, Video, VideoFormat, VideoStatus
from ..domain.states import assert_transition
from .editorial import Editorial
from .media import Media
from .publishing import Publishing
from .render import Rendering
from .ports import VideoRepository


class ProjectNotFound(LookupError):
    pass

from .errors import ServiceUnavailable  # noqa: F401  (reexportado: adaptadores e API importam daqui)


class InvalidInput(ValueError):
    """Dado recusado pela persistência (ex.: byte NUL em texto)."""


class CreateProject:
    def __init__(self, repo: VideoRepository):
        self.repo = repo

    def execute(self, name: str, niche: str = "", language: str = "pt-BR") -> Project:
        return self.repo.create_project(name, niche, language)


class CreateVideo:
    def __init__(self, repo: VideoRepository):
        self.repo = repo

    def execute(self, project_id: str, topic: str, fmt: VideoFormat) -> Video:
        if self.repo.get_project(project_id) is None:
            raise ProjectNotFound(project_id)
        return self.repo.create_video(project_id, topic, fmt)


class GetVideo:
    def __init__(self, repo: VideoRepository):
        self.repo = repo

    def execute(self, video_id: str) -> Video | None:
        return self.repo.get_video(video_id)


class TransitionVideo:
    def __init__(self, repo: VideoRepository):
        self.repo = repo

    def execute(self, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool:
        assert_transition(expected, new)  # antes de tocar no repositório
        return self.repo.transition_video(video_id, expected, new)


@dataclass(frozen=True)
class UseCases:
    create_project: CreateProject
    create_video: CreateVideo
    get_video: GetVideo
    transition_video: TransitionVideo
    editorial: Editorial | None = None
    media: Media | None = None
    rendering: Rendering | None = None
    publishing: Publishing | None = None

    @classmethod
    def from_repo(cls, repo: VideoRepository, editorial: Editorial | None = None, media: Media | None = None,
                  rendering: Rendering | None = None, publishing: Publishing | None = None) -> "UseCases":
        return cls(CreateProject(repo), CreateVideo(repo), GetVideo(repo), TransitionVideo(repo), editorial, media, rendering, publishing)
