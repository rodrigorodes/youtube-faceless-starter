"""RF-01 — vocabulário: no produto a unidade é o **canal**, nunca "projeto".

O reframe é de **linguagem da interface**, não de arquitetura: `project_id`, as rotas
`/studio/projects/...`, o schema `studio.projects` e os contratos JSON continuam iguais. O que
esta fatia trava é só o que o usuário **lê**: nenhuma página do painel pode mostrar
"Projeto"/"projeto" como texto visível.

Páginas cobertas por este arquivo (todas renderizadas de verdade contra o Studio, com Postgres
descartável):

- `/studio/panel`            — o painel principal (título, rótulo do seletor, modal de canal).
- `/studio/panel/novo-video` — o wizard de produção (aviso de "nenhum canal cadastrado").
- `/studio/canais` (com canal) — a tela de canal (seção avançada e configuração pública).
- `/studio/canais` (vazio)   — o estado vazio que ensina a criar o primeiro canal.
- `/studio/panel/conexoes`   — a tela de Conexões.
- `/studio/panel/estilos`    — a biblioteca de Estilos.
- `/studio/panel/analytics`  — a tela de Analytics (bloco avançado com o id do canal).
- `/studio/oauth/callback`   — o retorno do consentimento (sem `state` reconhecido).

Se uma tela nova aparecer e não estiver aqui, acrescente-a a `_PAGES`; o teste é o contrato.
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
from app.studio.api.routes import make_router  # noqa: E402
from app.studio.composition import Settings, Studio  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}

# O vocabulário proibido como TEXTO VISÍVEL. Os identificadores de código (`project_id`,
# `/projects/...`, `studio.projects`) não entram: o teste olha o texto renderizado, não o código.
FORBIDDEN_VOCABULARY = ("projeto", "projetos")


def _visible_text(html: str) -> str:
    """Texto que o usuário lê: tags fora e o conteúdo de `<script>`/`<style>` fora também.

    O feedback em JS (ex.: "Cadastrando canal...") é texto visível quando executa, mas o
    marcador bruto em `<script>` não é página renderizada — por isso ele não conta aqui.
    """
    without_code = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", without_code).split())


def _assert_no_project_vocabulary(html: str, page: str) -> None:
    visible = _visible_text(html).lower()
    offenders = [word for word in FORBIDDEN_VOCABULARY if word in visible]
    assert not offenders, f"{page}: vocabulário de 'projeto' visível ao usuário: {offenders}"


def _app(conn, dsn, tmp_path, *, with_project: bool = True):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Vocabulário", niche="História", language="pt-BR") if with_project else None
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "project": project, "videos": videos, "conn": conn}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path)


@pytest.fixture()
def env_empty(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path, with_project=False)


def _get(env, path, *, expect=200):
    r = env["client"].get(path, headers=AUTH_HEADER)
    assert r.status_code == expect, f"{path}: {r.status_code} — {r.text[:300]}"
    return r.text


def test_panel_main_page_has_no_project_vocabulary(env):
    pid = env["project"].id
    _assert_no_project_vocabulary(_get(env, f"/studio/panel?project_id={pid}"), "/studio/panel")


def test_production_wizard_has_no_project_vocabulary(env):
    pid = env["project"].id
    _assert_no_project_vocabulary(
        _get(env, f"/studio/panel/novo-video?project_id={pid}"), "/studio/panel/novo-video")


def test_channels_page_has_no_project_vocabulary(env):
    pid = env["project"].id
    _assert_no_project_vocabulary(_get(env, f"/studio/canais?project_id={pid}"), "/studio/canais (com canal)")


def test_channels_empty_state_has_no_project_vocabulary(env_empty):
    _assert_no_project_vocabulary(_get(env_empty, "/studio/canais"), "/studio/canais (vazio)")


def test_connections_page_has_no_project_vocabulary(env):
    _assert_no_project_vocabulary(_get(env, "/studio/panel/conexoes"), "/studio/panel/conexoes")


def test_styles_page_has_no_project_vocabulary(env):
    _assert_no_project_vocabulary(_get(env, "/studio/panel/estilos"), "/studio/panel/estilos")


def test_analytics_page_has_no_project_vocabulary(env):
    _assert_no_project_vocabulary(_get(env, "/studio/panel/analytics"), "/studio/panel/analytics")


def test_oauth_callback_has_no_project_vocabulary(env):
    _assert_no_project_vocabulary(_get(env, "/studio/oauth/callback"), "/studio/oauth/callback")
