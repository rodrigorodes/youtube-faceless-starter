# V3 - Plano 3: Telas e Jornadas UX V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as telas e jornadas da UX V3 do Faceless Studio em `renderer/app/studio/api/`, espelhando fielmente a proposta aprovada no protótipo navegável V3 (`prototype-v4-v3/index.html` e `v3.js`).

**Architecture:**
- Frontend Server-Rendered (Python/FastAPI): Casca `shell_v3.py` com tokens visuais e CSS do Studio.
- Home (`panel_home.py`): Card de criação rápida com seletor "Tenho uma ideia" vs "Já tenho roteiro", padrões do canal e botão contextual de ação.
- Canais (`panel_channels.py`): Criação atômica de canal em tela única com progressive disclosure (`<details>`) para personalização e chamada transacional (`POST /channels/transactional`).
- Workspace do Vídeo (`panel_video_nav.py`, `panel_video_workspace.py`): 5 abas principais (`cenas`, `composicao`, `qualidade`, `publicacao`, `fontes`), link de diagnóstico separado para `producao`, storyboard focado com histórico de narração, aprovação centrada na prévia, agendamento em horário de Brasília (UTC−03:00) e rotulagem honesta dos controles de composição.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, PostgreSQL, HTML5 semântico, CSS moderno (design tokens, color-scheme, dialog nativo, details/summary), Pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-22-v3-decisoes-e-escopo.md` e referência visual em `docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html`.

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção via GitHub.
- Fidelidade visual e semântica estrita à proposta V3 em `prototype-v4-v3/index.html`.
- Respeitar honestidade do produto: custo ausente nunca vira US$ 0,00; controles sem lastro no motor são rotulados "em breve" sem simulação falsa.
- Nenhuma alteração pode quebrar endpoints JSON REST existentes ou migrações do banco de dados.
- Todo JavaScript do cliente deve ser defensivo, sem dependências externas e com degradação graciosa.

## Review Focus

1. **Roteiro pronto colado na Home**: não pode ser tratado como mero tema de prompt; o texto original deve ser preservado e gravado como fonte do vídeo. (Task 1)
2. **Criação de canal**: deve disparar `POST /studio/channels/transactional` enviando todos os dados preenchidos de uma só vez, com feedback claro em caso de erro sem recarregar a página com perda de dados. (Task 2)
3. **Workspace com 5 abas**: rotas legadas (`/visao-geral`, `/narracao`) devem ser mapeadas de forma segura sem 404, e o link de diagnóstico de produção não deve aparecer como aba do menu principal. (Task 3)
4. **Storyboard com cena em foco e histórico de áudio**: restaurar versão de voz anterior não pode sobrescrever o texto atual se divergente, marcando o áudio como desatualizado (`stale`). (Task 4)
5. **Agendamento de publicação**: deve validar fuso horário de Brasília (UTC−03:00) e rejeitar datas passadas, desmarcando estado de publicação imediata. (Task 6)

---

### Task 1: Home V3 (Hero de Criação Rápida com Ideia vs Roteiro)

**Files:**
- Modify: `renderer/app/studio/api/panel_home.py`
- Test: `tests/test_home_v3.py`

**Interfaces:**
- Consumes: `view.project_id`, `view.channels`, `PanelView`
- Produces: Card de criação rápida com:
  - Seletor de entrada: "Tenho uma ideia" (`idea`) e "Já tenho roteiro" (`script`)
  - Placeholder dinâmico e aviso de que parágrafos viram cenas
  - Informação dos padrões do canal ativo (nome, duração, estilo)
  - Botão de ação: "⚡ Gerar vídeo completo" (no piloto) ou "🎬 Abrir storyboard" (no diretor)
  - JavaScript inline enviando POST para `/studio/videos` e, se roteiro, para `/studio/videos/{id}/sources`

- [x] **Step 1: Write failing test in `tests/test_home_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement quick creation card in `renderer/app/studio/api/panel_home.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_home.py tests/test_home_v3.py
git commit -m "feat(studio): atualizar hero da Home com seletor ideia vs roteiro e padroes do canal"
```

---

### Task 2: Criação e Perfil de Canal V3 com Transacionalidade

**Files:**
- Modify: `renderer/app/studio/api/panel_channels.py`
- Test: `tests/test_channels_page.py`
- Create: `tests/test_channels_v3_ux.py`

**Interfaces:**
- Consumes: `POST /studio/channels/transactional`, `GET /studio/channels/{id}`, `PATCH /studio/channels/{id}`
- Produces:
  - Formulário de novo canal com dados essenciais visíveis (nome, nicho, idioma, modo padrão, formato padrão, estilo)
  - Detalhes expansíveis (`<details class="diag">`) para Editorial, Orçamento e Provedores
  - Submissão AJAX chamando `POST /studio/channels/transactional` com feedback inline
  - Painel de perfil existente exibindo e editando `default_mode` e `default_format`

- [x] **Step 1: Write failing test in `tests/test_channels_v3_ux.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement V3 channel creation and profile editing in `panel_channels.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_channels.py tests/test_channels_v3_ux.py
git commit -m "feat(studio): atualizar criacao de canal para fluxo transacional V3"
```

---

### Task 3: Reestruturação da Navegação do Workspace (5 Áreas + Diagnóstico)

**Files:**
- Modify: `renderer/app/studio/api/panel_video_nav.py`
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Create: `tests/test_video_workspace_v3_nav.py`

**Interfaces:**
- Consumes: Rota `/studio/panel/videos/{id}/{area}`
- Produces:
  - 5 abas canônicas: `cenas` ("Cenas & Storyboard"), `composicao` ("Composição & Legendas"), `qualidade` ("Qualidade & Aprovação"), `publicacao` ("Publicação YouTube"), `fontes` ("Fontes & Evidências")
  - Área `producao` acessível via link no cabeçalho ("Ver progresso / Diagnóstico"), sem aparecer no menu de abas principal
  - Normalização segura de URLs legadas (`visao-geral` e `narracao` redirecionando/mapeando para `cenas`)

- [x] **Step 1: Write failing test in `tests/test_video_workspace_v3_nav.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update `panel_video_nav.py` and `panel_video_workspace.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_nav.py renderer/app/studio/api/panel_video_workspace.py tests/test_video_workspace_v3_nav.py
git commit -m "feat(studio): reestruturar navegacao do workspace para 5 abas e diagnostico"
```

---

### Task 4: Storyboard V3 (Cena em Foco, Desfazer/Refazer e Histórico de Áudio)

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Modify: `renderer/app/studio/api/panel_script.py`
- Create: `tests/test_video_storyboard_v3.py`

**Interfaces:**
- Consumes: Cenas do vídeo, narrações, `scene_revisions`
- Produces:
  - Navegação entre cenas (1, 2, 3...) com visualização compacta de uma cena ativa por vez
  - Seletor com `<details>` para expandir e ler o roteiro completo
  - Botões de desfazer e refazer no cabeçalho do storyboard
  - Cartão de cena com ações de regenerar voz, trocar mídia e ver histórico de gerações
  - Diálogo/seção para ouvir versões anteriores e restaurar voz

- [x] **Step 1: Write failing test in `tests/test_video_storyboard_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement V3 storyboard UI in `panel_video_workspace.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_workspace.py renderer/app/studio/api/panel_script.py tests/test_video_storyboard_v3.py
git commit -m "feat(studio): storyboard V3 com cena em foco, desfazer e historico de audio"
```

---

### Task 5: Qualidade & Aprovação V3 (Prévia em Destaque e Verificações Técnicas)

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Create: `tests/test_video_qa_v3.py`

**Interfaces:**
- Consumes: `video.qa_report`, status do vídeo
- Produces:
  - Aba `qualidade` renderizando o player/prévia do vídeo no topo
  - Cartão de resumo de revisão com pendências acionáveis
  - Detalhes expansíveis `<details class="diag">` com o checklist técnico completo
  - Botão de aprovação direcionando o operador para a publicação (`/publicacao`)
  - Disclaimer explícito: QA técnico automatizado não valida fatos do roteiro

- [x] **Step 1: Write failing test in `tests/test_video_qa_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update QA tab in `panel_video_workspace.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_workspace.py tests/test_video_qa_v3.py
git commit -m "feat(studio): aba de qualidade centrada na previa com verificacoes agrupadas"
```

---

### Task 6: Publicação V3 (Agendamento Brasília UTC−03:00 e Revalidação)

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Create: `tests/test_video_publication_v3.py`

**Interfaces:**
- Consumes: Metadados de publicação, canais do YouTube autorizados, status de aprovação
- Produces:
  - Aba `publicacao` com seletor "Publicar agora" vs "Agendar publicação"
  - Campo de agendamento datetime com aviso de Horário de Brasília (UTC−03:00)
  - Validação de data futura no cliente e feedback imediato
  - Cartão de status: "Agendado para [data]" vs "Publicado"
  - Detecção de edições posteriores desarmando a prontidão para publicação

- [x] **Step 1: Write failing test in `tests/test_video_publication_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update publication tab in `panel_video_workspace.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_workspace.py tests/test_video_publication_v3.py
git commit -m "feat(studio): aba de publicacao com agendamento no fuso de Brasilia"
```

---

### Task 7: Composição & Legendas V3 (Honestidade Visual e Rótulos "Em Breve")

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Create: `tests/test_video_composition_v3.py`

**Interfaces:**
- Consumes: Parâmetros de estilo e patch do vídeo
- Produces:
  - Aba `composicao` com controles ativos suportados pelo motor atual (`caption.font_size`, `caption.bottom`, `palette`, `motion`, `music.bpm/seed`)
  - Controles visuais do protótipo V3 destinados ao Plano 2 (posição topo/meio, fonte customizada, transição fade, FPS) claramente rotulados como "Em breve no Plano 2" ou desabilitados, garantindo honestidade

- [x] **Step 1: Write failing test in `tests/test_video_composition_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update composition tab in `panel_video_workspace.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_workspace.py tests/test_video_composition_v3.py
git commit -m "feat(studio): aba de composicao V3 com controles vigentes e rotulos honestos"
```

---

### Task 8: Verificação de Regressão da UX V3 e Testes E2E

**Files:**
- Test: `tests/test_home_v3.py`, `tests/test_channels_page.py`, `tests/test_video_workspace_*.py`, `tests/e2e_ux/`

- [ ] **Step 1: Run all unit and integration UI suites**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_home_v3.py tests/test_channels_v3_ux.py tests/test_video_workspace_*.py tests/test_video_storyboard_v3.py tests/test_video_qa_v3.py tests/test_video_publication_v3.py tests/test_video_composition_v3.py -v`
Expected: Todos passando com zero erros.

- [ ] **Step 2: Run containerized integration suites**

Run: `bash scripts/test-container.sh tests/test_home_v3.py tests/test_channels_page.py tests/test_channel_preferences_api.py`
Expected: Todos passando com código 0.

- [ ] **Step 3: Commit final integration milestone**

```bash
git commit --allow-empty -m "chore: marco do plano 3 - telas e jornadas UX V3 concluidas"
```

---
