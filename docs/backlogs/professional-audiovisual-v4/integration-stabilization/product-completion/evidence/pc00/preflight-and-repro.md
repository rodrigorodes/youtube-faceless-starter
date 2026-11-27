# PC-00 Preflight (`G0`) & Live PC-01 Edit-Integrity Bug Reproduction

- **Timestamp (UTC):** `2026-11-27T09:57Z`
- **Auditor / Role:** `pc00-auditor` (`PC-00.01` & `PC-00.02`, documentary & isolated read-only reproduction only)
- **Repository:** `/Users/rodrigomendes/youtube-faceless-starter`
- **Product Code / Existing Test Modifications:** **ZERO** (`alterações_em_renderer/tests=não`)

---

## 1. Gate `G0` — Git, Isolation, Runtime & Safety Verification

| Check | Exact Command / Source | Observed Output | Status |
|---|---|---|---|
| Active branch & `HEAD` SHA | `git rev-parse HEAD` | `8484b7202d7080d916a501a945bc81a2b51274cf` (`develop`) | **PASS** |
| Remote `origin/develop` SHA | `git rev-parse origin/develop` | `8484b7202d7080d916a501a945bc81a2b51274cf` (in sync) | **PASS** |
| Protected `main` SHA | `git rev-parse main` | `42700cb331165a68455173a91c463d4733292cfd` (**strictly untouched**) | **PASS** |
| Branch divergence (`main...develop`) | `git rev-list --left-right --count main...develop` | `1` (on `main`: `42700cb` merge INT-01..07) / `14` (on `develop`: `5800f46`..`8484b72`) | **PASS** (no merge/rebase) |
| Initial `git status -s` | `git status -s` | Only 4 coordinator tracking files (`?? product-completion/{EXECUTION-LOG,EXECUTION-STATE,MODEL-USAGE,SESSION-HANDOFF}.md`); **0** edits to `renderer/`, `tests/`, `scripts/`, `contracts/`, `workflows/`, `docker-compose*.yml` | **PASS** |
| Docker Engine version | `docker info --format '{{.ServerVersion}}'` | `29.1.3` | **PASS** |
| Host Node.js & Python | `node -v && python3 --version` | `Node v26.0.0` (host), `Python 3.9.6` (system shim) | **PASS** |
| Isolated test image alignment | `./scripts/test-container.sh` | `HEAD=8484b72`, `alterações_em_renderer/tests=não`, `hash renderer/app: checkout=b677160103d832a3 imagem=b677160103d832a3`, `migrações: checkout=49 imagem=49` | **PASS** |
| Container image digests | `docker images --no-trunc` | `faceless-renderer:test` = `sha256:d6c55857bad654ed0a99a7717eb6d45e9fb8cfbd6a1aa7725014d93d6f8017bb`; `faceless-renderer-pytest:test` = `sha256:2be92f04d4f9993c82177e0439e96a95f4ef38c4db3ade4a9fdf18f70b3c811d`; `postgres:16-alpine` = `sha256:81e77a4833487b8132fe4b00bedd39dc3f74b8641e387f19312a48f7de218c2e` | **PASS** |
| Container runtime versions | `docker run --rm --entrypoint sh faceless-renderer-pytest:test -c '...'` | `Python 3.12.16`, `ffmpeg version 7.1.5-0+deb13u1`, `piper-tts==1.8.0`, bundled offline voice `/opt/voices/pt_BR-faber-medium.onnx` (`63,221,984 B`) + `.onnx.json` (`6,257 B`) | **PASS** |
| Disposable PostgreSQL guard | `./scripts/test-container.sh` + `tests/conftest.py` | Ephemeral `postgres:16-alpine` on `--tmpfs /var/lib/postgresql/data`, isolated network `faceless-test-net-<pid>`, 64-hex `/budget-test-proof/proof` verified by `verified_test_connect`, torn down on `EXIT` trap | **PASS** |
| DEV containers / ports `8000` & `5678` | `docker ps` | Pre-existing DEV stack (`youtube-faceless-starter-renderer-1` on `127.0.0.1:8000`, `youtube-faceless-starter-n8n-1` on `127.0.0.1:5678`, `youtube-faceless-starter-postgres-1`) observed running (up 34h–4d) and **strictly untouched**; zero `faceless-e2e-*` containers active | **PASS** |
| Paid API keys & budget ceiling | `env` scan (host & container) + `Settings` | `ZERO_PAID_KEYS_IN_IMAGE`, zero paid provider keys (`OPENAI`/`GEMINI`/`GOOGLE_API`/`ELEVENLABS`/`PEXELS`/`PIXABAY`/`ANTHROPIC`) in shell/image; runtime budget ceiling enforced at `max_cost_video=0.0`, `max_cost_month=0.0`, `budget_guard=True` (`$0.00` spent) | **PASS** |
| Publication kill switch | `Settings` (`renderer/app/studio/composition/settings.py:71,101`) | **IMPORTANT CAVEAT RECORDED:** `Settings.publication_enabled` defaults to `True` in code (`STUDIO_PUBLICATION_ENABLED` defaults to `"1"` if unset); all isolated test/pilot runs MUST explicitly set `STUDIO_PUBLICATION_ENABLED=0` / `publication_enabled=False` (confirmed active in repro log: `publication_enabled=False`, `STUDIO_PUBLICATION_ENABLED=0`). | **PASS** *(with explicit env enforcement)* |

---

## 2. Live Reproduction of PC-01 Edit-Integrity Defect (`P1` Blocker)

### 2.1 Code Inspection Root Cause (`HEAD 8484b72`)
1. **Unconditional `DELETE FROM studio.scene_assets` on base replace:**
   - `renderer/app/studio/application/media.py:602-619` (`ImportExternalMedia._apply_scene_trim`) calls:
     - `self.scripts.save_scene_assets(scene_id, [sa])` when `trim_start_s` and `trim_end_s` are provided (with hardcoded `role="base", motion="none", transition_kind="none"`), and
     - `self.scripts.save_scene_assets(scene_id, [])` when no trim is provided!
   - `renderer/app/studio/adapters/postgres/editorial_repo.py:448-469` (`PostgresScriptRepository.save_scene_assets`) executes `DELETE FROM studio.scene_assets WHERE scene_id = %s` before inserting the passed list, **unconditionally destroying every existing `role="overlay"` (PNG/MP4 PiP), secondary B-roll, motion, and transition row on the scene**.
2. **Split PostgreSQL transactions & ineffective failure compensation:**
   - `renderer/app/studio/application/media.py:578-585` runs `self.assets.add_and_swap_scene_asset(...)` (`media_repo.py:68-101`, Transaction #1 — commits `studio.assets` + `UPDATE studio.scenes SET asset_id = ...`), and only **after** Transaction #1 commits does it invoke `self._apply_scene_trim(...)` (Transaction #2 — `save_scene_assets`).
   - If Transaction #2 fails, Transaction #1 is **not rolled back**; `_compensate_failed_import` (`media.py:621-635`) calls `delete_if_unreferenced(saved.id)`, which returns `False` because `studio.scenes.asset_id` already references `saved.id` from Transaction #1, leaving `studio.scenes.asset_id` permanently mutated and **desynchronized** from `studio.scene_assets`.
3. **CAS coverage gap (ABA & non-asset edits):**
   - `add_and_swap_scene_asset` (`media_repo.py:94-96`) and `swap_scene_asset` (`media_repo.py:54-56`) check only `asset_id IS NOT DISTINCT FROM expected_asset_id`. There is no monotonic `edit_revision` on `studio.scenes`, so replacing the same asset with a different trim, A→B→A ABA races, or concurrent overlay edits via `POST/DELETE /scenes/{sid}/assets` (`routes.py:1963-1987`) are unprotected.

### 2.2 Isolated Container Reproduction Proof
- **Artifact:** [pc01-bug-repro.log](pc01-bug-repro.log)
- **Method:** Ephemeral pytest module run inside `./scripts/test-container.sh` against real disposable `postgres:16-alpine` (`tmpfs`), real FastAPI routes (`POST /studio/videos/{vid}/scenes/{sid}/media/import`, `POST /studio/videos/{vid}/scenes/{sid}/assets`, `GET /studio/videos/{vid}/scenes/{sid}/assets`), real `FfmpegMediaProbe` (PNG + FFmpeg-generated MP4), and real `ImportExternalMedia`, then immediately removed (`0` repo changes).
- **Exit Code:** `0` (`1 passed in 2.01s`, proving all 3 defect modes reproduce deterministically on `HEAD 8484b72`):
  - **Repro A (Replace base WITHOUT trim):** Scene had `3` rows in `studio.scene_assets` (`['base', 'overlay', 'overlay']`). After `POST /media/import` with PNG #2 (no trim), `GET /assets` returned **`0` rows (`[]`)** — both PNG and MP4 PiP overlays were wiped.
  - **Repro B (Replace base WITH trim):** Scene had `2` overlay rows (`['overlay', 'overlay']`). After `POST /media/import` with MP4 #3 + trim `(0.25, 1.0)`, `GET /assets` returned **only `1` row (`['base']`)** — both overlays were wiped.
  - **Repro C (Split transaction failure):** Simulated `RuntimeError` inside `save_scene_assets` (Transaction #2) caused `ImportExternalMedia.execute` to fail, **yet `studio.scenes.asset_id` remained committed to `base4` (`b666fe46`) while `studio.scene_assets` still pointed to `base3` (`a4f1b9b8`)** — proving non-atomic partial state corruption.
