"""Integração do ciclo de vida da operação paga (PostgreSQL descartável com prova privada).

Só roda quando `STUDIO_BUDGET_DISPOSABLE_DSN` e `STUDIO_BUDGET_TEST_PROOF_FILE` apontam para um
banco exclusivamente descartável; a fixture principal derruba o schema `studio`. Sem essas variáveis,
os testes são ignorados — não há banco real nem credenciais aqui.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier

import psycopg
import pytest

from app.studio.adapters.postgres.db import migrate
from conftest import verified_test_connect, verify_disposable_connection

VIDEO, OTHER_VIDEO, PROJECT = "b" * 32, "c" * 32, "a" * 32


@pytest.fixture
def dsn():
    value = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not value or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável de orçamento não configurado")
    return value


def _reset_schema(connection, proof_path):
    verify_disposable_connection(connection, proof_path)
    connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
    connection.commit()


@pytest.fixture
def conn(dsn):
    connection = verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
    try:
        _reset_schema(connection, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"])
        yield connection
    finally:
        connection.close()


@pytest.fixture
def paid_db(conn, dsn):
    from app.studio.adapters.postgres.budget_repo import PostgresPaidOperationRepository

    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'test')", (PROJECT,))
    for video in (VIDEO, OTHER_VIDEO):
        conn.execute("INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'topic', 'short')", (video, PROJECT))
    conn.commit()
    repo = PostgresPaidOperationRepository(lambda: verified_test_connect(dsn, os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]))
    return repo, conn


def entry(cost, *, step="image", provider="fake", model="m"):
    from app.studio.domain.contracts import UsageEntry

    return UsageEntry(step=step, provider=provider, model=model, cost_usd=cost)


def actual(amount):
    from app.studio.application.budget import CostConfirmation

    return CostConfirmation.actual(Decimal(str(amount)), reference="provider:fake", confirmed_by="studio")


def free():
    from app.studio.application.budget import CostConfirmation

    return CostConfirmation.free(reference="provider:piper", confirmed_by="studio")


def estimate(amount):
    from app.studio.application.budget import CostConfirmation

    return CostConfirmation.estimate(Decimal(str(amount)), reference="estimate:image", confirmed_by="studio:image")


def charge(amount):
    from app.studio.application.budget import ChargeEvidence

    return ChargeEvidence(Decimal(str(amount)), reference="invoice:42", declared_by="billing:adapter")


def begin(repo, key, video=VIDEO, amount="0.60", monthly="1", video_limit="1"):
    return repo.begin(key, video, Decimal(amount), Decimal(monthly), Decimal(video_limit))


def row_counts(conn):
    return (conn.execute("SELECT count(*) FROM studio.paid_operations").fetchone()[0],
            conn.execute("SELECT count(*) FROM studio.budget_reservations").fetchone()[0])


def test_migration_creates_paid_operations_table(conn):
    applied = migrate(conn)
    assert "0017_paid_operations" in applied
    assert "0019_ledger_estimate_and_attribution" in applied
    assert conn.execute("SELECT to_regclass('studio.paid_operations') IS NOT NULL").fetchone()[0]


def test_begin_creates_state_and_reservation(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1") == BeginResult.CREATED
    assert repo.state("k1") == PaidOperationState.RESERVED
    assert row_counts(conn) == (1, 1)


def test_begin_replay_is_in_progress_without_touching_the_limit(paid_db):
    from app.studio.application.budget import BeginResult, IdempotencyConflict

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.60") == BeginResult.CREATED
    assert begin(repo, "k1", amount="0.60") == BeginResult.IN_PROGRESS
    assert row_counts(conn) == (1, 1)
    with pytest.raises(IdempotencyConflict):
        begin(repo, "k1", amount="0.61")
    with pytest.raises(IdempotencyConflict):
        begin(repo, "k1", video=OTHER_VIDEO)


def test_concurrent_same_key_reserves_once(paid_db):
    from app.studio.application.budget import BeginResult

    repo, conn = paid_db
    barrier = Barrier(2)

    def worker(_):
        barrier.wait()
        return begin(repo, "same")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(worker, range(2)), key=lambda r: r.value)
    assert BeginResult.CREATED in results and BeginResult.IN_PROGRESS in results
    assert row_counts(conn) == (1, 1)


def test_confirm_actual_records_cost_atomically_and_frees_reservation(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1") == BeginResult.CREATED
    repo.confirm("k1", entry(0.42), actual(0.42))
    assert repo.state("k1") == PaidOperationState.CONFIRMED
    assert row_counts(conn) == (1, 0)  # a reserva ativa sumiu: o gasto passou a ser o ledger confirmado
    kind, amount, confirmed = conn.execute(
        "SELECT cost_confirmation_kind, cost_confirmed_amount, cost_usd FROM studio.usage_ledger "
        "WHERE video_id = %s", (VIDEO,)).fetchone()
    assert (kind, amount, confirmed) == ("ACTUAL", Decimal("0.420000"), Decimal("0.420000"))
    # o gasto confirmado agora limita novas reservas pelo teto mensal
    assert begin(repo, "k2", amount="0.58") == BeginResult.CREATED
    assert begin(repo, "k3", amount="1") == BeginResult.DENIED


def test_confirm_free_records_zero_and_frees_reservation(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "voice", amount="0") == BeginResult.CREATED
    repo.confirm("voice", entry(0.0, step="voice", provider="piper", model="local"), free())
    assert repo.state("voice") == PaidOperationState.CONFIRMED
    assert row_counts(conn) == (1, 0)
    assert conn.execute("SELECT cost_confirmation_kind FROM studio.usage_ledger").fetchone()[0] == "FREE"
    assert begin(repo, "after", amount="1") == BeginResult.CREATED


def test_confirm_rejects_amount_that_does_not_match_the_entry(paid_db):
    from app.studio.application.budget import BeginResult, CostConfirmationError

    repo, _ = paid_db
    assert begin(repo, "k1") == BeginResult.CREATED
    with pytest.raises(CostConfirmationError):
        repo.confirm("k1", entry(0.42), actual(0.10))
    assert repo.state("k1").value == "RESERVED"


def test_confirm_or_release_unknown_key_is_refused(paid_db):
    from app.studio.application.budget import UnknownPaidOperation

    repo, _ = paid_db
    with pytest.raises(UnknownPaidOperation):
        repo.confirm("missing", entry(0.1), actual(0.1))
    with pytest.raises(UnknownPaidOperation):
        repo.release("missing", "no such operation")


def test_release_frees_the_reservation_without_recording_spend(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.9") == BeginResult.CREATED
    repo.release("k1", "local validation failed before the provider call")
    assert repo.state("k1") == PaidOperationState.RELEASED
    assert row_counts(conn) == (1, 0)
    assert conn.execute("SELECT count(*) FROM studio.usage_ledger").fetchone()[0] == 0
    assert begin(repo, "k2", amount="1") == BeginResult.CREATED


def test_uncertain_keeps_the_reservation_and_blocks_reexecution(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.9") == BeginResult.CREATED
    repo.mark_uncertain("k1", "connection reset after the request was sent")
    assert repo.state("k1") == PaidOperationState.UNCERTAIN
    assert row_counts(conn) == (1, 1)  # a reserva incerta continua bloqueando o orçamento
    assert begin(repo, "k1", amount="0.9") == BeginResult.UNCERTAIN
    assert begin(repo, "other", amount="0.2") == BeginResult.DENIED  # 0.9 incerto + 0.2 > teto 1


def test_uncertain_can_be_reconciled_by_confirm(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.9") == BeginResult.CREATED
    repo.mark_uncertain("k1", "ambiguous")
    repo.confirm("k1", entry(0.3), actual(0.3))
    assert repo.state("k1") == PaidOperationState.CONFIRMED
    assert row_counts(conn) == (1, 0)
    assert begin(repo, "k2", amount="0.7") == BeginResult.CREATED


def test_release_after_uncertain_is_allowed(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.9") == BeginResult.CREATED
    repo.mark_uncertain("k1", "ambiguous")
    repo.release("k1", "operator confirmed no spend occurred")
    assert repo.state("k1") == PaidOperationState.RELEASED
    assert row_counts(conn) == (1, 0)


def test_concurrent_videos_cannot_exceed_the_global_monthly_budget(paid_db):
    from app.studio.application.budget import BeginResult

    repo, conn = paid_db
    barrier = Barrier(2)

    def worker(index):
        barrier.wait()
        return begin(repo, str(index), video=(VIDEO if index == 0 else OTHER_VIDEO))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sorted(r.value for r in results) == ["CREATED", "DENIED"]
    assert row_counts(conn) == (1, 1)
    assert BeginResult.CREATED in results


def test_confirmed_spend_and_active_reservation_count_for_both_limits(paid_db):
    from app.studio.application.budget import BeginResult

    repo, _ = paid_db
    assert begin(repo, "reserved", amount="0.4", monthly="1") == BeginResult.CREATED
    assert begin(repo, "other-video", video=OTHER_VIDEO, amount="0.6", monthly="1") == BeginResult.CREATED
    assert begin(repo, "blocked-global", amount="0.01", monthly="1") == BeginResult.DENIED
    assert begin(repo, "blocked-video", amount="0.61", monthly="10", video_limit="1") == BeginResult.DENIED
    assert begin(repo, "other-blocked-video", video=OTHER_VIDEO, amount="0.41", monthly="10", video_limit="1") == BeginResult.DENIED


def test_invalid_begin_arguments_are_rejected(paid_db):
    repo, _ = paid_db
    with pytest.raises(ValueError):
        repo.begin("", VIDEO, Decimal("0.1"), Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError):
        repo.begin("k", VIDEO, Decimal("NaN"), Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError):
        repo.begin("k", VIDEO, 0.1, Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError):
        repo.release("k", "   ")


def test_repository_connection_checks_the_disposable_proof(paid_db, monkeypatch, tmp_path):
    from app.studio.adapters.postgres.budget_repo import PostgresPaidOperationRepository

    _, conn = paid_db
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", str(wrong))
    repo = PostgresPaidOperationRepository(lambda: verified_test_connect(
        os.environ["STUDIO_BUDGET_DISPOSABLE_DSN"], os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]))
    with pytest.raises(ValueError, match="proof"):
        begin(repo, "unsafe")
    assert row_counts(conn) == (0, 0)


# ---------------------------------------------------------------- policy: ESTIMATE, attribution, stale reservations


def test_confirm_estimate_counts_as_approximate_spend_and_is_not_unknown(paid_db):
    from app.studio.application.budget import BeginResult, PaidOperationState

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.6", monthly="1") == BeginResult.CREATED
    repo.confirm("k1", entry(0.6, provider="opencode"), estimate(0.6))
    assert repo.state("k1") == PaidOperationState.CONFIRMED
    assert conn.execute("SELECT cost_confirmation_kind FROM studio.usage_ledger").fetchone()[0] == "ESTIMATE"
    assert row_counts(conn) == (1, 0)
    # a estimativa conta como gasto aproximado no mês: 0.6 + 0.4 cabe, 0.6 + 0.4 + 0.01 não cabe
    assert begin(repo, "k2", amount="0.4", monthly="1") == BeginResult.CREATED
    assert begin(repo, "k3", amount="0.01", monthly="1") == BeginResult.DENIED


def test_reconcile_actual_replaces_the_estimate_with_evidence(paid_db):
    from app.studio.application.budget import BeginResult

    repo, conn = paid_db
    assert begin(repo, "k1", amount="0.3", monthly="10") == BeginResult.CREATED
    repo.confirm("k1", entry(0.3, provider="opencode"), estimate(0.3))
    assert repo.settlement("k1").kind == "ESTIMATE"

    repo.reconcile_actual("k1", Decimal("0.5"), reference="invoice:42", confirmed_by="billing:ops")
    kind, cost, confirmed = conn.execute(
        "SELECT cost_confirmation_kind, cost_usd, cost_confirmed_amount FROM studio.usage_ledger").fetchone()
    assert (kind, cost, confirmed) == ("ACTUAL", Decimal("0.500000"), Decimal("0.500000"))
    assert conn.execute("SELECT count(*) FROM studio.usage_ledger").fetchone()[0] == 1  # troca, não duplica
    settlement = repo.settlement("k1")
    assert (settlement.kind, settlement.amount_usd) == ("ACTUAL", Decimal("0.500000"))
    updated_kind, updated_amount = conn.execute(
        "SELECT confirmed_kind, confirmed_amount_usd FROM studio.paid_operations WHERE idempotency_key = 'k1'").fetchone()
    assert (updated_kind, updated_amount) == ("ACTUAL", Decimal("0.500000"))


def test_reconcile_actual_only_applies_to_an_estimate(paid_db):
    from app.studio.application.budget import BeginResult, CostConfirmationError, InvalidOperationTransition, UnknownPaidOperation

    repo, _ = paid_db
    assert begin(repo, "actual", amount="0.3") == BeginResult.CREATED
    repo.confirm("actual", entry(0.3), actual(0.3))
    with pytest.raises(InvalidOperationTransition):
        repo.reconcile_actual("actual", Decimal("0.4"), reference="invoice", confirmed_by="billing:ops")
    with pytest.raises(UnknownPaidOperation):
        repo.reconcile_actual("missing", Decimal("0.4"), reference="invoice", confirmed_by="billing:ops")
    assert begin(repo, "estimate", video=OTHER_VIDEO, amount="0.3") == BeginResult.CREATED
    repo.confirm("estimate", entry(0.3, provider="opencode"), estimate(0.3))
    with pytest.raises(CostConfirmationError):
        repo.reconcile_actual("estimate", Decimal("0"), reference="invoice", confirmed_by="billing:ops")
    with pytest.raises(ValueError):
        repo.reconcile_actual("estimate", Decimal("0.4"), reference="  ", confirmed_by="billing:ops")


def test_previous_month_reservation_does_not_block_the_current_month_and_is_reported(paid_db):
    from app.studio.application.budget import BeginResult

    repo, conn = paid_db
    conn.execute(
        "INSERT INTO studio.budget_reservations(idempotency_key, video_id, amount_usd, monthly_limit_usd, video_limit_usd, created_at) "
        "VALUES ('old', %s, 1, 1, 10, date_trunc('month', statement_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '1 day')",
        (VIDEO,))
    conn.commit()
    # a reserva antiga não consome o teto mensal atual (mas continua no teto por vídeo, conservador)
    assert begin(repo, "new", amount="0.6", monthly="1", video_limit="10") == BeginResult.CREATED
    pending = repo.pending_reconciliation()
    assert [(p.idempotency_key, p.reason) for p in pending] == [("old", "stale_reservation")]
    assert pending[0].amount_usd == Decimal("1")


def test_uncertain_operation_is_reported_for_reconciliation(paid_db):
    from app.studio.application.budget import BeginResult

    repo, _ = paid_db
    assert begin(repo, "k1", amount="0.3") == BeginResult.CREATED
    repo.mark_uncertain("k1", "ambiguous")
    pending = repo.pending_reconciliation()
    assert [(p.idempotency_key, p.reason) for p in pending] == [("k1", "uncertain_operation")]


def test_finite_legacy_cost_counts_but_nan_is_still_unknown(paid_db):
    from app.studio.application.budget import BeginResult

    repo, conn = paid_db
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 'text', 'legacy', 'm', 0.4)", (VIDEO,))
    conn.commit()
    # linha legada finita conta pelo valor gravado; não marca o mês inteiro como desconhecido
    assert begin(repo, "after-finite", amount="0.6", monthly="1", video_limit="10") == BeginResult.CREATED
    conn.execute("INSERT INTO studio.usage_ledger(video_id, step, provider, model, cost_usd) "
                 "VALUES (%s, 'text', 'broken', 'm', 'NaN')", (VIDEO,))
    conn.commit()
    assert begin(repo, "blocked", amount="0.01", monthly="100", video_limit="100") == BeginResult.DENIED
    reasons = {row.reason for row in repo.pending_reconciliation()}
    assert {"legacy_unconfirmed_ledger", "unknown_ledger_cost"} <= reasons  # reportados, não silenciados


def test_unattributed_operation_uses_only_the_monthly_limit(paid_db):
    from app.studio.application.budget import BeginResult

    repo, _ = paid_db
    assert repo.begin("project-1", None, Decimal("0.6"), Decimal("1"), Decimal("0")) == BeginResult.CREATED
    assert repo.begin("project-2", None, Decimal("0.5"), Decimal("1"), Decimal("0")) == BeginResult.DENIED


def test_settlement_is_none_while_the_operation_is_not_confirmed(paid_db):
    from app.studio.application.budget import BeginResult

    repo, _ = paid_db
    assert begin(repo, "k1", amount="0.3") == BeginResult.CREATED
    assert repo.settlement("k1") is None
