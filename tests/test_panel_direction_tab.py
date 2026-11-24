"""Testes da aba Direção Criativa e endpoints de briefing (Onda 4 / Task 3)."""
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
from app.studio.api.panel_video_nav import VIDEO_AREAS, normalize_area  # noqa: E402
from app.studio.domain.contracts import VideoFormat, ProductionMode  # noqa: E402


def test_video_nav_includes_direcao_area():
    area_ids = [area_id for area_id, _ in VIDEO_AREAS]
    assert "direcao" in area_ids
    assert normalize_area("direcao") == "direcao"


def test_direction_endpoints_get_post_and_put(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("Canal Direção")
    video = repo.create_video(project.id, "Tema de Teste para Direção", VideoFormat.short)

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    # 1. GET inicial: sem briefing
    res = client.get(f"/studio/videos/{video.id}/direction")
    assert res.status_code == 200, res.text
    assert res.json()["brief"] is None

    # 2. POST com brief estruturado
    brief_payload = {
        "schema_version": 1,
        "topic": "Tema de Teste para Direção",
        "narrative_goal": "Apresentar a história secreta",
        "hook": "Você sabia que existe uma cidade subterrânea?",
        "content_structure": ["O Gancho Inicial", "A Descoberta Histórica"],
        "tone": "Misterioso e instigante",
        "pacing": "Dinâmico com cortes a cada 2,5s",
        "visual_direction": "Túneis com iluminação quente",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Palavra ativa com realce",
        "audio_guidance": "Trilha grave sem percussão pesada",
        "max_budget_usd": 2.50,
        "quality_criteria": ["Boa iluminação", "Sem repetição de mídia"],
    }
    res_post = client.post(f"/studio/videos/{video.id}/direction", json={"brief": brief_payload})
    assert res_post.status_code == 200, res_post.text
    assert res_post.json()["brief"]["hook"] == brief_payload["hook"]

    # 3. GET após gravação
    res_get2 = client.get(f"/studio/videos/{video.id}/direction")
    assert res_get2.status_code == 200
    assert res_get2.json()["brief"]["narrative_goal"] == "Apresentar a história secreta"

    # 4. PUT atualizando um campo
    brief_payload["hook"] = "Gancho atualizado pelo criador!"
    res_put = client.put(f"/studio/videos/{video.id}/direction", json={"brief": brief_payload})
    assert res_put.status_code == 200
    assert res_put.json()["brief"]["hook"] == "Gancho atualizado pelo criador!"

    # 5. Verifica no repositório
    v_db = repo.get_video(video.id)
    assert v_db.creative_brief["hook"] == "Gancho atualizado pelo criador!"


def test_workspace_html_renders_direction_tab(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("Canal Workspace")
    video = repo.create_video(project.id, "Tema Workspace", VideoFormat.short)

    brief_data = {
        "schema_version": 1,
        "topic": "Tema Workspace",
        "narrative_goal": "Objetivo Visível",
        "hook": "Gancho Visível no Workspace",
        "content_structure": ["Secao 1", "Secao 2"],
        "tone": "Documental",
        "pacing": "Dinâmico",
        "visual_direction": "Visual Escuro",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Safe area",
        "audio_guidance": "Audio leve",
        "max_budget_usd": 1.0,
        "quality_criteria": [],
    }
    repo.update_video_creative_brief(video.id, brief_data)

    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app, headers={"Authorization": "Bearer test-worker-token"})

    res = client.get(f"/studio/panel/videos/{video.id}/direcao")
    assert res.status_code == 200, res.text
    html = res.text
    assert "Direção criativa" in html
    assert "Gancho Visível no Workspace" in html
    assert "Objetivo Visível" in html
    assert "Salvar ajustes do briefing" in html
