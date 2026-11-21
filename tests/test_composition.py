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


# -- F10-05: limites por canal ligados ao guard e à pausa humana (fakes, sem banco) --


class _Video:
    def __init__(self, project_id):
        self.project_id = project_id


class _Videos:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_video(self, video_id):
        return self.mapping.get(video_id)


class _Budgets:
    def __init__(self, limits):
        self.limits = limits

    def get(self, project_id):
        return next((lim for lim in self.limits if lim.project_id == project_id), None)


def test_channel_guard_limits_resolve_from_the_channel_budget():
    from decimal import Decimal

    from app.studio.composition import channel_guard_limits
    from app.studio.domain.channel_budget import BudgetLimits

    limits = BudgetLimits(project_id="a" * 32, hard_monthly_usd=Decimal("7"), soft_monthly_usd=Decimal("3"),
                          hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    resolve = channel_guard_limits(_Videos({"b" * 32: _Video("a" * 32)}), _Budgets([limits]))
    assert resolve("b" * 32) == (Decimal("7"), Decimal("2"))
    assert resolve(None) is None
    assert resolve("9" * 32) is None  # vídeo inexistente usa o padrão das settings
    assert resolve("not-a-hex-id") is None  # id inválido não bloqueia por si: cai no padrão


def test_channel_budget_floor_uses_soft_limit_and_falls_back():
    from decimal import Decimal

    from app.studio.composition import _ChannelBudgetFloor
    from app.studio.domain.channel_budget import BudgetLimits

    class Usage:
        def spent_month(self):
            return 4.0

    limits = BudgetLimits(project_id="a" * 32, hard_monthly_usd=Decimal("9"), soft_monthly_usd=Decimal("5"),
                          hard_video_usd=Decimal("2"), soft_video_usd=Decimal("1"))
    floor = _ChannelBudgetFloor(Usage(), _Videos({"b" * 32: _Video("a" * 32)}), _Budgets([limits]),
                                Decimal("15"))
    projection = floor.project(type("R", (), {"video_id": "b" * 32}), None)
    assert projection.ceiling_usd == Decimal("5")  # soft do canal, não o padrão
    assert projection.projected_usd == Decimal("4.0")
    default = floor.project(type("R", (), {"video_id": "c" * 32}), None)
    assert default.ceiling_usd == Decimal("15")  # sem budget de canal: teto das settings
