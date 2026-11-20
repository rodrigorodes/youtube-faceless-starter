"""Casos de uso. Dependem das portas, nunca de adaptadores."""
from dataclasses import dataclass

from ..domain.contracts import Project, Video, VideoFormat, VideoStatus
from ..domain.states import assert_transition
from .editorial import Editorial
from .media import Media
from .publishing import Publishing
from .render import Rendering
from .panel import BuildPanel
from .ports import CategoryRepository, ChannelProfileRepository, TrendRepository, VideoRepository
from .trends import IngestTrends
from .analytics import Analytics
from .observability import Resume
from .categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from .channels import CreateChannelProfile, GetChannelProfile, ListChannelProfiles, UpdateChannelProfile
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # import só para tipagem: evita ciclo com o coordenador (que importa os casos de uso)
    from .production import Production


from .errors import InvalidInput, ProjectNotFound, ServiceUnavailable  # noqa: F401  (reexportado: adaptadores e API importam daqui)


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
    analytics: Analytics | None = None
    resume: Resume | None = None
    panel: BuildPanel | None = None
    ingest_trends: IngestTrends | None = None
    trends_repo: TrendRepository | None = None
    categories_repo: CategoryRepository | None = None
    list_categories: ListCategories | None = None
    save_category: SaveCategory | None = None
    delete_category: DeleteCategory | None = None
    refresh_trends: RefreshTrends | None = None
    channel_profiles_repo: ChannelProfileRepository | None = None
    create_channel_profile: CreateChannelProfile | None = None
    get_channel_profile: GetChannelProfile | None = None
    update_channel_profile: UpdateChannelProfile | None = None
    list_channel_profiles: ListChannelProfiles | None = None
    production: "Production | None" = None

    @classmethod
    def from_repo(cls, repo: VideoRepository, editorial: Editorial | None = None, media: Media | None = None,
                  rendering: Rendering | None = None, publishing: Publishing | None = None,
                  analytics: Analytics | None = None, resume: Resume | None = None,
                  panel: BuildPanel | None = None, ingest_trends: IngestTrends | None = None,
                  trends_repo: TrendRepository | None = None,
                  categories_repo: CategoryRepository | None = None,
                  list_categories: ListCategories | None = None,
                  save_category: SaveCategory | None = None,
                  delete_category: DeleteCategory | None = None,
                  refresh_trends: RefreshTrends | None = None,
                  channel_profiles_repo: ChannelProfileRepository | None = None,
                  create_channel_profile: CreateChannelProfile | None = None,
                  get_channel_profile: GetChannelProfile | None = None,
                  update_channel_profile: UpdateChannelProfile | None = None,
                  list_channel_profiles: ListChannelProfiles | None = None,
                  production: "Production | None" = None) -> "UseCases":
        return cls(CreateProject(repo), CreateVideo(repo), GetVideo(repo), TransitionVideo(repo),
                   editorial, media, rendering, publishing, analytics, resume, panel, ingest_trends, trends_repo,
                   categories_repo, list_categories, save_category, delete_category, refresh_trends,
                   channel_profiles_repo, create_channel_profile, get_channel_profile, update_channel_profile,
                   list_channel_profiles, production)
