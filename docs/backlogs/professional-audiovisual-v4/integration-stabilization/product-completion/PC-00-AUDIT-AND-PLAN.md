# PC-00 — Focal Code Audit, Traceability Reconciliation & Test-First Execution Plan (`PC-00.01` & `PC-00.02`)

- **Campaign:** V4 Product Completion (`PC-00`..`PC-09`)
- **Audited Branch / SHA:** `develop` @ `8484b7202d7080d916a501a945bc81a2b51274cf`
- **Protected `main` SHA:** `42700cb331165a68455173a91c463d4733292cfd` (**strictly untouched**; `main...develop` = `1 / 14`)
- **Author Role:** `pc00-auditor` (`PC-00.01` & `PC-00.02` — documentary audit & isolated repro only; **zero edits to product code or existing tests**)
- **Mandatory Reviewer:** Independent `Carbon High` session (`pc00-reviewer` per [MODEL-ROUTING.md](MODEL-ROUTING.md))
- **External API Spend:** **`$0.00` USD** | **Publication Kill Switch:** **`BLOCKED`** (`STUDIO_PUBLICATION_ENABLED=0`)
- **Release / Audiovisual Verdict:** **`NO-GO / PLANNING ONLY`** (no audiovisual GO granted; no human approval inferred)

---

## 1. Baseline, Gate `G0` Preflight & Historical Status Reconciliation (`PC-00.01`)

### 1.1 Gate `G0` Preflight Summary
All preflight checks passed with zero mutations to product code, existing tests, DEV ports, or `main`. Full command outputs and digests are recorded in [evidence/pc00/preflight-and-repro.md](evidence/pc00/preflight-and-repro.md) and [evidence/pc00/pc01-bug-repro.log](evidence/pc00/pc01-bug-repro.log):
- **Git Alignment:** `HEAD == origin/develop == 8484b7202d7080d916a501a945bc81a2b51274cf`; `main == 42700cb331165a68455173a91c463d4733292cfd` (`git rev-list --left-right --count main...develop` = `1` commit on `main`, `14` commits on `develop` from `5800f46` to `8484b72`).
- **Container & DB Isolation (`./scripts/test-container.sh`):**
  - `hash renderer/app: checkout=b677160103d832a3 imagem=b677160103d832a3` (`alterações_em_renderer/tests=não`)
  - `migrações: checkout=49 imagem=49` (`0001_init.sql`..`0054_paid_operation_external_ref.sql`)
  - `faceless-renderer:test` = `sha256:d6c55857bad654ed0a99a7717eb6d45e9fb8cfbd6a1aa7725014d93d6f8017bb`
  - `faceless-renderer-pytest:test` = `sha256:2be92f04d4f9993c82177e0439e96a95f4ef38c4db3ade4a9fdf18f70b3c811d`
  - `postgres:16-alpine` = `sha256:81e77a4833487b8132fe4b00bedd39dc3f74b8641e387f19312a48f7de218c2e` (`--tmpfs`, 64-hex `/budget-test-proof/proof`, destroyed on exit)
  - Runtime inside container: `Python 3.12.16`, `ffmpeg 7.1.5-0+deb13u1`, `piper-tts==1.8.0`, bundled offline voice `/opt/voices/pt_BR-faber-medium.onnx` (`63,221,984 B`); Host: `Docker 29.1.3`, `Node v26.0.0`.
- **Safety Boundaries:** Zero paid API keys in shell/container; DEV containers on `127.0.0.1:8000` (`renderer-1`) and `127.0.0.1:5678` (`n8n-1`) strictly untouched.
- **Explicit Runtime Caveat Observed in `settings.py`:** `Settings.publication_enabled` (`renderer/app/studio/composition/settings.py:71,101`) defaults to `True` (`STUDIO_PUBLICATION_ENABLED="1"`) and `max_cost_month` (`:52,90`) defaults to `15.0` when env vars are unset. Every isolated test, E2E stack, and pilot run in `PC-01`..`PC-09` MUST explicitly inject `STUDIO_PUBLICATION_ENABLED=0`, `MAX_COST_USD_PER_VIDEO=0.0`, `MAX_COST_USD_PER_MONTH=0.0`, and `STUDIO_BUDGET_GUARD=1`.

### 1.2 Historical Status Reconciliation (`../TRACEABILITY-MATRIX.md` vs `../FINAL-REPORT.md` vs `REC-04.03–04` Review)
Direct inspection of commit `2e8b153c25b2d4a723f05e1f93f1a49c4dcbd1d6` explains every status mismatch between the historical REC documents (full table in [TRACEABILITY-MATRIX.md §(d)](TRACEABILITY-MATRIX.md)):
1. **Pre-Review Snapshot Lag in `2e8b153`:** `../TRACEABILITY-MATRIX.md` (`:17–22, :41–42, :70, :75, :103, :408, :434–435`) and `../FINAL-REPORT.md` (`:55–56, :73, :78`) were authored before the independent `Gemini 4 Neon (High)` release-gate review ran, so they still list `V4-13.14`, `R13`, `A13`, `INT-07.02`, `REC-04.03`, and `REC-04.04` as `IMPLEMENTED (Pending Final Neon High Review)` — and `R12`/`INT-07.01` as `VERIFIED` with a pending-audit caveat (`P2-04.3`).
2. **Independent `Neon High` Sign-Off Confirmed in Same Commit:** `../evidence/rec-04/rec-04-03-04-independent-review-neon-high.md` (`:8–9, :112, :129, :142, :148–150`) independently **APPROVED** `REC-04.03` (**`9.585/10`**, min `9.5`) and `REC-04.04` (**`9.470/10`**, min `9.2`), instructing in `P2-04.3` (`:112`) to promote `REC-04.03` (`R12`, `INT-07.01`) and `REC-04.04` (`R13`, `A13`, `INT-07.02`, `V4-13.14`) to technical `VERIFIED`. `../EXECUTION-STATE.md` (`:6, :44–45, :54, :59`) reflected that promotion, whereas `../TRACEABILITY-MATRIX.md` and `../FINAL-REPORT.md` remained at the pre-review snapshot (`180/44/2/1`).
3. **Reconciled Baseline Counts (227 Real V4 IDs):**
   - Historical REC pre-review snapshot (`../TRACEABILITY-MATRIX.md:42`): `180 VERIFIED` + `44 DEFERRED` + `2 AWAITING_HUMAN_REVIEW` + `1 IMPLEMENTED` = **`227`** (`0 P0` deferred).
   - Historical REC post-`Neon High` approval (`2e8b153`): `181` technical `VERIFIED` + `44 DEFERRED` + `2 AWAITING_HUMAN_REVIEW` + `0 IMPLEMENTED` = **`227`**.
   - Active Product Completion campaign (`8484b72`): Historical REC counts are preserved untouched, **NOT** inflated into "100% V4"; `V4-13.14` re-opens for `PC-09.02`; `V4-00.06` & `V4-13.11` remain `AWAITING_HUMAN_REVIEW`; all `44` deferred IDs are actively tracked in [TRACEABILITY-MATRIX.md](TRACEABILITY-MATRIX.md); and the `P1` edit-integrity defect (`PC-01`) blocks all downstream PC work.
4. **Historical Doc Nits Reconciled (`P2-04.1`, `P2-04.2`):** `../FINAL-REPORT.md:155` listed `v4_piloto_5min.mp4` instead of real file `v4_piloto_audiovisual_5min.mp4`; `../TRACEABILITY-MATRIX.md:111` rendered `<built-in function id>` instead of `{id}`. Both are corrected in `product-completion/TRACEABILITY-MATRIX.md` without modifying historical files.

---

## 2. Deep Code Audit & Call Graphs (`HEAD 8484b72`)

### 2.1 PC-01 Edit-Integrity Defect — Exact Code & Call Graph Audit

```
Browser (panel_video_storyboard_js.py:570 doImportMedia)
  └─ POST /studio/videos/{vid}/scenes/{sid}/media/import (routes.py:1720-1897)
       ├─ Validates trim finite/non-negative/end>start (routes.py:1838-1846) [MISSING: duration bound vs media probe!]
       └─ ImportExternalMedia.execute (application/media.py:468-593)
            ├─ probe.probe(data, mime) (media.py:516) [ProbedMedia.duration_s IGNORED for trim validation!]
            ├─ TX #1: PostgresAssetRepository.add_and_swap_scene_asset (media_repo.py:68-101)
            │    ├─ pg_advisory_xact_lock(hashtextextended(cache_key, 0)) (:84)
            │    ├─ INSERT studio.assets ON CONFLICT DO NOTHING (:85-90)
            │    └─ UPDATE studio.scenes SET asset_id = %s WHERE asset_id IS NOT DISTINCT FROM expected_asset_id (:93-97)
            │    └─ COMMITS TX #1!
            └─ TX #2: ImportExternalMedia._apply_scene_trim (media.py:602-619)
                 ├─ If trim provided -> scripts.save_scene_assets(scene_id, [DomainSceneAsset(..., role="base", motion="none")])
                 └─ If trim is None  -> scripts.save_scene_assets(scene_id, [])
                      └─ PostgresScriptRepository.save_scene_assets (editorial_repo.py:448-469)
                           └─ DELETE FROM studio.scene_assets WHERE scene_id = %s  <-- WIPES ALL OVERLAYS / PIP / MOTION!
```

**Six Confirmed Integrity Findings in This Path (All Verified in Code + Live Repro):**
1. **Unconditional Overlay Destruction (`media.py:602-619` → `editorial_repo.py:451`):** Both replacing base **without** trim (`save_scene_assets(scene_id, [])`) and replacing base **with** trim (`save_scene_assets(scene_id, [sa])`) delete every row in `studio.scene_assets` for `scene_id`, destroying all `role="overlay"` PNG/MP4 PiP layers, secondary B-rolls, custom `motion`, and `transition_kind`/`transition_duration_s`. **Live proof:** [evidence/pc00/pc01-bug-repro.log](evidence/pc00/pc01-bug-repro.log) (`Repro A`: `3 → 0` rows; `Repro B`: `2 → 1` row).
2. **Split Transactions & Broken Compensation (`media.py:578-593` → `media_repo.py:68-101` + `103-114`):** `add_and_swap_scene_asset` commits `studio.scenes.asset_id` in Transaction #1 before `_apply_scene_trim` runs Transaction #2. If Transaction #2 fails, Transaction #1 stays committed, `_compensate_failed_import` (`media.py:621-635`) cannot delete the asset because `studio.scenes.asset_id` already references it, and `scenes.asset_id` becomes permanently desynchronized from `scene_assets`. **Live proof:** [evidence/pc00/pc01-bug-repro.log](evidence/pc00/pc01-bug-repro.log) (`Repro C`: `scenes.asset_id=b666fe46` while `scene_assets.asset_id=a4f1b9b8`).
3. **ABA & Partial-CAS Gap (`media_repo.py:54-56, 94-96`, `0001_init.sql`..`0051`):** `studio.scenes` has no monotonic `edit_revision` counter. CAS checks only `expected_asset_id`, which cannot detect A→B→A ABA races, same-asset trim edits, or concurrent overlay mutations.
4. **`uq_scene_asset_pos` Collision Risk (`0050_scene_assets.sql:14`):** `UNIQUE (scene_id, position)` means inserting a base trim row at `position=0` will collide if an overlay was previously inserted at `position=0`.
5. **Routes Bypassing Application Layer & Ownership Guards (`routes.py:1956-1987`):** `GET/POST/DELETE /videos/{vid}/scenes/{sid}/assets` invoke `ed.get_script.scripts.*` directly with untyped `body: dict`, without verifying `scene_id` belongs to `video_id`, without verifying `asset_id` belongs to the project/video scope, without finite-number/duration validation, and without CAS revision bumping.
6. **Downstream Render-Job Hash Blind Spot (`application/render.py:165-180`):** `StartRender.execute` computes `overlay_sig` ONLY for `sa.role == "overlay"` — omitting `sa.role == "base"` trim (`start_s`/`end_s`) and layer transform/motion/transition attributes! Editing base trim on the same asset can produce an identical `input_hash` and fail to enqueue a fresh render job.
7. **Client Undo/Redo & Reload Drift (`panel_video_storyboard_js.py:297-300, 642-660`):** `reconcile()` calls `POST /scenes/{id}/media` (`SwapSceneMedia`) without `expected_scene_revision` and without restoring `trim_start_s`/`trim_end_s` or `scene_assets`; `doImportMedia()` does not clear `m.trim_start_s`/`m.trim_end_s` client-side when re-importing without trim (`P2 #3` from `REC-03.01-02`).
8. **Silent Exception Swallowing in `GetSceneTiming` (`media.py:651-654`):** Broad `except Exception: continue` silently drops DB/read failures instead of surfacing operational errors (scheduled for hardening in `PC-06.02`).

### 2.2 Studio Routes & Frontend Templates / JS Audit
| Subsystem | Exact Files & Symbols (`8484b72`) | Current State & Gaps |
|---|---|---|
| **Navigation & Shell** | `api/panel_video_nav.py:21-66` (`AREA_LABELS`, 6 tabs: `visao-geral`, `direcao`, `roteiro`, `narracao`, `composicao`, `qualidade`/`publicacao`); `api/shell_v3.py` | V3 server-rendered HTML + vanilla JS; preserves no-SPA constraint (`MASTER-PROMPT.md`). |
| **Storyboard & Media Replace** | `api/panel_video_workspace.py:541-681`, `api/panel_video_storyboard_js.py:8-707` (`STORYBOARD_JS`: `reconcile:258`, `openMedia:512`, `pickAsset:518`, `pickCandidate:524`, `doImportMedia:570`) | Supports PNG/MP4 upload + trim inputs + GAI-02 assisted prompt. **Gaps:** No layer editor UI (`V4-10.07`), no transition selector beyond `none`/`fade` (`V4-10.09`), channel media tab says *"ainda não tem leitura no servidor"* (`:470`, `V4-11.09`), no scene revision CAS in `reconcile()`/`.doImportMedia()`. |
| **Audio Studio UI** | `api/panel_video_workspace.py:461` (`_area_narracao`), `api/routes.py:2591-2606` (narration WAV + regen) | Narration-only preview & regeneration. **Gaps:** Zero HTTP routes or UI for audio import (`V4-03.02`), 3+ multitrack CRUD (`V4-03.16`/`V4-10.06`), mix-only preview (`V4-03.15`), or EQ/compression controls (`V4-03.13`). |
| **Voice & Channel Identity UI** | `api/panel_channels.py:642-944`, `api/panel_styles.py:644-878` (`_render_voice_cards:644`, `_load_music_tracks:813`), `api/panel_channel_style.py:390` | Uses `ProviderCatalog` + `VisualStyle` (`params.voice.model`). **Gaps:** No canonical voice catalog attributes/capabilities endpoint (`V4-02.05–06`), no pronunciation dictionary or pacing/intention UI (`V4-02.07–09`), no voice preview WAV by profile before synthesis. |
| **Creative Direction UI** | `api/panel_video_workspace.py:154-307` (`_area_direcao`, `DIRECAO_JS`), `api/routes.py:1374-1431` (`GET/POST/PUT /videos/{id}/direction`) | Persists video-level `CreativeBrief` with CLI-injection guard (`422`). **Gaps:** No per-scene direction (`SceneCreativeDirection`: goal, editorial emotion/intensity, `ShotIntent`) persistence, HTTP endpoints, or storyboard controls (`V4-06.03–05`). |
| **Composition & Preview UI** | `api/panel_video_workspace.py` (`/composicao`, `/previa`), `api/routes.py:2004, 2507, 2629` | Runs 1080p full render only. **Gaps:** No low-res preview preset trigger (`V4-04.19`/`V4-08.10`), no renderer capability badge/preflight endpoint (`V4-08.01`), no animated template or post-processing controls (`V4-05.17–30`). |

### 2.3 `RenderPlan`, Compiler, FFmpeg Renderer & Render Cache Audit
```
HTTP/Coordinator -> StartRender (render.py:155) -> RunRender._render (render.py:373)
  ├─ _effective_config -> style_from_effective_config (render.py:85) + config_snapshot_for (:119)
  ├─ _cached_narration (domain/render_cache.py:54 narration_fingerprint) -> Voice.speak (PiperVoice)
  ├─ _overlay_layers (render.py:340) [HARDCODES _overlay_placement(position), scale=0.45 -> NEEDS PC-04.01 per-layer geometry!]
  └─ PlanFfmpegRenderer.render (render_plan_ffmpeg.py:440)
       ├─ _preflight (render_plan_ffmpeg.py:465 -> domain/render_engine.py:138 evaluate_preflight)
       ├─ _build_plan (render_plan_ffmpeg.py:618) [produces RenderPlan v2 + _brief_render_hints:66]
       ├─ _compile (render_plan_ffmpeg.py:509)
       │    ├─ structure_render_plan (application/render_compiler.py:170)
       │    │    ├─ MAX_OVERLAYS_PER_SCENE = 8 (:46)
       │    │    ├─ SUPPORTED_TRANSITIONS = none|fade|crossfade|slide_left|slide_right|wipe_left|wipe_right (:47-48)
       │    │    └─ _validate_transitions (:309), _validate_overlays (:334), _compile_layers (:386)
       │    └─ compile_render_plan (adapters/render_plan_compiler.py:219)
       │         ├─ _compile_shot (:338), _overlay_filter (:449), _zoompan (:525 + calculate_motion_curve)
       │         ├─ _compile_concat (:556 — real tpad + xfade)
       │         └─ compile_multitrack_audio_args (:619 — verify_audio_licenses + adelay/afade/sidechaincompress/loudnorm)
       ├─ _reuse_hits / _record (render_plan_ffmpeg.py:528-588 -> domain/render_cache.py:68 visual_fingerprint)
       └─ FfmpegQualityEvaluator.evaluate (adapters/quality_ffmpeg.py:253 -> adapters/qa_ffmpeg.py:25 FfmpegQa)
```
**Key Gaps Identified:**
- `domain/render_plan.py:525` (`Output`) has `width`/`height`/`fps`/`codec` — ready to support preview presets (`PC-05.01`) without inventing a second pipeline, PROVIDED `visual_fingerprint` (`domain/render_cache.py:68`) and `CompiledRender` include `(preset_kind, width, height)` so preview cache NEVER collides with 1080p production cache!
- `domain/render_plan.py:197` (`Effects`) currently only holds `motion` — needs additive optional fields (`post_processing`, `templates`) with defaults=`None` so existing v1/v2 golden hashes (`test_render_golden.py` `8/8`) remain **byte-for-byte identical** when unset!
- `domain/visual_style.py:67` restricts `TRANSITION_KINDS = frozenset({"none", "fade"})` even though `render_compiler.py:47-48` and `render_plan_compiler.py:556` already implement real `crossfade`/`slide_left`/`slide_right`/`wipe_left`/`wipe_right`.

### 2.4 Audio Pipeline Audit
- **Verified in Renderer:** `domain/audio_catalog.py` (`AudioCategory`, `AudioTrack`, `AudioCatalog`), `domain/audio_multitrack.py` (`AudioEvent`, `MultitrackAudioPlan`, `verify_audio_licenses`, `build_multitrack_plan`), `adapters/render_plan_compiler.py:619` (`compile_multitrack_audio_args`), and `adapters/qa_ffmpeg.py:25` (`FfmpegQa` with real `ebur128=peak=true` LUFS/dBTP & `silencedetect`).
- **Gaps for `PC-02`:**
  1. `application/media.py:19-21` has no `ALLOWED_AUDIO_MIME` (`audio/wav`, `audio/mpeg`, `audio/mp4`/`audio/aac`, `audio/ogg`, `audio/flac`) and `adapters/media_probe.py` probes only image/video.
  2. No Postgres persistence for project/video multitrack audio configuration (or audio `AssetKind.audio` import + license + attribution + duration).
  3. `RunRender._render` (`render.py:373`) does not yet populate `RenderSpec.multitrack` / `RenderSpec.audio_catalog` from persisted video tracks.
  4. No FFmpeg parameterized EQ (`equalizer`/`highpass`/`lowpass`) or speech compressor (`acompressor`) args in `compile_multitrack_audio_args` / `_mix_filter` (`domain/audio_dsp.py` has 0 app callers and only does Python PCM mixing for test fixtures).
  5. No mix-only preview route (`POST/GET /videos/{id}/audio/preview`) producing real WAV/AAC from the exact same `MultitrackAudioPlan` compiled by `compile_multitrack_audio_args`.

### 2.5 Voice / TTS Pipeline Audit
- **Verified in Runtime:** `adapters/voice_piper.py:20` (`PiperVoice`, offline `/opt/voices/pt_BR-faber-medium.onnx`), `adapters/voice_kokoro.py:114` (`KokoroVoice`, fail-closed `validated=False` without binary weights), `adapters/voice_elevenlabs.py:16` (`ElevenLabsVoice`, `validated=False`, `$0.00`), `application/scene_narration.py:59,95` (`SceneNarration`, `RegenerateSceneNarration`), `composition/providers.py:143` (`_provider_implementations`).
- **Gaps for `PC-03.01`–`PC-03.02`:**
  1. `domain/voice_catalog.py` (`VoiceProfile`) and `composition/voice_catalog.py` (`list_voice_catalog`, `find_voice_profile`) have **0 callers**; Studio exposes raw provider specs without structured vocal identity (language, gender, style, real capability flags: `supports_emotion=False`, `supports_pacing=True`, `supports_pronunciation_dict=True`, `is_demo=True/False`).
  2. `domain/voice_preprocessing.py` (`PronunciationDictionary`, `apply_pacing_and_pauses`, `EmotionalIntention`) has **0 callers**; `PiperVoice.speak` receives unprocessed narration text, and `narration_fingerprint` (`domain/render_cache.py:54`) is not fed the preprocessed text / dictionary version / pacing params.
  3. **Honesty Constraint:** `PiperVoice` does NOT support neural emotional synthesis — `PC-03.02` MUST explicitly report `supports_emotion=False` and NEVER relabel speed/pause tweaks as neural emotion.

### 2.6 Visual Style, Motion, Creative Director & QA Audit
- `domain/visual_style.py:67,78`: `APPLIED_GROUPS = {"motion", "music", "caption", "palette", "voice", "transition"}`; `TRANSITION_KINDS = {"none", "fade"}`.
- `domain/motion_effects.py`: Only `calculate_motion_curve:49` is called (`render_plan_compiler.py:45`). `ColorGrading:18`, `PostProcessingEffects:72`, `LowerThirdGraphic:88`, `InfographicOverlay:106` have **0 callers**.
- `domain/creative_director.py`: `CreativeBrief:91`, `FORBIDDEN_COMMAND_PATTERNS:27`, `CreativeSecurityViolation:43` are wired in `routes.py:61`, `editorial.py:18`, `longform.py:36`, `wiring.py:123`. `SceneCreativeDirection:68` and `ShotIntent:56` have **0 callers** and no DB table/columns.
- `application/production.py:416` (`QaHandler`) + `adapters/quality_ffmpeg.py:253` (`FfmpegQualityEvaluator`) + `adapters/quality_semantic.py:18` (`NotVerifiedSemanticChecker`): `QaHandler` wires `scene_repair=None` in `wiring.py:748-752` (intentional under `$0.00` ceiling, needs explicit safe manual action & state reporting in `PC-06.01`). `domain/asset_registry.py:63-65,85-91` (`ai-generated:<slug>` branch) needs strict allowlist/regex hardening (`PC-06.02`) so disallowed licenses cannot be smuggled under `ai-generated:cc-by-nc-nd-4.0`.

### 2.7 Unwired / Dead Modules Inventory (AST-Verified for `PC-05.03`)

Verified across all `.py` files in `renderer/app/` via Python AST import scan:

| Module File | App Callers (`renderer/app/`) | Test Callers (`tests/`) | Canonical Equivalent in Production | Proposed `PC-05.03` Action (After `PC-02`..`PC-05.02`) |
|---|---:|---|---|---|
| `application/render_engine.py` (`SegmentCacheManager`, `SegmentedRenderPlanner`, `ProgressTracker`) | **0** | `test_v4_render_engine.py` | `application/render_cache.py` (`PlanRegeneration`) + `PostgresRenderPlanRepository` + `PlanFfmpegRenderer` | **Retire duplicate** (migrate relevant unit coverage to canonical `PlanRegeneration` + `PlanFfmpegRenderer`) |
| `application/asset_registry.py` (`AssetCatalogManager`) | **0** | `test_v4_asset_management.py` | `adapters/postgres/media_repo.py` (`PostgresAssetRepository` + SQL tags in `PC-05.02`) | **Retire duplicate** (migrate tag/orphan tests to canonical `PostgresAssetRepository`) |
| `application/studio_workbench.py` & `domain/studio_workbench.py` | **0** | `test_v4_studio_ux.py` | `routes.py` + `application/editorial.py` + `application/longform.py` + `panel_video_storyboard_js.py` | **Retire duplicate** (real Studio routes/browser E2E supersede in-memory workbench) |
| `application/resilience.py` (`ReadinessChecker`, etc.) | **0** | `test_v4_reliability_scale.py` | `renderer/app/main.py` (`/ready` + `Studio.ping`) + `ProductionCoordinator` | **Retire duplicate** (preserve `domain/resilience.py::StageTimeoutError` & `logical_operation_key` which ARE wired) |
| `composition/voice_catalog.py` & `domain/voice_catalog.py` | **0** | `test_v4_voice_professional.py` | `composition/providers.py` (`ProviderCatalog`) | **Integrate useful domain types** (`VoiceProfile`/capability flags) into `ProviderCatalog` in `PC-03.01`; retire parallel catalog list in `PC-05.03` |
| `domain/voice_preprocessing.py` | **0** | `test_v4_voice_professional.py` | `domain/render_cache.py:54` (`narration_fingerprint`) | **Integrate** `PronunciationDictionary` + `apply_pacing_and_pauses` into `PC-03.02`; retire duplicate `narration_fingerprint:90` in `PC-05.03` |
| `domain/voice_audio.py` | **0** | `test_v4_voice_professional.py`, `test_v4_audio_professional.py` | `adapters/qa_ffmpeg.py` (`FfmpegQa` `ebur128`/`silencedetect`) | **Evaluate/Integrate or Retire** in `PC-03.02`/`PC-05.03` (use for fast PCM narration check or retire duplicate) |
| `domain/audio_dsp.py` | **0** | 5 test files (fixture tone/WAV helpers) | `adapters/render_plan_compiler.py` (`compile_multitrack_audio_args`) | **Keep test-fixture helpers** or move/mark explicitly test-only; never build a second Python audio mixer |
| `domain/motion_effects.py` (partial) | **1** (`calculate_motion_curve` only) | `test_v4_visual_motion.py` | `PlanFfmpegRenderer` / `render_plan_compiler.py` | **Integrate** `LowerThirdGraphic`, `InfographicOverlay`, `ColorGrading`, `PostProcessingEffects` in `PC-04.03`–`04.04` |
| `domain/creative_director.py` (partial) | **5** (`CreativeBrief` only) | 6 test files | `routes.py`, `editorial.py`, `longform.py` | **Integrate** `SceneCreativeDirection` & `ShotIntent` in `PC-03.03` |
| `domain/render_engine.py` (partial) | **1** real (`evaluate_preflight`, `RenderProgress`) + 1 dead (`render_hardware`) | `test_rec_03_pipeline_integration.py`, `test_v4_render_engine.py` | `PlanFfmpegRenderer` | **Integrate** `RendererCapabilities` + `RenderQualityPreset` in `PC-05.01` |
| `adapters/render_hardware.py` | **0** | `test_v4_render_engine.py` | CPU `libx264` in Docker | **Use read-only in `PC-07.02` diagnostic**; keep opt-in or retire if unused |

---

## 3. Reconciliation of 44 Deferred V4 IDs, 6 Pending GAI IDs & Operator Decision Register (`PC-00.01`)

### 3.1 Verified Scope Breakdown (No Silent Reclassification)
Per [SCOPE-MATRIX.md](SCOPE-MATRIX.md) and verified 1-to-1 in [TRACEABILITY-MATRIX.md](TRACEABILITY-MATRIX.md):
- **`27 OBRIGATÓRIO_LOCAL` V4 IDs** — Mandatory local product completion under `$0.00` API budget (NON-NEGOTIABLE by executor; must reach real UI→coordinator→`RenderPlan`→FFmpeg→QA/persistence proof):
  - Audio Studio (`5`): `V4-03.02`, `V4-03.13`, `V4-03.15`, `V4-03.16`, `V4-10.06` → `PC-02.01`–`02.03`
  - Voice & Creative Direction (`8`): `V4-02.05`, `V4-02.06`, `V4-02.07`, `V4-02.08`, `V4-02.09`, `V4-06.03`, `V4-06.04`, `V4-06.05` → `PC-03.01`–`03.03`
  - Visual Studio (`10`): `V4-10.07`, `V4-10.09`, `V4-05.17`, `V4-05.18`, `V4-05.20`, `V4-05.22`, `V4-05.27`, `V4-05.28`, `V4-05.29`, `V4-05.30` → `PC-04.01`–`04.04`
  - Preview, Capabilities & Asset Library (`4`): `V4-04.19`, `V4-08.01`, `V4-08.10`, `V4-11.09` → `PC-05.01`–`05.02`
- **`4 VIABILIDADE` V4 IDs** — Offline feasibility diagnosis; if unavailable offline without spend/download, remain explicitly `BLOCKED`/`DEFERRED` pending operator decision (never faked):
  - `V4-02.15`, `V4-13.05` (`PC-07.01`: 2nd offline voice + blind comparison)
  - `V4-08.11` (`PC-07.02`: Apple Silicon / local hardware acceleration evaluation)
  - `V4-13.03` (`PC-08.02`: `balanced_local` pilot without API spend)
- **`13 OPCIONAL_AUTORIZAÇÃO` V4 IDs + `6` Pending GAI IDs (`GAI-03`..`GAI-08`)** — Explicitly require separate operator authorization, credentials/BYOK, license review, or budget; **ZERO execution/install/spend in this campaign** (`PC-07.02`–`07.03` produce offline plans only):
  - External engines/tools (`8`): `V4-03.05` (Freesound), `V4-05.02` (ComfyUI), `V4-05.23` & `V4-08.12` (Remotion), `V4-05.24` (Blender), `V4-07.03` (Whisper/WhisperX), `V4-08.13` (second renderer), `V4-12.14` (CI/CD — explicitly out of scope).
  - Paid GenAI / Cloud / Premium (`5` V4 + `6` GAI): `V4-05.15`/`GAI-06` (Veo), `V4-09.10`/`V4-09.11`/`GAI-08` (multimodal QA LLM), `V4-11.14`/`GAI-07` (Drive/S3 storage), `V4-13.04` (premium 15–20min pilot), `GAI-03` (Gemini Text), `GAI-04` (Image), `GAI-05` (Gemini TTS).

### 3.2 Operator Decision Register (Explicit Consent Required — Never Inferred)

| Decision ID | Linked IDs | Trigger / PC Task | Decision Required From Operator | Default If Unanswered |
|---|---|---|---|---|
| **DEC-01** | `V4-02.15`, `V4-13.05` | `PC-07.01` | Authorize offline download/licensing of a 2nd local voice (e.g., 2nd Piper PT-BR ONNX or verified Kokoro binary weights) OR accept `BLOCKED/DEFERRED` with single bundled Piper voice + assisted audio import. | Stay `BLOCKED/DEFERRED` (`$0.00`, zero downloads) |
| **DEC-02** | `V4-13.03` | `PC-08.02` | If `balanced_local` cannot produce a genuinely distinct higher-tier local profile without paid API/weights, accept `BLOCKED/DEFERRED` (do NOT relabel `economic_local`). | Stay `BLOCKED/DEFERRED` |
| **DEC-03** | `V4-08.11` | `PC-07.02` | Decide whether to authorize native macOS VideoToolbox execution outside Docker in a future slice (vs keeping Linux Docker CPU `libx264` canonical). | Stay `DEFERRED` (diagnostic only) |
| **DEC-04** | `V4-03.05`, `05.02`, `05.23`, `05.24`, `07.03`, `08.12`, `08.13`, `12.14` | `PC-07.02` | Explicitly accept deferral of optional external engines (Freesound, ComfyUI, Remotion, Blender, WhisperX, 2nd renderer) & CI/CD for V4 release, OR authorize a future scoped campaign. | Stay `DEFERRED` (no install, no CI/CD) |
| **DEC-05** | `GAI-03`..`GAI-08`, `V4-05.15`, `09.10–11`, `11.14`, `13.04` | `PC-07.03`, `PC-09.02` | Explicitly accept deferral of paid BYOK cloud APIs, Google Drive OAuth, and premium 15–20min pilot under `$0.00` ceiling, OR authorize BYOK credentials + budget cap separately. | Stay `DEFERRED` (`$0.00`, fail-closed) |
| **DEC-06** | `V4-00.06`, `V4-13.11` | `PC-08.03`, `PC-09.02` | Watch baseline MP4 + both new `PC-08` Studio pilot MP4s (60–90s & 5–8min) and record real human scores `>= 9.0/10` across all 6 dimensions with timestamped findings. | `AWAITING_HUMAN_REVIEW` (never simulated) |
| **DEC-07** | Release / Merge / Publish | `PC-09.02` | Separate explicit authorization to merge `develop` → `main` (`42700cb`) and (separately) whether to ever enable publication (`STUDIO_PUBLICATION_ENABLED`). | `NO-GO` for merge; `BLOCKED` for publication |

---

## 4. Detailed Test-First Execution Plan (`PC-00.02`: `PC-01.01`..`PC-09.02`)

### 4.1 Campaign Dependency DAG & Planned Additive Migrations
- **Blocking Gate:** `PC-00` (`Carbon High` review `>= 9.0`) → `PC-01.01` → `PC-01.02` (blocks all functional waves).
- **Parallelizable Post-PC-01 Tracks** (non-overlapping files):
  - Track A (Audio): `PC-02.01` → `PC-02.02` → `PC-02.03`
  - Track B (Voice & Direction): `PC-03.01` → (`PC-03.02` [→ `PC-07.01` offline diag] & `PC-03.03`)
  - Track C (Visual, needs `01.02` + `03.03`): `PC-04.01` → `PC-04.02` → `PC-04.03` → `PC-04.04`
  - Track D (Acervo, needs `01.02`): `PC-05.02`
- **Convergence:** (`02.03` + `04.04`) → `PC-05.01` → (`PC-05.03` [with `05.02`] & `PC-07.02` offline diag) → `PC-06.01` [→ `PC-07.03` offline plan] → `PC-06.02` → `PC-08.01` → `PC-08.02` → `PC-08.03` → `PC-09.01` → `PC-09.02`.

**Planned Additive PostgreSQL Migrations (All Reversible Without Data Loss, Preserving 49 Existing Migrations `0001`..`0054`):**
| Migration # | Owner Task | Additive Schema Change | Non-Destructive Rollback |
|---|---|---|---|
| `0055_scene_edit_revision.sql` | `PC-01.01` | `ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS edit_revision BIGINT NOT NULL DEFAULT 1;` + optional `studio.scene_assets` partial/supporting index | `ALTER TABLE studio.scenes DROP COLUMN IF EXISTS edit_revision;` + delete `schema_migrations` row |
| `0056_video_audio_tracks.sql` | `PC-02.02` | `CREATE TABLE IF NOT EXISTS studio.video_audio_tracks (...)` (track role `music`/`ambience`/`sfx`, `asset_id`, `start_s`, `end_s`, `trim_*`, `gain_db`, `fade_in_s`, `fade_out_s`, `loop`, `ducking_db`, `eq_preset`, `comp_preset`, `muted`, `solo`, `edit_revision`) | `DROP TABLE IF EXISTS studio.video_audio_tracks;` + delete `schema_migrations` row |
| `0057_voice_identity_and_pronunciation.sql` | `PC-03.01`–`03.02` | `CREATE TABLE IF NOT EXISTS studio.pronunciation_rules (...)` (scoped by `project_id`, term, replacement, active) + additive `voice_settings JSONB NOT NULL DEFAULT '{}'::jsonb` on `studio.channel_profiles` / `studio.videos` / `studio.scenes` | `DROP TABLE ...; ALTER TABLE ... DROP COLUMN IF EXISTS voice_settings;` |
| `0058_scene_creative_direction.sql` | `PC-03.03` | `ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS direction_json JSONB NOT NULL DEFAULT '{}'::jsonb;` + mirror column on `studio.scene_revisions` | `ALTER TABLE studio.scenes/scene_revisions DROP COLUMN IF EXISTS direction_json;` |
| `0059_scene_asset_layers_and_effects.sql` | `PC-04.01`–`04.04` | Additive columns on `studio.scene_assets`: `z_index INT NOT NULL DEFAULT 0`, `pos_x REAL NOT NULL DEFAULT 0.5`, `pos_y REAL NOT NULL DEFAULT 0.5`, `scale REAL NOT NULL DEFAULT 1.0`, `opacity REAL NOT NULL DEFAULT 1.0`, `layer_kind VARCHAR(24) NOT NULL DEFAULT 'media'`, `layer_spec JSONB NOT NULL DEFAULT '{}'::jsonb`; plus `post_processing JSONB NOT NULL DEFAULT '{}'::jsonb` on `studio.scenes` | `ALTER TABLE ... DROP COLUMN IF EXISTS ...;` (existing rows untouched) |
| `0060_asset_tags.sql` | `PC-05.02` | `CREATE TABLE IF NOT EXISTS studio.asset_tags (asset_id VARCHAR(64) REFERENCES studio.assets(id) ON DELETE CASCADE, project_id TEXT NOT NULL, tag VARCHAR(64) NOT NULL, created_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (project_id, asset_id, tag));` + `(project_id, tag)` index | `DROP TABLE IF EXISTS studio.asset_tags;` |

---

### 4.2 Per-Task Test-First Specifications (`PC-01.01`..`PC-09.02`)

#### `PC-01.01` — Single-Transaction Base Replace, Overlay Preservation & Unified Scene CAS (`P0`)
- **Objective:** Eliminate the P1 overlay-wipe and split-transaction defect proven in [evidence/pc00/pc01-bug-repro.log](evidence/pc00/pc01-bug-repro.log); introduce a dedicated repository operation that updates ONLY the base media/trim row in a single PostgreSQL transaction with monotonic `edit_revision` CAS, leaving all overlays, z-order, roles, motion, transitions, SFX, narration, and captions intact.
- **Target Files & Call Graph:** `migrations/0055_scene_edit_revision.sql` → `domain/contracts.py` (`Scene.edit_revision`, `SceneAsset`) → `adapters/postgres/media_repo.py` (`add_and_replace_scene_base_media` single tx with `SELECT ... FROM studio.scenes WHERE id=%s AND video_id=%s FOR UPDATE`, CAS on `expected_edit_revision` & `expected_asset_id`, upsert/delete ONLY `role='base'` row while shifting/avoiding `uq_scene_asset_pos` collisions) → `application/media.py` (`ImportExternalMedia`, `SwapSceneMedia`, base trim validation against `ProbedMedia.duration_s` and finite bounds) → `application/render.py` (`StartRender` `input_hash` includes base trim) → `api/routes.py` (application use cases for `GET/POST/DELETE /scenes/{sid}/assets` enforcing ownership + `edit_revision` bump; return `edit_revision` in `SceneMediaOut`).
- **Contract & Rollback:** Additive `edit_revision` (default `1`; backward-compatible if client omits `expected_edit_revision` during transition, strict `409` when supplied or when `expected_asset_id` mismatches); `save_scene_assets` preserved untouched for callers that intentionally replace all rows. Rollback: `git revert` + `DROP COLUMN edit_revision`.
- **Test-First Matrix:**
  - *Positive:* Replace base WITHOUT trim preserves 2 overlays (PNG + MP4 PiP) + IDs/order/motion/transitions; replace base WITH trim preserves both overlays & updates only `role='base'` row; replace SAME asset with new trim increments `edit_revision` & changes `StartRender` `input_hash`.
  - *Negative:* `trim_end_s > probed.duration_s` → `422` before commit; `NaN`/`inf`/negative trim → `422`; stale `expected_edit_revision` or ABA race → `409` without mutating DB or leaking orphan file; cross-video/project `POST/DELETE /scenes/{sid}/assets` → `403`/`404`.
  - *Concurrency/Restart:* Fault injection during `scene_assets` update inside the unified tx rolls back BOTH `studio.scenes.asset_id`, `edit_revision`, and newly inserted `studio.assets` row + cleans up unreferenced disk file cleanly (zero orphan leakage, never deletes referenced file); 2-connection `Barrier(2)` race produces exactly 1 winner and 1 `StateConflict` (`409`).
- **Deps:** `PC-00.02` | **Complexity:** `L` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Neon High`.
- **Risks & Mitigations:** Lock ordering deadlock between `pg_advisory_xact_lock(cache_key)` and `SELECT ... FOR UPDATE` on `studio.scenes` → always acquire `studio.scenes FOR UPDATE` first, or acquire advisory lock in deterministic order; test under 2-connection concurrent imports of swapped keys.
- **Gates:** `G1`, `G2`, `G4` (`>= 9.0` all dimensions, `0` P0/P1).

#### `PC-01.02` — Undo/Redo with Scene Revision, Selective Cache & Real Browser Integrity (`P0`)
- **Objective:** Close end-to-end edit integrity across reload, undo/redo, concurrent writers, selective render-cache invalidation, and real Chromium desktop/mobile UI.
- **Target Files & Call Graph:** `api/panel_video_workspace.py` (serialize `edit_revision` + `scene_assets` summary into workspace state) → `api/panel_video_storyboard_js.py` (`doImportMedia`, `reconcile`, undo/redo stack tracking `edit_revision` + `trim_start_s`/`trim_end_s` + `asset_id`; clear trim cleanly when re-importing without trim; handle `409` cleanly with reload prompt) → `application/media.py` (`SwapSceneMedia` supports optional trim restore + `expected_edit_revision`) → `domain/render_cache.py` / `adapters/render_plan_ffmpeg.py` (prove changing Scene 1 base/trim invalidates ONLY Scene 1 visual node + concat/final, reusing Scene 2 narration & visual).
- **Contract & Rollback:** Backward-compatible optional `edit_revision`/`trim_*` fields on `SceneMediaChoiceIn` & `SceneMediaOut`; zero DB schema change beyond `0055`.
- **Test-First Matrix:**
  - *Positive:* Browser Desktop (`1280x800`) + Mobile (`390x844`): create/load scene with 2 overlays → replace base (no trim, then with trim) → reload → overlays & trim intact → undo → redo → reload → real FFmpeg render proves both overlays & replaced base appear in final MP4.
  - *Negative:* Concurrent edit from tab B while tab A imports/undoes → `409`, no silent overwrite; reimport same content with different license (`CC0-1.0` vs `CC-BY-4.0`) creates distinct scoped dedup record; cross-project isolation verified.
  - *Concurrency/Restart:* Restart Studio/FastAPI process against same Postgres DB → reload preserves exact `edit_revision`, base asset, trim, overlays, and selective cache reuse (`0` re-render of untouched scene).
- **Deps:** `PC-01.01` | **Complexity:** `L` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Neon High`.
- **Risks & Mitigations:** Client undo of a media replace after overlay edit must not wipe newer overlays → undo sends base-only swap with `expected_edit_revision`, surfacing `409` if overlays changed underneath.
- **Gates:** `G2`, `G3`, `G4`, `G5` (Node VM + isolated Playwright `8100`).

#### `PC-02.01` — Authorized Audio Import, Isolated Probe, License & Preview (`P1`)
- **Objective:** Allow uploading/importing authorized local audio files (WAV/MP3/AAC-M4A/OGG/FLAC) into `studio.assets` (`AssetKind.audio`) with real `ffprobe` + decode verification, size/duration caps, license/provenance enforcement, content+scope dedup, and authenticated audio preview streaming.
- **Target Files & Call Graph:** `domain/contracts.py` (`AssetKind.audio` if missing, check existing enum) → `adapters/media_probe.py` (`FfmpegMediaProbe.probe_audio`: `-protocol_whitelist file`, codec allowlist, real full/bounded decode check, duration/sample-rate/channels bounds) → `adapters/storage.py` (`put_audio` with safe ext `.wav`/`.mp3`/`.m4a`/`.ogg`/`.flac`) → `application/media.py` (`ImportExternalAudio` reusing `verify_license_provenance`, `requires_attribution`, content SHA-256 + `(project_id, 'audio', hash, license)` dedup, `AssetFile` MIME map extended for audio) → `api/routes.py` (`POST /videos/{vid}/audio/import`, `GET /assets/{id}/file` audio MIME + `Accept-Ranges: bytes`).
- **Contract & Rollback:** Additive route + `AssetKind` check; existing image/video import routes untouched.
- **Test-First Matrix:**
  - *Positive:* Import local original WAV & MP3/M4A with `OWN_ORIGINAL` / `CC-BY-4.0` (with attribution) → persisted in PG → `GET /assets/{id}/file` returns `200`/`206` with `audio/*` MIME & valid audio bytes.
  - *Negative:* Unknown/NC/ND license → `422`; fake MIME (PNG renamed `.mp3` or corrupt bytes) → `422`; path traversal filename → `422`; oversized (>100MB or >duration limit) → `413`/`422`; cross-project access → `403`.
  - *Concurrency/Restart:* Concurrent identical audio upload deduplicates cleanly; restart preserves asset & streamability.
- **Deps:** `PC-01.02` | **Complexity:** `M` | **Routing:** Executor `Hydrogen Medium` / `Flash` UI, Reviewer `Neon High` (contracts/licenses) & `Carbon High` (UI).
- **Risks & Mitigations:** FFmpeg audio container exploits → strictly `-protocol_whitelist file`, disable network/playlists, timeout cap, decode verification.
- **Gates:** `G1`, `G2`, `G4`.

#### `PC-02.02` — Multitrack Audio CRUD (Voice/Music/Ambience/SFX), Fades, Ducking & Mix-Only Preview (`P1`)
- **Objective:** Expose full 3+ track Audio Studio CRUD (`music`, `ambience`, `sfx` alongside narration voice) in the existing Studio workspace, persisted in PostgreSQL, wired into `RenderSpec.multitrack` → `PlanFfmpegRenderer`, and providing real mix-only WAV/AAC preview using the exact same compiled FFmpeg audio graph.
- **Target Files & Call Graph:** `migrations/0056_video_audio_tracks.sql` → `adapters/postgres/audio_repo.py` (`PostgresAudioTrackRepository` with `edit_revision` CAS) → `application/audio_studio.py` (`ManageAudioTracks`, `PreviewAudioMix` invoking `compile_multitrack_audio_args` + FFmpeg to produce mix-only WAV/AAC) → `application/render.py` (`RunRender._render` builds `MultitrackAudioPlan` + `AudioCatalog` from persisted tracks, preserving legacy default voice+music when empty; `StartRender` `input_hash` includes audio track signature; `render_cache.py` invalidates only audio/final nodes) → `api/routes.py` (`GET/POST/PATCH/DELETE /videos/{vid}/audio-tracks`, `POST/GET /videos/{vid}/audio/preview`) → `api/panel_video_workspace.py` (`_area_narracao` / Audio Studio panel: add/remove/edit tracks, start/end/trim, gain dB, mute/solo, fade-in/out, loop, ducking, play/stop mix preview).
- **Contract & Rollback:** Additive table `0056`; videos with 0 rows in `video_audio_tracks` retain 100% identical legacy voice+generated-music behavior and golden hashes.
- **Test-First Matrix:**
  - *Positive:* Add voice + music + ambience + timed SFX (pulse/tone fixture) via UI/HTTP → generate mix-only preview WAV → export final MP4 → decode PCM from BOTH preview & MP4 proving exact SFX timing alignment, fade ramp, and measurable ducking attenuation during speech (`0` clipping).
  - *Negative:* Track with unverified license → fail closed before FFmpeg; `NaN`/`inf`/out-of-range gain or fades or negative/out-of-timeline bounds → `422`; stale `edit_revision` → `409`; missing audio asset file → explicit error, never silent success.
  - *Concurrency/Restart & Browser:* 2-writer track update CAS `409`; restart preserves tracks; isolated Playwright test adds 3+ tracks, previews mix, renders MP4, reloads, undoes.
- **Deps:** `PC-02.01` | **Complexity:** `XL` | **Routing:** Executor `Hydrogen Medium` / `Flash` UI, Reviewer `Neon High` (contracts) & `Carbon High` (UI).
- **Risks & Mitigations:** Cache invalidation drift → include canonical multitrack digest in `music_fingerprint` & `StartRender.input_hash`, while keeping visual segment nodes untouched (`0` visual re-renders when only audio changes!).
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-02.03` — Parameterized EQ / Compression, Real dBTP & Audio Regression (`P1`)
- **Objective:** Add safe, bounded, allowlisted FFmpeg EQ (`highpass`/`equalizer`/`lowpass` presets: `off`, `voice_clarity`, `warm_documentary`, `broadcast`) and voice compression (`acompressor` presets/ranges) to `AudioMix`/`MultitrackAudioPlan` → `compile_multitrack_audio_args`, verified via real `ebur128=peak=true` (LUFS & dBTP) and spectral/RMS PCM delta on both mix preview and final MP4.
- **Target Files & Call Graph:** `domain/audio_multitrack.py` (`AudioDspPreset` / bounded EQ & compressor dataclass, default `off`) → `adapters/render_plan_compiler.py` (`compile_multitrack_audio_args` & `_mix_filter` building allowlisted filter chain — zero raw user FFmpeg strings) → `application/audio_studio.py` + `api/routes.py` + `api/panel_video_workspace.py` (preset selector & bounded sliders) → `adapters/qa_ffmpeg.py` (`FfmpegQa` `ebur128=peak=true`).
- **Contract & Rollback:** Default `off` preserves all legacy audio golden hashes; rollback reverts commit with zero DB data loss (`eq_preset`/`comp_preset` default `'off'`).
- **Test-First Matrix:**
  - *Positive:* Render tone/speech fixture with `off` vs `voice_clarity` EQ + compression → measure real `ebur128` LUFS (`-16 ± 1.5`), true peak (`<= -1.0 dBTP`), and observable spectral/dynamic-range difference in decoded PCM on both preview WAV and final MP4.
  - *Negative:* Arbitrary FFmpeg filter injection (`;exec`, invalid preset, `NaN`, out-of-range gain/ratio) → `422` rejected at domain validation before FFmpeg.
  - *Regression:* Legacy `test_render_golden.py` (`8/8`) and `test_rec_02_av_composition.py` remain `100%` green.
- **Deps:** `PC-02.02` | **Complexity:** `M` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Neon High`.
- **Risks & Mitigations:** Over-boosting EQ causing true-peak clipping → enforce `loudnorm`/`alimiter` ceiling stage after EQ/compression and assert `true_peak_dbtp <= -1.0` via `ebur128=peak=true`.
- **Gates:** `G2`, `G3`, `G4`.

#### `PC-03.01` — Canonical Voice Catalog & Channel Vocal Identity (`P1`)
- **Objective:** Unify voice discovery into canonical `ProviderCatalog` (no parallel in-memory catalog), exposing real language/voice/capability/availability metadata (`is_demo`, `supports_emotion`, `supports_pacing`, `supports_pronunciation`), channel-level vocal identity, video/scene overrides, preview WAV endpoint, and frozen selection in `ProductionRunConfig`.
- **Target Files & Call Graph:** `migrations/0057_voice_identity_and_pronunciation.sql` → `domain/voice_catalog.py` (capability flags on `VoiceProfile`) → `composition/providers.py` (`ProviderCatalog` enriched with canonical local/configured voices + real readiness probes; `demo` clearly labeled; Kokoro/ElevenLabs fail-closed) → `domain/effective_config.py` (resolve `channel → video → scene` voice identity + freeze in `production_run_config`) → `api/routes.py` (`GET /studio/voices`, `POST /studio/voices/preview`, channel/video voice settings) → `api/panel_channels.py` / `api/panel_styles.py` / `api/panel_video_workspace.py` (select validated voice, play preview WAV, display capability badges honestly).
- **Contract & Rollback:** Additive `voice_settings` JSONB default `'{}'`; existing `params.voice.model` resolution continues working seamlessly.
- **Test-First Matrix:**
  - *Positive:* `GET /studio/voices` returns `piper:pt_BR-faber-medium` (`available=True`, `supports_emotion=False`), `kokoro` (`available=False`, fail-closed), `elevenlabs` (`available=False`, `$0.00`); set channel vocal identity → start run → verify `production_run_config` freezes exact voice → change channel voice mid-run → run uses frozen voice; preview WAV playable & valid PCM.
  - *Negative:* Selecting unavailable voice (`kokoro` without weights, `elevenlabs`, unknown ID) → `422` fail-closed (or explicit authorized fallback only when configured); zero downloads/network calls.
  - *Concurrency/Restart & Browser:* Restart preserves channel/video voice identity; browser selects voice & plays preview WAV.
- **Deps:** `PC-01.02` | **Complexity:** `M` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High`.
- **Risks & Mitigations:** Two divergent voice registries → single source of truth in `ProviderCatalog`; `composition/voice_catalog.py` delegates or retires in `PC-05.03`.
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-03.02` — Deterministic PT-BR Pronunciation Dictionary, Pacing/Pauses & Honest Capability Reporting (`P1`)
- **Objective:** Wire deterministic PT-BR pronunciation dictionary and pause/pacing preprocessing before `PiperVoice` synthesis, storing both original editorial text (for captions/script) and effective spoken text (for TTS & `narration_fingerprint`), invalidating only dependent scene narration/audio/final nodes, while explicitly flagging unsupported neural emotion (`supports_emotion=False`).
- **Target Files & Call Graph:** `domain/voice_preprocessing.py` (`PronunciationDictionary` with Unicode/number/boundary-safe deterministic substitution, `apply_pacing_and_pauses` mapped strictly to supported Piper punctuation/pause/length-scale parameters — NEVER labeling speed changes as neural emotion) → `adapters/postgres/voice_repo.py` (`pronunciation_rules` CRUD scoped by `project_id`) → `application/render.py` (`RunRender._synthesize_scene`) & `application/scene_narration.py` (`RegenerateSceneNarration`) → `domain/render_cache.py` (`narration_fingerprint` includes effective spoken text + pacing params + voice identity) → `api/routes.py` & `api/panel_video_workspace.py` (dictionary CRUD + scene pacing controls + explicit *"Emoção neural indisponível no Piper local"* badge).
- **Contract & Rollback:** Empty dictionary & default pacing produce identical `narration_fingerprint` and zero regression on existing videos.
- **Test-First Matrix:**
  - *Positive:* Real `PiperVoice` synthesizes PT-BR phrases with technical terms/acronyms (e.g., `"FFmpeg"`, `"API"`, `"1945"`) & pauses → verify original caption text is unchanged, effective TTS text reflects rules, WAV duration/pauses change measurably, audio-caption sync remains `<= 500ms`, and editing 1 rule invalidates ONLY scenes containing that term.
  - *Negative:* Invalid regex/control chars/empty term → `422`; requesting neural emotion on Piper → explicit capability warning/rejection (never silently faked); cross-project dictionary isolation.
  - *Restart:* Rules persist across restart; cached narration reuses WAV when text+rules unchanged.
- **Deps:** `PC-03.01` | **Complexity:** `M` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High`.
- **Risks & Mitigations:** Pronunciation substitutions corrupting visible captions → strictly separate `scene.narration` (displayed in subtitles/script) from `spoken_text` (passed to TTS & cached in `narration_fingerprint`).
- **Gates:** `G1`, `G2`, `G3`, `G4`.

#### `PC-03.03` — Per-Scene Creative Direction, Intensity, Editorial Goal & Editable Shot Plan (`P1`)
- **Objective:** Wire per-scene `SceneCreativeDirection` (editorial goal, emotional tone/intensity metadata — clearly labeled editorial, NOT TTS emotion — pacing, target duration, visual relevance notes) and editable `ShotIntent` list into PostgreSQL, HTTP routes, Storyboard UI, and `PlanFfmpegRenderer` (`RenderPlan` shot rhythm/motion/duration).
- **Target Files & Call Graph:** `migrations/0058_scene_creative_direction.sql` → `domain/creative_director.py` (`SceneCreativeDirection`, `ShotIntent`, `FORBIDDEN_COMMAND_PATTERNS` validation on all scene prose) → `adapters/postgres/editorial_repo.py` (persist `direction_json` on `scenes` & `scene_revisions` with `edit_revision` CAS) → `application/creative_director.py` (`UpdateSceneDirection`, deterministic local rule-based planner when LLM unavailable — zero fake AI claims) → `adapters/render_plan_ffmpeg.py` (`_build_plan` applies per-scene `ShotIntent` motion/framing/pacing hints to that scene's shots ONLY) → `api/routes.py` (`GET/PATCH /videos/{vid}/scenes/{sid}/direction`) → `api/panel_video_workspace.py` / `panel_video_storyboard_js.py` (collapsible scene direction & shot editor in storyboard).
- **Contract & Rollback:** Additive `direction_json` default `'{}'`; empty `{}` preserves existing video-level `CreativeBrief` behavior 100%.
- **Test-First Matrix:**
  - *Positive:* Edit Scene 1 goal/intensity/`ShotIntent` (`zoom_in` vs `pan_right`, shot framing) via UI/HTTP → persist & reload → render MP4 → prove Scene 1 `RenderPlan` & visual pixels reflect new shot intent while Scene 2 visual cache node is `100%` reused.
  - *Negative:* Shell/FFmpeg injection in scene goal or shot description → `422` (`CreativeSecurityViolation`); invalid intensity/motion/duration → `422`; stale `edit_revision` → `409`; cross-video scene ID → `404`.
  - *Browser/Undo:* Desktop browser edits direction, reloads, undoes/redoes cleanly.
- **Deps:** `PC-03.01` | **Complexity:** `L` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Neon High`.
- **Risks & Mitigations:** Per-scene overrides mutating unrelated scenes → scope `direction_json` strictly to `scene_id` and bind into `visual_fingerprint` of that scene's shots only.
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-04.01` — Storyboard Layer Editor UI & Persisted Layer Geometry/Alpha/Z-Index/Trim (`P1`)
- **Objective:** Upgrade `studio.scene_assets` and the existing Studio storyboard panel (no new SPA) into a real layer editor supporting base/overlay/PiP/text/graphic layers with persisted `z_index`, `pos_x`, `pos_y`, `scale`, `opacity`, `start_s`/`end_s` trim, safe-area hints (`16:9` & `9:16`), server-side validation, `edit_revision` CAS, and exact parity between preview and FFmpeg render.
- **Target Files & Call Graph:** `migrations/0059_scene_asset_layers_and_effects.sql` → `domain/contracts.py` (`SceneAsset` additive geometry/z-index/opacity/kind/spec fields, finite bounds) → `application/layers.py` (`ManageSceneLayers`: add/update/reorder/delete layer in single tx with `edit_revision` CAS, enforce `<= MAX_OVERLAYS_PER_SCENE = 8`, safe-area warnings, project-scoped asset ownership) → `application/render.py` (`RunRender._overlay_layers` consumes persisted `pos_x/pos_y/scale/opacity/z_index` instead of hardcoded `_overlay_placement`; `StartRender.input_hash` includes full layer sig) → `adapters/render_plan_compiler.py` (`_overlay_filter` applies z-order, scale, alpha, position, trim) → `api/routes.py` (`GET/POST/PATCH/DELETE /videos/{vid}/scenes/{sid}/layers` + backward-compatible `/assets` delegating to `ManageSceneLayers`) → `api/panel_video_workspace.py` & `panel_video_storyboard_js.py` (compact layer list + controls + 16:9/9:16 preview box).
- **Contract & Rollback:** Additive columns with safe defaults matching existing behavior; `/scenes/{sid}/assets` remains backward-compatible.
- **Test-First Matrix:**
  - *Positive:* Browser adds PNG overlay (`z=1`, `x=0.85, y=0.25, opacity=0.7`) + animated MP4 PiP (`z=2`, `x=0.15, y=0.55, scale=0.35`) → reorder z-index → reload → render real MP4 → pixel-probe frames proving BOTH simultaneous layers, alpha blending, z-order occlusion, and temporal window (`start_s`/`end_s`).
  - *Negative:* `> 8` overlays → `422`; `NaN`/`inf`/opacity `> 1.0` or `< 0`/scale `<= 0` → `422`; stale `edit_revision` → `409`; cross-project `asset_id` → `403`.
  - *Concurrency/Restart/Undo:* Undo/redo & reload preserve layers; replacing base asset (`PC-01`) preserves all configured layers and their geometry!
- **Deps:** `PC-01.02`, `PC-03.03` | **Complexity:** `XL` | **Routing:** Executor `Hydrogen Medium` / `Flash` UI, Reviewer `Neon High`.
- **Risks & Mitigations:** Overlay colliding with HUD/captions → expose explicit safe-area presets and bounds validation in both server and UI; verify via `FfmpegOverlayVerifier`.
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-04.02` — Configurable Real Transitions (`crossfade`/`slide`/`wipe`/`fade`/`cut`) UI → FFmpeg (`P1`)
- **Objective:** Expose the compiler's real inter-shot `xfade` transitions (`none`/`cut`, `fade`, `crossfade`, `slide_left`, `slide_right`, `wipe_left`, `wipe_right`) through `visual_style`, scene/shot HTTP endpoints, and Storyboard UI with strict pair-duration validation, exact timeline/narration/caption sync preservation, and selective adjacent-segment cache invalidation.
- **Target Files & Call Graph:** `domain/visual_style.py:67` (`TRANSITION_KINDS` expanded to match `application/render_compiler.py:48` `SUPPORTED_TRANSITIONS`) → `application/render_compiler.py` (`_validate_transitions`: fail closed if `duration >= min(shot_a, shot_b)` or unsupported kind) → `adapters/render_plan_compiler.py` (`_compile_concat` real `tpad`+`xfade`, zero fade-to-black alias for `crossfade`) → `domain/render_cache.py` (invalidate only adjacent segments + concat/final when a boundary transition changes) → `api/routes.py` & `api/panel_video_workspace.py` / `panel_styles.py` (transition kind + bounded duration picker).
- **Contract & Rollback:** Default remains `none`/`fade` on existing styles/videos (preserving all golden hashes).
- **Test-First Matrix:**
  - *Positive:* Configure `crossfade`, `slide_left`, and `wipe_left` (`0.5s`) via Studio UI/HTTP on solid-color/distinct scenes → render MP4 → verify midpoint RGB pixel blend (red+blue→purple for `crossfade`, spatial split for `slide_left`/`wipe_left`), exact total duration preserved (`0` drift vs narration/captions), and `0%` black frames.
  - *Negative:* Transition duration `>=` shot duration → `422`/`CompileError` before FFmpeg; unknown transition kind → `422`.
  - *Cache:* Changing transition between Scene 2 and Scene 3 reuses Scene 1 visual segment cleanly.
- **Deps:** `PC-04.01` | **Complexity:** `M` | **Routing:** Executor `Hydrogen Medium` / `Flash` UI, Reviewer `Neon High`.
- **Risks & Mitigations:** Cumulative `xfade` duration shortening causing subtitle desync → verify `tpad` compensation preserves exact timeline ticks and run `check_audio_caption_sync` (`<= 500ms`).
- **Gates:** `G1`, `G2`, `G3`, `G5`.

#### `PC-04.03` — Declarative Animated Templates: Lower Thirds, Timelines, Maps & Icons/Infographics (`P1`)
- **Objective:** Wire versioned declarative templates (`LowerThirdGraphic`, `InfographicOverlay` for timelines, data-backed simple maps without invented geography, and icon/KPI cards) from Studio UI/API → `RenderPlan` → Pillow/FFmpeg animated overlay compilation (slide/fade-in/out keyframes) using local licensed assets/DejaVu fonts, strict text escaping, safe-area constraints, and resource caps.
- **Target Files & Call Graph:** `domain/motion_effects.py` (versioned declarative `LowerThirdGraphic`, `InfographicOverlay`, `TemplateAnimationPreset` with strict length/count/bounds validation) → `application/layers.py` (`layer_kind="template"`, `layer_spec` validated against versioned schema) → `adapters/template_renderer.py` (deterministic Pillow RGBA graphic frame/card generator with local DejaVu fonts + safe-area clamping + text escaping) → `adapters/render_plan_compiler.py` (`_overlay_filter` applies animated entrance/exit expression `x`/`y`/`alpha` per declarative preset) → `api/routes.py` & `api/panel_video_workspace.py` (add/edit lower third, timeline, map, or infographic layer in panel).
- **Contract & Rollback:** Stored in `scene_assets.layer_kind` / `layer_spec` (`0059`); zero impact when no template layer is added.
- **Test-First Matrix:**
  - *Positive:* Create lower third, 3-point timeline, data-backed simple map/callout, and KPI icon card via Studio UI/HTTP → render real 1080p MP4 (both `16:9` and `9:16`) → extract frames at entry/mid/exit proving visible motion, legibility/contrast, safe-area compliance (no HUD/subtitle collision), and exact temporal removal.
  - *Negative:* FFmpeg filter-injection chars (`:`, `'`, `;`, `%`) in title/subtitle safely escaped (never executed); oversized text/item counts → `422`; unknown template type/version → `422`; zero external network fetches.
- **Deps:** `PC-04.02` | **Complexity:** `L` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Carbon High`.
- **Risks & Mitigations:** FFmpeg `drawtext` escaping bugs or font mismatches → render text/graphics deterministically with Pillow RGBA PNGs (like `static_overlay`) and animate via bounded FFmpeg `overlay` position/alpha expressions — immune to `drawtext` injection and 100% consistent with DejaVu fonts!
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-04.04` — Controlled Post-Processing: Blur, Local Licensed LUT, Vignette & Film Grain (`P1`)
- **Objective:** Wire `PostProcessingEffects` (`blur_background`, local licensed `.cube` LUT / `ColorGrading` presets, `vignette_strength`, `grain_strength` with deterministic seed) with defaults=`off`, strict finite parameter bounds, allowlisted FFmpeg filters only, zero impact on audio stream, and verified pixel deltas in real MP4s.
- **Target Files & Call Graph:** `domain/motion_effects.py` (`ColorGrading`, `PostProcessingEffects` with finite ranges & deterministic `grain_seed`, defaults all `0`/off) → `domain/render_plan.py` (additive optional `Effects.post_processing = None`) → `domain/render_cache.py` (`visual_fingerprint` includes `post_processing` ONLY when active, preserving legacy hashes when `None`/off!) → `adapters/render_plan_compiler.py` (allowlisted `boxblur`/`gblur`, bundled licensed `.cube` LUT via `lut3d` or deterministic `eq`/`colorbalance` preset, `vignette`, `noise=alls=...:allf=t` seeded) → `api/routes.py` & `api/panel_video_workspace.py` (post-processing preset/slider controls).
- **Contract & Rollback:** Defaults all `off`/`None` → `test_render_golden.py` (`8/8`) byte-identical; additive JSONB column `scenes.post_processing` (`0059`).
- **Test-First Matrix:**
  - *Positive:* Render identical scene with `off` vs each effect enabled (`blur_background`, `ColorGrading.WARM`/`NOIR`, `vignette=0.6`, `grain=0.25`) → measure pixel-level RGB/variance/edge-corner-luminance diffs proving real FFmpeg execution, verify audio stream SHA/LUFS unchanged, and verify cache miss on changed effect + hit on repeat.
  - *Negative:* Arbitrary LUT file path (`../../etc/passwd`) or raw filter string → `422` rejected; `NaN`/`inf`/strength `< 0` or `> 1` → `422`.
- **Deps:** `PC-04.03` | **Complexity:** `M` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Carbon High`.
- **Risks & Mitigations:** Grain non-determinism breaking render cache or visual tests → use deterministic FFmpeg `noise` seed and include `post_processing` params in `visual_fingerprint`.
- **Gates:** `G1`, `G2`, `G3`, `G4`.

#### `PC-05.01` — Real Renderer Capabilities & Preview (`540p`/`480p`) vs Production (`1080p`) Presets (`P1`)
- **Objective:** Wire real `RendererCapabilities` preflight validation (`V4-08.01`) and low-resolution preview preset (`540p` proportional: `960x540` for `16:9` long, `540x960` for `9:16` short, `ultrafast`/`crf 28`) vs `1080p` production preset (`V4-04.19`, `V4-08.10`) through the SAME `RenderPlan` and `PlanFfmpegRenderer`, with strict cache separation by `(preset, width, height)` and strict guard preventing preview MP4s from being approved/exported as final production output.
- **Target Files & Call Graph:** `domain/render_engine.py` (`RendererCapabilities`, `QualityPresetKind`, `RenderQualityPreset` proportional for `16:9` & `9:16`) → `adapters/render_plan_ffmpeg.py` (`PlanFfmpegRenderer.capabilities()`, preset-aware `_build_plan`/`_compile`/FFmpeg encoding args) → `domain/render_cache.py` (`visual_fingerprint` & `concat`/`final` cache keys include `preset_kind` when `!= "production"`, preserving `100%` of legacy 1080p hashes!) → `application/render.py` (`StartRender`/`RunRender` accept `preset: QualityPresetKind = PRODUCTION`; preview output stored separately as `preview.mp4` and NEVER transitions video to publishable/final state) → `api/routes.py` (`GET /studio/renderer/capabilities`, `POST /videos/{id}/render?preset=preview|production`, `GET /videos/{id}/preview.mp4`) → `api/panel_video_workspace.py` (UI button *"Gerar prévia rápida (540p)"* vs *"Renderizar final (1080p)"* + capability badge).
- **Contract & Rollback:** Default `preset="production"` preserves all existing callers, cache hashes, and golden fixtures.
- **Test-First Matrix:**
  - *Positive:* Render same video in `preview` (`960x540` / `540x960`) and `production` (`1920x1080` / `1080x1920`) → `ffprobe` verifies exact aspect/resolution/duration/audio/caption parity, observed wall time & file size recorded honestly, cache dirs/digests strictly isolated (preview never served as final), and switching preset works cleanly.
  - *Negative:* Requesting unsupported capability or invalid preset → fail-closed `422`; attempting `POST /approve` or final export with only a preview render → `409` rejected; cooperative cancellation mid-preview leaves clean state.
- **Deps:** `PC-02.03`, `PC-04.04` | **Complexity:** `L` | **Routing:** Executor `Hydrogen Medium`, Reviewer `Neon High`.
- **Risks & Mitigations:** Preview render overwriting `videos.output_asset_id` or triggering approval eligibility → store preview artifact separately from final `output_asset_id` and gate `Approve` strictly on `production` render artifact.
- **Gates:** `G1`, `G2`, `G3`, `G4`, `G5`.

#### `PC-05.02` — Persistent SQL Asset Tags, Scoped Search & Channel Library UI (`P1`)
- **Objective:** Replace the empty channel media library placeholder (`panel_video_storyboard_js.py:470`) and unwired in-memory `AssetCatalogManager.search_by_tag` with persistent PostgreSQL asset tags (`V4-11.09`), scoped search/pagination by project/channel, strict license/provenance preservation (no dedup collision across licenses), and browser UI CRUD.
- **Target Files & Call Graph:** `migrations/0060_asset_tags.sql` → `adapters/postgres/media_repo.py` (`add_asset_tag`, `remove_asset_tag`, `search_project_assets(project_id, query, tag, kind, limit, offset)`) → `application/media.py` (`ManageAssetTags`, `SearchProjectAssets` enforcing project scope + license metadata) → `api/routes.py` (`GET /projects/{pid}/assets`, `POST/DELETE /projects/{pid}/assets/{aid}/tags`) → `api/panel_video_storyboard_js.py:470` (wire `'channel'` media tab to live server search + tag filter + add/remove tag + pick asset).
- **Contract & Rollback:** Additive table `0060`; zero mutation to `studio.assets` dedup key `(project_id, kind, hash, license)`.
- **Test-First Matrix:**
  - *Positive:* Tag imported PNG/MP4/audio with `"historia"`, `"computacao"` → search by tag and free text with pagination → pick asset into another scene in same project → restart process → tags & search results persist.
  - *Negative:* Cross-project tag read/write/search → `0` leaked rows / `403`; invalid/empty/overlong tag (`>64` chars or control chars) → `422`; same content bytes with two different licenses retain distinct provenance records.
  - *Concurrency & Browser:* Concurrent tag add/remove is idempotent; Playwright test adds tag, searches, reloads, and applies asset from channel tab.
- **Deps:** `PC-01.02` | **Complexity:** `M` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High`.
- **Risks & Mitigations:** Cross-tenant asset leak in search query → every SQL query joins/filters strictly by `project_id` and `belongs_to_scope`.
- **Gates:** `G1`, `G2`, `G4`, `G5`.

#### `PC-05.03` — Unwired / Dead Modules Inventory Resolution (`P1`)
- **Objective:** Resolve every remaining `0`-caller legacy module listed in §2.7 (`application/render_engine.py`, `application/asset_registry.py`, `application/studio_workbench.py`, `domain/studio_workbench.py`, `application/resilience.py`, plus any superseded duplicates in `composition/voice_catalog.py`, `domain/voice_preprocessing.py::narration_fingerprint`, `domain/voice_audio.py`) — either wiring genuinely valuable helpers into canonical services or retiring proven duplicates cleanly with test migration, proving zero parallel pipeline exists.
- **Target Files & Call Graph:** Audit via AST scan after `PC-05.01` & `PC-05.02` → remove proven duplicate in-memory services + migrate/replace isolated tests (`test_v4_render_engine.py`, `test_v4_asset_management.py`, `test_v4_studio_ux.py`, `test_v4_reliability_scale.py`) to target canonical Postgres/FFmpeg/FastAPI equivalents without lowering coverage or assertions.
- **Contract & Rollback:** Single clean commit; reversible via `git revert`; `test_architecture.py` (`9/9`) & `test_contracts_snapshot.py` (`3/3`) verified.
- **Test-First Matrix:**
  - *Positive:* AST caller audit proves `0` parallel render/asset/workbench/resilience pipelines remain; all migrated tests pass against canonical services in `./scripts/test-container.sh`.
  - *Negative:* No dangling imports across `renderer/app/` or `tests/`; no regression in golden or contract tests.
- **Deps:** `PC-05.01`, `PC-05.02` | **Complexity:** `M` | **Routing:** Executor `Carbon High`, Reviewer `Neon High`.
- **Risks & Mitigations:** Deleting a helper still used by tests (e.g., `domain/audio_dsp.py` synthetic WAV helpers used by 5 test modules) → verify AST callers across BOTH `renderer/app/` and `tests/` before touching any file.
- **Gates:** `G1`, `G2`, `G6` (focused + architecture/contract).

#### `PC-06.01` — Honest Technical & Semantic QA, Authorized Selective Action & Fail-Closed Caps (`P1`)
- **Objective:** Upgrade QA findings & selective recovery across all new PC-02..PC-05 capabilities: localized scene findings (duration, codec, audio clipping/dBTP, silence, black/frozen, caption sync, license, timeline/transition/layer bounds), structured correction proposals, authorized local selective re-render with retry caps & cancellation, honest state when `scene_repair=None` (exposing safe manual action, never faking repair), and strict `NOT_VERIFIED` semantic status when multimodal vision LLM (`V4-09.10–11`/`GAI-08`) is absent.
- **Target Files & Call Graph:** `domain/quality.py` (scene-localized checks for multitrack audio, layer/transition integrity, explicit `manual_action` proposal when `scene_repair=None`) → `adapters/quality_ffmpeg.py` (`FfmpegQualityEvaluator`) & `adapters/quality_semantic.py` (`NotVerifiedSemanticChecker` stays fail-closed `not_verified`, never conflating pixel stats with semantic relevance) → `application/production.py` (`QaHandler`: bounded `max_regeneration_attempts`, cooperative cancellation, zero paid calls, explicit `AWAITING_MANUAL_FIX` / `FAILED` state when automated local repair cannot fix defect) → `api/panel_video_workspace.py` (`/qualidade`: display per-scene findings, `NOT_VERIFIED` semantic banner, and one-click safe manual jump to failing scene).
- **Contract & Rollback:** Additive fields on `QaReport` / findings (backward-compatible with existing `videos.qa_report` JSONB).
- **Test-First Matrix:**
  - *Positive:* Inject known single-scene defect (black frame, clipping audio, caption drift `>500ms`, or missing asset license) → `FfmpegQualityEvaluator` produces scene-attributed finding + proposal → authorized local fix + selective re-render fixes ONLY affected scene → re-QA passes technical checks while semantic stays `not_verified` (`$0.00`).
  - *Negative:* Persistent defect exhausts `max_regeneration_attempts` and fails closed (no infinite loop, no paid fallback); `scene_repair=None` exposes manual action cleanly without faking repair; semantic `not_verified` never auto-approves.
- **Deps:** `PC-02`–`PC-05` mandatory tasks | **Complexity:** `L` | **Routing:** Executor `Hydrogen` / `Carbon High`, Reviewer `Neon High`.
- **Risks & Mitigations:** Breaking `test_journey_piloto.py` / `test_render_quality_e2e.py` QA severity contracts → preserve `blocking`/`warning`/`info` taxonomy strictly.
- **Gates:** `G1`, `G2`, `G3`, `G4`.

#### `PC-06.02` — Security, License Slug Hardening, `GetSceneTiming`, Edit Regression & Kill Switch (`P0`)
- **Objective:** Close every security & reliability residual across editing, licensing, error surfacing, concurrency/restart, `$0.00` budget ceiling, and publication kill switch.
- **Target Files & Call Graph:** `domain/asset_registry.py:63-94` (harden `ai-generated:<slug>` against disallowed license smuggling e.g. `ai-generated:cc-by-nc-nd-4.0`, require explicit origin/allowlist & real attribution) → `application/media.py:638-658` (`GetSceneTiming`: replace broad `except Exception: continue` with explicit operational error surfacing when timing read fails) → `application/publication_gate.py` (verify `license_block_reason` covers base `scenes.asset_id`, ALL `scene_assets` overlays/templates, AND ALL `video_audio_tracks`!) → `application/budget.py` / `application/production.py` / `application/publication_execution.py` (verify `$0.00` ceiling + `STUDIO_PUBLICATION_ENABLED=0` `BLOCKED` before any token/upload call).
- **Contract & Rollback:** Strictly fail-closed tightening; zero schema migration.
- **Test-First Matrix:**
  - *Positive:* Valid `OWN_ORIGINAL`, `CC0-1.0`, `CC-BY-4.0` (with attribution), and allowlisted `ai-generated:<valid-model>` pass; valid `GetSceneTiming` returns exact trim tuples.
  - *Negative:* `"ai-generated:cc-by-nc-nd-4.0"` rejected `422` & blocked at all 4 publication gates; unlicensed audio track or overlay blocks `Approve`/`ClaimPublication`/`RunPublication`; DB failure in `GetSceneTiming` raises explicit operational error (not silently swallowed); timeout/restart/uncertain-effect paid-op tests (`REC-01`) + edit/trim/overlay concurrency tests (`PC-01`) + kill switch `BLOCKED` (`0` OAuth/upload calls) all green.
- **Deps:** `PC-06.01` | **Complexity:** `M` | **Routing:** Executor `Hydrogen` / `Carbon High`, Reviewer `Neon High`.
- **Risks & Mitigations:** Over-restrictive `ai-generated:` regex breaking legitimate existing tests (`ai-generated:placeholder:v4`) → inspect every existing license fixture in `tests/` before tightening.
- **Gates:** `G2`, `G4`, `G6` (focused security/DB/regression).

#### `PC-07.01` — Offline 2nd Voice Viability & Real Blind Comparison (`V4-02.15`, `V4-13.05`) (`P1`)
- **Objective:** Diagnostic only (zero downloads, zero spend): inspect installed container/host for any already-present, license-verified 2nd offline PT-BR voice (e.g., 2nd Piper ONNX or verified Kokoro binary weights). If present, synthesize identical PT-BR reference text with both voices and produce blind-comparison WAV samples + duration/LUFS/dBTP metrics for human listening. If absent (current container has ONLY `/opt/voices/pt_BR-faber-medium.onnx`), record hard evidence, mark `V4-02.15`/`V4-13.05` `BLOCKED` (never synthesize sinewave/fake voice!), and document assisted audio import path + explicit operator decision `DEC-01`.
- **Target Files:** Documentary evidence under `evidence/pc07/pc07-01-voice-viability.md` (zero Core mutations).
- **Test-First Matrix:** Verify offline inventory command output, confirm `KokoroVoice` remains fail-closed (`validated=False`), `$0.00` spent, zero downloads.
- **Deps:** `PC-03.02` | **Complexity:** `S` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High`.
- **Gates:** `G1`, `G4` (documentary score `>= 9.0` does NOT mark `V4-02.15`/`13.05` `VERIFIED` if 2nd voice is unavailable).

#### `PC-07.02` — Local Hardware & Optional External Engines Viability Inventory (`P2 opt.`)
- **Objective:** Offline diagnostic only (`$0.00`, zero installs, zero CI/CD): inventory host/Docker hardware (`Apple Silicon` vs Docker Linux CPU `libx264` baseline for `V4-08.11` without inventing unrun VideoToolbox benchmarks) and evaluate integration criteria, licensing, operational overhead, cost estimates (explicitly labeled estimates), and operator decision requirements for `V4-03.05` (Freesound), `V4-05.02` (ComfyUI), `V4-05.23`/`V4-08.12` (Remotion), `V4-05.24` (Blender), `V4-07.03` (WhisperX), `V4-08.13` (2nd renderer), `V4-11.14`/`GAI-07` (Drive/S3), and `V4-12.14` (CI/CD — explicitly out of scope).
- **Target Files:** Documentary evidence under `evidence/pc07/pc07-02-engines-hardware-viability.md` (zero Core mutations).
- **Deps:** `PC-05.01` | **Complexity:** `S` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High`.
- **Gates:** `G1` (diagnostic only; never marks optional features `VERIFIED`).

#### `PC-07.03` — GAI-03..08 & Premium Optional Activation Plan (`P1 opt.`)
- **Objective:** Produce a zero-spend, zero-live-call BYOK activation blueprint for `GAI-03` (Gemini Text), `GAI-04` (Image), `GAI-05` (Gemini TTS), `GAI-06`/`V4-05.15` (Veo async submit/poll/reconcile), `GAI-07`/`V4-11.14` (Drive OAuth opt-in, render offline-safe), `GAI-08`/`V4-09.10–11` (multimodal QA with `not_verified` fallback), and `V4-13.04` (premium 15–20min pilot): neutral ports/adapters (zero Google SDK in Core), per-project BYOK credentials (never consumer subscription/cookie automation), preflight budget reservation + reconciliation, explicitly labeled test doubles, cost estimates, license/privacy prerequisites, and exact operator consent items (`DEC-05`).
- **Target Files:** Documentary evidence under `evidence/pc07/pc07-03-gai-activation-plan.md` (zero Core mutations, zero speculative adapters).
- **Deps:** `PC-06.01` | **Complexity:** `S` | **Routing:** Executor `Flash` / `Hydrogen Medium`, Reviewer `Carbon High` + `Neon High` (financial controls).
- **Gates:** `G1`, `G4` (zero live calls, `$0.00`).

#### `PC-08.01` — 60–90s Vertical Slice Pilot via Studio Using All New Essential Capabilities (`P0`)
- **Objective:** Execute a real `60–90s` (`1080p25`) vertical slice strictly through the canonical Studio HTTP/UI path (`$0.00`, `STUDIO_PUBLICATION_ENABLED=0`) exercising ALL newly delivered capabilities: channel vocal identity + PT-BR pronunciation/pauses (`PC-03.01–02`), per-scene direction/shots (`PC-03.03`), authorized audio import + 3+ edited tracks + EQ/compression + mix preview (`PC-02.01–03`), layer editor + PNG overlay + animated MP4 PiP + base replace preserving overlays (`PC-01`, `PC-04.01`), real `crossfade`/`slide` transition (`PC-04.02`), declarative animated template/lower-third (`PC-04.03`), controlled post-processing (`PC-04.04`), `540p` preview → `1080p` production render (`PC-05.01`), persistent asset tags (`PC-05.02`), and QA + selective 1-scene regen (`PC-06`).
- **Target Files & Artifacts:** Dedicated pilot harness & `evidence/pc08/pc08-01-slice-evidence.md` + `manifest.json` (gitignored MP4 under `storage/output/runs/pc08_slice_<ts>_<sha>/` with SHA-256, `ffprobe`, `ebur128`, sync drift, frozen/black/silence, stage wall/CPU/RSS, `$0.00` ledger, kill switch `BLOCKED`, `auto_approved=false`). Clearly label browser vs API vs local fixture steps.
- **Deps:** All mandatory `PC-02`–`PC-06` tasks | **Complexity:** `L` | **Routing:** Executor `Flash`/`Hydrogen`/`Carbon`, Reviewer `Neon High` + Operator.
- **Gates:** `G3`, `G4`, `G7` (technical `>= 9.0`; human audiovisual `AWAITING_HUMAN_REVIEW`).

#### `PC-08.02` — 5–8min Documentary Pilot via Studio, Paired Comparison & Selective Regen (`P0`)
- **Objective:** Produce an original `300–480s` (`5–8min`, `1080p25`, `>=20–25` scenes) documentary via Studio (`economic_local`, `$0.00`) exercising all new PC capabilities, plus evaluate `balanced_local` (`V4-13.03`) honestly (run ONLY if a genuinely distinct higher-tier local media/voice setup is viable at `$0.00`; otherwise record `BLOCKED` and `DEC-02`, never relabel!). Produce controlled paired comparison against `V4-00` baseline (`345.80s`) and `REC-04.02` (`309.80s`) with explicit rebaseline caveats (zero fabricated causal claims), selective 1-scene regeneration reuse proof, and full SHA-256 manifest.
- **Target Files & Artifacts:** `evidence/pc08/pc08-02-documentary-evidence.md` + `manifest.json` + sampled PNG frames + gitignored MP4 under `storage/output/runs/pc08_doc_<ts>_<sha>/`.
- **Deps:** `PC-08.01` | **Complexity:** `L` | **Routing:** Executor `Flash`/`Hydrogen`/`Carbon`, Reviewer `Neon High` + Operator.
- **Gates:** `G3`, `G4`, `G7`.

#### `PC-08.03` — Real Browser Desktop/Mobile E2E User Journey & Human Handoff Package (`P0`)
- **Objective:** Execute full end-to-end user journey in isolated Chromium (`docker-compose.e2e.yml` on unique port `8100`, `tmpfs`, torn down via `down -v`) across Desktop (`1280x800`) and Mobile (`390x844`): create video → configure voice/pronunciation → edit brief & per-scene shots → import PNG/MP4/audio → add 3+ audio tracks + mix preview → add layers/template/transition/post-fx → replace base asset proving zero overlay loss → undo/redo/reload → low-res preview → 1080p render → QA → edit 1 scene & selectively regenerate → local export; plus negative flows (stale `409`, bad license `422`, kill switch `BLOCKED`). Prepare complete operator audiovisual handoff guide with macOS `open` commands, SHA-256 verification, and 6-dimension `>= 9.0` rubric (`V4-00.06` & `V4-13.11`).
- **Target Files & Artifacts:** Isolated Playwright E2E tests + `evidence/pc08/pc08-03-browser-e2e-and-handoff.md`.
- **Deps:** `PC-08.02` | **Complexity:** `L` | **Routing:** Executor `Flash`/`Hydrogen`/`Carbon`, Reviewer `Neon High` + Operator.
- **Gates:** `G4`, `G5`, `G7`.

#### `PC-09.01` — Full Clean-SHA Final Regression & Independent Release Audit (`P0`)
- **Objective:** Zero new features. On the final clean `develop` SHA after the last functional change, execute ALL 4 isolated test campaigns from scratch without summing overlapping campaigns: (1) Canonical Container Suite (`./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q`), (2) Host Node.js / Panel Suite, (3) Isolated Browser E2E (`tests/e2e_ux` + `tests/e2e_full` on `8100`, torn down `down -v`), (4) Host Playwright UI Contract Modules (`test_reference_browser.py` + `tests/ve08/`). Archive sanitized logs & JUnit XMLs with exact commands, exit codes, skip/exclusion reconciliation, image hash, migration count, and zero secret leaks. If any functional/contract fix is needed, re-run ALL 4 campaigns cleanly on the new SHA.
- **Target Files & Artifacts:** `evidence/pc09/pc09-01-regression-evidence.md` + sanitized logs & JUnit XMLs under `evidence/pc09/regression/`.
- **Deps:** `PC-08.03` | **Complexity:** `M` | **Routing:** Executor `Carbon High`, Reviewer `Neon High` (independent).
- **Gates:** `G0`, `G2`, `G4`, `G5`, `G6` (`>= 9.0` all dimensions, `0` P0/P1).

#### `PC-09.02` — Final Reconciled Matrix, `FINAL-REPORT.md`, Studio User Guide & Operator Sign-Off Gate (`P0`)
- **Objective:** Reconcile ALL 227 V4 IDs, 44 previously deferred IDs, 9 GAI IDs, 17 historical REC IDs, and 27 PC IDs without duplication or inflation (never claim "100% V4" while any `DEFERRED`/`BLOCKED`/`AWAITING_HUMAN_REVIEW` exists); update `../TRACEABILITY-MATRIX.md` additively without erasing historical REC records; author `product-completion/FINAL-REPORT.md`, Studio operational user guide, honest limitations register, and non-destructive rollback guide (commit-by-commit + SQL `0055`..`0060`). Stop strictly at `TECHNICAL GO / AWAITING OPERATOR` (if all mandatory technical gates & independent `Neon High` review pass `>= 9.0/10`) or `NO-GO/BLOCKED` (otherwise). Never execute merge, publication, or paid API calls.
- **Target Files & Artifacts:** `product-completion/FINAL-REPORT.md`, updated `product-completion/TRACEABILITY-MATRIX.md`, additive addendum in `../TRACEABILITY-MATRIX.md` (coordinator-owned).
- **Deps:** `PC-09.01` | **Complexity:** `M` | **Routing:** Executor `Carbon High`, Reviewer `Neon High` (independent) + Operator.
- **Gates:** `G1`–`G7` + Operator human audiovisual review (`>= 9.0` all 6 dimensions) + Operator explicit scope decision + separate Operator merge authorization.

---

## 5. Explicit Release & Audiovisual Status

| Scope | Status at `PC-00` (`HEAD 8484b72`) | Authorization / Blocker |
|---|---|---|
| **Campaign Technical Gate** | **`NO-GO / PLANNING ONLY`** | `PC-00.01` and `PC-00.02` are documentary planning artifacts awaiting independent `Carbon High` review (`>= 9.0/10`). Zero product code modified; `PC-01` edit-integrity `P1` defect is **OPEN** and proven live. |
| **Human Audiovisual Gate (`V4-00.06`, `V4-13.11`)** | **`AWAITING_HUMAN_REVIEW` (NO AUDIOVISUAL GO)** | Zero audiovisual approval granted or inferred; operator must personally evaluate baseline and new `PC-08` pilots (`>= 9.0/10` across all 6 dimensions). |
| **Merge `develop` → `main` (`42700cb`)** | **`NO-GO` (FORBIDDEN)** | Protected `main` untouched (`42700cb`); merge requires `PC-09` completion, human audiovisual sign-off, and separate explicit operator authorization. |
| **YouTube Publication & External Paid APIs** | **`BLOCKED` / `$0.00`** | `STUDIO_PUBLICATION_ENABLED=0`, zero paid keys, `$0.00` external API budget ceiling strictly enforced. |
