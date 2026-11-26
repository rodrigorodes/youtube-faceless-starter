# Independent Review — `REC-02.01` (`R04`) & `REC-02.02` (`R05`)

- **Reviewer:** `rec02-av-rev` (`Gemini 4 Neon High`)
- **Branch / Base SHA:** `develop` @ `4ece073164251d0dfb6f6b01bbf4ae787e82fc55` + uncommitted working-tree diff (`11` modified tracked files, `+394/-70`; `2` untracked author files: `tests/test_rec_02_av_composition.py`, `rec-02-01-02-av-evidence.md`)
- **Author Evidence Audited:** `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-02/rec-02-01-02-av-evidence.md`
- **External API Spend:** `$0.00` | **Publication:** `DISABLED`
- **Round 1 Verdict (`#27`):** **REJECTED** (`REC-02.01 = 8.575/10`, `REC-02.02 = 8.050/10`; 4 P1 blockers: `P1-1`..`P1-4`).
- **Round 2 Final Verdict:** **APPROVED (VERIFIED)** — All 4 P1 blockers + defense-in-depth resolved and independently verified in container (`REC-02.01 = 9.440/10`, `REC-02.02 = 9.425/10`, `164 passed in 42.97s`, exit code `0`, zero P0/P1 blockers).

---

## 1. Independent Container Test Verification (Round 2)

Executed verbatim in container (`Python 3.12.16`, `pytest 8.3.5`, `FFmpeg 7.1.5`, `Postgres 16-alpine` tmpfs, `hash renderer/app: 357fa45cf4168927`, `49` migrations):

```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh \
  tests/test_rec_02_av_composition.py \
  tests/test_int_03_composition.py \
  tests/test_v4_composition_core.py \
  tests/test_v4_audio_professional.py \
  tests/test_v4_visual_motion.py \
  tests/test_render_compiler.py \
  tests/test_render_plan_compiler_v2.py \
  tests/test_render_plan_overlay.py \
  tests/test_render_plan_ffmpeg_audiovisual.py \
  tests/test_render_golden.py \
  tests/test_render_plan_v2_contract.py \
  tests/test_contracts_snapshot.py \
  tests/test_architecture.py
```

- **Result:** `164 passed in 42.97s` (exit code `0`).
- **Contract / Golden / Architecture Parity:** `test_contracts_snapshot.py` (3/3), `test_render_golden.py` (8/8), `test_render_plan_v2_contract.py` (21/21), `test_architecture.py` (9/9) all passed unchanged.
- **Legacy Test Diff Audit:** Verified all 4 modified test files (`test_int_03_composition.py`, `test_render_compiler.py`, `test_render_plan_compiler_v2.py`, `test_v4_audio_professional.py`) — zero relaxed assertions; changes strictly reflect removal of fade-to-black crossfade, removal of fake `true_peak_dbtp` alias, and enabling `video` PiP while still rejecting `text`/`audio`.
- **Sample-Peak Alias Audit:** `git grep -n "true_peak_dbtp" renderer/app/` confirms zero remaining sample-peak aliases; `audio_dsp.py` exposes only `sample_peak_dbfs`, while `true_peak_dbtp` appears exclusively in real FFmpeg `ebur128` (`qa_ffmpeg.py:78`), target config (`audio_multitrack.py:58,183`, `render_plan_compiler.py:699`), and QA evaluation (`quality.py:290,292`).

---

## 2. Deep Technical Verification & Round 1 -> Round 2 Resolution Audit

### Core Capabilities Verified
1. **Real Inter-Shot `xfade` & Timeline Arithmetic (`REC-02.01` / `R04`):**
   - `_fade_filter` (`render_plan_compiler.py:712-753`) returns `""` for `crossfade`, `slide_left`, `slide_right`, `wipe_left`, `wipe_right`, `cut` (no fade-to-black masking).
   - `_compile_concat` (`render_plan_compiler.py:556-616`) compiles inter-shot transitions via `tpad=stop_duration=half_d:stop_mode=clone` + `tpad=start_duration=half_d:start_mode=clone` + `xfade=transition=<mapped>:duration=d:offset=cursor-half_d`. Duration math (`offset + (half_d + next_shot.seconds) = cursor + next_shot.seconds`) preserves exact total duration (`T0 + T1 + ...`) and frame-accurate audio/subtitle alignment, while keeping fast `-f concat -c copy` when no inter-shot transitions are present.
   - `_validate_transitions` (`application/render_compiler.py:300-322`) fails closed with `CompileError` when `duration_ticks <= 0` (added in Round 2), `duration_ticks >= shorter`, inter-shot transition is placed on the final shot, or transition kind is unsupported.
   - Real FFmpeg MP4 pixel proof verified for `crossfade` (red -> blended purple -> blue, non-black midpoint) and `slide_left`/`wipe_left` (spatial left/right split).
2. **Video PiP & Finite Bounds (`REC-02.01` / `R04`):**
   - Finite bounds (`opacity in [0, 1]`, `scale in (0, 4]`, `position_x/y in [0, 1]`, rejecting `NaN`/`Inf`) enforced across `Composition._validate_finite_bounds`, `_validate_overlays`, and `_overlay_filter`.
   - `video`, `image`, and `graphic` accepted in `_validate_overlays`; `text` and `audio` rejected with `CompileError`.
   - `_compile_shot` omits `-loop 1` for `video` overlays; `_overlay_filter` applies `setpts=PTS-STARTPTS+<start>/TB` (with optional `trim=start=<offset>`) and `eof_action=pass`.
   - Real FFmpeg MP4 proof verified moving green->yellow PiP at `(1700, 180)` + alpha-blended cyan PNG at `(240, 945)` over intact navy background at `(960, 540)`.
3. **Real `ebur128` dBTP, Canonical Multitrack Audio & Motion (`REC-02.02` / `R05`):**
   - `audio_dsp.mix_multitrack_pcm` removed `"true_peak_dbtp"`; real dBTP measured exclusively via `FfmpegQa` (`ebur128=peak=true`, verified `<= -1.0 dBTP`, `-22 <= integrated_lufs <= -11`, duration preserved).
   - `MultitrackAudioPlan` + `AudioCatalog` wired into `RenderSpec` / `compile_multitrack_audio_args` / `PlanFfmpegRenderer.execute`, enforcing fail-closed `verify_audio_licenses` before FFmpeg execution.
   - `calculate_motion_curve` wired into `_zoompan` preserving golden parity (`8/8`) and proven via real MP4 pixel displacement (`zoom_in` > `5.0` vs `none` < `1.0`).

### Round 1 P1 Blockers — Independently Verified Resolved in Round 2

| ID | Round 1 Blocker | Round 2 Resolution Verified | Status |
|---|---|---|---|
| **P1-1** | `render_cache.py::_hosted_overlays` omitted `opacity`, `scale`, `position_x`, `position_y`, and `asset_offset_ticks`, causing stale cache hits on overlay/PiP edits; test only checked transition `digest()`. | `renderer/app/studio/domain/render_cache.py:454-478` now hashes non-default `(fit, opacity, scale, position_x, position_y)` and non-zero `asset_offset_ticks` (backwards-compatible with golden/default hashes). `tests/test_rec_02_av_composition.py:425-489` proves both `CompiledRender.digest()` AND `plan_graph`/`selective_invalidation` invalidate on transition, overlay opacity, and PiP offset changes. | **CLOSED** |
| **P1-2** | `test_rec02_multitrack_voice_2music_ambience_sfx_ducking_ebur128` did not verify observable ducking attenuation on the real FFmpeg MP4 output. | `tests/test_rec_02_av_composition.py:598-633` renders both `ducked=True` and `ducked=False` MP4s via `PlanFfmpegRenderer.render`, decodes real PCM in speech (`[0.7s..1.7s]`) vs pause (`[2.4s..3.2s]`), and verifies `ducked_delta < unducked_delta - 1.5` dB (canceling `loudnorm` global gain). | **CLOSED** |
| **P1-3** | `compile_multitrack_audio_args` used `pan=stereo|c0=c0|c1=c0` (dropping stereo right channel) and `amix=duration=first` (truncating trailing audio on short narration). | `renderer/app/studio/adapters/render_plan_compiler.py:646-709` replaced `pan` with `aformat=channel_layouts=stereo`, added `apad=whole_dur={total_duration_s}` on `[1:a]` (avoiding early `sidechaincompress` EOF and avoiding dangling `[nsc]` when `ducked_labels` is empty), and switched final `amix` to `duration=longest`. `tests/test_rec_02_av_composition.py:635-691` proves stereo right-channel preservation and trailing audio past short narration (`[1.5s..2.2s]`, RMS `> -35.0 dB`) on real decoded stereo PCM. | **CLOSED** |
| **P1-4** | `PlanFfmpegRenderer.render` recorded `NodeId("final", "video")` into cache even when `multitrack is not None`, poisoning subsequent non-multitrack renders. | `renderer/app/studio/adapters/render_plan_ffmpeg.py:406,471-487` passes `skip_final=spec.multitrack is not None` to `_record()`, skipping `NodeId("final", "video")` persistence for multitrack renders. `tests/test_rec_02_av_composition.py:693-735` verifies `NodeId("final", "video")` is absent from recorded cache entries after a multitrack render. | **CLOSED** |
| **Minor** | Defense-in-depth guard for `tr.duration_ticks <= 0` when `Transition` bypasses Pydantic (`model_construct`). | `renderer/app/studio/application/render_compiler.py:310-313` added explicit `if tr.duration_ticks <= 0: raise CompileError(...)`. | **CLOSED** |

---

## 3. Rubric Scoring (`QUALITY-RUBRIC.md`) — Round 2 Final

### 3.1 `REC-02.01` (`R04`) — Real `xfade`, Video PiP, Finite Bounds & Cache/Contract Integrity

| Dimension | Weight | Score (0–10) | Evidence / Finding |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **9.5** | Real FFmpeg `xfade` + duration-preserving math, fail-closed `_validate_transitions` (including `<= 0` guard), real video PiP + finite bounds across 3 layers, and `render_cache.py::_hosted_overlays` now invalidates on transform and `asset_offset_ticks` changes (`P1-1` closed). |
| Arquitetura e simplicidade | 20% | **9.5** | Clean reuse of `RenderPlan`/compiler/FFmpeg/cache graph, fast `-f concat -c copy` preserved when no `xfade` is present, zero schema breaks (`contracts/v1/renderplan.schema.json`). |
| Testes e regressão | 20% | **9.2** | `164 passed in 42.97s` (exit `0`), real pixel sampling for `crossfade`/`slide_left`/`wipe_left`/moving PiP, `digest()` + `plan_graph`/`selective_invalidation` verified for transitions, overlay transforms, and PiP offsets, golden v1/v2 (`8/8`), contracts (`3/3`, `21/21`), and architecture (`9/9`) pass unchanged. Optional future expansion: `slide_right`/`wipe_right` and 3-shot `xfade` chains. |
| Segurança, orçamento e confiabilidade | 20% | **9.5** | Finite bounds & fail-closed validation on non-finite/out-of-range values, invalid transitions, and invalid media types; deterministic cache invalidation verified; `$0.00` external API spend. |
| Evidências e operação | 15% | **9.5** | Complete RED->GREEN + Round 2 trace, container hash (`357fa45cf4168927`), exact commands, justified legacy test updates (zero relaxed assertions), rollback plan. |

- **Exact Weighted Mean:** `9.5*0.25 + 9.5*0.20 + 9.2*0.20 + 9.5*0.20 + 9.5*0.15 = 9.440` (**9.440/10**)
- **Applicable Gates:** G1 (contracts/golden), G2 (functional/negative/FFmpeg pixel proof), G4 (cache/fingerprint determinism)
- **Blockers:** `0` P0, `0` P1
- **Decision:** **APPROVED (VERIFIED)**

### 3.2 `REC-02.02` (`R05`) — Real `ebur128` dBTP, Canonical Multitrack Audio & Motion Effects

| Dimension | Weight | Score (0–10) | Evidence / Finding |
|---|---:|---:|---|
| Correção funcional e integração | 25% | **9.5** | Fake `true_peak_dbtp` alias removed from `audio_dsp.py`, multitrack + license check + `calculate_motion_curve` wired into canonical renderer; stereo L/R preserved via `aformat=channel_layouts=stereo`, `apad=whole_dur` + `amix=duration=longest` prevents truncation/early sidechain EOF (`P1-3` closed), and `skip_final` prevents `final_node` cache poisoning (`P1-4` closed). |
| Arquitetura e simplicidade | 20% | **9.3** | Clean reuse of `MultitrackAudioPlan`, `AudioCatalog`, `verify_audio_licenses`, and `motion_effects` without duplicating renderer pipelines; clean `skip_final` guard on cache persistence. |
| Testes e regressão | 20% | **9.5** | `164 passed in 42.97s` (exit `0`), real `ebur128` (`true_peak_dbtp <= -1.0`, `LUFS`, duration), real PCM ducking control proof (`> 1.5 dB` attenuation, `P1-2` closed), stereo right-channel + trailing audio PCM proof, non-poisoned cache test, fail-closed license test, and real MP4 motion frame diff (`zoom_in` > `5.0` vs `none` < `1.0`). |
| Segurança, orçamento e confiabilidade | 20% | **9.4** | Fail-closed `verify_audio_licenses` before FFmpeg, real `ebur128` clipping guard (`<= -1.0 dBTP`), cache isolation verified (`skip_final`), `$0.00` external API spend. |
| Evidências e operação | 15% | **9.4** | Complete RED->GREEN + Round 2 evidence, updated container hash (`357fa45cf4168927`), exact test count (`164 passed`), justified legacy test updates, rollback plan. |

- **Exact Weighted Mean:** `9.5*0.25 + 9.3*0.20 + 9.5*0.20 + 9.4*0.20 + 9.4*0.15 = 9.425` (**9.425/10**)
- **Applicable Gates:** G2 (real FFmpeg multitrack/ducking/ebur128/motion proof), G3 (license fail-closed), G4 (cache integrity)
- **Blockers:** `0` P0, `0` P1
- **Decision:** **APPROVED (VERIFIED)**
