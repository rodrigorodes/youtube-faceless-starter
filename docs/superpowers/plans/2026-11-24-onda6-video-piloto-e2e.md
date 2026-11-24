# Onda 6 — Vídeo Piloto & Rastreabilidade de Orçamento Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Concluir a última onda do plano mestre produzindo e validando de ponta a ponta um vídeo piloto em formato `long` (16:9, 3–5 min) com os motores das Ondas 1 a 5 (RenderPlan v2 multi-shot, PacingEngine, AudioDirector ducking, legendas ASS, Pexels/Pixabay e QaReport v2), com rastreabilidade de custos por categoria (`usage_ledger.category`), amostragem visual e relatório honesto de entrega.

**Architecture:**
- Persistência e Rastreabilidade: Migração aditiva `0053_usage_ledger_category.sql` estendendo `studio.usage_ledger` com `category`, `duration_ms` e `attempt`, permitindo discriminar custos por categoria (`llm`, `tts`, `image`, `video_gen`, `render`).
- Agregação de Custos (`application/ports.py`, `adapters/postgres/editorial_repo.py`, `api/routes.py`): Consulta e agrupamento de custos reais do vídeo por categoria.
- Pipeline e Geração do Piloto (`tests/test_pilot_video_e2e.py` e script de orquestração): Criação de vídeo longo (16:9), roteiro de 3 a 5 minutos, multi-shots com pacing balanceado, mixagem de áudio com ducking, renderização do MP4 e validação via QaReport v2 com amostragem de frames.
- Validação Final e Encerramento: Execução completa no contêiner Docker, extração de frames do MP4, revisão de qualidade e atualização da documentação contínua (`CONTINUITY-producao-profissional-v1.md`).

**Tech Stack:** Python 3.11+, PostgreSQL, FFmpeg 7+ / ffprobe, Pydantic v2, Pytest.

**Spec:** `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` (Onda 6 — Piloto & Seção 7).

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub (push sob responsabilidade do operador).
- Clean Architecture: `domain/` puro sem I/O, adapters isolados, banco acessado apenas através de repositórios.
- Regra de ouro da Onda 6: Só declarar "vídeo gerado" se o render existir em disco, puder ser reproduzido e tiver sido revisado por amostragem de frames.
- Testes exclusivamente no contêiner Docker: `TMPDIR=/tmp scripts/test-container.sh <testes> -q`.
- Preservar integridade dos 496+ testes existentes das Ondas 0 a 5.

## Review Focus

1. **Migração retrocompatível do `usage_ledger`**: Inserções existentes sem `category` devem assumir o default `'other'`, sem quebrar queries antigas ou dados históricos.
2. **Formato do Vídeo Piloto**: Deve ser estritamente `format="long"` (16:9, 1920x1080), com duração alvo entre 180s e 300s (3–5 min).
3. **Integridade do RenderPlan v2 Multishot**: A timeline de 3 a 5 minutos deve ter múltiplos shots sincronizados com cortes ritmados (pacing) e transições válidas sem sobreposição de legendas ASS.
4. **Mixagem de Áudio Completa**: O áudio final deve conter voz (narração) e música CC0 com ducking automático (volume atenuado sob a fala e fade-out no término).
5. **Aprovação pelo QaReport v2**: O render deve passar pelas checagens determinísticas (resolução 1920x1080, True-Peak <= 0.0 dBTP, sem estourar silêncio ou preto) e registrar cobertura `verified`.

---

### Task 1: Rastreabilidade de Orçamento por Categoria (`usage_ledger.category`)

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0053_usage_ledger_category.sql`
- Modify: `renderer/app/studio/domain/contracts.py:270-290`
- Modify: `renderer/app/studio/adapters/postgres/editorial_repo.py:568-585`
- Modify: `renderer/app/studio/application/ports.py`
- Create: `tests/test_usage_ledger_category.py`

**Interfaces:**
- Produces:
  - Migração `0053_usage_ledger_category.sql`: colunas `category text NOT NULL DEFAULT 'other'`, `duration_ms integer DEFAULT NULL`, `attempt integer DEFAULT 1` na tabela `studio.usage_ledger`.
  - `domain/contracts.py::UsageEntry`: novos campos `category: str = 'other'`, `duration_ms: int | None = None`, `attempt: int = 1`.
  - `application/ports.py::UsageRepository` / `adapters/postgres/editorial_repo.py::PostgresUsageRepository`:
    - `record(video_id: str | None, entry: UsageEntry) -> None` gravando os novos campos.
    - `spent_by_category(video_id: str) -> dict[str, float]` retornando o total em US$ agrupado por categoria (`llm`, `tts`, `image`, `video_gen`, `render`, `other`).

- [ ] **Step 1: Write failing test in `tests/test_usage_ledger_category.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_usage_ledger_category.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement migration 0053, contracts and repo methods**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_usage_ledger_category.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/postgres/migrations/0053_usage_ledger_category.sql renderer/app/studio/domain/contracts.py renderer/app/studio/adapters/postgres/editorial_repo.py renderer/app/studio/application/ports.py tests/test_usage_ledger_category.py
  git commit -m "feat(ledger): adicionar category, duration_ms e spent_by_category no usage_ledger"
  ```

---

### Task 2: Endpoint de Detalhamento de Custos por Categoria da API

**Files:**
- Modify: `renderer/app/studio/api/routes.py`
- Modify: `renderer/app/studio/application/use_cases.py`
- Create: `tests/test_cost_breakdown_api.py`

**Interfaces:**
- Consumes: Task 1 (`spent_by_category`).
- Produces:
  - `GET /studio/videos/{id}/cost-breakdown`: retorna `{ "video_id": id, "total_usd": float, "categories": { "llm": float, "tts": float, "image": float, "render": float, ... } }`.

- [ ] **Step 1: Write failing test in `tests/test_cost_breakdown_api.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_cost_breakdown_api.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement endpoint in `api/routes.py` and wiring**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_cost_breakdown_api.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/api/routes.py renderer/app/studio/application/use_cases.py tests/test_cost_breakdown_api.py
  git commit -m "feat(api): endpoint /studio/videos/{id}/cost-breakdown com custos por categoria"
  ```

---

### Task 3: Suíte de Integração E2E do Vídeo Piloto Longo (3–5 min)

**Files:**
- Create: `tests/test_pilot_video_e2e.py`

**Interfaces:**
- Consumes: `RenderPlan` v2, `PacingEngine`, `AudioDirector`, `AssSubtitleRenderer`, `QaReport` v2, `FfmpegQa`.
- Produces:
  - Teste automatizado que constrói um vídeo completo de formato `long` (16:9, 1920x1080), 180 segundos (3 minutos), 12 cenas multishot com cortes dinâmicos/balanceados, narração sintetizada, trilha musical CC0 (`Sci-Fi Survival Dreamscape`) com ducking automático e legendas ASS.
  - Executa a compilação do plano e a renderização FFmpeg real.
  - Valida que o arquivo `.mp4` existe no disco com tamanho > 0 e pode ser lido pelo `ffprobe`.
  - Executa o `evaluate_quality` completo gerando `QaReport v2` sem achados `blocking` e com cobertura `verified`.
  - Registra os custos por categoria em `usage_ledger`.

- [ ] **Step 1: Write test in `tests/test_pilot_video_e2e.py`**
- [ ] **Step 2: Run test in container to verify execution and render**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_pilot_video_e2e.py -q`
  Expected: PASS
- [ ] **Step 3: Commit**
  ```bash
  git add tests/test_pilot_video_e2e.py
  git commit -m "test(pilot): suite e2e de geracao e avaliacao do video piloto longo (16:9, 3 min)"
  ```

---

### Task 4: Script de Amostragem Visual e Revisão dos Frames do Piloto

**Files:**
- Create: `scripts/sample_pilot_frames.py`
- Modify: `tests/test_pilot_video_e2e.py`

**Interfaces:**
- Produces:
  - `scripts/sample_pilot_frames.py`: extrai N frames em intervalos regulares ao longo do vídeo `.mp4` gerado (ex: a cada 20% da timeline: 0s, 36s, 72s, 108s, 144s, 175s) salvando PNGs e confirmando resolução 1920x1080, presença de elementos visuais e ausência de quadros corrompidos.
  - Integração no teste para garantir verificação programática dos frames amostrados.

- [ ] **Step 1: Implement `scripts/sample_pilot_frames.py`**
- [ ] **Step 2: Run frame sampling on pilot render in container**
  Run: `docker run --rm -v "$(pwd):/w" -w /w faceless-renderer-pytest:test python3 scripts/sample_pilot_frames.py --check`
  Expected: PASS (todos os frames válidos 1920x1080)
- [ ] **Step 3: Commit**
  ```bash
  git add scripts/sample_pilot_frames.py tests/test_pilot_video_e2e.py
  git commit -m "feat(pilot): extrator e validador de amostragem de frames do video piloto"
  ```

---

### Task 5: Relatório de Entrega da Onda 6 e Atualização Contínua

**Files:**
- Modify: `contracts/v1/usageentry.schema.json`
- Modify: `docs/superpowers/CONTINUITY-producao-profissional-v1.md`
- Create: `docs/superpowers/reports/2026-11-24-onda6-piloto-relatorio-final.md`

- [ ] **Step 1: Regenerar schemas de contratos atualizados**
  Run: `docker run --rm -v "$(pwd):/w" -w /w faceless-renderer-pytest:test python3 scripts/export_contracts.py`
- [ ] **Step 2: Executar regressão completa de todas as 6 ondas**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py tests/test_panel_new_video_active.py tests/test_panel_direction_tab.py tests/test_panel_scene_multimedia.py tests/test_video_download_and_audiovisual_summary.py tests/test_qa_report_v2_contract.py tests/test_quality_v2_domain.py tests/test_quality_ffmpeg_v2.py tests/test_quality_semantic_v2.py tests/test_panel_quality_v2.py tests/test_usage_ledger_category.py tests/test_cost_breakdown_api.py tests/test_pilot_video_e2e.py tests/test_pacing_*.py tests/test_music_*.py tests/test_captions_*.py tests/test_word_alignment.py tests/test_render_plan_*.py tests/test_creative_director_*.py tests/test_media_*.py tests/test_contracts_snapshot.py tests/test_audio_director.py tests/test_script_revision_restore.py -q`
  Expected: ALL PASS (500+ testes)
- [ ] **Step 3: Gerar relatório final em `docs/superpowers/reports/2026-11-24-onda6-piloto-relatorio-final.md`**
- [ ] **Step 4: Atualizar `CONTINUITY-producao-profissional-v1.md` e sincronizar com worktree**
- [ ] **Step 5: Commit final**
  ```bash
  git add contracts/v1/usageentry.schema.json docs/superpowers/CONTINUITY-producao-profissional-v1.md docs/superpowers/reports/2026-11-24-onda6-piloto-relatorio-final.md
  git commit -m "docs(pilot): relatorio final da Onda 6 e conclusao das 6 ondas de producao profissional"
  ```
