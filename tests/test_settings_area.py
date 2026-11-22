"""UX-02: Configurações como área de rotas reais (/studio/configuracoes/<seção>).

Cada seção leva à tela real correspondente; seção desconhecida dá 404 (nada de link morto).
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

# F02.T03: as sete áreas. Estratégia/Produção vivem na tela de Canais (sanfonas reais).
SECTIONS = {
    "canais": "/studio/canais",
    "estrategia": "/studio/canais#painel-perfil",
    "estilos": "/studio/panel/estilos",
    "producao": "/studio/canais#painel-providers",
    "conexoes": "/studio/panel/conexoes",
    "equipe": "/studio/panel/equipe",
    "avancado": "/studio/panel/avancado",
}


@pytest.mark.parametrize("section,target", SECTIONS.items())
def test_each_settings_section_redirects_to_its_real_screen(section, target):
    r = TestClient(app).get(f"/studio/configuracoes/{section}", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == target


def test_settings_root_opens_the_first_section():
    r = TestClient(app).get("/studio/configuracoes", auth=AUTH, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/studio/canais"


def test_unknown_settings_section_is_404():
    r = TestClient(app).get("/studio/configuracoes/inexistente", auth=AUTH, follow_redirects=False)
    assert r.status_code == 404


def test_settings_area_requires_authentication():
    r = TestClient(app).get("/studio/configuracoes/canais", follow_redirects=False)
    assert r.status_code in (401, 403)
