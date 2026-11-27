# PC-01 Execution Evidence (`PC-01.01` & `PC-01.02` — Edit Integrity)

- **Branch / Base HEAD:** `develop` @ `6b6dfbe` (`main` strictly untouched)
- **Executor:** `pc01-executor` (`gemini-4-hydrogen-medium`)
- **External API Spend:** `$0.00` USD | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0`
- **DEV Ports (`8000` / `5678`):** Untouched

---

## 1. Changed & Added Files

### Modified Files (Product & Tests)
- `renderer/app/studio/domain/contracts.py` — Added `edit_revision: int = Field(default=1, ge=1)` to `Scene`.
- `renderer/app/studio/adapters/postgres/media_repo.py` — Added `add_and_replace_scene_base_media` (single PostgreSQL transaction with `FOR UPDATE` scene lock first, `edit_revision` + `asset_id` CAS, `edit_revision` increment, `role='base'`-only upsert/delete, collision-safe two-step offset for `uq_scene_asset_pos` when `position=0` is occupied by an overlay), `is_path_referenced`, `belongs_to_other_project`, and `edit_revision` increment in `swap_scene_asset`.
- `renderer/app/studio/adapters/postgres/editorial_repo.py` — Included `edit_revision` in `_SCENE` / `_read_scenes`; added `FOR UPDATE` + `expected_edit_revision` CAS + `edit_revision` increment to `add_scene_asset` and `delete_scene_asset` (leaving `save_scene_assets` untouched for full-layer callers).
- `renderer/app/studio/application/media.py` — Validated finite/bounded `trim_start_s`/`trim_end_s` against `ProbedMedia.duration_s` before commit; wired `ImportExternalMedia` and `SwapSceneMedia` to `add_and_replace_scene_base_media` with `expected_edit_revision` CAS; hardened `_compensate_failed_import` with `is_path_referenced`; fixed `GetSceneTiming.execute` to match only `role == "base"`.
- `renderer/app/studio/api/routes.py` — Added `expected_edit_revision`, `apply_trim`, `trim_start_s`, `trim_end_s` to `SceneMediaChoiceIn`/`SceneMediaOut`, `import_scene_media`, and `swap_scene_media`; guarded `GET/POST/DELETE /videos/{video_id}/scenes/{scene_id}/assets` with `_require_video_scene`, cross-project isolation (`403`/`404`), numeric bounds (`422`), and `edit_revision` CAS (`409`).
- `renderer/app/studio/application/render.py` — Included all `scene_assets` (including `role='base'` trim and overlay motion/transitions) in `StartRender.execute` `input_hash` while preserving legacy hashes when `scene_assets` is empty.
- `renderer/app/studio/domain/render_plan.py`, `render_plan_builder.py`, `render_cache.py`, `adapters/render_plan_ffmpeg.py` — Propagated optional `asset_trim_start_s`/`asset_trim_end_s` on `Shot` & `visual_fingerprint` ONLY when set (preserving `test_render_golden.py` 8/8 hashes byte-for-byte) so changing Scene 0 base trim invalidates ONLY Scene 0 visual cache.
- `renderer/app/studio/api/panel_video_workspace.py` & `panel_video_storyboard_js.py` — Serialized `edit_revision` into workspace state; wired `doImportMedia`, `reconcile`, `pickCandidate`, and undo/redo (`#btn-undo-cenas`, `#btn-redo-cenas`) to carry `expected_edit_revision`, restore/clear trim cleanly, and surface `409` conflicts without silent overwrite.
- `tests/test_db.py` — Updated expected migration list to include `0055_scene_edit_revision`.
- `tests/test_storyboard_js.py` — Added `test_storyboard_js_undo_redo_trim_and_409_conflict` (Node VM).

### New Files
- `renderer/app/studio/adapters/postgres/migrations/0055_scene_edit_revision.sql`
- `tests/test_pc01_edit_integrity.py` (9 real PostgreSQL & application tests)
- `tests/e2e_ux/test_pc01_browser_integrity.py` (isolated Playwright Desktop + Mobile E2E)

---

## 2. Migration & Non-Destructive Rollback (`0055_scene_edit_revision.sql`)

```sql
ALTER TABLE studio.scenes
    ADD COLUMN IF NOT EXISTS edit_revision BIGINT NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS ix_scene_assets_scene_role
    ON studio.scene_assets (scene_id, role);
```

**Manual Non-Destructive Rollback:**
```sql
DROP INDEX IF EXISTS studio.ix_scene_assets_scene_role;
ALTER TABLE studio.scenes DROP COLUMN IF EXISTS edit_revision;
DELETE FROM studio.schema_migrations WHERE version = '0055_scene_edit_revision';
```

---

## 3. Single-Transaction, Collision-Safe Offset, Concurrency & Fault-Injection Design

1. **Lock Ordering:** `add_and_replace_scene_base_media` acquires `SELECT id, asset_id, edit_revision FROM studio.scenes WHERE id = %s AND video_id = %s FOR UPDATE` **before** acquiring `pg_advisory_xact_lock(hashtextextended(cache_key, 0))`, preventing lock-inversion deadlocks.
2. **Unified CAS:** Checks both `expected_edit_revision` (closing `A -> B -> A` ABA races) and `expected_asset_id`, returning `409 Conflict` (`StateConflict`) on mismatch before any mutation.
3. **Overlay Preservation & `P2-PC00-2` Two-Step Offset:** Only `role = 'base'` rows in `studio.scene_assets` are updated or deleted. When inserting a new `role = 'base'` row at `position = 0` while an overlay occupies `position = 0`, all `role <> 'base'` rows are shifted by `+ (MAX(position) + 10000)` and then normalized to `1..k` via `ROW_NUMBER() OVER (ORDER BY position, created_at, id)` inside the same transaction, preventing `UniqueViolation` on `uq_scene_asset_pos`.
4. **Fault Injection & Orphan Cleanup:** Any DB error mid-transaction rolls back `studio.assets`, `studio.scenes`, and `studio.scene_assets` atomically. `_compensate_failed_import` checks `is_path_referenced(path)` before unlinking on disk so live files referenced by other asset rows are never deleted.

---

## 4. Exact Verification Commands, Exit Codes & Results

### 4.1 Container PostgreSQL, Golden, Media & Studio Suite (12 files, `node`-free)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh \
    tests/test_pc01_edit_integrity.py tests/test_render_golden.py tests/test_db.py \
    tests/test_media.py tests/test_media_api.py tests/test_media_swap.py \
    tests/test_media_swap_api.py tests/test_rec_02_media_import.py \
    tests/test_rec_03_studio_routes.py tests/test_panel_scene_multimedia.py \
    tests/test_studio_api.py tests/test_video_storyboard_v3.py -ra -q
  ```
- **Exit Code:** `0`
- **Container Alignment:** `hash renderer/app: checkout=05f4f2cd00b859d9 imagem=05f4f2cd00b859d9`, `migrações: checkout=50 imagem=50`
- **Result:** **`172 passed, 0 skipped`** in `67.88s` (`test_pc01_edit_integrity.py`: `9/9 passed` incl. `P2-PC00-2` `position=0` two-step offset, `Barrier(2)` 2-conn race + empty-scene legacy CAS race `[200, 409]`, fault-injection rollback, ABA `409`, cross-project `403`/`404` on `/media` and `/assets`, selective cache; `test_render_golden.py`: `8/8` golden parity preserved; `test_db.py`: `100% passed`). Note: `test_storyboard_js.py` and `test_erro_js.py` require `node` (not installed in the Python test container) and are executed on host below.

### 4.2 Host Node JS Unit Suite (`node v26.0.0`)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  python3 -m pytest tests/test_storyboard_js.py tests/test_erro_js.py -ra -v -p no:cacheprovider
  ```
- **Exit Code:** `0`
- **Result:** **`13 passed, 0 skipped`** in `8.74s` (includes `test_storyboard_js_undo_redo_trim_and_409_conflict` verifying Undo, Redo, trim clearing/restoration, `expected_edit_revision` propagation, and `409` non-overwrite).

### 4.3 Isolated Playwright Browser E2E (Desktop `1280x800` + Mobile `390x844`, Port `8100`)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" bash -c '
  set -euo pipefail
  trap "docker compose -p faceless-e2e-pc01 -f docker-compose.e2e.yml down -v >/dev/null 2>&1 || true" EXIT
  docker compose -p faceless-e2e-pc01 -f docker-compose.e2e.yml down -v >/dev/null 2>&1 || true
  E2E_PORT=8100 docker compose -p faceless-e2e-pc01 -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" python3 -m pytest tests/e2e_ux/test_pc01_browser_integrity.py -v -s -p no:cacheprovider
  '
  ```
- **Exit Code:** `0`
- **Result:** **`1 passed`** in `23.04s` (`chromium`):
  - Desktop (`1280x800`): created channel/video -> imported base PNG -> attached 2 overlays (PNG + MP4 PiP) -> replaced base without trim -> replaced base with MP4 + trim `(0.2s, 1.4s)` -> clicked Undo (reverted base + cleared trim, overlays preserved) -> clicked Redo (restored MP4 + trim `0.2s, 1.4s`, overlays preserved) -> reloaded page (persisted) -> resumed production run -> real Piper TTS + FFmpeg render -> downloaded `/studio/videos/{id}/file` -> verified `video` and `audio` streams via `ffprobe`.
  - Mobile (`390x844`): reloaded storyboard -> `0` duplicate IDs, `0` horizontal overflow.
  - Stack torn down cleanly via `docker compose -p faceless-e2e-pc01 -f docker-compose.e2e.yml down -v`.
