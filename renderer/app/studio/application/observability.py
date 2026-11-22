"""Small, explicit retry primitive; never use for ambiguous external writes."""
import random
import time
import json
import logging
import threading
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone


class BridgeAlerts:
    """Passive, process-local observation; never contacts the bridge itself."""
    def __init__(self, *, clock=time.monotonic, max_age=300.0):
        self._clock, self._max_age = clock, max_age
        self._lock = threading.Lock()
        self._state, self._observed_at = "unknown", None

    def status(self):
        with self._lock:
            if self._observed_at is None or self._clock() - self._observed_at >= self._max_age:
                return "unknown"
            return self._state

    def observe(self, reachable: bool):
        with self._lock:
            observed_at = self._clock()
            previous = self._state if self._observed_at is not None and observed_at - self._observed_at < self._max_age else "unknown"
            self._state = "reachable" if reachable else "unreachable"
            self._observed_at = observed_at
            if not reachable and previous != "unreachable":
                logging.getLogger("studio.alerts").warning('{"event":"bridge_unreachable"}')


def oauth_expiry_status(expires_at=None, *, now=None, warning_window=timedelta(days=7)):
    """Classify trusted expiry metadata, not token validity or authorization."""
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(warning_window, timedelta) or warning_window < timedelta(0):
        raise ValueError("warning_window must be a non-negative timedelta")
    if (not isinstance(expires_at, datetime) or expires_at.utcoffset() is None
            or not isinstance(now, datetime) or now.utcoffset() is None):
        return "unknown"
    remaining = expires_at - now
    if remaining <= timedelta(0):
        return "expired"
    if remaining <= warning_window:
        return "expiring"
    return "not_expiring"


def check_oauth_expiry(expires_at=None, *, now=None, warning_window=timedelta(days=7)):
    status = oauth_expiry_status(expires_at, now=now, warning_window=warning_window)
    if status in ("expiring", "expired"):
        logging.getLogger("studio.alerts").warning('{"event":"oauth_%s"}', status)
    return status


def retry_transient(operation, *, attempts=3, sleep=time.sleep, random_value=random.random):
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            response = getattr(exc, "response", None)
            if status is None and response is not None:
                status = getattr(response, "status_code", None)
            transient = isinstance(exc, TimeoutError) or status == 429 or isinstance(status, int) and 500 <= status <= 599
            if not transient or attempt + 1 == attempts:
                raise
            sleep(min(30.0, 2**attempt) * random_value())


def record_provider_decision(*, kind, profile, candidate, effective, reason, model="",
                             attempt, production=False, logger=None):
    """Registra a decisão de provider que a execução vai seguir (F06.T02).

    Trilha única de observabilidade (log JSON `studio.providers`), sem segunda persistência:
    candidato decidido, provider realmente construído, motivo da política, modelo/versão e a
    tentativa (1 = decisão original; >1 = reavaliação explícita após indisponibilidade). Nomes e
    motivos são categorias do catálogo — nunca token, chave ou resposta crua do provedor.
    """
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason is required to audit a provider decision")
    payload = {
        "event": "provider_decision",
        "kind": str(kind),
        "profile": None if profile is None else str(getattr(profile, "value", profile)),
        "candidate": candidate,
        "effective": effective,
        "model": model or "",
        "reason": reason,
        "attempt": attempt,
        "production": bool(production),
    }
    (logger or logging.getLogger("studio.providers")).info(json.dumps(payload, ensure_ascii=False))


def run_step(repo, video_id, step, input_hash, operation, *, reusable=True):
    """Run an independently reusable step; operation must persist its own output."""
    guard = repo.render_guard(video_id) if step == "render" else nullcontext()
    with guard:
        return _run_step(repo, video_id, step, input_hash, operation, reusable=reusable)


def _run_step(repo, video_id, step, input_hash, operation, *, reusable):
    run_id = repo.begin(video_id, step, input_hash, reusable=reusable)
    if run_id is None:
        return False
    logger = logging.getLogger("studio.steps")
    attempt = None
    try:
        attempt = repo.attempt(run_id)
        operation()
        if not repo.finish(run_id, True):
            raise RuntimeError("step ownership lost")
    except Exception:
        try:
            repo.finish(run_id, False)
        except Exception:
            pass  # recovery on the next render; preserve the original failure
        if attempt is not None:
            logger.info(json.dumps({"video_id": video_id, "step": step, "attempt": attempt, "status": "FAILED"}))
        raise
    logger.info(json.dumps({"video_id": video_id, "step": step, "attempt": attempt, "status": "SUCCEEDED"}))
    return True


class Resume:
    """Resume the render only where the existing state proves it is appropriate."""
    def __init__(self, videos, start_render):
        self.videos, self.start_render = videos, start_render

    def execute(self, video_id):
        from .editorial import StateConflict, _require_video
        from ..domain.contracts import VideoStatus

        video = _require_video(self.videos, video_id)
        if video.status != VideoStatus.ASSETS_READY:
            raise StateConflict("resume is supported only from ASSETS_READY")
        return self.start_render.execute(video_id)
