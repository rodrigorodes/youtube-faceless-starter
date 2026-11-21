"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos."""
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

from .adapters.postgres.db import migrate
from .domain.ids import InvalidId
from .adapters.fetcher import HttpxFetcher
from .adapters.postgres.budget_repo import PostgresPaidOperationRepository
from .adapters.image_opencode import OpenCodeImage
from .adapters.image_placeholder import PlaceholderImage
from .adapters.image_stock import PexelsImage
from .adapters.image_veo import VeoImage
from .adapters.postgres.publish_repo import PostgresApprovalRepository, PostgresPublicationRepository
from .adapters.postgres.analytics_repo import PostgresAnalyticsRepository
from .adapters.postgres.panel_repo import PostgresPanelRepository
from .adapters.postgres.saas_repo import PostgresSaasRepository
from .adapters.postgres.step_repo import PostgresStepRepository
from .adapters.postgres.trend_repo import PostgresTrendRepository
from .adapters.postgres.render_repo import PostgresRenderJobRepository
from .adapters.postgres.render_plan_repo import PostgresRenderPlanRepository
from .adapters.postgres.production_repo import build_postgres_production_run_repository
from .adapters.postgres.category_repo import PostgresCategoryRepository
from .adapters.postgres.analytics_learning_repo import PostgresAnalyticsLearningRepository
from .adapters.channel_analytics import ChannelAnalyticsAdapter
from .adapters.postgres.channel_repo import PostgresChannelProfileRepository
from .adapters.postgres.visual_style_repo import PostgresVisualStyleRepository
from .adapters.postgres.channel_budget_repo import (PostgresChannelBudgetRepository,
                                                    PostgresChannelUsageRepository)
from .adapters.postgres.youtube_channel_repo import PostgresYouTubeChannelRepository
from .adapters.postgres.youtube_identity_repo import PostgresChannelAuthorizationRepository
from .adapters.google_oauth import GoogleOAuthClient, google_oauth_from_client_secret
from .adapters.secret_store import FileSecretStore
from .adapters.token_env import EnvRefreshTokenProvider
from .adapters.youtube_publisher import GoogleYouTubeUploader
from .adapters.provider_probes import HttpReachableProbe, LocalProviderProbe
from .adapters.youtube_trends import fetch_popular_trends, fetch_youtube_trends
from .adapters.postgres.media_repo import PostgresAssetRepository, PostgresProductionLock
from .adapters.thumbnail import PillowThumbnail
from .adapters.qa_ffmpeg import FfmpegQa
from .adapters.quality_ffmpeg import FfmpegQualityEvaluator, FfmpegQualityProbe
from .adapters.render_disabled import DisabledRenderer
from .adapters.render_plan_ffmpeg import PlanFfmpegRenderer
from .adapters.storage import FileAssetStore, FileRenderStorage
from .adapters.voice_piper import PiperVoice
from .adapters.postgres.editorial_repo import (PostgresFactCheckRepository, PostgresScriptRepository,
                                               PostgresSnapshotRepository, PostgresUsageRepository)
from .adapters.postgres.repo import PostgresVideoRepository
from .adapters.text_demo import DemoText
from .adapters.text_opencode import OpenCodeText
from .application.config import ProjectConfig, ProviderNotFound, build, register
from .application.ideas import ScoreIdeas
from .application.analytics import Analytics
from .application.analytics_collection import CollectMetrics
from .application.analytics_dashboard import BuildAnalyticsDashboard
from .application.analytics_learning import DecideRecommendation, RegisterExperiment
from .application.panel import BuildPanel
from .application.saas import (BuildTeamView, ChangeMemberRole, InviteMember, RegisterByokKey,
                                RemoveMember, ResolveActor, RevokeByokKey, RotateByokKey)
from .application.trends import IngestTrends
from .application.categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from .application.channels import CreateChannelProfile, GetChannelProfile, ListChannelProfiles, UpdateChannelProfile
from .application.channels_page import BuildChannelsPage
from .application.channel_budget import GetChannelBudget, SetChannelBudget
from .application.providers import ProviderService
from .application.secrets import GetPublicProjectConfig, SetPublicProjectConfig
from .application.youtube_channels import (AssociateYouTubeChannel, DisconnectYouTubeChannel,
                                           GetYouTubeChannel)
from .domain.provider import CostEstimate, ProviderImplementation, ProviderKind
from .domain.visual_style import resolve_style
from .application.observability import BridgeAlerts, Resume
from .application.publishing import (Approve, ClaimPublication, GetPreview, GetPublication, GetThumbnail, MarkFailed, MarkThumbnail, MarkUploaded,
                                       Publishing, Reject, RetryPublication, SetUploadUri)
from .application.publication_execution import (FallbackTokenProvider, MissingTokenProvider, ReconcilePublication,
                                                RunPublication)
from .application.youtube_oauth import (BeginConsent, CompleteConsent, EnsureAccessToken, GetChannelStatus,
                                        RefreshYouTubeChannel, RevokeConsent)
from .domain.youtube_oauth import OAuthConfigurationError
from .application.render import GetRender, GetRenderFile, Rendering, RunRender, StartRender
from .application.render_cache import PlanRegeneration
from .application.media import ListAssets, Media, PrepareStoryboard, ProduceAssets
from .application.editorial import CostGuard, Editorial, GenerateScript, GetScript, IngestSource, RunFactCheck
from .application.longform import ApproveScriptVersion, EditScriptScene, GenerateLongScript
from .application.script_view import BuildScriptView
from .application.budget import PaidOperationGuard
from .application.production import (COORDINATOR_DAG, BudgetProjection, Production, ProductionMode, ProductionWorker,
                                     ProductionCoordinator, build_stage_handlers)
from .application.use_cases import ServiceUnavailable, UseCases

DEFAULT_ALLOWLIST = ("amsterdam-dance-event.nl",)
DEFAULT_ALLOW_NAMES = ("amsterda",)  # exônimo pt-BR de Amsterdam


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    items = tuple(x.strip().lower() for x in (value or "").split(",") if x.strip())
    return items or default


def _cap(value: str | None, default: float) -> float:
    try:
        number = float(value) if value not in (None, "") else default
    except ValueError:
        return default
    return number if number == number and 0 <= number < float("inf") else default


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _production_mode(value: str | None) -> ProductionMode:
    try:
        return ProductionMode((value or ProductionMode.INTERACTIVE.value).strip().upper())
    except ValueError:
        return ProductionMode.INTERACTIVE


class _ChannelBudgetFloor:
    """Teto soft do canal para o modo guardado do coordenador (F10-05).

    O limite hard é do guard de operação paga; aqui o soft decide a pausa humana. O gasto medido é
    global (piso conservador — superestimar é seguro): sem budget de canal, vale o teto das settings.
    """

    def __init__(self, usage, videos, budgets, default_ceiling_usd: Decimal):
        self.usage = usage
        self.videos = videos
        self.budgets = budgets
        self.default_ceiling_usd = default_ceiling_usd

    def project(self, run, next_stage) -> BudgetProjection:
        ceiling = self.default_ceiling_usd
        video = self.videos.get_video(run.video_id) if run.video_id else None
        if video is not None:
            limits = self.budgets.get(video.project_id)
            if limits is not None:
                ceiling = limits.soft_monthly_usd
        return BudgetProjection(projected_usd=Decimal(str(self.usage.spent_month())), ceiling_usd=ceiling)


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


def _style_for_project(project_id, channels, styles):
    """VS-03/RP-016: o estilo **resolvido** do render é o do canal do projeto.

    Resolve o caminho real: canal do projeto → ``style_id`` → ``VisualStyle`` → ``ResolvedStyle``
    (snapshot versionado + motion/music). Sem canal, sem ``style_id`` ou estilo inexistente,
    devolve None — o renderer usa o bundle neutro. Mesma tolerância do ``channel_guard_limits``:
    um id estranho não derruba o render.
    """
    try:
        profile = channels.get_by_project(project_id)
    except InvalidId:
        return None
    if profile is None or profile.style_id is None:
        return None
    try:
        style = styles.get(profile.style_id)
    except InvalidId:
        return None
    return resolve_style(profile, style)


def build_google_oauth(settings: "Settings",
                       transport=None) -> GoogleOAuthClient | None:
    """Monta o cliente OAuth a partir do client secret **no caminho original** (somente leitura).

    App ausente/inválido não derruba a composição: devolve None e a API responde 503 com motivo.
    """
    if settings.google_client_secret_file is None:
        return None
    try:
        return google_oauth_from_client_secret(settings.google_client_secret_file,
                                               redirect_uri=settings.google_oauth_redirect_uri,
                                               transport=transport)
    except (OAuthConfigurationError, OSError):
        return None


def _provider_implementations(s: "Settings") -> list[ProviderImplementation]:
    """Implementações registradas e o que cada uma é capaz de fazer (F10-03).

    `validated=False` quando falta credencial ou homologação: o catálogo mostra UNAVAILABLE.
    """
    bridge_ok = bool(s.bridge_token)
    pexels_ok = bool(s.pexels_key)
    return [
        ProviderImplementation(ProviderKind.TEXT, "opencode",
                               capabilities=("text.generate", "text.json"),
                               cost=CostEstimate.unknown(note="preço do bridge"), quality=4,
                               validated=bridge_ok, reason=None if bridge_ok else "OPENCODE_BRIDGE_TOKEN ausente"),
        ProviderImplementation(ProviderKind.TEXT, "demo", capabilities=("text.generate",),
                               cost=CostEstimate.free(note="texto determinístico local"), quality=1,
                               validated=True),
        ProviderImplementation(ProviderKind.IMAGE, "opencode", capabilities=("image.generate",),
                               cost=CostEstimate.estimate(s.paid_image_usd, note="por imagem"),
                               quality=4, validated=bridge_ok,
                               reason=None if bridge_ok else "OPENCODE_BRIDGE_TOKEN ausente"),
        ProviderImplementation(ProviderKind.IMAGE, "placeholder", capabilities=("image.generate",),
                               cost=CostEstimate.free(note="placeholder local"), quality=1, validated=True),
        ProviderImplementation(ProviderKind.IMAGE, "stock", capabilities=("image.generate",),
                               cost=CostEstimate.free(note="Pexels com licença"), quality=3,
                               validated=pexels_ok, reason=None if pexels_ok else "PEXELS_API_KEY ausente"),
        ProviderImplementation(ProviderKind.IMAGE, "veo", capabilities=("image.generate",),
                               cost=CostEstimate.estimate(s.veo_usd_per_second, note="por segundo"),
                               quality=5, validated=False, reason="provedor experimental, sem homologação"),
        ProviderImplementation(ProviderKind.VOICE, "piper", capabilities=("voice.speak",),
                               cost=CostEstimate.free(note="síntese local"), quality=3, validated=True),
        ProviderImplementation(ProviderKind.RENDERER, "ffmpeg", capabilities=("render.video",),
                               cost=CostEstimate.free(note="render local"), quality=4, validated=True),
    ]


def _provider_probes(s: "Settings", implementations) -> dict[tuple[str, str], object]:
    probes: dict[tuple[str, str], object] = {}
    local = {"demo", "placeholder", "piper", "ffmpeg"}
    for impl in implementations:
        if not impl.validated:
            continue
        if impl.name == "opencode":
            probes[(impl.kind.value, impl.name)] = HttpReachableProbe(
                f"{s.bridge_url.rstrip('/')}/health", timeout=3.0)
        elif impl.name in local:
            probes[(impl.kind.value, impl.name)] = LocalProviderProbe()
    return probes


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    storage_root: Path = Path("/data")
    source_allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST
    allow_names: tuple[str, ...] = DEFAULT_ALLOW_NAMES
    max_cost_video: float = 0.0   # gasto pago só com o teto do vídeo liberado explicitamente
    max_cost_month: float = 15.0  # teto mensal do projeto (US$ 15)
    bridge_token: str = ""
    bridge_url: str = "http://host.docker.internal:8787"
    pexels_key: str = ""
    paid_image_usd: float = 0.05        # estimativa por imagem de modelo não ':free' (o guard decide)
    veo_usd_per_second: float = 0.40    # Veo 3.1 (conferido em out/2026); clipe de 8 s
    render_concurrency: int = 1         # renders simultâneos (1 não satura o Lenovo)
    trend_hosts: tuple[str, ...] = ("www.googleapis.com", "www.youtube.com")
    token_env_path: Path = Path("credentials/token.env")
    budget_guard: bool = False  # liga a reserva preventiva de orçamento nos caminhos pagos (STUDIO_BUDGET_GUARD=1)
    production_mode: ProductionMode = ProductionMode.INTERACTIVE  # modo do coordenador (STUDIO_PRODUCTION_MODE)
    secrets_root: Path | None = None  # cofre de segredos (F10-07); None = <storage_root>/secrets
    google_client_secret_file: Path | None = None  # app OAuth web do Google (F8-05); lido no lugar, nunca copiado
    google_oauth_redirect_uri: str = "http://localhost:8000/studio/oauth/callback"
    # RP-032: disponibilidade do caminho baseado em plano. Não é um dispatch dual (o legado
    # foi removido): desligar recusa o render e a volta é o redeploy da imagem anterior.
    render_plan_enabled: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets_root = env.get("STUDIO_SECRETS_ROOT") or None
        return cls(env.get("STUDIO_DATABASE_URL") or None, Path(env.get("STUDIO_STORAGE_ROOT", "/data")),
                   _csv(env.get("STUDIO_SOURCE_ALLOWLIST"), DEFAULT_ALLOWLIST), _csv(env.get("STUDIO_ALLOW_NAMES"), DEFAULT_ALLOW_NAMES),
                   _cap(env.get("MAX_COST_USD_PER_VIDEO"), 0.0), _cap(env.get("MAX_COST_USD_PER_MONTH"), 15.0),
                   env.get("OPENCODE_BRIDGE_TOKEN", ""), env.get("OPENCODE_BRIDGE_URL") or "http://host.docker.internal:8787",
                   env.get("PEXELS_API_KEY", ""), _cap(env.get("STUDIO_PAID_IMAGE_USD"), 0.05), _cap(env.get("STUDIO_VEO_USD_PER_SECOND"), 0.40),
                   max(1, min(4, int(_cap(env.get("RENDER_CONCURRENCY"), 1)))),
                   _csv(env.get("STUDIO_TREND_SOURCES"), ("www.googleapis.com", "www.youtube.com")),
                   Path(env.get("STUDIO_TOKEN_ENV_PATH", "credentials/token.env")), _flag(env.get("STUDIO_BUDGET_GUARD")),
                   _production_mode(env.get("STUDIO_PRODUCTION_MODE")),
                   Path(secrets_root) if secrets_root else None,
                   Path(env["STUDIO_GOOGLE_CLIENT_SECRET_FILE"]) if env.get("STUDIO_GOOGLE_CLIENT_SECRET_FILE") else None,
                   env.get("STUDIO_GOOGLE_OAUTH_REDIRECT_URI") or "http://localhost:8000/studio/oauth/callback",
                   _flag(env.get("STUDIO_RENDER_PLAN_ENABLED", "1")))


RETRY_SECONDS = 5.0
PING_TTL_SECONDS = 5.0
CONNECT_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=15000"  # nenhuma consulta espera para sempre


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
        self._quality_evaluator = quality_evaluator or FfmpegQualityEvaluator(FfmpegQualityProbe(self._analyzer))
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

        def provider_for(kind: str, project_id: str | None):
            project = repo.get_project(project_id) if project_id else None
            try:
                spec = getattr(ProjectConfig.resolve(project.config if project else {}, self.environ), kind)
            except ValueError as exc:
                raise ProviderNotFound(str(exc)) from exc
            return self._build_provider(kind, spec)

        def text_for(project_id: str | None):
            return provider_for("text", project_id)

        guard = CostGuard(usage, s.max_cost_video, s.max_cost_month)
        budget_repo = PostgresChannelBudgetRepository(connect)
        usage_repo = PostgresChannelUsageRepository(connect)
        youtube_repo = PostgresYouTubeChannelRepository(connect)
        # RP-016: o perfil do canal é a identidade versionada do render. Uma instância só,
        # reusada pela fiação do render (abaixo) e pela página de Canais.
        channel_repo = PostgresChannelProfileRepository(connect)
        # VS-03: a biblioteca de estilos; o render resolve o estilo do canal do projeto.
        style_repo = PostgresVisualStyleRepository(connect)
        secret_store = FileSecretStore(s.secrets_root or (s.storage_root / "secrets"))

        paid_guard = None
        if s.budget_guard:  # caminhos pagos passam a exigir reserva; desligado por padrão até a operação estar pronta
            paid_guard = PaidOperationGuard(PostgresPaidOperationRepository(connect),
                                            Decimal(str(s.max_cost_month)), Decimal(str(s.max_cost_video)),
                                            limits_for=channel_guard_limits(repo, budget_repo))
        editorial = Editorial(
            ingest=IngestSource(self._fetcher, snaps, repo, s.source_allowlist),
            generate=GenerateScript(repo, snaps, scripts, None, guard, usage, model_for=text_for, paid=paid_guard),
            get_script=GetScript(repo, scripts),
            fact_check=RunFactCheck(repo, snaps, scripts, checks, frozenset(s.allow_names)),
            score_ideas=ScoreIdeas(None, guard, usage, model_for=text_for, paid=paid_guard),
            long_generate=GenerateLongScript(repo, snaps, scripts, None, guard, usage, scripts,
                                             model_for=text_for, paid=paid_guard,
                                             allow_names=frozenset(s.allow_names)),
            edit_script=EditScriptScene(repo, snaps, scripts, scripts, allow_names=frozenset(s.allow_names)),
            approve_script=ApproveScriptVersion(repo, snaps, scripts, scripts, checks=checks,
                                                allow_names=frozenset(s.allow_names)))
        assets = PostgresAssetRepository(connect)
        media = Media(
            storyboard=PrepareStoryboard(repo, scripts),
            produce=ProduceAssets(repo, scripts, assets, FileAssetStore(s.storage_root), guard, usage,
                                  image_for=lambda project_id: provider_for("image", project_id),
                                  lock=PostgresProductionLock(self._connect_autocommit), paid=paid_guard),
            list_assets=ListAssets(repo, scripts, assets))
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
        run = RunRender(repo, scripts, assets, jobs, files, voice_for=lambda project_id: provider_for("voice", project_id),
                         renderer_for=lambda project_id: provider_for("renderer", project_id), quality=self._quality_evaluator, steps=steps,
                         paid=paid_guard, plans=PostgresRenderPlanRepository(connect),
                         style_for=lambda project_id: _style_for_project(project_id, channel_repo, style_repo))
        rendering = Rendering(start=StartRender(repo, scripts, assets, jobs, enqueue=lambda job_id: self._executor.submit(run.execute, job_id)),
                              get=GetRender(repo, jobs), file=GetRenderFile(repo, jobs, files))
        approvals, pubs = PostgresApprovalRepository(connect), PostgresPublicationRepository(connect)
        oauth_client = build_google_oauth(s)
        if oauth_client is not None:
            get_channel_status = GetChannelStatus(youtube_repo, secret_store)
            begin_oauth = BeginConsent(oauth_client, secret_store, redirect_uri=s.google_oauth_redirect_uri)
            complete_oauth = CompleteConsent(oauth_client, youtube_repo, secret_store, redirect_uri=s.google_oauth_redirect_uri)
            refresh_channel = RefreshYouTubeChannel(EnsureAccessToken(oauth_client, youtube_repo, secret_store), get_channel_status)
            revoke_channel = RevokeConsent(oauth_client, youtube_repo, secret_store)
            tokens = FallbackTokenProvider(EnsureAccessToken(oauth_client, youtube_repo, secret_store),
                                           EnvRefreshTokenProvider(oauth_client, s.token_env_path))
        else:
            begin_oauth = complete_oauth = refresh_channel = revoke_channel = None
            tokens = MissingTokenProvider()
        uploader = GoogleYouTubeUploader()
        # YT-03: o gate de identidade compara o canal do token com o destino do canal do projeto,
        # resolvendo a autorização validada (channel_authorizations). Wiring só aqui.
        publish = RunPublication(repo, scripts, assets, jobs, snaps, approvals, approvals, pubs, files, uploader, tokens,
                                 channels=channel_repo,
                                 authorizations=PostgresChannelAuthorizationRepository(connect))
        reconcile = ReconcilePublication(repo, pubs, uploader, tokens)
        publishing = Publishing(
            approve=Approve(repo, scripts, approvals), reject=Reject(repo, approvals),
            claim=ClaimPublication(repo, scripts, assets, jobs, snaps, pubs, files), set_uri=SetUploadUri(pubs), uploaded=MarkUploaded(pubs),
            failed=MarkFailed(pubs), thumbnail_set=MarkThumbnail(pubs), retry=RetryPublication(repo, pubs), get=GetPublication(repo, pubs),
            thumbnail=GetThumbnail(repo, scripts, assets, files, PillowThumbnail()),
            preview=GetPreview(repo, scripts, assets, jobs, snaps, approvals, pubs, files),
            publish=publish, reconcile=reconcile)
        trend_repo = PostgresTrendRepository(connect)
        ingest_trends = IngestTrends(trend_repo, repo, s.trend_hosts)
        category_repo = PostgresCategoryRepository(connect)
        list_categories = ListCategories(category_repo, repo)
        save_category = SaveCategory(category_repo, repo)
        delete_category = DeleteCategory(category_repo)
        implementations = _provider_implementations(s)
        probes = _provider_probes(s, implementations)
        refresh_trends = RefreshTrends(
            repo=category_repo,
            ingest=ingest_trends,
            token_env_path=s.token_env_path,
            videos_repo=repo,
            fetcher=self._youtube_fetcher or fetch_youtube_trends,
            popular_fetcher=self._youtube_popular_fetcher or fetch_popular_trends,
            environ=self.environ,
        )
        run_repo = build_postgres_production_run_repository(connect, dag=COORDINATOR_DAG)
        # O coordenador roda o render em linha (enqueue no-op); a fila de render HTTP continua a mesma.
        coordinator_start = StartRender(repo, scripts, assets, jobs, enqueue=lambda job_id: None)
        handlers = build_stage_handlers(editorial=editorial, media=media, start_render=coordinator_start,
                                        run_render=run, videos=repo, jobs=jobs, assets=assets, approvals=approvals,
                                        publish=publish)
        # Piso medido do gasto mensal (não é previsão): só com o guard hard ligado o modo guardado
        # pode dispensar a pausa intermediária; o teto é o soft do canal (fallback: settings).
        budget = _ChannelBudgetFloor(usage, repo, budget_repo, Decimal(str(s.max_cost_month))) if s.budget_guard else None
        coordinator = ProductionCoordinator(run_repo, handlers=handlers, mode=s.production_mode, budget=budget)
        worker = ProductionWorker(coordinator)
        production = Production(coordinator=coordinator, worker=worker,
                                submit=lambda run_id: self._executor.submit(worker.work, run_id))
        analytics_learning_repo = PostgresAnalyticsLearningRepository(connect)
        analytics_dashboard = BuildAnalyticsDashboard(analytics_learning_repo)
        analytics_collection = CollectMetrics(
            ChannelAnalyticsAdapter(youtube_repo, secret_store), analytics_learning_repo)
        analytics_decide = DecideRecommendation(analytics_learning_repo)
        analytics_register_experiment = RegisterExperiment(analytics_learning_repo)
        panel_repo = PostgresPanelRepository(connect)
        panel = BuildPanel(panel_repo, s.max_cost_month, lambda: datetime.now(timezone.utc), trends=trend_repo, categories_repo=category_repo)
        saas_repo = PostgresSaasRepository(connect)
        saas_clock = lambda: datetime.now(timezone.utc)
        team_view = BuildTeamView(saas_repo, saas_clock)
        script_view = BuildScriptView(repo, snaps, scripts, scripts, checks=checks, allow_names=frozenset(s.allow_names))
        providers_service = ProviderService(repo, self.environ, implementations, probes)
        channel_budget = GetChannelBudget(
            budget_repo, repo, usage_repo,
            default_hard_monthly=Decimal(str(s.max_cost_month)),
            default_hard_video=Decimal(str(s.max_cost_video)))
        youtube_channel = GetYouTubeChannel(youtube_repo, secret_store)
        project_config = GetPublicProjectConfig(repo)
        set_project_config = SetPublicProjectConfig(repo, implementations)
        channels_page = BuildChannelsPage(panel_repo, repo, GetChannelProfile(channel_repo, repo),
                                          providers_service, channel_budget, youtube_channel, project_config,
                                          oauth_available=oauth_client is not None)
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
                                  team_view=team_view,
                                  analytics_repo=analytics_learning_repo,
                                  analytics_dashboard=analytics_dashboard,
                                  analytics_collection=analytics_collection,
                                  analytics_decide=analytics_decide,
                                  analytics_register_experiment=analytics_register_experiment,
                                  begin_youtube_oauth=begin_oauth, complete_youtube_oauth=complete_oauth,
                                  refresh_youtube_channel=refresh_channel, revoke_youtube_channel=revoke_channel,
                                  resolve_actor=ResolveActor(saas_repo),
                                  invite_member=InviteMember(saas_repo, saas_clock),
                                  change_member_role=ChangeMemberRole(saas_repo),
                                  remove_member=RemoveMember(saas_repo),
                                  register_byok_key=RegisterByokKey(saas_repo, secret_store, saas_clock),
                                  rotate_byok_key=RotateByokKey(saas_repo, secret_store, saas_clock),
                                  revoke_byok_key=RevokeByokKey(saas_repo, secret_store, saas_clock),
                                  plan_regeneration=plan_regeneration)

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
