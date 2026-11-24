"""Testes do endpoint de custos por categoria da API (Onda 6 / Task 2)."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import UsageEntry, VideoFormat  # noqa: E402


def test_video_cost_breakdown_endpoint(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    u_repo = PostgresUsageRepository(connect)

    project = v_repo.create_project("Canal API Custos")
    video = v_repo.create_video(project.id, "Tema API Custos", VideoFormat.short)

    u_repo.record(video.id, UsageEntry(
        step="script",
        provider="openai",
        model="gpt-4o",
        cost_usd=0.15,
        category="llm",
    ))
    u_repo.record(video.id, UsageEntry(
        step="speech",
        provider="piper",
        model="pt_BR",
        cost_usd=0.05,
        category="tts",
    ))
    u_repo.record(video.id, UsageEntry(
        step="render",
        provider="ffmpeg",
        model="h264",
        cost_usd=0.10,
        category="render",
    ))

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/videos/{video.id}/cost-breakdown")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["video_id"] == video.id
    assert pytest.approx(data["total_usd"], 0.001) == 0.30
    assert pytest.approx(data["categories"]["llm"], 0.001) == 0.15
    assert pytest.approx(data["categories"]["tts"], 0.001) == 0.05
    assert pytest.approx(data["categories"]["render"], 0.001) == 0.10
