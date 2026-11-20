# Dashboard UX, Neutral YouTube Theme & Project Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o painel e a tela de prévia em uma experiência unificada e moderna com Tema YouTube Studio Dark Neutro (`#0f0f0f`), barra lateral de navegação completa na tela de prévia, gestão e alternância de projetos/canais na interface, esteira visual de produção do workflow, cards de vídeos aprimorados e radar de tendências compacto e despoluído.

**Architecture:** A camada de apresentação (`api/panel.py` e `api/preview.py`) adota a paleta YouTube Dark neutra em `:root`. A tela de prévia passa a renderizar o layout com `<aside class="sidebar">` e topbar consistente. O topo do painel recebe um seletor global de canal conectado à URL (`?project_id=...`) e um modal in-page de cadastro de projetos consumindo `POST /studio/projects`. A esteira do workflow é destacada com cartões semânticos de pipeline. A listagem de vídeos adota cards modernos com miniaturas e botões de ação rápida. A seção de tendências exibe os virais de forma compacta com expansor interativo, evitando a rolagem infinita.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL / psycopg3, Vanilla CSS/JS com CSP Nonce estrito, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-dashboard-ux-projects-and-workflow-redesign.md`

## Global Constraints
- Python 3.12 com tipagem estrita, sem dependências frontend externas.
- Cores neutras oficiais do YouTube: fundo `#0f0f0f`, superfícies `#181818`/`#212121`, bordas `#282828`. Zero tons azul-marinho (`#0b111e`).
- Barra lateral unificada: `/studio/panel` e `/studio/videos/{id}/preview` compartilham a mesma identidade de navegação.
- Segurança CSP: 100% de scripts e estilos utilizam `nonce="{nonce}"`. Zero inline scripts/styles sem nonce.
- Zero XSS: Toda interpolação no backend usa `e(...)` (`html.escape`). Toda manipulação no frontend usa `textContent` e APIs seguras de DOM. Zero `innerHTML` com dados externos.
- Preservar integridade dos testes de regressão existentes (`tests/test_panel_page.py`, `tests/test_panel.py`, `tests/test_publishing.py`, etc.).

## Review Focus
1. A tela de prévia de vídeo (`/studio/videos/{id}/preview`) deve conter a barra lateral com menu completo sem quebrar a reprodução do vídeo ou o formulário de aprovação/rejeição.
2. Seletor de canal no topo do painel deve preservar os filtros de período (`days=7|14|30`) ao alternar de projeto.
3. Cadastro de novo projeto via modal deve validar nome entre 1 e 120 caracteres e redirecionar para o novo canal criado com feedback imediato.
4. Se o banco não tiver nenhum projeto cadastrado, o painel deve exibir estado vazio amigável convidando a cadastrar o primeiro projeto sem quebrar os selects.
5. O expansor de tendências deve alternar suavemente a visibilidade dos cards excedentes sem recarregar a página e sem quebrar os filtros de pílulas.

---

### Task 1: Neutral YouTube Studio Dark Palette & Global CSS Variables (Panel & Preview)

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Modify: `renderer/app/studio/api/preview.py`
- Test: `tests/test_panel_page.py`
- Test: `tests/test_publishing.py`

**Interfaces:**
- Produces: CSS `:root` com variáveis neutras do YouTube Studio: `--bg: #0f0f0f; --surface: #181818; --surface-alt: #212121; --border: #282828; --text: #f1f1f1; --text-muted: #aaaaaa;` no painel e na prévia
- Consumes: Estrutura HTML do painel e da prévia

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

```python
def test_panel_and_preview_use_neutral_youtube_dark_theme(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "--bg: #0f0f0f" in r.text
    assert "--surface: #181818" in r.text
    assert "#0b111e" not in r.text  # no navy blue tint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_and_preview_use_neutral_youtube_dark_theme`
Expected: FAIL

- [ ] **Step 3: Update CSS variables and theme styles in `panel.py` and `preview.py`**

Substituir `--bg: #0b111e`, `--surface: #131d31`, `--border: #1e293b` pelas variáveis neutras do YouTube Studio Dark (`#0f0f0f`, `#181818`, `#212121`, `#282828`) no painel e na tela de prévia.

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py tests/test_publishing.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py renderer/app/studio/api/preview.py tests/test_panel_page.py
git commit -m "style(theme): neutral YouTube Studio dark palette (#0f0f0f / #181818) in panel and preview"
```

---

### Task 2: Project Management UI & Topbar Channel Switcher

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: Topbar channel selector (`#global-project-select`), modal `#project-modal` com formulário de cadastro, chamada a `POST /studio/projects`
- Consumes: `view.projects`, `current_project_id`

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

```python
def test_panel_has_project_selector_and_create_project_modal(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert 'id="global-project-select"' in r.text
    assert 'id="btn-open-project-modal"' in r.text
    assert 'id="project-modal"' in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_has_project_selector_and_create_project_modal`
Expected: FAIL

- [ ] **Step 3: Implement project selector and modal in `renderer/app/studio/api/panel.py`**

1. No topbar: renderizar `<select id="global-project-select">` com as opções de `view.projects` marcando `selected` no projeto ativo. Adicionar botão `+ Novo Projeto` (`#btn-open-project-modal`).
2. Adicionar modal `#project-modal` com campos:
   - Nome do Canal / Projeto (`name`, minlength 1, maxlength 120, required)
   - Nicho editorial (`niche`, opcional)
   - Idioma (`language`, padrão `pt-BR`)
   - Botões Salvar e Cancelar.
3. No script JS:
   - Evento `change` no `#global-project-select` redireciona para `/studio/panel?project_id={id}&days={days}`.
   - Envio do form de projeto para `POST /studio/projects`. Ao concluir com sucesso, redireciona para a página com o novo projeto selecionado.
   - Abertura e fechamento acessível do modal (botão fechar, backdrop e tecla `Escape`).

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): topbar project switcher and in-page project creation modal"
```

---

### Task 3: Unified Sidebar in Preview Page & Workflow Funnel with Modern Video Cards

**Files:**
- Modify: `renderer/app/studio/api/preview.py`
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`
- Test: `tests/test_publishing.py`

**Interfaces:**
- Produces: Barra lateral unificada em `preview.py` (`.sidebar` com logo, links de menu e rodapé com teto), esteira de workflow visual e grid de cards de vídeos modernos
- Consumes: `Preview` model em `preview.py`, `PanelView` em `panel.py`

- [ ] **Step 1: Write the failing tests in `tests/test_publishing.py` and `tests/test_panel_page.py`**

```python
def test_preview_page_renders_sidebar_navigation(client_env):
    # verifies that preview page contains <aside class="sidebar">, links to /studio/panel, and unified header
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_publishing.py::test_preview_page_renders_sidebar_navigation`
Expected: FAIL

- [ ] **Step 3: Implement unified layout in `preview.py` and video cards in `panel.py`**

1. Em `preview.py`:
   - Envolver o conteúdo da tela de prévia no layout de grid do Studio com `<div class="app-layout">`, `<aside class="sidebar">` com menu completo, topbar com breadcrumb `Painel / Prévia de Vídeo` e rodapé.
   - Ajustar estilos CSS da prévia para herdar a barra lateral responsiva.
2. Em `panel.py`:
   - Estruturar a linha executiva de métricas do workflow em cartões de pipeline claros: `Em Produção`, `Aguardando Aprovação`, `Concluídos / Publicados`, `Gasto no Mês vs Teto`.
   - Na seção de vídeos: renderizar os vídeos em cards modernos com miniatura/placeholder 16:9, badge do estágio atual, título, formato (Short/Long) e botões de ação (`Ver Prévia`, `Aprovar`, `Ver Progresso`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py tests/test_publishing.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/preview.py renderer/app/studio/api/panel.py tests/test_publishing.py tests/test_panel_page.py
git commit -m "feat(preview): unified sidebar layout in preview page and modern workflow cards"
```

---

### Task 4: Uncluttered Trends Section (Compact Initial Display & Expansion)

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: Radar de tendências com exibição inicial dos 6 maiores virais e botão interativo `Ver Mais Tendências (+N)` / `Recolher`
- Consumes: `view.trends`

- [ ] **Step 1: Write failing test in `tests/test_panel_page.py`**

```python
def test_panel_trends_has_compact_expansion_toggle(client_env):
    # verifies toggle button presence and data attributes for compact trends view
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_trends_has_compact_expansion_toggle`
Expected: FAIL

- [ ] **Step 3: Implement compact trends view and expansion toggle in `renderer/app/studio/api/panel.py`**

1. Nos cards de tendência: itens além do 6º recebem classe `.trend-item-extra` e ficam ocultos por padrão.
2. Adicionar botão no rodapé do card de tendências: `<button type="button" class="btn btn-compact" id="btn-toggle-more-trends">Ver Mais Tendências (+N)</button>` quando houver mais de 6 itens.
3. No script JS: alternar a visibilidade de `.trend-item-extra` ao clicar no botão, mantendo o respeito ativo aos filtros de pílulas selecionados.

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): compact trends radar with interactive expansion toggle"
```

---

### Task 5: Docker Rebuild, Visual Validation & Docs

**Files:**
- Modify: `docs/18-painel.md`
- Create/Update: `docs/images/painel-dashboard.png`
- Create/Update: `docs/images/painel-preview.png`

**Interfaces:**
- Produces: Container `renderer` reconstruído, screenshots em alta resolução do dashboard e da tela de prévia unificada, documentação atualizada

- [ ] **Step 1: Rebuild renderer container and verify health**

Run: `docker compose up -d --build renderer && sleep 3 && curl -s http://localhost:8000/health`
Expected: `{"status":"ok","ffmpeg":true,"studio_db":"ok"}`

- [ ] **Step 2: Capture updated screenshots with Chrome headless**

Capturar:
1. `docs/images/painel-dashboard.png` (dashboard despoluído com tema YouTube Dark neutro, seletor de canal e pipeline)
2. `docs/images/painel-preview.png` (tela de prévia com menu lateral unificado)

- [ ] **Step 3: Update documentation in `docs/18-painel.md`**

Documentar a navegação unificada na prévia, o seletor de canais, modal de cadastro de novos projetos, esteira de workflow e o novo design despoluído.

- [ ] **Step 4: Run full test suite in test container**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py tests/test_panel.py tests/test_category_api.py tests/test_youtube_popular_trends.py tests/test_category_repo.py tests/test_db.py tests/test_architecture.py tests/test_publishing.py`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add docs/18-painel.md docs/images/
git commit -m "docs: update panel guide and screenshots with unified preview menu and neutral YouTube theme"
```
