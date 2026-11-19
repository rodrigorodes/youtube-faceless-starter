"""Conexão e migrações SQL numeradas (sem ORM). Cada migração roda em uma transação."""
import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
LOCK_KEY = 726_001  # pg_advisory_xact_lock: dois processos não migram ao mesmo tempo


def connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or os.environ["STUDIO_DATABASE_URL"])


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica as migrações pendentes em ordem. Devolve as versões aplicadas nesta chamada."""
    applied_now: list[str] = []
    for path in sorted(Path(directory).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = path.stem
        with conn.transaction():  # falha reverte tudo, inclusive o registro da versão
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            conn.execute("CREATE SCHEMA IF NOT EXISTS studio")
            conn.execute("CREATE TABLE IF NOT EXISTS studio.schema_migrations "
                         "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            if conn.execute("SELECT 1 FROM studio.schema_migrations WHERE version = %s", (version,)).fetchone():
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO studio.schema_migrations(version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now
