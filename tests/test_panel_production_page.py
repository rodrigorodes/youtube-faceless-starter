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

from test_panel import _visible_text  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal Produção", niche="Finanças", language="pt-BR")
    # A pesquisa automática é o padrão de produção (settings.auto_research=True), mas estas telas
    # descrevem a pipeline clássica de 8 etapas e o estado "estágio indisponível" (Fontes).
    # Sem a pesquisa, o DAG volta a COORDINATOR_DAG e a etapa de pesquisa fica explicitamente
    # indisponível — que é o que as asserções de stepper e de etapas indisponíveis exercitam.
    # A pipeline com pesquisa continua coberta em tests/test_pesquisa_automatica.py.
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path, auto_research=False))
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

    # UX V3: o canal real aparece na topbar e na predefinição; o formulário é o do conceito.
    assert "Canal Produção" in r.text
    assert "Predefinição do canal" in r.text
    assert 'id="tema-novo"' in r.text and 'id="btn-criar-abrir"' in r.text
    assert 'name="estilo-novo"' in r.text and 'name="formato-novo"' in r.text
    # O que o canal não define é dito como ausência, não inventado.
    assert "Canal sem perfil" in r.text and "nenhum idioma definido" in r.text
    # O único controle desabilitado é o "Estrutura do roteiro", que declara vir do perfil
    # editorial; tema e criação continuam habilitados.
    assert "Definida pelo perfil editorial do canal" in r.text


def test_wizard_page_marks_its_nav_as_the_production_screen(env):
    client = env["client"]
    r = client.get("/studio/panel/novo-video", headers=AUTH_HEADER)
    markup = re.sub(r"<(style|script)\b.*?</\1>", "", r.text, flags=re.S)
    nav = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S).group(1)
    assert nav.count('aria-current="page"') == 1
    active = re.search(r'<a href="/studio/panel/novo-video[^"]*" aria-current="page">(.*?)</a>',
                       nav, re.S).group(1)
    assert "Criar vídeo" in active


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
    assert "Etapa <b>1 de 8</b>" in r.text
    assert "⚡ Produção em andamento" in r.text and re.search(r"\d/8 etapas", r.text)
    assert "grade-video" not in r.text and "cab-video" not in r.text
    for label in ("Roteiro", "Fact-check", "Cenas", "Render", "QA", "Aprovação", "Publicação"):
        assert label in r.text


def test_execution_page_keeps_the_run_id_only_in_the_closed_advanced_section(env):
    client = env["client"]
    video, run = _start_run(env)
    r = client.get(f"/studio/panel/videos/{video.id}/production-runs/{run.run_id}", headers=AUTH_HEADER)
    main_area, advanced = r.text.split('id="advanced-diagnostics"', 1)
    assert run.run_id not in _visible_text(main_area)
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


# -- página de produção (FS31-A3: sai da casca V2) ---------------------------


def test_production_page_uses_the_v3_shell_and_real_data(env):
    client = env["client"]
    env["videos"].create_video(env["project_id"], "Tema de produção real", VideoFormat.short)
    r = client.get("/studio/panel/producao", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert_ux_contract(r.text, page="painel/produção")
    assert 'id="pagina-producao"' in r.text
    assert "Tema de produção real" in r.text
    assert "Não iniciado" in r.text and "sem registro de uso" in r.text

    # a casca antiga não pode voltar: sem sidebar V2, sem links de API/n8n
    assert "Faceless Studio V2" not in r.text
    assert 'class="sidebar"' not in r.text
    assert "API Docs" not in r.text and "n8n" not in r.text

    markup = re.sub(r"<(style|script)\b.*?</\1>", "", r.text, flags=re.S)
    nav = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S).group(1)
    assert nav.count('aria-current="page"') == 1
    assert "Vídeos" in re.search(r'<a[^>]*aria-current="page">(.*?)</a>', nav, re.S).group(1)


def test_production_page_empty_state_is_explicit(env):
    r = env["client"].get("/studio/panel/producao", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "Nenhum vídeo" in r.text
    assert_ux_contract(r.text, page="painel/produção/vazio")

