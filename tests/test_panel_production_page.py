"""Rotas HTML das telas de produção (F2-02..F2-05) contra o Studio real (Postgres descartável).

O wizard e a página de execução só renderizam dado real (ou estado vazio explícito); as ações
são condicionadas ao estado e o contrato de UX canônico é aplicado a cada página.
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
from app.studio.domain.contracts import VideoFormat  # noqa: E402

from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Produção", niche="Finanças", language="pt-BR")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path))
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    client = TestClient(app)
    return {"client": client, "videos": videos, "project_id": project.id, "conn": conn, "studio": studio}


def _start_run(env, key="run-key-1"):
    videos = env["videos"]
    video = videos.create_video(env["project_id"], "Tema real do operador", VideoFormat.short)
    uc = env["studio"].use_cases()
    creation = uc.production.coordinator.start(video.id, key)
    return video, creation.run


# -- wizard Novo vídeo (F2-02/F2-03) -----------------------------------------


def test_wizard_page_requires_auth_and_host_guard(env):
    client = env["client"]
    assert client.get("/studio/panel/novo-video").status_code == 401
    assert client.get("/studio/panel/novo-video",
                      headers={**AUTH_HEADER, "Host": "evil.com"}).status_code == 403


def test_wizard_page_renders_real_channel_and_honest_fields(env):
    client = env["client"]
    r = client.get("/studio/panel/novo-video", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/novo-video")

    assert "Canal Produção" in r.text
    assert 'id="wiz-tema"' in r.text and 'id="btn-produzir-video"' in r.text
    for control in ("wiz-publico", "wiz-duracao", "wiz-estilo", "wiz-idioma", "wiz-teto"):
        match = re.search(rf'<[^>]*id="{control}"[^>]*>', r.text)
        assert match is not None and "disabled" in match.group(0), control
        assert "Motivo:" in r.text


def test_wizard_page_marks_research_and_publish_unavailable_with_reason(env):
    client = env["client"]
    r = client.get("/studio/panel/novo-video", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "indisponível" in r.text
    assert "research automático não existe" in r.text
    assert "F8" in r.text


def test_wizard_page_marks_its_nav_as_the_production_screen(env):
    client = env["client"]
    r = client.get("/studio/panel/novo-video", headers=AUTH_HEADER)
    nav = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', r.text, re.S).group(1)
    assert nav.count('aria-current="page"') == 1
    active = re.search(r'<a class="nav-item active"[^>]*>(.*?)</a>', nav, re.S).group(1)
    assert "Produção" in active


def test_wizard_page_never_leaks_illustrative_mockup_text(env):
    client = env["client"]
    r = client.get("/studio/panel/novo-video", headers=AUTH_HEADER)
    for leaked in ("Como a OpenAI ganha dinheiro?", "1,2 mi views", "run_7f31",
                   "Finanças Descomplicadas", "US$ 0,42", "US$ 1,50"):
        assert leaked not in r.text


# -- página de execução (F2-04/F2-05) ----------------------------------------


def test_execution_page_requires_auth(env):
    client = env["client"]
    video, run = _start_run(env)
    assert client.get(
        f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}").status_code == 401


def test_execution_page_renders_real_run_with_stepper_and_contract(env):
    client = env["client"]
    video, run = _start_run(env)
    r = client.get(f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/execução")

    assert "Tema real do operador" in r.text
    assert "Etapa <b>1 de 7</b>" in r.text
    assert "Não há barra de progresso nem percentual" in r.text
    for label in ("Roteiro", "Fact-check", "Cenas", "Render", "QA", "Aprovação"):
        assert label in r.text


def test_execution_page_keeps_the_run_id_only_in_the_closed_advanced_section(env):
    client = env["client"]
    video, run = _start_run(env)
    r = client.get(f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    main_area, advanced = r.text.split('id="advanced-diagnostics"', 1)
    assert run.run_id not in main_area
    assert run.run_id in advanced
    assert "<details open" not in r.text


def test_execution_page_only_offers_actions_valid_for_the_state(env):
    client = env["client"]
    video, run = _start_run(env)
    r = client.get(f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    # Run em CREATED: só cancelar é válido.
    assert "Cancelar" in r.text
    assert "Pausar" not in r.text
    assert "Tentar novamente" not in r.text
    assert "Continuar" not in r.text
    # Sem artefato aprovado, "Revisar" não aparece no rail de ações.
    actions_rail = r.text.split('id="h-acoes"', 1)[1]
    assert ">Revisar</a>" not in actions_rail


def test_execution_page_404_for_unknown_run_and_422_for_bad_id(env):
    client = env["client"]
    video, run = _start_run(env)
    assert client.get(
        f"/studio/panel/videos/{video.id}/production-runs/{'a' * 32}", headers=AUTH_HEADER).status_code == 404
    assert client.get(
        f"/studio/panel/videos/bad-id/production-runs/{run.run_id}", headers=AUTH_HEADER).status_code == 422


def test_execution_page_404_for_a_run_of_another_video(env):
    client = env["client"]
    _, run = _start_run(env)
    other = env["videos"].create_video(env["project_id"], "Outro tema real", VideoFormat.short)
    r = client.get(f"/studio/panel/videos/{other.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    assert r.status_code == 404


def test_execution_page_lists_unavailable_stages_with_reason(env):
    client = env["client"]
    video, run = _start_run(env)
    r = client.get(f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    assert "Indisponível nesta versão" in r.text
    assert "Fontes" in r.text and "Publicação" in r.text
