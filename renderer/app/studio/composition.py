"""Raiz de composição: único lugar que liga casos de uso aos adaptadores concretos."""
import os
import threading
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


class Studio:
    """Inicializa o banco sob demanda. Sem banco, o app segue de pé em modo degradado."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._use_cases: UseCases | None = None
        self._lock = threading.Lock()

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.settings.database_url, connect_timeout=3)
        except psycopg.OperationalError as exc:
            raise ServiceUnavailable("studio database unavailable") from exc

    def use_cases(self) -> UseCases | None:
        if self._use_cases is not None:
            return self._use_cases
        if not self.settings.database_url:
            return None
        with self._lock:
            if self._use_cases is None:
                try:
                    with self._connect() as conn:
                        migrate(conn)
                except (ServiceUnavailable, psycopg.Error):
                    return None
                self._use_cases = UseCases.from_repo(PostgresVideoRepository(self._connect))
        return self._use_cases

    def ping(self) -> bool:
        if self.use_cases() is None:
            return False
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except (ServiceUnavailable, psycopg.Error):
            return False
