"""Integration tests require a PostgreSQL container with a private proof mount."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import os
from pathlib import Path
import secrets
from threading import Barrier

import psycopg
import pytest

from app.studio.adapters.postgres.db import MIGRATIONS_DIR, migrate


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável de orçamento não configurado")
    return value


def reset_disposable_schema(connection, proof_path):
    """Never drop studio unless this server can read our private proof."""
    try:
        proof = Path(proof_path).read_text(encoding="ascii").strip()
        if len(proof) != 64 or any(c not in "0123456789abcdef" for c in proof):
            raise ValueError("invalid disposable database proof")
        server_proof = connection.execute(
            "SELECT pg_read_file('/budget-test-proof/proof')"
        ).fetchone()[0].strip()
        if not secrets.compare_digest(proof, server_proof):
            raise ValueError("disposable database proof mismatch")
    except (OSError, UnicodeError, psycopg.Error) as exc:
        raise ValueError("disposable database proof unavailable") from exc
    connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
    connection.commit()


@pytest.fixture
def conn(dsn):
    connection = psycopg.connect(dsn)
    try:
        reset_disposable_schema(connection, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
        yield connection
    finally:
        connection.close()


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
    assert reserve(repo, "request") == "CREATED"
    assert reserve(repo, "request") == "EXISTING"
    with pytest.raises(IdempotencyConflict):
        reserve(repo, "request", amount="0.61")
    with pytest.raises(IdempotencyConflict):
        reserve(repo, "request", video="c" * 32)


def test_reservation_results_cannot_be_treated_as_boolean(budget_db):
    repo, _ = budget_db
    created = reserve(repo, "one")
    existing = reserve(repo, "one")
    denied = reserve(repo, "two")
    for result in (created, existing, denied):
        with pytest.raises(TypeError):
            bool(result)


def test_concurrent_videos_cannot_exceed_global_monthly_budget(budget_db):
    repo, conn = budget_db
    barrier = Barrier(2)

    def worker(index):
        barrier.wait()
        return reserve(repo, str(index), video=("b" if index == 0 else "c") * 32)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sorted(results) == ["CREATED", "DENIED"]
    assert conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 1


def test_existing_spend_and_active_reservations_count_for_both_limits(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 's', 'p', 'm', 0.3)", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "one", amount="0.4") == "CREATED"
    assert reserve(repo, "two", amount="0.31", monthly="10") == "DENIED"
    assert reserve(repo, "three", video="c" * 32, amount="0.31") == "DENIED"
    assert reserve(repo, "four", video="c" * 32, amount="0.3") == "CREATED"


def test_concurrent_same_key_is_idempotent(budget_db):
    repo, conn = budget_db
    barrier = Barrier(2)

    def worker(_):
        barrier.wait()
        return reserve(repo, "same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, range(2))) == ["CREATED", "EXISTING"]
    assert conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 1


def test_monthly_spend_uses_utc_month_and_video_spend_is_lifetime(budget_db):
    repo, conn = budget_db
    conn.execute(
        "INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, created_at) "
        "VALUES (%s, 's', 'p', 'm', 0.8, date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '1 second')",
        ("b" * 32,),
    )
    conn.commit()
    assert reserve(repo, "old-video", amount="0.21") == "DENIED"
    assert reserve(repo, "new-video", video="c" * 32, amount="1") == "CREATED"


def test_decimal_precision_does_not_round_away_spend(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 's', 'p', 'm', 0.000001)", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "precision", amount="0.99999900000000000000000000001") == "DENIED"


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
        assert future.result(timeout=5) == "DENIED"


def test_unknown_zero_cost_blocks_new_reservation_but_not_idempotent_replay(budget_db):
    repo, conn = budget_db
    assert reserve(repo, "existing") == "CREATED"
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model) "
                 "VALUES (%s, 'text', 'opencode', 'unspecified')", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "new", amount="0.01", monthly="100", video_limit="100") == "DENIED"
    assert reserve(repo, "existing") == "EXISTING"


def test_confirmed_free_ledger_entry_allows_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_zero_evidence) "
                 "VALUES (%s, 'text', 'demo', 'local', 'manual confirmation')", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "free") == "CREATED"


@pytest.mark.parametrize(("cost", "evidence"), [("0", "  "), ("0", "\t\n"), ("0.1", "not free")])
def test_database_rejects_invalid_zero_cost_evidence(budget_db, cost, evidence):
    _, conn = budget_db
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, cost_zero_evidence) "
                     "VALUES ('text', 'demo', 'local', %s, %s)", (Decimal(cost), evidence))
    conn.rollback()


def test_nan_ledger_cost_is_unknown(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) "
                 "VALUES ('text', 'paid', 'model', 'NaN')")
    conn.commit()
    assert reserve(repo, "nan", monthly="100", video_limit="100") == "DENIED"


def test_migration_preserves_legacy_zero_as_unknown(conn, dsn, tmp_path):
    from app.studio.adapters.postgres.budget_repo import PostgresBudgetRepository

    for path in MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < "0014":
            (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'test')", ("a" * 32,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                 ("b" * 32, "a" * 32))
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model) VALUES ('text', 'demo', 'local')")
    conn.commit()
    assert migrate(conn) == ["0014_ledger_cost_evidence"]
    repo = PostgresBudgetRepository(lambda: psycopg.connect(dsn))
    assert reserve(repo, "legacy", monthly="100", video_limit="100") == "DENIED"


def test_unattributed_ledger_spend_and_unknown_cost_affect_global_budget(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) "
                 "VALUES ('text', 'paid', 'model', 0.8)")
    conn.commit()
    assert reserve(repo, "global-spend", amount="0.21", video_limit="10") == "DENIED"
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model) VALUES ('text', 'unknown', 'model')")
    conn.commit()
    assert reserve(repo, "global-unknown", amount="0.01", monthly="100", video_limit="100") == "DENIED"


def test_old_unknown_cost_only_blocks_its_own_video(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, created_at) "
                 "VALUES (%s, 'text', 'unknown', 'model', "
                 "date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '1 second')",
                 ("b" * 32,))
    conn.commit()
    assert reserve(repo, "old-unknown", monthly="100", video_limit="100") == "DENIED"
    assert reserve(repo, "other-video", video="c" * 32) == "CREATED"


def test_guard_refuses_wrong_or_missing_proof_before_dropping_schema(budget_db, dsn, tmp_path):
    _, conn = budget_db
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    with psycopg.connect(dsn) as other:
        with pytest.raises(ValueError):
            reset_disposable_schema(other, wrong)
        with pytest.raises(ValueError):
            reset_disposable_schema(other, tmp_path / "missing")
    assert conn.execute("SELECT to_regclass('studio.videos') IS NOT NULL").fetchone()[0]


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
