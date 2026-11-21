"""Contrato de UX — as regras canônicas de `produto/JORNADA-E-TELAS.md` num lugar só.

Fonte de verdade visual: `docs/backlogs/Faceless_Studio_V2_Projeto_Completo/produto/`
(mockup aprovado pelo usuário). Cada fatia de UI — G, E, H e as seguintes — tem de passar
por aqui. O contrato existe porque as regras já estavam enforçadas, mas espalhadas em ~2.300
linhas de teste: quem escreve uma tela nova não descobria o que tinha de cumprir.

A regra que atravessa todas: onde o mockup mostra dado **ilustrativo**, o painel real
renderiza **dado real** ou **estado vazio explícito** — o texto de exemplo nunca embarca.
"""

import re

import pytest

from test_panel import _detail_view, _render_panel_html, _row, _visible_text

# Texto que existe SÓ no mockup ilustrativo e não pode vazar para o produto.
MOCKUP_ONLY_TEXT = (
    "1,2 mi views",
    "run_7f31",
    "840 mil views",
    "Finanças Descomplicadas",
)


def _states(html):
    """Todo badge de estado e o texto visível dentro dele — sem contar o glifo de ícone.

    O glifo é decorativo: se ele contasse como "texto", um estado só com cor+ícone passaria
    (a sonda `test_contract_catches_a_state_without_text` pega exatamente isso).
    """
    without_glyph = re.sub(r'<span class="glyph"[^>]*>.*?</span>', "", html, flags=re.S)
    return [(kind, _visible_text(body)) for kind, body in
            re.findall(r'<span class="state (s-[a-z]+)"[^>]*>(.*?)</span>', without_glyph, re.S)]


def _nav_items(html):
    """Itens da navegação principal — ou vazio quando a página não tem a casca aprovada."""
    match = re.search(r'<nav class="nav" aria-label="Principal">(.*?)</nav>', html, re.S)
    if match is None:
        return []
    return re.findall(r"<li>(.*?)</li>", match.group(1), re.S)


def assert_ux_contract(html, *, page):
    """As regras de UX canônicas, aplicáveis a qualquer página renderizada."""
    text = _visible_text(html)

    # R1 — concluído / em execução / ação necessária sempre com TEXTO, nunca só cor ou ícone.
    for kind, body in _states(html):
        assert body.strip(), f"{page}: estado '{kind}' sem texto (só cor/ícone)"

    # R2 — nenhum comando inválido pelo estado; item indisponível não é focável.
    for item in _nav_items(html):
        if 'aria-disabled="true"' in item:
            assert not item.lstrip().startswith(("<a ", "<button")), \
                f"{page}: item indisponível focável (deve ser <span>)"

    # R3 — custo real vs estimado com rótulo explícito; ausência NUNCA é zero.
    assert "US$ 0,00" not in html, f"{page}: ausência de custo renderizada como US$ 0,00"

    # R4 — falha não mostra stack trace ao operador.
    for forbidden in ("Traceback (most recent call last)", 'File "', "raise "):
        assert forbidden not in text, f"{page}: stack trace exposta ao operador ({forbidden!r})"

    # R5 — IDs, traces e uso de modelos só em seção técnica avançada (fechada por padrão).
    assert "<details open" not in html, f"{page}: seção avançada aberta por padrão"

    # R6 — responsivo e acessível.
    assert '<meta name="viewport"' in html, f"{page}: sem viewport (não é responsivo)"
    assert "@media" in html, f"{page}: sem media query (não é responsivo)"
    assert html.count("<h1") == 1, f"{page}: exatamente um <h1> esperado"

    # Extra — sem barra de progresso onde o trabalho não é linear (a regra do mockup).
    assert "<progress" not in html and 'role="progressbar"' not in html, \
        f"{page}: barra de progresso afirmando linearidade que não existe"

    # Extra — nada do mockup ilustrativo vaza para o produto.
    for leaked in MOCKUP_ONLY_TEXT:
        assert leaked not in text, f"{page}: texto ilustrativo do mockup vazou ({leaked!r})"


def test_panel_home_satisfies_the_ux_contract():
    assert_ux_contract(_render_panel_html(), page="painel/início")


def test_video_detail_satisfies_the_ux_contract():
    assert_ux_contract(_detail_view(_row("v1", "Tópico real")), page="painel/vídeo")


# HTML mínimo que satisfaz as checagens estruturais, para as sondas isolarem UMA regra.
_BASE = (
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<style>@media (max-width: 1px) {}</style>"
    "<h1>Título</h1>"
    '<nav class="nav" aria-label="Principal"><li><span>Início</span></li></nav>'
)


def test_contract_catches_a_state_without_text():
    """Prova que a checagem de R1 é load-bearing."""
    html = _BASE + '<span class="state s-run"><span class="glyph">◐</span></span>'
    with pytest.raises(AssertionError, match="sem texto"):
        assert_ux_contract(html, page="probe")


def test_contract_catches_zero_for_absent_cost():
    with pytest.raises(AssertionError, match=r"US\$ 0,00"):
        assert_ux_contract(_BASE + "<p>Total US$ 0,00</p>", page="probe")


def test_contract_catches_leaked_mockup_text():
    with pytest.raises(AssertionError, match="ilustrativo"):
        assert_ux_contract(_BASE + "<p>1,2 mi views</p>", page="probe")


def test_contract_catches_a_focusable_unavailable_nav_item():
    """Item indisponível tem de ser <span>, não algo em que o foco entra."""
    html = _BASE.replace('<li><span>Início</span></li>',
                         '<li><a href="#x" aria-disabled="true">Canais</a></li>')
    with pytest.raises(AssertionError, match="focável"):
        assert_ux_contract(html, page="probe")


def test_contract_catches_an_open_advanced_section():
    with pytest.raises(AssertionError, match="aberta por padrão"):
        assert_ux_contract(_BASE + "<details open><summary>d</summary></details>", page="probe")
