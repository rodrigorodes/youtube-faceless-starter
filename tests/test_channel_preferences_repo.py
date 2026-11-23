import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.postgres.db import migrate
from app.studio.domain.contracts import ProductionMode, VideoFormat


@pytest.fixture()
def repo_env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    channels = PostgresChannelProfileRepository(connect)
    project = videos.create_project("Canal Prefs", niche="Tecnologia", language="pt-BR")
    return {"videos": videos, "channels": channels, "project_id": project.id}


def test_channel_profile_repo_persists_preferences(repo_env):
    channels = repo_env["channels"]
    pid = repo_env["project_id"]

    created = channels.create(
        pid,
        "Canal Prefs",
        default_mode=ProductionMode.diretor,
        default_format=VideoFormat.long,
    )
    assert created.default_mode is ProductionMode.diretor
    assert created.default_format is VideoFormat.long

    fetched = channels.get(created.id)
    assert fetched.default_mode is ProductionMode.diretor
    assert fetched.default_format is VideoFormat.long

    # Update
    updated = channels.update(created.id, 1, {"default_mode": "piloto"})
    assert updated.default_mode is ProductionMode.piloto

    # Update format too
    updated2 = channels.update(created.id, 2, {"default_format": "short"})
    assert updated2.default_format is VideoFormat.short

    # Fetch by project
    by_proj = channels.get_by_project(pid)
    assert by_proj.default_mode is ProductionMode.piloto
    assert by_proj.default_format is VideoFormat.short

    # List channels
    listed = channels.list()
    assert len(listed) == 1
    assert listed[0].default_mode is ProductionMode.piloto
    assert listed[0].default_format is VideoFormat.short


def test_channel_profile_repo_uses_defaults(repo_env):
    channels = repo_env["channels"]
    videos = repo_env["videos"]
    p2 = videos.create_project("Canal Defaults", niche="Geral", language="pt-BR")

    created = channels.create(p2.id, "Canal Defaults")
    assert created.default_mode is ProductionMode.piloto
    assert created.default_format is VideoFormat.short

    fetched = channels.get(created.id)
    assert fetched.default_mode is ProductionMode.piloto
    assert fetched.default_format is VideoFormat.short


def test_video_repo_persists_production_mode(repo_env):
    videos = repo_env["videos"]
    pid = repo_env["project_id"]

    video = videos.create_video(
        pid,
        "Tema Diretor",
        VideoFormat.short,
        production_mode=ProductionMode.diretor,
    )
    assert video.production_mode is ProductionMode.diretor

    fetched = videos.get_video(video.id)
    assert fetched.production_mode is ProductionMode.diretor


def test_video_repo_defaults_to_piloto_mode(repo_env):
    videos = repo_env["videos"]
    pid = repo_env["project_id"]

    video = videos.create_video(
        pid,
        "Tema Piloto Default",
        VideoFormat.short,
    )
    assert video.production_mode is ProductionMode.piloto

    fetched = videos.get_video(video.id)
    assert fetched.production_mode is ProductionMode.piloto
