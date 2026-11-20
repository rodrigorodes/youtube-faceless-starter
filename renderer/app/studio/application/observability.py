"""Small, explicit retry primitive; never use for ambiguous external writes."""
import random
import time
import json
import logging
from contextlib import nullcontext


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
