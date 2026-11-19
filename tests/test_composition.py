import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

pytest.importorskip("psycopg")
from app.studio.composition import Settings, Studio  # noqa: E402

DEAD = "postgresql://x:y@127.0.0.1:1/z"


def counting(studio, monkeypatch):
    calls, original = [], studio._connect
    monkeypatch.setattr(studio, "_connect", lambda: (calls.append(1), original())[1])
    return calls


def test_connection_has_lock_and_statement_timeouts(dsn, tmp_path):
    with Studio(Settings(database_url=dsn, storage_root=tmp_path))._connect() as c:
        assert c.execute("SHOW statement_timeout").fetchone()[0] == "15s"
        assert c.execute("SHOW lock_timeout").fetchone()[0] == "5s"


def test_failed_init_backs_off_instead_of_retrying_every_call(tmp_path, monkeypatch):
    studio = Studio(Settings(database_url=DEAD, storage_root=tmp_path))
    calls = counting(studio, monkeypatch)
    assert studio.use_cases() is None and studio.use_cases() is None and studio.ping() is False
    assert len(calls) == 1


def test_ping_is_cached_for_a_few_seconds(conn, dsn, tmp_path, monkeypatch):
    from app.studio.adapters.postgres.db import migrate
    migrate(conn)
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    calls = counting(studio, monkeypatch)
    assert studio.ping() is True
    after_first = len(calls)
    assert studio.ping() is True and len(calls) == after_first
