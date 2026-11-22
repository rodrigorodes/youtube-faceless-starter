# Automação de Testes de UX, Jornadas e Comportamento E2E — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar uma suíte de testes de ponta a ponta (E2E) com Playwright Chromium no host macOS para validar as jornadas críticas de operação (A01–A22), comportamento de DOM vivo (IDs únicos, diálogos, tema, chips) e configurações essenciais do Faceless Studio.

**Architecture:** A suíte reside em `tests/e2e_ux/` utilizando `pytest-playwright` contra o servidor Studio em execução local (`http://localhost:8000`). Os testes utilizam Page Objects semânticos baseados em acessibilidade (`getByRole`, `getByLabel`), helpers de inspeção de DOM (detector de IDs duplicados e overflow horizontal) e fixtures de autenticação HTTP Basic Auth e banco de dados isolado.

**Tech Stack:** Python 3.11/3.12, pytest, pytest-playwright, Chromium, FastAPI/Uvicorn, PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-11-22-ux-e2e-testing-design.md`

## Global Constraints

- **Ambiente de execução:** Host macOS com Playwright Chromium conectando em `http://localhost:8000`.
- **Seletores semânticos:** Usar estritamente papéis e rótulos acessíveis (`getByRole`, `getByLabel`, `getByText`); nunca classes CSS internas voláteis.
- **Fail-Continue:** Falhas em cenários de teste não interrompem a suíte; cada falha é registrada com rastro e print no log de evidências.
- **Zero custo de IA:** Modo de teste utiliza `STUDIO_TEXT=demo`, imagens `placeholder` e voz `piper` local; nenhuma chamada paga a provedores externos.
- **Segurança de credenciais:** Nunca registrar ou exibir tokens, senhas ou segredos em logs ou relatórios de teste.

## Review Focus

1. **Colisão de IDs em modais:** Elementos do diálogo `#dlg-canal` com IDs idênticos aos da página base (ex.: `canal-nome`), fazendo `getElementById` manipular o elemento errado.
2. **Navegação fantasma em itens desabilitados:** Links ou botões indisponíveis que recebem foco ou quebram a navegação por teclado.
3. **Falso `US$ 0,00` em custo ausente:** Telas de prévia ou cards exibindo custo zero quando o provedor não reportou custos.
4. **Invalidação de aprovação em edição:** Editar o texto de uma cena de um vídeo aprovado sem que a aprovação e o gate de publicação sejam invalidados.
5. **Overflow horizontal em mobile:** Elementos com largura fixa gerando barra de rolagem horizontal em viewport de 390px.

---

### Task 1: Instalação de Dependências e Harness E2E

**Files:**
- Create: `tests/e2e_ux/__init__.py`
- Create: `tests/e2e_ux/conftest.py`
- Create: `tests/e2e_ux/helpers.py`
- Create: `tests/e2e_ux/test_e2e_smoke.py`

**Interfaces:**
- Consumes: Studio rodando em `http://localhost:8000`, credenciais em `.env` ou padrão (`test-user:test-browser-password`).
- Produces: Fixture `authenticated_page(page)` com Basic Auth configurado e helpers `assert_no_duplicate_ids(page)`, `assert_no_horizontal_overflow(page)`.

- [ ] **Step 1: Instalar pytest-playwright e binários do Chromium no host**
Run: `pip install pytest-playwright && playwright install chromium`
Expected: Playwright e Chromium instalados com sucesso no ambiente Python do host.

- [ ] **Step 2: Implementar helpers de DOM em `tests/e2e_ux/helpers.py`**
Criar `assert_no_duplicate_ids(page)` e `assert_no_horizontal_overflow(page)`.

- [ ] **Step 3: Implementar fixtures em `tests/e2e_ux/conftest.py`**
Configurar `base_url`, credenciais HTTP Basic Auth e fixture `authenticated_page`.

- [ ] **Step 4: Escrever teste de smoke em `tests/e2e_ux/test_e2e_smoke.py`**
Verificar carregamento da página inicial (`/studio/panel`), status 200 e ausência de IDs duplicados.

- [ ] **Step 5: Executar o teste de smoke**
Run: `pytest tests/e2e_ux/test_e2e_smoke.py -v`
Expected: PASS com título e layout da casca renderizados.

---

### Task 2: Page Objects Básicos e Validação da Casca V3 (Shell)

**Files:**
- Create: `tests/e2e_ux/pages/base_page.py`
- Create: `tests/e2e_ux/test_e2e_shell_navigation.py`

**Interfaces:**
- Consumes: Playwright `Page`.
- Produces: `BasePage` com métodos `navigate_to(section_name)`, `switch_channel(channel_name)`, `toggle_theme()`, `get_active_nav_item()`.

- [ ] **Step 1: Implementar `BasePage` em `tests/e2e_ux/pages/base_page.py`**
Mapear os 7 itens canônicos: `Início`, `Criar vídeo`, `Vídeos`, `Tendências e ideias`, `Desempenho`, `Biblioteca`, `Configurações`.

- [ ] **Step 2: Escrever testes de navegação e tema em `tests/e2e_ux/test_e2e_shell_navigation.py`**
Testar transição entre as seções, marcação de `aria-current="page"` e alternância de tema no `#theme-toggle`.

- [ ] **Step 3: Executar testes da casca**
Run: `pytest tests/e2e_ux/test_e2e_shell_navigation.py -v`
Expected: PASS.

---

### Task 3: Jornada J1 — Onboarding, Criação de Canal e Novo Vídeo (A01, A03, A33)

**Files:**
- Create: `tests/e2e_ux/pages/channels_page.py`
- Create: `tests/e2e_ux/pages/new_video_page.py`
- Create: `tests/e2e_ux/test_e2e_journey_creation.py`

**Interfaces:**
- Consumes: `BasePage`.
- Produces: `ChannelsPage` e `NewVideoPage`.

- [ ] **Step 1: Implementar `ChannelsPage` e `NewVideoPage`**
Métodos para preencher o diálogo `#dlg-canal` e o formulário de novo vídeo com tema e roteiro colado.

- [ ] **Step 2: Escrever teste da Jornada J1 em `test_e2e_journey_creation.py`**
Fluxo: Criar novo canal "Canal E2E Teste" → Verificar seleção ativa → Abrir "Criar vídeo" → Preencher tema "Evolução da Arquitetura" → Colar roteiro de 3 cenas → Submeter.
Verificar: Vídeo criado na lista com status pendente e título correto.

- [ ] **Step 3: Executar teste da Jornada J1**
Run: `pytest tests/e2e_ux/test_e2e_journey_creation.py -v`
Expected: PASS.

---

### Task 4: Jornada J2 — Workspace, Edição por Cena e Invalidação de Render (A06, A07, A08)

**Files:**
- Create: `tests/e2e_ux/pages/workspace_page.py`
- Create: `tests/e2e_ux/test_e2e_journey_workspace.py`

**Interfaces:**
- Consumes: ID do vídeo criado na Task 3 ou fixture de vídeo.
- Produces: `WorkspacePage` com métodos para alternar abas (`Conteúdo`, `Edição`, `Publicação`), selecionar cena, alterar texto de narração e salvar.

- [ ] **Step 1: Implementar `WorkspacePage` em `tests/e2e_ux/pages/workspace_page.py`**
Interações com lista de cenas, `textarea` da narração e botão de salvar.

- [ ] **Step 2: Escrever teste de edição e invalidação em `test_e2e_journey_workspace.py`**
Fluxo: Abrir workspace do vídeo → Ir para aba Edição → Alterar texto da Cena 2 → Salvar.
Verificar: Indicação de cena pendente de renderização / atualização necessária; integridade dos IDs das demais cenas.

- [ ] **Step 3: Executar teste da Jornada J2**
Run: `pytest tests/e2e_ux/test_e2e_journey_workspace.py -v`
Expected: PASS.

---

### Task 5: Jornada J3 — Revisão, Gates e Aprovação Atômica (A17, A18, A21)

**Files:**
- Create: `tests/e2e_ux/pages/preview_page.py`
- Create: `tests/e2e_ux/test_e2e_journey_approval.py`

**Interfaces:**
- Consumes: Vídeo com render pronto.
- Produces: `PreviewPage` com métodos `get_qa_badges()`, `approve_video()`, `reject_video()`.

- [ ] **Step 1: Implementar `PreviewPage` em `tests/e2e_ux/pages/preview_page.py`**
Mapear botões de aprovar/rejeitar vinculados atomicamente ao `render_id` e badges de QA.

- [ ] **Step 2: Escrever teste de aprovação em `test_e2e_journey_approval.py`**
Fluxo: Acessar página de prévia → Verificar checklist de QA (técnico aprovado, custo honesto sem `US$ 0,00`) → Clicar em Aprovar.
Verificar: Transição de estado para Aprovado; edição subsequente invalida aprovação.

- [ ] **Step 3: Executar teste da Jornada J3**
Run: `pytest tests/e2e_ux/test_e2e_journey_approval.py -v`
Expected: PASS.

---

### Task 6: Configurações — Canais, Produção/Orçamento e Equipe

**Files:**
- Create: `tests/e2e_ux/pages/settings_page.py`
- Create: `tests/e2e_ux/test_e2e_settings.py`

**Interfaces:**
- Consumes: Rotas `/studio/canais`, `/studio/configuracoes/producao`, `/studio/panel/equipe`.
- Produces: `SettingsPage`.

- [ ] **Step 1: Implementar `SettingsPage` em `tests/e2e_ux/pages/settings_page.py`**
Acesso às 7 seções, seleção de cartões de perfil econômico (`fieldset[name="economic_profile"]`), tabela de papéis da equipe.

- [ ] **Step 2: Escrever testes de configurações em `test_e2e_settings.py`**
Verificar:
1. Troca do perfil econômico para "Econômico" / "Equilibrado" via cartões clicáveis e persistência.
2. Presença da matriz de papéis (Owner, Editor, Reviewer, Viewer) com permissões canônicas.
3. Ausência de IDs duplicados em todas as seções de configuração.

- [ ] **Step 3: Executar testes de configurações**
Run: `pytest tests/e2e_ux/test_e2e_settings.py -v`
Expected: PASS.

---

### Task 7: Comportamento de DOM, Radar de Tendências e Responsividade (390px, 768px, 1280px)

**Files:**
- Create: `tests/e2e_ux/test_e2e_dom_behavior.py`
- Create: `tests/e2e_ux/test_e2e_responsive.py`

**Interfaces:**
- Consumes: `authenticated_page` com viewports configurados (390x844, 768x1024, 1280x800).

- [ ] **Step 1: Escrever teste de filtros de Tendências em `test_e2e_dom_behavior.py`**
Clicar nas pílulas de filtro ("Todas", "Em Alta Brasil", "Em Alta Mundo") e validar que a lista de cards é filtrada instantaneamente sem reload de página.

- [ ] **Step 2: Escrever testes de responsividade em `test_e2e_responsive.py`**
Carregar Início, Workspace e Configurações nos viewports de 390px, 768px e 1280px.
Verificar: `assert_no_horizontal_overflow(page)` passa em todos os tamanhos; sidebar colapsa corretamente em mobile.

- [ ] **Step 3: Executar testes de DOM e responsividade**
Run: `pytest tests/e2e_ux/test_e2e_dom_behavior.py tests/e2e_ux/test_e2e_responsive.py -v`
Expected: PASS.

---

### Task 8: Runner Script, Triage e Relatório Consolidado de Achados

**Files:**
- Create: `scripts/run-e2e-tests.sh`
- Create: `docs/superpowers/evidence/2026-11-22-ux-e2e-findings.md`

- [ ] **Step 1: Criar script `scripts/run-e2e-tests.sh`**
Script bash executável aceitando `--headed` para visualização e passando opções de relatório.

- [ ] **Step 2: Executar a suíte E2E completa**
Run: `bash scripts/run-e2e-tests.sh`
Expected: Todos os cenários executados com status detalhado.

- [ ] **Step 3: Documentar achados e melhorias em `2026-11-22-ux-e2e-findings.md`**
Registrar bugs descobertos, tempos de resposta, métricas de cliques e correções efetuadas.
