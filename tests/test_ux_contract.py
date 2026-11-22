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

from test_panel import _detail_view, _render_panel_html, _render_producao_html, _row, _visible_text

# Texto que existe SÓ no mockup ilustrativo e não pode vazar para o produto.
MOCKUP_ONLY_TEXT = (
    "1,2 mi views",
    "run_7f31",
    "840 mil views",
    "Finanças Descomplicadas",
    # W1.4: temas e nomes de demonstração do protótipo novo (`prototype/index.html`, S.videos/ideas).
    "O que quase ninguém sabe sobre este lugar",
    "Três perguntas para entender o futuro",
    "Uma descoberta que mudou nossa história",
    "Além do planeta",
    "Histórias em 5 minutos",
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
    match = re.search(r'<nav(?: class="nav")? aria-label="Principal">(.*?)</nav>', html, re.S)
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


def test_shell_uses_the_prototype_typeface():
    """A fonte da casca é a do protótipo aprovado: Inter primeiro, mesmo fallback do original.

    Sem isso, trocar a ordem do `font-family` muda a renderização de todas as telas sem quebrar
    nenhum outro teste.
    """
    html = _render_producao_html()
    css = re.search(r"<style[^>]*>(.*?)</style>", html, re.S).group(1)

    assert "--font-ui: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont" in css
    assert "font-family: var(--font-ui)" in css
    assert re.search(r"--font-scale-h1:\s*35px", css)


def test_nav_icon_set_covers_the_approved_ia():
    """Todo item da IA aprovada tem ícone decorativo próprio (nunca anunciado como texto)."""
    from app.studio.api.panel import _NAV_ICONS

    for key in ("inicio", "novo-video", "videos", "tendencias", "desempenho",
                "canais", "estilos", "conexoes", "equipe"):
        assert key in _NAV_ICONS, key
        assert 'aria-hidden="true"' in _NAV_ICONS[key], key
        assert 'focusable="false"' in _NAV_ICONS[key], key


def test_panel_home_satisfies_the_ux_contract():
    assert_ux_contract(_render_panel_html(), page="painel/início")


def test_video_detail_satisfies_the_ux_contract():
    html = _detail_view(_row("v1", "Tópico real"))
    assert_ux_contract(html, page="painel/vídeo")
    # A página tem a casca aprovada: o contrato não pode ser satisfeito de forma vacuosa
    # (R2 só morde quando a nav principal existe).
    assert _nav_items(html), "painel/vídeo: contrato passou sem a navegação principal"


def test_video_detail_uses_the_shell_and_videos_has_a_real_destination():
    """O detalhe usa a casca aprovada e "Vídeos" volta à sidebar com destino real."""
    html = _detail_view(_row("v1", "Tópico real"))
    items = _nav_items(html)
    labels = [_visible_text(item) for item in items]

    for expected in ("Início", "Criar vídeo", "Vídeos", "Tendências e ideias"):
        assert any(expected in label for label in labels), f"painel/vídeo: '{expected}' fora da casca"

    videos = next(item for item in items if "Vídeos" in _visible_text(item))
    # IA-01: destino real e sem link morto — a rota /studio/panel/videos redireciona (302) para o
    # bloco `#videos` do Início.
    assert 'href="/studio/panel/videos"' in videos, videos

    active = [item for item in items if 'aria-current="page"' in item]
    assert len(active) == 1, f"painel/vídeo: {len(active)} itens ativos na casca"
    assert "Vídeos" in _visible_text(active[0])

    # A casca não duplica o <h1> da página.
    assert html.count("<h1") == 1

    # A navegação interna do vídeo coexiste como secundária — cada <nav> com rótulo próprio.
    labels = re.findall(r'<nav[^>]*aria-label="([^"]+)"', html)
    assert "Principal" in labels
    assert len(labels) == len(set(labels)), f"painel/vídeo: aria-label de <nav> repetido: {labels}"


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


# ---------------------------------------------------------------- UX-03: tema claro


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(value):
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_light_theme_text_pairs_meet_wcag_aa():
    """Cada par texto/fundo do tema claro tem contraste >= 4,5:1 (medido, não suposto)."""
    from app.studio.api.panel import LIGHT_TOKENS as t

    backgrounds = ("bg-app", "bg-canvas", "surface", "surface-raised")
    for fg in ("text", "text-muted", "text-dim", "accent", "success", "info", "warn", "danger"):
        for bg in backgrounds:
            assert _contrast(t[fg], t[bg]) >= 4.5, (fg, bg, _contrast(t[fg], t[bg]))
    for fg, bg in (("accent-contrast", "accent"), ("accent-contrast", "accent-strong"),
                   ("text", "accent-soft"), ("success", "success-surface"),
                   ("info", "info-surface"), ("warn", "warn-surface"), ("danger", "danger-surface")):
        assert _contrast(t[fg], t[bg]) >= 4.5, (fg, bg, _contrast(t[fg], t[bg]))


def test_theme_css_follows_os_preference_and_explicit_choice():
    html = _render_producao_html()
    css = re.search(r"<style[^>]*>(.*?)</style>", html, re.S).group(1)
    assert '<meta name="color-scheme" content="dark light">' in html
    assert '@media (prefers-color-scheme: light)' in css
    assert ':root[data-theme="light"]' in css
    assert ':root:not([data-theme="dark"])' in css  # a escolha explícita escura vence o SO
    assert '@media (forced-colors: active)' in css


def test_theme_toggle_is_hidden_without_js_and_uses_no_inline_handlers():
    html = _render_producao_html()
    button = re.search(r'<button[^>]*id="theme-toggle"[^>]*>', html).group(0)
    assert " hidden" in button  # sem JS não existe controle morto
    assert "onclick" not in html.lower()
    assert re.search(r'<script nonce="[^"]+">[^<]*studio-theme', html)
