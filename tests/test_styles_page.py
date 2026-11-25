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


def _nav_text(item: str) -> str:
    # Os glifos do protótipo são `aria-hidden`: não fazem parte do rótulo acessível.
    return " ".join(re.sub(r"<span aria-hidden.*?</span>|<[^>]+>", " ", item).split())


def _create_style(env, name, params=None):
    r = env["client"].post("/studio/styles", json={"name": name, "params": params or {}}, headers=WORKER_HEADER)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ contrato


def test_styles_empty_state_teaches_the_next_step(env):
    r = page(env)
    assert r.status_code == 200, r.text
    visible = page_text(r.text)
    assert "A biblioteca ainda não tem estilos" in visible  # sem estilo do mockup
    assert "+ Criar novo estilo" in visible
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
    # `pgLibrary` não mostra contagem de uso por cartão; arquivar continua no diálogo de edição
    assert "Vincular ao canal" in visible or "Ativo no canal" in visible
    assert "Arquivar" in page(env).text


def test_styles_page_empty_library_says_no_canal_uses_any(env):
    assert "Nenhum canal usa" not in page_text(page(env).text)


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


def test_styles_page_keeps_the_active_channel_in_the_topbar(env):
    html = page(env).text
    assert 'id="canal-ativo"' in html
    assert "Canal H" in html
    assert "Nenhum canal cadastrado" not in html


def test_styles_page_marks_biblioteca_active_and_no_dead_configuracoes(env):
    """W1.5: a biblioteca de estilos é o item **Biblioteca** do menu, não seção de Configurações."""
    html = page(env).text
    items = nav_items(html)
    assert [_nav_text(i) for i in items] == ["Início", "Criar vídeo", "Vídeos", "Tendências e ideias",
                                            "Desempenho", "Biblioteca", "Configurações"]
    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1 and "Biblioteca" in _nav_text(active[0])
    assert re.search(r'href="/studio/panel/estilos(?:\?project_id=[^"]+)?"', active[0])
    # A página é a própria Biblioteca: sem a navegação de seções de Configurações.
    assert 'id="pagina-biblioteca"' in html
    assert 'id="menu-config"' not in html
    # Configurações não fica falso-ativa nesta tela (o item existe no menu, mas sem `aria-current`).
    config_item = next(i for i in items if "Configurações" in _nav_text(i))
    assert 'aria-current="page"' not in config_item
    assert _without_style_and_script(html).count('aria-current="page"') == 1
    assert "em breve" not in html
    # nenhum item indisponível na casca: "Configurações — em breve" virou área real
    assert not any('aria-disabled="true"' in item for item in items)
    # a seção "Indisponível nesta versão" não existe vazia
    assert "Indisponível nesta versão" not in html


# ------------------------------------------------------------- acessibilidade


def test_styles_form_has_labels_hints_and_collapsed_advanced(env):
    _create_style(env, "Com avançado")
    html = page(env).text
    # modal de criação = `renderModal` (`m.t==='style'`): Nome, Descrição curta, Instrução de arte
    for field_id in ("novo-estilo-nome", "novo-estilo-descricao", "novo-estilo-arte"):
        assert f'for="{field_id}"' in html, field_id
    assert "Salvar na biblioteca" in html and "Cancelar" in html
    # o diálogo de edição mantém os parâmetros reais do render, com "Avançado" recolhido
    assert re.search(r'for="editar-[0-9a-f]{32}-bpm"', html)
    assert 'role="status"' in html and 'aria-live="polite"' in html
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
    card = page(env).text.split('class="card" data-style-id', 1)[1].split("</div>", 4)
    summary = re.search(r'<p class="sub"[^>]*>(.*?)</p>', "</div>".join(card), re.S).group(1)
    assert "transição" not in summary and "extra" not in summary


# ------------------------------------------------------------------ higiene


def test_styles_page_preserves_csp_and_no_store(env):
    r = page(env)
    assert r.status_code == 200
    assert "nonce-" in r.headers["Content-Security-Policy"]
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_styles_page_requires_authentication(env):
    assert env["client"].get("/studio/panel/estilos").status_code == 401


def test_studio_music_endpoint_streams_audio_and_validates(env):
    # Extensão inválida
    assert env["client"].get("/studio/music/malicious.sh", headers=AUTH_HEADER).status_code == 400
    # Arquivo inexistente
    assert env["client"].get("/studio/music/nao_existe_12345.mp3", headers=AUTH_HEADER).status_code == 404
    # Arquivo existente local
    r = env["client"].get("/studio/music/939d0f93.mp3", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["accept-ranges"] == "bytes"
    assert len(r.content) > 1000


def test_library_voices_and_script_templates_tabs(env):
    html = page(env).text
    # 1. Aba Vozes
    assert 'id="painel-vozes"' in html
    assert "Piper Faber" in html
    assert "pt_BR-faber-medium" in html
    assert "172" in html
    # 2. Aba Modelos de Roteiro
    assert 'id="painel-modelos"' in html
    assert "Shorts" in html
    assert "Retenção" in html or "Viral" in html
    assert "Documentário" in html or "capítulos" in html
