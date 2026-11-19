"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos."""
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .adapters.postgres.db import migrate
from .adapters.fetcher import HttpxFetcher
from .adapters.postgres.editorial_repo import (PostgresFactCheckRepository, PostgresScriptRepository,
                                               PostgresSnapshotRepository, PostgresUsageRepository)
from .adapters.postgres.repo import PostgresVideoRepository
from .adapters.text_demo import DemoText
from .adapters.text_opencode import OpenCodeText
from .application.config import ProjectConfig, ProviderNotFound, build, register
from .application.ideas import ScoreIdeas
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

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        return cls(env.get("STUDIO_DATABASE_URL") or None, Path(env.get("STUDIO_STORAGE_ROOT", "/data")),
                   _csv(env.get("STUDIO_SOURCE_ALLOWLIST"), DEFAULT_ALLOWLIST), _csv(env.get("STUDIO_ALLOW_NAMES"), DEFAULT_ALLOW_NAMES),
                   _cap(env.get("MAX_COST_USD_PER_VIDEO"), 0.0), _cap(env.get("MAX_COST_USD_PER_MONTH"), 15.0),
                   env.get("OPENCODE_BRIDGE_TOKEN", ""), env.get("OPENCODE_BRIDGE_URL") or "http://host.docker.internal:8787")


RETRY_SECONDS = 5.0
PING_TTL_SECONDS = 5.0
CONNECT_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=15000"  # nenhuma consulta espera para sempre


class Studio:
    """Inicializa o banco sob demanda. Sem banco, o app segue de pé em modo degradado."""

    def __init__(self, settings: Settings, environ: Mapping[str, str] | None = None, fetcher=None):
        self.settings = settings
        self.environ = os.environ if environ is None else environ
        self._fetcher = fetcher or HttpxFetcher(settings.source_allowlist)
        register("text", "opencode", lambda model: OpenCodeText(model, settings.bridge_token, settings.bridge_url))
        register("text", "demo", DemoText)
        self._use_cases: UseCases | None = None
        self._lock = threading.Lock()
        self._retry_at = 0.0  # backoff após falha de inicialização
        self._ping: tuple[bool, float] = (False, 0.0)  # (resultado, validade)

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.settings.database_url, connect_timeout=3, options=CONNECT_OPTIONS)
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
                self._use_cases = self._wire()
        return self._use_cases

    def _wire(self) -> UseCases:
        s, connect = self.settings, self._connect
        repo, snaps, scripts = PostgresVideoRepository(connect), PostgresSnapshotRepository(connect), PostgresScriptRepository(connect)
        usage, checks = PostgresUsageRepository(connect), PostgresFactCheckRepository(connect)

        def text_for(project_id: str | None):
            project = repo.get_project(project_id) if project_id else None
            try:
                spec = ProjectConfig.resolve(project.config if project else {}, self.environ).text
            except ValueError as exc:
                raise ProviderNotFound(str(exc)) from exc
            return build("text", spec)

        guard = CostGuard(usage, s.max_cost_video, s.max_cost_month)
        editorial = Editorial(
            ingest=IngestSource(self._fetcher, snaps, repo, s.source_allowlist),
            generate=GenerateScript(repo, snaps, scripts, None, guard, usage, model_for=text_for),
            get_script=GetScript(repo, scripts),
            fact_check=RunFactCheck(repo, snaps, scripts, checks, frozenset(s.allow_names)),
            score_ideas=ScoreIdeas(None, guard, usage, model_for=text_for))
        return UseCases.from_repo(repo, editorial)

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
