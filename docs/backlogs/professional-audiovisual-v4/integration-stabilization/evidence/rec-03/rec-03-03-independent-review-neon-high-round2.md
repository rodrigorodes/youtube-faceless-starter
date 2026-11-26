# REC-03.03 Independent Review (`github-copilot/gemini-4-neon`, Round 2 — Fresh Session)

- **Reviewer / Real Model:** Independent Reviewer (fresh subagent session, zero deference) — `github-copilot/gemini-4-neon` (Gemini 4 Neon)
- **Target Slice:** `REC-03.03` (`R10` — Lacunas de pipeline: cache segmentado vídeo + narração, `REC-03.03b` preflight/progresso/cancelamento, QA + regeneração seletiva limitada em `QaHandler`/`ProductionCoordinator`, restart completo, Creative Direction → Brief → Short/Long Script → `RenderPlan`, `ExportSubtitles` em `/subtitles`/`.vtt`/`.ass`, `render.caption_sync` fail-closed, licença fail-closed em todos os gates + `adapters/license_mapping.py`)
- **Repository / Branch:** `/Users/rodrigomendes/youtube-faceless-starter` on `develop` (`main` untouched @ `42700cb331165a68455173a91c463d4733292cfd`)
- **Base HEAD:** `7ded0f5d58d655df41df6dda32f479308489314b` + uncommitted working tree (read-only audit; zero code/test edits, zero commits/pushes)
- **Reviewed Artifact Hashes (SHA-256 — independently computed):**
  - `git diff` (20 tracked files, `+682 / -57`, `78658` bytes): `8f114b9f649d6e4e451b4218c2983d6f9cdfdbe63217989d0d2f7cc5ac2cdfea`
  - `git diff renderer/` (`77461` bytes): `61aa45f8fc231b1be2a5dcaa384b94cde9ac96cfaf90edf7445fecf73b34fdeb`
  - `renderer/app/studio/adapters/license_mapping.py` (untracked, `1006` bytes): `1a4f72a161c90bb1a598bb47f8f4015b7ee7fe54ece2f696d8ae15af6afc8f59`
  - `tests/test_rec_03_pipeline_integration.py` (untracked, `66741` bytes): `fb4bc357c885346f20c3eee35bbef01d21816ee5400467045b4ecff5520caeda`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-03/rec-03-03-pipeline-evidence.md` (untracked, `18871` bytes): `55d3acb3a3ceed200f172b4f0f35e6561efb2ef6e8a172f8526f881c15c8b469`
  - Alignment `renderer/app` checkout x Docker image: `94d8d9bcea2693a0` (migrations `49/49`)
- **External Paid API Spend:** `$0.00` | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`, 1st guard) | **DEV Ports (`8000`/`5678`):** untouched
- **Review Round:** Round 2 (re-review after Round 1 `REJECTED` with `3` P0, `6` P1, `2` P2)
- **Final Decision:** **`APPROVED`**
  - **Weighted Mean:** **`9.44 / 10`** (`>= 9.0`)
  - **Minimum Dimension Score:** **`9.2 / 10`** (`>= 9.0` on **all** applicable dimensions)
  - **Open Blockers:** **`0` P0**, **`0` P1** (`2` non-blocking P2 hardening/operational notes)
  - **Absolute Rubric Blocks Triggered (`QUALITY-RUBRIC.md:22-26`):** **NONE**

---

## 1. Independent Verification Re-Executed

All commands were executed independently on the exact working tree (`HEAD 7ded0f5` + diff SHA-256 `8f114b9f...`) with `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`.

### 1.1 Focused REC-03 Container Suite
- **Command:**
  ```bash
  ./scripts/test-container.sh tests/test_rec_03_pipeline_integration.py tests/test_rec_03_studio_routes.py -ra
  ```
- **Alignment:** `HEAD=7ded0f5 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=94d8d9bcea2693a0 imagem=94d8d9bcea2693a0`, `migrações: checkout=49 imagem=49`
- **Observed Result:** **`37 passed, 1 warning in 37.98s`** (`10` in `test_rec_03_pipeline_integration.py` + `27` in `test_rec_03_studio_routes.py`) | **Exit code:** **`0`**

### 1.2 Full Canonical Container Suite (Gate G6)
- **Command:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alignment:** `HEAD=7ded0f5 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=94d8d9bcea2693a0 imagem=94d8d9bcea2693a0`, `migrações: checkout=49 imagem=49`
- **Observed Result:** **`4501 passed, 26 skipped, 1 warning in 716.75s (0:11:56)`** (`0` failed; total collected `4527`; `tests/test_architecture.py` `9/9` passed) | **Exit code:** **`0`**
- **Skips Breakdown (26 — structural in slim container):** `3` Playwright browser tests (`test_reference_browser.py`, `ve08/test_composition_functional.py`, `ve08/test_storyboard_functional.py` — `pytest_playwright` absent in slim image) + `23` Node.js tests (all executed and passed on host in §1.3).

### 1.3 Host Node.js / Panel / Workflow Suite (+ Architecture Check)
- **Command:**
  ```bash
  python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
    tests/test_falha_producao.py tests/test_publicacao_acao.py tests/test_workflow_analytics.py \
    tests/test_workflow_publish.py tests/test_workflow_trends.py -ra
  ```
- **Observed Result:** **`101 passed in 8.51s`** | **Exit code:** **`0`**
- **Additional Host Architecture Check:** `python3 -m pytest tests/test_architecture.py -ra` → **`9 passed in 0.75s`** | **Exit code:** **`0`**

### 1.4 Isolated Playwright Chromium E2E (`docker-compose.e2e.yml`, Port `8100`, `tmpfs`)
- **Commands:**
  ```bash
  E2E_PROJECT_NAME=faceless-e2e-rec0303r2 E2E_PORT=8100 \
    docker compose -p faceless-e2e-rec0303r2 -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
    STUDIO_E2E_USER="e2e" STUDIO_E2E_PASSWORD="e2e-senha-descartavel" \
    python3 -m pytest tests/e2e_ux/test_rec_03_studio_browser.py -v -ra
  docker compose -p faceless-e2e-rec0303r2 -f docker-compose.e2e.yml down -v
  lsof -i :8100
  ```
- **Observed Result:** **`1 passed in 8.71s`** (`test_rec_03_studio_browser_desktop_and_mobile_e2e[chromium]`) | **Exit code:** **`0`**
- **Teardown Proof:** Containers `faceless-e2e-rec0303r2-renderer-e2e-1`, `faceless-e2e-rec0303r2-postgres-e2e-1` and network `faceless-e2e-rec0303r2_default` removed; `lsof -i :8100` confirmed `PORT_8100_CLOSED`.

### 1.5 Out-of-Repo Mutation Verification (4 Independent Mutations — All 4 KILLED)
Executed on isolated temporary copies under `/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/` (unconditionally cleaned up after each run; zero repo changes). Unmutated Postgres baseline confirmed `exit 0` before running container mutations.

| # | Target File & Mutation Applied | Test Executed | Observed Result | Verdict |
|---|---|---|---|---|
| **M1** | `application/production.py`: disable `QaHandler` selective regeneration loop (`compute_selective_regeneration`) so QA immediately raises `StageExecutionFailed` | `test_pipeline_qa_known_defect_triggers_bounded_selective_regeneration` (ephemeral Postgres + FFmpeg container) | `FAILED` (`1 failed in 5.54s`), **exit `1`** | **KILLED** |
| **M2** | `domain/asset_registry.py`: re-introduce substring bypass (`"commercial"`, `"cc0"`, `"cc-by"`, `"public domain"`) in `verify_license_provenance` | `test_pipeline_license_allowlist_no_bypass_and_vendor_boundary` | `FAILED` (`AssertionError: Bypass aceito indevidamente: 'non-commercial'`), **exit `1`** | **KILLED** |
| **M3** | `adapters/quality_ffmpeg.py`: delete the entire `caption_sync` measurement block in `FfmpegQualityEvaluator.evaluate` | `test_pipeline_qa_caption_sync_measured_drift_and_fail_closed_probe` | `FAILED` (`AssertionError: assert 'render.caption_sync' in ...`), **exit `1`** | **KILLED** |
| **M4** | `adapters/render_plan_ffmpeg.py`: replace `_brief_render_hints(spec.creative_brief)` with `_brief_render_hints(None)` in `_build_plan` | `test_pipeline_creative_brief_flows_to_short_long_scripts_and_render_plan` (ephemeral Postgres container) | `FAILED` (`AssertionError: assert (122 == 132)`), **exit `1`** | **KILLED** |

### 1.6 Forensic Security & Contract Probes (Read-Only)
1. **License Allowlist & Adapter Mapping (`domain/asset_registry.py`, `adapters/license_mapping.py`):**
   - Rejected (`False`) both in domain and after `normalize_vendor_license`: `"non-commercial"`, `"not commercial"`, `"prohibited commercial use"`, `"cc-by-nc-nd-4.0"`, `"cc-by-nc-4.0"`, `"cc-by-nd-4.0"`, `"cc-by-nc-sa-4.0"`, `"stolen-cc0-pirated"`, `"not public domain"`, `"stolen from pexels"`, `"gerado por terceiro sem autorizacao"`, `"non-commercial ai-generated"`, `"ai-generated:"`, `"ai-generated:unknown"`, `"ai-generated:non-commercial-v1"`, `"cc0 (gerada localmente pelo estúdio) extra"`, `"not cc0 (gerada localmente pelo estúdio)"`.
   - Domain rejects `"Pexels License"`, `"Pixabay License"`, `"Pixabay Content License"`, `"Unsplash License"` (`False`); `normalize_vendor_license` maps exact vendor labels to `"free stock"` (`True` in domain) and leaves tampered strings like `"stolen from pexels"` intact (`False`).
   - Edge case logged as **P2-1**: `"ai-generated:cc-by-nc-nd-4.0"` / `"ai-generated:not-commercial"` still pass `_AI_MODEL_RE` because `_DISALLOWED_AI_TOKENS` only lists 6 tokens (see §4).
2. **Creative Direction Sanitizer (`domain/creative_director.py`):**
   - `10/10` legitimate PT-BR/technical phrases pass (`match=None`): `"Vídeo sobre auto-afirmação e motivação"`, `"A pré-afirmação científica do método"`, `"Re-afirmar o compromisso educacional"`, `"Usar estilo color-preset cinematográfico"`, `"Tutorial de comandos bash para iniciantes"`, `"Como fazer requisições com curl em APIs REST"`, `"História do projeto FFmpeg em código aberto"`, etc.
   - `14/14` real CLI/shell injection vectors matched & blocked with HTTP `422` (`-vf`, `-af`, `-filter_complex`, `-preset=`, `-crf`, `-c:v`, `-c:a`, `ffmpeg -`, `; rm -rf`, `$(whoami)`, `` `id` ``, `curl https://... | bash`, `sh -c`, `; python3`).
3. **Cache Hash & Contract Stability When `creative_brief` Is Absent (`G2`):**
   - Verified `plan_graph(plan_none) == plan_graph(plan_empty)`, `music.params == {'bpm': 122, 'seed': 7}`, and `shots == 1` when `creative_brief=None` or `{}` — zero unintended cache invalidation for legacy/briefless renders.
4. **Legacy In-Memory Modules Audit (`R10` / `G1`):**
   - `grep` confirmed `0` production callers in `renderer/app/` for `SegmentCacheManager` (`application/render_engine.py`), `AssetCatalogManager` (`application/asset_registry.py`), and `StudioWorkbenchService` (`application/studio_workbench.py`). All 3 are honestly classified `DEFERRED` (with risk, owner, and migration path) in `rec-03-03-pipeline-evidence.md` §2.

---

## 2. Round 1 Findings Verification Matrix

| Round 1 ID | Sev | Status in Round 2 | Verified Code & Test Evidence |
|---|---|---|---|
| **P0-1** | P0 | **RESOLVED** | `renderer/app/studio/domain/asset_registry.py:35-92` uses strict normalized allowlist + exact local suffix check + `ai-generated:` format check (zero substring bypass). Verified in §1.6 and Mutation M2 (`exit 1`). Minor hardening note logged as P2-1. |
| **P0-2** | P0 | **RESOLVED** | Zero vendor names in `domain/` or `application/`; `renderer/app/studio/adapters/license_mapping.py:8-24` wired in `composition/wiring.py:60,717,720,724`. `tests/test_architecture.py` `9/9` passed. |
| **P0-3** | P0 | **RESOLVED** | `compute_selective_regeneration` integrated in `QaHandler.execute` (`application/production.py:457-516`), wired via `build_stage_handlers` (`production.py:705-712`) and `composition/wiring.py:748-752`; `black_intervals` parsed in `adapters/qa_ffmpeg.py:78,86-89,97` and scene-attributed in `domain/quality.py:288-302,385-403`. Proven with real `ProductionCoordinator` + Postgres + FFmpeg + Mutation M1 (`exit 1`). |
| **P1-1** | P1 | **RESOLVED** | Centralized `license_block_reason` (`application/publication_gate.py:26-60`) checks primary `sc.asset_id`, secondary `scene_assets`, and fails closed when `assets.get(...) is None`. Wired into `publication_block_reason` (`publication_gate.py:113-116`), `Approve` (`publishing.py:65-69`), `ClaimPublication` (`publishing.py:143-153`), and `RunPublication._prepare` (`publication_execution.py:212-217`). Kill switch `enabled=False` remains 1st guard. |
| **P1-2** | P1 | **RESOLVED** | `GenerateScript` (`application/editorial.py:475-481`) and `GenerateLongScript` (`application/longform.py:150-196,331-365`) load/validate `video.creative_brief` without swallowing errors; `RunRender._render` (`application/render.py:360`) sets `RenderSpec.creative_brief`; `PlanFfmpegRenderer._build_plan` (`adapters/render_plan_ffmpeg.py:66-110,690-718`) applies pacing/motion/music hints while preserving frozen `config_snapshot`. Verified by Mutation M4 (`exit 1`). |
| **P1-3** | P1 | **RESOLVED** | `ExportSubtitles` (`application/render.py:415-447`) injected in `composition/wiring.py:673` with `export_captions_from_plan` (`adapters/captions_exporters.py:95-125`) and served by `/subtitles`, `/subtitles.vtt`, `/subtitles.ass` (`api/routes.py:2531-2582`) with legacy `.srt`/`.vtt` fallback and Clean Architecture preserved. |
| **P1-4** | P1 | **RESOLVED** | `_probe_duration` (`adapters/quality_ffmpeg.py:127-141`) raises `RuntimeError` on error (never `0.0`); `FfmpegQualityEvaluator.evaluate` (`quality_ffmpeg.py:151-180`) calls `check_audio_caption_sync` and records `caption_sync_error` (no silent `except`); `_collect_caption_sync_checks` (`domain/quality.py:491-509`) only emits `CHECK_CAPTION_SYNC` when measured and sets coverage gap (`not_verified`) on probe error. Verified by Mutation M3 (`exit 1`). |
| **P1-5** | P1 | **RESOLVED** | `FORBIDDEN_COMMAND_PATTERNS` (`domain/creative_director.py:27-39`) enforces CLI/shell token boundaries; `PUT`/`POST /direction` (`api/routes.py:1362-1431`) accept legitimate PT-BR (`200`) and block injections (`422`). |
| **P1-6** | P1 | **RESOLVED** | Test (a) proves TTS + video cache reuse with real counters (`voice.calls == 1`, `ffmpeg_calls == 3`) and changed scene 0 hash; `REC-03.03b` implemented in `PlanFfmpegRenderer` (`_preflight`, `RenderProgress`, `cancel_check` / `RenderCancelledError` wired in `RunRender._render`); test (c) proves restart across new `ProductionCoordinator` + new `PlanFfmpegRenderer` (`0` FFmpeg calls); legacy modules honestly declared `DEFERRED`. |
| **P2-1** | P2 | **RESOLVED** | `adapters/postgres/editorial_repo.py` reverted (clean in `git diff`). |
| **P2-2** | P2 | **RESOLVED** | Unused fixtures/repos removed from `tests/test_rec_03_pipeline_integration.py`; tests use canonical `SceneDraft` + `PostgresAssetRepository.swap_scene_asset`. |

---

## 3. Rubric Scoring (`QUALITY-RUBRIC.md`)

> Threshold: `>= 9.0` on **every** applicable dimension, weighted mean `>= 9.0` (no rounding), and **zero** open P0/P1 findings or absolute blocks.

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **9.5** | Todos os requisitos (`a`, `REC-03.03b`, `b`, `c`, `d.1`, `d.2`, `d.3`) conectados a consumidores reais (`RunRender`, `PlanFfmpegRenderer`, `QaHandler`/`ProductionCoordinator`, `GenerateScript`/`GenerateLongScript`, `ExportSubtitles` em `/subtitles`/`.vtt`/`.ass`, `FfmpegQualityEvaluator`, `publication_block_reason`/`Approve`/`ClaimPublication`/`RunPublication`, `wiring.py`) e provados com Postgres + FFmpeg + FastAPI + Playwright reais. Nota operacional não bloqueante **P2-2** (`scene_repair=None` no wiring `$0.00`). |
| Arquitetura e simplicidade | 20% | **9.5** | Clean Architecture preservada integralmente (`tests/test_architecture.py` `9/9` verde; normalização de vendor isolada em `adapters/license_mapping.py`; `ExportSubtitles` injetado via composição sem acoplar `api/` a `adapters/`). Reúso canônico de `PlanRegeneration`, `ProductionCoordinator`, `FfmpegQualityEvaluator` e `publication_gate`; `0` migrações novas (`49/49`); hash de cache e contratos `QaReport` v1/v2 preservados quando `creative_brief=None`; rollback trivial por `git revert`. Módulos legados em memória documentados honestamente como `DEFERRED` (0 chamadores em produção). |
| Testes e regressão | 20% | **9.5** | Reexecução independente 100% verde: focados REC-03 `37 passed` (exit `0`), suíte canônica completa `4501 passed, 26 skipped` (`4527` coletados, `0` falhas, exit `0`), Node/painel/workflows no host `101 passed` (exit `0`, cobrindo os 23 skips de Node), E2E Playwright isolado porta `8100` `1 passed` (exit `0`, `down -v` + `PORT_8100_CLOSED`), e **4/4 mutações fora do repo mortas** (`QaHandler`, allowlist de licença, `caption_sync`, `creative_brief` em `_build_plan`). |
| Segurança, orçamento e confiabilidade | 20% | **9.2** | Allowlist estrita fail-closed aplicada nos 4 gates de publicação (`Approve`, `publication_block_reason`, `ClaimPublication`, `RunPublication`) cobrindo `scene_assets` e assets ausentes; kill switch `STUDIO_PUBLICATION_ENABLED=0` preservado como 1ª guarda (`0` chamadas de token/upload); custo externo `$0.00` confirmado; `/direction` bloqueia 14/14 injeções (`422`) sem falsos positivos em 10/10 frases PT-BR (`200`); `caption_sync` falha fechado (`not_verified`) em erro de probe; cancelamento cooperativo e fencing preservados. Pequena ressalva não bloqueante **P2-1** na denylist de `ai-generated:`. |
| Evidências e operação | 15% | **9.5** | `rec-03-03-pipeline-evidence.md` totalmente alinhada ao código e ao `git diff`: todos os 4 SHA-256 conferidos byte a byte, contagens exatas (`37`, `4501/26`, `101`, `1`), classificações honestas (`IMPLEMENTED_PENDING_REVIEW`, `INTEGRATED`, `DEFERRED` para módulos legados sem alegar remoção inexistente), sem falsas alegações de `VERIFIED`. |

### Exact Weighted Mean Calculation
$$\text{Weighted Mean} = (9.5 \times 0.25) + (9.5 \times 0.20) + (9.5 \times 0.20) + (9.2 \times 0.20) + (9.5 \times 0.15) = 2.375 + 1.900 + 1.900 + 1.840 + 1.425 = \mathbf{9.44 / 10}$$

- **Minimum Dimension Score:** `9.2` (`>= 9.0`)
- **Weighted Mean:** `9.44` (`>= 9.0`)
- **Open P0 / P1 Findings:** `0` P0, `0` P1
- **Decision:** **`APPROVED`**

---

## 4. Findings (P0 / P1 / P2) with `file:line`

### P0 — Critical Blockers
*None (`0`).*

### P1 — Mandatory Blockers
*None (`0`).*

### P2 — Non-Blocking Hardening & Operational Notes

1. **[P2-1] `verify_license_provenance` uses a small denylist for `ai-generated:<model>` slugs**
   - **Location:** `renderer/app/studio/domain/asset_registry.py:63-65,85-91`
   - **Observation:** While every real non-commercial/NC/ND/negated license string (`"non-commercial"`, `"not commercial"`, `"cc-by-nc-nd-4.0"`, `"stolen-cc0-pirated"`, `"not public domain"`, `"gerado por terceiro sem autorizacao"`, etc.) is properly rejected (`False`), the `ai-generated:` branch allows any slug matching `^[a-z0-9][a-z0-9._:/-]*$` outside `_DISALLOWED_AI_TOKENS` (`6` substrings), so synthetic prefixed strings such as `"ai-generated:cc-by-nc-nd-4.0"` or `"ai-generated:not-commercial"` still evaluate to `True`.
   - **Suggested Follow-Up (Non-Blocking):** Expand `_DISALLOWED_AI_TOKENS` (or regex word/hyphen boundaries for `nc`, `nd`, `not-commercial`, `noncommercial`) and/or normalize adapter-generated AI license tags in `adapters/license_mapping.py` while restricting `ImportExternalMedia` to explicit open/commercial license identifiers.

2. **[P2-2] `QaHandler` default wiring (`scene_repair=None`) and retry attempt accounting**
   - **Location:** `renderer/app/studio/application/production.py:466-486`, `renderer/app/studio/composition/wiring.py:748-752`
   - **Observation:** `QaHandler` is genuinely integrated with `compute_selective_regeneration`, `plans`, `start_render`, `run_render`, and `max_regeneration_attempts` (fail-closed at cap, preserving `$0.00` spend and cache reuse). In `wiring.py`, `scene_repair` defaults to `None` (appropriate under `$0.00` ceiling so automated QA cannot trigger unguarded paid image regeneration), and manual stage retry after exhaustion relies on `context.execution.attempt` (still strictly bounded by `max_regeneration_attempts`).
   - **Suggested Follow-Up (Non-Blocking):** When automated local/offline repair strategies are introduced in future slices, wire an explicit budget-guarded `scene_repair` adapter and optionally persist cumulative regeneration counts across manual stage retries.

---

## 5. Compatibility, Contracts & Rollback Check

- **`QaReport` v1/v2 & Golden Contracts:** All contract, legacy-read, and QA suites pass inside the `4501 passed` canonical regression (`exit 0`). `_collect_caption_sync_checks` strictly obeys `QaCoverage` fail-closed semantics.
- **Cache Hash Stability (`G2`):** Verified `plan_graph` and `music_params` (`bpm=122, seed=7`) remain byte-identical when `creative_brief` is `None` or `{}`.
- **Unit Test Stub Updates (`tests/test_publication_execution.py:75`, `tests/test_publishing.py:57`):** Replacing dummy `"Pexels License"` with canonical `"Free Stock"` in adapter-isolated application stubs preserves all assertions and coverage; full-stack `Studio` wiring continues accepting `"Pexels License"` and `"Pixabay Content License"` via `normalize_vendor_license`.
- **Rollback:** Zero new DB migrations (`49/49` unchanged); complete rollback is a clean `git revert` with zero destructive state migration.
