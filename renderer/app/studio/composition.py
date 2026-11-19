"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos."""
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .adapters.postgres.db import migrate
from .adapters.postgres.repo import PostgresVideoRepository
from .application.use_cases import ServiceUnavailable, UseCases


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    storage_root: Path = Path("/data")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(os.getenv("STUDIO_DATABASE_URL") or None, Path(os.getenv("STUDIO_STORAGE_ROOT", "/data")))


RETRY_SECONDS = 5.0
PING_TTL_SECONDS = 5.0
CONNECT_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=15000"  # nenhuma consulta espera para sempre


class Studio:
    """Inicializa o banco sob demanda. Sem banco, o app segue de pé em modo degradado."""

    def __init__(self, settings: Settings):
        self.settings = settings
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
                self._use_cases = UseCases.from_repo(PostgresVideoRepository(self._connect))
        return self._use_cases

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
