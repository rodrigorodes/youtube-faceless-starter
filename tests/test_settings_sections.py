"""W1.5 (SET): as quatro seções de Configurações e o item Biblioteca do menu.

Regra do protótipo (`prototype-v4-v3/index.html:638`) e do plano: as quatro seções precisam ser
navegáveis e cada uma mostrar **conteúdo real** — nada de página vazia que "parece funcional".
As seções novas (`estrategia`, `marca`, `producao`) têm página própria, mas reusam os cartões,
o formulário, o endpoint de escrita e o JavaScript da tela de Canais (um conceito, um dono).
"""
import base64
import html
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

# Rótulos do menu principal e das seções, na ordem do protótipo.
NAV_LABELS = ["Início", "Criar vídeo", "Vídeos", "Tendências e ideias", "Desempenho",
              "Biblioteca", "Configurações"]
SETTINGS_LABELS = ["Canais", "Marca & Editorial", "Produção & Orçamento",
                   "Conexões & Equipe"]


@pytest.fixture()
def env(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="História", language="pt-BR")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "project": project, "dsn": dsn}


@pytest.fixture()
def profile(env):
    """Perfil de canal real: sem ele, as seções mostram o estado vazio explícito."""
    response = env["client"].post(f"/studio/projects/{env['project'].id}/channels",
                                  headers={**AUTH_HEADER, "Origin": "http://testserver"},
                                  json={"name": "Canal H", "strategy": "Explicar com fontes",
                                        "audience": "Curiosos", "pillars": ["História"],
                                        "narrative": "Didática", "target_duration_s": 60,
                                        "cta": "Qual tema você quer ver?"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _page(env, path):
    response = env["client"].get(path, headers=AUTH_HEADER)
    assert response.status_code == 200, (path, response.status_code)
    return response.text


def _nav_text(item):
    # Os glifos do protótipo são `aria-hidden`: não fazem parte do rótulo acessível.
    return html.unescape(re.sub(r"<span aria-hidden.*?</span>|<[^>]+>", "", item).strip())


def _nav_items(html, label):
    nav = re.search(rf'<nav aria-label="{label}">(.*?)</nav>', html, re.S).group(1)
    return re.findall(r"<li>.*?</li>", nav, re.S)


def test_the_global_menu_lists_the_prototype_items_and_the_library(env, profile):
    """Menu do protótipo, incluindo **Biblioteca**, apontando para a biblioteca de estilos real."""
    html = _page(env, "/studio/panel")
    items = _nav_items(html, "Principal")
    assert [_nav_text(item) for item in items] == NAV_LABELS
    biblioteca = [item for item in items if "Biblioteca" in item][0]
    assert 'href="/studio/panel/estilos' in biblioteca
    # NAV: Configurações é o 7º item do menu principal (`prototype/index.html:583`).
    configuracoes = [item for item in items if "Configurações" in item][0]
    assert 'href="/studio/configuracoes/canais' in configuracoes


def test_the_library_page_marks_biblioteca_as_the_active_item(env, profile):
    html = _page(env, "/studio/panel/estilos")
    items = _nav_items(html, "Principal")
    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Biblioteca" in _nav_text(active[0])


def test_the_settings_menu_has_the_seven_prototype_sections_with_the_active_channel(env, profile):
    html = _page(env, "/studio/configuracoes/canais")
    labels = [_nav_text(item) for item in _nav_items(html, "Seções de configuração")]
    assert labels == SETTINGS_LABELS
    for item in _nav_items(html, "Seções de configuração"):
        assert f"project_id={env['project'].id}" in item, item


def test_every_settings_section_reaches_real_content(env, profile):
    """Cada seção do menu de Configurações mostra conteúdo real (nada de cartão vazio ou 404)."""
    expected = {
        "/studio/configuracoes/canais": ["Canal ativo", 'id="painel-perfil"'],
        "/studio/configuracoes/estrategia": ['id="painel-perfil"', 'id="channel-form"'],
        "/studio/configuracoes/marca": ['id="channel-form"', 'id="personalizar-estilo-canal"'],
        "/studio/configuracoes/producao": ['id="painel-orcamento"', 'id="painel-providers"'],
        "/studio/configuracoes/conexoes": ["configurações", "Conex"],
        "/studio/configuracoes/equipe": ["Equipe"],
        "/studio/configuracoes/avancado": ["Diagnóstico"],
    }
    for path, markers in expected.items():
        html = _page(env, path)
        for marker in markers:
            assert marker in html, (path, marker)


def test_the_section_pages_reuse_the_channels_page_javascript(env, profile):
    """Os formulários reusados funcionam: a página traz o mesmo JavaScript da tela de Canais.

    O JS compartilhado é o da tela de Canais (inclui o handler de troca de canal, que só age se o
    elemento existir); o que a seção **não** faz é renderizar o bloco de troca de canal.
    """
    html = _page(env, "/studio/configuracoes/estrategia")
    assert "splitPillars" in html                 # handler do formulário do perfil
    assert 'id="canal-ativo-card"' not in html    # sem o bloco de troca de canal nesta seção
    assert 'id="canal-switcher"' not in html


def test_legacy_settings_addresses_still_work(env, profile):
    """Endereço antigo (`estilos`, `identidade`) não pode virar 404 nem perder o canal ativo."""
    client, project_id = env["client"], env["project"].id
    for section, target in (("estilos", "/studio/panel/estilos"), ("identidade", "/studio/configuracoes/marca")):
        response = client.get(f"/studio/configuracoes/{section}?project_id={project_id}",
                              headers=AUTH_HEADER, follow_redirects=False)
        assert response.status_code == 302, section
        assert response.headers["location"] == f"{target}?project_id={project_id}"

    unknown = client.get("/studio/configuracoes/nao-existe", headers=AUTH_HEADER, follow_redirects=False)
    assert unknown.status_code == 404
