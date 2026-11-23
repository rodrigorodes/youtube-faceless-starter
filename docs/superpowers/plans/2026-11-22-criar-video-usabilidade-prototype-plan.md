# Alinhamento da Usabilidade de Criar Vídeo com o Protótipo V3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alinhar a experiência e usabilidade da tela de criação de vídeos (`/studio/panel/novo-video`) ao protótipo canônico (`prototype/index.html:611`), eliminando o wizard burocrático de 3 etapas em favor de criação direta (1 clique para criar e abrir), suportando roteiro colado opcional, duração-alvo, checkbox de revisão e o card educativo "Seu caminho até publicar".

**Architecture:** Modificar `renderer/app/studio/api/panel_new_video.py` para adotar o layout de 2 colunas e fluxo direto do protótipo. O formulário passa a conter tema, formato, duração-alvo, estilo visual, roteiro pronto (opcional) e checkbox de revisão. Na submissão via JS, o vídeo é criado via `POST /studio/videos`; se houver roteiro colado, este é salvo como fonte inicial (`POST /studio/videos/{id}/sources`), e a página redireciona imediatamente para o Workspace do vídeo (`/studio/panel/videos/{id}`), sem etapas de parada.

**Tech Stack:** Python 3.11/3.12, FastAPI, HTML5/CSS3 (design tokens do Studio), JavaScript nativo (sem dependências externas), Playwright E2E.

**Spec:** `docs/backlogs/faceless-visual-evolution 2/prototype/index.html` (linhas 533, 575 e 611).

## Global Constraints

- **Preservar compatibilidade de API:** `POST /studio/videos` continua recebendo `{project_id, topic, format, style_id}`.
- **Roteiro colado preservado:** Quando preenchido, é adicionado como fonte inicial (`POST /studio/videos/{id}/sources`) com URL representativa `local://roteiro-inicial` e texto integral.
- **Redirecionamento imediato:** Criar rascunho deve redirecionar diretamente para o Workspace do vídeo criado (`/studio/panel/videos/{id}`).
- **Layout responsivo:** Duas colunas em desktop/tablet (`.two`) colapsando para coluna única em mobile (390px) sem overflow horizontal.
- **Acessibilidade:** Todos os novos campos com `<label for="...">` explícitos e `:focus-visible` ativo.

## Review Focus

1. **Persistência de roteiro colado:** Operador cola texto com 3 parágrafos; o texto deve ser gravado nas fontes do vídeo e aparecer disponível para a produção.
2. **Fluxo sem paradas:** O botão primário "Criar e abrir vídeo →" não pode travar em telas intermediárias de confirmação.
3. **Canais sem perfil:** Canal que não tem estilo ou voz definidos exibe estado vazio honesto no card de predefinição.
4. **Validação mínima:** Tentativa de envio com tema vazio ou < 3 caracteres deve focar no campo e exibir erro sem recarregar a tela.
5. **Manutenção do canal ativo:** Ao criar o vídeo, o `project_id` selecionado na topbar/URL deve ser preservado.

---

### Task 1: Testes de Unidade e Contrato para a Nova Usabilidade

**Files:**
- Modify: `tests/test_new_video_v3.py`

- [ ] **Step 1: Escrever testes que cobrem os campos e layout do protótipo**
Adicionar testes em `tests/test_new_video_v3.py` para:
- Presença do campo `roteiro-pronto` (`#script` / `#roteiro-pronto`).
- Presença do campo de duração-alvo (`#duracao-alvo`).
- Presença do checkbox de revisão de roteiro (`#revisar-roteiro`).
- Presença do botão de submissão direta "Criar e abrir vídeo →" (`#btn-criar-abrir`).
- Presença do card lateral "Seu caminho até publicar" com os 4 passos.

- [ ] **Step 2: Executar testes e verificar falha (RED)**
Run: `python3 -m pytest tests/test_new_video_v3.py -k "prototype_usability" -v`
Expected: FAIL (campos e novos cards ainda não existem no template).

---

### Task 2: Implementação do Layout e Campos do Protótipo em `panel_new_video.py`

**Files:**
- Modify: `renderer/app/studio/api/panel_new_video.py`

- [ ] **Step 1: Atualizar o HTML do formulário de criação**
Implementar o layout de 2 colunas (`.two`):
- Coluna principal com:
  - Input `#tema-novo` (Qual é o tema?)
  - Seletor lado a lado de Formato (Short 9:16 / Longo 16:9) e Duração-alvo (`#duracao-alvo`, padrão 60s).
  - Textarea `#roteiro-pronto` ("Roteiro pronto (opcional)").
  - Checkbox `#revisar-roteiro` ("Revisar roteiro antes de gerar voz e imagens").
  - Galeria de estilos visuais da biblioteca / herança do canal.
  - Barra de ações com nota "Criar rascunho não inicia geração." e botão primário `#btn-criar-abrir` ("Criar e abrir vídeo →").
- Coluna lateral (`.stack`) com:
  - Card "Predefinição do canal" (estilo, voz, idioma).
  - Card "Seu caminho até publicar" com os 4 passos:
    1. Adicione fontes e revise o roteiro.
    2. Gere narração e monte as cenas.
    3. Ajuste composição e confira a qualidade.
    4. Aprove a versão e prepare a publicação.

- [ ] **Step 2: Atualizar o JavaScript client-side de criação direta**
Ao submeter o formulário:
1. Valida tema (≥ 3 caracteres).
2. Faz `POST /studio/videos` com `{project_id, topic, format, style_id}`.
3. Se `#roteiro-pronto` tiver texto preenchido, faz `POST /studio/videos/{id}/sources` com `{url: "local://roteiro-inicial", text: roteiro}`.
4. Redireciona imediatamente para `location.href = '/studio/panel/videos/' + encodeURIComponent(d.id)`.

- [ ] **Step 3: Executar testes e verificar sucesso (GREEN)**
Run: `python3 -m pytest tests/test_new_video_v3.py -v`
Expected: PASS.

---

### Task 3: Atualização e Validação na Suíte E2E Playwright

**Files:**
- Modify: `tests/e2e_ux/pages/new_video_page.py`
- Modify: `tests/e2e_ux/test_e2e_journey_creation.py`

- [ ] **Step 1: Atualizar Page Object `NewVideoPage`**
Método `create_video_direct(topic, format_choice="short", script="", duration=60)` que preenche os campos e submete em 1 clique.

- [ ] **Step 2: Atualizar teste de jornada `test_journey_create_video_and_open_workspace`**
Verificar:
1. Preenchimento de tema e roteiro colado.
2. Submissão direta com 1 clique no botão "Criar e abrir vídeo →".
3. Redirecionamento direto para o Workspace do vídeo (`/studio/panel/videos/{id}`).
4. Roteiro colado persistido nas fontes do vídeo.

- [ ] **Step 3: Executar a suíte E2E completa**
Run: `bash scripts/run-e2e-tests.sh`
Expected: 22/22 PASSED.

---

### Task 4: Atualização de Documentação e Evidências

**Files:**
- Modify: `docs/superpowers/evidence/2026-11-22-ux-e2e-findings.md`

- [ ] **Step 1: Registrar o alinhamento da usabilidade no relatório de evidências**
- [ ] **Step 2: Validar ausência de regressões no restante do sistema**
Run: `python3 -m pytest tests/test_ux_contract.py tests/test_home_v3.py -v`
Expected: ALL PASSED.
