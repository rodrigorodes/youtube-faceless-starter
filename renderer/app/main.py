import asyncio
import logging
import shutil
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException

from .studio.api.routes import make_router
from .studio.composition import Settings, Studio

logger = logging.getLogger("studio.boot")

studio = Studio(Settings.from_env())  # estado de domínio (Postgres); sem banco o app sobe e /health indica indisponível


async def _recovery_loop(studio, interval):
    while True:
        await asyncio.sleep(interval)
        try:
            recovered = await asyncio.to_thread(studio.recover_orphans)
            if recovered:
                logger.warning("production: %d run(s) orfao(s) re-dirigido(s) pela varredura periodica",
                               len(recovered))
        except Exception:  # nunca derruba o laço; próxima rodada tenta de novo
            logger.warning("production: varredura periodica indisponivel", exc_info=True)


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(studio.use_cases)  # migra o schema studio; falha não derruba o app
    try:
        # Depois da migração: re-dirige os runs de produção em voo que ficaram órfãos (PROD-03),
        # como um deploy/queda no meio de uma produção. Em thread para não bloquear a subida.
        recovered = await asyncio.to_thread(studio.recover_in_flight)
        if recovered:
            logger.warning("production: %d run(s) em voo orfao(s) re-dirigido(s) no boot",
                           len(recovered))
    except Exception:  # banco indisponível/erro na varredura nunca derruba a subida (no-op)
        logger.warning("production: recuperacao de runs em voo indisponivel no boot", exc_info=True)
    interval = studio.settings.recovery_interval_seconds
    task = asyncio.create_task(_recovery_loop(studio, interval)) if interval > 0 else None
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await asyncio.to_thread(studio.shutdown)


app = FastAPI(title="Faceless Renderer MVP", version="0.3.0", lifespan=lifespan)


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


@app.get("/health")
def health():
    return {"status": "ok", "ffmpeg": _check_ffmpeg(), "studio_db": "ok" if studio.ping() else "unavailable"}


@app.get("/ready")
def ready():
    db_ok = bool(studio.ping())
    ffmpeg_ok = _check_ffmpeg()
    if not (db_ok and ffmpeg_ok):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "studio_db": "ok" if db_ok else "unavailable",
                "ffmpeg": "ok" if ffmpeg_ok else "unavailable",
            },
        )
    return {
        "status": "ready",
        "studio_db": "ok",
        "ffmpeg": "ok",
    }


@app.api_route("/videos", methods=["GET", "POST", "HEAD"])
@app.api_route("/videos/{path:path}", methods=["GET", "POST", "HEAD"])
def legacy_videos_removed():
    raise HTTPException(410, "legacy unauthenticated endpoint removed; use /studio/panel or /studio/videos")


app.include_router(make_router(lambda: studio.use_cases(), lambda: studio.ping()))
