# REC-03.03 Independent Review (`github-copilot/gemini-4-neon`, High — Round 1)

- **Reviewer / Real Model:** Independent Reviewer — `github-copilot/gemini-4-neon` (high)
- **Target Slice:** `REC-03.03` (`R10` — Lacunas de pipeline: cache segmentado, QA + regeneração seletiva limitada, restart, Creative Direction → Brief → RenderPlan, captions/export, licença fail-closed)
- **Repository / Branch:** `/Users/rodrigomendes/youtube-faceless-starter` on `develop` (`main` untouched @ `42700cb331165a68455173a91c463d4733292cfd`)
- **Base HEAD:** `7ded0f5d58d655df41df6dda32f479308489314b` + uncommitted working tree (read-only audit; zero production/test edits, zero commits/pushes)
- **Reviewed Artifact Hashes (SHA-256):**
  - `git diff` (full working tree, 10 tracked files, `+135 / -11`): `0f54afcf90e5ca9caab7969be8c29dd94e9c61bff639db76fc69006820934143`
  - `git diff renderer/`: `0f54afcf90e5ca9caab7969be8c29dd94e9c61bff639db76fc69006820934143`
  - `tests/test_rec_03_pipeline_integration.py` (untracked): `76740305de2cb6ad6d954318985f26ca1df4d696be2a608ae9f1e3697f9913c2`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-03/rec-03-03-pipeline-evidence.md` (untracked): `2ff23ddb4167698fe307a5dff56b20ac0086a59d35f66ba4b54161798f766a55`
- **External Paid API Spend:** `$0.00` | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`) | **DEV Ports (`8000`/`5678`):** untouched
- **Review Round:** Round 1
- **Final Decision:** **`REJECTED`**
  - **Weighted Mean:** **`3.95 / 10`** (min dimension **`3.0`** < `9.0`)
  - **Open Blockers:** **`3` P0**, **`6` P1**, `2` P2
  - **Absolute Rubric Blocks Triggered (`QUALITY-RUBRIC.md:22-26`):**
    1. **Regressão na suíte canônica completa (Gate G6 reprovado):** `tests/test_architecture.py` falha em 2 testes (`exit code 1`) por violação direta de fronteira (`pexels`/`pixabay` em `domain/asset_registry.py`).
    2. **Segurança de licença comprometida (Gate G4 reprovado):** substring match em `verify_license_provenance` permite bypass trivial (`"non-commercial"`, `"cc-by-nc-nd-4.0"`, `"stolen-cc0-pirated"`, `"not public domain"`), enfraquecendo publicação e `REC-02.03/04`.
    3. **Capability falsa / evidência contradita pelo código:** `rec-03-03-pipeline-evidence.md` afirma integrações que **não existem** no diff (`compute_selective_regeneration` em `QaHandler`/`ProductionCoordinator`, `creative_brief` em `GenerateLongScript`/`RenderPlan`, rotas usando `export_captions_from_plan`, bloqueio em `publication_block_reason`, aposentadoria de `render_engine.py`/`asset_registry.py`/`studio_workbench.py`).
    4. **Teste de QA não valida comportamento real (mutação sobreviveu):** deletar todo o cálculo de `caption_sync_drift_ms` em `adapters/quality_ffmpeg.py` mantém `test_pipeline_qa_evaluator_persists_caption_sync_drift` passando (`exit 0`).

---

## 1. Independent Verification Re-Executed

All commands were executed independently on the exact working tree (`HEAD 7ded0f5` + diff SHA-256 `0f54afcf...`) with:
`PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`

### 1.1 Focused REC-03 Container Suite
- **Command:**
  ```bash
  ./scripts/test-container.sh tests/test_rec_03_pipeline_integration.py tests/test_rec_03_studio_routes.py -ra
  ```
- **Alignment:** `HEAD=7ded0f5 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=7b1cb426bb68f2c1 imagem=7b1cb426bb68f2c1`, `migrações: checkout=49 imagem=49`
- **Observed Result:** `36 passed, 1 warning in 17.84s` (`9` in `test_rec_03_pipeline_integration.py` + `27` in `test_rec_03_studio_routes.py`) | **Exit code:** `0`

### 1.2 Related Subsystems Container Suite (Architecture, Publishing, QA, Captions, Cache, Coordinator, Media, Pilot)
- **Command:**
  ```bash
  ./scripts/test-container.sh \
    tests/test_architecture.py tests/test_publishing.py tests/test_publication_execution.py \
    tests/test_publish_api.py tests/test_publication_api.py tests/test_render_api.py \
    tests/test_quality.py tests/test_quality_overlay.py tests/test_quality_ffmpeg_v2.py \
    tests/test_qa_report.py tests/test_qa_report_v2_contract.py tests/test_qa_legacy_read.py \
    tests/test_v4_quality_multimodal.py tests/test_captions_ass.py tests/test_caption_position_v3.py \
    tests/test_render_cache.py tests/test_render_cache_v2.py tests/test_render_reuse.py \
    tests/test_render_regeneration.py tests/test_production_coordinator.py tests/test_production_handlers.py \
    tests/test_v4_asset_management.py tests/test_rec_02_media_import.py tests/test_v4_studio_real_flow_pilot.py -ra
  ```
- **Observed Result:** **`2 failed, 488 passed, 1 warning in 129.09s (0:02:09)`** | **Exit code:** **`1`**
- **Failures:**
  - `FAILED tests/test_architecture.py::test_domain_and_application_do_not_name_media_vendors` (`renderer/app/studio/domain/asset_registry.py` cita `'pexels'`)
  - `FAILED tests/test_architecture.py::test_domain_does_not_name_concrete_suppliers` (`('domain/asset_registry.py', 51/52/55/56/85, 'pexels'|'pixabay')`)

### 1.3 Full Canonical Container Suite (Gate G6)
- **Command:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alignment:** `HEAD=7ded0f5`, `hash renderer/app: checkout=7b1cb426bb68f2c1 imagem=7b1cb426bb68f2c1`, `migrações: checkout=49 imagem=49`
- **Observed Result:** **`2 failed, 4498 passed, 26 skipped, 1 warning in 709.44s (0:11:49)`** (total collected: `4526`) | **Exit code:** **`1`**
- **Failures (2):**
  - `FAILED tests/test_architecture.py::test_domain_and_application_do_not_name_media_vendors`
  - `FAILED tests/test_architecture.py::test_domain_does_not_name_concrete_suppliers`
- **Skips Breakdown (26):** `3` Playwright browser tests (`test_reference_browser.py`, `ve08/test_composition_functional.py`, `ve08/test_storyboard_functional.py` — `pytest_playwright` absent in slim container) + `23` Node.js tests (verified on host in §1.4).

### 1.4 Host Node.js / Panel / Workflow Suite
- **Command:**
  ```bash
  python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
    tests/test_falha_producao.py tests/test_publicacao_acao.py tests/test_workflow_analytics.py \
    tests/test_workflow_publish.py tests/test_workflow_trends.py -ra
  ```
- **Observed Result:** `101 passed in 9.33s` | **Exit code:** `0`

### 1.5 Isolated Playwright Chromium E2E (`docker-compose.e2e.yml`, Port `8100`, `tmpfs`)
- **Commands:**
  ```bash
  E2E_PORT=8100 docker compose -p faceless-e2e-rec0303 -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
    STUDIO_E2E_USER="e2e" STUDIO_E2E_PASSWORD="e2e-senha-descartavel" \
    python3 -m pytest tests/e2e_ux/test_rec_03_studio_browser.py -v -ra
  docker compose -p faceless-e2e-rec0303 -f docker-compose.e2e.yml down -v
  lsof -i :8100
  ```
- **Observed Result:** `1 passed in 9.04s` | **Exit code:** `0`
- **Teardown Proof:** Containers `faceless-e2e-rec0303-renderer-e2e-1`, `faceless-e2e-rec0303-postgres-e2e-1` and network `faceless-e2e-rec0303_default` removed; `lsof -i :8100` confirmed `PORT_8100_CLOSED`.

### 1.6 Forensic Security, Coverage & Out-of-Repo Mutation Checks
1. **License Bypass Proof (read-only Python against `domain/asset_registry.py`):**
   - `verify_license_provenance('non-commercial') -> True`
   - `verify_license_provenance('not commercial') -> True`
   - `verify_license_provenance('prohibited commercial use') -> True`
   - `verify_license_provenance('cc-by-nc-nd-4.0') -> True`
   - `verify_license_provenance('cc-by-nc-4.0') -> True`
   - `verify_license_provenance('stolen-cc0-pirated') -> True`
   - `verify_license_provenance('not public domain') -> True`
   - `verify_license_provenance('stolen from pexels') -> True`
   - `verify_license_provenance('gerado por terceiro sem autorizacao') -> True`
   - `verify_license_provenance('non-commercial ai-generated') -> True`
2. **Sanitizer False-Positive Proof (read-only Python against `FORBIDDEN_COMMAND_PATTERNS`):**
   - `'Vídeo sobre auto-afirmação e motivação'` -> `MATCH='-af'` (HTTP 422)
   - `'A pré-afirmação científica do método'` -> `MATCH='-af'` (HTTP 422)
   - `'Re-afirmar o compromisso educacional'` -> `MATCH='-af'` (HTTP 422)
   - `'Usar estilo color-preset cinematográfico'` -> `MATCH='-preset'` (HTTP 422)
   - `'Tutorial de comandos bash para iniciantes'` / `'Como fazer requisições com curl em APIs REST'` / `'História do projeto FFmpeg em código aberto'` -> HTTP 422.
3. **Out-of-Repo Temporary Copy Mutation Proof (`/private/var/folders/.../T/opencode/rec0303-mut*`, deleted after run):**
   - **Mutation A (SURVIVED — test is vacuous):** Deleted the entire `caption_sync_drift_ms` calculation block in `adapters/quality_ffmpeg.py:272-284` in a temp copy and executed `test_pipeline_qa_evaluator_persists_caption_sync_drift` -> **PASSED** (`MUTATION_A_SURVIVED`), proving the test does not verify that drift was measured or persisted.
   - **Mutation B (KILLED):** Mutated `export_captions_from_plan` to return `""` -> `test_pipeline_export_captions_from_plan` **FAILED** (`exit 1`), confirming that unit test checks output text (though the function itself has 0 production callers).

---

## 2. Per-Requirement Classification (Gate G1)

| Requisito | Status Honesto | Consumidor Real / Call Sites Verificados | Evidência e Lacunas Reais |
|---|---|---|---|
| **(a) Cache segmentado por cena** (mudança de 1 cena preserva segmentos das demais) | **`INTEGRATED` (parcial)** | `PlanFfmpegRenderer.render` + `PostgresRenderPlanRepository` (existente) | Prova real com FFmpeg + Postgres para vídeo (`artifact_sha256`, `artifact_uri`, `mtime_ns` das cenas 1 e 2 preservados). **Lacunas:** chama `PlanFfmpegRenderer` diretamente sem `RunRender` (não prova skip de TTS / cache de narração), não verifica mudança de hash/mtime da cena 0 nem contador de chamadas FFmpeg; `REC-03.03b` (preflight, progresso por shot, cancelamento cooperativo) não foi implementado. |
| **(b) QA defect detection → regeneração seletiva LIMITADA + reavaliação, falha fechada no teto** | **`MODEL_ONLY`** | **0 call sites** de `compute_selective_regeneration` em `renderer/app/` (`QaHandler` e `ProductionCoordinator` intocados) | `test_pipeline_qa_known_defect_triggers_bounded_selective_regeneration` instancia `video_repo`/`plan_repo` sem usá-los e chama `compute_selective_regeneration(None, QaReport(...))` diretamente. Não exercita `ProductionCoordinator`, `QaHandler`, `FfmpegQualityEvaluator`, regeneração nem reavaliação real. A evidência do executor declara integração inexistente. |
| **(c) Restart (novo processo/conexão lê Postgres sem perda/duplicação)** | **`INTEGRATED` (parcial)** | `PostgresVideoRepository`, `PostgresScriptRepository`, `PostgresProductionRunRepository` | Corrige `conn.transaction()` em `repo.py:281,287` e prova releitura de `creative_brief`, cenas/legendas e `EffectiveConfig` + `CreateRunResult.EXISTING` em nova conexão. **Lacuna:** não testa restart do `ProductionCoordinator` nem reuso do cache do `PlanFfmpegRenderer` após reconexão. |
| **(d.1) Creative Direction sanitização + Brief → Script → RenderPlan (identidade congelada)** | **`INTEGRATED` parcial / `MODEL_ONLY` no RenderPlan** | `routes.py:1362-1431`, `GenerateScript` (`editorial.py:475-479`). **0 call sites** em `GenerateLongScript`, `RunRender`, `PlanFfmpegRenderer._build_plan` | `GenerateScript` lê `video.creative_brief` (mas engole erro em `except Exception: pass`). `GenerateLongScript` não lê `creative_brief`. `RenderSpec.creative_brief` nunca é preenchido em `RunRender._render` nem consumido para montar `RenderPlan`. Sanitização em `/direction` causa falsos positivos em português (`"auto-afirmação"`). |
| **(d.2) Captions/Export a partir do RenderPlan + `render.caption_sync` no QA** | **`MODEL_ONLY` (export) / `INTEGRATED` defeituoso (sync)** | `export_captions_from_plan` tem **0 call sites** em `renderer/app/` (`routes.py:2531-2540` inalterado). `FfmpegQualityEvaluator` adiciona drift ad-hoc. | Rotas `/subtitles` e `/subtitles.vtt` não chamam `captions_exporters.py`. `domain/quality.py:464-473` declara `render.caption_sync` em `checks_run` mesmo sem medição (`drift is None`); `quality_ffmpeg.py` engole exceções, retorna `0.0` em erro de `ffprobe` e não chama `check_audio_caption_sync`. Mutação deletando a medição sobrevive ao teste. |
| **(d.3) Licença fail-closed na publicação e importação** | **REGRESSÃO P0 + `INTEGRATED` parcial** | `Approve` (`wiring.py:711`), `ClaimPublication` (`publishing.py:148`). **Ausente** em `RunPublication` e `publication_block_reason`. | Substring match em `domain/asset_registry.py:85-86` quebra fail-closed de publicação e `REC-02.03/04`. Nomes de fornecedores em `domain` quebram `test_architecture.py`. `RunPublication` (caminho efetivo de publicação) e `publication_block_reason` não checam licenças; `Approve`/`ClaimPublication` ignoram `scene_assets` e falham aberto se `assets.get(...)` retornar `None`. |
| **Consolidação / Remoção de duplicados (R10)** | **NÃO EXECUTADO** | `application/render_engine.py`, `application/asset_registry.py`, `application/studio_workbench.py` | Os 3 módulos permanecem intactos no repositório (0 linhas alteradas no diff), contradizendo a seção 2 de `rec-03-03-pipeline-evidence.md`. |

---

## 3. Rubric Scoring (`QUALITY-RUBRIC.md`)

> Threshold: `>= 9.0` on **every** applicable dimension, weighted mean `>= 9.0` (no rounding), and **zero** open P0/P1 findings or absolute blocks.

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **4.0** | Requisito (a) validado parcialmente em `PlanFfmpegRenderer` + Postgres e (c) na camada de repositórios; `GenerateScript` passa a carregar `video.creative_brief`. **Bloqueado:** (b) é `MODEL_ONLY` (`compute_selective_regeneration` com 0 chamadores em `renderer/app/`; `QaHandler`/`ProductionCoordinator` intocados), `CreativeBrief` não chega a `GenerateLongScript` nem a `RenderPlan`, `export_captions_from_plan` tem 0 chamadores, `RunPublication`/`publication_block_reason` não checam licenças, `REC-03.03b` não implementado. |
| Arquitetura e simplicidade | 20% | **5.0** | Não criou serviço/cache/coordenador paralelo; `Approve(..., assets=None)` preserva compatibilidade e `repo.py` usa `conn.transaction()` alinhado ao restante do Postgres. **Bloqueado por P0/P1:** violou fronteira Clean Architecture inserindo `pexels`/`pixabay` em `domain/asset_registry.py` (quebrando `test_architecture.py`); deixou os 3 módulos duplicados intactos apesar de declará-los aposentados; deixou `captions_exporters.py` órfão; `_persist_scenes` acoplado a atributos de `Scene` em parâmetro `SceneDraft`. |
| Testes e regressão | 20% | **4.5** | Reexecução independente: REC-03 focados `36 passed`, Host Node `101 passed`, E2E Playwright isolado `1 passed` (teardown `down -v` verificado). **Bloqueado por P0/P1:** suíte canônica completa **FALHOU** (`2 failed, 4498 passed, 26 skipped`, exit `1` em `test_architecture.py`); teste (b) exercita apenas função pura isolada com `plan=None`; teste de `caption_sync` sobrevive à mutação que remove toda a medição em `quality_ffmpeg.py`; faltam negativos para bypass de licença, falsos positivos PT-BR, drift > 500ms, `RunPublication` e narração/restart do coordenador. |
| Segurança, orçamento e confiabilidade | 20% | **3.0** | Kill switch (`STUDIO_PUBLICATION_ENABLED=0`) intacto e custo externo `$0.00`. **Bloqueado por P0/P1:** substring match em `domain/asset_registry.py:85-86` destrói fail-closed de licenças (`"non-commercial"`, `"cc-by-nc-nd-4.0"`, `"stolen-cc0-pirated"` retornam `True`) afetando publicação e `REC-02.03/04`; `RunPublication` não verifica licenças; `Approve`/`ClaimPublication` falham aberto em asset órfão e ignoram `scene_assets`; `render.caption_sync` falha aberto (declara check sem medir + `except Exception: pass` + `0.0` em erro de `ffprobe`); sanitização em `/direction` rejeita português legítimo (`"auto-afirmação"`). |
| Evidências e operação | 15% | **3.0** | `rec-03-03-pipeline-evidence.md` registra comandos locais e lista alguns arquivos, mas contém **múltiplas declarações factualmente falsas** contraditas pelo `git diff` e pela suíte canônica (`QaHandler`/`ProductionCoordinator`, `GenerateLongScript`/`RenderPlan`, rotas de legendas via `export_captions_from_plan`, `publication_block_reason`, aposentadoria de módulos duplicados, e "100% verde sem regressões" sem executar `test_architecture.py` nem a suíte canônica completa). |

### Exact Weighted Mean Calculation
$$\text{Weighted Mean} = (4.0 \times 0.25) + (5.0 \times 0.20) + (4.5 \times 0.20) + (3.0 \times 0.20) + (3.0 \times 0.15) = 1.00 + 1.00 + 0.90 + 0.60 + 0.45 = \mathbf{3.95 / 10}$$

- **Minimum Dimension Score:** `3.0` (`< 9.0`)
- **Weighted Mean:** `3.95` (`< 9.0`)
- **Decision:** **`REJECTED`**

---

## 4. Findings (P0 / P1 / P2) with `file:line`

### P0 — Critical Blockers

1. **[P0-1] Substring match in `verify_license_provenance` breaks license fail-closed across publication and `REC-02.03/04` import**
   - **Location:** `renderer/app/studio/domain/asset_registry.py:74-87`
   - **Evidence:** Lines `85-86` added:
     `if any(k in normalized for k in ("cc0", "cc-by", "public domain", "free stock", "pexels", "pixabay", "unsplash", "gerad", "ai-generated", "commercial")): return True`
   - **Observed Impact:** Proven in §1.6 that `"non-commercial"`, `"not commercial"`, `"prohibited commercial use"`, `"cc-by-nc-nd-4.0"`, `"cc-by-nc-4.0"`, `"stolen-cc0-pirated"`, `"not public domain"`, `"stolen from pexels"`, `"gerado por terceiro sem autorizacao"`, and `"non-commercial ai-generated"` all return `True`. Because `ImportExternalMedia` (`application/media.py:8,487`) calls `verify_license_provenance`, this also directly regresses the strict allowlist security of `REC-02.03/04`.
   - **Required Fix:** Remove substring matching completely. Enforce strict exact membership against a normalized allowlist of license identifiers (never vendor names in `domain`), rejecting non-commercial/unknown/arbitrary strings fail-closed.

2. **[P0-2] Architecture regression: concrete media vendor names added to `domain` layer, breaking full canonical suite**
   - **Location:** `renderer/app/studio/domain/asset_registry.py:51-56,85`
   - **Evidence:** Adding `"pexels"`, `"pexels license"`, `"pixabay"`, `"pixabay license"` to `domain/asset_registry.py` directly breaks `tests/test_architecture.py::test_domain_and_application_do_not_name_media_vendors` (line 88) and `test_domain_does_not_name_concrete_suppliers` (line 146), causing the full canonical container suite to fail (`exit code 1`).
   - **Required Fix:** Keep `domain/asset_registry.py` vendor-agnostic (standardized license classes such as `cc0`, `cc0-1.0`, `cc-by-4.0`, `public domain`, `free stock`, `commercial stock`, `studio generated`, `own_original`, etc.). Normalize vendor-specific license labels (`Pexels License`, `Pixabay License`, etc.) in the **adapter** layer (e.g., stock media adapters) into canonical domain license strings before persistence/validation.

3. **[P0-3] Requirement (b) (`compute_selective_regeneration`) is `MODEL_ONLY` — zero pipeline integration, contradicted by executor evidence**
   - **Location:** `renderer/app/studio/domain/quality.py:544-598`, `renderer/app/studio/application/production.py:414-436`, `tests/test_rec_03_pipeline_integration.py:311-376`, `docs/.../evidence/rec-03/rec-03-03-pipeline-evidence.md:15`
   - **Evidence:** `grep` across all of `renderer/app/` confirms `compute_selective_regeneration` has **zero call sites**. `application/production.py` was not modified at all (`QaHandler.execute` simply raises `StageExecutionFailed`). The test creates `video_repo`/`plan_repo` without using them and invokes `compute_selective_regeneration(None, QaReport(...))` directly in memory. Yet `rec-03-03-pipeline-evidence.md:15` claims it was integrated into `QaHandler`/`ProductionCoordinator` with selective re-rendering and QA re-evaluation.
   - **Required Fix:** Integrate `compute_selective_regeneration` into the real canonical pipeline (`ProductionCoordinator` / `QaHandler` / render-QA loop) with persisted attempt tracking, selective regeneration restricted to defective scenes while reusing unaffected cached segments, QA re-evaluation, and fail-closed termination at `max_attempts`. Prove it in an integration test exercising the real coordinator/QA/renderer path on disposable Postgres + real FFmpeg (injecting a real defect, e.g., black frame/bad scene, verifying selective re-render + re-eval + fail-closed exhaustion).

---

### P1 — Mandatory Blockers

4. **[P1-1] Effective publication path (`RunPublication` and `publication_block_reason`) does not enforce license fail-closed; `Approve`/`ClaimPublication` fail open on missing asset records and ignore `scene_assets`**
   - **Location:** `renderer/app/studio/application/publication_gate.py:37-61`, `renderer/app/studio/application/publication_execution.py:205-228`, `renderer/app/studio/application/publishing.py:63-68,148-153`
   - **Evidence:** `publication_gate.py` and `publication_execution.py` were not modified; `RunPublication._prepare` (`publication_execution.py:210`) is the effective upload path and never checks asset licenses (despite `rec-03-03-pipeline-evidence.md:17` claiming `publication_block_reason` blocks unverified assets). In `Approve` and `ClaimPublication`, `if ast and not verify_license_provenance(ast.license)` fails open if `self.assets.get(sc.asset_id)` returns `None`, and ignores secondary/overlay assets linked via `studio.scene_assets` (`get_scene_assets`).
   - **Required Fix:** Centralize license verification in `publication_block_reason` (or a shared gate helper invoked by `Approve`, `ClaimPublication`, and `RunPublication._prepare`) checking both primary `sc.asset_id` and `scene_assets` (fail-closed if an attached `asset_id` cannot be resolved or has an unverified license). Keep `RunPublication(enabled=False)` short-circuiting first with zero token/upload calls.

5. **[P1-2] `CreativeBrief` does not flow into `GenerateLongScript` or `RenderPlan`, and `GenerateScript` silently swallows invalid briefs**
   - **Location:** `renderer/app/studio/application/editorial.py:475-479`, `renderer/app/studio/application/longform.py:307-340`, `renderer/app/studio/application/render.py:354-358`, `renderer/app/studio/adapters/render_plan_ffmpeg.py:536-625`
   - **Evidence:** `RenderSpec.creative_brief` (`application/ports.py:726`) has **zero** assignments in `RunRender._render` (`render.py:354-358`) and **zero** readers in `PlanFfmpegRenderer._build_plan` / `build_render_plan`. `GenerateLongScript.execute` never loads `video.creative_brief`. In `GenerateScript.execute`, `except Exception: pass` silently discards malformed briefs. `rec-03-03-pipeline-evidence.md:17` erroneously claims `GenerateLongScript` and `RenderPlan` consume `creative_brief`.
   - **Required Fix:** Propagate persisted `video.creative_brief` into `GenerateLongScript` and `RunRender._render` → `RenderSpec.creative_brief` → `RenderPlan` (affecting plan metadata/pacing/motion/audio hints while keeping frozen `EffectiveConfig` identity unchanged across regenerations), and prove via real test that the generated `RenderPlan` reflects the brief and preserves frozen identity across regenerations. Do not swallow unexpected exceptions silently.

6. **[P1-3] `export_captions_from_plan` / `captions_exporters.py` remains completely disconnected (0 production callers)**
   - **Location:** `renderer/app/studio/adapters/captions_exporters.py:95-125`, `renderer/app/studio/api/routes.py:2531-2540`
   - **Evidence:** `grep` confirms 0 call sites for `export_captions` and `export_captions_from_plan` anywhere in `renderer/app/`. `routes.py:2531-2540` (`/videos/{video_id}/subtitles` and `/subtitles.vtt`) still reads raw `.srt` from disk and calls `domain/publish.py::srt_to_vtt`, contradicting `rec-03-03-pipeline-evidence.md:17`.
   - **Required Fix:** Consolidate caption export cleanly so SRT/VTT export in the canonical render/route flow uses `export_captions_from_plan` from the persisted `RenderPlan` (with backward-compatible fallback for legacy renders lacking a stored plan) and verify via API/route test.

7. **[P1-4] `render.caption_sync` violates QA coverage fail-closed contract and fails mutation testing**
   - **Location:** `renderer/app/studio/domain/quality.py:464-473`, `renderer/app/studio/adapters/quality_ffmpeg.py:81-86,272-284`, `tests/test_rec_03_pipeline_integration.py:676-736`
   - **Evidence:**
     1. `_collect_caption_sync_checks` appends `CHECK_CAPTION_SYNC` to `checks_run` whenever `plan.timeline.subtitles` is non-empty, even if `evidence.media.get("caption_sync_drift_ms")` is `None` — falsely claiming the check ran with no measurement (violating `domain/qa_report.py:20-25`).
     2. `_probe_duration` returns `0.0` on `ffprobe` failure (turning a probe error into a fabricated drift), `FfmpegQualityEvaluator.evaluate` swallows all errors with `except Exception: pass`, and never calls `domain/captions.py::check_audio_caption_sync`.
     3. Out-of-repo mutation proved that deleting lines `272-284` of `quality_ffmpeg.py` still lets `test_pipeline_qa_evaluator_persists_caption_sync_drift` pass (`exit 0`).
   - **Required Fix:** Use `check_audio_caption_sync` with explicit probe error handling (record a coverage gap / `not_verified` when audio duration cannot be probed, never `0.0` or silent `pass`), append `CHECK_CAPTION_SYNC` only when drift was actually measured (or add gap when subtitles exist and drift is missing), persist observed drift evidence in `QaReport`, and add tests for both synced and out-of-sync (`>500ms`) cases that fail if measurement is removed.

8. **[P1-5] Creative direction sanitizer produces false positives on legitimate Portuguese/editorial prose**
   - **Location:** `renderer/app/studio/api/routes.py:1362-1431`, `renderer/app/studio/domain/creative_director.py:25-28`
   - **Evidence:** `FORBIDDEN_COMMAND_PATTERNS` matches `-vf|-af|-preset|-crf` without a preceding whitespace/start-of-string boundary and matches bare words like `bash`, `curl`, `ffmpeg` across all keys/values recursively. Proven in §1.6: legitimate Portuguese phrases such as `"Vídeo sobre auto-afirmação e motivação"`, `"pré-afirmação"`, `"re-afirmar"`, and `"color-preset"` are rejected with HTTP 422.
   - **Required Fix:** Require whitespace/command boundaries before CLI flags (e.g., `(?:^|\s)-(?:filter_complex|vf|af|c:v|c:a|preset|crf)(?:\s|$|=)`) and match shell/command invocation syntax (e.g., `ffmpeg\s+-`, `sh\s+-c`, `rm\s+-rf`, shell metacharacters/pipelines with commands) rather than breaking hyphenated Portuguese words or legitimate educational topics. Add regression tests for both injection attempts and legitimate PT-BR prose (`"auto-afirmação"`, `"pré-afirmação"`, etc.).

9. **[P1-6] Unfulfilled `REC-03.03b` scope, incomplete proofs for (a)/(c), and false claim of retiring duplicate modules**
   - **Location:** `docs/.../evidence/rec-03/rec-03-03-pipeline-evidence.md:21-26`, `tests/test_rec_03_pipeline_integration.py:171-305,382-481`, `renderer/app/studio/application/{render_engine.py,asset_registry.py,studio_workbench.py}`
   - **Evidence:**
     1. The evidence claims `application/render_engine.py`, `application/asset_registry.py`, and `application/studio_workbench.py` were retired/consolidated, yet all three files are completely untouched in `git diff`.
     2. Test (a) does not verify cached narration reuse (`RunRender._cached_narration` / TTS invocation count), does not assert that scene 0's cache hash changed, and does not assert FFmpeg invocation count (`1` scene + concat/final, not `3` scenes).
     3. Test (c) does not verify restart of `ProductionCoordinator` or reuse of cached segments by a new `PlanFfmpegRenderer` instance after reconnecting to Postgres.
     4. `REC-03.03b` items from `REC-00-AUDIT-AND-PLAN.md:347-349` (preflight disk/codec check, per-shot progress on `RenderJob`, cooperative cancellation between shots) were not implemented or explicitly reconciled.
   - **Required Fix:** Either genuinely retire/replace the parallel in-memory duplicates (updating/migrating their unit tests cleanly) or document exact disposition without false claims; strengthen (a) to prove both visual and narration cache reuse + changed hash on scene 0 + call counters; strengthen (c) to prove coordinator + render cache survival across restart; address `REC-03.03b` (preflight/progress/cancel) in the canonical `PlanFfmpegRenderer`/`RunRender` path.

---

### P2 — Non-Blocking Improvements

10. **[P2-1] `_persist_scenes` accepting arbitrary `id`/`asset_id` on `draft` objects**
    - **Location:** `renderer/app/studio/adapters/postgres/editorial_repo.py:212-221`
    - **Observation:** `sc_id = getattr(draft, "id", None) or uuid.uuid4().hex` and `ast_id = getattr(draft, "asset_id", None)` work for existing nullable columns and do not break migrations/old rows, but `SceneDraft` does not declare `id` or `asset_id`. Passing a `Scene` copied from another video could trigger a PK collision or link an asset without project-scope verification. Prefer linking assets in tests via `AssetRepository` (`swap_scene_asset`) or explicitly validating `video_id`/scope if `Scene` reuse is intentional.

11. **[P2-2] Unused DB fixtures and dead repo instances in integration tests**
    - **Location:** `tests/test_rec_03_pipeline_integration.py:323-324,568,676`
    - **Observation:** `test_pipeline_captions_export_and_sync_drift_persisted_in_qa` and `test_pipeline_qa_evaluator_persists_caption_sync_drift` request `(conn, dsn)` without touching PostgreSQL; `test_pipeline_qa_known_defect_triggers_bounded_selective_regeneration` instantiates `video_repo` and `plan_repo` without using them.

---

## 5. Compatibility, Contracts & Rollback Check

- **`Approve` signature compatibility (`application/publishing.py:40`, `composition/wiring.py:711`):** `assets: AssetRepository | None = None` is backward-compatible with legacy callers/tests (`test_publishing.py` 36/36 passed). Kill switch (`RunPublication.enabled=False`) remains intact.
- **`QaReport` v1/v2 & Golden contracts (`test_qa_report.py`, `test_qa_report_v2_contract.py`, `test_qa_legacy_read.py`, `test_quality.py`):** Serialization/deserialization remains green, **except** for the semantic coverage bug in `_collect_caption_sync_checks` (P1-4).
- **`conn.transaction()` in `adapters/postgres/repo.py:281,287`:** Compatible with `psycopg` 3 and consistent with `production_repo.py` / `editorial_repo.py`; fixes missing explicit transaction block on `update_video_creative_brief` and `update_video_pacing_preset`.
- **Rollback:** All changes are uncommitted on `develop` (`0` DB migrations added; `49` migrations unchanged). Reverting or fixing requires zero destructive DB rollback.

---

## 6. Re-Review Entry Criteria (Round 2)

Before requesting Round 2 review, the executor MUST:
1. Resolve **all 3 P0s** and **all 6 P1s** above.
2. Re-run the **full canonical container suite** (`./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q`) and confirm `0 failed` (exit `0`), plus Host Node suite (`exit 0`) and isolated Playwright E2E (`exit 0` + `down -v`).
3. Update `evidence/rec-03/rec-03-03-pipeline-evidence.md` so every single claim matches real code, call sites, and observed outputs with exact SHA-256 and counts.
