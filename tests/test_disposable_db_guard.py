import pytest
import psycopg

from conftest import verified_test_connect


@pytest.mark.parametrize("dsn", [
    "host=one,two dbname=test",
    "postgresql://one,two/test",
    "host=one hostaddr=127.0.0.1,127.0.0.2 dbname=test",
    "host=one port=5432,5433 dbname=test",
    "service=example",
])
def test_guard_refuses_ambiguous_targets_before_connecting(dsn, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe target reached psycopg.connect")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    with pytest.raises(ValueError):
        verified_test_connect(dsn, "/nonexistent")


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE"])
def test_guard_refuses_libpq_redirect_environment(variable, monkeypatch):
    monkeypatch.setenv(variable, "unsafe")
    with pytest.raises(ValueError):
        verified_test_connect("host=one dbname=test", "/nonexistent")


def test_global_drop_fixture_checks_proof_on_its_connection(dsn, request, monkeypatch, tmp_path):
    import os

    proof = os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE")
    if not proof:
        pytest.skip("prova do PostgreSQL descartável ausente")
    with verified_test_connect(dsn, proof) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS studio")
        connection.execute("CREATE TABLE IF NOT EXISTS studio.guard_sentinel (id int)")
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", str(wrong))
    with pytest.raises(ValueError, match="proof"):
        request.getfixturevalue("conn")
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", proof)
    with verified_test_connect(dsn, proof) as connection:
        assert connection.execute("SELECT to_regclass('studio.guard_sentinel') IS NOT NULL").fetchone()[0]


def test_global_dsn_guards_secondary_legacy_connections(dsn, monkeypatch, tmp_path):
    wrong = tmp_path / "proof"
    wrong.write_text("f" * 64)
    monkeypatch.setenv("STUDIO_BUDGET_TEST_PROOF_FILE", str(wrong))
    with pytest.raises(ValueError, match="proof"):
        psycopg.connect(dsn)
