"""Canal ativo (F02.T01/G11): o parâmetro sobrevive na navegação, nunca invade o vídeo.

Regra do produto: quem escolheu o Canal B continua no Canal B ao andar pelas áreas do Estúdio;
o vídeo mantém o projeto **proprietário** (derivado pelo Core), e link externo/âncora não muda.
"""
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.studio.api.active_channel import propagate, with_channel  # noqa: E402

AUTH = ("test-user", "test-browser-password")
A = "a" * 32
B = "b" * 32


@pytest.mark.parametrize("path", [
    "/studio/panel",
    "/studio/panel/novo-video",
    "/studio/panel/videos",
    "/studio/panel/tendencias",
    "/studio/panel/analytics",
    "/studio/panel/producao",
    "/studio/canais",
    "/studio/panel/estilos",
    "/studio/panel/conexoes",
    "/studio/panel/equipe",
    "/studio/configuracoes/canais",
])
def test_channel_pages_carry_the_active_channel(path):
    assert with_channel(path, B) == f"{path}?project_id={B}"


@pytest.mark.parametrize("url", [
    "/studio/panel/videos/" + "c" * 32,          # vídeo: dono é o vídeo
    "/studio/videos/" + "c" * 32 + "/preview",   # prévia do vídeo
    "/studio/videos/" + "c" * 32 + "/file",      # download
    "/studio/publications/claim",                # API
    "https://www.youtube.com/watch?v=x",         # externo
    "#conteudo",                                 # âncora
    "mailto:alguem@exemplo.com",
])
def test_video_endpoints_and_external_links_are_left_alone(url):
    assert with_channel(url, B) == url


def test_existing_query_is_preserved_and_the_param_is_not_duplicated():
    assert with_channel("/studio/panel?project_id=" + A, B) == "/studio/panel?project_id=" + A
    assert with_channel("/studio/panel?days=7", B) == f"/studio/panel?days=7&project_id={B}"


def test_without_an_active_channel_nothing_changes():
    assert with_channel("/studio/panel", "") == "/studio/panel"
    html = '<a href="/studio/panel">x</a>'
    assert propagate(html, "") == html


def test_propagate_touches_only_hrefs_of_channel_pages():
    html = ('<a href="/studio/panel">Início</a>'
            '<a href="/studio/panel/videos/' + "c" * 32 + '">Vídeo</a>'
            '<a href="/studio/videos/' + "c" * 32 + '/file">Baixar</a>'
            '<a href="https://exemplo.com">Fora</a>')
    out = propagate(html, B)
    assert f'href="/studio/panel?project_id={B}"' in out
    assert f'/studio/panel/videos/{"c" * 32}"' in out  # vídeo intacto
    assert f'/studio/videos/{"c" * 32}/file"' in out   # download intacto
    assert 'href="https://exemplo.com"' in out
    assert propagate(out, B) == out  # idempotente


def test_propagate_is_idempotent_on_the_same_document():
    html = propagate('<a href="/studio/panel">x</a>', B)
    assert propagate(html, B) == html


def test_settings_redirect_keeps_the_active_channel():
    client = TestClient(app)
    r = client.get(f"/studio/configuracoes/canais?project_id={B}", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"/studio/canais?project_id={B}"


def test_settings_root_redirect_keeps_the_active_channel():
    client = TestClient(app)
    r = client.get(f"/studio/configuracoes?project_id={B}", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"/studio/canais?project_id={B}"

def test_the_video_page_shell_shows_the_owner_channel_and_not_the_empty_state():
    """W1.2 (R6): páginas do vídeo mostram o canal **dono** (leitura), nunca a casca vazia."""
    from app.studio.api.shell_v3 import render_document

    html = render_document(
        title="Vídeo", active="videos", crumb="Vídeos / Detalhe", nonce="n",
        body_html="<p>x</p>", projects=[], project_id="", cost_note="",
        video_channel="Canal B",
    )
    assert "Canal B" in html
    assert 'id="canal-do-video"' in html      # rótulo de leitura do dono do vídeo
    assert 'id="sem-canal"' not in html       # nada de "Nenhum canal"
    assert "Nenhum canal cadastrado" not in html


def test_without_a_video_channel_the_shell_keeps_the_previous_behavior():
    """Sem canal de vídeo, a casca continua mostrando o seletor (ou o estado vazio) como antes."""
    from app.studio.api.shell_v3 import render_document

    html = render_document(title="Vídeos", active="videos", crumb="Vídeos", nonce="n",
                           body_html="<p>x</p>", projects=[(A, "Canal A")], project_id=A, cost_note="")
    assert '<select class="canal-select" id="canal-ativo">' in html
    assert 'id="canal-do-video"' not in html


def test_a_rendered_page_keeps_the_channel_in_nav_and_body_but_not_in_the_video():
    """Aceite F02.T01: escolher o Canal B mantém B na casca e no corpo; o vídeo não muda."""
    from app.studio.api.shell_v3 import render_document

    video_id = "c" * 32
    html = render_document(
        title="Vídeos", active="videos", crumb="Vídeos", nonce="n",
        body_html=(f'<a href="/studio/panel/tendencias">Tendências</a>'
                   f'<a href="/studio/panel/videos/{video_id}">Vídeo</a>'),
        projects=[(B, "Canal B")], project_id=B, cost_note="",
    )
    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    for page in ("/studio/panel", "/studio/panel/novo-video", "/studio/panel/videos",
                 "/studio/panel/tendencias", "/studio/panel/analytics"):
        assert f'href="{page}?project_id={B}"' in main
    cfg = re.search(r'<nav aria-label="Configuração">(.*?)</nav>', html, re.S).group(1)
    assert f'href="/studio/configuracoes/canais?project_id={B}"' in cfg
    assert f'href="/studio/panel/tendencias?project_id={B}"' in html     # corpo
    assert f'href="/studio/panel/videos/{video_id}"' in html             # vídeo intacto
    assert f'/studio/panel/videos/{video_id}?project_id' not in html
    select = re.search(r'<select class="canal-select" id="canal-ativo">(.*?)</select>', html, re.S).group(1)
    assert f'<option value="{B}" selected>Canal B</option>' in select
