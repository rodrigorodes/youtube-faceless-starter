"""Testes do formulário Novo Vídeo com parâmetros ativos e API (Onda 4 / Task 2)."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.api.panel_new_video import render_new_video_v3  # noqa: E402
from app.studio.api.panel_production import NewVideoView, PipelineStage  # noqa: E402
from app.studio.application.panel import MonthCost, CostBreakdown  # noqa: E402
from app.studio.domain.production_run import ProductionStage  # noqa: E402
from app.studio.domain.contracts import VideoFormat, ProductionMode  # noqa: E402


def test_render_new_video_v3_contains_pacing_and_cost_fields():
    month = MonthCost(cap_usd=15.0, known_usd=2.4, unknown_calls=0, percent=16, text="US$ 2,40 de US$ 15,00",
                      breakdown=CostBreakdown())
    pipeline = (PipelineStage(ProductionStage.SCRIPT, "Roteiro", True),)
    view = NewVideoView(
        projects=[("proj_1", "Canal Teste")],
        month=month,
        pipeline=pipeline,
        selected_project_id="proj_1",
        styles=(("s1", "Cinemático"),),
        inherited_style_name="Cinemático",
        channel_language="pt-BR",
        channel_voice="Voz Padrão",
        has_profile=True,
    )
    html, _ = render_new_video_v3(view)
    assert 'name="ritmo-cortes"' in html or 'name="pacing"' in html
    assert 'Dinâmico' in html
    assert 'Balanceado' in html
    assert 'Cinemático' in html
    assert 'id="teto-custo"' in html
    assert 'id="duracao-alvo"' in html
    assert 'id="resumo-ritmo"' in html
    assert 'id="resumo-duracao"' in html
    assert 'id="resumo-teto"' in html


def test_api_create_video_persists_pacing_duration_and_budget(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("Canal API")

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    payload = {
        "project_id": project.id,
        "topic": "Tema com Parâmetros Ativos",
        "format": "short",
        "production_mode": "piloto",
        "target_duration_s": 45,
        "pacing_preset": "balanced",
        "budget_cap_usd": 3.50,
    }

    res = client.post("/studio/videos", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["target_duration_s"] == 45
    assert data["pacing_preset"] == "balanced"
    assert data["budget_cap_usd"] == 3.50

    # Verifica leitura persistida
    video = repo.get_video(data["id"])
    assert video is not None
    assert video.target_duration_s == 45
    assert video.pacing_preset == "balanced"
    assert video.budget_cap_usd == 3.50
