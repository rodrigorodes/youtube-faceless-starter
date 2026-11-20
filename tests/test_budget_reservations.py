"""Integration tests require the explicitly disposable STUDIO_TEST_DSN database."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import os
from threading import Barrier

import psycopg
import pytest

from app.studio.adapters.postgres.db import migrate


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value:
        pytest.skip("PostgreSQL descartável de orçamento não configurado")
    info = psycopg.conninfo.conninfo_to_dict(value)
    if info.get("host") != "f1-budget-postgres-39a258" or info.get("dbname") != "budget_test":
        pytest.fail("DSN de orçamento não identifica o container descartável esperado")
    return value


@pytest.fixture
def budget_db(conn, dsn):
    from app.studio.adapters.postgres.budget_repo import PostgresBudgetRepository

    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'test')", ("a" * 32,))
    for video in ("b" * 32, "c" * 32):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                     (video, "a" * 32))
    conn.commit()
    return PostgresBudgetRepository(lambda: psycopg.connect(dsn)), conn


def reserve(repo, key, video="b" * 32, amount="0.60", monthly="1", video_limit="1"):
    return repo.reserve(key, video, Decimal(amount), Decimal(monthly), Decimal(video_limit))


def test_reserve_is_idempotent_and_rejects_conflicting_reuse(budget_db):
    from app.studio.application.budget import IdempotencyConflict

    repo, _ = budget_db
    assert reserve(repo, "request")
    assert reserve(repo, "request")
    with pytest.raises(IdempotencyConflict):
        reserve(repo, "request", amount="0.61")
    with pytest.raises(IdempotencyConflict):
        reserve(repo, "request", video="c" * 32)


def test_concurrent_videos_cannot_exceed_global_monthly_budget(budget_db):
    repo, conn = budget_db
    barrier = Barrier(2)

    def worker(index):
        barrier.wait()
        return reserve(repo, str(index), video=("b" if index == 0 else "c") * 32)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sorted(results) == [False, True]
    assert conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 1


def test_existing_spend_and_active_reservations_count_for_both_limits(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 's', 'p', 'm', 0.3)", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "one", amount="0.4")
    assert not reserve(repo, "two", amount="0.31", monthly="10")
    assert not reserve(repo, "three", video="c" * 32, amount="0.31")
    assert reserve(repo, "four", video="c" * 32, amount="0.3")


def test_concurrent_same_key_is_idempotent(budget_db):
    repo, conn = budget_db
    barrier = Barrier(2)

    def worker(_):
        barrier.wait()
        return reserve(repo, "same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(worker, range(2))) == [True, True]
    assert conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 1


def test_monthly_spend_uses_utc_month_and_video_spend_is_lifetime(budget_db):
    repo, conn = budget_db
    conn.execute(
        "INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, created_at) "
        "VALUES (%s, 's', 'p', 'm', 0.8, date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '1 second')",
        ("b" * 32,),
    )
    conn.commit()
    assert not reserve(repo, "old-video", amount="0.21")
    assert reserve(repo, "new-video", video="c" * 32, amount="1")


def test_decimal_precision_does_not_round_away_spend(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 's', 'p', 'm', 0.000001)", ("b" * 32,))
    conn.commit()
    assert not reserve(repo, "precision", amount="0.99999900000000000000000000001")


def test_uncommitted_ledger_write_serializes_before_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 's', 'p', 'm', 0.8)", ("b" * 32,))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reserve, repo, "pending", amount="0.3")
        try:
            with pytest.raises(TimeoutError):
                future.result(timeout=0.3)
        finally:
            conn.commit()
        assert future.result(timeout=5) is False


def test_autocommit_connection_is_rejected(budget_db, dsn):
    from app.studio.adapters.postgres.budget_repo import PostgresBudgetRepository

    repo = PostgresBudgetRepository(lambda: psycopg.connect(dsn, autocommit=True))
    with pytest.raises(ValueError, match="autocommit"):
        reserve(repo, "unsafe")


@pytest.mark.parametrize("amount", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 0.1])
def test_invalid_amount_is_rejected(budget_db, amount):
    repo, _ = budget_db
    with pytest.raises(ValueError):
        repo.reserve("bad", "b" * 32, amount, Decimal("1"), Decimal("1"))
