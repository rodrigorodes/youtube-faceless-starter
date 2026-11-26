# REC-00 — Deep Audit, Financial/Resilience Inventory & Test-First Recovery Plan

**Campaign:** V4 Integration & Stabilization Recovery (`PROMPT-MASTER.md`)  
**Wave / Tasks:** `REC-00.01`, `REC-00.02`  
**Executor:** `Gemini 4 Neon (High)` (`rec00-auditor`)  
**Independent Reviewer (Assigned):** `Gemini 4 Carbon (High)` (`rec00-reviewer`)  
**Audit Base:** `develop` `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd` (reopening base `72438e9ea215bbec12bd350d8c2606ca62bc7d94`)  
**Code Changes in REC-00:** **ZERO** (read-only code inspection + recovery documentation only)  
**External API Spend:** `$0.00` | **Publication:** `DISABLED` (`BLOCKED`)

---

## 1. G0 Preflight Verification

All preflight commands and raw outputs are captured in [`evidence/rec-00/preflight-and-inventory.md`](evidence/rec-00/preflight-and-inventory.md).

### 1.1 Git, Branch & Protection State
- **Active Branch:** `develop` tracking `origin/develop`
- **HEAD SHA:** `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd` (`docs(v4): reopen integration recovery with strict 9-point gates and model routing`)
- **Reopening Base (`HEAD~1`):** `72438e9ea215bbec12bd350d8c2606ca62bc7d94` (`chore(int-07): regressao canonica completa e homologacao dos achados a01-a13`)
- **Observed `main` SHA:** `42700cb331165a68455173a91c463d4733292cfd` (`Merge branch 'develop' into main: integracao e estabilizacao V4 (INT-01 a INT-07)`), whose parents are `be0c463edc55ff567f9149d26c8fd350c803d745` (`main^1`) and `72438e9ea215bbec12bd350d8c2606ca62bc7d94` (`main^2`).
  - **Transparency Note:** `PROMPT-MASTER.md:3` and `RECOVERY-REVIEW.md:3` cited the pre-merge `main` SHA `be0c463`. In reality, `main` already points to `42700cb`. Per strict campaign boundaries, `main` is **never touched** during recovery; all fixes occur on `develop` and any subsequent merge to `main` requires separate explicit operator authorization after `REC-04.04`.
- **Working Tree Before REC-00:** Clean (`git status --short` empty).

### 1.2 Host vs Container Runtime Matrix
| Component | macOS Host (`PATH` prefixed) | Canonical Container (`faceless-renderer-pytest:test`, ID `cbeba9e7b44c`) | Impact on Campaign |
|---|---|---|---|
| Python / pytest | `3.11.9` / `8.2.0` | `3.12.16` / `8.3.5` | Backend & FFmpeg regression runs in container (`scripts/test-container.sh`) |
| Docker Engine | `29.1.3` (`aarch64` Docker Desktop) | N/A | Isolated tmpfs Postgres & isolated E2E Compose supported |
| Tree & Migrations Match | `HOST_TREE=02efa18bc76d3e9d`, `48` SQL migrations | `IMAGE_TREE=02efa18bc76d3e9d`, `48` SQL migrations | **100% aligned** |
| FFmpeg / FFprobe | `9.1` (`/opt/homebrew/bin/ffmpeg`) | `7.1.5-0+deb13u1` (with `libass`, `ebur128`, `silencedetect`, `blackdetect`, `freezedetect`) | Production-parity FFmpeg 7.1.5 inside container |
| Piper TTS | Not on host | `/usr/local/bin/piper` + `/opt/voices/pt_BR-faber-medium.onnx` (`63.2 MB`) | Real offline PT-BR voice available in container |
| Kokoro TTS | Not checked on host | `find_spec("kokoro") == None` (not installed, no local weights) | Must remain fail-closed (`validated=False`) unless verified offline |
| Node.js / npm | `v26.0.0` / `11.12.1` (`/opt/homebrew/bin/node`) | **Not installed** (explains 17 Node skips in container) | Node JS unit tests (`test_erro_js.py`, `test_panel.py`, `test_workflow_*.py`, `test_publicacao_acao.py`, `test_falha_producao.py`) CAN run on host! |
| Playwright + Browsers | Installed (`playwright` Python + `chromium-1255` + `chromium_headless_shell-1255`) | Not installed | Real browser E2E (`scripts/run-e2e-full.sh` & `scripts/run-e2e-tests.sh` against port `8100`) IS **EXECUTABLE** on host! |

### 1.3 Isolation, Disposable DB, Kill Switch & Quota Controls
- **Dev Stack Ports (Untouched):** `127.0.0.1:8000` and `127.0.0.1:5678` are actively listening (dev stack). Never targeted by tests.
  - `scripts/test-container.sh` creates an ephemeral private Docker network (`faceless-test-net-$$`), `postgres:16-alpine` on `tmpfs` with zero host ports, mounts the repo `:ro`, and cleans up on `EXIT`.
  - `scripts/run-e2e-full.sh` and `tests/e2e_ux/conftest.py:24-30` enforce port `8100` (`docker-compose.e2e.yml`, tmpfs DB & storage) and hard-fail if pointed at port `8000`.
- **Disposable DB Proof Guard:** `tests/conftest.py:10-46` (`verified_test_connect`) verifies `STUDIO_BUDGET_DISPOSABLE_DSN` + `STUDIO_BUDGET_TEST_PROOF_FILE` (`/proof/proof` vs server-side `pg_read_file('/budget-test-proof/proof')` via constant-time `secrets.compare_digest`) on every physical connection before allowing schema drops or writes.
- **Publication Kill Switch:** `composition/wiring.py:702-705` injects `enabled=s.publication_enabled` into `RunPublication`. `application/publication_execution.py:271-273` short-circuits with `PublicationResult.BLOCKED` before `_claimed()`, token lookup, or `YouTubeUploader.upload()`. Because `composition/settings.py:71,101` defaults `publication_enabled=True` (`STUDIO_PUBLICATION_ENABLED="1"`) and `budget_guard=False`, every recovery test and pilot MUST explicitly set `STUDIO_PUBLICATION_ENABLED=0`, `STUDIO_BUDGET_GUARD=1`, `MAX_COST_USD_PER_VIDEO=0.0`, and `MAX_COST_USD_PER_MONTH=0.0` (note: `docker-compose.e2e.yml:40` sets `STUDIO_BUDGET_GUARD: "0"` while `STUDIO_PUBLICATION_ENABLED: "0"`; REC-03/04 will verify budget guard enabled in E2E/pilot runs).
- **Model Delegation & Quota Baseline:** Native swarm delegation is verified operational (Coordinator: `Gemini 4 Carbon (High)`, REC-00 Executor: `Gemini 4 Neon (High)`, REC-00 Reviewer: `Gemini 4 Carbon (High)`). Initial observed Google quota: `81%` (resets `2026-11-26T15:00:59Z`). External API spend ceiling: `$0.00`.

---

## 2. Code-Verified Deep Audit of `R01`–`R13`

Every finding from `RECOVERY-REVIEW.md` was independently verified against live code at `develop` `5800f46`.

### R01 (P0) — Unsafe `PostgresOperationStore` Arbitrarily Picks a Video & Hardcodes `$1000/$100` Caps
- **Code Location:** `renderer/app/studio/adapters/postgres/operation_store.py:18,54-147`
- **Verified Defect:**
  - Line 57: `vid_row = conn.execute("SELECT id FROM studio.videos LIMIT 1").fetchone()` — ignores the caller's `video_id` completely and attaches operations/ledger entries to whichever arbitrary row PostgreSQL returns first!
  - Lines 72, 110, 134: Hardcodes `monthly_limit_usd = 1000.0` and `video_limit_usd = 100.0`, completely bypassing `Settings.max_cost_month`, `Settings.max_cost_video` (`0.0`), and `studio.channel_budgets`.
  - Lines 65–145: Writes directly into `studio.paid_operations` and `studio.usage_ledger` without acquiring `pg_advisory_xact_lock(726002)`, without inserting/deleting `studio.budget_reservations`, without setting `paid_operations.project_id`, and without checking `NaN` unknown costs.
- **Consumer Call Graph:** `PostgresOperationStore` has **ZERO consumers** in `renderer/app/` (only imported in `tests/test_int_04_pipeline.py:15`). The real production path uses `PaidOperationGuard` + `PostgresPaidOperationRepository` (`wiring.py:530`).
- **Reproduction:** Create two videos `V1` (project A, hard cap `$0.00`) and `V2` (project B, hard cap `$0.00`). Invoke `PostgresOperationStore.save()` for `V2`: it silently bills `V1` (or whichever `LIMIT 1` returns) with `$1000/$100` limits and succeeds despite `$0.00` ceiling.

### R02 (P0) — Broken State Machine, Lost `external_reference_id`, Unconditional UPSERT, Double Ledger & Key Drift on Retry
- **Code Locations:** `renderer/app/studio/adapters/postgres/operation_store.py:63-145` and `renderer/app/studio/application/resilience.py:73-121`
- **Verified Defects:**
  1. `operation_store.py:63-83`: Collapses `RESERVED`, `SUBMITTED`, and `POLLING` into `state = 'RESERVED'` with `reason = NULL` — permanently **discarding `record.external_reference_id`** on `record_submission()`.
  2. `operation_store.py:74-80,112-118,136-142`: Uses `ON CONFLICT (idempotency_key) DO UPDATE SET ...` with **no CAS / state-transition guard** — a stale `RESERVED` or `FAILED` write silently overwrites an already `CONFIRMED` operation and NULLs out `ledger_id`!
  3. `operation_store.py:87-101`: On `CONFIRMED`, executes `cost = record.actual_cost_usd or Decimal("0.00")` (converting `None` / unknown cost silently into `$0.00` `FREE`!) and unconditionally `INSERT INTO studio.usage_ledger ...` on every call — calling `record_confirmation()` twice inserts **duplicate ledger rows**!
  4. `resilience.py:88-90`: `compute_deterministic_idempotency_key(tenant_scope.tenant_id, video_id, stage_name, attempt, p_hash)` includes `attempt` in the idempotency key — so retry `attempt=2` generates a brand-new key and bypasses deduplication against `attempt=1`!
  5. `resilience.py:92-121`: `begin_operation()` reads (`get_by_idempotency_key`) and writes (`save`) in two separate transactions — classic TOCTOU race allowing two concurrent workers to both get `should_execute=True`.
- **Consumer Call Graph:** `OperationReconciler` is only defaulted inside `ResilientStageExecutor.__init__` (`resilience.py:241`), which has **ZERO production consumers**.

### R03 (P0) — Post-Return Timeout, Retained `mock_duration_seconds`, Unused Reconciler & Parallel Unwired Executor
- **Code Location:** `renderer/app/studio/application/resilience.py:227-300`
- **Verified Defects:**
  - Line 252 & 270: Keeps `mock_duration_seconds: float = 0.0` and evaluates `elapsed = max(mock_duration_seconds, self.clock() - t0)` **after** synchronous `handler(attempt)` has already returned (cannot interrupt or cancel a hung handler!).
  - Line 241 vs lines 244–300: Instantiates `self.reconciler` in `__init__` and **never calls `self.reconciler`** anywhere in `execute_stage()`.
  - **Architectural Duplication:** `ProductionCoordinator` (`application/production.py:764`) + `LeaseHeartbeat` (`application/lease_heartbeat.py:32`) + `PostgresProductionRunRepository` (`adapters/postgres/production_repo.py:183`) already own stage execution, leasing, fencing tokens, outbox, and orphan recovery (`wiring.py:744-754`). `ResilientStageExecutor` duplicates that responsibility without wiring.
  - **Real Coordinator Gap Verified:** Reading `ProductionCoordinator._execute_claimed` (`application/production.py:1018-1061`) confirms it already enforces `LeaseHeartbeat` + `fencing_token` CAS on `complete_stage`/`fail_stage`, **but** does NOT yet enforce a per-stage execution timeout/cooperative cancellation signal, nor an automatic pre-retry reconciliation check against `PaidOperationRepository` (`UNCERTAIN`/`RESERVED` operations) before re-running a stage with external effects!

### R04 (P0) — Fake `crossfade`, Silent `slide`/`wipe` Drop, Rejected Video PiP & Unvalidated/Dropped Transforms
- **Code Locations:**
  - `renderer/app/studio/adapters/render_plan_compiler.py:521-557` (`_fade_filter`)
  - `renderer/app/studio/application/render_compiler.py:312-316` (`_validate_overlays`)
  - `renderer/app/studio/adapters/render_plan_compiler.py:390-398,448-499` (`_overlay_filter`)
  - `renderer/app/studio/adapters/render_plan_ffmpeg.py:566-588,714-720`
  - `renderer/app/studio/domain/render_plan.py:167-175,196-211` (`Composition`, `Transition`)
- **Verified Defects:**
  1. `render_plan_compiler.py:538-548`: Treats `transition.kind in ("fade", "crossfade")` identically as a single-shot `fade=t=in:st=0:d=FADE_S,fade=t=out:st=...` (fade-to-black), NOT an inter-shot overlap (`xfade`) between two consecutive shots!
  2. `domain/render_plan.py:199-202` accepts `"slide_left"`, `"slide_right"`, `"wipe_left"`, `"wipe_right"`, yet `render_plan_compiler.py:549-557` has no branch for them and silently falls through to `return ""` (cut!) instead of compiling them or raising `CompileError`!
  3. `render_compiler.py:312-316`: `_validate_overlays` rejects every overlay where `reference.media_type not in ("image", "graphic")` (`CompileError: VE-01 supports image/graphic overlays only`). Meanwhile `render_plan_ffmpeg.py:571` tags `.mp4/.webm` overlays as `media_type="video"`, causing an immediate crash, and `render_plan_compiler.py:397` passes `["-loop", "1", "-i", layer.source]` which only works for still images, NOT video PiP!
  4. `render_plan_ffmpeg.py:581-588`: Builds `StoryboardOverlay(scene_id=..., asset_id=..., start_s=..., duration_s=..., z_index=..., fit=...)` without propagating `opacity`, `scale`, `position_x`, `position_y`!
  5. `domain/render_plan.py:167-175` & `render_plan_compiler.py:455-491`: No finiteness/range validation on `opacity` (`0..1`), `scale` (`>0`, finite upper bound), `position_x`/`position_y` (`0..1`), and `scale=0.0` silently turns into `1.0` via `or 1.0`!
- **Consumer Call Graph:** `PlanFfmpegRenderer.render` → `compile_render_plan` → `structure_render_plan` (**REAL CONSUMER** wired at `wiring.py:341`).

### R05 (P1) — Synthetic String Tests, Fake `true_peak_dbtp` Alias & Disconnected Multitrack/Motion
- **Code Locations:**
  - `renderer/app/studio/domain/audio_dsp.py:170-179` (`mix_multitrack_pcm`)
  - `tests/test_int_03_composition.py:28-123`
  - `renderer/app/studio/domain/audio_multitrack.py`, `domain/audio_catalog.py`, `domain/motion_effects.py`
- **Verified Defects:**
  - `audio_dsp.py:176`: `"true_peak_dbtp": sample_peak_dbfs` still aliases 1x sample peak as ITU-R BS.1770 / EBU R128 True Peak (`dBTP`), and `test_int_03_composition.py:122` explicitly asserts `metrics["sample_peak_dbfs"] == metrics["true_peak_dbtp"]`! Real oversampled True Peak already exists in `adapters/qa_ffmpeg.py:30,38-40,78` (`ebur128=peak=true`).
  - `test_int_03_composition.py` checks only constants (`MAX_OVERLAYS_PER_SCENE == 8`), dataclass fields, filter strings (`"colorchannelmixer=aa=0.60" in flt`), and pure-Python PCM sine wave — zero FFmpeg rendering, zero pixel inspection, zero real audio analysis.
  - `audio_multitrack`, `audio_dsp`, `audio_catalog`, and `motion_effects` have **ZERO call sites** in `render_compiler.py`, `render_plan_compiler.py`, `render_plan_ffmpeg.py`, or `wiring.py`.

### R06 (P0) — Insecure External Media Validation (`>=16 bytes` MP4, Arbitrary License String, `.mp4` for WebM)
- **Code Locations:** `renderer/app/studio/application/media.py:381-431` and `renderer/app/studio/adapters/storage.py:76-92`
- **Verified Defects:**
  - `media.py:424-426`: For `video/mp4` and `video/webm`, ONLY checks `if len(data) < 16:`! Any arbitrary 16+ byte file (HTML, ZIP, random bytes, truncated MP4) is accepted without `ffprobe`/decode, codec/stream validation, duration bounds, or resolution limits!
  - `media.py:418-423`: Checks magic bytes for PNG and JPEG only — **`image/webp` has zero magic-byte validation** (though Pillow decodes it inside `FileAssetStore.put`).
  - `media.py:406`: Rejects only `("", "unknown", "unlicensed", "proprietary")`; accepts arbitrary unverified strings (e.g. `"any-string"` or `"stolen"`).
  - `storage.py:81`: `FileAssetStore.put_video()` always writes `key + ".mp4"`, even when `mime == "video/webm"`!
  - `tests/test_int_05_studio_assets.py:142`: Uses fake `b"\x00\x00\x00\x20ftypisom..." + b"\x00" * 64` (unplayable by FFmpeg!).

### R07 (P0) — Filename in Dedup Key, Unscoped Global Lookup, Broken CAS (`expected=None`) & Non-Atomic Persistence
- **Code Location:** `renderer/app/studio/application/media.py:436-471` and `adapters/postgres/media_repo.py:51-58`
- **Verified Defects:**
  - `media.py:437`: `key = asset_cache_key(kind.value, "import", content_hash, clean_filename, {"size": len(data)})` — same bytes uploaded under two filenames duplicate storage/rows; worse, `project_id` and `license` are omitted from scope!
  - `media.py:439-446`: Global `self.assets.find(key)` reuses an existing asset across projects/videos without verifying project ownership or license compatibility.
  - `media.py:443,468`: Calls `self.assets.swap_scene_asset(video.id, scene_id, ..., None)` passing `expected_asset_id=None` and **ignores the boolean return value**! In `media_repo.py:55`, `asset_id IS NOT DISTINCT FROM NULL` silently returns `False` (0 rows updated!) whenever the scene ALREADY has an asset linked — meaning replacing a scene's existing media via `ImportExternalMedia` silently fails to link while returning the new `Asset`!
  - `media.py:449-470`: Storage write (`put_video`/`put`), DB insert (`assets.add`), and scene link (`swap_scene_asset`) are 3 separate operations with no rollback/compensation if linking fails (leaving orphan files/rows or corrupting prior scene state).

### R08 (P1) — `import_media` Unwired in Routes, Upload Explicitly Disabled in UI & Zero Browser Execution
- **Code Locations:** `composition/wiring.py:579`, `api/routes.py` (0 references to `import_media`), `api/panel_video_storyboard_js.py:411`
- **Verified Defects:**
  - `wiring.py:579` instantiates `import_media=ImportExternalMedia(...)`, but **no route** in `routes.py` calls it.
  - `panel_video_storyboard_js.py:411` literally renders: `<input type="file" disabled>` with `"O envio de arquivos ainda não existe no servidor."`!
  - No generic assisted-generation panel (`GAI-02`: editable/copyable prompt + import + preview + apply + reload) exists in `panel_video_storyboard_js.py` / `panel_video_workspace.py`.
  - Good news verified in code: Real storyboard CRUD routes (`routes.py:1474-1525,1660-1731`) and client-side undo/redo (`panel_video_storyboard_js.py:49,169-174,469-470`) ALREADY exist and should be reused/extended, NOT replaced with a new SPA or the isolated `application/studio_workbench.py`.
  - Real Playwright browser tests (`tests/e2e_ux/` 16 tests + `tests/e2e_full/` 4 tests) were NEVER executed in INT-01–07 even though Node `v26.0.0` and Playwright Chromium `1255` are present on host!

### R09 (P1) — Kokoro `find_spec`-Only Check, Single-Chunk Truncation & Possible Auto-Download
- **Code Locations:** `adapters/voice_kokoro.py:26-28,80-92` and `composition/providers.py:151,174-177`
- **Verified Defects:**
  - `voice_kokoro.py:26-28` & `providers.py:151`: `is_kokoro_installed()` only runs `importlib.util.find_spec("kokoro") is not None`. Installing the Python package without local model weights marks Kokoro `validated=True` in the registry!
  - `voice_kokoro.py:84`: `kokoro.KPipeline(lang_code="b")` can attempt silent HuggingFace network downloads if local weights are not verified and offline mode is not enforced.
  - `voice_kokoro.py:87-91`: `for _, _, audio in generator: ... sf.write(...); return ...` — returns immediately on the **first yielded chunk**, silently truncating multi-sentence narration!
  - `tests/test_int_02_providers.py:25,39,65`: Guards assertions with `if not is_kokoro_installed():` and never tests multi-chunk concatenation or offline weights verification.
  - Confirmed: `PiperVoice` (`/opt/voices/pt_BR-faber-medium.onnx`) works offline; `ElevenLabsVoice` stays disabled (`validated=False`, raises `ProviderMissingCredential` / `NotImplementedError`).

### R10 (P1) — Isolated V4 Modules Falsely Claimed Integrated in `INT-07-FINAL-REPORT.md`
- **Verified Call-Site Audit (`renderer/app/`):**
  - **0 Production Consumers (`NONE — ISOLATED`):** `application/render_engine.py`, `application/asset_registry.py`, `application/studio_workbench.py`, `application/resilience.py`, `adapters/postgres/operation_store.py`, `adapters/captions_exporters.py`, `adapters/render_hardware.py`, `domain/audio_dsp.py`, `domain/audio_multitrack.py`, `domain/audio_catalog.py`, `domain/motion_effects.py`, `domain/voice_preprocessing.py`, `domain/voice_audio.py`, `domain/quality.py::compute_selective_regeneration`.
  - **Partially Wired:** `application/creative_director.py::CreateCreativeBrief` is wired at `wiring.py:633,661` and called at `routes.py:1376` (storing `videos.creative_brief`), and displayed at `panel_video_workspace.py:156` — **but** is never fed into `GenerateScript` or `RenderPlan` compilation.
  - **Inherited Canonical Components (Already Wired — Must Be Reused, Not Duplicated):** `PlanRegeneration` + `PostgresRenderPlanRepository` (`wiring.py:341,583,835`), `PostgresAssetRepository` + `FileAssetStore` (`wiring.py:539-540`), `FfmpegQualityEvaluator` (`wiring.py:349`), `ProductionCoordinator` (`wiring.py:744`), `PaidOperationGuard` (`wiring.py:530`), `routes.py:2270-2279` (SRT/VTT), `routes.py:1474-1525` (storyboard editing + revisions).

### R11 (P0) — `test_int_06_pilot.py` Is a 15s Smoke Test, Not a 60–90s Slice or 5–8min Paired Pilot
- **Code Location:** `tests/test_int_06_pilot.py:116-185`
- **Verified Defects:**
  - Runs `format="short"`, `target_duration_s=15`, `scene_count=2`, `STUDIO_TEXT=demo:v4`, `STUDIO_IMAGE=placeholder:v4`.
  - Zero external PNG/MP4 import, zero video PiP/overlays, zero multitrack/SFX/motion, zero selective regeneration, zero persisted metrics JSON/SHA-256 manifest (output lives in ephemeral `tmp_path`), zero paired comparison against V4-00 baseline.
  - Line 175 invokes `POST /studio/videos/{video_id}/approve` inside the test (`"Aprovado em teste INT-06"`), which is an API endpoint test, NOT human audiovisual approval.

### R12 (P0) — Unreconciled Test Counts (`4416` vs `4419`), Partial Retest (`228/228`) & Unexecuted Browser Suite
- **Code Location:** `docs/.../INT-07-FINAL-REPORT.md:6,76-89`
- **Verified Defects:**
  - Claims `4.416` collected, `4.389` passed, `20` skips, and `10` fixes — arithmetic `4389 + 10 + 20 = 4419 ≠ 4416` (+3 discrepancy, unreconciled).
  - After applying 10 fixes (including production code in `wiring.py` and `panel_advanced.py`), only a partial subset (`228/228`) was re-run; no full canonical regression was executed on final commit `72438e9`.
  - Container `--collect-only` at `5800f46` confirms `4,416` canonical tests; host `--collect-only` confirms `26` Playwright tests (`tests/e2e_ux` + `tests/e2e_full`), none executed in INT-07.

### R13 (P1) — Missing Per-ID Matrix & Stale Governance States
- **Verified:** `INT-01-AUDIT-REPORT.md` only tracked `A01`–`A13`, `EXECUTION-BACKLOG.md` remained `PENDING`, and `history/PROMPT-MASTER-INT-01-07.md` marked all waves complete without independent rubric review. Resolved for REC-00 by `TRACEABILITY-MATRIX.md` (all 227 V4 IDs + 9 GAI + 21 INT + 13 A + 13 R + 17 REC) and control files; final closure in `REC-04.04`.

---

## 3. Existing Financial & Resilience Architecture Inventory (Mandatory Pre-REC-01 Reference)

**Rule:** REC-01 MUST reuse the existing transactional PostgreSQL mechanisms below and MUST NOT create parallel tables, ledgers, guards, or coordinators.

### 3.1 Existing PostgreSQL Migrations & Schema Constraints
| Migration File | Tables / Columns / Constraints / Triggers | Financial / Resilience Role |
|---|---|---|
| `0013_budget_reservations.sql` | `studio.budget_reservations(idempotency_key PK, video_id FK RESTRICT, amount_usd, monthly_limit_usd, video_limit_usd, created_at)` + trigger `usage_ledger_budget_lock` (`pg_advisory_xact_lock(726002)`) | Active budget lock table; serializes ALL budget reservations and `usage_ledger` writes under advisory lock `726002` |
| `0014_ledger_cost_evidence.sql` | `usage_ledger.cost_zero_evidence` + `CHECK` | Legacy zero cannot masquerade as free without evidence |
| `0015_ledger_cost_confirmation.sql` | `usage_ledger.cost_confirmation_kind`, `cost_confirmed_amount`, `cost_confirmation_reference`, `cost_confirmed_by`, `cost_confirmed_at` + `usage_ledger_cost_confirmation_check` | Enforces structured confirmation (`ACTUAL`/`ESTIMATE`/`FREE`) matching `cost_usd` |
| `0017_paid_operations.sql` | `studio.paid_operations(idempotency_key PK, video_id FK RESTRICT, estimate_usd, monthly_limit_usd, video_limit_usd, state IN ('RESERVED','CONFIRMED','RELEASED','UNCERTAIN'), confirmed_kind, confirmed_amount_usd, ledger_id FK RESTRICT, reason, created_at, updated_at)` + `paid_operations_settlement_check` | Canonical 1:1 persisted paid-operation state machine tied to `budget_reservations` and `usage_ledger` |
| `0018_production_runs.sql` | `studio.production_runs(run_id PK, video_id, channel_id, idempotency_key UNIQUE, state, reason)` + `studio.stage_executions(run_id, stage_id PK, state, attempt, lease_owner, lease_expires_at, fencing_token, checkpoint, checkpoint_version, error)` + `studio.production_outbox` | Canonical DAG run idempotency, stage leasing, monotonic `fencing_token` CAS, checkpoints, transactional outbox |
| `0019_ledger_estimate_and_attribution.sql` | Extends `confirmed_kind` to include `ESTIMATE` | Allows estimated settlement subject to `reconcile_actual()` |
| `0020_paid_operation_attempt_and_budget_indexes.sql` | `paid_operations.attempt >= 1` + 4 indexes (`usage_ledger_created_at_idx`, `usage_ledger_video_id_idx`, `budget_reservations_created_at_idx`, `paid_operations_state_updated_at_idx`) | Tracks safe reopen attempts after `RELEASED` (pre-effect failure only) |
| `0028_publication_resilience.sql` | Publication retry/reconcile/DLQ columns & constraints | Idempotent resumable upload session tracking |
| `0038_budget_scope_attribution.sql` | Adds `project_id FK RESTRICT` to `usage_ledger`, `budget_reservations`, `paid_operations` + trigger `usage_ledger_project_attribution` (`assign_ledger_project()`) + 3 scope indexes | Enforces 3-scope isolation: **GLOBAL (month)**, **CHANNEL (`project_id`, month)**, **VIDEO (lifetime)**; video is authoritative for `project_id` |
| `0039_production_run_config.sql` | Frozen `EffectiveConfig` snapshot persisted on `production_runs` | Prevents config/provider drift across retries & restarts |
| `0041_production_run_operation.sql` | Adds `'production.run.operation'` to `production_outbox` | Durable lifecycle audit trail (pause/resume/retry/regenerate) |
| `0053_usage_ledger_category.sql` | Adds `category`, `duration_ms`, `attempt` to `usage_ledger` + 2 indexes | Cost categorization & attribution without new FinOps tables |

> **Schema Note for REC-01.02:** `studio.paid_operations` currently has states `('RESERVED', 'CONFIRMED', 'RELEASED', 'UNCERTAIN')`, `attempt`, `ledger_id`, `reason`, `project_id`, `video_id`, but does **not** yet have dedicated columns for an asynchronous provider's durable `external_reference_id` / `operation_id` (if needed for async submit/poll/reconcile). REC-01.02 can either add an additive nullable column (`external_reference_id text`, plus optional `submitted_at timestamptz` or state extension) on `studio.paid_operations` via a clean reversible migration `0054_...sql`, OR store/verify it inside `studio.paid_operations` while strictly preserving `paid_operations_settlement_check` and all existing `PostgresPaidOperationRepository` invariants!

### 3.2 Existing Domain, Application & Adapter Classes (Canonical vs Unsafe Duplicate)
| Class / Symbol | File & Line | Status | Action in REC-01 |
|---|---|---|---|
| `PaidOperationGuard`, `PaidOperationRepository`, `PaidOperationState`, `BeginResult`, `CostConfirmation`, `ChargeEvidence`, `PendingReconciliation`, `BudgetDenied`, `BudgetDenial`, `OperationInProgress`, `OperationUncertain`, `OperationSettled`, `PreEffectFailure`, `paid_key`, `provider_settlement` | `application/budget.py:25-473` | **CANONICAL (Wired @`wiring.py:530`)** | **PRESERVE & EXTEND** (support idempotent confirmation / durable external operation ref / pre-retry reconcile hook) |
| `PostgresPaidOperationRepository`, `PostgresBudgetRepository`, `_lock_budget`, `_scope_project`, `_reserve_within` | `adapters/postgres/budget_repo.py:19-469` | **CANONICAL (Wired @`wiring.py:530`)** | **PRESERVE & EXTEND** (already enforces advisory lock `726002`, `FOR UPDATE`, 3 scopes, `NaN` unknown-cost block, `IdempotencyConflict`, `reconcile_actual`, `pending_reconciliation`) |
| `ChannelBudgetFloor`, `GetChannelBudget`, `SetChannelBudget` | `application/channel_budget.py:39-197` | **CANONICAL (Wired @`wiring.py:742,768,807`)** | **PRESERVE** |
| `PostgresChannelBudgetRepository`, `PostgresChannelUsageRepository` | `adapters/postgres/channel_budget_repo.py:32-114` | **CANONICAL (Wired @`wiring.py:447,513`)** | **PRESERVE** |
| `CostGuard` | `application/editorial.py:216` | **CANONICAL (Pre-check @`wiring.py:512`)** | **PRESERVE** (hard guard is `PaidOperationGuard` when `budget_guard=True`) |
| `ProductionCoordinator`, `ProductionWorker`, `Production`, `ActiveRuns`, `CapacityExceeded` | `application/production.py:723-1320` | **CANONICAL (Wired @`wiring.py:744-754`)** | **PRESERVE & EXTEND** (add cooperative stage timeout/cancel + pre-retry paid-operation reconciliation check) |
| `LeaseHeartbeat`, `StageLease`, `LeaseLost` | `application/lease_heartbeat.py:21-116` | **CANONICAL (Wired @`production.py:1027`)** | **PRESERVE & EXTEND** (ensure late handler cannot confirm stage or paid op after lease loss) |
| `PostgresProductionRunRepository` | `adapters/postgres/production_repo.py:183-767` | **CANONICAL (Wired @`wiring.py:599`)** | **PRESERVE** |
| `PostgresOperationStore` | `adapters/postgres/operation_store.py:18-147` | **UNSAFE PARALLEL ADAPTER (R01/R02)** | **REMOVE / RETIRE** in `REC-01.01` |
| `OperationReconciler`, `InMemoryOperationStore`, `ResilientStageExecutor`, `ReadinessChecker` | `application/resilience.py:40-300` | **UNSAFE PARALLEL EXECUTOR (R02/R03)** | **REMOVE / CONSOLIDATE** unsafe duplication in `REC-01.02`/`REC-01.03` (keep pure domain value types only if genuinely reused by canonical coordinator/guard) |

### 3.3 Existing Financial & Resilience Test Suites (Baseline Counts)
| Test File | Test Count | What It Already Covers |
|---|---:|---|
| `tests/test_paid_operations.py` | 35 | Atomic `begin`/`confirm`/`release`/`mark_uncertain`/`reconcile_actual`, CAS transitions, `IdempotencyConflict`, `NaN` blocking |
| `tests/test_budget_reservations.py` | 32 | 3-scope ceilings (Global/Channel/Video), concurrent reservations, advisory lock serialization |
| `tests/test_budget_guard.py` | 36 | `PaidOperationGuard.run` pre-effect vs ambiguous failure, validation failure, settlement failure, free replay |
| `tests/test_budget_guard_wiring.py` | 4 | Real `Studio` wiring with `STUDIO_BUDGET_GUARD=1` |
| `tests/test_budget_http.py` | 2 | HTTP 403 actionable `BudgetDenial` payload |
| `tests/test_channel_budget.py` + `test_channel_budget_service.py` | 31 | Channel soft/hard limits, economic profile routing |
| `tests/test_lease_heartbeat.py` + `test_lease_recovery_concurrency.py` | 21 | 90% self-fencing latch, concurrent claim/fencing, orphan recovery |
| `tests/test_production_coordinator.py` | 43 | DAG, pause/resume/retry/cancel, frozen config snapshot, outbox |
| `tests/test_publication_execution.py` + `test_publication_resilience_repo.py` | 61 | Kill switch (`BLOCKED`), resumable upload idempotency, DLQ/reconcile |

---

## 4. AS-IS vs TO-BE Architecture Map (Waves REC-01 to REC-04)

| Wave | Domain | AS-IS (Observed at `5800f46`) | TO-BE (Recovery Target >= 9.0/10) |
|---|---|---|---|
| **REC-01** | Financial Safety & Resilience (`R01–R03`) | Unsafe parallel `PostgresOperationStore` (`SELECT LIMIT 1`, caps `1000/100`, UPSERT without CAS, double ledger, drops `external_reference_id`) + `OperationReconciler` (key includes `attempt`, TOCTOU) + `ResilientStageExecutor` (post-return timeout, `mock_duration_seconds`, unwired). Canonical `ProductionCoordinator` lacks stage timeout/cancel & pre-retry uncertain-op check. | Single canonical financial path (`PaidOperationGuard` + `PostgresPaidOperationRepository`, zero bypass). `PostgresOperationStore` & `ResilientStageExecutor` removed/retired. Atomic exclusive admission (`pg_advisory_xact_lock` + `FOR UPDATE`), stable logical key across retries, durable `external_reference_id`, idempotent once-only ledger settlement, unknown cost never coerced to `$0.00`. `ProductionCoordinator` enforces cooperative stage timeout/cancel, pre-retry reconciliation blocking uncertain ops, and post-lease-loss fencing. Proven with 2 concurrent PG connections, 2 videos/projects, `$0.00` cap, restart, and kill switch. |
| **REC-02** | Composition, Audio, Import & Voice (`R04–R07, R09`) | `_validate_overlays` rejects `video` PiP; `_overlay_filter` uses `-loop 1` and unvalidated floats; `StoryboardOverlay` drops transforms; `_fade_filter` fakes `crossfade` as fade-to-black and silently drops `slide`/`wipe`. `audio_dsp.py` aliases `true_peak_dbtp = sample_peak_dbfs`; multitrack & motion disconnected from FFmpeg. `ImportExternalMedia` accepts any >=16B video, arbitrary license strings, saves WebM as `.mp4`, puts filename in key, global lookup, `expected=None` CAS ignored. Kokoro checks only `find_spec`, returns 1st chunk, no offline weight check. | Real multi-overlay + video PiP + validated finite transforms propagated end-to-end; real inter-shot `crossfade` (`xfade` with synced audio/captions/duration) and explicit compile or fail-closed `CompileError` for `slide`/`wipe` (never silent). Real EBU R128 `dBTP` via FFmpeg `ebur128` (alias removed); multitrack (voice + 2 music + ambience + SFX + fades + ducking + license) & observable motion/post-proc wired into `PlanFfmpegRenderer` with pixel/audio/duration/fingerprint/golden proofs. Reproducible MP4/PNG/JPEG/WebP import with sandboxed `ffprobe`/decode, codec/dimension/duration/size limits, `.webm`/`.mp4` coherence, allowlisted license, content+scope dedup, real CAS conflict handling, atomic/compensated persistence. Kokoro fail-closed offline (multi-chunk concat when weights present locally, else explicit `ModelUnavailable`/`validated=False`); Piper official; ElevenLabs disabled. |
| **REC-03** | Studio UX, Browser E2E & Pipeline Integration (`R08, R10`) | `import_media` unwired in `routes.py`; UI shows `<input type="file" disabled>`; no generic assisted mode (`GAI-02`); Playwright browser suite (`26` tests) never executed. Creative brief stored in DB but unused by script/RenderPlan; duplicate isolated `render_engine.py`, `asset_registry.py`, `studio_workbench.py`, `captions_exporters.py`, `compute_selective_regeneration`. | Authorized upload/import FastAPI route(s) with size limits, ownership, CAS revision & 409 conflict; enabled upload/preview (PNG+MP4 MIME)/trim-crop-mute/associate + generic assisted mode (editable/copyable prompt) in existing Studio storyboard (no new SPA); undo/redo/reload/generate-missing verified in real Playwright browser (desktop + mobile) on isolated port `8100`. Creative brief flows into script/RenderPlan with frozen identity; single canonical `PlanRegeneration` cache + preflight/progress/cancel + QA defect detection + bounded selective regeneration + license publication blocking + persistent asset metadata; parallel in-memory duplicates retired. |
| **REC-04** | Observed Pilots, Full Regression & Release Gate (`R11–R13`) | `test_int_06_pilot.py` is a 15s 2-scene demo smoke calling `POST /approve`; no 60–90s slice or 5–8min Studio documentary with V4 capabilities; `INT-07-FINAL-REPORT.md` has 4416 vs 4419 discrepancy & 228/228 partial retest; human audiovisual review pending. | `test_int_06_pilot.py` kept and clearly labeled `SMOKE`. Real 60–90s vertical slice + original 5–8min documentary rendered via Studio ($0.00 API, kill switch `BLOCKED`) with all V4 capabilities, paired comparison vs V4-00 baseline, observed ffprobe/ebur128/dBTP/drift/frozen/CPU/RAM/stage-time/cost-per-min/regeneration-savings/human-time, preserved in exclusive run dirs with versioned SHA-256 manifest + sampled frames. Clean final-SHA full canonical regression (`scripts/test-container.sh` + host Node JS tests + isolated Playwright browser suite), exit 0, exact counts reconciled. Independent Neon High final review >=9.0/10 → `TECHNICAL GO / AWAITING HUMAN REVIEW` (never auto-merged or self-approved aesthetically). |

---

## 5. Test-First Execution Plan per Task (`REC-01.01`–`REC-04.04`)

Every task follows the mandatory cycle: **Write failing test proving defect/gap → Minimal reuse-first implementation → Focused + negative + real-consumer tests → Independent reviewer sign-off (>=9.0/10 on diff/SHA) → Atomic commit**.

### Wave REC-01 — Financial Safety & Resilience (Executor: `Hydrogen Medium` | Reviewer: `Neon High`)

#### `REC-01.01` (P0 | Dep: `REC-00.02`) — Remove Unsafe `PostgresOperationStore` & Enforce Real Identity / `$0.00` Ceiling
- **Files to Modify/Remove/Reuse:**
  - Remove (or tombstone/delete) `renderer/app/studio/adapters/postgres/operation_store.py`.
  - Reuse `renderer/app/studio/application/budget.py` (`PaidOperationGuard`) and `renderer/app/studio/adapters/postgres/budget_repo.py` (`PostgresPaidOperationRepository`).
  - Update/replace `tests/test_int_04_pipeline.py` to test the canonical `PaidOperationGuard` + `PostgresPaidOperationRepository` against disposable Postgres.
- **Failing Test First:** Regression test proving (a) `PostgresOperationStore` is no longer importable/reachable, (b) two videos in two different projects with `$0.00` caps block any paid operation `> $0.00` (`BudgetDenied` with actionable `BudgetDenial`) and never attribute cost to another video, and (c) zero hardcoded `$1000/$100` limits exist anywhere in paid operation persistence.
- **Positive & Negative Cases:** Positive: `$0.00` `FREE` operation succeeds with real `video_id`/`project_id` attribution; Negative: `$0.01` under `$0.00` cap raises `BudgetDenied`, unknown `video_id` fails closed (`ValueError`), cross-video key reuse raises `IdempotencyConflict`, `NaN` cost in ledger blocks subsequent paid ops.
- **Real Consumer Proof:** `Studio` wired with `budget_guard=True`, `max_cost_video=0.0`, `max_cost_month=0.0` via `wiring.py:530` calling `ProduceAssets`/`GenerateScript` with a paid-estimate offline double.
- **Rollback:** `git revert <commit_sha>` (zero destructive schema changes).

#### `REC-01.02` (P0 | Dep: `REC-01.01`) — Atomic Admission/Settlement, Durable External Ref, Stable Logical Key & GAI-09 Min Accounting (`REC-01.02b`)
- **Files to Modify/Reuse:**
  - Reuse/extend `renderer/app/studio/adapters/postgres/budget_repo.py` (`PostgresPaidOperationRepository`), `renderer/app/studio/application/budget.py` (`PaidOperationGuard`), plus minimal additive migration `0054_paid_operation_external_ref.sql` (nullable `external_reference_id text`, `submitted_at timestamptz` with rollback SQL comment) if needed to persist external provider operation ID durably across restarts without weakening `paid_operations_settlement_check`.
  - Remove/deprecate broken `OperationReconciler` / `InMemoryOperationStore` in `application/resilience.py` (or delegate strictly to `PaidOperationGuard` with attempt-free logical key).
  - Sub-slice `REC-01.02b` (GAI-09 min): verify `usage_ledger.category` (`0053_usage_ledger_category.sql`) & existing `PostgresChannelUsageRepository` distinguish local/assisted/API without creating a parallel FinOps service, and unknown cost never coerces to `$0.00`.
- **Failing Test First:** Disposable Postgres test with **2 concurrent connections** (threads/barrier) racing `begin()` on the same logical key (same intent, retry without attempt in key), asserting exactly ONE `CREATED` and ONE `IN_PROGRESS`, followed by restart (new repo/connection), duplicate `confirm()` call (idempotent / rejected without second `usage_ledger` row), `None`/unconfirmable cost transitioning to `UNCERTAIN` (never `$0.00` `FREE`), and stale state overwrite rejected (`InvalidOperationTransition`).
- **Positive & Negative Cases:** Positive: `CREATED` → `record_external_ref` → restart → `confirm` produces exactly 1 `usage_ledger` row; `RELEASED` (pre-effect failure) safely reopens with `attempt + 1` under the SAME logical key; Negative: concurrent double submit blocked, duplicate confirm does not duplicate ledger, `UNCERTAIN` blocks retry until `reconcile_actual()`, unknown/negative/NaN cost rejected/marked `UNCERTAIN`.
- **Real Consumer Proof:** `PaidOperationGuard.run` + offline async-provider double over disposable Postgres (`SELECT COUNT(*) FROM studio.usage_ledger` == 1, double submit count == 1).
- **Rollback:** `git revert <commit_sha>` + additive migration rollback SQL (`ALTER TABLE studio.paid_operations DROP COLUMN ...; DELETE FROM studio.schema_migrations WHERE version = '0054_...'`).

#### `REC-01.03` (P0 | Dep: `REC-01.02`) — Pre-Retry Reconciliation & Cooperative Timeout/Cancellation in Canonical `ProductionCoordinator`
- **Files to Modify/Remove/Reuse:**
  - Reuse/extend `renderer/app/studio/application/production.py` (`ProductionCoordinator._execute_claimed`, `StageContext`, `StageHandler`) and `renderer/app/studio/application/lease_heartbeat.py` (`LeaseHeartbeat`).
  - Remove/retire parallel `ResilientStageExecutor` (and `mock_duration_seconds`) from `renderer/app/studio/application/resilience.py` (keep pure domain errors/policies only if imported by canonical code, otherwise remove dead duplicate classes cleanly while updating unit tests).
  - Wire optional `paid_ops: PaidOperationRepository | None` and `stage_timeouts` into `ProductionCoordinator` in `composition/wiring.py:744`.
- **Failing Test First:** Disposable Postgres test on real `ProductionCoordinator`: (1) stage handler exceeding timeout triggers cooperative cancellation/timeout failure without waiting indefinitely or using `mock_duration_seconds`; (2) late handler completing AFTER lease loss (`LeaseHeartbeat.lost == True` / bumped `fencing_token`) CANNOT commit `complete_stage` or confirm a paid operation; (3) retrying a stage that left a `RESERVED`/`UNCERTAIN` paid operation blocks duplicate external submit until reconciled; (4) two videos run isolated without cross-video interference; (5) `RunPublication(enabled=False)` blocks before token/upload.
- **Positive & Negative Cases:** Positive: normal stage finishes within timeout & lease; pre-effect failure allows bounded retry; Negative: hung handler timed out, stolen lease fences late write (`WorkerStepResult.LOST`), uncertain op blocks retry (double submit count == 1), kill switch returns `BLOCKED` with 0 token/upload calls.
- **Real Consumer Proof:** `ProductionCoordinator` + `ProductionWorker` + `PostgresProductionRunRepository` + `PostgresPaidOperationRepository` on disposable Postgres.
- **Rollback:** `git revert <commit_sha>`.

---

### Wave REC-02 — Real AV Composition, Media Import & Voice (Executor: `Hydrogen Medium`/`Carbon High`/`Flash 3.8` | Reviewer: `Neon High`/`Carbon High`)

#### `REC-02.01` (P0 | Dep: `REC-01.03`) — Consistent `RenderPlan`/Compiler/FFmpeg: Multi-Overlay, Video PiP, Transforms & Real Crossfade
- **Files to Modify/Reuse:**
  - `renderer/app/studio/domain/render_plan.py` (strict finite bounds validators on `Composition`: `0.0 <= opacity <= 1.0`, `0.05 <= scale <= 4.0`, `0.0 <= position_x/y <= 1.0`, reject NaN/Inf).
  - `renderer/app/studio/domain/render_plan_builder.py` (carry transform fields on `StoryboardOverlay` and pass to `Shot.composition`).
  - `renderer/app/studio/application/render_compiler.py` (allow `video` overlays in `_validate_overlays` with explicit resource bounds; preserve `MAX_OVERLAYS_PER_SCENE = 8`; validate finite bounds).
  - `renderer/app/studio/adapters/render_plan_compiler.py` (support video PiP input without `-loop 1`, with trim/scale/fps/opacity/position; compile real inter-shot `crossfade` via FFmpeg `xfade` + timeline/audio/caption duration sync; explicitly compile or fail-closed with `CompileError` on `slide_*`/`wipe_*` — NEVER silently drop to `""`; include transforms & transitions in `_digest`/fingerprint).
  - `renderer/app/studio/adapters/render_plan_ffmpeg.py` (propagate `StoryboardOverlay` transforms; execute inter-shot `xfade` assembly when crossfade is present; keep fast concat demuxer when all transitions are `none`/`cut`/`fade`).
  - `contracts/v1/renderplan.schema.json` (regenerate via `scripts/export_contracts.py` if schema changes, preserving v1/v2 read compatibility).
- **Failing Test First:** Real FFmpeg render test in container using two solid-color/moving-clip fixtures: (a) video PiP overlay at `scale=0.35, pos=(0.8, 0.2), opacity=0.7` proves pixel difference at target quadrant across multiple frames; (b) `crossfade` between red shot and blue shot proves blended midpoint frame pixels (`R > 50` and `B > 50`, NOT black `(0,0,0)` fade-to-black!) and exact `ffprobe` output duration; (c) `slide_left`/`wipe_left` either produce verifiable spatial transition pixels OR raise explicit `CompileError` (never silent cut).
- **Positive & Negative Cases:** Positive: v1/v2 golden compatibility preserved, multi-overlay z-order, video PiP, real crossfade, cache fingerprint invalidation on transform/transition change; Negative: `opacity=NaN/1.5`, `scale=0/-1/99`, `>8` overlays, `crossfade` duration >= shot duration, unsupported transition rejected with `CompileError`.
- **Real Consumer Proof:** `PlanFfmpegRenderer.render()` producing real MP4 inspected via `ffprobe` + Pillow frame pixel sampling.
- **Rollback:** `git revert <commit_sha>` + restore `contracts/v1/renderplan.schema.json`.

#### `REC-02.02` (P1 | Dep: `REC-02.01`) — Real Multitrack Audio, Ducking, SFX, Motion & Real EBU R128 `dBTP`
- **Files to Modify/Reuse:**
  - `renderer/app/studio/domain/audio_dsp.py`: Remove fake `"true_peak_dbtp": sample_peak_dbfs` alias (keep only honest `sample_peak_dbfs`; real `true_peak_dbtp` comes exclusively from FFmpeg `ebur128=peak=true` in `adapters/qa_ffmpeg.py:30,78`). Update `tests/test_int_03_composition.py` to stop asserting the fake alias!
  - Integrate `domain/audio_catalog.py`, `domain/audio_multitrack.py` (`verify_audio_licenses`, multi-music, ambience, SFX, fades, ducking) and `domain/motion_effects.py` (observable blur/vignette/color-grading/lower-third presets) into `RenderPlan` / `render_plan_compiler.py` / `render_plan_ffmpeg.py` with explicit license verification and cache fingerprints.
- **Failing Test First:** Real FFmpeg render test with voice (Piper) + 2 distinct music segments (with crossfade) + ambience + timed SFX + motion/vignette/lower-third preset → verify via `FfmpegQa` (`ebur128=peak=true` real `true_peak_dbtp <= -1.0`, `-18 <= LUFS <= -14`, zero clipping, duration preserved), audio energy ducking under speech vs silence, and frame pixel proof of motion/post-processing effect; plus negative test refusing unlicensed audio track before FFmpeg runs.
- **Positive & Negative Cases:** Positive: multitrack + ducking + fades + SFX + motion rendered and measured via `FfmpegQa`; Negative: unknown-license audio track rejected (`AssetRefused`/`CompileError`), `audio_dsp` does NOT emit `true_peak_dbtp`.
- **Real Consumer Proof:** `PlanFfmpegRenderer` + `FfmpegQa` real execution in container.
- **Rollback:** `git revert <commit_sha>`.

#### `REC-02.03` (P0 | Dep: `REC-01.03`) — Secure External Media Import (Reproducible PNG/JPEG/WebP/MP4/WebM + Probe/Decode & License Allowlist)
- **Files to Modify/Reuse:**
  - Add sandboxed media prober adapter (e.g., `MediaProbe` port in `application/ports.py` + `FfmpegMediaProbe` in `adapters/` using `ffprobe` + 1-frame `ffmpeg` decode check with strict timeout & resource bounds, preserving Clean Architecture — zero `subprocess` in `application/`).
  - Harden `renderer/app/studio/application/media.py` (`ImportExternalMedia`):
    - Real magic bytes + Pillow decode for PNG/JPEG/WebP (enforce pixel/byte limits).
    - Real `ffprobe` + decode verification for MP4/WebM (container matches MIME, valid video stream, allowed codecs, finite resolution/FPS/duration limits, max 100MB).
    - Allowlisted / structured verifiable license policy reusing `domain/asset_registry.py::verify_license_provenance` (reject arbitrary strings like `"banana"` or `"unknown"`).
  - Fix `renderer/app/studio/adapters/storage.py:76-92` (`put_video`): store `.webm` for `video/webm` and `.mp4` for `video/mp4` (never mislabel WebM as `.mp4`).
  - Wire prober into `ImportExternalMedia` in `composition/wiring.py:579`.
- **Failing Test First:** Test in container generating a **real playable MP4** (via `ffmpeg -f lavfi -i testsrc2...`) and a **real WebM**, plus negatives: (1) 80-byte fake `ftyp`+zeros payload MUST BE REJECTED; (2) arbitrary 64-byte text labeled `video/mp4` MUST BE REJECTED; (3) truncated MP4 MUST BE REJECTED; (4) PNG disguised as MP4 / ZIP disguised as PNG MUST BE REJECTED; (5) arbitrary license `"my-random-string"` MUST BE REJECTED; (6) path traversal `../../../etc/passwd.mp4` MUST BE REJECTED or safely neutralized without escaping root; (7) oversized file MUST BE REJECTED.
- **Real Consumer Proof:** `ImportExternalMedia` wired via `Studio` + real FFmpeg-generated MP4/PNG rendered through `PlanFfmpegRenderer`.
- **Rollback:** `git revert <commit_sha>`.

#### `REC-02.04` (P0 | Dep: `REC-02.03`) — Scoped Content-Hash Dedup, Real CAS Revision & Atomic/Compensated Persistence
- **Files to Modify/Reuse:**
  - `renderer/app/studio/application/media.py` (`ImportExternalMedia`):
    - Compute dedup key from `(kind, project_id, content_sha256, normalized_license)` — **remove `clean_filename`** from identity; never share/reuse an asset across different projects or incompatible licenses!
    - Accept explicit `expected_asset_id: str | None` (CAS) when linking to a scene; **check boolean return** of `swap_scene_asset(video.id, scene_id, asset.id, expected_asset_id)` and raise `StateConflict` (HTTP 409) on mismatch — never ignore return value or hardcode `None`!
    - Atomic / compensated workflow: verify scene exists & CAS precondition before disk write where possible; if DB insert or scene link fails after writing file, clean up newly created unreferenced file (without deleting any previously linked asset/file) and preserve previous scene binding intact!
  - `renderer/app/studio/adapters/postgres/media_repo.py`: verify `swap_scene_asset` / `add` under concurrent access and restart.
- **Failing Test First:** Disposable Postgres test proving: (1) same PNG/MP4 bytes imported under two different filenames in the same project+license deduplicate to the SAME asset; (2) same bytes imported in Project B or under a different license do NOT leak Project A's asset/license; (3) replacing a scene that already has `asset_A` with wrong `expected_asset_id` raises `StateConflict` and leaves `asset_A` intact; (4) simulated link failure after upload triggers compensation and preserves prior scene & file; (5) survives repo restart and 2 concurrent import requests.
- **Real Consumer Proof:** `ImportExternalMedia` + `PostgresAssetRepository` + `FileAssetStore` on disposable Postgres.
- **Rollback:** `git revert <commit_sha>`.

#### `REC-02.05` (P1 | Dep: `REC-01.03`) — Kokoro Offline Verification / Fail-Closed, Piper Preserved & ElevenLabs Disabled
- **Files to Modify/Reuse:**
  - `renderer/app/studio/adapters/voice_kokoro.py`:
    - Check BOTH `find_spec("kokoro")` AND explicit local offline weights directory (env/path check — NO silent HuggingFace download; set `HF_HUB_OFFLINE=1` / fail closed if weights absent).
    - Fix `_synthesize_native`: concatenate ALL audio chunks yielded by `generator` (not just the first chunk!) before writing WAV, validate non-empty intelligible audio duration/RMS/no-clipping.
    - Keep `allow_synthetic_fixture=False` default so production never emits 220Hz sine waves.
  - `renderer/app/studio/composition/providers.py:151,174-177`: Set `kokoro_ok` using real offline readiness check (package + verified local weights), NOT `find_spec` alone.
  - Preserve `PiperVoice` (`pt_BR-faber-medium`) as official validated offline voice and `ElevenLabsVoice` as `validated=False`.
- **Failing Test First:** Unit + integration test with a multi-chunk generator double proving current `_synthesize_native` truncates after chunk 1, AND test proving `find_spec("kokoro") != None` WITHOUT local weights still marks `validated=False` and raises `ModelUnavailable` (zero network download attempt). Plus real Piper WAV synthesis test in container verifying intelligible non-silent, non-clipped PT-BR audio.
- **Real Consumer Proof:** `ProviderService` catalog + `Studio` voice selection using Piper in container; Kokoro explicitly unavailable (`validated=False`) in container since weights are absent.
- **Rollback:** `git revert <commit_sha>`.

---

### Wave REC-03 — Product Integration & Browser UX (Executor: `Flash 3.8`/`Hydrogen Medium` | Reviewer: `Carbon High`/`Neon High`)

#### `REC-03.01` (P1 | Dep: `REC-02.01–05`) — Studio Import Route, Preview, Assisted Mode (`GAI-02`) & Storyboard Continuity
- **Files to Modify/Reuse:**
  - `renderer/app/studio/api/routes.py`: Add authorized multipart upload endpoint `POST /studio/videos/{video_id}/scenes/{scene_id}/media/import` (and/or video-level import) wired to `uc.media.import_media` with explicit max body size limit, auth/ownership check, `expected_asset_id` CAS (`409 Conflict` on stale revision), license + attribution + source_url fields, and trim/crop/mute scene metadata via existing `scene_assets` (`0050_scene_assets.sql`). Update `GET /studio/videos/{video_id}/scenes/{scene_id}/asset` (`routes.py:1688`) to serve accurate MIME (`image/png`, `video/mp4`, `video/webm`) for `<video>`/`<img>` preview.
  - `renderer/app/studio/api/panel_video_storyboard_js.py` & `panel_video_workspace.py`: Replace disabled `<input type="file" disabled>` at line 411 with real external media upload + license selector + image/video preview + trim/mute controls + **generic Assisted Generation panel (`GAI-02`)** (editable/copyable scene prompt with duration/aspect/identity context, no subscription automation, no unverified quota display). Preserve existing client undo/redo (`panel_video_storyboard_js.py:49,169-174`), scene add/reorder/edit/delete, and "gerar faltantes" (`ProduceAssets`) without creating a new SPA!
- **Failing Test First:** FastAPI `TestClient` integration tests proving: (a) `POST .../media/import` accepts real PNG & real MP4, updates scene with CAS, serves correct `Content-Type` on `GET .../asset`, and renders into MP4; (b) stale `expected_asset_id` returns `409`; (c) unauthenticated / invalid license / fake MP4 / oversized payload returns `401`/`400`/`413`/`422`; (d) uploading to scene 1 leaves scene 2 narration/assets untouched; (e) storyboard HTML no longer contains `O envio de arquivos ainda não existe no servidor`.
- **Real Consumer Proof:** Full FastAPI route → `ImportExternalMedia` → `PostgresAssetRepository` → `GET .../asset` → `PlanFfmpegRenderer`.
- **Rollback:** `git revert <commit_sha>`.

#### `REC-03.02` (P1 | Dep: `REC-03.01`) — Real Browser E2E (Playwright Desktop & Mobile + Node JS Tests)
- **Files to Modify/Add/Reuse:**
  - Reuse `docker-compose.e2e.yml` (set `STUDIO_BUDGET_GUARD: "1"`, `MAX_COST_USD_PER_VIDEO: "0"`, `STUDIO_PUBLICATION_ENABLED: "0"`), `scripts/run-e2e-full.sh`, `scripts/run-e2e-tests.sh`, `tests/e2e_ux/`, `tests/e2e_full/`.
  - Add Playwright test(s) in `tests/e2e_ux/` (e.g. `test_e2e_external_media_and_assisted.py`) exercising desktop (`1280x800`) and mobile (`390x844`) viewports: open storyboard → copy/edit assisted prompt → upload real PNG & real MP4 fixtures → verify preview (`<img>`/`<video>`) → edit scene text → undo/redo → reload page (verify persistence, zero edit loss) → reject invalid file/missing license (error shown, prior media preserved) → generate missing → trigger render (zero external API calls).
- **Failing Test First:** Write the new Playwright journey test before finishing UI polish, run via isolated port `8100` (`docker-compose.e2e.yml`), observe failure on missing UI controls, fix, then re-run ALL `tests/e2e_ux` + `tests/e2e_full` + host Node JS tests (`test_erro_js.py`, `test_panel.py`, `test_workflow_*.py`, `test_publicacao_acao.py`, `test_falha_producao.py`).
- **Real Consumer Proof:** Real Chromium headless browser (`chromium-1255`) driving isolated Docker Studio on `127.0.0.1:8100` (port `8000` untouched).
- **Rollback:** `git revert <commit_sha>`.

#### `REC-03.03` (P1 | Dep: `REC-02.01–05`) — Pipeline Integration of Remaining V4 Gaps (3 Minimal Sub-Slices)
- **Sub-slice `REC-03.03a` (Creative Brief + Captions/Sync):**
  - Feed persisted `video.creative_brief` (`routes.py:1365-1409`) into `GenerateScript`/`GenerateLongScript` context and `RenderPlan` metadata/motion/audio hints while keeping frozen `EffectiveConfig` identity; enforce `CreativeSecurityViolation` (anti-FFmpeg) on `PUT /direction` too!
  - Consolidate SRT/VTT export (`routes.py:2270-2279` vs `adapters/captions_exporters.py` — remove unused duplicate or delegate cleanly) and wire audio-caption sync drift (`check_audio_caption_sync`) into `FfmpegQualityEvaluator` so observed drift ms is persisted in `QaReport`.
- **Sub-slice `REC-03.03b` (Canonical Render Cache, Preflight, Progress & Cancellation):**
  - Reuse canonical `PlanRegeneration` + `PostgresRenderPlanRepository` + `PlanFfmpegRenderer` (`wiring.py:341,583`) — wire preflight disk/codec check, per-shot progress updates on `RenderJob`, and cooperative cancellation check between shots/during FFmpeg subprocess.
  - Retire duplicate in-memory `application/render_engine.py` (`SegmentCacheManager`) or make it a thin view over `PlanRegeneration` (no duplicate cache store!).
- **Sub-slice `REC-03.03c` (QA Defect Detection, Bounded Selective Regeneration & Asset/License Provenance):**
  - Wire `domain/quality.py::compute_selective_regeneration` (with strict `max_attempts` cap) into QA/regeneration flow so a known defect (e.g. missing/black/frozen scene) produces a bounded selective regeneration plan that re-renders ONLY the affected scene while reusing unaffected scene segments & audio from `PlanRegeneration` cache (verified across restart!).
  - Enforce license provenance check (`verify_license_provenance`) before publication approval/claim; retire in-memory dict `application/asset_registry.py` and isolated `application/studio_workbench.py` (consolidating onto `PostgresAssetRepository` + existing `routes.py` storyboard commands).
- **Failing Test First:** Integration test on disposable Postgres + real FFmpeg proving: (1) editing 1 scene of a 3-scene video reuses cached segments & narration WAVs for the 2 untouched scenes after restart; (2) injecting a known QA defect triggers bounded selective regeneration (`attempt <= max_attempts`) and re-evaluates QA; (3) creative brief anti-FFmpeg injection is rejected via API and valid brief flows into script/plan; (4) unknown-license asset blocks publication.
- **Rollback:** `git revert <commit_sha>` per sub-slice.

---

### Wave REC-04 — Observed Pilots, Full Regression & Release Gate (Executor: `Flash 3.8`/`Carbon High` | Reviewer: `Neon High` + Human Operator)

#### `REC-04.01` (P0 | Dep: `REC-03.01–03`) — Real 60–90s Vertical Slice via Studio
- **Actions:**
  - Reclassify `tests/test_int_06_pilot.py` docstring/markers explicitly as `SMOKE` (15s short); keep test green.
  - Execute a real **60–90s vertical slice** through the canonical Studio API/pipeline (`budget_guard=True`, `$0.00` cap, `publication_enabled=False`) exercising: Piper PT-BR voice, imported real PNG + real MP4, PiP/multi-overlay, real crossfade, motion effect, multitrack audio (music + ambience + SFX + ducking), burned & exported captions, 1-scene edit + selective regeneration (measuring cache hits & time saved), `FfmpegQualityEvaluator` (`ebur128` real LUFS & `dBTP`, drift, frozen/black/silence), and kill switch `BLOCKED`.
  - Persist MP4 + sampled frames + sanitized metrics JSON + SHA-256 manifest in an exclusive run dir under `storage/output/runs/rec04_slice_<timestamp>_<id>/` and version the lightweight manifest under `evidence/rec-04/` (never commit large MP4s!).
- **Rollback:** Non-destructive run artifacts only; revert any harness script commit if needed.

#### `REC-04.02` (P0 | Dep: `REC-04.01`) — Original 5–8min Documentary & Controlled Paired Comparison vs V4-00
- **Actions:**
  - Render an original **5–8min (300–480s) 1080p documentary** via Studio using the V4-00 reference topic/script structure (`A História da Computação`), same container hardware/format, exercising the V4 capabilities (imported media, PiP/overlays, transitions, motion, multitrack + ducking, captions, selective regeneration).
  - Perform controlled paired comparison against V4-00 baseline (`run_20261126_132447_198e47cb` or controlled rebaseline on the same SHA/container if needed) measuring: `ffprobe` streams/fps/duration, `ebur128` LUFS & real `dBTP`, observed caption drift ms, `frozen_ratio`/`black_ratio`/`silence_ratio`, `RUSAGE_SELF`/`RUSAGE_CHILDREN` CPU & RAM (with kernel limitation note), per-stage wall time, real `usage_ledger` API cost (`$0.00`) & cost/min with valid duration denominator, selective regeneration savings, and real observed human/operator intervention time.
  - Evaluate second local profile (`BALANCED` local) if viable offline at `$0.00`; otherwise record explicit `DEFERRED` (with reason & operator sign-off required for paid APIs).
  - Preserve MP4s & sampled frames in exclusive run dir `storage/output/runs/rec04_pilot5m_<timestamp>_<id>/` and version manifest + hashes in `evidence/rec-04/`.
- **Rollback:** Non-destructive artifacts/docs only.

#### `REC-04.03` (P0 | Dep: `REC-04.02`) — Full Canonical + Browser Regression on Clean Final SHA
- **Actions:**
  - On the clean working tree AFTER the last functional code change, run:
    1. `./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q --junitxml=/test-reports/rec04-canonical-junit.xml`
    2. Host Node JS tests (`test_erro_js.py`, `test_panel.py`, `test_workflow_*.py`, `test_publicacao_acao.py`, `test_falha_producao.py`) so the 17 container Node skips are ALSO executed and proven green!
    3. Isolated Playwright browser suites (`scripts/run-e2e-full.sh` + `tests/e2e_ux` against isolated port `8100`).
  - Record exact SHA, image hash, migration count (`48` or `49` if `0054` added), exit codes (`0`), exact collected/passed/skipped counts reconciled to the exact integer, and sanitized logs/JUnit in `evidence/rec-04/`. If ANY test fails, fix root cause and re-run the **entire** suite on the new SHA (never combine partial retests!).
- **Rollback:** Revert offending commit if regression introduced; re-verify full suite.

#### `REC-04.04` (P0 | Dep: `REC-04.03`) — Independent Final Review (`Neon High`) & Release Gate
- **Actions:**
  - Independent `Neon High` review of full campaign diff, every G0–G7 gate, `TRACEABILITY-MATRIX.md`, `FINAL-REPORT.md`, and rubric scores (>=9.0/10 on every applicable dimension, zero open P0/P1).
  - If all technical gates pass, emit verdict **`TECHNICAL GO / AWAITING HUMAN REVIEW`** with playable paths, sampled frames, and audiovisual rubric for the human operator (intelligibility, composition, rhythm, media relevance, audio, captions >=9/10).
  - **NEVER** auto-approve human aesthetic review (`V4-00.06`, `V4-13.11`), **NEVER** enable publication, **NEVER** merge to `main`.

### 5.1 Explicit Out-of-Scope / `DEFERRED` Register
The following optional items are formally `DEFERRED` (not counted as `VERIFIED`, require explicit operator authorization & budget/infra decision to activate):
- **Paid External AI APIs (`GAI-03` Gemini Text, `GAI-04` Image, `GAI-05` Gemini TTS, `GAI-06` Veo Video, `GAI-08` Gemini Multimodal QA, `V4-02.04` live ElevenLabs, `V4-03.05` Freesound, `V4-05.15`, `V4-09.10–11`, `V4-13.04` Premium Pilot, 15–20min Paid Pilot):** Blocked by `$0.00` campaign ceiling (`PROMPT-MASTER.md` §7). Fail-closed `validated=False` / `not_verified` preserved.
- **Cloud Storage / Drive (`GAI-07`, `V4-11.14`):** Optional P2; local atomic storage + backup scripts active.
- **Optional External Render/ML Engines (`V4-05.02` ComfyUI, `V4-05.23`/`V4-08.12` Remotion, `V4-05.24` Blender, `V4-07.03` Whisper/WhisperX, `V4-08.11` Mac HW VideoToolbox, `V4-08.13` 2nd Renderer):** Not installed in canonical slim container; FFmpeg + Piper remain canonical.
- **CI/CD Pipelines (`V4-12.14` / `FS-03`):** Explicitly excluded by `PROMPT-MASTER.md` §7 (*"sem CI/CD"*).

---

## 6. Historical Addendum / Corrigendum for `INT-07-FINAL-REPORT.md`

Per `prompts/REC-00-audit.md` (*"Corrigir relatório histórico apenas via adendo rastreável"*), [`INT-07-FINAL-REPORT.md`](INT-07-FINAL-REPORT.md) is preserved unmodified as historical record, and the following factual discrepancies are formally recorded:

1. **Test Count Arithmetic Discrepancy (`INT-07-FINAL-REPORT.md:76-78`):**
   - Historical report stated: `4,416` collected, `4,389` passed, `20` skips, and `10` corrected non-conformities.
   - Arithmetic check: `4,389 + 10 + 20 = 4,419 ≠ 4,416` (unexplained **+3** discrepancy; the 10 numbered prose items mixed multi-file fixes with individual test failures, e.g., items 8 & 9 both addressed `panel_advanced.py` escaping and item 2 regenerated `renderplan.schema.json`).
   - Current container `--collect-only` at `5800f46` confirms `4,416` collected tests (excluding `tests/e2e_full` and `tests/e2e_ux`).
2. **Partial Retest Presented as Full Regression (`INT-07-FINAL-REPORT.md:65,89`):**
   - After modifying production code (`wiring.py`, `panel_advanced.py`) and tests in commit `72438e9`, only `228/228` tests were re-run. A partial retest does NOT satisfy Gate G6 (`QUALITY-GATES.md:10,17`).
3. **HEAD SHA Mismatch (`INT-07-FINAL-REPORT.md:6`):**
   - Historical report header cited `HEAD de Homologação: 8a01c34`, whereas the report and 10 fixes were actually committed in `72438e9ea215bbec12bd350d8c2606ca62bc7d94`.
4. **Browser E2E & Node.js Availability (`INT-07-FINAL-REPORT.md:77` & `V4-00-BASELINE-REPORT.md:28`):**
   - Historical reports treated Node.js and Playwright as unavailable on host. Preflight at `5800f46` proves Node `v26.0.0`, Playwright Python, and Chromium `1255` ARE present on the macOS host and runnable against isolated port `8100` (`docker-compose.e2e.yml`).
5. **Branch `main` State (`INT-07-FINAL-REPORT.md:17` & `PROMPT-MASTER.md:3`):**
   - `main` was subsequently merged at `42700cb331165a68455173a91c463d4733292cfd` (`be0c463` + `72438e9`). Recovery proceeds strictly on `develop` without modifying `main`.

---

## 7. Executor Self-Assessment (`QUALITY-RUBRIC.md`) — NON-APPROVING

> **Governance Notice:** Per `QUALITY-RUBRIC.md:20`, this table is strictly an **executor self-assessment with ZERO approval authority**. Approval requires independent evaluation and scoring (`>= 9.0/10` on every applicable dimension) by `Gemini 4 Carbon (High)` (`rec00-reviewer`) recorded in `evidence/rec-00/independent-review-carbon-high.md`.

| Dimension | Weight | Self-Assessed Score (Non-Approving) | Verifiable Evidence | Open Notes for Independent Reviewer |
|---|---:|---:|---|---|
| Functional Correctness & Integration (Audit Completeness) | 25% | 9.5 | All 13 `R01–R13`, 13 `A01–A13`, 21 `INT-01..07`, 9 `GAI-01..09`, 227 exact real `V4-00..13` IDs, and 17 `REC-00..04` tasks reconciled with exact `file:line` & real consumer tracing in `TRACEABILITY-MATRIX.md` and `REC-00-AUDIT-AND-PLAN.md` §2. | Audit wave does not claim runtime credit for unexecuted REC-01..04 code fixes. |
| Architecture & Simplicity | 20% | 9.5 | Complete pre-REC-01 financial & resilience inventory (§3: 12 migrations, locks, constraints, canonical classes vs parallel duplicates); AS-IS/TO-BE map (§4) prevents duplicating `PaidOperationGuard`, `ProductionCoordinator`, `PlanRegeneration`, `PostgresAssetRepository`, or Studio UI; concrete rollback per task (§5). | Confirm sub-slices `REC-01.02b` and `REC-03.03a/b/c` stay within original V4/GAI scope. |
| Tests & Regression Planning | 20% | 9.5 | Exact container (`4,416`) & host E2E (`26`) test collection verified read-only; failing-test-first + positive/negative + real-consumer proofs specified for every `REC-01.01..REC-04.04` task; host Node v26 & Playwright Chromium 1255 availability verified. | No production code edited in REC-00 (strictly compliant with boundary). |
| Security, Budget & Reliability | 20% | 9.5 | G0 preflight verified disposable DB proof guard (`verified_test_connect`), dev ports 8000/5678 untouched, kill switch (`RunPublication.enabled=False` → `BLOCKED`), `$0.00` spend, `main` (`42700cb`) untouched, and `settings.py` default caution (`publication_enabled=True`/`budget_guard=False`) flagged explicitly. | `docker-compose.e2e.yml:40` `STUDIO_BUDGET_GUARD=0` flagged for REC-03.02/REC-04 hardening. |
| Evidence & Operations | 15% | 9.5 | `evidence/rec-00/preflight-and-inventory.md` captures commands, exit codes, SHAs, container image IDs, tree hashes, migration counts, and SHA-256 hashes of all 16 `storage/output/` files; `INT-07-FINAL-REPORT.md` corrigendum (§6); control files initialized cleanly. | Pending independent review by `Gemini 4 Carbon (High)`. |
| **Weighted Self-Assessment** | **100%** | **9.50** | **STATUS: `IMPLEMENTED` — AWAITING INDEPENDENT REVIEW (`rec00-reviewer`)** | **Zero approval power until independent reviewer signs off.** |
