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
from .analytics_collection import CollectMetrics
from .analytics_dashboard import BuildAnalyticsDashboard
from .analytics_learning import DecideRecommendation, RegisterExperiment
from .analytics_ports import AnalyticsRepository
from .observability import Resume
from .categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from .channels import CreateChannelProfile, GetChannelProfile, ListChannelProfiles, UpdateChannelProfile
from .channel_budget import GetChannelBudget, SetChannelBudget
from .providers import ProviderService
from .secrets import GetPublicProjectConfig
from .youtube_channels import AssociateYouTubeChannel, DisconnectYouTubeChannel, GetYouTubeChannel
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # import só para tipagem: evita ciclo com o coordenador (que importa os casos de uso)
    from .production import Production
    from .script_view import BuildScriptView


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
    script_view: "BuildScriptView | None" = None
    # F10-03..07 (backend/HTTP de canais e providers)
    providers: ProviderService | None = None
    get_channel_budget: GetChannelBudget | None = None
    set_channel_budget: SetChannelBudget | None = None
    get_youtube_channel: GetYouTubeChannel | None = None
    associate_youtube_channel: AssociateYouTubeChannel | None = None
    disconnect_youtube_channel: DisconnectYouTubeChannel | None = None
    get_project_config: GetPublicProjectConfig | None = None
    # F9 (analytics e loop de aprendizado)
    analytics_repo: AnalyticsRepository | None = None
    analytics_dashboard: BuildAnalyticsDashboard | None = None
    analytics_collection: CollectMetrics | None = None
    analytics_decide: DecideRecommendation | None = None
    analytics_register_experiment: RegisterExperiment | None = None

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
                  production: "Production | None" = None,
                  script_view: "BuildScriptView | None" = None,
                  providers: ProviderService | None = None,
                  get_channel_budget: GetChannelBudget | None = None,
                  set_channel_budget: SetChannelBudget | None = None,
                  get_youtube_channel: GetYouTubeChannel | None = None,
                  associate_youtube_channel: AssociateYouTubeChannel | None = None,
                  disconnect_youtube_channel: DisconnectYouTubeChannel | None = None,
                  get_project_config: GetPublicProjectConfig | None = None,
                  analytics_repo: AnalyticsRepository | None = None,
                  analytics_dashboard: BuildAnalyticsDashboard | None = None,
                  analytics_collection: CollectMetrics | None = None,
                  analytics_decide: DecideRecommendation | None = None,
                  analytics_register_experiment: RegisterExperiment | None = None) -> "UseCases":
        return cls(CreateProject(repo), CreateVideo(repo), GetVideo(repo), TransitionVideo(repo),
                   editorial, media, rendering, publishing, analytics, resume, panel, ingest_trends, trends_repo,
                   categories_repo, list_categories, save_category, delete_category, refresh_trends,
                   channel_profiles_repo, create_channel_profile, get_channel_profile, update_channel_profile,
list_channel_profiles, production, script_view, providers, get_channel_budget, set_channel_budget,
                   get_youtube_channel, associate_youtube_channel, disconnect_youtube_channel, get_project_config,
                   analytics_repo, analytics_dashboard, analytics_collection, analytics_decide,
                   analytics_register_experiment)
