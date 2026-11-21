"""Override de estilo por vídeo (VS-05b): API + telas, com Postgres descartável.

O canal herda o estilo da biblioteca; o vídeo pode **sobrepor** ou voltar a herdar. Cobre a rota
`PATCH /videos/{id}/style` (fixar, limpar, estilo inexistente → 422, vídeo inexistente → 404) e a
tela do vídeo: "herda do canal (nome)" quando nulo e o estilo próprio quando não é — sempre com o
nome do estilo do canal **certo**.
"""
import base64
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository  # noqa: E402
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
POST_HEADER = {**AUTH_HEADER, "Origin": "http://testserver"}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    styles = PostgresVisualStyleRepository(connect)
    project = videos.create_project("Canal H", niche="Geral", language="pt-BR")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "styles": styles,
            "project": project, "connect": connect, "conn": conn}


def _page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def _channel(env, project_id, **fields):
    payload = {"name": "História"}
    payload.update(fields)
    r = env["client"].post(f"/studio/projects/{project_id}/channels", json=payload, headers=WORKER_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


def _video_page(env, video_id):
    return env["client"].get(f"/studio/panel/videos/{video_id}", headers=AUTH_HEADER)


# ----------------------------------------------------------------------- API


def test_set_and_clear_the_video_style(env):
    style = env["styles"].create("Cinemático")
    video = env["videos"].create_video(env["project"].id, "ADE 2026", VideoFormat.short)
    client = env["client"]

    fixed = client.patch(f"/studio/videos/{video.id}/style", json={"style_id": style.id}, headers=POST_HEADER)
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["style_id"] == style.id
    assert env["videos"].get_video(video.id).style_id == style.id  # persistiu

    cleared = client.patch(f"/studio/videos/{video.id}/style", json={"style_id": None}, headers=POST_HEADER)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["style_id"] is None
    assert env["videos"].get_video(video.id).style_id is None  # voltou a herdar


def test_unknown_style_is_422_without_a_stack_trace(env):
    video = env["videos"].create_video(env["project"].id, "ADE 2026", VideoFormat.short)
    r = env["client"].patch(f"/studio/videos/{video.id}/style", json={"style_id": "f" * 32}, headers=POST_HEADER)
    assert r.status_code == 422
    assert "style" in r.json()["detail"].lower()
    assert "Traceback" not in r.text  # nada de stack trace para o operador
    assert env["videos"].get_video(video.id).style_id is None  # nada gravado


def test_unknown_video_is_404(env):
    style = env["styles"].create("Cinemático")
    r = env["client"].patch(f"/studio/videos/{'a' * 32}/style", json={"style_id": style.id}, headers=POST_HEADER)
    assert r.status_code == 404


def test_video_style_requires_authentication(env):
    r = env["client"].patch(f"/studio/videos/{'a' * 32}/style", json={"style_id": None})
    assert r.status_code == 401


# ------------------------------------------------------------- página do vídeo


def test_video_page_shows_inheritance_from_the_channel_style(env):
    style = env["styles"].create("Documentário Cinemático")
    _channel(env, env["project"].id, style_id=style.id)
    video = env["videos"].create_video(env["project"].id, "ADE 2026", VideoFormat.short)

    html = _video_page(env, video.id).text
    visible = _page_text(html)
    assert 'id="video-estilo"' in html
    assert "Herdar do canal (Documentário Cinemático)" in visible
    assert "Este vídeo herda o estilo do canal: Documentário Cinemático." in visible
    assert re.search(r'<option value="" selected>Herdar do canal \(Documentário Cinemático\)</option>', html)
    assert_ux_contract(html, page="video/aparencia")


def test_video_page_shows_the_override_when_set(env):
    channel_style = env["styles"].create("Estilo do Canal")
    own = env["styles"].create("Estilo do Vídeo")
    _channel(env, env["project"].id, style_id=channel_style.id)
    video = env["videos"].create_video(env["project"].id, "ADE 2026", VideoFormat.short)
    env["client"].patch(f"/studio/videos/{video.id}/style", json={"style_id": own.id}, headers=POST_HEADER)

    html = _video_page(env, video.id).text
    visible = _page_text(html)
    assert "Este vídeo sobrepõe o canal com Estilo do Vídeo (o canal herda Estilo do Canal)." in visible
    assert re.search(rf'<option value="{own.id}" selected>Estilo do Vídeo</option>', html)


def test_video_page_says_no_channel_style_when_channel_has_none(env):
    _channel(env, env["project"].id)  # canal sem estilo: não é erro
    video = env["videos"].create_video(env["project"].id, "ADE 2026", VideoFormat.short)

    visible = _page_text(_video_page(env, video.id).text)
    assert "Herdar do canal (nenhum estilo)" in visible
    assert "Este vídeo herda do canal, que não usa estilo" in visible


def test_video_inherits_the_style_of_its_own_channel_not_another(env):
    style_a = env["styles"].create("Estilo A")
    style_b = env["styles"].create("Estilo B")
    other = env["videos"].create_project("Outro", niche="", language="pt-BR")
    _channel(env, env["project"].id, style_id=style_a.id)
    _channel(env, other.id, style_id=style_b.id)

    video = env["videos"].create_video(other.id, "ADE 2026", VideoFormat.short)
    visible = _page_text(_video_page(env, video.id).text)
    # Herda do canal do **próprio** projeto (B), não do primeiro canal da base.
    assert "Herdar do canal (Estilo B)" in visible


# ----------------------------------------------------------------- projeção pura


def test_effective_style_prefers_the_video_override():
    from app.studio.domain.visual_style import effective_style_id

    assert effective_style_id("a" * 32, "b" * 32) == "b" * 32  # o vídeo sobrepõe
    assert effective_style_id("a" * 32, None) == "a" * 32  # herda o canal
    assert effective_style_id(None, None) is None  # padrão do estúdio


class _FakeVideos:
    def __init__(self, video):
        self._video = video

    def get_video(self, video_id):
        return self._video if self._video is not None and self._video.id == video_id else None


class _FakeChannels:
    def __init__(self, profile):
        self._profile = profile

    def get_by_project(self, project_id):
        return self._profile


class _FakeStyles:
    def __init__(self, styles):
        self._styles = list(styles)

    def get(self, style_id):
        return next((s for s in self._styles if s.id == style_id), None)

    def list(self, include_archived=False):
        return [s for s in self._styles if include_archived or not s.archived]


def test_build_video_style_view_names_the_inherited_channel_style():
    from types import SimpleNamespace

    from app.studio.application.video_style import BuildVideoStyleView
    from app.studio.domain.visual_style import VisualStyle

    channel_style = VisualStyle(id="c" * 32, name="Canal")
    other = VisualStyle(id="d" * 32, name="Outra")
    video = SimpleNamespace(id="2" * 32, project_id="1" * 32, style_id=None)
    profile = SimpleNamespace(style_id=channel_style.id)
    view = BuildVideoStyleView(_FakeVideos(video), _FakeChannels(profile),
                               _FakeStyles([channel_style, other])).execute(video.id)

    assert view.inherits_from_channel is True
    assert view.inherited_style_name == "Canal"
    assert view.effective_style_id == channel_style.id
    assert {s.id for s in view.styles} == {channel_style.id, other.id}


def test_build_video_style_view_keeps_an_archived_current_style_representable():
    from types import SimpleNamespace

    from app.studio.application.video_style import BuildVideoStyleView
    from app.studio.domain.visual_style import VisualStyle

    archived = VisualStyle(id="a" * 32, name="Antigo", archived=True)
    active = VisualStyle(id="b" * 32, name="Atual")
    video = SimpleNamespace(id="2" * 32, project_id="1" * 32, style_id=archived.id)
    view = BuildVideoStyleView(_FakeVideos(video), _FakeChannels(None),
                               _FakeStyles([active, archived])).execute(video.id)

    assert view.override_style_id == archived.id
    assert view.inherits_from_channel is False
    # A lista ativa não a traz, mas a opção atual continua representável com o nome real.
    assert any(s.id == archived.id for s in view.styles)
