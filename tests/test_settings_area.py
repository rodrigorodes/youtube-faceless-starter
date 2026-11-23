"""UX-02/W1.5: Configurações como área de rotas reais (/studio/configuracoes/<seção>).

As seções que levam à tela canônica **redirecionam** (302); as que ganharam **página própria** na
W1.5 (`estrategia`, `marca`, `producao`) são renderizadas pela aplicação — não redirecionam. Seção
desconhecida dá 404 (nada de link morto). O conteúdo real das páginas próprias é verificado em
`tests/test_settings_sections.py` (com Postgres descartável).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

AUTH = ("test-user", "test-browser-password")

# W1.5: sete seções do protótipo. Estas continuam sendo redirecionamento para a tela canônica.
# `estilos` e `identidade` são apelidos legados (não aparecem no menu) que não podem virar 404.
REDIRECTS = {
    "estilos": "/studio/panel/estilos",
    "conexoes": "/studio/panel/conexoes",
    "equipe": "/studio/panel/equipe",
    "avancado": "/studio/panel/avancado",
    "identidade": "/studio/configuracoes/marca",
}

# W1.5: seções com página própria (`panel_settings`), renderizadas pela aplicação — sem redirect.
OWN_PAGES = ("canais", "estrategia", "marca", "producao")


@pytest.mark.parametrize("section,target", REDIRECTS.items())
def test_each_settings_section_that_redirects_reaches_its_real_screen(section, target):
    r = TestClient(app).get(f"/studio/configuracoes/{section}", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == target


@pytest.mark.parametrize("section", OWN_PAGES)
def test_sections_with_their_own_page_do_not_redirect(section):
    r = TestClient(app).get(f"/studio/configuracoes/{section}", auth=AUTH, follow_redirects=False)
    assert r.status_code != 302, f"{section}: deveria ter página própria, não redirecionar"


def test_settings_root_opens_the_first_section():
    r = TestClient(app).get("/studio/configuracoes", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/studio/configuracoes/canais"


def test_unknown_settings_section_is_404():
    r = TestClient(app).get("/studio/configuracoes/inexistente", auth=AUTH, follow_redirects=False)
    assert r.status_code == 404


def test_settings_area_requires_authentication():
    r = TestClient(app).get("/studio/configuracoes/canais", follow_redirects=False)
    assert r.status_code in (401, 403)
