"""Testes de persistência dos novos parâmetros de produção e CreativeBrief (Onda 4 / Task 1)."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.domain.contracts import Video, VideoFormat, ProductionMode, VideoStatus  # noqa: E402


def test_video_model_has_production_and_creative_brief_fields():
    video = Video(
        id="vid_test_123",
        project_id="proj_1",
        topic="Teste de Tópico",
        format=VideoFormat.short,
        status=VideoStatus.IDEA,
        production_mode=ProductionMode.piloto,
        pacing_preset="dynamic",
        target_duration_s=60,
        budget_cap_usd=2.50,
        creative_brief={"hook": "Gancho inicial", "topic": "Teste de Tópico"}
    )
    assert video.pacing_preset == "dynamic"
    assert video.target_duration_s == 60
    assert video.budget_cap_usd == 2.50
    assert video.creative_brief["hook"] == "Gancho inicial"


def test_postgres_repo_creates_and_reads_video_production_settings(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("canal_test")

    video = repo.create_video(
        project_id=project.id,
        topic="Vídeo com Pacing e Duração",
        fmt=VideoFormat.short,
        production_mode=ProductionMode.piloto,
        target_duration_s=45,
        pacing_preset="balanced",
        budget_cap_usd=5.00,
    )
    assert video.target_duration_s == 45
    assert video.pacing_preset == "balanced"
    assert video.budget_cap_usd == 5.00

    fetched = repo.get_video(video.id)
    assert fetched is not None
    assert fetched.target_duration_s == 45
    assert fetched.pacing_preset == "balanced"
    assert fetched.budget_cap_usd == 5.00


def test_postgres_repo_updates_creative_brief(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    repo = PostgresVideoRepository(connect)
    project = repo.create_project("canal_brief")

    video = repo.create_video(
        project_id=project.id,
        topic="Vídeo para Briefing",
        fmt=VideoFormat.short,
    )
    assert video.creative_brief is None

    brief_data = {
        "schema_version": 1,
        "topic": "Vídeo para Briefing",
        "narrative_goal": "Explicar conceito",
        "hook": "Você sabia disso?",
        "content_structure": ["Intro", "Desenvolvimento"],
        "tone": "Curioso",
        "pacing": "Dinâmico",
        "visual_direction": "Tons escuros",
        "recommended_media_types": ["image", "video"],
        "caption_strategy": "Palavra ativa destacada",
        "audio_guidance": "Trilha ambiente",
        "max_budget_usd": 3.0,
        "quality_criteria": ["Qualidade HD"],
    }

    repo.update_video_creative_brief(video.id, brief_data)

    fetched = repo.get_video(video.id)
    assert fetched is not None
    assert fetched.creative_brief is not None
    assert fetched.creative_brief["hook"] == "Você sabia disso?"
    assert fetched.creative_brief["tone"] == "Curioso"
