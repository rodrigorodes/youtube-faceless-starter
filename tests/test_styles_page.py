"""Tela de Estilos (VS-05a) no painel: lista + criar + editar + arquivar, só com dado real.

O contrato de UX (`test_ux_contract.assert_ux_contract`) é aplicado à tela inteira. O estado vazio
ensina o próximo passo; a contagem de canais é medida; nada de preview falso nem percentual.
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
from test_ux_contract import assert_ux_contract  # noqa: E402

AUTH_HEADER = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-browser-password").decode()}
WORKER_HEADER = {"Authorization": "Bearer test-worker-token"}


def _app(conn, dsn, tmp_path):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    videos = PostgresVideoRepository(connect)
    project = videos.create_project("Canal H", niche="História", language="pt-BR")
    studio = Studio(Settings(database_url=dsn, storage_root=tmp_path), environ={"STUDIO_TEXT": "demo"})
    app = FastAPI()
    app.include_router(make_router(studio.use_cases, studio.ping))
    return {"client": TestClient(app), "videos": videos, "project": project, "conn": conn}


@pytest.fixture()
def env(conn, dsn, tmp_path):
    return _app(conn, dsn, tmp_path)


def page(env):
    return env["client"].get("/studio/panel/estilos", headers=AUTH_HEADER)


def page_text(html: str) -> str:
    stripped = re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", stripped).split())


def _without_style_and_script(html: str) -> str:
    return re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S | re.I)


def nav_items(html: str):
    """Itens da navegação principal da casca V3 (`<nav aria-label="Principal">`)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Principal">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação principal ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def settings_nav_items(html: str):
    """Itens da navegação da área de Configurações (Canais/Estilos/Conexões/Equipe)."""
    markup = _without_style_and_script(html)
    match = re.search(r'<nav aria-label="Seções de configuração">(.*?)</nav>', markup, re.S)
    assert match is not None, "navegação de configurações ausente"
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def _nav_text(item: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", item).split())


def _create_style(env, name, params=None):
    r = env["client"].post("/studio/styles", json={"name": name, "params": params or {}}, headers=WORKER_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ contrato


def test_styles_empty_state_teaches_the_next_step(env):
    r = page(env)
    assert r.status_code == 200, r.text
    visible = page_text(r.text)
    assert "Nenhum estilo ainda" in visible
    assert "Criar o primeiro estilo" in visible
    assert_ux_contract(r.text, page="estilos/vazio")


def test_styles_page_with_real_data_satisfies_the_ux_contract(env):
    style = _create_style(env, "Documentário Cinemático",
                          {"motion": ["zoom_in"], "music": {"bpm": 122}, "caption": {"font_size": 58}})
    created = env["client"].post(f"/studio/projects/{env['project'].id}/channels",
                                 json={"name": "História", "style_id": style["id"]}, headers=WORKER_HEADER)
    assert created.status_code == 201, created.text
    r = page(env)
    assert r.status_code == 200, r.text
    assert_ux_contract(r.text, page="estilos/com-dados")


# -------------------------------------------------------------------- lista


def test_styles_page_lists_name_summary_and_measured_usage(env):
    style = _create_style(env, "Documentário Cinemático",
                          {"motion": ["zoom_in"], "music": {"bpm": 122}, "caption": {"font_size": 58}})
    env["client"].post(f"/studio/projects/{env['project'].id}/channels",
                       json={"name": "História", "style_id": style["id"]}, headers=WORKER_HEADER)
    visible = page_text(page(env).text)
    assert "Documentário Cinemático" in visible
    assert "zoom_in" in visible and "122 bpm" in visible and "legenda 58px" in visible
    assert "1 canal usa" in visible  # contagem medida, não estimada
    # arquivável pela tela (o controle existe), sem apagar
    assert "Arquivar" in page(env).text


def test_styles_page_empty_library_says_no_canal_uses_any(env):
    assert "Nenhum canal usa" not in page_text(page(env).text)  # sem estilo, não há linha de uso


def test_styles_page_never_invents_preview_or_percentage(env):
    _create_style(env, "Cinemático", {"motion": ["zoom_in"]})
    html = page(env).text
    visible = page_text(html)
    assert "preview" not in visible.lower()
    assert "%" not in visible
    assert "role=\"progressbar\"" not in html


def test_styles_page_escapes_xss_from_real_data(env):
    _create_style(env, "Nome <script>alert(1)</script>")
    html = page(env).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ------------------------------------------------------------------- menu


def test_styles_page_menu_has_estilos_active_and_no_dead_configuracoes(env):
    html = page(env).text
    items = nav_items(html)
    # UX V3: o menu principal tem cinco destinos e nenhum é falso-ativo nesta tela.
    assert [_nav_text(i) for i in items] == ["Início", "Novo vídeo", "Vídeos", "Tendências", "Desempenho"]
    assert not [item for item in items if 'aria-current="page"' in item]
    # A entrada ativa é Configurações, no rodapé da casca.
    config_nav = re.search(r'<nav aria-label="Configuração">(.*?)</nav>', html, re.S).group(1)
    assert re.search(r'<a href="/studio/configuracoes/canais[^"]*" aria-current="page"', config_nav)
    # A tela Estilos é o item ativo da navegação de configurações.
    sections = settings_nav_items(html)
    section_active = [item for item in sections if 'aria-current="page"' in item]
    assert len(section_active) == 1 and "Estilos" in _nav_text(section_active[0])
    assert 'href="/studio/panel/estilos"' in section_active[0]
    assert _without_style_and_script(html).count('aria-current="page"') == 2
    assert "em breve" not in html
    # nenhum item indisponível na casca: "Configurações — em breve" virou área real
    assert not any('aria-disabled="true"' in item for item in items + sections)
    # a seção "Indisponível nesta versão" não existe vazia
    assert "Indisponível nesta versão" not in html


# ------------------------------------------------------------- acessibilidade


def test_styles_form_has_labels_hints_and_collapsed_advanced(env):
    html = page(env).text
    for field_id in ("novo-estilo-nome", "novo-estilo-bpm", "novo-estilo-caption-size",
                     "novo-estilo-voice"):
        assert f'for="{field_id}"' in html, field_id
    assert 'aria-describedby="novo-estilo-nome-hint"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    # "Avançado" recolhido por padrão (divulgação progressiva em 2 níveis)
    assert "<details open" not in html
    assert 'class="advanced"' in html


def test_styles_form_does_not_edit_params_the_render_ignores(env):
    """`extra` era um JSON livre que o render não lê: sai da edição e não vira promessa.

    O valor declarado continua preservado no formulário (`data-params`), mas não há controle
    editável — a API continua aceitando o bag para extensão, a tela não finge suporte.
    """
    _create_style(env, "Com extra", {"extra": {"lut": "warm"}})
    html = page(env).text
    assert "data-extra" not in html and "novo-estilo-extra" not in html
    # Preservado no round-trip do formulário, sem campo dedicado.
    assert 'data-params="{&quot;extra&quot;: {&quot;lut&quot;: &quot;warm&quot;}}"' in html


def test_styles_page_flags_declared_but_unapplied_params(env):
    """Transição/extra são carregados pelo contrato, mas o render ainda não os aplica."""
    _create_style(env, "Com transição",
                  {"transition": {"kind": "fade", "duration_ticks": 12}, "extra": {"lut": "warm"}})
    visible = page_text(page(env).text)
    assert "não aplicado pelo render" in visible
    assert "transição" in visible and "extra" in visible
    # O resumo do que o render aplica não lista o que ele não aplica.
    row = visible.split("Com transição", 1)[1]
    summary = row.split("versão", 1)[0]
    assert "transição" not in summary and "extra" not in summary


# ------------------------------------------------------------------ higiene


def test_styles_page_preserves_csp_and_no_store(env):
    r = page(env)
    assert r.status_code == 200
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_styles_page_requires_authentication(env):
    assert env["client"].get("/studio/panel/estilos").status_code == 401
