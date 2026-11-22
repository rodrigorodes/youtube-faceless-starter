"""Casos de uso. Dependem das portas, nunca de adaptadores."""
from dataclasses import dataclass

from ..domain.contracts import Project, Video, VideoFormat, VideoStatus
from ..domain.states import assert_transition
from .editorial import Editorial
from .media import Media
from .publishing import Publishing
from .render import Rendering
from .render_cache import PlanRegeneration
from .panel import BuildPanel
from .ports import CategoryRepository, ChannelProfileRepository, TrendRepository, VideoRepository
from ..domain.visual_style import VisualStyleArchived
from .errors import VisualStyleNotFound
from .trends import IngestTrends
from .analytics import Analytics
from .analytics_collection import CollectMetrics
from .analytics_dashboard import BuildAnalyticsDashboard
from .analytics_learning import DecideRecommendation, RegisterExperiment
from .analytics_ports import AnalyticsRepository
from .observability import Resume
from .categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from .channels import CreateChannelProfile, GetChannelProfile, ListChannelProfiles, UpdateChannelProfile
from .styles import (ArchiveVisualStyle, CreateVisualStyle, GetVisualStyle, ListVisualStyles,
                     UpdateVisualStyle, VisualStyleUsage)
from .video_style import SetChannelStylePatch, BuildVideoStyleView, SetVideoStyle
from .channel_budget import GetChannelBudget, SetChannelBudget
from .providers import ProviderService
from .secrets import GetPublicProjectConfig, SetPublicProjectConfig
from .youtube_channels import AssociateYouTubeChannel, DisconnectYouTubeChannel, GetYouTubeChannel
from .youtube_oauth import (BeginConsent, CompleteConsent, RefreshYouTubeChannel, RevokeConsent)
from .connections import (BeginAccountConsent, CompleteAccountConsent, LinkStudioChannel, ListConnections,
                          RevokeAuthorization, Unlink)
from .saas import (ChangeMemberRole, InviteMember, RegisterByokKey, RemoveMember, ResolveActor,
                   RevokeByokKey, RotateByokKey)
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # import só para tipagem: evita ciclo com o coordenador (que importa os casos de uso)
    from .production import Production
    from .script_view import BuildScriptView
    from .channel_style_page import BuildChannelStylePage
    from .channels_page import BuildChannelsPage
    from .styles_page import BuildStylesPage
    from .advanced_page import BuildAdvancedView
    from .composition_view import BuildCompositionView
    from .ports import VisualStyleRepository


from .errors import InvalidInput, ProjectNotFound, ServiceUnavailable  # noqa: F401  (reexportado: adaptadores e API importam daqui)


class CreateProject:
    def __init__(self, repo: VideoRepository):
        self.repo = repo

    def execute(self, name: str, niche: str = "", language: str = "pt-BR") -> Project:
        return self.repo.create_project(name, niche, language)


class CreateVideo:
    def __init__(self, repo: VideoRepository, styles: "VisualStyleRepository | None" = None):
        self.repo = repo
        # F02.T02/G15: com a biblioteca injetada, o estilo escolhido é validado antes de gravar
        # (existe e está ativo). Sem ela o caso de uso mantém o comportamento legado (sem estilo).
        self.styles = styles

    def execute(self, project_id: str, topic: str, fmt: VideoFormat,
                style_id: str | None = None) -> Video:
        if self.repo.get_project(project_id) is None:
            raise ProjectNotFound(project_id)
        if style_id is None:
            return self.repo.create_video(project_id, topic, fmt)
        if self.styles is None:
            # sem biblioteca não há como provar que o estilo existe: falha fechado
            raise VisualStyleNotFound(style_id)
        sid = style_id
        style = self.styles.get(sid)
        if style is None:
            raise VisualStyleNotFound(style_id)
        if style.archived:
            raise VisualStyleArchived(f"visual style {style.name!r} is archived")
        return self.repo.create_video(project_id, topic, fmt, style_id=style.id)


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
    set_project_config: SetPublicProjectConfig | None = None
    # F10 (UI): projeção da tela de Canais consumindo os casos de uso acima
    channels_page: "BuildChannelsPage | None" = None
    # F05.T04: personalização do canal (origem/efetivo/reset) e escrita do patch com revisão.
    channel_style_page: "BuildChannelStylePage | None" = None
    set_channel_style_patch: "SetChannelStylePatch | None" = None
    # F11: leitura da tela de Equipe (tenancy/BYOK).
    team_view: "BuildTeamView | None" = None
    # F9 (analytics e loop de aprendizado)
    analytics_repo: AnalyticsRepository | None = None
    analytics_dashboard: BuildAnalyticsDashboard | None = None
    analytics_collection: CollectMetrics | None = None
    analytics_decide: DecideRecommendation | None = None
    analytics_register_experiment: RegisterExperiment | None = None
    # F8-05: OAuth real atrás de porta (consentimento/refresh/revogação)
    begin_youtube_oauth: BeginConsent | None = None
    complete_youtube_oauth: CompleteConsent | None = None
    refresh_youtube_channel: RefreshYouTubeChannel | None = None
    revoke_youtube_channel: RevokeConsent | None = None
    # YT-04a: Conexões (conta Google → autorizações → canais do YouTube). Sem painel; só serviço + API.
    list_connections: ListConnections | None = None
    begin_account_consent: BeginAccountConsent | None = None
    complete_account_consent: CompleteAccountConsent | None = None
    revoke_authorization: RevokeAuthorization | None = None
    link_studio_channel: LinkStudioChannel | None = None
    unlink_studio_channel: Unlink | None = None
    # L2: mutações de Equipe. O ator é o operador autenticado do painel, resolvido no vínculo dele.
    resolve_actor: ResolveActor | None = None
    invite_member: InviteMember | None = None
    change_member_role: ChangeMemberRole | None = None
    remove_member: RemoveMember | None = None
    register_byok_key: RegisterByokKey | None = None
    rotate_byok_key: RotateByokKey | None = None
    revoke_byok_key: RevokeByokKey | None = None
    # RP-06: regeneração seletiva (grafo de dependências + cache) da tela Editor (fatia posterior).
    plan_regeneration: PlanRegeneration | None = None
    # VS-05a (UI): a biblioteca de estilos (lista + criar + editar + arquivar + uso medido).
    create_visual_style: CreateVisualStyle | None = None
    get_visual_style: GetVisualStyle | None = None
    list_visual_styles: ListVisualStyles | None = None
    update_visual_style: UpdateVisualStyle | None = None
    archive_visual_style: ArchiveVisualStyle | None = None
    visual_style_usage: VisualStyleUsage | None = None
    styles_page: "BuildStylesPage | None" = None
    # VS-05b (UI/API): o override de estilo por vídeo (o canal herda, o vídeo pode sobrepor).
    set_video_style: SetVideoStyle | None = None
    video_style_view: BuildVideoStyleView | None = None
    # F02.T03: view model da tela Avançado (diagnóstico read-only).
    advanced_page: "BuildAdvancedView | None" = None
    # W2.3: leitura do plano de composição persistido (só a porta `RenderPlanRepository`).
    composition_view: "BuildCompositionView | None" = None

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
                  set_project_config: SetPublicProjectConfig | None = None,
                  channels_page: "BuildChannelsPage | None" = None,
                  channel_style_page: "BuildChannelStylePage | None" = None,
                  set_channel_style_patch: SetChannelStylePatch | None = None,
                  team_view: "BuildTeamView | None" = None,
                  analytics_repo: AnalyticsRepository | None = None,
                  analytics_dashboard: BuildAnalyticsDashboard | None = None,
                  analytics_collection: CollectMetrics | None = None,
                  analytics_decide: DecideRecommendation | None = None,
                  analytics_register_experiment: RegisterExperiment | None = None,
                  begin_youtube_oauth: BeginConsent | None = None,
                  complete_youtube_oauth: CompleteConsent | None = None,
                  refresh_youtube_channel: RefreshYouTubeChannel | None = None,
                  revoke_youtube_channel: RevokeConsent | None = None,
                  list_connections: ListConnections | None = None,
                  begin_account_consent: BeginAccountConsent | None = None,
                  complete_account_consent: CompleteAccountConsent | None = None,
                  revoke_authorization: RevokeAuthorization | None = None,
                  link_studio_channel: LinkStudioChannel | None = None,
                  unlink_studio_channel: Unlink | None = None,
                  resolve_actor: ResolveActor | None = None,
                  invite_member: InviteMember | None = None,
                  change_member_role: ChangeMemberRole | None = None,
                  remove_member: RemoveMember | None = None,
                  register_byok_key: RegisterByokKey | None = None,
                  rotate_byok_key: RotateByokKey | None = None,
                  revoke_byok_key: RevokeByokKey | None = None,
                  plan_regeneration: PlanRegeneration | None = None,
                  create_visual_style: CreateVisualStyle | None = None,
                  get_visual_style: GetVisualStyle | None = None,
                  list_visual_styles: ListVisualStyles | None = None,
                  update_visual_style: UpdateVisualStyle | None = None,
                  archive_visual_style: ArchiveVisualStyle | None = None,
                  visual_style_usage: VisualStyleUsage | None = None,
                  styles_page: "BuildStylesPage | None" = None,
                  set_video_style: SetVideoStyle | None = None,
                  video_style_view: BuildVideoStyleView | None = None,
                  style_repo: "VisualStyleRepository | None" = None,
                  advanced_page: "BuildAdvancedView | None" = None,
                  composition_view: "BuildCompositionView | None" = None) -> "UseCases":
        return cls(CreateProject(repo), CreateVideo(repo, style_repo), GetVideo(repo), TransitionVideo(repo),
                   editorial, media, rendering, publishing, analytics, resume, panel, ingest_trends, trends_repo,
                   categories_repo, list_categories, save_category, delete_category, refresh_trends,
                   channel_profiles_repo, create_channel_profile, get_channel_profile, update_channel_profile,
list_channel_profiles, production, script_view, providers, get_channel_budget, set_channel_budget,
                   get_youtube_channel, associate_youtube_channel, disconnect_youtube_channel, get_project_config,
                   set_project_config,
                   channels_page,
                   channel_style_page, set_channel_style_patch,
                   team_view,
                   analytics_repo, analytics_dashboard, analytics_collection, analytics_decide,
                   analytics_register_experiment,
                   begin_youtube_oauth, complete_youtube_oauth, refresh_youtube_channel, revoke_youtube_channel,
                   list_connections, begin_account_consent, complete_account_consent, revoke_authorization,
                   link_studio_channel, unlink_studio_channel,
                   resolve_actor, invite_member, change_member_role, remove_member,
                   register_byok_key, rotate_byok_key, revoke_byok_key, plan_regeneration,
                   create_visual_style, get_visual_style, list_visual_styles, update_visual_style,
                   archive_visual_style, visual_style_usage, styles_page, set_video_style, video_style_view,
                   advanced_page, composition_view)
