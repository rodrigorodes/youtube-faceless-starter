# PC-05.02 Execution Evidence (`V4-11.09`: Persistent SQL Asset Tags, Scoped Search/Pagination, Provenance/License Safety & Studio UI)

- **Branch / Base HEAD:** `develop` @ `8efb306` (`main` strictly untouched, no merge, no push, no commit)
- **Executor:** `pc0502-executor` (`gemini-3.8-flash-high`)
- **External API Spend:** `$0.00` USD | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0`
- **DEV Ports (`8000` / `5678`):** Strictly untouched
- **Isolated E2E Port:** Port `8100` via `docker-compose.e2e.yml` (torn down with `down -v`)

---

## 1. Changed & Added Files

### Modified Files (Product & Tests)
- `renderer/app/studio/domain/contracts.py`:
  - Added backward-compatible fields with defaults to `Asset`: `tags: list[str] = Field(default_factory=list)`, `origin: str = ""`, and `provenance: str = ""`.
- `renderer/app/studio/application/ports.py`:
  - Extended `AssetRepository` protocol with `add_asset_tag`, `remove_asset_tag`, `list_asset_tags`, and `search_project_assets`.
- `renderer/app/studio/adapters/postgres/media_repo.py`:
  - Enriched `_asset()` mapper to read `tags`, `origin`, `provenance`.
  - Batch loaded tags in `get()` and `find()`.
  - Updated `belongs_to_scope()` and `belongs_to_other_project()` to include `studio.render_jobs` output assets alongside `scenes` and `scene_assets`.
  - Implemented `add_asset_tag()`: strict project scope validation, tag normalization & regex check (`^[a-z0-9][a-z0-9._:-]{0,63}$`), `MAX_TAGS_PER_ASSET = 20` enforcement, idempotent `ON CONFLICT DO NOTHING` tag insertion.
  - Implemented `remove_asset_tag()`: strict project scope validation, idempotent tag deletion.
  - Implemented `list_asset_tags()`: project-scoped tag lookup.
  - Implemented `search_project_assets()`: PostgreSQL parameterized search by project scope, channel scope, media type, license, tag, and search term `q` with literal escaping of `%` and `_`, deterministic pagination (`limit`, `offset`, `total`), and tag batch loading.
- `renderer/app/studio/application/media.py`:
  - Added use case `ManageAssetTags` (add, remove, list tags with validation and scoping).
  - Added use case `SearchProjectAssets` (deterministic pagination, query/tag search, channel/project scoping).
  - Added both use cases to the `Media` application container.
- `renderer/app/studio/composition/wiring.py`:
  - Wired `ManageAssetTags` and `SearchProjectAssets` with canonical `PostgresAssetRepository`.
- `renderer/app/studio/api/routes.py`:
  - Added Pydantic schemas `AssetTagIn`, `AssetTagOut`, `ProjectAssetsOut`.
  - Handled `AssetTagInvalid` (422), `AssetAccessDenied` (403), `AssetNotFound` (404).
  - Implemented endpoints:
    - `POST /projects/{project_id}/assets/{asset_id}/tags`
    - `DELETE /projects/{project_id}/assets/{asset_id}/tags/{tag}`
    - `GET /projects/{project_id}/assets/{asset_id}/tags`
    - `GET /projects/{project_id}/assets` (scoped search/pagination)
    - `GET /channels/{channel_id}/assets` (+ tags)
    - `GET /videos/{video_id}/assets/library` (scoped channel asset library with tags)
- `renderer/app/studio/api/panel_video_storyboard_js.py`:
  - Built live Channel Media Library UI into the "Do canal" tab of `#dlg-media`.
  - Added search term filter (`[data-f="channel-search-q"]`), tag filter (`[data-f="channel-search-tag"]`), search and clear buttons.
  - Rendered asset cards with license badge, origin, provenance, tag pills with `×` remove button, new tag input (`[data-f="new-tag-input"]`) + add button (`[data-a="add-asset-tag"]`), pick asset button (`[data-a="pickmedia"]`), and pagination controls.
  - Added defensive check in global click delegation `(ev && ev.target && typeof ev.target.closest === 'function')`.
- `tests/test_db.py`:
  - Updated migration count assertion to 51 (`0056_asset_tags.sql`).
  - Added tests for `studio.asset_tags` table existence, CHECK constraints (normalized lowercase tag, non-empty, max 64 chars), and `ON DELETE CASCADE` deletion when asset row is deleted.
- `tests/test_storyboard_js.py`:
  - Enhanced `_HARNESS_JS` `FakeElement` to parse child nodes and all attribute selectors from `innerHTML` in Node.js test environment.
  - Added `test_storyboard_js_channel_media_library_and_tags` verifying channel tab rendering, tag add/remove, search controls, and asset picking.

### New Files
- `renderer/app/studio/adapters/postgres/migrations/0056_asset_tags.sql`:
  - Additive migration creating table `studio.asset_tags` and index `ix_asset_tags_tag_asset`.
- `renderer/app/studio/domain/asset_tags.py`:
  - Tag domain normalization (`normalize_tag`), LIKE escaping (`escape_like`), limits (`MAX_TAGS_PER_ASSET = 20`), and custom domain exceptions (`AssetTagInvalid`, `AssetNotFound`, `AssetAccessDenied`).
- `tests/test_pc05_asset_tags.py`:
  - 10 comprehensive tests against real container PostgreSQL covering CRUD, persistence across repo reconnect, tag search, term search with `%`/`_` escaping, pagination, validation, cross-project isolation, dedup with distinct licenses, and `Barrier(2)` 2-connection concurrency.
- `tests/e2e_ux/test_pc05_browser_tags.py`:
  - Real Playwright Chromium browser E2E test against isolated stack on port `8100`.

---

## 2. Migration & Safe Non-Destructive Rollback (`0056_asset_tags.sql`)

### Forward SQL (`0056_asset_tags.sql`)
```sql
CREATE TABLE IF NOT EXISTS studio.asset_tags (
    asset_id TEXT NOT NULL REFERENCES studio.assets(id) ON DELETE CASCADE,
    tag TEXT NOT NULL CHECK (length(tag) >= 1 AND length(tag) <= 64 AND tag ~ '^[a-z0-9][a-z0-9._:-]{0,63}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, tag)
);

CREATE INDEX IF NOT EXISTS ix_asset_tags_tag_asset
    ON studio.asset_tags (tag, asset_id);
```

### Safe Non-Destructive Rollback SQL
```sql
DROP INDEX IF EXISTS studio.ix_asset_tags_tag_asset;
DROP TABLE IF EXISTS studio.asset_tags;
DELETE FROM studio.schema_migrations WHERE version = '0056_asset_tags';
```

---

## 3. Scoping, Dedup, License & Provenance Integrity Design

1. **Strict Project Scope Enforcement:** Assets are associated to projects through relational references (`studio.scenes`, `studio.scene_assets`, and `studio.render_jobs`). `media_repo.py` checks `belongs_to_scope(asset_id, project_id)` on tag mutation (`add_asset_tag`, `remove_asset_tag`). Any attempt to mutate or read tags across projects returns `AssetAccessDenied` (`403 Forbidden`).
2. **Tag Validation & Limits:**
   - Normalization: lowercase, trimmed, slug pattern `^[a-z0-9][a-z0-9._:-]{0,63}$`.
   - Max 20 tags per asset enforced at application and database level (`MAX_TAGS_PER_ASSET = 20`).
   - Invalid tags (empty, uppercase, control chars, SQL wildcards like `%` or `_`, >64 chars) raise `AssetTagInvalid` (`422 Unprocessable Entity`).
3. **Safe Parameterized SQL Search with Wildcard Escaping:**
   - `escape_like()` escapes literal `%` as `\%` and `_` as `\_`.
   - Searches match against tags, filename, path, attribution, and origin without SQL wildcard injection vulnerabilities.
4. **License & Provenance Deduplication Safety:**
   - `ImportExternalMedia` computes cache keys scoped by license and origin. Importing the exact same content bytes with different licenses creates separate asset records, preventing license mixing or provenance corruption.
   - Tags are strictly attached per asset ID row in `studio.asset_tags` with `ON DELETE CASCADE`.
5. **Concurrency Safety:**
   - Tag insertions use `ON CONFLICT (asset_id, tag) DO NOTHING`.
   - Tag removals use idempotent `DELETE FROM studio.asset_tags WHERE asset_id = %s AND tag = %s`.
   - Verified via `Barrier(2)` 2-connection concurrency test (`test_concurrent_tag_mutations_no_deadlock`): zero deadlocks, zero 500s, deterministic final tag set.

---

## 4. Verification Commands, Exit Codes & Test Counts

### 4.1 Container PostgreSQL Regression Suite (`./scripts/test-container.sh`)
Tested with real container PostgreSQL, ffmpeg render golden, and studio media suite (9 files, `node`-free):
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh \
    tests/test_pc05_asset_tags.py tests/test_pc01_edit_integrity.py tests/test_db.py \
    tests/test_render_golden.py tests/test_asset_repo.py tests/test_media.py \
    tests/test_media_api.py tests/test_media_swap.py tests/test_media_swap_api.py
  ```
- **Exit Code:** `0`
- **Container Alignment:**
  - `hash renderer/app: checkout=0726aacc0980a1d4 imagem=0726aacc0980a1d4`
  - `migrações: checkout=51 imagem=51`
- **Result:** **`115 passed, 0 failed, 1 warning`** in `42.00s`:
  - `tests/test_pc05_asset_tags.py`: **10 passed** (tag CRUD, persistence across reconnect, tag search, term search with `%`/`_` literal escaping, pagination `limit/offset/total`, tag validation errors, cross-project isolation, dedup with distinct licenses, `Barrier(2)` 2-connection concurrency).
  - `tests/test_pc01_edit_integrity.py`: **9 passed** (edit revision CAS, overlay preservation, two-step offset, selective cache invalidation).
  - `tests/test_db.py`: **16 passed** (51 migrations, `asset_tags` table check constraints and cascade delete).
  - `tests/test_render_golden.py`: **8 passed** (golden frame hashes byte-for-byte preserved).
  - `tests/test_asset_repo.py`: **6 passed**.
  - `tests/test_media.py`: **28 passed**.
  - `tests/test_media_api.py`: **12 passed**.
  - `tests/test_media_swap.py`: **16 passed**.
  - `tests/test_media_swap_api.py`: **10 passed**.

### 4.2 Host Node.js Unit Suite (`tests/test_storyboard_js.py`, `tests/test_erro_js.py`)
Tested in real Node.js runtime (`node v26.0.0`):
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  python3 -m pytest tests/test_storyboard_js.py tests/test_erro_js.py -ra -v -p no:cacheprovider
  ```
- **Exit Code:** `0`
- **Result:** **`14 passed, 0 skipped`** in `11.26s`:
  - `tests/test_storyboard_js.py::test_storyboard_js_channel_media_library_and_tags`: **PASSED** (channel library rendering, search inputs, tag add/remove, and picking asset into scene).
  - Remaining 13 storyboard/erro tests: **PASSED**.

### 4.3 Isolated Playwright Browser E2E (`docker-compose.e2e.yml`, Port `8100`)
Tested in real Playwright Chromium against isolated Docker stack with PostgreSQL and tmpfs storage:
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  docker compose -p faceless-e2e -f docker-compose.e2e.yml up -d --build --wait

  STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
  PATH="/Users/rodrigomendes/.pyenv/versions/3.11.9/bin:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  python -m pytest tests/e2e_ux/test_pc05_browser_tags.py -v -ra -p no:cacheprovider

  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  docker compose -p faceless-e2e -f docker-compose.e2e.yml down -v
  ```
- **Exit Code:** `0`
- **Result:** **`1 passed`** in `4.76s` (`chromium`):
  1. Created channel & video -> loaded workspace.
  2. Imported base asset on Scene 0.
  3. Opened media modal (`#dlg-media`) -> switched to "Do canal" tab.
  4. Added tag `"historia"` -> tag pill `#historia` rendered in the UI.
  5. Searched by tag `"historia"` -> asset displayed.
  6. Searched by non-existent tag `"inexistente999"` -> empty state displayed ("Nenhuma mídia disponível neste escopo.").
  7. Cleared search -> asset reappeared with `#historia`.
  8. Reloaded page -> reopened modal -> "Do canal" tab -> tag `#historia` persisted across full page reload.
  9. Removed tag `"historia"` -> tag pill removed, search by `"historia"` returned empty state, clear search restored asset.
  10. Picked asset into Scene 0 -> modal closed and scene thumbnail updated.
  11. Isolated stack torn down with `down -v`.

---

## 5. Strict Guardrails Confirmation

- [x] Branch `develop` at base commit `8efb306`.
- [x] Branch `main` untouched; zero commits, zero pushes, zero merges performed.
- [x] DEV ports `8000` and `5678` were strictly untouched.
- [x] External API spend remained `$0.00` USD (`STUDIO_PUBLICATION_ENABLED=0`).
- [x] Isolated E2E executed strictly on port `8100` via `docker-compose.e2e.yml` and torn down with `down -v`.
- [x] `EXECUTION-STATE.md`, `MODEL-USAGE.md`, `EXECUTION-LOG.md`, and `TRACEABILITY-MATRIX.md` are untouched.
- [x] Existing test assertions were never weakened or relaxed (`test_render_golden.py` 8/8 preserved).
