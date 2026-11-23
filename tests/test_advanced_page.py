"""Tela Avançado (F02.T03): diagnóstico real, read-only, sem segredo e sem controle fictício."""
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OUTPUT_DIR", "/tmp/yfs-test/output")
os.environ.setdefault("JOB_DIR", "/tmp/yfs-test/jobs")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.panel_advanced import render_advanced  # noqa: E402
from app.studio.application.advanced_page import AdvancedPageView, AdvancedRow  # noqa: E402
from test_ux_contract import assert_ux_contract  # noqa: E402

A = "a" * 32


def _view(**kw):
    base = dict(
        projects=[(A, "Canal Gamer")],
        selected_project_id=A,
        database_ok=True,
        providers=(AdvancedRow("Texto", "opencode:luna", "disponível", "Estimado US$ 0,01", "8"),
                   AdvancedRow("Voz", "piper", "indisponível: binário ausente", "Sem custo", "9")),
        effective=(("Texto", "opencode:luna"), ("Voz", "piper"), ("Render", "ffmpeg")),
        notes=(),
    )
    base.update(kw)
    return AdvancedPageView(**base)


def test_advanced_page_is_the_v3_shell_and_says_what_is_real():
    html, headers = render_advanced(_view())
    assert html.count("<h1") == 1
    assert "Diagnóstico do Estúdio" in html
    # Fica dentro de Configurações: o protótipo só tem quatro abas, então "Avançado" mora em
    # "Conexões & Equipe" (aba ativa) e é alcançado pelo atalho secundário.
    cfg = re.search(r'<nav aria-label="Seções de configuração">(.*?)</nav>', html, re.S).group(1)
    ativo = re.search(r'<a[^>]*aria-current="page"[^>]*>(.*?)</a>', cfg, re.S).group(0)
    assert "Conexões" in ativo
    assert re.search(r'<a class="btn small" href="[^"]*/studio/panel/avancado[^"]*">Avançado e diagnóstico</a>', cfg)
    assert "Banco de dados: respondendo." in html
    assert "opencode:luna" in html and "piper" in html
    assert "indisponível: binário ausente" in html     # motivo real, não "erro"
    assert "Estimado US$ 0,01" in html or "Estimado US$ 0,01".replace(".", ",") in html
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert_ux_contract(html, page="configuracoes/avancado")


def test_advanced_page_reports_a_database_outage_instead_of_pretending_health():
    html, _ = render_advanced(_view(database_ok=False))
    assert "sem resposta agora" in html
    assert "Banco de dados: respondendo." not in html
    assert 'data-tipo="erro"' in html


def test_advanced_page_never_shows_a_secret_or_a_writable_control():
    html, _ = render_advanced(_view(
        effective=(("Texto", "opencode:luna"),),
        providers=(AdvancedRow("Texto", "opencode:luna", "disponível", "Desconhecido", "8"),)))
    visivel = re.sub(r"<[^>]+>", " ", re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S))
    for proibido in ("api_key", "API_KEY", "secret", "Bearer", "access_token"):
        assert proibido not in visivel
    pagina = re.search(r'<section class="pagina" id="pagina-configuracoes".*?</section>', html, re.S).group(0)
    assert "<input" not in pagina and "<textarea" not in pagina and "<select" not in pagina
    assert "<form" not in pagina and "<button" not in pagina
    assert not re.search(r"\son[a-z]+=", html)


def test_advanced_page_marks_the_settings_area_as_active():
    html, _ = render_advanced(_view())
    main = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, re.S).group(1)
    # NAV: "Configurações" é o 7º item do menu principal e fica ativo nesta tela.
    config_item = [li for li in re.findall(r"<li>.*?</li>", main, re.S) if "Configurações" in li]
    assert config_item and 'aria-current="page"' in config_item[0]


def test_empty_catalog_is_an_explicit_state():
    html, _ = render_advanced(_view(providers=(), effective=()))
    assert "Nenhum provider no catálogo desta instalação." in html
    assert "Nenhum canal ativo para resolver a configuração." in html