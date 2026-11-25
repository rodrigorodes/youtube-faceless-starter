"""Validação das regras de isolamento de ambientes e separação de suites (FS-02 / G3).

Garante por código estático e de comportamento que:
1. docker-compose.e2e.yml desativa publicação (STUDIO_PUBLICATION_ENABLED=0) e usa porta parametrizável;
2. scripts/run-e2e-tests.sh protege a stack DEV (recusa porta 8000 sem STUDIO_E2E_ALLOW_DEV=1);
3. scripts/run-e2e-full.sh parametriza projeto e porta evitando colisão em execuções simultâneas;
4. scripts/test-container.sh provê volume gravável seguro para evidências/relatórios em checkout RO;
5. As fixtures de E2E (e2e_full e e2e_ux) guardam imports e destinos com fail-fast.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_e2e_isolation_and_publication_guard():
    content = (ROOT / "docker-compose.e2e.yml").read_text(encoding="utf-8")
    assert "STUDIO_PUBLICATION_ENABLED: \"0\"" in content or "STUDIO_PUBLICATION_ENABLED: '0'" in content
    assert "${E2E_PORT:-8100}:8000" in content
    assert "tmpfs:" in content
    assert "/data" in content
    assert "/var/lib/postgresql/data" in content


def test_run_e2e_tests_destination_guard_against_dev_stack():
    script = (ROOT / "scripts/run-e2e-tests.sh").read_text(encoding="utf-8")
    assert "STUDIO_E2E_ALLOW_DEV" in script
    assert "8000" in script
    assert "8100" in script
    assert "ERRO DE DESTINO" in script


def test_run_e2e_full_project_isolation():
    script = (ROOT / "scripts/run-e2e-full.sh").read_text(encoding="utf-8")
    assert "RUN_ID=" in script or "E2E_RUN_ID" in script
    assert "PROJECT_NAME=" in script or "E2E_PROJECT_NAME" in script
    assert "E2E_PORT=" in script


def test_test_container_provides_writable_reports_mount():
    script = (ROOT / "scripts/test-container.sh").read_text(encoding="utf-8")
    assert "storage/test-reports" in script
    assert ":rw" in script
    assert "/w:ro" in script


def test_e2e_conftest_guards_destination_and_dependencies():
    full_conftest = (ROOT / "tests/e2e_full/conftest.py").read_text(encoding="utf-8")
    assert "Browser is None" in full_conftest
    assert "STUDIO_E2E_ISOLATED" in full_conftest
    assert "STUDIO_E2E_ALLOW_DEV" in full_conftest

    ux_conftest = (ROOT / "tests/e2e_ux/conftest.py").read_text(encoding="utf-8")
    assert "Browser is None" in ux_conftest
    assert "_validate_destination" in ux_conftest
    assert "STUDIO_E2E_ALLOW_DEV" in ux_conftest
