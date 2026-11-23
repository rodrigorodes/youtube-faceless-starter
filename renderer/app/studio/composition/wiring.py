import os
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

# A raiz de composição é resolvida pelo módulo, não pelo nome importado: consumidores e testes
# fazem ``monkeypatch.setattr(composition, "build_google_oauth", ...)`` e a fiação precisa honrar
# o patch. Um ``from .providers import build_google_oauth`` congelaria a referência no import.
import app.studio.composition as _composition

from ..adapters.postgres.db import migrate
from ..domain.ids import InvalidId
from ..adapters.fetcher import HttpxFetcher
from ..adapters.postgres.budget_repo import PostgresPaidOperationRepository
from ..adapters.image_opencode import OpenCodeImage
from ..adapters.image_placeholder import PlaceholderImage
from ..adapters.image_stock import PexelsImage
from ..adapters.image_veo import VeoImage
from ..adapters.media_pexels import PexelsMediaFetcher, PexelsMediaSearch
from ..adapters.postgres.publish_repo import (PostgresApprovalRepository, PostgresPublicationIntentRepository,
                                             PostgresPublicationRepository)
from ..adapters.postgres.analytics_repo import PostgresAnalyticsRepository
from ..adapters.postgres.panel_repo import PostgresPanelRepository
from ..adapters.postgres.saas_repo import PostgresSaasRepository
from ..adapters.postgres.step_repo import PostgresStepRepository
from ..adapters.postgres.trend_repo import PostgresTrendRepository
from ..adapters.postgres.render_repo import PostgresRenderJobRepository
from ..adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from ..adapters.postgres.production_repo import build_postgres_production_run_repository
from ..adapters.postgres.category_repo import PostgresCategoryRepository
from ..adapters.postgres.analytics_learning_repo import PostgresAnalyticsLearningRepository
from ..adapters.channel_analytics import ChannelAnalyticsAdapter
from ..adapters.postgres.channel_repo import PostgresChannelProfileRepository
from ..adapters.postgres.visual_style_repo import PostgresVisualStyleRepository
from ..adapters.postgres.channel_budget_repo import (PostgresChannelBudgetRepository,
                                                    PostgresChannelUsageRepository)
from ..adapters.postgres.youtube_channel_repo import PostgresYouTubeChannelRepository
from ..adapters.postgres.youtube_identity_repo import (PostgresChannelAuthorizationRepository,
                                                       PostgresGoogleAccountRepository,
                                                       PostgresOAuthGrantRepository,
                                                       PostgresYouTubeChannelIdentityRepository)
from ..adapters.google_oauth import GoogleOAuthClient, google_oauth_from_client_secret
from ..adapters.secret_store import FileSecretStore
from ..adapters.token_env import EnvRefreshTokenProvider
from ..adapters.youtube_publisher import GoogleYouTubeUploader
from ..adapters.provider_probes import HttpReachableProbe, LocalProviderProbe
from ..adapters.youtube_trends import fetch_popular_trends, fetch_youtube_trends
from ..adapters.postgres.media_repo import PostgresAssetRepository, PostgresProductionLock
from ..adapters.thumbnail import PillowThumbnail
from ..adapters.qa_ffmpeg import FfmpegQa
from ..adapters.quality_ffmpeg import FfmpegOverlayVerifier, FfmpegQualityEvaluator, FfmpegQualityProbe
from ..adapters.quality_semantic import NotVerifiedSemanticChecker
from ..adapters.render_disabled import DisabledRenderer
from ..adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from ..adapters.storage import FileAssetStore, FileRenderStorage
from ..adapters.voice_piper import PiperVoice
from ..adapters.postgres.editorial_repo import (PostgresFactCheckRepository, PostgresScriptRepository,
                                               PostgresSnapshotRepository, PostgresUsageRepository)
from ..adapters.postgres.scene_duration_repo import PostgresSceneDurationRepository
from ..adapters.postgres.repo import PostgresVideoRepository
from ..adapters.text_demo import DemoText
from ..adapters.text_opencode import OpenCodeText
from ..application.config import ProjectConfig, ProviderNotFound, build, register
from ..application.ideas import ScoreIdeas
from ..application.analytics import Analytics
from ..application.analytics_collection import CollectMetrics
from ..application.analytics_dashboard import BuildAnalyticsDashboard
from ..application.analytics_learning import DecideRecommendation, RegisterExperiment
from ..application.panel import BuildPanel
from ..application.saas import (BuildTeamView, ChangeMemberRole, InviteMember, RegisterByokKey,
                                RemoveMember, ResolveActor, RevokeByokKey, RotateByokKey)
from ..application.trends import IngestTrends
from ..application.categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from ..application.channels import CreateChannelProfile, GetChannelProfile, ListChannelProfiles, UpdateChannelProfile
from ..application.channel_creation import CreateChannelTransactional
from ..application.channel_style_page import BuildChannelStylePage
from ..application.channels_page import BuildChannelsPage
from ..application.composition_view import BuildCompositionView
from ..application.styles import (ArchiveVisualStyle, CreateVisualStyle, GetVisualStyle, ListVisualStyles,
                                 UpdateVisualStyle, VisualStyleUsage)
from ..application.styles_page import BuildStylesPage
from ..application.video_style import BuildVideoStyleView, SetChannelStylePatch, SetVideoStyle, SetVideoStylePatch
from ..application.channel_budget import ChannelBudgetFloor, GetChannelBudget, SetChannelBudget
from ..application.providers import ProviderService
from ..application.secrets import GetPublicProjectConfig, SetPublicProjectConfig
from ..application.youtube_channels import (AssociateYouTubeChannel, DisconnectYouTubeChannel,
                                           GetYouTubeChannel)
from ..domain.effective_config import resolve_effective_config
from ..domain.provider import (CostEstimate, NoProviderAvailable, ProviderImplementation, ProviderKind,
                              ProviderSpecInvalid)
from ..domain.visual_style import resolve_style
from ..application.observability import BridgeAlerts, Resume, record_provider_decision
from ..application.publishing import (Approve, ClaimPublication, GetPreview, GetPublication, GetThumbnail, MarkFailed, MarkThumbnail, MarkUploaded,
                                       Publishing, RearmPublication, Reject, RetryPublication, SetUploadUri)
from ..application.publication_execution import (FallbackTokenProvider, MissingTokenProvider, ReconcilePublication,
                                                RunPublication, TargetChannelTokenProvider)
from ..application.channel_grant import EnsureGrantAccessToken
from ..application.youtube_oauth import (BeginConsent, CompleteConsent, EnsureAccessToken, GetChannelStatus,
                                        RefreshYouTubeChannel, RevokeConsent)
from ..application.connections import (BeginAccountConsent, CompleteAccountConsent, LinkStudioChannel,
                                      ListConnections, RevokeAuthorization, Unlink)
from ..domain.youtube_oauth import OAuthConfigurationError
from ..application.render import GetRender, GetRenderFile, Rendering, RunRender, StartRender
from ..application.scene_narration import RegenerateSceneNarration, SceneNarration
from ..application.render_cache import PlanRegeneration
from ..application.media import ListAssets, ListSceneCandidates, Media, PrepareStoryboard, ProduceAssets, SceneAssetFile, SetSceneBroll, SwapSceneMedia
from ..application.editorial import CostGuard, Editorial, GenerateScript, GetScript, IngestSource, ListSources, RunFactCheck
from ..application.longform import (AddScriptScene, ApproveScriptVersion, EditScriptScene, GenerateLongScript,
                                   GetScriptRevision, ListScriptRevisions, RemoveScriptScene, ReorderScriptScenes,
                                   RestoreScriptRevision)
from ..application.script_view import BuildScriptView
from ..application.budget import PaidOperationGuard
from ..application.production import (COORDINATOR_DAG, BudgetProjection, Production, ProductionMode, ProductionWorker,
                                     ProductionCoordinator, build_stage_handlers, frozen_provider_selection)
from ..application.advanced_page import BuildAdvancedView
from ..application.use_cases import ServiceUnavailable, UseCases

from .settings import CONNECT_OPTIONS, PING_TTL_SECONDS, RETRY_SECONDS, Settings
from .providers import (FREE_PROVIDERS, ProviderRouting, _configured_provider_spec,
                        _provider_implementations, _provider_probes)


def channel_guard_limits(videos, budgets):
    """Resolvedor de limites hard do canal para o guard de operação paga (F10-05).

    Devolve `(teto mensal, teto por vídeo)` do canal do vídeo, ou None para o guard usar os padrões
    das settings. Vídeo desconhecido/id inválido não bloqueia por si: cai no padrão.
    """
    def limits_for(video_id: str | None):
        if not video_id:
            return None
        try:
            video = videos.get_video(video_id)
        except InvalidId:
            return None
        if video is None:
            return None
        limits = budgets.get(video.project_id)
        return limits.guard_limits() if limits is not None else None
    return limits_for


def _active_style(styles, style_id):
    """Carrega um estilo pelo id, tolerando id estranho e tratando o **arquivado** como ausente.

    Defesa em profundidade da VS-05c: mesmo que um vínculo escape (canal/vídeo apontando para um
    estilo arquivado), ele não dirige render nenhum — um estilo arquivado conta como se não houvesse
    estilo, deixando o neutral (studio-default) ou o estilo do canal decidir.
    """
    if style_id is None:
        return None
    try:
        style = styles.get(style_id)
    except InvalidId:
        return None
    return None if style is None or style.archived else style


def _style_for_video(video, channels, styles):
    """VS-03/VS-05c: o estilo efetivo do render de um vídeo — precedência **vídeo > canal > neutro**.

    Resolve o caminho real: canal do projeto → ``channel_profiles.style_id`` (estilo herdado) **e**
    ``videos.style_id`` (override do vídeo, VS-02b) → ``VisualStyle`` → ``ResolvedStyle`` (snapshot
    versionado + motion/music/caption/palette). O override do vídeo tem precedência sobre o do canal;
    sem override, vale o do canal e, sem nenhum dos dois, devolve None — o renderer usa o bundle
    neutro. Estilo arquivado conta como ausente nos dois lados. Mesma tolerância do
    ``channel_guard_limits``: um id estranho não derruba o render.
    """
    try:
        profile = channels.get_by_project(video.project_id)
    except InvalidId:
        profile = None
    channel_style = _active_style(styles, profile.style_id if profile is not None else None)
    video_style = _active_style(styles, video.style_id)
    return resolve_style(profile, channel_style, override=video_style)


def _economic_profile_for(budgets, project_id):
    """Perfil econômico **declarado** do canal (`channel_budgets.economic_profile`), ou None.

    W0B.3/R9: o snapshot nascia sempre ``BALANCED``/``engine_default`` porque o resolvedor não
    recebia o perfil — o roteamento real, esse sim, lê o perfil do canal dinamicamente. Sem orçamento
    de canal devolve None (o domínio congela o default do motor, como antes); id estranho ou linha
    ausente não derruba o run, a mesma tolerância do ``channel_guard_limits``.
    """
    if budgets is None:
        return None
    try:
        limits = budgets.get(project_id)
    except InvalidId:
        return None
    return limits.economic_profile if limits is not None else None


def _effective_config_for(video, channels, styles, videos=None, budgets=None):
    """F03.T02/F05.T02: resolvedor da configuração efetiva ligado na composição.

    Recebe o `Video` já carregado (o coordenador entrega o agregado), resolve o canal do projeto
    (a mesma relação usada pelo render/estilo) e a biblioteca de estilos. Os overrides tipados de
    estilo entram aqui: o patch do canal vem do perfil e o do vídeo da sua própria linha
    (`get_video_style_patch`), sempre normalizados por `StylePatch`. A leitura é injetada e pura no
    domínio; nada aqui executa efeito nem grava: o snapshot só entra no banco dentro do
    `create_run`, na transação do run.

    W0B.3/R9: com `budgets`, a política econômica **declarada** do canal também é congelada no
    snapshot (`provider_policy.profile`), em vez de o snapshot afirmar sempre `BALANCED`.
    """
    try:
        profile = channels.get_by_project(video.project_id)
    except InvalidId:
        profile = None
    video_patch = None
    if videos is not None:
        stored = videos.get_video_style_patch(video.id)
        video_patch = stored.patch if stored is not None else None
    return resolve_effective_config(video=video, channel=profile, lookup_style=styles.get,
                                    video_patch=video_patch,
                                    channel_patch=profile.style_patch if profile is not None else None,
                                    provider_profile=_economic_profile_for(budgets, video.project_id))


def _voice_model(style) -> str | None:
    """O modelo de voz que o estilo declara (``params.voice.model``), ou None. Puro."""
    model = style.voice.get("model") if style is not None else None
    return model.strip() if isinstance(model, str) and model.strip() else None


def _voice_for_video(video, channels, styles, fallback, build_provider):
    """VS-06: a voz **efetiva** do render — precedência **estilo > projeto > default**.

    Resolve o estilo do vídeo pelo mesmo caminho da VS-05c (``_style_for_video``: canal + override
    do vídeo); se o estilo declara ``params.voice.model``, ele manda e o provider é construído
    **pelo registro** (``build_provider("voice", "piper:<modelo>")``), mantendo a validação num
    lugar só. Aceita o modelo com ou sem o prefixo ``piper:``. Sem voz no estilo, quem decide é o
    projeto (``fallback`` → ``provider_for("voice", ...)``, que resolve ``ProjectConfig.voice``:
    override do projeto > ``STUDIO_VOICE`` > default).

    O ``Voice`` devolvido carrega o **modelo efetivo** no atributo ``model``: é a mesma identidade
    que a síntese usa (``PiperVoice.voice_path`` deriva dela) e que o cache/ledger registram
    (``_voice_identity``), então a divergência entre "quem fala" e "quem é registrado" deixa de
    existir. Voz de estilo sem arquivo em ``/opt/voices`` falha no ``synthesize_speech`` dizendo
    **qual** modelo faltou — nunca cai para outra voz em silêncio.
    """
    model = _voice_model(_style_for_video(video, channels, styles))
    if model is None:
        return fallback(video.project_id)
    spec = model if ":" in model else f"piper:{model}"
    return build_provider("voice", spec)


def _voice_for_config(video, config, fallback, build_provider):
    """F03.T03/S8: a voz sai da **configuração efetiva congelada**, não de uma nova leitura.

    A seleção congelada do run vence; sem ela (run legado), ``config.voice.model`` — o modelo já
    mesclado pelas camadas criativas (patch do vídeo > canal > estilo) e congelado no snapshot —
    continua valendo. Sem voz declarada, o projeto decide (``fallback`` → ``provider_for("voice",
    ...)``) — o mesmo legado de antes. A composição é a única que conhece o registro de providers;
    o core só recebe o ``Voice`` resolvido.
    """
    selection = getattr(config, "provider_selection", None) if config is not None else None
    spec = selection.get("voice") if selection else None
    if spec:
        return build_provider("voice", spec)
    model = config.voice.get("model") if config is not None else None
    model = model.strip() if isinstance(model, str) and model.strip() else None
    if model is None:
        return fallback(video.project_id)
    spec = model if ":" in model else f"piper:{model}"
    return build_provider("voice", spec)


class Studio:
    """Inicializa o banco sob demanda. Sem banco, o app segue de pé em modo degradado."""

    def __init__(self, settings: Settings, environ: Mapping[str, str] | None = None, fetcher=None, executor=None, analyzer=None, youtube_fetcher=None, youtube_popular_fetcher=None, quality_evaluator=None):
        self.settings = settings
        self.environ = os.environ if environ is None else environ
        self._fetcher = fetcher or HttpxFetcher(settings.source_allowlist)
        self._youtube_fetcher = youtube_fetcher
        self._youtube_popular_fetcher = youtube_popular_fetcher
        self.bridge_alerts = BridgeAlerts()
        register("text", "opencode", lambda model: OpenCodeText(model, settings.bridge_token, settings.bridge_url))
        register("text", "demo", DemoText)
        register("image", "opencode", lambda model: OpenCodeImage(model, settings.bridge_token, settings.bridge_url, paid_estimate_usd=settings.paid_image_usd))
        register("image", "placeholder", PlaceholderImage)
        register("image", "stock", lambda model: PexelsImage(model, settings.pexels_key))
        register("image", "veo", lambda model: VeoImage(model, settings.veo_usd_per_second))
        register("search", "pexels", lambda model: PexelsMediaSearch(model, settings.pexels_key))
        register("voice", "piper", PiperVoice)
        # RP-032: a flag é disponibilidade do caminho baseado em plano, não dispatch dual —
        # o legado foi removido (emenda §14). Desligada, o renderer recusa o render.
        # RP-06b: é aqui — e só aqui — que o executor recebe o repositório versionado do plano e
        # a raiz do cache de artefatos: o reúso por fingerprint de conteúdo roda no caminho de
        # produção (RunRender → executor) sem contaminar domain/application com banco ou mídia.
        def _renderer(model: str):
            if not settings.render_plan_enabled:
                return DisabledRenderer(model)
            return PlanFfmpegRenderer(model, plans=PostgresRenderPlanRepository(self._connect),
                                      cache_root=settings.storage_root / "render-cache")
        register("renderer", "ffmpeg", _renderer)
        self._executor = executor or ThreadPoolExecutor(max_workers=settings.render_concurrency, thread_name_prefix="render")
        self._analyzer = analyzer or FfmpegQa()
        # O probe mede (ffprobe/ebur128) com o MESMO analisador do render; o avaliador junta a
        # medição à política pura. Passar o analisador como probe quebraria o ``measure``.
        self._quality_evaluator = quality_evaluator or FfmpegQualityEvaluator(
            FfmpegQualityProbe(self._analyzer),
            overlay_verifier=FfmpegOverlayVerifier(),
            semantic_checker=NotVerifiedSemanticChecker(),
        )
        self._use_cases: UseCases | None = None
        self._lock = threading.Lock()
        self._retry_at = 0.0  # backoff após falha de inicialização
        self._ping: tuple[bool, float] = (False, 0.0)  # (resultado, validade)

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.settings.database_url, connect_timeout=3, options=CONNECT_OPTIONS)
        except psycopg.OperationalError as exc:
            raise ServiceUnavailable("studio database unavailable") from exc

    def _connect_autocommit(self) -> psycopg.Connection:
        try:  # sessão própria do lock de produção: sem transação aberta enquanto dura a geração
            return psycopg.connect(self.settings.database_url, connect_timeout=3, options=CONNECT_OPTIONS, autocommit=True)
        except psycopg.OperationalError as exc:
            raise ServiceUnavailable("studio database unavailable") from exc

    def use_cases(self) -> UseCases | None:
        if self._use_cases is not None:
            return self._use_cases
        if not self.settings.database_url:
            return None
        with self._lock:
            if self._use_cases is None:
                if time.monotonic() < self._retry_at:
                    return None
                try:
                    with self._connect() as conn:
                        migrate(conn)
                except (ServiceUnavailable, psycopg.Error):
                    self._retry_at = time.monotonic() + RETRY_SECONDS
                    return None
                try:
                    self._use_cases = self._wire()
                except (ServiceUnavailable, psycopg.Error):  # o banco caiu entre a migração e a limpeza de jobs: tenta de novo depois
                    self._retry_at = time.monotonic() + RETRY_SECONDS
                    return None
        return self._use_cases

    def shutdown(self) -> None:
        """Não espera render em andamento (o SIGTERM não pode travar por minutos); o job fica para o reaper/próxima subida."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def recover_in_flight(self) -> tuple[str, ...]:
        """Religa no boot os runs de produção em voo que ficaram órfãos (PROD-03).

        Sem banco (ou sem a fiação de produção) é no-op e devolve vazio: a subida degrada como
        hoje. Chamado pelo `lifespan` em thread, depois da migração; o serviço re-dirige cada órfão
        pelo mesmo `submit` do `start`.
        """
        cases = self.use_cases()
        if cases is None or cases.production is None:
            return ()
        return cases.production.recover_in_flight()

    @property
    def quality_evaluator(self):
        """Porta de QA do render (RP-030) montada na raiz de composição.

        Junta a medição real (``FfmpegQualityProbe``: ffprobe/ebur128, com o mesmo
        ``FfmpegQa`` do render) à política pura (``PlanQualityEvaluator``/``domain.quality``).
        É a instância que o ``RunRender`` usa para produzir o relatório versionado da F6 e
        persistir em ``videos.qa_report`` (RP-07b: adoção concluída; o tipo legado foi
        aposentado).
        """
        return self._quality_evaluator

    def _build_provider(self, kind: str, spec: str):
        # Um candidato roteado pode chegar sem modelo (o catálogo só conhece o nome): o registro
        # exige o separador para escolher a factory e usa o modelo padrão do adaptador.
        if ":" not in spec:
            spec = f"{spec}:"
        name, sep, model = spec.partition(":")
        if sep and name == "opencode":
            if kind == "text":
                return OpenCodeText(model, self.settings.bridge_token, self.settings.bridge_url, alerts=self.bridge_alerts)
            if kind == "image":
                return OpenCodeImage(model, self.settings.bridge_token, self.settings.bridge_url,
                                     paid_estimate_usd=self.settings.paid_image_usd, alerts=self.bridge_alerts)
        return build(kind, spec)

    def _wire(self) -> UseCases:
        s, connect = self.settings, self._connect
        repo, snaps, scripts = PostgresVideoRepository(connect), PostgresSnapshotRepository(connect), PostgresScriptRepository(connect)
        usage, checks = PostgresUsageRepository(connect), PostgresFactCheckRepository(connect)

        budget_repo = PostgresChannelBudgetRepository(connect)
        implementations = _provider_implementations(s)
        probes = _provider_probes(s, implementations)
        providers_service = ProviderService(repo, self.environ, implementations, probes,
                                            production=s.provider_production)

        def budget_limits(project_id):
            if not project_id:
                return None
            try:
                return budget_repo.get(project_id)
            except InvalidId:
                return None  # vínculo inválido não inventa perfil: mantém o caminho legado

        # F06.T02: a execução consome a decisão econômica do canal (perfil -> candidato, motivo,
        # modelo/versão, tentativa). Sem perfil persistido, `provider_for` continua byte a byte
        # como antes. A auditoria usa a trilha de observabilidade existente (`studio.providers`).
        provider_routing = ProviderRouting(
            providers_service, self._build_provider,
            lambda kind, project_id: _configured_provider_spec(repo, self.environ, kind, project_id),
            budget_limits, production=s.provider_production)

        def provider_for(kind: str, project_id: str | None):
            return provider_routing(kind, project_id)

        def _frozen_selection_for(video, config):
            """S8: seleção efetiva por capacidade, resolvida UMA vez na criação do run.

            Usa o mesmo perfil/limites do roteamento vivo. A voz declarada pelo estilo criativo
            vence o roteamento (é o mesmo critério de `_voice_for_config`); as demais capacidades
            seguem a decisão do perfil. Sem candidato para uma capacidade, ela fica fora da
            seleção e o run cai no roteamento vivo só para ela.
            """
            limits = budget_limits(video.project_id)
            profile = getattr(limits, "economic_profile", None) if limits is not None else None
            max_cost = getattr(limits, "hard_video_usd", None) if limits is not None else None
            selection: dict[str, str] = {}
            for kind in ProviderKind:
                if kind is ProviderKind.SEARCH:
                    # W3.1: `search` é capacidade de catálogo sem chave em `Project.config`;
                    # não entra no congelamento de execução (não gera conteúdo no run).
                    continue
                if kind is ProviderKind.VOICE:
                    model = config.voice.get("model") if config is not None else None
                    model = model.strip() if isinstance(model, str) and model.strip() else None
                    if model is not None:
                        selection[kind.value] = model if ":" in model else f"piper:{model}"
                        continue
                try:
                    if profile is None:
                        spec = _configured_provider_spec(repo, self.environ, kind.value,
                                                         video.project_id)
                    else:
                        spec = providers_service.route(
                            video.project_id, kind, profile, max_cost_usd=max_cost,
                            production=s.provider_production).primary.spec
                except (ProviderNotFound, NoProviderAvailable):
                    continue
                selection[kind.value] = spec
            return selection or None

        def text_for(project_id: str | None):
            return provider_for("text", project_id)

        guard = CostGuard(usage, s.max_cost_video, s.max_cost_month)
        usage_repo = PostgresChannelUsageRepository(connect)
        youtube_repo = PostgresYouTubeChannelRepository(connect)
        # RP-016: o perfil do canal é a identidade versionada do render. Uma instância só,
        # reusada pela fiação do render (abaixo) e pela página de Canais.
        channel_repo = PostgresChannelProfileRepository(connect)
        # VS-03: a biblioteca de estilos; o render resolve o estilo do canal do projeto.
        style_repo = PostgresVisualStyleRepository(connect)
        secret_store = FileSecretStore(s.secrets_root or (s.storage_root / "secrets"))
        # YT-04a: a identidade de publicação nova (conta → autorizações → canais) tem repositórios
        # próprios; o vínculo validado também é o que o gate da publicação (YT-03) consulta.
        google_accounts = PostgresGoogleAccountRepository(connect)
        oauth_grants = PostgresOAuthGrantRepository(connect)
        youtube_identities = PostgresYouTubeChannelIdentityRepository(connect)
        channel_authorizations = PostgresChannelAuthorizationRepository(connect)

        paid_guard = None
        if s.budget_guard:  # caminhos pagos passam a exigir reserva; desligado por padrão até a operação estar pronta
            paid_guard = PaidOperationGuard(PostgresPaidOperationRepository(connect),
                                            Decimal(str(s.max_cost_month)), Decimal(str(s.max_cost_video)),
                                            limits_for=channel_guard_limits(repo, budget_repo))
        # F04: o contexto editorial (idioma, público, narrativa, pilares, CTA e duração) vem da
        # configuração efetiva do canal — a mesma resolução do run, sem segunda leitura nem cópia.
        # Sem canal/perfil, `EditorialContext` é o retrato legado e o prompt não muda.
        def editorial_for(video):
            return _effective_config_for(video, channel_repo, style_repo, repo, budget_repo)

        assets = PostgresAssetRepository(connect)
        asset_store = FileAssetStore(s.storage_root)
        # W3.1/W4.4: a busca de mídia e a materialização de um candidato existem quando há chave do
        # provedor (a capacidade `search` não entra na config por projeto). Sem chave, `list_candidates`
        # fica desligado e o caminho de candidato do `swap` recusa — o vínculo por `asset_id` continua.
        media_search = PexelsMediaSearch("pexels", s.pexels_key) if s.pexels_key else None
        media_fetcher = PexelsMediaFetcher("pexels") if s.pexels_key else None
        media = Media(
            storyboard=PrepareStoryboard(repo, scripts),
            produce=ProduceAssets(repo, scripts, assets, asset_store, guard, usage,
                                  image_for=lambda project_id: provider_for("image", project_id),
                                  lock=PostgresProductionLock(self._connect_autocommit), paid=paid_guard),
            list_assets=ListAssets(repo, scripts, assets),
            list_candidates=ListSceneCandidates(repo, scripts, media_search) if media_search else None,
            swap=SwapSceneMedia(repo, scripts, assets, asset_store, fetcher=media_fetcher, guard=guard, usage=usage),
            broll=SetSceneBroll(repo, scripts, assets),
            asset_file=SceneAssetFile(repo, scripts, assets, s.storage_root))
        jobs = PostgresRenderJobRepository(connect)
        steps = PostgresStepRepository(connect)
        # RP-06: persistência versionada do plano + índice de cache da regeneração seletiva.
        plan_regeneration = PlanRegeneration(PostgresRenderPlanRepository(connect))
        files = FileRenderStorage(s.storage_root)
        # Restrição: um processo só. Job QUEUED/RUNNING de um processo anterior não vai terminar: vira FAILED e `work/` é limpo
        # (retomada fina: P06). Com várias réplicas isto derrubaria jobs vivos de outro processo.
        jobs.fail_interrupted()
        steps.fail_interrupted_render()
        try:
            files.sweep_work()
        except OSError:
            pass
        # F03.T02/T03: o repositório do run é a leitura do snapshot congelado (e a escrita da
        # criação). Ele é construído aqui porque o `RunRender` precisa da MESMA porta: job de run
        # existente lê o snapshot, nunca re-resolve canal/estilo.
        run_repo = build_postgres_production_run_repository(connect, dag=COORDINATOR_DAG)
        # W4.3: duração real por cena e WAV durável para pré-escuta. Opcionais no RunRender, mas
        # fiados aqui para que o render passe a gravar a medida e o áudio de cada cena.
        scene_durations = PostgresSceneDurationRepository(connect)
        run = RunRender(repo, scripts, assets, jobs, files,
                         voice_for=lambda video: _voice_for_video(video, channel_repo, style_repo,
                                                                  lambda project_id: provider_for("voice", project_id),
                                                                  self._build_provider),
                         renderer_for=lambda project_id: provider_for("renderer", project_id), quality=self._quality_evaluator, steps=steps,
                         paid=paid_guard, plans=PostgresRenderPlanRepository(connect),
                         style_for=lambda video: _style_for_video(video, channel_repo, style_repo),
                         # F03.T03: no run existente vale o snapshot; no render avulso a config é
                         # resolvida UMA vez no início e alimenta voz e plano.
                         effective_config_for=lambda video: _effective_config_for(video, channel_repo, style_repo, repo, budget_repo),
                         config_store=run_repo,
                         voice_for_config=lambda video, config: _voice_for_config(
                             video, config, lambda project_id: provider_for("voice", project_id),
                             self._build_provider),
                         scene_durations=scene_durations,
                         scene_narration=files)
        # W4.3: a pré-escuta lê o WAV durável e o índice de cache; a regeneração usa a mesma voz
        # por vídeo do render e a mesma guarda de orçamento. Construídas depois do `run` porque
        # dependem de `files`/`scene_durations`.
        scene_narration = SceneNarration(repo, scripts, files, plans=PostgresRenderPlanRepository(connect),
                                         durations=scene_durations)
        regenerate_narration = RegenerateSceneNarration(
            repo, scripts,
            lambda video: _voice_for_video(video, channel_repo, style_repo,
                                           lambda project_id: provider_for("voice", project_id),
                                           self._build_provider),
            files, scene_durations, paid=paid_guard)
        editorial = Editorial(
            ingest=IngestSource(self._fetcher, snaps, repo, s.source_allowlist),
            generate=GenerateScript(repo, snaps, scripts, None, guard, usage, model_for=text_for,
                                    paid=paid_guard, editorial_for=editorial_for),
            get_script=GetScript(repo, scripts),
            fact_check=RunFactCheck(repo, snaps, scripts, checks, frozenset(s.allow_names)),
            score_ideas=ScoreIdeas(None, guard, usage, model_for=text_for, paid=paid_guard),
            long_generate=GenerateLongScript(repo, snaps, scripts, None, guard, usage, scripts,
                                             model_for=text_for, paid=paid_guard,
                                             allow_names=frozenset(s.allow_names),
                                             editorial_for=editorial_for),
            edit_script=EditScriptScene(repo, snaps, scripts, scripts, allow_names=frozenset(s.allow_names)),
            add_scene=AddScriptScene(repo, snaps, scripts, scripts, allow_names=frozenset(s.allow_names)),
            remove_scene=RemoveScriptScene(repo, snaps, scripts, scripts, allow_names=frozenset(s.allow_names)),
            reorder_scenes=ReorderScriptScenes(repo, snaps, scripts, scripts, allow_names=frozenset(s.allow_names)),
            approve_script=ApproveScriptVersion(repo, snaps, scripts, scripts, checks=checks,
                                                allow_names=frozenset(s.allow_names)),
            list_sources=ListSources(snaps, repo),
            scene_narration=scene_narration,
            regenerate_narration=regenerate_narration,
            restore_revision=RestoreScriptRevision(repo, snaps, scripts, scripts,
                                                   allow_names=frozenset(s.allow_names)),
            list_revisions=ListScriptRevisions(repo, scripts),
            get_revision=GetScriptRevision(repo, scripts))
        rendering = Rendering(start=StartRender(repo, scripts, assets, jobs, enqueue=lambda job_id: self._executor.submit(run.execute, job_id)),
                              get=GetRender(repo, jobs), file=GetRenderFile(repo, jobs, files))
        approvals, pubs = PostgresApprovalRepository(connect), PostgresPublicationRepository(connect)
        # Achado 1: a porta da intenção pede `get()` e a de aprovação também — um objeto só não
        # serve às duas. Sem este adaptador, o gate de publicação lia um `Approval` (sem `render_id`)
        # e `/publications/execute` estourava `AttributeError` no caminho real.
        intents = PostgresPublicationIntentRepository(approvals)
        oauth_client = _composition.build_google_oauth(s)
        if oauth_client is not None:
            get_channel_status = GetChannelStatus(youtube_repo, secret_store)
            begin_oauth = BeginConsent(oauth_client, secret_store, redirect_uri=s.google_oauth_redirect_uri)
            complete_oauth = CompleteConsent(oauth_client, youtube_repo, secret_store, redirect_uri=s.google_oauth_redirect_uri)
            refresh_channel = RefreshYouTubeChannel(EnsureAccessToken(oauth_client, youtube_repo, secret_store), get_channel_status)
            revoke_channel = RevokeConsent(oauth_client, youtube_repo, secret_store)
            # F01.T01: com destino configurado, o token da publicação vem da autorização (grant) do
            # canal do projeto. Sem destino, mantém-se o caminho legado explícito e restrito (cofre
            # por projeto → token.env), nunca como fallback de um canal com destino.
            legacy_tokens = FallbackTokenProvider(EnsureAccessToken(oauth_client, youtube_repo, secret_store),
                                                  EnvRefreshTokenProvider(oauth_client, s.token_env_path))
            grant_tokens = EnsureGrantAccessToken(channel_repo, channel_authorizations, oauth_grants,
                                                  secret_store, oauth_client)
            tokens = TargetChannelTokenProvider(channel_repo, grant_tokens, legacy_tokens)
            begin_account_consent = BeginAccountConsent(oauth_client, secret_store,
                                                        redirect_uri=s.google_oauth_redirect_uri)
            complete_account_consent = CompleteAccountConsent(
                oauth_client, google_accounts, oauth_grants, youtube_identities, channel_authorizations,
                secret_store, redirect_uri=s.google_oauth_redirect_uri)
            revoke_authorization = RevokeAuthorization(oauth_grants, channel_authorizations, youtube_identities,
                                                       secret_store, oauth_client)
        else:
            begin_oauth = complete_oauth = refresh_channel = revoke_channel = None
            begin_account_consent = complete_account_consent = None
            # Sem app OAuth não há como revogar no Google; a revogação local continua possível.
            revoke_authorization = RevokeAuthorization(oauth_grants, channel_authorizations, youtube_identities,
                                                       secret_store, None)
            tokens = MissingTokenProvider()
            grant_tokens = None
        uploader = GoogleYouTubeUploader()
        # YT-03: o gate de identidade compara o canal do token com o destino do canal do projeto,
        # resolvendo a autorização validada (channel_authorizations). Wiring só aqui.
        publish = RunPublication(repo, scripts, assets, jobs, snaps, approvals, intents, pubs, files, uploader, tokens,
                                 channels=channel_repo,
                                 authorizations=channel_authorizations,
                                 enabled=s.publication_enabled)
        reconcile = ReconcilePublication(repo, pubs, uploader, tokens)
        publishing = Publishing(
            approve=Approve(repo, scripts, approvals), reject=Reject(repo, approvals),
            claim=ClaimPublication(repo, scripts, assets, jobs, snaps, pubs, files,
                                   approvals=approvals, intents=intents, channels=channel_repo),
            set_uri=SetUploadUri(pubs), uploaded=MarkUploaded(pubs),
            failed=MarkFailed(pubs), thumbnail_set=MarkThumbnail(pubs), retry=RetryPublication(repo, pubs), get=GetPublication(repo, pubs),
            thumbnail=GetThumbnail(repo, scripts, assets, files, PillowThumbnail()),
            preview=GetPreview(repo, scripts, assets, jobs, snaps, approvals, pubs, files),
            publish=publish, reconcile=reconcile, rearm=RearmPublication(repo, pubs))
        trend_repo = PostgresTrendRepository(connect)
        ingest_trends = IngestTrends(trend_repo, repo, s.trend_hosts)
        category_repo = PostgresCategoryRepository(connect)
        list_categories = ListCategories(category_repo, repo)
        save_category = SaveCategory(category_repo, repo)
        delete_category = DeleteCategory(category_repo)
        refresh_trends = RefreshTrends(
            repo=category_repo,
            ingest=ingest_trends,
            token_env_path=s.token_env_path,
            videos_repo=repo,
            fetcher=self._youtube_fetcher or fetch_youtube_trends,
            popular_fetcher=self._youtube_popular_fetcher or fetch_popular_trends,
            environ=self.environ,
        )
        # O coordenador roda o render em linha (enqueue no-op); a fila de render HTTP continua a mesma.
        coordinator_start = StartRender(repo, scripts, assets, jobs, enqueue=lambda job_id: None)
        handlers = build_stage_handlers(editorial=editorial, media=media, start_render=coordinator_start,
                                        run_render=run, videos=repo, jobs=jobs, assets=assets, approvals=approvals,
                                        publish=publish)
        # Piso medido do gasto mensal (não é previsão): só com o guard hard ligado o modo guardado
        # pode dispensar a pausa intermediária.
        # F01.T03: piso medido no ESCOPO DO CANAL (não no gasto global) e com o teto das settings
        # como limite superior. O guard hard recebe os dois escopos via `channel_guard_limits`.
        budget = ChannelBudgetFloor(usage_repo, repo, budget_repo,
                                    default_ceiling_usd=Decimal(str(s.max_cost_month))) if s.budget_guard else None
        coordinator = ProductionCoordinator(run_repo, handlers=handlers, mode=s.production_mode, budget=budget,
                                            videos=repo, config_store=run_repo)
        worker = ProductionWorker(coordinator)
        # F03.T02: resolução única, antes do run; o snapshot é gravado pelo `create_run` (mesma
        # transação). A leitura para retomada/retry/painel vem da mesma porta (`run_config`).
        production = Production(coordinator=coordinator, worker=worker,
                                submit=lambda run_id: self._executor.submit(worker.work, run_id),
                                in_flight=run_repo,
                                effective_config_for=lambda video: _effective_config_for(video, channel_repo, style_repo, repo, budget_repo),
                                config_store=run_repo,
                                provider_selection_for=_frozen_selection_for)
        analytics_learning_repo = PostgresAnalyticsLearningRepository(connect)
        analytics_dashboard = BuildAnalyticsDashboard(analytics_learning_repo)
        analytics_collection = CollectMetrics(
            ChannelAnalyticsAdapter(youtube_repo, secret_store, targets=channel_repo,
                                    grant_tokens=grant_tokens), analytics_learning_repo)
        analytics_decide = DecideRecommendation(analytics_learning_repo)
        analytics_register_experiment = RegisterExperiment(analytics_learning_repo)
        panel_repo = PostgresPanelRepository(connect)
        panel = BuildPanel(panel_repo, s.max_cost_month, lambda: datetime.now(timezone.utc), trends=trend_repo, categories_repo=category_repo, free_providers=FREE_PROVIDERS)
        saas_repo = PostgresSaasRepository(connect)
        saas_clock = lambda: datetime.now(timezone.utc)
        team_view = BuildTeamView(saas_repo, saas_clock, free_providers=FREE_PROVIDERS)
        script_view = BuildScriptView(repo, snaps, scripts, scripts, checks=checks, allow_names=frozenset(s.allow_names))
        channel_budget = GetChannelBudget(
            budget_repo, repo, usage_repo,
            default_hard_monthly=Decimal(str(s.max_cost_month)),
            default_hard_video=Decimal(str(s.max_cost_video)))
        youtube_channel = GetYouTubeChannel(youtube_repo, secret_store)
        project_config = GetPublicProjectConfig(repo)
        set_project_config = SetPublicProjectConfig(repo, implementations)
        # F05.T04: a personalização do canal resolve a configuração efetiva no domínio; a tela
        # não recalcula precedência nem copia parâmetros da biblioteca.
        channel_style_page = BuildChannelStylePage(channel_repo, style_repo)
        set_channel_style_patch = SetChannelStylePatch(channel_repo)
        channels_page = BuildChannelsPage(panel_repo, repo, GetChannelProfile(channel_repo, repo),
                                          providers_service, channel_budget, youtube_channel, project_config,
                                          oauth_available=oauth_client is not None,
                                          list_styles=ListVisualStyles(style_repo),
                                          get_style=GetVisualStyle(style_repo))
        # VS-05a: a biblioteca de estilos é a projeção da tela de Estilos (lista + uso medido).
        styles_page = BuildStylesPage(style_repo)
        # YT-04a: Conexões (serviço + API). A página "Conexões" é a YT-04b, outra fatia.
        list_connections = ListConnections(google_accounts, oauth_grants, youtube_identities,
                                           channel_authorizations, channel_repo, secret_store)
        link_studio_channel = LinkStudioChannel(channel_repo, youtube_identities)
        unlink_studio_channel = Unlink(channel_repo)
        # VS-05b: a tela do vídeo lê o override real (o canal herda, o vídeo pode sobrepor).
        video_style_view = BuildVideoStyleView(repo, channel_repo, style_repo)
        return UseCases.from_repo(repo, editorial, media, rendering, publishing,
                                  Analytics(PostgresAnalyticsRepository(connect)), Resume(repo, rendering.start),
                                  panel=panel, ingest_trends=ingest_trends, trends_repo=trend_repo,
                                  categories_repo=category_repo, list_categories=list_categories,
                                  save_category=save_category, delete_category=delete_category,
                                  refresh_trends=refresh_trends,
                                  channel_profiles_repo=channel_repo,
                                  create_channel_profile=CreateChannelProfile(channel_repo, repo),
                                  get_channel_profile=GetChannelProfile(channel_repo, repo),
                                  update_channel_profile=UpdateChannelProfile(channel_repo),
                                  list_channel_profiles=ListChannelProfiles(channel_repo),
production=production, script_view=script_view,
                                  providers=providers_service,
                                  get_channel_budget=channel_budget,
                                  set_channel_budget=SetChannelBudget(budget_repo, repo),
                                  get_youtube_channel=youtube_channel,
                                  associate_youtube_channel=AssociateYouTubeChannel(youtube_repo, secret_store),
                                  disconnect_youtube_channel=DisconnectYouTubeChannel(youtube_repo, secret_store),
                                  get_project_config=project_config,
                                  set_project_config=set_project_config,
                                  channels_page=channels_page,
                                  channel_style_page=channel_style_page,
                                  set_channel_style_patch=set_channel_style_patch,
                                  team_view=team_view,
                                  analytics_repo=analytics_learning_repo,
                                  analytics_dashboard=analytics_dashboard,
                                  analytics_collection=analytics_collection,
                                  analytics_decide=analytics_decide,
                                  analytics_register_experiment=analytics_register_experiment,
                                  begin_youtube_oauth=begin_oauth, complete_youtube_oauth=complete_oauth,
                                  refresh_youtube_channel=refresh_channel, revoke_youtube_channel=revoke_channel,
                                  list_connections=list_connections, begin_account_consent=begin_account_consent,
                                  complete_account_consent=complete_account_consent,
                                  revoke_authorization=revoke_authorization,
                                  link_studio_channel=link_studio_channel, unlink_studio_channel=unlink_studio_channel,
                                  resolve_actor=ResolveActor(saas_repo),
                                  invite_member=InviteMember(saas_repo, saas_clock),
                                  change_member_role=ChangeMemberRole(saas_repo),
                                  remove_member=RemoveMember(saas_repo),
                                  register_byok_key=RegisterByokKey(saas_repo, secret_store, saas_clock),
                                  rotate_byok_key=RotateByokKey(saas_repo, secret_store, saas_clock),
                                  revoke_byok_key=RevokeByokKey(saas_repo, secret_store, saas_clock),
                                  plan_regeneration=plan_regeneration,
                                  create_visual_style=CreateVisualStyle(style_repo),
                                  get_visual_style=GetVisualStyle(style_repo),
                                  list_visual_styles=ListVisualStyles(style_repo),
                                  update_visual_style=UpdateVisualStyle(style_repo),
                                  archive_visual_style=ArchiveVisualStyle(style_repo),
                                  visual_style_usage=VisualStyleUsage(style_repo),
                                  styles_page=styles_page,
                                  set_video_style=SetVideoStyle(repo),
                                  set_video_style_patch=SetVideoStylePatch(repo),
                                  video_style_view=video_style_view,
                                  style_repo=style_repo,
                                  advanced_page=BuildAdvancedView(providers_service, panel_repo),
                                  composition_view=BuildCompositionView(PostgresRenderPlanRepository(connect)),
                                  create_channel_transactional=CreateChannelTransactional(connect))

    def ping(self) -> bool:
        ok, valid_until = self._ping
        if time.monotonic() < valid_until:
            return ok
        ok = self._check()
        self._ping = (ok, time.monotonic() + PING_TTL_SECONDS)
        return ok

    def _check(self) -> bool:
        if self.use_cases() is None:
            return False
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except (ServiceUnavailable, psycopg.Error):
            return False
