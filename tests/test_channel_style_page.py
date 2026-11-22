"""Personalizar o estilo do canal (F05.T04): origem, valor efetivo, reset e revisão otimista.

A tela é o **componente** que será montado na página de Canais: ela não edita a biblioteca e não
recalcula nada — a resolução exibida vem de `domain.effective_config.resolve_effective_config`
(mesmo caminho do Core, com `channel_patch`). Aqui testamos a projeção pura, o HTML do componente
(escape, sem `on*=` inline, avançado recolhido) e o caso de uso `SetChannelStylePatch` no Postgres
descartável (grava/reset sem `{}`, revisão velha → conflito tipado sem escrita).
"""
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate  # noqa: E402
from app.studio.adapters.postgres.channel_repo import PostgresChannelProfileRepository  # noqa: E402
from app.studio.adapters.postgres.repo import PostgresVideoRepository  # noqa: E402
from app.studio.adapters.postgres.visual_style_repo import PostgresVisualStyleRepository  # noqa: E402
from app.studio.api.panel_channel_style import (  # noqa: E402
    CHANNEL_STYLE_CSS,
    CHANNEL_STYLE_JS,
    render_channel_style,
)
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.application.channel_style_page import (  # noqa: E402
    BuildChannelStylePage,
)
from app.studio.application.video_style import (  # noqa: E402
    ChannelStylePatchConflict,
    SetChannelStylePatch,
    validate_style_patch_revision,
)
from app.studio.composition import Settings, Studio  # noqa: E402
from app.studio.domain.channel import ChannelProfile  # noqa: E402
from app.studio.domain.visual_style import StylePatchInvalid, VisualStyle  # noqa: E402

PID = "f" * 32
CID = "d" * 32
SID = "a" * 32


# ------------------------------------------------------------------ projeção


class _FakeChannels:
    def __init__(self, profile):
        self._profile = profile

    def get(self, profile_id):
        if self._profile is not None and self._profile.id == profile_id:
            return self._profile
        return None


class _FakeStyles:
    def __init__(self, styles=()):
        self._styles = list(styles)

    def get(self, style_id):
        return next((style for style in self._styles if style.id == style_id), None)

    def list(self, include_archived=False):
        return [style for style in self._styles if include_archived or not style.archived]


def _profile(style_id=None, patch=None, revision=0, name="História"):
    return ChannelProfile(id=CID, project_id=PID, name=name, style_id=style_id,
                          style_patch=patch, style_patch_revision=revision)


def _style(name="Documentário Cinemático", **params):
    return VisualStyle(id=SID, name=name, params=params)


def _view(profile, styles):
    return BuildChannelStylePage(_FakeChannels(profile), _FakeStyles(styles)).execute(profile.id)


def _field(view, path):
    found = next(field for field in view.fields if field.path == path)
    return found


def test_view_shows_origin_effective_and_reset_target_for_each_field():
    """Cada campo traz de onde vem, o valor efetivo e o que o reset devolveria (do Core)."""
    style = _style(motion=["zoom_in"], music={"bpm": 122},
                   caption={"font_size": 58}, palette={"accent": "#FFCC00"})
    view = _view(_profile(style_id=SID, patch={"music": {"bpm": 150}}, revision=3), [style])

    bpm = _field(view, "music.bpm")
    assert bpm.origin == "channel" and bpm.overridden is True
    assert bpm.effective == 150
    # Reset volta a herdar do estilo (122), não ao default do motor.
    assert bpm.inherited_origin == "style" and bpm.inherited == 122

    seed = _field(view, "music.seed")
    assert seed.origin == "engine_default" and seed.overridden is False
    assert seed.effective == 7  # o default explícito do motor, sem inventar zero

    motion = _field(view, "motion")
    assert motion.origin == "style" and motion.effective == ("zoom_in",)
    assert _field(view, "caption.font_size").origin == "style"
    assert _field(view, "caption.font_size").effective == 58
    # Chave não declarada por ninguém: o motor decide (ausência não é zero).
    assert _field(view, "caption.bottom").origin == "engine_default"
    assert _field(view, "caption.bottom").effective is None
    assert _field(view, "voice.model").origin == "engine_default"

    assert view.revision == 3
    assert view.patch_document() == {"music": {"bpm": 150}}
    assert view.has_patch is True


def test_view_marks_transition_and_extra_as_declared_but_not_applied():
    """O que o render não aplica não vira controle: aparece rotulado, com o motivo."""
    style = _style(transition={"kind": "fade", "duration_ticks": 12}, extra={"lut": "warm"})
    view = _view(_profile(style_id=SID, patch={"extra": {"lut": "warm"}}), [style])

    transition = _field(view, "transition.kind")
    assert transition.applied is False
    assert transition.origin == "style" and transition.effective == "fade"
    assert transition.reason

    extra = _field(view, "extra.lut")
    assert extra.applied is False and extra.overridden is True


def test_view_without_style_falls_back_to_engine_defaults():
    view = _view(_profile(), [])
    assert view.style_id is None
    assert _field(view, "motion").origin == "engine_default"
    assert _field(view, "music.bpm").effective == 122
    assert view.has_patch is False


def test_unknown_channel_returns_none():
    assert BuildChannelStylePage(_FakeChannels(None), _FakeStyles()).execute(CID) is None


# ----------------------------------------------------------------------- HTML


def test_html_names_the_inherited_style_for_every_field():
    style = _style(music={"bpm": 122})
    view = _view(_profile(style_id=SID, patch={"music": {"bpm": 150}}, revision=1), [style])
    html = render_channel_style(view)

    visible = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<(style|script)\b.*?</\1>", "", html,
                                                       flags=re.S | re.I)).split())
    assert "herda do estilo Documentário Cinemático" in visible
    assert "canal" in visible          # origem explícita do override
    assert "padrão do motor" in visible
    # Reset só existe no campo de fato personalizado.
    assert 'data-reset-field="music.bpm"' in html
    assert 'data-reset-field="music.seed"' not in html
    # O componente não promete controle do que o render não aplica.
    assert "data-extra" not in html and "<textarea" not in html
    assert "<details open" not in html
    # Nenhum handler inline: o JS acompanha a página e roda sob o nonce/CSP dela.
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)


def test_html_escapes_data_and_has_no_inline_handlers():
    style = _style(name="Nome <script>alert(1)</script>")
    hostile = '"><img src=x onerror=alert(1)>'
    view = _view(_profile(style_id=SID, patch={"voice": {"model": hostile}}), [style])
    html = render_channel_style(view)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x" not in html
    assert "&quot;&gt;&lt;img" in html  # o payload hostil foi escapado dentro do atributo


def test_component_js_keeps_typed_values_on_conflict_and_sends_the_full_patch():
    """409 é mensagem humana e não recarrega nem limpa os campos; ausência vira `null`."""
    assert "409" in CHANNEL_STYLE_JS
    assert "Outra pessoa" in CHANNEL_STYLE_JS
    assert "location.reload" in CHANNEL_STYLE_JS  # só no sucesso explícito
    # Nada de innerHTML/eval com dado de servidor; o feedback usa textContent.
    assert "innerHTML" not in CHANNEL_STYLE_JS
    assert "eval(" not in CHANNEL_STYLE_JS
    assert "textContent" in CHANNEL_STYLE_JS
    assert "patch: hasFields ? collected : null" in CHANNEL_STYLE_JS  # vazio = herdar (NULL)
    conflict = CHANNEL_STYLE_JS.split("result.status === 409", 1)[1].split("return;", 1)[0]
    assert "location.reload" not in conflict  # 409 não recarrega nem apaga a entrada
    assert "digitou" in conflict


def test_component_mounts_in_the_existing_shell_with_csp_and_no_store():
    """O fragmento herda a casca/CSP/no-store da página; nada de handler inline na montagem."""
    import secrets

    from fastapi.responses import Response

    from app.studio.api import panel as shell
    from app.studio.api import shell_v3
    from test_ux_contract import assert_ux_contract

    style = _style(music={"bpm": 122})
    view = _view(_profile(style_id=SID), [style])
    nonce = secrets.token_urlsafe(16)
    body = shell_v3.render_settings_page_body(
        active_section="canais", section_title="Canais",
        content_html=render_channel_style(view))
    document = shell_v3.render_document(
        title="Faceless Studio — Canais", active="canais", crumb="Configurações / Canais",
        body_html=body, nonce=nonce, projects=[], project_id="",
        page_js=CHANNEL_STYLE_JS, extra_css=CHANNEL_STYLE_CSS)
    app = FastAPI()

    @app.get("/montagem")
    def montagem():
        return Response(document, media_type="text/html", headers=shell._headers(nonce))

    response = TestClient(app).get("/montagem")
    assert response.status_code == 200
    assert f"nonce-{nonce}" in response.headers["Content-Security-Policy"]
    assert "no-store" in response.headers["Cache-Control"]
    assert "data-channel-style-form" in response.text
    assert not re.search(r"\son[a-z]+\s*=", response.text, re.I)
    assert_ux_contract(response.text, page="canais/personalizar-estilo")


# ------------------------------------------------------- caso de uso (Postgres)


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    styles = PostgresVisualStyleRepository(connect)
    channels = PostgresChannelProfileRepository(connect)
    project = videos.create_project("Canal H", niche="Geral", language="pt-BR")
    profile = channels.create(project.id, "História")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "channels": channels, "styles": styles,
            "project": project, "profile": profile, "conn": conn}


def _stored(env, profile_id):
    return env["conn"].execute(
        "SELECT style_patch, style_patch_revision, version FROM studio.channel_profiles "
        "WHERE id = %s", (profile_id,)).fetchone()


def test_channel_patch_persists_and_never_writes_an_empty_object(env):
    channels = env["channels"]
    saved = SetChannelStylePatch(channels).execute(env["profile"].id, 0, {"music": {"bpm": 150}})
    assert saved.revision == 1
    assert saved.patch.to_mapping() == {"music": {"bpm": 150}}
    assert _stored(env, env["profile"].id) == ({"music": {"bpm": 150}}, 1, 1)  # version editorial intacta

    reset = SetChannelStylePatch(channels).execute(env["profile"].id, saved.revision, None)
    assert reset.revision == 2 and reset.patch is None
    assert _stored(env, env["profile"].id) == (None, 2, 1)  # NULL = herda, nunca `{}`

    empty = SetChannelStylePatch(channels).execute(env["profile"].id, reset.revision, {})
    assert empty.patch is None
    assert _stored(env, env["profile"].id) == (None, 3, 1)


def test_channel_patch_is_normalized_and_refuses_unknown_fields_without_writing(env):
    channels = env["channels"]
    saved = SetChannelStylePatch(channels).execute(
        env["profile"].id, 0, {"voice": {"model": "  piper:pt_BR-x  "}})
    assert saved.patch.to_mapping() == {"voice": {"model": "piper:pt_BR-x"}}

    with pytest.raises(StylePatchInvalid):
        SetChannelStylePatch(channels).execute(env["profile"].id, saved.revision, {"colour": "#fff"})
    assert _stored(env, env["profile"].id) == ({"voice": {"model": "piper:pt_BR-x"}}, 1, 1)


def test_channel_patch_stale_revision_is_a_typed_conflict_without_writing(env):
    channels = env["channels"]
    first = SetChannelStylePatch(channels).execute(env["profile"].id, 0, {"music": {"bpm": 150}})
    with pytest.raises(ChannelStylePatchConflict):
        SetChannelStylePatch(channels).execute(env["profile"].id, 0, {"music": {"bpm": 90}})
    assert _stored(env, env["profile"].id) == ({"music": {"bpm": 150}}, 1, 1)
    assert channels.get(env["profile"].id).style_patch == first.patch


def test_channel_patch_of_an_unknown_channel_returns_none(env):
    assert SetChannelStylePatch(env["channels"]).execute("a" * 32, 0, {"music": {"bpm": 150}}) is None


def test_invalid_channel_patch_revision_is_refused_before_the_database(env):
    for bad in (-1, True, "1"):
        with pytest.raises(ValueError):
            validate_style_patch_revision(bad)
        with pytest.raises(ValueError):
            SetChannelStylePatch(env["channels"]).execute(env["profile"].id, bad, {"music": {"bpm": 150}})
    assert _stored(env, env["profile"].id) == (None, 0, 1)


def test_built_view_reads_the_persisted_patch_from_postgres(env):
    """A projeção usa o agregado real do banco (nada de SQL na camada de tela)."""
    style = env["styles"].create("Cinema Noturno", params={"music": {"bpm": 122}})
    env["channels"].update(env["profile"].id, 1, {"style_id": style.id})
    SetChannelStylePatch(env["channels"]).execute(env["profile"].id, 0, {"music": {"bpm": 150}})

    view = BuildChannelStylePage(env["channels"], env["styles"]).execute(env["profile"].id)
    assert view.style_name == "Cinema Noturno"
    assert view.revision == 1
    bpm = _field(view, "music.bpm")
    assert (bpm.origin, bpm.effective, bpm.inherited) == ("channel", 150, 122)
    html = render_channel_style(view)
    assert 'data-patch="{&quot;music&quot;: {&quot;bpm&quot;: 150}}"' in html
    assert json.dumps(view.patch_document()) == '{"music": {"bpm": 150}}'