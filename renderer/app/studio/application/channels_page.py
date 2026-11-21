"""Projeção da tela de Canais (F10) — só dado real do Studio, com estados vazios explícitos.

A tela consome os casos de uso já existentes da fatia H: perfil de canal versionado, catálogo de
providers (capability/custo/rate limit/disponibilidade), roteamento econômico, budget com limites
hard/soft, associação YouTube (status OAuth sem token) e configuração pública sanitizada.

Regras que valem aqui:
- nada é inventado: provider sem implementação validada aparece UNAVAILABLE com o motivo real;
- roteamento é derivado do perfil econômico persistido; quando não há candidato, o motivo é exposto;
- custo desconhecido nunca vira zero; ausência de uso é "sem registro", não `US$ 0,00`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ..domain.channel import ChannelProfile
from ..domain.channel_budget import CostSummary
from ..domain.contracts import Project
from ..domain.provider import NoProviderAvailable, ProviderCard, ProviderKind, RoutingDecision
from .channel_budget import ChannelBudgetView, GetChannelBudget
from .channels import GetChannelProfile
from .errors import ProjectNotFound
from .providers import ProviderService
from .secrets import GetPublicProjectConfig
from .youtube_channels import GetYouTubeChannel

__all__ = ["ChannelsPageView", "BuildChannelsPage", "ProjectListPort"]

# Motivo real quando o servidor não tem app OAuth do Google configurado. A tela usa o texto no
# controle desabilitado; nunca diz que o fluxo "não está implementado" (ele existe desde a F8).
OAUTH_UNAVAILABLE_REASON = "OAuth do YouTube não configurado no servidor (falta o client secret do Google)"


class ProjectListPort(Protocol):
    """Lista (id, nome) dos canais/projetos cadastrados. Leitura apenas."""

    def projects(self) -> list[tuple[str, str]]: ...


@dataclass(frozen=True)
class ChannelsPageView:
    """Dados reais da tela. `project is None` significa Studio sem canal cadastrado."""

    projects: tuple[tuple[str, str], ...] = ()
    project: Project | None = None
    profile: ChannelProfile | None = None
    providers: tuple[ProviderCard, ...] = ()
    routes: tuple[RoutingDecision, ...] = ()
    route_failures: tuple[tuple[ProviderKind, str], ...] = ()
    budget: ChannelBudgetView | None = None
    youtube: dict[str, object] | None = None
    public_config: dict[str, str] = field(default_factory=dict)
    providers_error: str | None = None
    # O fluxo OAuth existe (F8) mas só pode ser iniciado se o servidor tiver o app do Google.
    # `oauth_available=False` desabilita o controle **com o motivo real**, nunca negando o fluxo.
    oauth_available: bool = False
    oauth_unavailable_reason: str | None = None
    oauth_authorize_path: str | None = None
    oauth_revoke_path: str | None = None

    @property
    def cost_summary(self) -> CostSummary | None:
        return self.budget.summary if self.budget is not None else None


class BuildChannelsPage:
    """Monta a projeção da tela de Canais a partir dos casos de uso da fatia H."""

    def __init__(self, project_list: ProjectListPort, videos, get_profile: GetChannelProfile,
                 providers: ProviderService, budget: GetChannelBudget,
                 youtube: GetYouTubeChannel, config: GetPublicProjectConfig, *,
                 oauth_available: bool = False,
                 oauth_unavailable_reason: str | None = None):
        self.project_list = project_list
        self.videos = videos
        self.get_profile = get_profile
        self.providers = providers
        self.budget = budget
        self.youtube = youtube
        self.config = config
        # Fonte de verdade do wiring: o mesmo flag que decide se `begin_youtube_oauth` existe.
        # Sem app OAuth montado, o botão não pode prometer um consentimento que daria 503.
        self.oauth_available = oauth_available
        self.oauth_unavailable_reason = oauth_unavailable_reason

    def execute(self, project_id: str | None = None) -> ChannelsPageView:
        projects = tuple(self.project_list.projects())
        if project_id is None:
            project = self.videos.get_project(projects[0][0]) if projects else None
        else:
            project = self.videos.get_project(project_id)
            if project is None:
                raise ProjectNotFound(project_id)
        if project is None:
            return ChannelsPageView(projects=projects)

        profile = self.get_profile.execute(project.id)
        providers_error = None
        try:
            cards = tuple(self.providers.list(project.id))
        except ValueError:
            # Configuração legada pode conter chave não reconhecida. O catálogo não é inventado:
            # a página diz que está indisponível e por quê, sem repetir a chave (que pode ser segredo).
            cards = ()
            providers_error = ("a configuração de providers deste canal tem chave não reconhecida; "
                               "o catálogo fica indisponível até a configuração ser corrigida")
        budget = self.budget.execute(project.id)
        routes, failures = self._routing(project.id, budget.limits.economic_profile, cards)
        authorize_path = revoke_path = None
        oauth_reason = None
        if self.oauth_available:
            authorize_path = f"/studio/projects/{project.id}/youtube-oauth/authorize"
            revoke_path = f"/studio/projects/{project.id}/youtube-oauth/revoke"
        else:
            oauth_reason = self.oauth_unavailable_reason or OAUTH_UNAVAILABLE_REASON
        return ChannelsPageView(
            projects=projects,
            project=project,
            profile=profile,
            providers=cards,
            routes=routes,
            route_failures=failures,
            budget=budget,
            youtube=self.youtube.execute(project.id),
            public_config=dict(self.config.execute(project.id)["config"]),
            providers_error=providers_error,
            oauth_available=self.oauth_available,
            oauth_unavailable_reason=oauth_reason,
            oauth_authorize_path=authorize_path,
            oauth_revoke_path=revoke_path,
        )

    def _routing(self, project_id: str, economic_profile, cards: Sequence[ProviderCard]):
        """Roteamento real por porta; porta sem candidato vira motivo explícito, não provider falso."""
        routes: list[RoutingDecision] = []
        failures: list[tuple[ProviderKind, str]] = []
        for card in cards:
            try:
                decision = self.providers.route(project_id, card.kind, economic_profile)
            except NoProviderAvailable as exc:
                failures.append((card.kind, str(exc)))
            else:
                if all(r.kind is not decision.kind for r in routes):
                    routes.append(decision)
        return tuple(routes), tuple(failures)