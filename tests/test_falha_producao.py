"""A produção que para por falta de fonte explica o que fazer, leva à aba certa e mantém o motivo técnico."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.api.falha_producao import explicar_falha, falha_html  # noqa: E402

VID = "a" * 32
SEM_FONTE = "SourceRefused: no sources with checkable claims: add sources first"


def test_missing_sources_explains_the_next_step_and_links_to_the_sources_area():
    falha = explicar_falha(SEM_FONTE)
    assert falha is not None and "fonte" in falha.texto and "Tentar novamente" in falha.texto
    html = falha_html(SEM_FONTE, VID)
    assert f'href="/studio/panel/videos/{VID}/fontes"' in html and "Adicionar fonte" in html
    assert SEM_FONTE in html  # o motivo técnico continua visível


def test_each_known_failure_points_to_the_right_place():
    assert 'videos/' + VID + '/cenas"' in falha_html("fact-check did not pass (scenes: 2)", VID)
    assert '/qualidade"' in falha_html("QA failed: audio clipping", VID)
    assert 'href="/studio/panel/conexoes"' in falha_html("YouTube channel reconnect required: x", VID)
    assert '/fontes"' in falha_html("url host is not in the allowlist", VID)


def test_unknown_or_empty_reason_never_invents_an_explanation():
    html = falha_html("kaboom: weird", VID)
    assert "não tem uma explicação pronta" in html and "kaboom: weird" in html and "<a " not in html
    assert explicar_falha("kaboom") is None and explicar_falha("  ") is None and explicar_falha(None) is None
    assert "motivo não foi registrado" in falha_html(None, VID)


def test_technical_reason_is_escaped():
    assert "<script>" not in falha_html("<script>alert(1)</script>", VID)
