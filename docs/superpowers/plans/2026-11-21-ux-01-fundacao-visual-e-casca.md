# UX-01 — Fundação visual e casca de navegação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar ao painel real (rotas de servidor) a tipografia, os ícones e a navegação da proposta V3 aprovada, sem mudar behavior nenhum.

**Architecture:** Toda a casca vem de `renderer/app/studio/api/panel.py` — o `CSS` (uma string única usada por todas as telas), `_NAV_ICONS` e `build_sidebar_nav`/`render_sidebar`. As telas já chamam `shell.render_sidebar(active=...)`. A fatia mexe só nessa casca + nos rótulos das páginas; nenhum caso de uso, repositório ou rota muda de comportamento.

**Tech Stack:** Python 3.11, FastAPI, HTML/CSS server-rendered com CSP por nonce, pytest.

**Spec:** `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (aprovada pelo dono em 2026-11-21) e `docs/backlogs/Faceless_Studio_V2_Projeto_Completo/produto/JORNADA-E-TELAS.md`.

## Global Constraints

- CSP do painel: `script-src 'nonce-…'`; **nenhum** handler inline (`onclick`, `onkeydown`). Interação só por `<script nonce>`.
- Exatamente **um** `<h1>` por página e **um** `aria-current="page"` na navegação principal (contrato em `tests/test_ux_contract.py`).
- Nada de texto ilustrativo do mockup (`1,2 mi views`, `run_7f31`, …) e nada de número inventado; ausência nunca vira `US$ 0,00`.
- Ícone é decorativo: `<svg aria-hidden="true" focusable="false">`, e o rótulo em texto ao lado (nunca só ícone).
- Copy em português do Brasil. `domain`/`application` puros; wiring só em `composition.py` (não tocado aqui).
- Nunca `git add -A`: caminhos exatos.
- Suíte desta fatia roda offline: `PYTHONPATH=renderer python -m pytest tests/test_panel.py tests/test_ux_contract.py -q`.

## Review Focus

- **Item de navegação apontando para rota inexistente** — o usuário clica e recebe 404; todo `href` da casca precisa responder 200/302.
- **Dois `aria-current="page"`** — leitor de tela anuncia duas "páginas atuais"; o contrato precisa pegar.
- **Ícone anunciado como texto** — SVG sem `aria-hidden` faz o leitor de tela ler lixo no meio do rótulo.
- **Página órfã** — tirar "Produção" do menu sem outro caminho deixa uma tela real inalcançável.
- **Fonte divergente do protótipo** — trocar a ordem do `font-family` muda a renderização sem quebrar teste nenhum; precisa de teste.

---

### Task 1: Tipografia do protótipo

**Files:**
- Modify: `renderer/app/studio/api/panel.py` (bloco `CSS`, a partir da linha 216; `font-family` na linha 268)
- Test: `tests/test_ux_contract.py`

**Interfaces:**
- Produces: token `--font-ui` em `:root`, consumido por `body { font-family: var(--font-ui) }`. Escala: `.h1`/`h1` 35px com `letter-spacing:-1.3px`, `.eyebrow` 10px com `letter-spacing:2px`, `.nav-item` peso 560, `.brand-title` peso 780.

- [ ] **Step 1: Write the failing test**

Em `tests/test_ux_contract.py`:

```python
def test_shell_uses_the_prototype_typeface():
    """A fonte da casca é a do protótipo aprovado: Inter primeiro, mesmo fallback do original."""
    html, _ = render_panel(_render_view())
    css = re.search(r"<style[^>]*>(.*?)</style>", html, re.S).group(1)
    assert "--font-ui: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont" in css
    assert "font-family: var(--font-ui)" in css
    assert re.search(r"--font-scale-h1:\s*35px", css)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python -m pytest tests/test_ux_contract.py::test_shell_uses_the_prototype_typeface -v`
Expected: FAIL — `--font-ui` não existe no CSS.

- [ ] **Step 3: Implement the tokens in the `CSS` block**

Em `:root`, junto dos demais tokens:

```css
/* Tipografia do protótipo aprovado (faceless-studio-v3-proposta-ptbr.html). */
--font-ui: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-scale-h1: 35px;
--font-tracking-h1: -1.3px;
--font-scale-eyebrow: 10px;
--font-tracking-eyebrow: 2px;
```

Trocar `font-family: -apple-system, …` do `body` por `font-family: var(--font-ui)`, e usar os tokens em `h1`/`.h1`/`.eyebrow`/`.nav-item`/`.brand-title` (35px/-1.3px, 10px/2px, 560, 780).

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=renderer python -m pytest tests/test_panel.py tests/test_ux_contract.py -q`
Expected: PASS (61 ou mais).

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_ux_contract.py
git commit -m "feat(ux-01): tipografia da casca igual ao protótipo aprovado"
```

---

### Task 2: Ícones que faltam na navegação

**Files:**
- Modify: `renderer/app/studio/api/panel.py` (`_NAV_ICONS`, linha 70)
- Test: `tests/test_ux_contract.py`

**Interfaces:**
- Produces: chaves `"novo-video"`, `"desempenho"` e `"configuracao"` em `_NAV_ICONS`, cada uma com `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">…</svg>`. Consumidas por `build_sidebar_nav` na Task 3.

- [ ] **Step 1: Write the failing test**

```python
def test_every_primary_nav_item_has_a_decorative_icon():
    html = _render_panel_html()
    items = _nav_items(html)
    assert items
    for item in items:
        svgs = re.findall(r"<svg[^>]*>", item)
        assert len(svgs) == 1, item
        assert 'aria-hidden="true"' in svgs[0] and 'focusable="false"' in svgs[0], svgs[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python -m pytest tests/test_ux_contract.py::test_every_primary_nav_item_has_a_decorative_icon -v`
Expected: FAIL — item "Novo vídeo" (novo) ou "Desempenho" sem ícone.

- [ ] **Step 3: Add the icons**

Usar os traços do protótipo (18×18, `stroke-width:1.8` via CSS):

```python
"novo-video": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v8M8 12h8"></path></svg>',
"desempenho": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><path d="M3 20h18M6 16V9m6 7V4m6 12v-5"></path></svg>',
"configuracao": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"></circle><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"></path></svg>',
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=renderer python -m pytest tests/test_ux_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_ux_contract.py
git commit -m "feat(ux-01): ícones de novo vídeo, desempenho e configuração"
```

---

### Task 3: Navegação na IA aprovada

**Files:**
- Modify: `renderer/app/studio/api/panel.py` (`build_sidebar_nav`, linha 87)
- Modify: `tests/test_panel.py` (teste `test_render_panel_shell_marks_exactly_one_active_nav_item`, ~linha 625)
- Modify: `tests/test_ux_contract.py` (`test_video_detail_uses_the_shell_and_videos_has_a_real_destination`)
- Test: `tests/test_panel.py`

**Interfaces:**
- Consumes: `_NAV_ICONS["novo-video"|"desempenho"|"configuracao"]` da Task 2.
- Produces: `build_sidebar_nav(active=...)` com dois grupos — **Operação**: `inicio`→`/studio/panel`, `novo-video`→`/studio/panel/novo-video`, `videos`→`/studio/panel/videos`, `tendencias`→`/studio/panel/tendencias`, `desempenho`→`/studio/panel/analytics`; **Configuração**: `canais`→`/studio/canais`, `estilos`→`/studio/panel/estilos`, `conexoes`→`/studio/panel/conexoes`, `equipe`→`/studio/panel/equipe`. "Produção" sai do menu.

- [ ] **Step 1: Write the failing test**

Substituir, em `tests/test_panel.py`, a lista de rótulos e o mapa de hrefs por:

```python
for expected in ("Início", "Novo vídeo", "Vídeos", "Tendências", "Desempenho",
                 "Canais", "Estilos", "Conexões", "Equipe"):
    assert any(expected in label for label in labels), expected

for label, href in (
    ("Início", "/studio/panel"),
    ("Novo vídeo", "/studio/panel/novo-video"),
    ("Vídeos", "/studio/panel/videos"),
    ("Tendências", "/studio/panel/tendencias"),
    ("Desempenho", "/studio/panel/analytics"),
):
    item = next(item for item in items if label in _nav_text(item))
    assert f'href="{href}"' in item

# Produção deixou de ser item de menu (a tela continua existindo — Task 4).
assert not any("Produção" in label for label in labels)
```

E em `tests/test_ux_contract.py`, no teste da casca do vídeo, trocar a tupla por `("Início", "Novo vídeo", "Vídeos", "Tendências")`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=renderer python -m pytest tests/test_panel.py::test_render_panel_shell_marks_exactly_one_active_nav_item tests/test_ux_contract.py -q`
Expected: FAIL — "Novo vídeo" e "Desempenho" ausentes; "Produção" ainda presente.

- [ ] **Step 3: Rewrite `build_sidebar_nav`**

Reescrever `links` e o bloco `management` com os pares acima, mantendo o padrão atual (`aria-current="page"` + classe `active` só para `key == active`) e o rótulo do segundo grupo como `<p class="nav-label">Configuração</p>`. Nenhum href novo é inventado: todos já têm rota (`/panel/novo-video` em `routes.py:1720`, `/panel/analytics` em `:1392`, `/canais` em `:1369`, `/panel/estilos` em `:1857`, `/panel/conexoes` em `:1866`, `/panel/equipe` em `:1269`).

- [ ] **Step 4: Run the full panel suite**

Run: `PYTHONPATH=renderer python -m pytest tests/test_panel.py tests/test_ux_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel.py tests/test_ux_contract.py
git commit -m "feat(ux-01): navegação na IA aprovada (Início, Novo vídeo, Vídeos, Tendências, Desempenho + Configuração)"
```

---

### Task 4: Produção continua alcançável

**Files:**
- Modify: `renderer/app/studio/api/panel.py` (bloco `inicio_producao_body_html`, ~linha 2403)
- Test: `tests/test_panel.py`

**Interfaces:**
- Consumes: a rota `/studio/panel/producao` (existe desde IA-01).
- Produces: link permanente no estado vazio do Início.

- [ ] **Step 1: Write the failing test**

```python
def test_production_stays_reachable_after_leaving_the_menu():
    """Produção saiu do menu; o Início sem vídeos ainda precisa dar o caminho."""
    html = _render_panel_html()
    assert 'href="/studio/panel/producao"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python -m pytest tests/test_panel.py::test_production_stays_reachable_after_leaving_the_menu -v`
Expected: FAIL — o repositório falso não tem vídeos, então só renderiza o card vazio, sem link.

- [ ] **Step 3: Add the link to the empty state**

No `article.card.empty` de `inicio_producao_body_html`, acrescentar depois do `<p class="fine">`:

```html
<div class="row"><a class="btn" href="/studio/panel/producao">Abrir Produção</a></div>
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=renderer python -m pytest tests/test_panel.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel.py
git commit -m "feat(ux-01): Início mantém caminho para Produção fora do menu"
```

---

### Task 5: A página de Analytics passa a se chamar Desempenho

**Files:**
- Modify: `renderer/app/studio/api/panel_analytics.py` (linha 387 `<title>`, linha 393 `<h1>`)
- Modify: `tests/test_analytics_page.py` (linha 117, asserção do `<h1>`)
- Test: `tests/test_analytics_page.py` e um teste offline novo em `tests/test_analytics_page.py`

**Interfaces:**
- Produces: `<h1 id="analytics-heading">Desempenho</h1>` e `<title>Faceless Studio — Desempenho</title>`; o rótulo do menu é o mesmo texto, então nav e título concordam.

- [ ] **Step 1: Write the failing offline test**

```python
def test_performance_page_title_matches_the_navigation():
    """O título da página é o mesmo rótulo do menu — sem 'Analytics' sobrando."""
    from app.studio.api.panel_analytics import render_analytics

    html, _ = render_analytics(_empty_dashboard_view())
    assert re.search(r"<h1[^>]*>Desempenho</h1>", html)
    assert "<title>Faceless Studio — Desempenho</title>" in html
```

`_empty_dashboard_view()` constrói `AnalyticsDashboardView` com campos vazios (`tiles=()`, `insights=()`, …, `readiness=CollectionReadiness(...)` com tudo indisponível), seguindo os campos da dataclass em `application/analytics_dashboard.py:256-280`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python -m pytest tests/test_analytics_page.py::test_performance_page_title_matches_the_navigation -v`
Expected: FAIL — o `<h1>` é "Analytics".

- [ ] **Step 3: Rename in the template**

Trocar os dois textos em `panel_analytics.py` e atualizar a asserção da linha 117 de `tests/test_analytics_page.py` para `Desempenho`.

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=renderer python -m pytest tests/test_analytics_page.py -q`
Expected: o teste novo PASSA; os testes de banco continuam `skipped` (sem `STUDIO_TEST_DSN`), sem falha.

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_analytics.py tests/test_analytics_page.py
git commit -m "feat(ux-01): Analytics vira Desempenho no menu e no título"
```

---

## Fora desta fatia (próximos planos)

- **UX-02 — Configurações como área:** `/configuracoes/<seção>` reunindo canais, estilos, conexões e equipe, com sub-navegação e redirects das rotas antigas. É lá que o grupo "Configuração" vira o item único "Configurações" do protótipo.
- **UX-03 — Tema claro:** o protótipo tem `light-dark()` e alternador; o painel hoje é dark-only (`color-scheme: dark`). Exige pares de contraste medidos e persistência da escolha.
- **UX-04 — Tendências no visual novo:** a tela já tem pilares (pills + modal); falta alinhar tipografia/estados ao protótipo.
