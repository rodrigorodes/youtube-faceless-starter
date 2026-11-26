import os
from pathlib import Path
import secrets

import pytest

os.environ.setdefault("STUDIO_ALLOWED_HOSTS", "localhost,127.0.0.1,renderer,testserver")


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: smoke test rápido do fluxo Studio (ex.: 15s short, não substitui piloto/slice)")
    config.addinivalue_line("markers", "rec04_slice: vertical slice real 60-90s via rotas HTTP do Studio e ProductionCoordinator (REC-04.01)")
    config.addinivalue_line("markers", "rec04_documentary: documentário real 5-8min via rotas HTTP do Studio + comparação pareada V4-00 (REC-04.02)")


def verify_disposable_connection(connection, proof_path):
    import psycopg
    try:
        proof = Path(proof_path).read_text(encoding="ascii").strip()
        if len(proof) != 64 or any(c not in "0123456789abcdef" for c in proof):
            raise ValueError("invalid disposable database proof")
        server_proof = connection.execute(
            "SELECT pg_read_file('/budget-test-proof/proof')"
        ).fetchone()[0].strip()
        if not secrets.compare_digest(proof, server_proof):
            raise ValueError("disposable database proof mismatch")
    except (OSError, UnicodeError, psycopg.Error, TypeError) as exc:
        raise ValueError("disposable database proof unavailable") from exc


def verified_test_connect(dsn, proof_path, *, autocommit=False, _connect=None, **kwargs):
    """Check each physical connection before permitting writes."""
    import psycopg
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    if (not info.get("host") or "," in info["host"]
            or "," in info.get("port", "")
            or info.get("hostaddr") or info.get("service")
            or os.environ.get("PGHOSTADDR") or os.environ.get("PGSERVICE")
            or any(key in kwargs for key in ("host", "hostaddr", "service"))
            or "," in str(kwargs.get("port", ""))):
        raise ValueError("single explicit host required for disposable database")
    # Port is explicit too; refuse environment overrides that can redirect a connection.
    kwargs.setdefault("port", info.get("port", "5432"))
    connection = (_connect or psycopg.connect)(dsn, **kwargs)
    try:
        verify_disposable_connection(connection, proof_path)
        connection.rollback()
        connection.autocommit = autocommit
        return connection
    except BaseException:
        connection.close()
        raise


@pytest.fixture(autouse=True)
def studio_test_credentials():
    with pytest.MonkeyPatch.context() as env:
        env.setenv("STUDIO_BROWSER_USER", "test-user")
        env.setenv("STUDIO_BROWSER_PASSWORD", "test-browser-password")
        env.setenv("STUDIO_WORKER_TOKEN", "test-worker-token")
        yield


@pytest.fixture()
def registered_providers():
    """Registra providers de teste no `_REGISTRY` global e **desfaz** ao final.

    Achado 11: `register()` em nível de módulo (`tests/test_editorial_api.py`,
    `tests/test_render_api.py`) rodava na coleta e **vazava** para `test_port_contracts`, que
    compara o catálogo do produto com o registro — duas falhas falsas na suíte completa, com o
    arquivo isolado passando. O `_REGISTRY` é global; registrar dentro do teste, com restauração,
    mantém o catálogo do produto visível para os outros testes.
    """
    from app.studio.application.config import _REGISTRY, register

    snapshot = dict(_REGISTRY)
    try:
        yield register
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)


@pytest.fixture()
def dsn(monkeypatch):
    value = os.environ.get("STUDIO_TEST_DSN")
    if not value:
        pytest.skip("STUDIO_TEST_DSN não definido (Postgres de teste ausente)")
    import psycopg
    original = psycopg.connect

    def guarded_connect(conninfo="", **kwargs):
        return verified_test_connect(
            conninfo, os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE", ""),
            _connect=original, **kwargs,
        )

    monkeypatch.setattr(psycopg, "connect", guarded_connect)
    return value


@pytest.fixture()
def conn(dsn):
    proof_path = os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE")
    if not proof_path:
        pytest.fail("prova do PostgreSQL descartável é necessária antes de remover o schema", pytrace=False)
    connection = verified_test_connect(dsn, proof_path)
    try:
        connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.close()
