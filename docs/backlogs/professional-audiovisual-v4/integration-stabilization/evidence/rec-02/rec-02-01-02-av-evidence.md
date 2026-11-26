# REC-02.01 & REC-02.02 Evidence — Audiovisual Composition, Video PiP, Multitrack Audio & Motion

**Branch:** `develop` (base HEAD `4ece073164251d0dfb6f6b01bbf4ae787e82fc55`)  
**Executor:** `rec02-av` (`Gemini 4 Hydrogen Medium`)  
**External API Spend:** `$0.00` | **Publication:** `DISABLED` (`publication_enabled=False`)  
**Container Runtime:** `./scripts/test-container.sh` (Python `3.12.16`, pytest `8.3.5`, FFmpeg `7.1.5-0+deb13u1`, Postgres `16-alpine` tmpfs, `hash renderer/app: 357fa45cf4168927`, `49` migrations).

---

## 1. Test-First Proof (RED -> GREEN)

### 1.1 RED Phase (`tests/test_rec_02_av_composition.py` before implementation)
Command:
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh tests/test_rec_02_av_composition.py
```
Result: **`23 failed, 1 passed in 7.34s`** (exit code `1`), proving:
- `_fade_filter` previously emitted `fade=t=in:st=0:d=0.25,fade=t=out:st=1.500:d=0.500` for `crossfade` (fade-to-black instead of inter-shot `xfade`).
- `crossfade`, `slide_left`, and `wipe_left` produced unblended/unsplit cut pixels at `t=2.0s` (`(0, 0, 253)`).
- `Composition` accepted out-of-range and non-finite `opacity`/`scale`/`position_x`/`position_y` (`NaN`, `Inf`, `0.0`, `-1.0`, `4.1`).
- `_validate_overlays` rejected `media_type="video"` PiP overlays.
- `audio_dsp.mix_multitrack_pcm` still emitted `"true_peak_dbtp": sample_peak_dbfs`.
- `RenderSpec` / `PlanFfmpegRenderer` had no `multitrack` / `audio_catalog` integration.

### 1.2 GREEN Phase (Full 13-File Target Suite)
Command:
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
Result: **`164 passed in 43.16s`** (exit code `0`) after Round 2 P1-1..P1-4 fixes.

---

## 2. Implemented Changes & Observed Verification

### 2.1 `REC-02.01` (`R04`) — Real `xfade` Transitions, Video PiP, Finite Bounds & Golden/Contract Preservation
- **Real Inter-Segment `xfade` Transitions** (`renderer/app/studio/adapters/render_plan_compiler.py`, `renderer/app/studio/application/render_compiler.py`):
  - `_fade_filter` no longer treats `crossfade` as `fade=t=in`/`fade=t=out` (returns `""` for `crossfade`, `slide_left`, `slide_right`, `wipe_left`, `wipe_right`, `cut`).
  - `_compile_concat` compiles inter-shot transitions via FFmpeg `tpad` + `xfade` (`fade`, `slideleft`, `slideright`, `wipeleft`, `wiperight`) centered at the shot boundary, preserving exact total timeline duration (`4.0s` ± `0.12s` via `ffprobe`) and audio/subtitle sync. Fast `-f concat -c copy` is preserved when no inter-shot transition is present (preserving all golden v1/v2 renders).
  - `_validate_transitions` fails closed with `CompileError` when `duration_ticks >= shorter adjacent shot`, when an inter-shot transition is placed on the final shot, or when an unsupported transition kind is passed.
  - **Two-Color MP4 Proof:** Pure red `(255, 0, 0)` + pure blue `(0, 0, 255)` fixture with `crossfade` (`0.5s`): `t=0.5s` red (`R>200, B<40`), `t=2.0s` blended purple (`R>70 and B>70`, NOT black `(0,0,0)`), `t=3.5s` blue (`B>200, R<40`). `slide_left` and `wipe_left` split left/right pixels (`x=200` vs `x=1720`) at `t=2.0s`.
- **Video PiP & Finite Bounds** (`renderer/app/studio/domain/render_plan.py`, `application/ports.py`, `application/render_compiler.py`, `adapters/render_plan_compiler.py`, `adapters/render_plan_ffmpeg.py`):
  - `Composition` enforces finite bounds via `@model_validator`: `opacity in [0.0, 1.0]`, `scale in (0.0, 4.0]`, `position_x/position_y in [0.0, 1.0]`, rejecting `NaN`, `Inf`, `0.0`, and negative/out-of-range values.
  - `_validate_overlays` accepts `("image", "graphic", "video")` and rejects `"text"` / `"audio"` with `CompileError`.
  - `OverlayLayer` and `PlanFfmpegRenderer._build_plan` propagate `opacity`, `scale`, `position_x`, `position_y` into `StoryboardOverlay`.
  - `_compile_shot` & `_overlay_filter` omit `-loop 1` for `media_type == "video"`, apply `setpts=PTS-STARTPTS+<start>/TB` (with optional `trim=start=<offset>`) and `eof_action=pass`, and validate finite bounds defensively.
  - **Moving PiP + Multi-Overlay MP4 Proof:** Moving green->yellow PiP MP4 at `(scale=0.35, pos=(1.0, 0.0), opacity=1.0)` + static cyan PNG at `(scale=0.25, pos=(0.0, 1.0), opacity=0.6)` over navy background: top-right quadrant shifts from green (`t=0.7s`) to yellow (`t=2.0s`), bottom-left shows alpha-blended cyan, center stays navy.
- **Contracts, Golden & Digest:**
  - `test_contracts_snapshot.py` (3/3), `test_render_golden.py` (8/8), `test_render_plan_v2_contract.py` (21/21), and `test_architecture.py` (9/9) all pass unchanged.
  - `CompiledRender.digest()` AND `domain/render_cache.py::plan_graph` / `selective_invalidation` (`_hosted_overlays` now includes `opacity`, `scale`, `position_x`, `position_y`, and `asset_offset_ticks` using backwards-compatible default omission) invalidate deterministically when transition kind, overlay transform, or PiP offset changes.

### 2.2 `REC-02.02` (`R05`) — Real EBU R128 `dBTP`, Canonical Multitrack Audio & Motion Effects
- **Removed Fake `true_peak_dbtp` Alias** (`renderer/app/studio/domain/audio_dsp.py`):
  - Removed `"true_peak_dbtp": sample_peak_dbfs` from `mix_multitrack_pcm` metrics; keeps only `sample_peak_dbfs`.
  - Real `true_peak_dbtp` is measured exclusively via `FfmpegQa` (`ebur128=peak=true`).
- **Canonical Multitrack Audio Mix** (`application/ports.py`, `adapters/render_plan_compiler.py`, `adapters/render_plan_ffmpeg.py`):
  - Wired `MultitrackAudioPlan` + `AudioCatalog` into `RenderSpec` and `PlanFfmpegRenderer.execute` via `compile_multitrack_audio_args`.
  - Enforces `verify_audio_licenses(multitrack, audio_catalog)` before running FFmpeg (unknown/missing licenses raise `CompileError`).
  - **Real Multitrack MP4 Proof:** Voice `[0.4s..2.0s]` + 2 music tracks (`m1`, `m2` with `afade`) + ambience + timed SFX (`ding` at `3.5s` via `adelay`) + `sidechaincompress` ducking + `loudnorm`: `FfmpegQa().analyze(out_mp4)` verified `has_audio=True`, `duration_s ≈ 5.0s`, `true_peak_dbtp <= -1.0`, `-22.0 <= integrated_lufs <= -11.0`. Observable ducking attenuation proved by comparing speech-vs-pause RMS ratio on real rendered MP4 (`ducked=True` vs `ducked=False`, `> 1.5 dB` attenuation). Stereo right-channel preservation (`aformat=channel_layouts=stereo`) and trailing audio past short narration (`apad=whole_dur=...` + `amix=duration=longest`) proved on real stereo PCM decoded from rendered MP4 (`[1.5s..2.2s]`). Multitrack renders skip recording `NodeId("final", "video")` in `_record(..., skip_final=True)` so non-multitrack `final_node` cache is never poisoned.
- **Motion Effects Integration** (`adapters/render_plan_compiler.py`):
  - Wired `motion_effects.calculate_motion_curve` into `_zoompan`, preserving default `MOTION_NAMES` and golden parity.
  - **Real Motion MP4 Proof:** Grid PNG rendered with `zoom_in` shows `mean_abs_diff > 5.0` between `t=0.2s` and `t=1.5s`, while `none` shows `< 1.0`.

---

## 3. Modified / Added Files & Updated Test Justifications

### Production Files
- `renderer/app/studio/domain/render_plan.py`
- `renderer/app/studio/domain/render_cache.py`
- `renderer/app/studio/domain/audio_dsp.py`
- `renderer/app/studio/application/ports.py`
- `renderer/app/studio/application/render_compiler.py`
- `renderer/app/studio/adapters/render_plan_compiler.py`
- `renderer/app/studio/adapters/render_plan_ffmpeg.py`

### Test Files
- **New:** `tests/test_rec_02_av_composition.py` (26 tests covering REC-02.01 & REC-02.02).
- **Updated (only where old tests explicitly asserted old unimplemented limitations):**
  - `tests/test_int_03_composition.py`: updated `test_int_03_fade_filter_supports_crossfade` (no longer asserts fade-to-black for `crossfade`) and `test_int_03_audio_metrics_labeling` (asserts `"true_peak_dbtp" not in metrics` after R05 alias removal).
  - `tests/test_render_plan_compiler_v2.py`: updated `test_fade_filter_crossfade_supported` (asserts `_fade_filter` returns `""` for `crossfade` since `xfade` runs in `_compile_concat`).
  - `tests/test_v4_audio_professional.py`: updated line 255 from `metrics["true_peak_dbtp"]` to `metrics["sample_peak_dbfs"]` after R05 alias removal.
  - `tests/test_render_compiler.py`: updated `test_T12_overlay_media_must_be_image_or_graphic` from `["video", "text"]` to `["text", "audio"]` because `REC-02.01` enables `video` PiP overlays while still rejecting `text` and `audio`.

---

## 4. Rollback Plan
All changes are local, uncommitted on `develop` (`HEAD 4ece073`), with zero schema/migration changes and `$0.00` external API spend. Rollback is `git checkout -- renderer/app/studio/ tests/` and `rm tests/test_rec_02_av_composition.py`.
