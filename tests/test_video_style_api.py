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
from app.studio.application.video_style import SetVideoStylePatch, VideoStylePatchConflict  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.contracts import VideoFormat  # noqa: E402
from app.studio.domain.visual_style import StylePatchInvalid  # noqa: E402
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


# ------------------------------------------- criação com estilo (F02.T02/G15)


def test_create_video_persists_the_chosen_style(env):
    """O estilo escolhido no Create é validado e gravado na mesma criação."""
    style = env["styles"].create("Cinema Noturno")
    r = env["client"].post("/studio/videos", headers=POST_HEADER,
                           json={"project_id": env["project"].id, "topic": "Agentes autônomos",
                                 "format": "short", "style_id": style.id})
    assert r.status_code == 201, r.text
    assert r.json()["style_id"] == style.id
    assert env["videos"].get_video(r.json()["id"]).style_id == style.id  # persistiu de verdade


def test_create_video_without_style_keeps_inheriting_the_channel(env):
    r = env["client"].post("/studio/videos", headers=POST_HEADER,
                           json={"project_id": env["project"].id, "topic": "Agentes autônomos",
                                 "format": "short"})
    assert r.status_code == 201, r.text
    assert r.json()["style_id"] is None


def _video_count(env) -> int:
    return env["conn"].execute("SELECT count(*) FROM studio.videos WHERE project_id = %s",
                               (env["project"].id,)).fetchone()[0]


def test_create_video_with_unknown_style_is_404_and_creates_nothing(env):
    before = _video_count(env)
    r = env["client"].post("/studio/videos", headers=POST_HEADER,
                           json={"project_id": env["project"].id, "topic": "Agentes autônomos",
                                 "format": "short", "style_id": "f" * 32})
    assert r.status_code == 404, r.text
    assert "Traceback" not in r.text
    assert _video_count(env) == before  # nada criado pela metade


def test_create_video_with_archived_style_is_refused(env):
    style = env["styles"].create("Estilo antigo")
    env["styles"].archive(style.id)
    r = env["client"].post("/studio/videos", headers=POST_HEADER,
                           json={"project_id": env["project"].id, "topic": "Agentes autônomos",
                                 "format": "short", "style_id": style.id})
    assert r.status_code == 422, r.text
    assert "archived" in r.json()["detail"]


def test_new_video_page_shows_the_real_styles_of_the_selected_channel(env):
    style = env["styles"].create("Cinema Noturno")
    env["styles"].create("Clean Tech")
    _channel(env, env["project"].id, style_id=style.id)
    html = env["client"].get(f"/studio/panel/novo-video?project_id={env['project'].id}",
                             headers=AUTH_HEADER).text
    bloco = [m for m in re.findall(r'<fieldset class="pills"[^>]*>.*?</fieldset>', html, re.S)
             if 'name="estilo-novo"' in m][0]
    assert "Cinema Noturno" in bloco and "Clean Tech" in bloco
    assert "Herdar do canal — Cinema Noturno" in bloco
    assert 'value="" checked' in bloco
    for ficticio in ("Cinemático", "Documentário", "Tech Clean"):
        assert ficticio not in html
    assert_ux_contract(html, page="painel/novo-video")


# ------------------------------------ canal ativo validado no Core (F02.T01)


def test_unknown_active_channel_is_404_instead_of_silently_switching(env):
    r = env["client"].get(f"/studio/panel?project_id={'f' * 32}", headers=AUTH_HEADER)
    assert r.status_code == 404, r.text
    assert "project not found" in r.text


def test_malformed_active_channel_is_422(env):
    r = env["client"].get("/studio/panel?project_id=nao-e-id", headers=AUTH_HEADER)
    assert r.status_code == 422, r.text


def test_existing_active_channel_renders_the_channel_context(env):
    r = env["client"].get(f"/studio/panel?project_id={env['project'].id}", headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    assert f'value="{env["project"].id}" selected' in r.text
    assert f'/studio/panel/videos?project_id={env["project"].id}' in r.text


# --------------------------------- Área Avançado das Configurações (F02.T03)


def test_advanced_page_shows_the_real_effective_configuration(env):
    r = env["client"].get(f"/studio/panel/avancado?project_id={env['project'].id}", headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    assert "Diagnóstico do Estúdio" in r.text
    assert "Banco de dados: respondendo." in r.text
    assert "Configuração efetiva do canal" in r.text
    assert "Providers disponíveis" in r.text
    assert "demo" in r.text  # spec real deste ambiente de teste, não um placeholder inventado


def test_advanced_page_validates_the_active_channel(env):
    r = env["client"].get(f"/studio/panel/avancado?project_id={'f' * 32}", headers=AUTH_HEADER)
    assert r.status_code == 404, r.text


def test_advanced_page_requires_authentication(env):
    r = env["client"].get("/studio/panel/avancado")
    assert r.status_code == 401


def test_settings_area_links_to_the_seven_groups(env):
    # W1.5: sete seções. As de tela canônica redirecionam (302); `estrategia`, `marca` e `producao`
    # ganharam página própria (200), renderizada pela aplicação.
    for section in ("canais", "estilos", "conexoes", "equipe", "avancado"):
        r = env["client"].get(f"/studio/configuracoes/{section}", headers=AUTH_HEADER, follow_redirects=False)
        assert r.status_code == 302, section
    for section in ("estrategia", "marca", "producao"):
        r = env["client"].get(f"/studio/configuracoes/{section}", headers=AUTH_HEADER, follow_redirects=False)
        assert r.status_code == 200, section


def test_new_video_preset_reads_the_channel_language_and_voice(env):
    _channel(env, env["project"].id, language="en-US", voice="piper:voz-do-canal")
    html = env["client"].get(f"/studio/panel/novo-video?project_id={env['project'].id}",
                             headers=AUTH_HEADER).text
    aside = re.search(r'<aside class="painel" aria-labelledby="t-preset">(.*?)</aside>', html, re.S).group(1)
    assert "Inglês (EUA)" in aside
    assert "piper:voz-do-canal" in aside
    assert "Português (BR)" not in aside


# ------------------------------------ patch de estilo persistido no vídeo (F05.T02)


def test_video_style_patch_persists_and_reset_returns_to_inheriting(env):
    """O patch do vídeo sobrepõe o canal; reset remove o patch (NULL), não grava `{}`."""
    videos = env["videos"]
    video = videos.create_video(env["project"].id, "ADE 2026", VideoFormat.short)

    saved = SetVideoStylePatch(videos).execute(video.id, 0, {"music": {"bpm": 150}})
    assert saved.revision == 1
    assert saved.patch.to_mapping() == {"music": {"bpm": 150}}
    assert videos.get_video_style_patch(video.id) == saved

    reset = SetVideoStylePatch(videos).execute(video.id, saved.revision, None)
    assert reset.revision == 2 and reset.patch is None
    stored = env["conn"].execute(
        "SELECT style_patch, style_patch_revision FROM studio.videos WHERE id = %s", (video.id,)).fetchone()
    assert stored == (None, 2)  # o patch saiu da linha: o vídeo volta a herdar


def test_video_style_patch_is_normalized_before_persisting_and_refuses_unknown_fields(env):
    """A allowlist vale no banco: normaliza pelo `StylePatch` e nada é gravado no erro."""
    videos = env["videos"]
    video = videos.create_video(env["project"].id, "ADE 2026", VideoFormat.short)

    saved = SetVideoStylePatch(videos).execute(video.id, 0, {"voice": {"model": "  piper:pt_BR-x  "}})
    assert saved.patch.to_mapping() == {"voice": {"model": "piper:pt_BR-x"}}
    assert env["conn"].execute(
        "SELECT style_patch FROM studio.videos WHERE id = %s", (video.id,)).fetchone()[0] == {
            "voice": {"model": "piper:pt_BR-x"}}

    with pytest.raises(StylePatchInvalid):
        SetVideoStylePatch(videos).execute(video.id, saved.revision, {"colour": "#fff"})
    assert videos.get_video_style_patch(video.id) == saved


def test_video_style_patch_stale_revision_is_a_typed_conflict_without_writing(env):
    videos = env["videos"]
    video = videos.create_video(env["project"].id, "ADE 2026", VideoFormat.short)
    first = SetVideoStylePatch(videos).execute(video.id, 0, {"music": {"bpm": 150}})

    with pytest.raises(VideoStylePatchConflict):
        SetVideoStylePatch(videos).execute(video.id, 0, {"music": {"bpm": 90}})
    assert videos.get_video_style_patch(video.id) == first


def test_video_style_patch_of_an_unknown_video_returns_none(env):
    assert SetVideoStylePatch(env["videos"]).execute("a" * 32, 0, {"music": {"bpm": 150}}) is None


def test_an_invalid_patch_revision_is_refused_before_touching_the_database(env):
    videos = env["videos"]
    video = videos.create_video(env["project"].id, "ADE 2026", VideoFormat.short)
    for bad in (-1, True, "1"):
        with pytest.raises(ValueError):
            SetVideoStylePatch(videos).execute(video.id, bad, {"music": {"bpm": 150}})
    assert videos.get_video_style_patch(video.id).revision == 0
