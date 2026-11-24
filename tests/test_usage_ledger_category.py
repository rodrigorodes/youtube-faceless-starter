"""Testes da rastreabilidade de custos por categoria no usage_ledger (Onda 6 / Task 1)."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.editorial_repo import PostgresUsageRepository  # noqa: E402
from app.studio.domain.contracts import UsageEntry, VideoFormat  # noqa: E402


def test_usage_entry_model_has_category_and_duration_fields():
    entry = UsageEntry(
        step="render",
        provider="ffmpeg",
        model="h264",
        cost_usd=0.05,
        category="render",
        duration_ms=4500,
        attempt=1,
    )
    assert entry.category == "render"
    assert entry.duration_ms == 4500
    assert entry.attempt == 1


def test_postgres_usage_repo_records_and_aggregates_by_category(conn, dsn):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    v_repo = PostgresVideoRepository(connect)
    u_repo = PostgresUsageRepository(connect)

    project = v_repo.create_project("Canal Ledger Category")
    video = v_repo.create_video(project.id, "Tema Ledger", VideoFormat.short)

    # Grava entradas de diferentes categorias
    u_repo.record(video.id, UsageEntry(
        step="script",
        provider="openai",
        model="gpt-4o",
        cost_usd=0.12,
        category="llm",
        duration_ms=1200,
    ))
    u_repo.record(video.id, UsageEntry(
        step="speech",
        provider="piper",
        model="pt_BR",
        cost_usd=0.04,
        category="tts",
        duration_ms=3000,
    ))
    u_repo.record(video.id, UsageEntry(
        step="images",
        provider="pexels",
        model="stock",
        cost_usd=0.00,
        category="image",
        duration_ms=800,
    ))
    u_repo.record(video.id, UsageEntry(
        step="render",
        provider="ffmpeg",
        model="local",
        cost_usd=0.08,
        category="render",
        duration_ms=15000,
    ))

    # Total geral do vídeo
    assert pytest.approx(u_repo.spent_video(video.id), 0.001) == 0.24

    # Agregação por categoria
    by_category = u_repo.spent_by_category(video.id)
    assert pytest.approx(by_category.get("llm", 0.0), 0.001) == 0.12
    assert pytest.approx(by_category.get("tts", 0.0), 0.001) == 0.04
    assert pytest.approx(by_category.get("image", 0.0), 0.001) == 0.00
    assert pytest.approx(by_category.get("render", 0.0), 0.001) == 0.08
