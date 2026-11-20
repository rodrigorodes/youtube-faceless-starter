"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos."""
import os
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from .adapters.postgres.db import migrate
from .adapters.fetcher import HttpxFetcher
from .adapters.image_opencode import OpenCodeImage
from .adapters.image_placeholder import PlaceholderImage
from .adapters.image_stock import PexelsImage
from .adapters.image_veo import VeoImage
from .adapters.postgres.publish_repo import PostgresApprovalRepository, PostgresPublicationRepository
from .adapters.postgres.analytics_repo import PostgresAnalyticsRepository
from .adapters.postgres.panel_repo import PostgresPanelRepository
from .adapters.postgres.step_repo import PostgresStepRepository
from .adapters.postgres.trend_repo import PostgresTrendRepository
from .adapters.postgres.render_repo import PostgresRenderJobRepository
from .adapters.postgres.category_repo import PostgresCategoryRepository
from .adapters.youtube_trends import fetch_popular_trends, fetch_youtube_trends
from .adapters.postgres.media_repo import PostgresAssetRepository, PostgresProductionLock
from .adapters.thumbnail import PillowThumbnail
from .adapters.qa_ffmpeg import FfmpegQa
from .adapters.render_ffmpeg import FfmpegRenderer
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
from .application.panel import BuildPanel
from .application.trends import IngestTrends
from .application.categories import DeleteCategory, ListCategories, RefreshTrends, SaveCategory
from .application.observability import BridgeAlerts, Resume
from .application.publishing import (Approve, ClaimPublication, GetPreview, GetPublication, GetThumbnail, MarkFailed, MarkThumbnail, MarkUploaded,
                                       Publishing, Reject, RetryPublication, SetUploadUri)
from .application.render import GetRender, GetRenderFile, Rendering, RunRender, StartRender
from .application.media import ListAssets, Media, PrepareStoryboard, ProduceAssets
from .application.editorial import CostGuard, Editorial, GenerateScript, GetScript, IngestSource, RunFactCheck
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

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        return cls(env.get("STUDIO_DATABASE_URL") or None, Path(env.get("STUDIO_STORAGE_ROOT", "/data")),
                   _csv(env.get("STUDIO_SOURCE_ALLOWLIST"), DEFAULT_ALLOWLIST), _csv(env.get("STUDIO_ALLOW_NAMES"), DEFAULT_ALLOW_NAMES),
                   _cap(env.get("MAX_COST_USD_PER_VIDEO"), 0.0), _cap(env.get("MAX_COST_USD_PER_MONTH"), 15.0),
                   env.get("OPENCODE_BRIDGE_TOKEN", ""), env.get("OPENCODE_BRIDGE_URL") or "http://host.docker.internal:8787",
                   env.get("PEXELS_API_KEY", ""), _cap(env.get("STUDIO_PAID_IMAGE_USD"), 0.05), _cap(env.get("STUDIO_VEO_USD_PER_SECOND"), 0.40),
                   max(1, min(4, int(_cap(env.get("RENDER_CONCURRENCY"), 1)))),
                   _csv(env.get("STUDIO_TREND_SOURCES"), ("www.googleapis.com", "www.youtube.com")),
                   Path(env.get("STUDIO_TOKEN_ENV_PATH", "credentials/token.env")))


RETRY_SECONDS = 5.0
PING_TTL_SECONDS = 5.0
CONNECT_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=15000"  # nenhuma consulta espera para sempre


class Studio:
    """Inicializa o banco sob demanda. Sem banco, o app segue de pé em modo degradado."""

    def __init__(self, settings: Settings, environ: Mapping[str, str] | None = None, fetcher=None, executor=None, analyzer=None, youtube_fetcher=None, youtube_popular_fetcher=None):
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
        register("renderer", "ffmpeg", FfmpegRenderer)
        self._executor = executor or ThreadPoolExecutor(max_workers=settings.render_concurrency, thread_name_prefix="render")
        self._analyzer = analyzer or FfmpegQa()
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
        editorial = Editorial(
            ingest=IngestSource(self._fetcher, snaps, repo, s.source_allowlist),
            generate=GenerateScript(repo, snaps, scripts, None, guard, usage, model_for=text_for),
            get_script=GetScript(repo, scripts),
            fact_check=RunFactCheck(repo, snaps, scripts, checks, frozenset(s.allow_names)),
            score_ideas=ScoreIdeas(None, guard, usage, model_for=text_for))
        assets = PostgresAssetRepository(connect)
        media = Media(
            storyboard=PrepareStoryboard(repo, scripts),
            produce=ProduceAssets(repo, scripts, assets, FileAssetStore(s.storage_root), guard, usage,
                                  image_for=lambda project_id: provider_for("image", project_id),
                                  lock=PostgresProductionLock(self._connect_autocommit)),
            list_assets=ListAssets(repo, scripts, assets))
        jobs = PostgresRenderJobRepository(connect)
        steps = PostgresStepRepository(connect)
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
                         renderer_for=lambda project_id: provider_for("renderer", project_id), analyzer=self._analyzer, steps=steps)
        rendering = Rendering(start=StartRender(repo, scripts, assets, jobs, enqueue=lambda job_id: self._executor.submit(run.execute, job_id)),
                              get=GetRender(repo, jobs), file=GetRenderFile(repo, jobs, files))
        approvals, pubs = PostgresApprovalRepository(connect), PostgresPublicationRepository(connect)
        publishing = Publishing(
            approve=Approve(repo, scripts, approvals), reject=Reject(repo, approvals),
            claim=ClaimPublication(repo, scripts, assets, jobs, snaps, pubs, files), set_uri=SetUploadUri(pubs), uploaded=MarkUploaded(pubs),
            failed=MarkFailed(pubs), thumbnail_set=MarkThumbnail(pubs), retry=RetryPublication(repo, pubs), get=GetPublication(repo, pubs),
            thumbnail=GetThumbnail(repo, scripts, assets, files, PillowThumbnail()),
            preview=GetPreview(repo, scripts, assets, jobs, snaps, approvals, pubs, files))
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
        panel = BuildPanel(PostgresPanelRepository(connect), s.max_cost_month, lambda: datetime.now(timezone.utc), trends=trend_repo, categories_repo=category_repo)
        return UseCases.from_repo(repo, editorial, media, rendering, publishing,
                                  Analytics(PostgresAnalyticsRepository(connect)), Resume(repo, rendering.start),
                                  panel=panel, ingest_trends=ingest_trends, trends_repo=trend_repo,
                                  categories_repo=category_repo, list_categories=list_categories,
                                  save_category=save_category, delete_category=delete_category,
                                  refresh_trends=refresh_trends)

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
