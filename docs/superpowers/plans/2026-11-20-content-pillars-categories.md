# Content Pillars & Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o cadastro e gerenciamento de categorias fixas (pilares de conteúdo) por projeto e a filtragem/atualização de tendências do YouTube diretamente no painel web.

**Architecture:** Uma nova tabela e repositório (`studio.project_categories`) gerenciam os pilares e suas palavras-chave por projeto. Endpoints REST permitem listar, salvar e excluir categorias, além de disparar a busca ao vivo na YouTube Data API (`/trends/refresh`). O painel web exibe pílulas de filtro dinâmicas, modal de gerenciamento e botão de atualização em um clique com proteção CSP e sanitização estrita.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL (Psycopg 3), Vanilla HTML/CSS/JS com CSP nonce, YouTube Data API v3.

**Spec:** `docs/superpowers/specs/2026-11-20-content-pillars-categories-design.md`

## Global Constraints

- Python 3.12 com tipagem estrita e sem dependências extras de frontend.
- Migrações incrementais numeradas em `renderer/app/studio/adapters/postgres/migrations/`.
- Sanitização rigorosa via `html.escape` em todo texto inserido no HTML do painel.
- CSP estrita: apenas scripts e estilos com o `nonce` gerado por requisição.
- Nenhuma chave ou segredo exposta no navegador ou no repositório Git.

## Review Focus

1. **Nome de categoria duplicado no mesmo projeto:** Banco e API devem recusar com HTTP 409 ou mensagem clara sem corromper estado.
2. **Termos de busca vazios ou excessivos:** Sanitizar lista de termos, ignorar itens em branco e limitar a no máximo 10 termos por pilar para preservar cota.
3. **Projeto sem categorias:** O painel deve exibir estado vazio amigável nas pílulas sem quebrar a renderização.
4. **Falha na chave da YouTube Data API durante refresh:** Endpoint de refresh deve retornar erro legível (ex: 502/400) com mensagem clara sem travar o painel.
5. **Remoção de categoria associada a tendências:** `ON DELETE SET NULL` na chave estrangeira para não apagar histórico de tendências.

---

### Task 1: Migração do Banco de Dados e Teste de Schema

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0012_categories.sql`
- Modify: `tests/test_db.py:25,37`

**Interfaces:**
- Produces: Tabela `studio.project_categories` com colunas `id`, `project_id`, `name`, `queries`, `created_at`, `updated_at` e coluna `category_id` em `studio.trend_topics`.

- [ ] **Step 1: Write the failing test**

Atualizar `tests/test_db.py` para incluir `"0012_categories"` na lista de migrações esperadas.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL com diferença na lista de migrações.

- [ ] **Step 3: Implement `0012_categories.sql`**

Criar a tabela `studio.project_categories` e adicionar `category_id` em `studio.trend_topics`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/postgres/migrations/0012_categories.sql tests/test_db.py
git commit -m "feat(db): add 0012_categories migration for project content pillars"
```

---

### Task 2: Modelo de Domínio e Repositório de Categorias

**Files:**
- Create: `renderer/app/studio/domain/categories.py`
- Create: `renderer/app/studio/adapters/postgres/category_repo.py`
- Test: `tests/test_category_repo.py`

**Interfaces:**
- Produces: `ProjectCategory(id, project_id, name, queries, created_at, updated_at)` e `PostgresCategoryRepository(list, get, save, delete)`.

- [ ] **Step 1: Write the failing test in `tests/test_category_repo.py`**

Testar criação, listagem, atualização de termos e exclusão de categoria por projeto.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_category_repo.py -v`
Expected: FAIL com módulo não encontrado.

- [ ] **Step 3: Implement domain e repository**

Criar `ProjectCategory` e `PostgresCategoryRepository` com suporte a listagem e exclusão segura.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_category_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/categories.py renderer/app/studio/adapters/postgres/category_repo.py tests/test_category_repo.py
git commit -m "feat(categories): domain model and postgres repository for content pillars"
```

---

### Task 3: Casos de Uso e Endpoints REST de Categorias e Refresh

**Files:**
- Create: `renderer/app/studio/application/categories.py`
- Modify: `renderer/app/studio/application/use_cases.py`
- Modify: `renderer/app/studio/composition.py`
- Modify: `renderer/app/studio/api/routes.py`
- Test: `tests/test_category_api.py`

**Interfaces:**
- Produces: Endpoints `GET /studio/projects/{id}/categories`, `POST /studio/projects/{id}/categories`, `DELETE /studio/projects/{id}/categories/{cat_id}` e `POST /studio/projects/{id}/trends/refresh`.

- [ ] **Step 1: Write the failing test in `tests/test_category_api.py`**

Testar CRUD de categorias e recusa com 409 quando nome duplicado.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_category_api.py -v`
Expected: FAIL com rotas não encontradas.

- [ ] **Step 3: Implement endpoints e injeção de dependência**

Adicionar rotas no `make_router` e conectar ao `UseCases`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_category_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/application/categories.py renderer/app/studio/application/use_cases.py renderer/app/studio/composition.py renderer/app/studio/api/routes.py tests/test_category_api.py
git commit -m "feat(api): endpoints for managing categories and refreshing live trends"
```

---

### Task 4: Atualização do Painel Web (Pílulas de Filtro e Modal de Gerenciamento)

**Files:**
- Modify: `renderer/app/studio/application/panel.py`
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Consumes: Categorias em `PanelView` e dados de pilar em `TrendItemView`.
- Produces: Pílulas de filtro dinâmicas, modal interativo e botões "Buscar Agora" e "Gerenciar Categorias".

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

Testar presença da barra de categorias, modal de gerenciamento e botão de refresh.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_panel_page.py -v`
Expected: FAIL com elementos ausentes.

- [ ] **Step 3: Implement UI de categorias no `panel.py`**

Adicionar as pílulas, estilos de modal, handlers JS e integração com a API de categorias.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_panel_page.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/application/panel.py renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): category pills filter, management modal and live refresh button"
```

---

### Task 5: Validação Visual no Navegador e Atualização da Documentação

**Files:**
- Modify: `docs/18-painel.md`
- Modify: `docs/19-tendencias.md`
- Capture: `docs/images/painel-dashboard.png`

**Interfaces:**
- Produces: Capturas atualizadas das categorias no painel e documentação operacional completa.

- [ ] **Step 1: Executar migração e recriar o container do renderer**

Comando: `docker compose up -d --build renderer`
Verificar saúde: `curl http://localhost:8000/health` -> `status: ok`.

- [ ] **Step 2: Capturar screenshot da nova tela do painel com Chrome headless**

Verificar visual das pílulas e modal.

- [ ] **Step 3: Executar a suíte completa de testes de regressão**

Comando: `~/.yfs-test.sh tests/test_panel_page.py tests/test_panel.py tests/test_category_api.py tests/test_db.py`
Expected: Todos verdes.

- [ ] **Step 4: Commit e merge na branch `main`**

```bash
git add docs/18-painel.md docs/19-tendencias.md docs/images/
git commit -m "docs: update panel guide and screenshots with content pillars"
```
