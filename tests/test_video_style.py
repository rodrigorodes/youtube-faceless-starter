"""Override de estilo por vídeo (VS-02b): o canal herda, o vídeo pode sobrepor. Postgres real."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository  # noqa: E402
from app.studio.application.errors import VisualStyleNotFound  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402


@pytest.fixture()
def env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal", niche="Geral", language="pt-BR")
    return {"videos": videos, "styles": PostgresVisualStyleRepository(connect), "project_id": project.id}


def test_a_new_video_inherits_the_channel_style(env):
    video = env["videos"].create_video(env["project_id"], "ADE 2026", VideoFormat.short)
    assert video.style_id is None  # nulo = herda o estilo do canal
    assert env["videos"].get_video(video.id).style_id is None


def test_a_video_can_override_and_then_clear_the_style(env):
    style = env["styles"].create("Cinemático")
    video = env["videos"].create_video(env["project_id"], "ADE 2026", VideoFormat.short)
    overridden = env["videos"].set_video_style(video.id, style.id)
    assert overridden.style_id == style.id
    assert env["videos"].get_video(video.id).style_id == style.id  # persistiu
    cleared = env["videos"].set_video_style(video.id, None)
    assert cleared.style_id is None  # volta a herdar do canal


def test_an_unknown_style_is_refused_never_a_broken_link(env):
    video = env["videos"].create_video(env["project_id"], "ADE 2026", VideoFormat.short)
    with pytest.raises(VisualStyleNotFound):
        env["videos"].set_video_style(video.id, "f" * 32)
    assert env["videos"].get_video(video.id).style_id is None  # nada gravado


def test_setting_style_on_an_unknown_video_returns_none(env):
    style = env["styles"].create("Cinemático")
    assert env["videos"].set_video_style("a" * 32, style.id) is None
