"""Integration tests require a PostgreSQL container with a private proof mount."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import os
from threading import Barrier

import psycopg
import pytest

from app.studio.adapters.postgres.db import MIGRATIONS_DIR, migrate
from conftest import verified_test_connect, verify_disposable_connection


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável de orçamento não configurado")
    return value


def reset_disposable_schema(connection, proof_path):
    """Never drop studio unless this server can read our private proof."""
    verify_disposable_connection(connection, proof_path)
    connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
    connection.commit()


@pytest.fixture
def conn(dsn):
    connection = verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
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
    return PostgresBudgetRepository(
        lambda: verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
    ), conn


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
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES (%s, 's', 'p', 'm', 0.3, 'ACTUAL', 0.3, 'invoice', 'reviewer', now())", ("b" * 32,))
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
        "INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, created_at, cost_confirmation_kind, "
        "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
        "VALUES (%s, 's', 'p', 'm', 0.8, date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '1 second', "
        "'ACTUAL', 0.8, 'invoice', 'reviewer', now())",
        ("b" * 32,),
    )
    conn.commit()
    assert reserve(repo, "old-video", amount="0.21") == "DENIED"
    assert reserve(repo, "new-video", video="c" * 32, amount="1") == "CREATED"


def test_decimal_precision_does_not_round_away_spend(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES (%s, 's', 'p', 'm', 0.000001, 'ACTUAL', 0.000001, 'invoice', 'reviewer', now())", ("b" * 32,))
    conn.commit()
    assert reserve(repo, "precision", amount="0.99999900000000000000000000001") == "DENIED"


def test_uncommitted_ledger_write_serializes_before_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES (%s, 's', 'p', 'm', 0.8, 'ACTUAL', 0.8, 'invoice', 'reviewer', now())", ("b" * 32,))
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


def test_positive_estimate_without_confirmation_blocks_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) "
                 "VALUES ('image', 'opencode', 'model', 0.05)")
    conn.commit()
    assert reserve(repo, "estimated", monthly="100", video_limit="100") == "DENIED"


def test_legacy_zero_evidence_alone_does_not_confirm_free(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_zero_evidence) "
                 "VALUES ('text', 'demo', 'local', 'legacy note')")
    conn.commit()
    assert reserve(repo, "legacy-free", monthly="100", video_limit="100") == "DENIED"


def test_explicit_confirmed_paid_cost_allows_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, "
                 "cost_confirmation_kind, cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES ('image', 'opencode', 'model', 0.2, 'ACTUAL', 0.2, 'invoice 1', 'reviewer', now())")
    conn.commit()
    assert reserve(repo, "confirmed", amount="0.8") == "CREATED"
    assert reserve(repo, "over", amount="0.01") == "DENIED"


def test_manual_reconciliation_confirms_same_amount_without_rewriting_history(budget_db):
    repo, conn = budget_db
    ledger_id = conn.execute(
        "INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) "
        "VALUES ('image', 'opencode', 'model', 0.2) RETURNING id"
    ).fetchone()[0]
    conn.commit()
    assert reserve(repo, "before", monthly="10") == "DENIED"
    conn.execute("UPDATE studio.usage_ledger SET cost_confirmation_kind = 'ACTUAL', cost_confirmed_amount = 0.2, "
                 "cost_confirmation_reference = 'invoice 1', cost_confirmed_by = 'reviewer', cost_confirmed_at = now() "
                 "WHERE id = %s AND cost_usd = 0.2 AND cost_confirmation_kind IS NULL", (ledger_id,))
    conn.commit()
    assert reserve(repo, "after", monthly="10") == "CREATED"


@pytest.mark.parametrize(("kind", "cost", "confirmed", "reference", "actor"), [
    ("ACTUAL", "0.2", "0.1", "invoice", "reviewer"),
    ("ACTUAL", "0", "0", "invoice", "reviewer"),
    ("FREE", "0.2", "0.2", "invoice", "reviewer"),
    ("FREE", "0", "0", " \t", "reviewer"),
    ("FREE", "0", "0", "invoice", ""),
    ("ACTUAL", "NaN", "NaN", "invoice", "reviewer"),
])
def test_database_rejects_inconsistent_structured_confirmation(budget_db, kind, cost, confirmed, reference, actor):
    _, conn = budget_db
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, cost_confirmation_kind, "
                     "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                     "VALUES ('s', 'p', 'm', %s, %s, %s, %s, %s, now())",
                     (Decimal(cost), kind, Decimal(confirmed), reference, actor))
    conn.rollback()


def test_confirmed_cost_cannot_change_without_updating_confirmation(budget_db):
    _, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES ('s', 'p', 'm', 0.2, 'ACTUAL', 0.2, 'invoice', 'reviewer', now())")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE studio.usage_ledger SET cost_usd = 0.4")
    conn.rollback()


def test_confirmed_free_ledger_entry_allows_reservation(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES (%s, 'text', 'demo', 'local', 'FREE', 0, 'manual confirmation', 'reviewer', now())", ("b" * 32,))
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
        if path.name < "0015":
            (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'test')", ("a" * 32,))
    conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')",
                 ("b" * 32, "a" * 32))
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_zero_evidence) "
                 "VALUES ('text', 'demo', 'local', 'old note')")
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd) "
                 "VALUES ('image', 'opencode', 'model', 0.05)")
    conn.commit()
    assert migrate(conn) == ["0015_ledger_cost_confirmation"]
    assert conn.execute("SELECT count(*) FROM studio.usage_ledger WHERE cost_confirmation_kind IS NULL").fetchone()[0] == 2
    conn.commit()
    repo = PostgresBudgetRepository(
        lambda: verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
    )
    assert reserve(repo, "legacy", monthly="100", video_limit="100") == "DENIED"


def test_unattributed_ledger_spend_and_unknown_cost_affect_global_budget(budget_db):
    repo, conn = budget_db
    conn.execute("INSERT INTO studio.usage_ledger(step, provider, model, cost_usd, cost_confirmation_kind, "
                 "cost_confirmed_amount, cost_confirmation_reference, cost_confirmed_by, cost_confirmed_at) "
                 "VALUES ('text', 'paid', 'model', 0.8, 'ACTUAL', 0.8, 'invoice', 'reviewer', now())")
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
    with verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]) as other:
        with pytest.raises(ValueError):
            reset_disposable_schema(other, wrong)
        with pytest.raises(ValueError):
            reset_disposable_schema(other, tmp_path / "missing")
    assert conn.execute("SELECT to_regclass('studio.videos') IS NOT NULL").fetchone()[0]


def test_each_repository_connection_checks_disposable_proof(budget_db, monkeypatch, tmp_path):
    repo, conn = budget_db
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", str(wrong))
    with pytest.raises(ValueError, match="proof"):
        reserve(repo, "unsafe")
    assert conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0] == 0


def test_autocommit_connection_is_rejected(budget_db, dsn):
    from app.studio.adapters.postgres.budget_repo import PostgresBudgetRepository

    repo = PostgresBudgetRepository(
        lambda: verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"], autocommit=True)
    )
    with pytest.raises(ValueError, match="autocommit"):
        reserve(repo, "unsafe")


@pytest.mark.parametrize("amount", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 0.1])
def test_invalid_amount_is_rejected(budget_db, amount):
    repo, _ = budget_db
    with pytest.raises(ValueError):
        repo.reserve("bad", "b" * 32, amount, Decimal("1"), Decimal("1"))
