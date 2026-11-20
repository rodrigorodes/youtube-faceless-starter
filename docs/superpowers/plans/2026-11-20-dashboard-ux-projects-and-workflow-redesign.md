# Dashboard UX, Neutral YouTube Theme & Project Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o painel em um Dashboard Executivo moderno com Tema YouTube Studio Dark Neutro (`#0f0f0f`), gestão e alternância de projetos/canais na interface, esteira visual de produção do workflow, cards de vídeos aprimorados e radar de tendências compacto e despoluído.

**Architecture:** A camada de apresentação (`api/panel.py`) adota a paleta YouTube Dark neutra em `:root`. O topo da interface recebe um seletor global de canal conectado à URL (`?project_id=...`) e um modal in-page de cadastro de projetos consumindo `POST /studio/projects`. A esteira do workflow é destacada com cartões semânticos de pipeline. A listagem de vídeos adota cards modernos com miniaturas e botões de ação rápida. A seção de tendências exibe os virais de forma compacta com expansor interativo, evitando a rolagem infinita.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL / psycopg3, Vanilla CSS/JS com CSP Nonce estrito, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-dashboard-ux-projects-and-workflow-redesign.md`

## Global Constraints
- Python 3.12 com tipagem estrita, sem dependências frontend externas.
- Cores neutras oficiais do YouTube: fundo `#0f0f0f`, superfícies `#181818`/`#212121`, bordas `#282828`. Zero tons azul-marinho (`#0b111e`).
- Segurança CSP: 100% de scripts e estilos utilizam `nonce="{nonce}"`. Zero inline scripts/styles sem nonce.
- Zero XSS: Toda interpolação no backend usa `e(...)` (`html.escape`). Toda manipulação no frontend usa `textContent` e APIs seguras de DOM. Zero `innerHTML` com dados externos.
- Preservar integridade dos testes de regressão existentes (`tests/test_panel_page.py`, `tests/test_panel.py`, etc.).

## Review Focus
1. Seletor de canal no topo deve preservar os filtros de período (`days=7|14|30`) ao alternar de projeto.
2. Cadastro de novo projeto via modal deve validar nome entre 1 e 120 caracteres e redirecionar para o novo canal criado com feedback imediato.
3. Se o banco não tiver nenhum projeto cadastrado, o painel deve exibir estado vazio amigável convidando a cadastrar o primeiro projeto sem quebrar os selects.
4. O expansor de tendências deve alternar suavemente a visibilidade dos cards excedentes sem recarregar a página e sem quebrar os filtros de pílulas.
5. Todos os novos modais e elementos devem fechar adequadamente com tecla `Escape` e clique no backdrop.

---

### Task 1: Neutral YouTube Studio Dark Palette & Global CSS Variables

**Files:**
- Modify: `renderer/app/studio/api/panel.py:125-240`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: CSS `:root` com variáveis neutras do YouTube Studio: `--bg: #0f0f0f; --surface: #181818; --surface-alt: #212121; --border: #282828; --text: #f1f1f1; --text-muted: #aaaaaa;`
- Consumes: Estrutura HTML do painel

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

```python
def test_panel_uses_neutral_youtube_dark_theme(client_env):
    client = client_env["client"]
    r = client.get("/studio/panel", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert "--bg: #0f0f0f" in r.text
    assert "--surface: #181818" in r.text
    assert "#0b111e" not in r.text  # no navy blue tint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_uses_neutral_youtube_dark_theme`
Expected: FAIL

- [ ] **Step 3: Update CSS variables and theme styles in `renderer/app/studio/api/panel.py`**

Substituir `--bg: #0b111e`, `--surface: #131d31`, `--border: #1e293b` pelas variáveis neutras do YouTube Studio Dark (`#0f0f0f`, `#181818`, `#212121`, `#282828`). Atualizar os componentes da barra lateral e topbar para usar a nova paleta.

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "style(panel): neutral YouTube Studio dark palette (#0f0f0f / #181818)"
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

### Task 3: Workflow Pipeline Funnel & Modern Video Sample Cards

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: Visual pipeline cards da esteira de workflow (`.workflow-pipeline`), grid de cards de vídeos (`.video-sample-card`) com status, formato, duração e ações
- Consumes: `view.totals`, `view.topics`, `view.month`

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

```python
def test_panel_renders_workflow_pipeline_and_video_cards(client_env):
    # verifies presence of workflow pipeline stages and modern video sample cards
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_renders_workflow_pipeline_and_video_cards`
Expected: FAIL

- [ ] **Step 3: Implement workflow funnel and video cards markup in `renderer/app/studio/api/panel.py`**

1. Estruturar a linha executiva de métricas do workflow em cartões de pipeline claros:
   - `Em Produção (Render/IA)` com indicador azul
   - `Aguardando Aprovação` com indicador âmbar
   - `Concluídos / Publicados` com indicador verde
   - `Gasto no Mês vs Teto` com indicador lilás
2. Na seção de vídeos:
   - Renderizar os vídeos em cards modernos com:
     - Placeholder/miniatura 16:9 (`.video-thumb-sample`)
     - Badge do estágio atual do workflow (`Aguardando Aprovação`, `Em Produção`, `Concluído`)
     - Título do vídeo
     - Metadados: formato (Short/Long), data de atualização, custo
     - Botões de ação contextuais (`Ver Prévia`, `Aprovar`, `Ver Progresso`)

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): workflow pipeline funnel and modern video sample cards"
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

**Interfaces:**
- Produces: Container `renderer` reconstruído, screenshots em alta resolução e documentação operacional completa

- [ ] **Step 1: Rebuild renderer container and verify health**

Run: `docker compose up -d --build renderer && sleep 3 && curl -s http://localhost:8000/health`
Expected: `{"status":"ok","ffmpeg":true,"studio_db":"ok"}`

- [ ] **Step 2: Capture updated screenshots with Chrome headless**

Capturar `docs/images/painel-dashboard.png` com o novo visual YouTube Studio Dark neutro, seletor de canais e esteira de workflow.

- [ ] **Step 3: Update documentation in `docs/18-painel.md`**

Documentar o seletor de canais, modal de cadastro de novos projetos, esteira de workflow e o novo design despoluído.

- [ ] **Step 4: Run full test suite in test container**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py tests/test_panel.py tests/test_category_api.py tests/test_youtube_popular_trends.py tests/test_category_repo.py tests/test_db.py tests/test_architecture.py`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add docs/18-painel.md docs/images/painel-dashboard.png
git commit -m "docs: update panel guide and screenshot with neutral YouTube theme and project management"
```
