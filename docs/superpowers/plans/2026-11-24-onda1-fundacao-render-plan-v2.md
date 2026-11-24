# Onda 1 — Fundação (Multi-shot, Transições e RenderPlan v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o motor de renderização do Faceless Studio para suportar o RenderPlan v2 com múltiplos assets sequenciais por cena (multi-shot), corte seco e transições configuráveis, suporte real a shots de vídeo com offset temporal, áudio mix declarativo e invalidação de cache precisa, mantendo paridade e compatibilidade total com planos v1 existentes.

**Architecture:**
- Domínio (`domain/render_plan.py`): Adiciona modelo `AudioMix`, expande `Transition.kind` para `("none", "fade", "crossfade", "cut")`, adiciona `asset_offset_ticks` em `Shot`, suporta `schema_version = 2` com função `upconvert_v1_to_v2`, e atualiza `render_plan_builder.py` para aceitar múltiplos shots base contíguos por cena.
- Persistência (`adapters/postgres/migrations/0050_scene_assets.sql`, `domain/contracts.py`, `editorial_repo.py`): Cria tabela `scene_assets` para associar N assets ordenados a uma cena com fatias temporais (`start_s`, `end_s`), preservando fallback transparente para `scene.asset_id` legado.
- Compilação e Render (`adapters/render_plan_compiler.py`, `adapters/render_plan_ffmpeg.py`): `_fade_filter` compila corte seco (`cut`/`none` em v2) ou fade configurado; compilador trata shots de vídeo com trim (`start`, `duration`) e scale; e aplica parâmetros declarativos de `AudioMix` na mixagem de áudio.
- Cache de Render (`domain/render_cache.py`): Inclui parâmetros de transição, offset e estilo visual nos fingerprints dos nós visuais e de áudio.
- Integração (`tests/test_render_plan_multishot_e2e.py`): Valida com FFmpeg real dentro do contêiner a renderização de cenas multi-shot combinando imagem e vídeo sintéticos.

**Tech Stack:** Python 3.11/3.12, Pydantic v2, PostgreSQL (psycopg 3), FFmpeg 7.1, Pillow, Pytest.

**Spec:** `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` (Seção 6, Onda 1) e `docs/adr/ADR-001-render-plan.md`.

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub.
- Paridade estrita: planos v1 persistidos devem carregar, validar e renderizar exatamente como antes (mesmo hash, mesmos filtros).
- Apenas migrações aditivas (próxima: `0050_scene_assets.sql`).
- Camadas puras: `domain/` e `application/` não importam `ffmpeg`, `subprocess` nem realizam I/O de disco.
- Todos os contratos gerados devem ser atualizados via `scripts/export_contracts.py` e validados por `test_committed_contracts_match_code`.
- Execução de testes sempre dentro do contêiner via `TMPDIR=/tmp scripts/test-container.sh`.

## Review Focus

1. **Paridade e Upconvert v1→v2**: Planos serializados com `schema_version=1` devem ser deserializados sem erro e produzir comandos FFmpeg idênticos aos anteriores.
2. **Cobertura contígua em Multi-shot**: Cenas com múltiplos shots base devem cobrir exatamente a duração da cena em ticks, sem lacunas (`gap`) e sem sobreposição de shots base (`overlap`).
3. **Corte seco honesto**: Em v2, `Transition(kind="cut")` ou `Transition(kind="none")` não deve injetar `fade=t=in` nem `fade=t=out` no filter_complex.
4. **Trimming seguro de vídeo**: Shots com `media_type="video"` devem aplicar `trim=start={offset}:duration={dur}` sem ultrapassar a duração física do arquivo de mídia.
5. **Invalidação de cache visual por estilo**: Alteração de cor de legenda ou família tipográfica deve alterar o fingerprint do nó `visual` no grafo de cache para forçar regeração do overlay.

---

### Task 1: Contrato RenderPlan v2 & Upconversion

**Files:**
- Modify: `renderer/app/studio/domain/render_plan.py:179-220,484-565`
- Create: `tests/test_render_plan_v2_contract.py`
- Modify: `scripts/export_contracts.py` (se necessário para versionamento)

**Interfaces:**
- Consumes: `_PlanModel`, `Tick`, `DurationTick`, `NonBlank`
- Produces:
  - `class AudioMix(_PlanModel)`:
    - `music_gain: float = 0.40`
    - `ducking_threshold: float = 0.02`
    - `ducking_ratio: float = 10.0`
    - `afade_in_s: float = 0.25`
    - `afade_out_s: float = 0.25`
    - `loudnorm_i: float = -16.0`
    - `loudnorm_tp: float = -1.5`
    - `loudnorm_lra: float = 11.0`
  - `class Transition(_PlanModel)`:
    - `kind: Literal["none", "fade", "crossfade", "cut"] = "none"`
    - `duration_ticks: Tick = 0`
    - Validador: `none` e `cut` exigem `duration_ticks == 0`; `fade` e `crossfade` exigem `duration_ticks >= 1`.
  - `class Shot(_PlanModel)`:
    - Novo campo: `asset_offset_ticks: Tick = 0`
  - `class RenderPlan(_Model)`:
    - Novo campo: `audio_mix: AudioMix = Field(default_factory=AudioMix)`
    - `schema_version: int = 2` (com validador que aceita `1` ou `2`)
  - `def upconvert_v1_to_v2(data: dict) -> dict`:
    - Converte dicionário de plano v1 para v2 (adiciona `audio_mix` default se ausente, define `schema_version = 2`).

- [x] **Step 1: Write failing test in `tests/test_render_plan_v2_contract.py`**
  - Testa validação de `AudioMix`
  - Testa `Transition` com `cut`, `crossfade`, `fade`, `none`
  - Testa `Shot.asset_offset_ticks`
  - Testa `upconvert_v1_to_v2` com payload v1 existente
  - Testa que `RenderPlan` aceita schema_version 1 e 2

- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_v2_contract.py -q`
  Expected: FAIL

- [x] **Step 3: Implement `AudioMix`, `Transition`, `Shot` e `upconvert_v1_to_v2` em `domain/render_plan.py`**

- [x] **Step 4: Regenerar snapshots de contrato e rodar testes**
  Run: `docker run --rm -v "$(pwd):/w" -w /w faceless-renderer-pytest:test python3 scripts/export_contracts.py`
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_v2_contract.py tests/test_contracts_snapshot.py -q`
  Expected: PASS

- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/render_plan.py contracts/ docs/10-arquitetura.md tests/test_render_plan_v2_contract.py
  git commit -m "feat(render_plan): evoluir RenderPlan para v2 com AudioMix, novas transicoes e offset"
  ```

---

### Task 2: Persistência de Múltiplos Assets por Cena (Migração 0050)

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0050_scene_assets.sql`
- Modify: `renderer/app/studio/domain/contracts.py:100-140`
- Modify: `renderer/app/studio/adapters/postgres/editorial_repo.py:200-350`
- Create: `tests/test_scene_assets_repo.py`

**Interfaces:**
- Consumes: `Scene`, `AssetReference`, `PostgresEditorialRepository`
- Produces:
  - `class SceneAsset(_Model)` em `domain/contracts.py`:
    - `id: UUIDStr = Field(default_factory=new_id)`
    - `scene_id: NonBlank`
    - `asset_id: NonBlank`
    - `position: int` (>= 0)
    - `start_s: float` (>= 0.0)
    - `end_s: float` (> start_s)
    - `role: Literal["base", "overlay"] = "base"`
    - `motion: str = "none"`
    - `transition_kind: str = "none"`
    - `transition_duration_s: float = 0.0`
  - Campo em `Scene`:
    - `assets: list[SceneAsset] = Field(default_factory=list)`
  - `PostgresEditorialRepository`:
    - Salva e recupera itens de `studio.scene_assets`
    - Fallback: se cena não tem registros em `scene_assets` mas possui `asset_id`, sintetiza um `SceneAsset(asset_id=scene.asset_id, position=0, start_s=0.0, end_s=scene.duration_s or 5.0)`.

- [x] **Step 1: Create migration `0050_scene_assets.sql`**
  DDL idempotente para tabela `studio.scene_assets` com chaves estrangeiras e índices.

- [x] **Step 2: Write failing test in `tests/test_scene_assets_repo.py`**
  - Testa inserção e busca de múltiplos `SceneAsset` por cena
  - Testa deleção em cascata com a cena
  - Testa fallback transparente para cenas legadas com apenas `asset_id`

- [x] **Step 3: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_scene_assets_repo.py -q`
  Expected: FAIL

- [x] **Step 4: Implement `SceneAsset` em `domain/contracts.py` e persistência em `editorial_repo.py`**

- [x] **Step 5: Run tests to verify it passes**
  Run: `docker run --rm -v "$(pwd):/w" -w /w faceless-renderer-pytest:test python3 scripts/export_contracts.py`
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_scene_assets_repo.py tests/test_editorial_repo.py tests/test_contracts_snapshot.py -q`
  Expected: PASS

- [x] **Step 6: Commit**
  ```bash
  git add renderer/app/studio/adapters/postgres/migrations/0050_scene_assets.sql renderer/app/studio/domain/contracts.py renderer/app/studio/adapters/postgres/editorial_repo.py contracts/ tests/test_scene_assets_repo.py
  git commit -m "feat(repo): implementar persistencia e contratos para multiplos assets por cena"
  ```

---

### Task 3: Produtor de Beats e Builder Multi-shot

**Files:**
- Modify: `renderer/app/studio/domain/render_plan_builder.py:20-80,240-340`
- Create: `tests/test_render_plan_builder_multishot.py`

**Interfaces:**
- Consumes: `StoryboardScene`, `StoryboardShot`, `SceneAsset`, `RenderPlan`
- Produces:
  - `class StoryboardShot(_PlanModel)`:
    - `shot_id: NonBlank`
    - `asset_id: NonBlank`
    - `duration_s: float`
    - `asset_offset_s: float = 0.0`
    - `motion: Motion = "none"`
    - `transition: Transition | None = None`
  - `StoryboardScene`:
    - Adiciona `shots: list[StoryboardShot] | None = None`
  - `build_render_plan`:
    - Se `scene.shots` estiver presente: cria um `Shot` base contíguo para cada `StoryboardShot`, convertendo durações em ticks inteiros e garantindo que a soma dos ticks bata exatamente com a duração total da cena.
    - Se `scene.shots` for None: preserva comportamento legado de 1 shot base por cena.

- [x] **Step 1: Write failing test in `tests/test_render_plan_builder_multishot.py`**
  - Testa cena com 3 shots sequenciais (ex: 2s, 3s, 2.5s)
  - Verifica ausência de gaps na track `visual-main`
  - Verifica que cada shot recebe os ticks corretos e asset_ref correspondente
  - Verifica preservação de paridade quando `shots=None`

- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_builder_multishot.py -q`
  Expected: FAIL

- [x] **Step 3: Implement multi-shot support in `domain/render_plan_builder.py`**

- [x] **Step 4: Run tests to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_builder_multishot.py tests/test_render_plan_builder.py -q`
  Expected: PASS

- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/render_plan_builder.py tests/test_render_plan_builder_multishot.py
  git commit -m "feat(builder): suportar multiplos shots base sequenciais por cena no RenderPlan"
  ```

---

### Task 4: Compilador FFmpeg — Cortes, Transições e Vídeo Trim

**Files:**
- Modify: `renderer/app/studio/adapters/render_plan_compiler.py:240-305,380-405`
- Modify: `renderer/app/studio/adapters/render_plan_ffmpeg.py:480-605`
- Create: `tests/test_render_plan_compiler_v2.py`

**Interfaces:**
- Consumes: `ShotExecution`, `RenderPlan`, `AudioMix`, `Transition`
- Produces:
  - `_fade_filter(transition: Transition | None, seconds: float, tps: int, shot_id: str, schema_version: int = 2) -> str`:
    - Se `transition.kind == "cut"`: retorna `""` (sem filtros fade).
    - Se `transition.kind == "none"` e `schema_version >= 2`: retorna `""` (sem fade; corte seco).
    - Se `transition.kind == "none"` e `schema_version == 1`: retorna fade legado (`d=0.25`).
    - Se `transition.kind == "fade"`: aplica fade out configurado.
  - Video shot compile:
    - Extrai `asset_offset_ticks` e aplica no `trim=start={offset_s:.6f}:duration={dur_s:.6f}`.
  - `_descriptors` em `render_plan_ffmpeg.py`:
    - Inspeciona sufixo ou metadados da mídia: `.mp4`, `.mov`, `.webm` identificados como `media_type="video"`; imagens como `"image"`.
  - Audio mix compilation:
    - Compila argumentos com base nos valores declarados em `plan.audio_mix` (ganho da música, ducking ratio, loudnorm target).

- [x] **Step 1: Write failing test in `tests/test_render_plan_compiler_v2.py`**
  - Testa filter_complex gerado para shot com corte seco (`cut`)
  - Testa filter_complex gerado para shot de vídeo com `asset_offset_ticks`
  - Testa preservação de fade legado para planos com `schema_version = 1`
  - Testa aplicação dos parâmetros de `AudioMix` no comando de áudio

- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_compiler_v2.py -q`
  Expected: FAIL

- [x] **Step 3: Implement changes in `render_plan_compiler.py` and `render_plan_ffmpeg.py`**

- [x] **Step 4: Run tests to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_compiler_v2.py tests/test_render_compiler.py tests/test_render_plan_executor.py -q`
  Expected: PASS

- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/render_plan_compiler.py renderer/app/studio/adapters/render_plan_ffmpeg.py tests/test_render_plan_compiler_v2.py
  git commit -m "feat(compiler): implementar corte seco, trim de video com offset e audio mix declarativo"
  ```

---

### Task 5: Cache de Render com Invalidação Precisa

**Files:**
- Modify: `renderer/app/studio/domain/render_cache.py:220-280`
- Create: `tests/test_render_cache_v2.py`

**Interfaces:**
- Consumes: `RenderPlan`, `Shot`, `AudioMix`, `NodeId`
- Produces:
  - `visual_fingerprint(shot: Shot, asset_digest: str, style_digest: str | None = None) -> str`:
    - Inclui `shot.transition.kind`, `shot.transition.duration_ticks`, `shot.asset_offset_ticks`.
    - Inclui `style_digest` (se fornecido) para garantir que mudanças de cor ou fonte invalidem o shot visual correspondente.
  - `music_fingerprint(source: GeneratedAudioSource, audio_mix: AudioMix | None = None) -> str`:
    - Inclui parâmetros de `audio_mix` no digest da música.

- [x] **Step 1: Write failing test in `tests/test_render_cache_v2.py`**
  - Testa que alterar a transição de um shot altera seu fingerprint
  - Testa que alterar o offset temporal de um shot altera seu fingerprint
  - Testa que alterar o estilo de legenda altera o fingerprint visual
  - Testa que alterar o ganho do `AudioMix` altera o fingerprint de mix/música

- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_cache_v2.py -q`
  Expected: FAIL

- [x] **Step 3: Update `domain/render_cache.py`**

- [x] **Step 4: Run tests to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_cache_v2.py tests/test_render_cache.py -q`
  Expected: PASS

- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/render_cache.py tests/test_render_cache_v2.py
  git commit -m "feat(cache): refinar fingerprints visuais e de audio para invalidacao seletiva precisa"
  ```

---

### Task 6: Teste de Integração FFmpeg Real com Assets Sintéticos (Multi-shot E2E)

**Files:**
- Create: `tests/test_render_plan_multishot_e2e.py`

**Interfaces:**
- Consumes: `RenderPlanExecutor`, `PostgresRenderPlanRepository`, `RenderPlan`, FFmpeg no contêiner
- Produces:
  - Teste de ponta a ponta que:
    1. Cria 2 imagens de teste (PNG) e 1 vídeo de teste (MP4 gerado via `ffmpeg -f lavfi -i testsrc=duration=4:size=1080x1920:rate=25`).
    2. Constrói um `RenderPlan` v2 com 2 cenas:
       - Cena 1: multi-shot com imagem (2s) -> corte seco (`cut`) -> vídeo com offset (2s).
       - Cena 2: imagem única (3s) com transição `fade`.
    3. Executa a compilação e renderização completa através de `RenderPlanExecutor`.
    4. Executa `ffprobe` no MP4 de saída verificando integridade: duração exata de 7s, formato 1080x1920, presença de vídeo e áudio mixado.
    5. Executa `evaluate_qa` e valida aprovação técnica sem achados bloqueantes.

- [x] **Step 1: Write `tests/test_render_plan_multishot_e2e.py`**

- [x] **Step 2: Run integration test inside container**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_multishot_e2e.py -q`
  Expected: PASS

- [x] **Step 3: Commit**
  ```bash
  git add tests/test_render_plan_multishot_e2e.py
  git commit -m "test(render): adicionar teste de integracao FFmpeg real com cenas multi-shot e video"
  ```

---

### Task 7: Validação de Regressão e Fechamento da Onda 1

**Files:**
- Test: Suíte completa de renderização e contratos

- [x] **Step 1: Run full render and persistence test suite in container**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_*.py tests/test_composition.py tests/test_contracts_snapshot.py tests/test_scene_assets_repo.py -q`
  Expected: ALL PASS (0 failures)

- [x] **Step 2: Verify git status is clean and document progress**
  Atualizar `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` marcando Onda 1 como concluída.

- [x] **Step 3: Commit**
  ```bash
  git add docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md docs/superpowers/plans/2026-11-24-onda1-fundacao-render-plan-v2.md
  git commit -m "docs(onda1): registrar conclusao da Onda 1 - fundacao RenderPlan v2 e multi-shot"
  ```
