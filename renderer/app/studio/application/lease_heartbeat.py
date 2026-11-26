"""Heartbeat do lease de uma etapa: renova em thread daemon enquanto o handler síncrono executa.

Puro (sem banco): a renovação é injetada. Nunca renova depois de perder o lease; se não houver
renovação confirmada por 90% do lease (ex.: banco indisponível), o próprio processo se considera
sem posse (auto-cerco) antes de o lease expirar para outro executor.
"""
import logging
import threading
import time
from typing import Callable, Optional

from app.studio.domain.production_run import LeaseResult

logger = logging.getLogger(__name__)

_RETRY_CAP_SECONDS = 5.0
_FENCE_RATIO = 0.9
_JOIN_TIMEOUT_SECONDS = 2.0


class LeaseLost(RuntimeError):
    """O lease da etapa foi perdido (ou presumido perdido): o executor deve parar de escrever."""


class StageLease:
    """Visão mínima da posse, usada por quem precisa checar antes de efeitos externos."""

    def ensure_held(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LeaseHeartbeat(StageLease):
    """`last_ok` nasce na construção (o lease foi adquirido antes do objeto existir: escolha
    conservadora). Construa imediatamente antes de `start()`.

    `lost` é sensível ao tempo: também é True quando `clock() - last_ok >= 90%` do lease, mesmo que
    um `renew()` bloqueado nunca retorne. Uma vez observado, o estado é preso (latch): resultado
    tardio, inclusive RENEWED, não o desfaz.
    """

    def __init__(
        self,
        renew: Callable[[], LeaseResult],
        lease_seconds: float,
        interval_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        wait: Optional[Callable[[float], bool]] = None,
    ):
        self._renew = renew
        self._lease_seconds = float(lease_seconds)
        self._interval = float(interval_seconds or self._lease_seconds / 3)
        self._clock = clock
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait
        self._lost = threading.Event()
        self.last_ok = self._clock()
        self._started = False
        self._thread = threading.Thread(target=self._run, name="lease-heartbeat", daemon=True)

    @property
    def lost(self) -> bool:
        if self._lost.is_set():
            return True
        if self._clock() - self.last_ok >= self._lease_seconds * _FENCE_RATIO:
            self._mark_lost("sem renovação confirmada dentro de 90% do lease")
            return True
        return False

    def ensure_held(self) -> None:
        if self.lost:
            raise LeaseLost("lease da etapa perdido")

    def revoke(self, reason: str = "lease revoked") -> None:
        """Cerca imediatamente o processo local (latch irreversível), sem esperar o próximo tick."""
        self._mark_lost(reason)

    def start(self) -> "LeaseHeartbeat":
        if self._stop.is_set():
            raise RuntimeError("LeaseHeartbeat já foi parado; crie outro")
        if not self._started:
            self._started = True
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)

    def __enter__(self) -> "LeaseHeartbeat":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def _mark_lost(self, reason: str) -> None:
        self._lost.set()
        logger.warning("lease heartbeat: posse perdida (%s)", reason)

    def _run(self) -> None:
        while not self._stop.is_set():
            base = self._clock()
            delay = self._interval
            try:
                result = self._renew()
            except Exception as exc:  # falha transitória: tenta de novo mais cedo
                logger.warning("lease heartbeat: falha ao renovar (%s)", type(exc).__name__)
                delay = min(self._interval, _RETRY_CAP_SECONDS)
            else:
                if result == LeaseResult.RENEWED:
                    if self._lost.is_set():
                        return
                    self.last_ok = base
                else:
                    self._mark_lost(str(getattr(result, "value", result)))
                    return
            if self.lost:
                return
            if self._wait(delay):
                return
