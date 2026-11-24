"""Primitiva de heartbeat do lease: sem banco, sem sleep real (renew/clock/wait falsos)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.application.lease_heartbeat import LeaseHeartbeat, LeaseLost  # noqa: E402
from app.studio.domain.production_run import LeaseResult  # noqa: E402


class Fake:
    """Relógio/espera falsos: cada wait avança o relógio; `max_waits` pede parada."""

    def __init__(self, results, max_waits=50):
        self.results = list(results)
        self.now = 0.0
        self.calls = 0
        self.waits = []
        self.max_waits = max_waits

    def clock(self):
        return self.now

    def renew(self):
        self.calls += 1
        r = self.results.pop(0) if self.results else LeaseResult.RENEWED
        if isinstance(r, Exception):
            raise r
        return r

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return len(self.waits) >= self.max_waits


def run(fake, lease=30.0):
    hb = LeaseHeartbeat(renew=fake.renew, lease_seconds=lease, clock=fake.clock, wait=fake.wait)
    with hb:
        hb._thread.join(5)
    return hb


def test_renewed_keeps_lease_each_interval():
    f = Fake([], max_waits=4)
    hb = run(f)
    assert hb.lost is False
    assert f.calls == 4
    assert set(f.waits) == {10.0}


@pytest.mark.parametrize("res", [LeaseResult.LOST, LeaseResult.UNKNOWN])
def test_lost_or_unknown_stops_without_retry(res):
    f = Fake([res])
    hb = run(f)
    assert hb.lost is True
    assert f.calls == 1
    with pytest.raises(LeaseLost):
        hb.ensure_held()


def test_exceptions_self_fence_after_90_percent():
    f = Fake([LeaseResult.RENEWED] + [RuntimeError("db")] * 20)
    hb = run(f)
    assert hb.lost is True
    assert f.now - 0.0 >= 27.0
    assert f.calls < 21
    assert 5.0 in f.waits


def test_exception_then_renewed_keeps_holding_and_advances_last_ok():
    f = Fake([RuntimeError("x"), LeaseResult.RENEWED], max_waits=6)
    hb = run(f)
    assert hb.lost is False
    assert hb.last_ok > 0.0


def test_stop_idempotent_and_thread_dead():
    f = Fake([], max_waits=2)
    hb = LeaseHeartbeat(renew=f.renew, lease_seconds=30, clock=f.clock, wait=f.wait)
    with hb:
        pass
    hb.stop()
    hb.stop()
    assert not hb._thread.is_alive()
    assert hb._thread.daemon is True


def test_no_renew_after_lost():
    f = Fake([LeaseResult.LOST])
    hb = run(f)
    n = f.calls
    hb.stop()
    assert f.calls == n == 1
