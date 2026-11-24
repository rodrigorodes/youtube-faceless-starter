# Onda 4 — UX Studio: Reuso da UX V3, Bancada da Cena & Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar os motores das Ondas 1 a 3 (RenderPlan v2 multi-shot, CreativeDirector, PacingEngine, AudioDirector ducking e legendas ASS) na interface web da UX V3 do Faceless Studio, sem criar telas novas e preservando a fidelidade aos mockups aprovados.

**Architecture:**
- Persistência e Domínio: Migração aditiva `0052` estendendo `studio.videos` com `target_duration_s`, `pacing_preset`, `budget_cap_usd` e `creative_brief`, com contratos tipados imutáveis em `domain/contracts.py`.
- Módulo A (Novo Vídeo): Formulário único enviando `pacing_preset` (dinâmico/balanceado/cinemático), meta de duração e teto de orçamento com resumo visual em tempo real.
- Módulo B (Direção Criativa): Nova aba `direcao` em `VIDEO_AREAS` exibindo e permitindo editar/regenerar o `CreativeBrief` via rotas dedicadas no workspace.
- Módulo C (Bancada da Cena): Cards do storyboard exibindo tomadas multi-asset (`studio.scene_assets`), controle de ritmo por cena, botão de adicionar mídia e pílula de tomadas no dock.
- Módulo D (Download e Resumo): Rota de download direto do MP4 aprovado com `Content-Disposition`, cartão de resumo audiovisual (mídia, ducking, karaokê, licenças CC0) e ativação dos controles de mixagem e legendas ASS na Composição.

**Tech Stack:** Python 3.11+, FastAPI / Starlette, HTML/CSS nativos (UX V3 protótipo), PostgreSQL, Pydantic v2, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-onda4-ux-studio-design.md` e mockups em `docs/superpowers/mockups/onda4/index.html`.

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub.
- Clean Architecture: `domain/` sem I/O, adapters isolados, rotas e painéis sem chamadas diretas de banco fora dos repositórios.
- UX: Ajustes estritamente sobre as telas existentes da UX V3; proibido criar telas ou rotas de navegação fora da casca existente.
- Testes exclusivamente no contêiner: `TMPDIR=/tmp scripts/test-container.sh <testes> -q`.
- Preservar integridade dos 468+ testes existentes das Ondas 0 a 3.

## Review Focus

1. **Persistência retrocompatível no `CreateVideo`**: Criação de vídeos sem novos parâmetros deve manter os padrões exatos (`pacing_preset='dynamic'`, `target_duration_s=None`, `budget_cap_usd=None`, `creative_brief=None`).
2. **Serialização e Sanitização do Briefing Criativo**: A rota `POST /studio/videos/{id}/direction` deve validar a estrutura do `CreativeBrief` e escapar HTML ao renderizar a aba de Direção Criativa.
3. **Integridade de `scene_assets` no Storyboard**: Adicionar ou remover tomadas de uma cena deve manter a sequência de `position` e garantir `end_s > start_s` sem corromper o cálculo de pacing.
4. **Download do MP4 com Header Correto**: `GET /studio/videos/{id}/download` deve retornar 404 se o vídeo não estiver em status aprovado/renderizado e fornecer `Content-Disposition: attachment; filename="..."` com `media_type="video/mp4"`.
5. **Ativação dos Controles na Composição**: O seletor de legendas `destaque` e o switch de ducking não podem mais ter a classe ou atributo `disabled` na Composição, refletindo o motor de legendas ASS e mixagem já entregues na Onda 3.

---

### Task 1: Banco de Dados, Contratos e Persistência de Produção (Fundação)

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0052_video_production_settings.sql`
- Modify: `renderer/app/studio/domain/contracts.py:83-100`
- Modify: `renderer/app/studio/adapters/postgres/repo.py:237-270`
- Modify: `renderer/app/studio/application/ports.py:121-135`
- Modify: `renderer/app/studio/application/use_cases.py:60-85`
- Create: `tests/test_video_production_persistence.py`

**Interfaces:**
- Produces:
  - `0052_video_production_settings.sql`: colunas `target_duration_s integer`, `pacing_preset text DEFAULT 'dynamic'`, `budget_cap_usd numeric(8,2) DEFAULT NULL`, `creative_brief jsonb DEFAULT NULL` em `studio.videos`.
  - `domain/contracts.py::Video`: novos campos `target_duration_s: int | None = None`, `pacing_preset: str = 'dynamic'`, `budget_cap_usd: float | None = None`, `creative_brief: dict | None = None`.
  - `application/ports.py::VideoRepository`:
    - `create_video(..., target_duration_s: int | None = None, pacing_preset: str = 'dynamic', budget_cap_usd: float | None = None)`
    - `update_video_creative_brief(video_id: str, brief_dict: dict) -> None`
    - `update_video_pacing_preset(video_id: str, preset: str) -> None`
  - `adapters/postgres/repo.py`: implementação em `PostgresVideoRepository`.

- [ ] **Step 1: Write failing test in `tests/test_video_production_persistence.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement migration and repo updates**
  Create migration `0052`, update `domain/contracts.py`, `application/ports.py`, `application/use_cases.py`, and `adapters/postgres/repo.py`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/postgres/migrations/0052_video_production_settings.sql renderer/app/studio/domain/contracts.py renderer/app/studio/application/ports.py renderer/app/studio/application/use_cases.py renderer/app/studio/adapters/postgres/repo.py tests/test_video_production_persistence.py
  git commit -m "feat(persistence): adicionar suporte a parametros de producao e creative brief em studio.videos"
  ```

---

### Task 2: Módulo A — Novo Vídeo com Parâmetros Ativos

**Files:**
- Modify: `renderer/app/studio/api/panel_new_video.py`
- Modify: `renderer/app/studio/api/routes.py:191-203,1326-1340`
- Create: `tests/test_panel_new_video_active.py`

**Interfaces:**
- Consumes: Task 1 (`create_video` com novos campos).
- Produces:
  - `api/routes.py::VideoIn`: campos opcionais `target_duration_s: int | None = None`, `pacing_preset: str = "dynamic"`, `budget_cap_usd: float | None = None`.
  - `api/panel_new_video.py`:
    - Campos de formulário: `name="pacing"` (Dinâmico / Balanceado / Cinemático), `name="target_duration_s"` / `id="duracao-alvo"`, `id="teto-custo"` (opcional).
    - `NEW_VIDEO_JS`: envia esses valores no payload de `fetch('/studio/videos')`.
    - Resumo lateral atualiza em tempo real: Duração alvo, Ritmo de cortes, Teto de custo.

- [ ] **Step 1: Write failing test in `tests/test_panel_new_video_active.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_new_video_active.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement form fields, JS submit and route endpoints**
  Update `api/panel_new_video.py` and `api/routes.py`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_new_video_active.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/api/panel_new_video.py renderer/app/studio/api/routes.py tests/test_panel_new_video_active.py
  git commit -m "feat(ux): conectar ritmo, duracao alvo e teto de custo na criacao de video"
  ```

---

### Task 3: Módulo B — Aba Direção Criativa & Endpoints do Briefing

**Files:**
- Modify: `renderer/app/studio/api/panel_video_nav.py:12-40`
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Modify: `renderer/app/studio/api/routes.py`
- Create: `tests/test_panel_direction_tab.py`

**Interfaces:**
- Consumes: Task 1 (`update_video_creative_brief`, `Video.creative_brief`), `CreateCreativeBrief` da Onda 2.
- Produces:
  - `api/panel_video_nav.py`: constante `VIDEO_AREAS` com aba `("direcao", "Direção")`.
  - `api/panel_video_workspace.py`: renderizador `_area_direcao` exibindo seções do briefing (gancho, objetivo narrativo, estrutura, tom, ritmo, direção visual, orientação de áudio, mídias e critérios), botão `↻ Regenerar briefing` e `Salvar ajustes do briefing`.
  - `api/routes.py`:
    - `GET /studio/videos/{id}/direction`: retorna `{ "brief": ... }`.
    - `POST /studio/videos/{id}/direction`: executa `CreateCreativeBrief` a partir do tópico e contexto do canal, grava no vídeo e retorna o brief.
    - `PUT /studio/videos/{id}/direction`: recebe briefing editado e atualiza no vídeo.

- [ ] **Step 1: Write failing test in `tests/test_panel_direction_tab.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_direction_tab.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement navigation tab, direction area renderer and endpoints**
  Update `api/panel_video_nav.py`, `api/panel_video_workspace.py`, and `api/routes.py`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_direction_tab.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/api/panel_video_nav.py renderer/app/studio/api/panel_video_workspace.py renderer/app/studio/api/routes.py tests/test_panel_direction_tab.py
  git commit -m "feat(ux): implementar aba Direcao Criativa no workspace e rotas de briefing"
  ```

---

### Task 4: Módulo C — Bancada da Cena & Múltiplos Assets

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Modify: `renderer/app/studio/api/panel_video_storyboard_js.py`
- Modify: `renderer/app/studio/adapters/postgres/editorial_repo.py`
- Modify: `renderer/app/studio/api/routes.py`
- Create: `tests/test_panel_scene_multimedia.py`

**Interfaces:**
- Consumes: `0050_scene_assets.sql`, `SceneAsset`, `PacingEngine`.
- Produces:
  - `adapters/postgres/editorial_repo.py`: métodos para gerenciar `scene_assets` (`list_scene_assets(scene_id)`, `add_scene_asset(scene_asset)`, `delete_scene_asset(asset_id)`).
  - `api/panel_video_workspace.py` (`_scene_card`): bloco visual "TOMADAS DESTA CENA" com lista de tomadas (thumbnail gradiente/asset, duração em segundos, tipo de movimento e fonte), botão `+ Adicionar mídia` e seletor de ritmo da cena.
  - Dock inferior do storyboard: pílula `⚡ Dinâmico · N tomadas`.
  - `api/routes.py`: rotas de CRUD para `scene_assets` da cena.

- [ ] **Step 1: Write failing test in `tests/test_panel_scene_multimedia.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_scene_multimedia.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement scene assets management, UI components and endpoints**
  Update `adapters/postgres/editorial_repo.py`, `api/panel_video_workspace.py`, `api/panel_video_storyboard_js.py`, and `api/routes.py`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_scene_multimedia.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/postgres/editorial_repo.py renderer/app/studio/api/panel_video_workspace.py renderer/app/studio/api/panel_video_storyboard_js.py renderer/app/studio/api/routes.py tests/test_panel_scene_multimedia.py
  git commit -m "feat(ux): bancada da cena com tomadas multishot e gerenciamento de scene_assets"
  ```

---

### Task 5: Módulo D — Download, Resumo Audiovisual & Composição Ativa

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Modify: `renderer/app/studio/api/routes.py`
- Create: `tests/test_video_download_and_audiovisual_summary.py`

**Interfaces:**
- Consumes: `AudioDirector`, `AssSubtitleRenderer`, `storage/music-candidates`.
- Produces:
  - `api/routes.py`: `GET /studio/videos/{id}/download` que serve o arquivo `.mp4` aprovado com `Content-Disposition: attachment; filename="<titulo_slug>.mp4"`. Retorna 404 caso o vídeo ainda não possua render.
  - `api/panel_video_workspace.py` (`_area_qualidade`): botão `⬇ Baixar vídeo (.mp4)` ao lado de `Abrir prévia completa`, dados do arquivo e cartão `Resumo audiovisual desta versão` (duração, tomadas/ritmo, música CC0, mixagem ducking/fade, legendas dinâmicas, mídias).
  - `api/panel_video_workspace.py` (`_area_composicao`): ativação dos campos `Volume da música`, switch de ducking (`Abaixar a música quando houver voz`), estilo de legenda `Destaque por palavra (karaokê)` e seletor da trilha CC0.

- [ ] **Step 1: Write failing test in `tests/test_video_download_and_audiovisual_summary.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_download_and_audiovisual_summary.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement download endpoint, audio/caption controls and summary card**
  Update `api/routes.py` and `api/panel_video_workspace.py`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_download_and_audiovisual_summary.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/api/routes.py renderer/app/studio/api/panel_video_workspace.py tests/test_video_download_and_audiovisual_summary.py
  git commit -m "feat(ux): download de mp4, resumo audiovisual e ativacao de controles na composicao"
  ```

---

### Task 6: Validação Integrada e Regressão Ampla

**Files:**
- Test: Todas as suítes das Ondas 0 a 4 no contêiner.

- [ ] **Step 1: Executar suíte de testes da Onda 4**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py tests/test_panel_new_video_active.py tests/test_panel_direction_tab.py tests/test_panel_scene_multimedia.py tests/test_video_download_and_audiovisual_summary.py -q`
  Expected: ALL PASS
- [ ] **Step 2: Executar regressão completa das Ondas 0 a 3**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_pacing_*.py tests/test_music_*.py tests/test_captions_*.py tests/test_word_alignment.py tests/test_render_plan_*.py tests/test_creative_director_*.py tests/test_media_*.py tests/test_audio_director.py -q`
  Expected: ALL PASS (468+ passing)
- [ ] **Step 3: Atualizar CONTINUITY e documentação de entrega da Onda 4**
