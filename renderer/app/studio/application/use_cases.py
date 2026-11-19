"""Casos de uso. Dependem das portas, nunca de adaptadores."""
from dataclasses import dataclass

from ..domain.contracts import Project, Video, VideoFormat, VideoStatus
from ..domain.states import assert_transition
from .ports import VideoRepository


class ProjectNotFound(LookupError):
    pass


class ServiceUnavailable(RuntimeError):
    """Persistência indisponível (traduzida pelos adaptadores; a API responde 503)."""


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

    @classmethod
    def from_repo(cls, repo: VideoRepository) -> "UseCases":
        return cls(CreateProject(repo), CreateVideo(repo), GetVideo(repo), TransitionVideo(repo))
