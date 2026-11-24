"""Prova de boot do app novo: o renderer sobe (importa `app.main:app`) e as rotas de fachada
respondem. Cobre o `/health` e a rota `/videos`, que existe apenas para declarar que o endpoint
legado (MVP) foi removido.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

LEGACY_MESSAGE = "legacy unauthenticated endpoint removed"


def test_boot_imports_app_and_health_responds():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["ffmpeg"] is True
    assert body["studio_db"] in {"ok", "unavailable"}  # sem banco configurado: degradado, não quebra


def test_legacy_videos_route_is_replaced_by_410():
    client = TestClient(app)
    assert client.get("/videos").status_code == 410
    assert client.post("/videos", json={"topic": "x"}).status_code == 410
    assert client.head("/videos").status_code == 410
    assert LEGACY_MESSAGE in client.get("/videos").json()["detail"]
    nested = client.get("/videos/abc/file")
    assert nested.status_code == 410 and LEGACY_MESSAGE in nested.json()["detail"]


# -- PROD-03: o lifespan re-dirige runs em voo órfãos, sem derrubar a subida --


class _FakeStudio:
    """Dublê do `Studio` para exercitar o lifespan sem banco."""

    def __init__(self, *, recovered=(), error=None):
        self.recovered, self.error = tuple(recovered), error
        self.recover_calls = 0
        self.use_cases_calls = 0
        self.orphan_calls = 0
        self.orphan_error = None
        self.orphan_gate = None
        self.active = self.max_active = 0
        self.settings = type("S", (), {"recovery_interval_seconds": 0})()

    def recover_orphans(self):
        self.orphan_calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.orphan_gate is not None:
                self.orphan_gate.wait(2)
            if self.orphan_error is not None:
                raise self.orphan_error
            return ()
        finally:
            self.active -= 1

    def use_cases(self):
        self.use_cases_calls += 1
        return None  # migração/no-op: o boot segue

    def recover_in_flight(self):
        self.recover_calls += 1
        if self.error is not None:
            raise self.error
        return self.recovered

    def shutdown(self):
        pass

    def ping(self):
        return True


def _boot_with(monkeypatch, fake):
    import app.main as main
    monkeypatch.setattr(main, "studio", fake)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    return fake


def test_lifespan_redrives_orphan_runs_on_boot(monkeypatch):
    fake = _boot_with(monkeypatch, _FakeStudio(recovered=("a" * 32,)))
    assert fake.recover_calls == 1  # a recuperação é chamada depois da migração


def test_lifespan_recovery_is_a_noop_without_in_flight_runs(monkeypatch):
    fake = _boot_with(monkeypatch, _FakeStudio())
    assert fake.recover_calls == 1  # chamada, mas nada a re-dirigir: não quebra


def test_lifespan_startup_survives_a_failing_recovery(monkeypatch):
    """Banco indisponível/erro na varredura: o app sobe de qualquer forma."""
    fake = _boot_with(monkeypatch, _FakeStudio(error=RuntimeError("banco caiu")))
    assert fake.recover_calls == 1


# -- R03: varredura periódica de órfãos --


def _wait_until(pred, timeout=2.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end and not pred():
        time.sleep(0.005)
    return pred()


def _with_interval(monkeypatch, fake, interval):
    import app.main as main
    fake.settings.recovery_interval_seconds = interval
    monkeypatch.setattr(main, "studio", fake)
    return main


def test_recovery_loop_sweeps_repeatedly_and_survives_errors(monkeypatch):
    import time
    fake = _FakeStudio()
    fake.orphan_error = RuntimeError("banco caiu")
    main = _with_interval(monkeypatch, fake, 0.01)
    with TestClient(main.app):
        assert _wait_until(lambda: fake.orphan_calls >= 3)  # erro não mata o laço
    calls = fake.orphan_calls
    time.sleep(0.05)
    assert fake.orphan_calls == calls  # tarefa cancelada no shutdown


def test_recovery_loop_disabled_when_interval_is_zero(monkeypatch):
    import time
    fake = _FakeStudio()
    main = _with_interval(monkeypatch, fake, 0)
    with TestClient(main.app):
        time.sleep(0.05)
    assert fake.orphan_calls == 0


def test_recovery_loop_never_overlaps(monkeypatch):
    import threading
    import time
    fake = _FakeStudio()
    fake.orphan_gate = threading.Event()
    main = _with_interval(monkeypatch, fake, 0.01)
    with TestClient(main.app):
        assert _wait_until(lambda: fake.orphan_calls >= 1)
        time.sleep(0.1)
        assert fake.orphan_calls == 1 and fake.max_active == 1
        fake.orphan_gate.set()
    assert fake.max_active == 1
