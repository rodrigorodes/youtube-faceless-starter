# PC-05.02 Independent Review Report (`V4-11.09` — Persistent SQL Asset Tags, Scoped Search/Pagination, Provenance/License Safety & Studio UI)

- **Reviewer / Model:** `pc0502-reviewer` (`gemini-4-carbon-high`) — Independent Review (**Round 1**)
- **Executor / Model Reviewed:** `pc0502-executor` (`gemini-3.8-flash-high`)
- **Branch / Base HEAD / Diff Audited:** `develop` @ `8efb3069735ce2186ffc19cc882748e11b981c5e` + working tree diff (`9` tracked product/test files modified, `+946/-26`; `4` new product/test files: `renderer/app/studio/adapters/postgres/migrations/0056_asset_tags.sql`, `renderer/app/studio/domain/asset_tags.py`, `tests/test_pc05_asset_tags.py`, `tests/e2e_ux/test_pc05_browser_tags.py`, plus `evidence/pc05/pc05-02-execution-evidence.md`; container hash `0726aacc0980a1d4`, `51/51` migrations)
- **Protected `main` / DEV Ports / Budget:** `main` == `42700cb331165a68455173a91c463d4733292cfd` (strictly untouched), DEV ports `8000`/`5678` untouched, zero leftover E2E/`8100` containers (`docker ps` verified), `$0.00` external API spend, `STUDIO_PUBLICATION_ENABLED=0`, tracking docs (`EXECUTION-STATE.md`, `MODEL-USAGE.md`, `EXECUTION-LOG.md`, `TRACEABILITY-MATRIX.md`) untouched.
- **Round 1 Verdict:** **`REJECTED`**
  - **Exact Unrounded Weighted Average (`PC-05.02`):** **`8.010 / 10`** (minimum dimension `7.8` < `9.0`)
  - **Open Blocking Findings:** **`1` P0 (`P0-PC0502-1`), `3` P1 (`P1-PC0502-1`, `P1-PC0502-2`, `P1-PC0502-3`)**, plus `3` non-blocking `P2` hardening items.

---

## 1. Independent Live Verification (Executed by Reviewer)

### 1.1 Container PostgreSQL & Migration Suite (`./scripts/test-container.sh`)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh tests/test_pc05_asset_tags.py tests/test_db.py -ra -q
  ```
- **Exit Code:** `0`
- **Container Alignment:** `HEAD=8efb306 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=0726aacc0980a1d4 imagem=0726aacc0980a1d4`, `migrações: checkout=51 imagem=51`
- **Observed Result:** **`26 passed, 0 skipped, 1 warning`** in `7.63s`
  - `tests/test_pc05_asset_tags.py`: `10/10 passed`
  - `tests/test_db.py`: `16/16 passed` (zero existing assertions weakened)

### 1.2 Independent Host Node.js Suite (`tests/test_storyboard_js.py`, `tests/test_erro_js.py`)
- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  python3 -m pytest tests/test_storyboard_js.py tests/test_erro_js.py -ra -q -p no:cacheprovider
  ```
- **Exit Code:** `0`
- **Observed Result:** **`14 passed, 0 skipped`** in `11.16s`
  - `tests/test_storyboard_js.py`: `8/8 passed` (zero existing assertions weakened)
  - `tests/test_erro_js.py`: `6/6 passed`

### 1.3 Stack Hygiene & Contract Snapshot Audit
- **`docker ps`:** Confirmed zero leftover `faceless-e2e` or port `8100` containers; pre-existing DEV containers on `8000`/`5678` untouched.
- **Contract Snapshot Audit (`contracts/v1/asset.schema.json` vs `renderer/app/studio/domain/contracts.py`):** Confirmed stale committed schema (`tags`, `origin`, `provenance` added to `Asset` at `contracts.py:162-164` without regenerating `contracts/v1/asset.schema.json` via `scripts/export_contracts.py` — see `P0-PC0502-1`).

---

## 2. Independent Audit Checklist Results (Round 1)

| Area | Status | Audit Evidence |
|---|---|---|
| 1. Additive SQL Migration & Rollback (`0056_asset_tags.sql`) | **FAIL (`P1-PC0502-1`)** | Additive `CREATE TABLE IF NOT EXISTS studio.asset_tags` + `CREATE INDEX IF NOT EXISTS` + DB `CHECK` constraint + safe rollback SQL, zero parallel in-memory catalog; however, `project_id` was omitted from `studio.asset_tags` (`PRIMARY KEY (asset_id, tag)` instead of `(project_id, asset_id, tag)` per `PC-00-AUDIT-AND-PLAN.md:201`), allowing cross-project tag leakage/mutation on globally cached generated/stock assets. |
| 2. Tag Normalization, `ILIKE` Escaping & Concurrency (`asset_tags.py`, `media_repo.py`) | **PASS (with `P2-PC0502-1`)** | Strict `normalize_tag` (`^[a-z0-9][a-z0-9._:-]{0,63}$`), `escape_like` escaping `\`, `%`, `_` paired with parameterized `ILIKE %(like_q)s ESCAPE '\\'`, `ON CONFLICT DO NOTHING` idempotent insert. Minor `P2` race on `MAX_TAGS_PER_ASSET = 20` check without `FOR UPDATE` row lock. |
| 3. Project/Channel Scope Isolation & Provenance/License Dedup (`media_repo.py`, `media.py`, `routes.py`) | **FAIL (`P1-PC0502-1`, `P1-PC0502-3`)** | Imported media with distinct licenses creates separate rows (`test_dedup_license_and_provenance_integrity`); however, globally cached `ProduceAssets`/`_materialize` assets share `asset_id` across projects and leak/expose tags across projects (`P1-PC0502-1`), and `/channels/{channel_id}/assets*` always `404`s on real `ChannelProfile.id` due to non-existent `uc.channel_profiles` (`P1-PC0502-3`). |
| 4. Studio Channel Library UI & Backward Compatibility (`contracts.py`, `routes.py`, `panel_video_storyboard_js.py`) | **FAIL (`P0-PC0502-1`, `P1-PC0502-2`)** | `contracts/v1/asset.schema.json` was not regenerated (`P0-PC0502-1`, breaking `test_contracts_snapshot.py`); Channel Library UI (`panel_video_storyboard_js.py:498`) builds asset file URLs with `?video_id=${VID}` instead of `?project_id=${channelProjectId}`, causing `403 Forbidden` on every preview of assets belonging to other videos in the same channel (`P1-PC0502-2`). |
| 5. Test Integrity (`test_db.py`, `test_storyboard_js.py`, `test_pc05_asset_tags.py`, `test_pc05_browser_tags.py`) | **FAIL (`P0-PC0502-1`, `P1-PC0502-1..3`)** | Zero existing test assertions relaxed/weakened; however, `test_contracts_snapshot.py` was not verified, `/channels/{cid}/assets` had 0 HTTP test calls despite docstring claim, and multi-video same-channel preview + shared-`asset_id` cross-project tag isolation were untested. |

---

## 3. Detailed Findings & Required Fixes (`file:line`)

### Blocking Findings (`P0` / `P1` — Must Fix Before Approval)

#### 1. `P0-PC0502-1` — Committed Contract Schema Drift Breaks `tests/test_contracts_snapshot.py` (`G2` / `G6`)
- **Files & Lines:**
  - `renderer/app/studio/domain/contracts.py:162-164`
  - `contracts/v1/asset.schema.json:17-67`
  - `tests/test_contracts_snapshot.py:10-12` (`scripts/export_contracts.py:17,21-22`)
- **Defect:** `Asset` in `contracts.py:162-164` added three optional fields (`tags`, `origin`, `provenance`), changing `Asset.model_json_schema()`. `contracts/v1/asset.schema.json` (`additionalProperties: false`) was never updated via `scripts/export_contracts.py`, causing `tests/test_contracts_snapshot.py::test_committed_contracts_match_code` to fail deterministically (`contracts/v1/asset.schema.json desatualizado: rode scripts/export_contracts.py`).
- **Exact Fix Required:**
  1. Run `python scripts/export_contracts.py` to update `contracts/v1/asset.schema.json` (and `docs/10-arquitetura.md` if affected).
  2. Run `./scripts/test-container.sh tests/test_contracts_snapshot.py tests/test_architecture.py` and include exit code `0` in evidence.

#### 2. `P1-PC0502-1` — Cross-Project Tag Leakage & Mutation When Globally Cached Assets Share `studio.assets.id` (`G2` / `G4`)
- **Files & Lines:**
  - `renderer/app/studio/adapters/postgres/migrations/0056_asset_tags.sql:6-14`
  - `renderer/app/studio/adapters/postgres/media_repo.py:44-59,365-436,475-496,532-542`
  - `renderer/app/studio/application/media.py:83-90,342-345` (`tests/test_media.py:197`)
- **Defect:** By design (`tests/test_media.py:197`), `ProduceAssets` (`media.py:83`) and `SwapSceneMedia._materialize` (`media.py:342`) use a global `asset_cache_key` without `project_id`, so two distinct projects/channels generating the same prompt or materializing the same stock candidate link the **same `studio.assets.id`** into their scenes. Because `0056_asset_tags.sql:6-11` omitted `project_id` (`PRIMARY KEY (asset_id, tag)` instead of `PRIMARY KEY (project_id, asset_id, tag)` specified in `PC-00-AUDIT-AND-PLAN.md:201`) and `media_repo.py` queries `studio.asset_tags` by `asset_id` alone:
  - Tags created by Project A (`"segredo-cliente-a"`) leak into Project B's `search_project_assets(project_id=proj_b)`, `list_asset_tags(aid, project_id=proj_b)`, and `get(aid)`.
  - Project B can filter by Project A's private tags and **delete Project A's tags** via `DELETE /projects/{proj_b}/assets/{aid}/tags/segredo-cliente-a` (since `belongs_to_scope(aid, project_id=proj_b)` is `True`).
  - Additionally, `SwapSceneMedia._materialize` (`media.py:342`) omits `license` from `asset_cache_key` (`{"aspect": aspect, "license": ...}`), risking license/provenance conflation if two stock candidates share URL/media_id under distinct licenses; note: keep `ProduceAssets` `asset_cache_key` (`media.py:83`) unchanged so `tests/test_media.py:197` stays green!
- **Exact Fix Required:**
  1. Update `0056_asset_tags.sql:6-14` to include `project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE` with `PRIMARY KEY (project_id, asset_id, tag)` and `CREATE INDEX IF NOT EXISTS ix_asset_tags_project_tag_asset ON studio.asset_tags (project_id, tag, asset_id);`, and update `tests/test_db.py:178-210` accordingly.
  2. Require/scope `project_id` across `add_asset_tag`, `remove_asset_tag`, `list_asset_tags`, and `search_project_assets` (`media_repo.py:365-543`), filtering every `studio.asset_tags` read/write/count/search (`at.project_id = %(project_id)s` / `WHERE project_id = %s AND asset_id = %s`). Do **not** populate unscoped cross-project tags in `get(aid)` / `find(key)` (`media_repo.py:44-59`) when no `project_id` is given.
  3. Add a real PostgreSQL test in `tests/test_pc05_asset_tags.py` where Project A and Project B both link the **exact same `asset_id`** in their scenes: prove Project A's tags do NOT appear in Project B's `search_project_assets` or `list_asset_tags`, and Project B's `remove_asset_tag` does NOT delete Project A's tag.

#### 3. `P1-PC0502-2` — Channel Media Library UI Thumbnails Return `403 Forbidden` for Assets From Other Videos in the Same Channel (`G1` / `G5`)
- **Files & Lines:**
  - `renderer/app/studio/api/panel_video_storyboard_js.py:472,498,545-551`
  - Interacts with `renderer/app/studio/api/routes.py:2252-2270`, `renderer/app/studio/application/media.py:438-451`, `renderer/app/studio/adapters/postgres/media_repo.py:319-342`
- **Defect:** In the **"Do canal"** tab (`mediaTab === 'channel'`), `loadChannelMedia()` (`panel_video_storyboard_js.py:542-551`) fetches `/studio/videos/${VID}/assets/library`, which returns `{ project_id, assets, ... }` across **all videos** of the channel/project. However, `loadChannelMedia()` ignores `res.project_id`, and `renderChannelBody()` (`panel_video_storyboard_js.py:498`) hardcodes:
  ```js
  var fileUrl = '/studio/assets/' + encodeURIComponent(a.id) + '/file?video_id=' + encodeURIComponent(VID);
  ```
  When Video 2 opens "Do canal" to browse/pick an asset originally imported/generated in Video 1 of the **same** channel, `GET /studio/assets/${a.id}/file?video_id=${video_2_id}` checks `belongs_to_scope(a.id, video_id=video_2_id)` (`media_repo.py:319-342`), which is `False` until `a.id` is linked to Video 2 — returning **`403 Forbidden`** on every cross-video channel thumbnail (`<img>` / `<video>`). (`tests/e2e_ux/test_pc05_browser_tags.py` missed this because it only tested 1 video where `aid` was already linked to `VID`.)
- **Exact Fix Required:**
  1. Store `channelProjectId = res.project_id || ''` in `loadChannelMedia()` (`panel_video_storyboard_js.py:472,545-551`) and build `fileUrl` in `renderChannelBody()` (`panel_video_storyboard_js.py:498`) using `project_id` (`'/studio/assets/' + encodeURIComponent(a.id) + '/file?' + (channelProjectId ? 'project_id=' + encodeURIComponent(channelProjectId) : 'video_id=' + encodeURIComponent(VID))`).
  2. Assert `?project_id=p_test` in `tests/test_storyboard_js.py:700-818` and add a 2-video same-project test in `tests/test_pc05_asset_tags.py` (and/or `tests/e2e_ux/test_pc05_browser_tags.py`) proving Video 2 lists, previews (`GET /studio/assets/{aid}/file?project_id={pid}` -> `200`), and picks (`POST /studio/videos/{vid2}/scenes/{sid}/media` -> `200`) Video 1's asset.

#### 4. `P1-PC0502-3` — `/channels/{channel_id}/assets*` Endpoints Always Return `404` for Real `ChannelProfile.id` Due to Non-Existent `uc.channel_profiles` (`G1` / `G2`)
- **Files & Lines:**
  - `renderer/app/studio/api/routes.py:1369-1381,1462-1522`
  - `renderer/app/studio/application/use_cases.py:113-136`
  - `renderer/app/studio/application/media.py:772-829` & `renderer/app/studio/composition/wiring.py:586-587`
  - `tests/test_pc05_asset_tags.py:23,564-621`
- **Defect:** `routes.py:1369-1381` defines `_resolve_project_id(uc, project_or_channel_id)` checking `hasattr(uc, "videos")` and `hasattr(uc, "channel_profiles")`. Neither attribute exists on `UseCases` (`use_cases.py:113-136` defines `channel_profiles_repo`, and `VideoRepository` lives on use-case instances). When a caller invokes `GET /studio/channels/{channel_id}/assets` or `POST/DELETE /studio/channels/{channel_id}/assets/{asset_id}/tags` with a real `ChannelProfile.id` (from `POST /projects/{pid}/channels` or `GET /channels`, where `profile.id != profile.project_id`, matching `PATCH /channels/{profile_id}` at `routes.py:3439`), `_resolve_project_id` returns `profile.id` unresolved, causing `ManageAssetTags` / `SearchProjectAssets` to fail with **`404 project not found`**. Moreover, `tests/test_pc05_asset_tags.py:23` claims full REST verification of `/channels/{cid}/assets`, but `test_api_rest_endpoints` (`lines 564-621`) makes zero requests to `/channels/{cid}/assets*`.
- **Exact Fix Required:**
  1. Inject `channels: ChannelProfileRepository | None = None` into `ManageAssetTags` and `SearchProjectAssets` (`media.py:772-829`, wired in `wiring.py:586-587` with `channel_repo`) to resolve `project_or_channel_id` cleanly in the application layer (`videos.get_project(id)` first; else `channels.get(id).project_id`; else raise `ProjectNotFound`), and also expose `GET /channels/{channel_id}/assets/{asset_id}/tags` and `GET /videos/{video_id}/assets/{asset_id}/tags` for endpoint parity.
  2. Add real HTTP tests in `tests/test_pc05_asset_tags.py` creating a `ChannelProfile` (`profile.id != proj.id`) and verifying `GET/POST/DELETE /studio/channels/{profile.id}/assets*` (`200` in-scope, `403` cross-channel, `404` unknown channel).

---

### Non-Blocking Hardening Recommendations (`P2`)

1. **`P2-PC0502-1` (`renderer/app/studio/adapters/postgres/media_repo.py:369-435`):**
   - Lock the parent asset row (`SELECT 1 FROM studio.assets WHERE id = %s FOR UPDATE`) in `add_asset_tag` before checking `count >= MAX_TAGS_PER_ASSET` so two concurrent `READ COMMITTED` transactions at `count == 19` cannot insert a 21st tag; also reuse the open `conn` for scope checks instead of opening nested connections inside `with self._connect() as conn:`.
2. **`P2-PC0502-2` (`renderer/app/studio/api/routes.py:1431,1445,1507,1521,1582,1601`, `panel_video_storyboard_js.py:483,520,567,590`):**
   - Return normalized `normalize_tag(tag)` in `AssetTagOut.tag` / `AssetTagOut.removed` instead of raw input, and strip optional leading `#` in UI tag filter/input (`tagVal.replace(/^#+/, '')`) since UI pills display `#tag`.
3. **`P2-PC0502-3` (`renderer/app/studio/application/media.py:580-586`):**
   - Include normalized `attribution` and `source_url` in `ImportExternalMedia` `scope_params` so identical bytes imported under `CC-BY-4.0` from two different authors retain distinct provenance records.

---

## 4. Rubric Scoring (`QUALITY-RUBRIC.md` — Round 1)

| Dimension | Weight | Score | Evidence & Findings |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **7.8** | Tag CRUD, SQL search (`tag` & `q` with `%`/`_` escaping), and pagination work on single-video project paths (`26/26` container, `14/14` Node), but Channel Library UI thumbnails break (`403`) across videos in the same channel (`P1-PC0502-2`) and `/channels/{channel_id}/assets*` fails (`404`) for real `ChannelProfile.id` (`P1-PC0502-3`). |
| Arquitetura e simplicidade | 20% | **8.0** | Reuses canonical `PostgresAssetRepository` and existing `#dlg-media` modal (zero parallel in-memory catalog, zero new SPA), additive `0056_asset_tags.sql` with rollback; penalized by stale `contracts/v1/asset.schema.json` (`P0-PC0502-1`), missing `project_id` on `studio.asset_tags` (`P1-PC0502-1`), and broken `UseCases` attribute probing in `routes.py` (`P1-PC0502-3`). |
| Testes e regressão | 20% | **7.9** | `tests/test_pc05_asset_tags.py` (`10/10`), `tests/test_db.py` (`16/16`), and host Node suite (`14/14`, `0 skipped`) pass with zero weakened assertions; however, `tests/test_contracts_snapshot.py` fails on stale schema (`P0-PC0502-1`), `/channels/{cid}/assets` has `0` test calls despite docstring claim (`P1-PC0502-3`), and shared-`asset_id` cross-project tag isolation + 2-video channel preview were untested. |
| Segurança, orçamento e confiabilidade | 20% | **7.8** | Parameterized `ILIKE ... ESCAPE '\\'`, strict `TAG_REGEX` + DB `CHECK`, `ON CONFLICT DO NOTHING`, `$0.00` spend, `STUDIO_PUBLICATION_ENABLED=0`, DEV ports untouched; blocked by cross-project tag read/search/delete leakage on globally cached `studio.assets` rows (`P1-PC0502-1`; plus `P2-PC0502-1`, `P2-PC0502-3`). |
| Evidências e operação | 15% | **8.8** | Clear forward/rollback SQL, container hash (`0726aacc0980a1d4`, `51/51` migrations), separated container/Node/Playwright runs, clean `8100` teardown confirmed via `docker ps`; minor deduction for unrun contract snapshot check and overstated `/channels/{cid}/assets` test coverage claim. |

- **Exact Unrounded Weighted Average (`PC-05.02`):**
  `0.25×7.8 + 0.20×8.0 + 0.20×7.9 + 0.20×7.8 + 0.15×8.8 = 1.950 + 1.600 + 1.580 + 1.560 + 1.320` = **`8.010 / 10`**
- **Applicable Gates:** `G1` (FAIL — `P1-PC0502-2`, `P1-PC0502-3`), `G2` (FAIL — `P0-PC0502-1`, `P1-PC0502-1`, `P1-PC0502-3`), `G4` (FAIL — `P1-PC0502-1`), `G5` (PARTIAL/FAIL — `P1-PC0502-2`), `G6` (FAIL — `P0-PC0502-1`)
- **Final Decision (`PC-05.02` — Round 1):** **`REJECTED`** (Requires fixing `P0-PC0502-1`, `P1-PC0502-1`, `P1-PC0502-2`, `P1-PC0502-3` and independent Round 2 re-verification).
