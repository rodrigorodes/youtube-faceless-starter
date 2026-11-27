# PC-01 Independent Review Report (`PC-01.01` & `PC-01.02` — Edit Integrity)

- **Reviewer / Model:** `pc01-reviewer` (`gemini-4-neon-high`) — Independent Review (**Round 2 Final**)
- **Executor / Model Reviewed:** `pc01-executor` (`gemini-4-hydrogen-medium`)
- **Branch / Base HEAD / Diff Audited:** `develop` @ `6b6dfbe8c6472af1ad4cba8afa1163f421907a31` + working tree diff (`14` product/test tracked files modified, `+712/-67`; `3` new product/test files: `0055_scene_edit_revision.sql`, `tests/test_pc01_edit_integrity.py`, `tests/e2e_ux/test_pc01_browser_integrity.py`; container hash `05f4f2cd00b859d9`, `50/50` migrations)
- **Protected `main` / DEV Ports / Budget:** `main` == `42700cb331165a68455173a91c463d4733292cfd` (strictly untouched), DEV ports `8000`/`5678` untouched, zero leftover E2E/`8100` containers, `$0.00` external API spend, `STUDIO_PUBLICATION_ENABLED=0`
- **Review History:**
  - **Round 1:** `REJECTED` (`PC-01.01`: `8.565/10`, `PC-01.02`: `7.740/10`) due to `P0-PC01-1`, `P1-PC01-1`, `P1-PC01-2`.
  - **Round 2 (Current):** **`APPROVED`** — All `3` blocking findings verified closed in `git diff` + independent live execution; `0` P0, `0` P1 open.
    - **`PC-01.01`:** **`9.350 / 10`** (min dimension `9.2` >= `9.0`; `0` P0, `0` P1) → **`APPROVED`**
    - **`PC-01.02`:** **`9.300 / 10`** (min dimension `9.2` >= `9.0`; `0` P0, `0` P1) → **`APPROVED`**

---

## 1. Round 2 Independent Live Verification (Executed by Reviewer)

### 1.1 Container PostgreSQL, Golden & DB Suite
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh \
    tests/test_pc01_edit_integrity.py tests/test_render_golden.py tests/test_db.py -ra -q
  ```
- **Exit Code:** `0`
- **Container Alignment:** `HEAD=6b6dfbe alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=05f4f2cd00b859d9 imagem=05f4f2cd00b859d9`, `migrações: checkout=50 imagem=50`
- **Observed Result:** **`32 passed, 0 skipped`** in `28.64s`
  - `tests/test_pc01_edit_integrity.py`: `9/9 passed` (incl. Round 2 Case C empty-scene legacy CAS race `[200, 409]` and cross-project `POST /scenes/{sid}/media` `403`)
  - `tests/test_render_golden.py`: `8/8 passed` (`git diff tests/test_render_golden.py` = empty; zero hashes altered or relaxed)
  - `tests/test_db.py`: `15/15 passed` (`git diff tests/test_db.py` only appends `"0055_scene_edit_revision"` to the expected migration list)

### 1.2 Independent Host Node.js Suite (`Node.js v26.0.0`)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  python3 -m pytest tests/test_storyboard_js.py tests/test_erro_js.py -ra -v -p no:cacheprovider
  ```
- **Exit Code:** `0`
- **Observed Result:** **`13 passed, 0 skipped`** in `8.66s`
  - `tests/test_storyboard_js.py`: `7/7 passed` (incl. `test_storyboard_js_undo_redo_trim_and_409_conflict` exercising real Undo, Redo, `expected_edit_revision` `2`→`3`, trim clearing/restoration, and `409 Conflict` non-overwrite)
  - `tests/test_erro_js.py`: `6/6 passed`

### 1.3 Guardrails & Clean Stack Verification
- `git rev-parse main HEAD`: `main` == `42700cb331165a68455173a91c463d4733292cfd`, `HEAD` == `6b6dfbe8c6472af1ad4cba8afa1163f421907a31` (zero commits/merges/pushes).
- `docker ps`: only pre-existing DEV containers (`renderer-1` on `8000`, `n8n-1` on `5678`); zero leftover `faceless-e2e-pc01` / port `8100` containers.

---

## 2. Independent Audit Checklist Results (Round 2)

| Area | Status | Audit Evidence |
|---|---|---|
| 1. SQL & Single-Tx Atomicity (`0055_scene_edit_revision.sql`, `media_repo.py`, `editorial_repo.py`, `media.py`) | **PASS** | `save_scene_assets` untouched; `add_and_replace_scene_base_media` runs asset dedup/insert + `scenes.asset_id` + `edit_revision + 1` + `role='base'`-only upsert/delete + `P2-PC00-2` two-step offset (`+(MAX+10000)` → `ROW_NUMBER()`) in ONE PG tx with deterministic lock order (`scenes FOR UPDATE` before `pg_advisory_xact_lock`). Monotonic `edit_revision` closes ABA races; `_UNSET` sentinel restores `IS NOT DISTINCT FROM` CAS when `expected_asset_id=None` (`P1-PC01-1` closed). |
| 2. Validation, Rollback, Orphan Cleanup & Security (`media.py`, `routes.py`) | **PASS** | Trim validation (`isfinite`, `0 <= start < end <= probed.duration_s`) runs before commit; mid-tx fault rolls back entire tx; `is_path_referenced` prevents deleting referenced files; `GetSceneTiming` fixed to match `sa.role == "base"`; `/scenes/{sid}/assets` enforces `_require_video_scene`, numeric bounds (`422`), `belongs_to_other_project` (`403`), and `edit_revision` CAS (`409`); `SwapSceneMedia` + `POST /scenes/{sid}/media` now enforce `belongs_to_other_project` → `403` (`P1-PC01-2` closed). |
| 3. RenderPlan, Cache & Golden Compatibility (`render.py`, `render_plan*.py`, `render_cache.py`, `render_plan_ffmpeg.py`) | **PASS** | `StartRender` `input_hash` includes all `scene_assets` (base trim + overlays + motion/transitions) while keeping legacy hash when empty; `visual_fingerprint` appends `extra_trim` only when set; `test_render_golden.py` `8/8` untouched and passing; selective cache invalidation proven for Scene 0 vs Scene 1. |
| 4. Undo/Redo, Persistence & Frontend (`panel_video_workspace.py`, `panel_video_storyboard_js.py`, `test_storyboard_js.py`, `test_pc01_browser_integrity.py`) | **PASS** | `STORYBOARD_JS` carries `expected_edit_revision` in `reconcile()`, `pickCandidate()`, and `doImportMedia()`, clears/restores trim on undo/redo, and surfaces `409` without silent overwrite. No existing test assertions weakened. Host Node VM suite (`13/13`, `0 skipped`) and isolated Playwright Desktop+Mobile E2E (`1/1`, real Piper+FFmpeg+`ffprobe`) verified (`P0-PC01-1` closed). |

---

## 3. Finding Disposition (Round 1 → Round 2)

### Closed Blocking Findings (`0` P0 / `0` P1 Open)
1. **`P0-PC01-1` — CLOSED (`tests/test_storyboard_js.py:591-661`, `evidence/pc01/pc01-execution-evidence.md:61-84`):**
   - Registered `#btn-undo-cenas` (`data-a="undo-v3"`) and `#btn-redo-cenas` (`data-a="redo-v3"`) in the Node test DOM and reused existing template `trim-start`/`trim-end` inputs; verified Undo, Redo, `expected_edit_revision`, and `409` non-overwrite in real host `Node.js v26.0.0` (`13 passed, 0 skipped`, `exit 0`). Evidence accurately separates container (`172 passed, 0 skipped`) vs host Node (`13 passed, 0 skipped`) runs.
2. **`P1-PC01-1` — CLOSED (`renderer/app/studio/adapters/postgres/media_repo.py:14,111,125-126,150`, `tests/test_pc01_edit_integrity.py:698-725`):**
   - Added `_UNSET = object()` sentinel for `expected_asset_id` in `add_and_replace_scene_base_media` so `expected_asset_id=None` enforces `(scene_row["asset_id"] or None) is None` (`IS NOT DISTINCT FROM`). Case C 2-connection `Barrier(2)` empty-scene legacy CAS race passes with `[200, 409]`.
3. **`P1-PC01-2` — CLOSED (`renderer/app/studio/application/media.py:296-297`, `renderer/app/studio/api/routes.py:1704-1713`, `tests/test_pc01_edit_integrity.py:445-449`):**
   - Added `belongs_to_other_project(asset.id, video.project_id)` guard in `SwapSceneMedia.execute` raising `PermissionError`, mapped to `HTTPException(403, str(exc))` in `swap_scene_media`. Negative cross-project `403` test passes.

### Non-Blocking Recommendations (`P2` — Documented for Follow-Up Waves)
- **`P2-PC01-1` (`media_repo.py:232-237`, `panel_video_storyboard_js.py:539-564`):** When `SwapSceneMedia` runs with `apply_trim=False` (e.g., `pickCandidate`), `media_repo.py` keeps the old asset's `start_s`/`end_s` trim row while returning `trim_start_s=None, trim_end_s=None` to the client. Consider clearing base trim on asset swap without trim or returning persisted base trim.
- **`P2-PC01-2` (`media.py:727-746`, `tests/test_pc01_edit_integrity.py:576-586`):** `_compensate_failed_import` checks `find(cache_key)` and `is_path_referenced(path)` outside `pg_advisory_xact_lock(hashtextextended(cache_key, 0))` (narrow cross-scene TOCTOU if two scenes concurrently upload identical bytes+license). Harden in `PC-06.02`.
- **`P2-PC01-3` (`render_plan_compiler.py:352-357`, `render_plan_builder.py:461-474`):** `Shot.asset_trim_start_s`/`asset_trim_end_s` properly invalidates `visual_fingerprint` and `StartRender.input_hash`, while FFmpeg's `trim=start=...` filter still reads `shot.asset_offset_ticks` (default `0`). Wire offset/trim duration into FFmpeg compilation in `PC-04.01` with duration-clamp safety against `render_compiler.py:473`.
- **`P2-PC01-4` (`routes.py:1940-1946`, `editorial_repo.py:449-470`, `media_repo.py:94`):** `import_scene_media` re-reads `scenes(vid)` post-commit for `edit_revision`; `save_scene_assets` and legacy `add_and_swap_scene_asset` do not increment `edit_revision`.

---

## 4. Final Rubric Scoring (`QUALITY-RUBRIC.md` — Round 2)

### 4.1 `PC-01.01` — Single-Transaction Base Replace, Overlay Preservation & Unified Scene CAS

| Dimension | Weight | Score | Evidence & Findings |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **9.5** | Single-tx base replace, overlay preservation (with/without trim), `P2-PC00-2` `position=0` two-step offset, ABA `409`, empty-scene legacy CAS `[200, 409]`, `GetSceneTiming` `role='base'` fix, and `StartRender` `input_hash` verified in real PG. |
| Arquitetura e simplicidade | 20% | **9.3** | Additive `0055_scene_edit_revision.sql` with non-destructive rollback, `save_scene_assets` untouched, deterministic lock ordering (`scenes FOR UPDATE` before advisory lock), clean `_UNSET` sentinel. |
| Testes e regressão | 20% | **9.4** | `9/9` real PG & concurrency tests (3 `Barrier(2)` races, fault-injection rollback, ABA `409`, cross-project `403`/`404` on `/assets` & `/media`, restart reload), `test_render_golden.py` `8/8` untouched, `test_db.py` `15/15`, container suite `172/172` (`0 skipped`). |
| Segurança, orçamento e confiabilidade | 20% | **9.2** | Fail-closed trim bounds vs `ProbedMedia.duration_s` & `isfinite`, cross-project isolation enforced (`403`/`404`) across `/assets` and `/media`, `is_path_referenced` orphan guard, `$0.00` API spend, `STUDIO_PUBLICATION_ENABLED=0`, `0` P0/P1 open (`P2-PC01-2` documented). |
| Evidências e operação | 15% | **9.3** | Complete migration + rollback SQL, accurate container (`05f4f2cd00b859d9`, `50/50` migrations, `0 skipped`) vs host Node (`0 skipped`) reporting, verified clean stack & `main` untouched. |

- **Exact Unrounded Weighted Average (`PC-01.01`):**
  `0.25×9.5 + 0.20×9.3 + 0.20×9.4 + 0.20×9.2 + 0.15×9.3 = 2.375 + 1.860 + 1.880 + 1.840 + 1.395` = **`9.350 / 10`**
- **Applicable Gates:** `G1` (PASS), `G2` (PASS), `G4` (PASS)
- **Final Decision (`PC-01.01`):** **`APPROVED`**

### 4.2 `PC-01.02` — Undo/Redo with Scene Revision, Selective Cache & Real Browser Integrity

| Dimension | Weight | Score | Evidence & Findings |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **9.3** | `STORYBOARD_JS` carries `expected_edit_revision`, clears/restores trim on undo/redo, surfaces `409` without overwrite; selective `visual_fingerprint` invalidation preserves `test_render_golden.py` `8/8` (`P2-PC01-1`, `P2-PC01-3` documented). |
| Arquitetura e simplicidade | 20% | **9.3** | Additive optional `asset_trim_start_s`/`asset_trim_end_s` on `Shot`/`StoryboardScene`, vanilla JS updates without SPA rewrite, zero regressions on golden fixtures or legacy callers. |
| Testes e regressão | 20% | **9.4** | Independently verified in real host `Node.js v26.0.0` (`13 passed, 0 skipped`, incl. Undo + Redo + `expected_edit_revision` + `409`), container PG/Golden/DB (`32 passed, 0 skipped`), and isolated Playwright Desktop (`1280x800`) + Mobile (`390x844`) E2E (`1 passed`, real Piper+FFmpeg+`ffprobe`). |
| Segurança, orçamento e confiabilidade | 20% | **9.2** | `409` conflict/rollback paths prevent silent overwrite, `$0.00` spend, `STUDIO_PUBLICATION_ENABLED=0`, isolated E2E stack (`8100`) verified torn down (`0` leftover containers), `0` P0/P1 open. |
| Evidências e operação | 15% | **9.3** | Accurate separation of container, host Node, and Playwright E2E commands, exit codes, hashes, and skip counts (`0 skipped` across both Python container and host Node runs). |

- **Exact Unrounded Weighted Average (`PC-01.02`):**
  `0.25×9.3 + 0.20×9.3 + 0.20×9.4 + 0.20×9.2 + 0.15×9.3 = 2.325 + 1.860 + 1.880 + 1.840 + 1.395` = **`9.300 / 10`**
- **Applicable Gates:** `G2` (PASS), `G3` (PASS), `G4` (PASS), `G5` (PASS — real Node + isolated Playwright Desktop & Mobile)
- **Final Decision (`PC-01.02`):** **`APPROVED`**
