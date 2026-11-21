import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .studio.api.routes import make_router
from .studio.composition import Settings, Studio

studio = Studio(Settings.from_env())  # estado de domínio (Postgres); sem banco o app sobe e /health indica indisponível


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(studio.use_cases)  # migra o schema studio; falha não derruba o app
    yield
    await asyncio.to_thread(studio.shutdown)


app = FastAPI(title="Faceless Renderer MVP", version="0.3.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "ffmpeg": True, "studio_db": "ok" if studio.ping() else "unavailable"}


@app.api_route("/videos", methods=["GET", "POST", "HEAD"])
@app.api_route("/videos/{path:path}", methods=["GET", "POST", "HEAD"])
def legacy_videos_removed():
    raise HTTPException(410, "legacy unauthenticated endpoint removed; use /studio/panel or /studio/videos")


app.include_router(make_router(lambda: studio.use_cases(), lambda: studio.ping()))
