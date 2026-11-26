# REC-04.01 Independent Review (`github-copilot/gemini-4-neon`, Round 1 — Fresh Session)

- **Reviewer / Real Model:** Independent Reviewer (fresh subagent session, zero deference) — `github-copilot/gemini-4-neon` (Gemini 4 Neon)
- **Target Slice:** `REC-04.01` (`R11` / `INT-06.01` — Vertical Slice real de 60–90s via rotas HTTP canônicas do Studio + `ProductionCoordinator` + `PlanFfmpegRenderer`, reclassificação de `tests/test_int_06_pilot.py` como `SMOKE`, artefatos preservados em diretório exclusivo e manifesto versionado)
- **Repository / Branch:** `/Users/rodrigomendes/youtube-faceless-starter` on `develop` (`main` untouched @ `42700cb331165a68455173a91c463d4733292cfd`)
- **Base HEAD:** `4fa225b34853093097c40cce57b7a601ab753d2f` + uncommitted working tree (read-only audit; zero code/test edits, zero commits/pushes)
- **Reviewed Artifact Hashes (SHA-256 — independently computed):**
  - `git diff` (3 tracked files, `+75 / -14`): `3a824744032ef1517ea6066658d908cec3a93e610a10f733582e7d033745d8d4`
  - `renderer/app/studio/application/render.py`: `f698a61472857f84e91e793912bf55d136b6b054ebabcf201c5cb2760d3fc32b`
  - `tests/conftest.py`: `69d9262a922c54daa0e2c64ed020894c267f819ca1bb433456c018f9d8b4011c`
  - `tests/test_int_06_pilot.py`: `d121c2038bd394525af90283612b72d22cc6dcbdcdf4a6d4009953e15bf07cf0`
  - `tests/test_rec_04_vertical_slice.py` (untracked): `77201f17bc4778d2e4241dfeff8652192775ab80a42e7c120ce0fd288183c66b`
  - `scripts/run-rec04-slice.sh` (untracked): `207611f3f25b291c3efe97cfc06ef3623d1a9d0e389af785dd96c0fc7dff139b`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-01/manifest.json` (untracked): `2165e8c731991e9e00d09a84abb0749e113aaa0d919bcc5c26cabbcd4ce8f676`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-01-slice-evidence.md` (untracked): `b1e0c67e4eaff68dfc5eb7cc0a8979a7465cb2362f9621afbf1ea3684e7e4694`
  - Executor MP4 (`storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4`, `53,226,343 bytes`, gitignored): `088c11300a2b7f6737b13d2095741d3313bd27a487ff86e6876e2634ea92fcc3`
  - Reviewer Independent Run MP4 (`storage/output/runs/rec04_slice_20261126_215800_4fa225b/rec04_01_vertical_slice.mp4`, `52,798,984 bytes`, gitignored): `01e78856a3d426ec2a949d527c9b57c1abf6ad0974ca21fa60cca8b0c4f8c85e`
  - Alignment `renderer/app` checkout x Docker image: `8369da6e25579efe` (`49/49` migrations)
- **External Paid API Spend:** `$0.00` | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`) | **DEV Ports (`8000`/`5678`):** untouched
- **Review Round:** Round 1
- **Final Decision:** **`APPROVED`** *(Technical gate satisfied; audiovisual/aesthetic sign-off remains explicitly **`AWAITING_HUMAN_REVIEW`** until human operator inspects the MP4)*
  - **Exact Weighted Mean:** **`9.345 / 10`** (`>= 9.0`)
  - **Minimum Dimension Score:** **`9.1 / 10`** (`>= 9.0` on **all** 5 applicable dimensions)
  - **Open Blockers:** **`0` P0**, **`0` P1** (`4` non-blocking P2 items + `1` preexisting defect in untouched `render_compiler.py` logged separately)
  - **Absolute Rubric Blocks Triggered (`QUALITY-RUBRIC.md:22-26`):** **NONE**

---

## 1. Independent Verification Re-Executed

All commands were executed independently on the exact working tree (`HEAD 4fa225b` + diff SHA-256 `3a824744...`) with `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`.

### 1.1 Focused Container Suite
- **Command:**
  ```bash
  ./scripts/test-container.sh \
    tests/test_rec_04_vertical_slice.py \
    tests/test_int_06_pilot.py \
    tests/test_v4_studio_real_flow_pilot.py \
    tests/test_architecture.py -ra
  ```
- **Alignment:** `HEAD=4fa225b alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=8369da6e25579efe imagem=8369da6e25579efe`, `migrações: checkout=49 imagem=49`
- **Observed Result:** **`12 passed, 1 warning in 69.49s (0:01:09)`** (`0` failed, `0` skipped) | **Exit code:** **`0`**

### 1.2 Fresh Independent Vertical Slice Run (`scripts/run-rec04-slice.sh`)
- **Command:**
  ```bash
  ./scripts/run-rec04-slice.sh
  ```
- **Observed Result:** **`1 passed, 1 warning in 55.33s`** | **Exit code:** **`0`**
- **New Exclusive Run Dir:** `storage/output/runs/rec04_slice_20261126_215800_4fa225b/` (executor run `rec04_slice_20261126_213537_4fa225b/` preserved untouched).
- **Metric Comparison (Executor Run vs Independent Reviewer Run):**

| Metric | Executor Run (`213537`) | Reviewer Run (`215800`) | Verdict |
|---|---:|---:|---|
| Duration (`ffprobe`) | `67.360 s` | `66.920 s` | Consistent (`60–90s`; `0.44s` delta from normal Piper VITS synthesis variance) |
| Resolution / Codec / FPS | `1920x1080`, `h264`, `yuv420p`, `25/1` | `1920x1080`, `h264`, `yuv420p`, `25/1` | Exact match |
| Audio Codec / Rate / Ch | `aac`, `96000 Hz`, `2 ch` | `aac`, `96000 Hz`, `2 ch` | Exact match |
| Integrated Loudness (`ebur128`) | `-16.1 LUFS` | `-15.9 LUFS` | Consistent (`[-20, -12]`) |
| True Peak (`ebur128=peak=true`) | `-1.4 dBTP` | `-1.4 dBTP` | Exact match (`<= -1.0 dBTP`) |
| `black_ratio` / `silence_ratio` | `0.0` / `0.0` | `0.0` / `0.0` | Exact match |
| `frozen_ratio` | `0.1455` (`14.55%`) | `0.1447` (`14.47%`) | Consistent (`< 20%`) |
| Pixel diffs (PNG ov / KB / PiP / MP4) | `88.56 / 88.59 / 8.74 / 107.92 / 134.38 / 94.01 / 144.22` | `88.56 / 88.59 / 8.74 / 107.92 / 134.38 / 94.01 / 144.23` | Reproducible to 0.01 |
| Selective Regen Cache Hits | `4/4` nar + `10/10` vis (`-11.386s` / `-42.5%`) | `4/4` nar + `10/10` vis (`-10.916s` / `-41.7%`) | Proven reproducible |
| QA Checks / Blocking Findings | `10` checks (`render.overlay`, `render.caption_sync`), `0` blocking | `10` checks (`render.overlay`, `render.caption_sync`), `0` blocking | Exact match |
| Kill Switch / API Cost / Auto-approve | `BLOCKED` / `$0.00` / `False` (`AWAITING_APPROVAL`) | `BLOCKED` / `$0.00` / `False` (`AWAITING_APPROVAL`) | Exact match |

### 1.3 Full Canonical Container Suite (Gate G6)
- **Command:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alignment:** `HEAD=4fa225b alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=8369da6e25579efe imagem=8369da6e25579efe`, `migrações: checkout=49 imagem=49`
- **Observed Result:** **`4502 passed, 26 skipped, 1 warning in 827.17s (0:13:47)`** (`0` failed; total collected `4528`) | **Exit code:** **`0`**
- **Skips Breakdown (26 — structural in slim container):** `3` Playwright browser tests (`test_reference_browser.py`, `ve08/test_composition_functional.py`, `ve08/test_storyboard_functional.py` — `pytest_playwright` absent in slim image) + `23` Node.js tests (`node` absent in slim image — all executed and passed on host in §1.4).

### 1.4 Host Node.js / Panel / Workflow Suite
- **Command:**
  ```bash
  python3 -m pytest \
    tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
    tests/test_falha_producao.py tests/test_publicacao_acao.py \
    tests/test_workflow_analytics.py tests/test_workflow_publish.py \
    tests/test_workflow_trends.py -ra
  ```
- **Observed Result:** **`101 passed in 9.28s`** (`0` failed, `0` skipped) | **Exit code:** **`0`**

### 1.5 Out-of-Repo Mutation Verification (3 Independent Mutations — All 3 KILLED)
Executed on isolated temporary copies under `/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rec04_mut_*` mounted `:ro` into `faceless-renderer-pytest:test` against ephemeral Postgres 16 `tmpfs` (zero repo mutations; temp dir, container, and network removed unconditionally via `trap`).

| # | Target File & Mutation Applied | Test Executed | Observed Result | Verdict |
|---|---|---|---|---|
| **M1** | `renderer/app/studio/application/render.py`: short-circuit `RunRender._overlay_layers` to `return ()` | `tests/test_rec_04_vertical_slice.py` | `FAILED` at `:767` (`AssertionError: FfmpegOverlayVerifier não executou`), `1 failed in 48.23s`, **exit `1`** | **KILLED** |
| **M2** | `renderer/app/studio/application/render.py`: short-circuit `RunRender._cached_narration` to `return None` (breaking selective cache reuse) | `tests/test_rec_04_vertical_slice.py` | `FAILED` at `:734` (`AssertionError: Shot visual intocado ... não reutilizou cache`), `1 failed in 60.60s`, **exit `1`** | **KILLED** |
| **M3** | `renderer/app/studio/adapters/voice_piper.py`: replace `PiperVoice.speak` with 10s silent PCM16 WAV (`b'\x00\x00'`) | `tests/test_rec_04_vertical_slice.py` | `FAILED` at `:604` (`Run #1 stage qa failed: QA failed after 2 selective regeneration attempt(s)...`), `1 failed in 38.95s`, **exit `1`** | **KILLED** |

---

## 2. Independent Artifact Forensics, Visual Frame Inspection & Diff Audit

### 2.1 Artifact Integrity, Gitignore & Independent Media Measurements
Re-measured directly on executor artifact `storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4`:
- **`git check-ignore -v`:** `.gitignore:2:storage/output/*` — confirmed MP4 is **NOT** tracked or staged in Git.
- **SHA-256 & Size:** `088c11300a2b7f6737b13d2095741d3313bd27a487ff86e6876e2634ea92fcc3`, `53,226,343 bytes` — **100% match** with `manifest.json:32-33`. All `3` subtitle files (`srt`/`vtt`/`ass`) and all `5` sampled PNGs also matched `manifest.json` SHA-256 byte-for-byte.
- **`ffprobe`:** `duration=67.360000s`, `bit_rate=6321418 bps`, video `h264` `1920x1080` `yuv420p` `25/1 fps` (`1684` frames), audio `aac` `96000 Hz` stereo `158554 bps` — **100% match** with `manifest.json:41-57`.
- **`ffmpeg -af ebur128=peak=true`:** `I = -16.1 LUFS`, `LRA = 2.9 LU`, `True peak = -1.4 dBFS (-1.4 dBTP)` — **100% match** with `manifest.json:64,68`.
- **`ffmpeg -af volumedetect,silencedetect=noise=-45dB:d=0.5`:** `mean_volume = -18.7 dB`, `max_volume = -1.4 dB`, **`0` silence intervals** (`silence_ratio = 0.0`) — proves real, non-silent, non-clipping audio throughout.
- **`ffmpeg -vf blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-50dB:d=1.0`:** **`0` black intervals** (`black_ratio = 0.0`); freeze segments occur exclusively in the subtle gradient of Scene 4 (`56.52s–67.36s`), totaling `~14.55%` (`< 20%` QA threshold) — matches `FfmpegQa` exactly (`manifest.json:71`).

### 2.2 Direct Visual Inspection of Real Frames (10 PNGs Read)
Inspected all `5` manifest frames (`scene0_png_overlay.png` .. `scene4_studio_generated.png`) plus `5` independently extracted frames via `ffmpeg` (`t=0.50s, 15.20s, 16.30s, 34.00s, 65.50s`):
- **`t=0.50s` vs `scene0_png_overlay.png` (`t=1.80s`):** Dark grid + gold concentric circles; top-right gold graphic PNG badge cleanly absent at `0.50s` and visible at `1.80s` without touching HUD or captions; ASS karaoke active-word highlight progresses from `"da computação começou muito"` to `"começou muito"` in sync with `subtitles.srt` cue 1 (`00:00:00,300 --> 00:00:02,619`).
- **`t=15.20s`, `scene1_mp4_pip.png` (`t=15.44s`), `t=16.30s`:** Real video PiP animated from cyan (`t=15.20s/15.44s`) to magenta (`t=16.30s`) with white border over cyan bar-chart background; subtitles match `subtitles.srt` cues 8–9 (`"No século dezenove,"` -> `"Charles Babbage projetou a Máquina"`). **Objective composition defect observed (P2-1):** at `position_x=0.06, position_y=0.14` (`x=63..927, y=83..569`), the left-side PiP sits directly behind the top-left HUD (`"Ilustração gerada por IA"` at `y=96..130` and `"FATO"` pill at `y=160..245`). Z-order keeps disclosure/`FATO` on top (`render_plan_compiler.py:399`), so policy disclosure is not hidden, but contrast/legibility of the white disclosure text is objectively degraded by the bright white PiP border and the magenta PiP blends with the magenta `"FATO"` pill.
- **`scene2_imported_mp4.png` (`t=28.56s`) & `t=34.00s`:** Real imported 1080p MP4 moving (`testsrc2` timestamp advances `00:00:02.040` -> `00:00:07.480` with hue shift). **Objective preexisting defect observed (PRE-1) + evidence mislabeling (P2-3):** BOTH the Pillow `caption_overlay` dark rounded box AND the ASS karaoke subtitle appear simultaneously with identical text (`"Alan Turing e John von Neumann"` at `28.56s`; `"permitindo que computadores eletrônicos"` at `34.00s`). Root cause is preexisting in `renderer/app/studio/application/render_compiler.py:219` (`shot_subtitles = subtitles if len(scene.base_shots) == 1 else []`) combined with global ASS burn-in (`render_plan_compiler.py:283-294`): video base scenes stay single-shot, triggering double subtitle rendering. `rec-04-01-slice-evidence.md:153` inaccurately described this duplicate Pillow box as a `"lower-third"`.
- **`scene3_edited_v2.png` (`t=42.84s`):** Purple/gold v2 PNG and updated caption `"1971 integrou milhares de transistores em"` match `subtitles.srt` cue 23 (`00:00:42,632 --> 00:00:45,252`), confirming selective regeneration updated the final MP4.
- **`scene4_studio_generated.png` (`t=58.08s`) & `t=65.50s`:** Clean purple gradient from `AssetsHandler` (`placeholder:v4`) with synchronized subtitles (`"a expansão da internet e dos sistemas"` / `"consolidando a computação moderna em"`). Zero black frames across the entire sample.

### 2.3 Code Diff, Hash Preservation & Reclassification Audit
1. **`tests/test_int_06_pilot.py` (`git diff`):** Verified line-by-line that **ZERO assertions were removed or relaxed**. Changes are strictly docstring reclassification as `SMOKE (15s Short)`, `@pytest.mark.smoke` marker, and function rename (`test_int_06_real_studio_pilot_...` -> `test_int_06_smoke_15s_studio_flow_...`).
2. **`renderer/app/studio/application/render.py:134-166` (`StartRender.execute`):** When no scene has `scene_assets(role='overlay')`, `any(items for _, items in overlay_sig)` is `False` and the `else` branch produces the **exact byte-for-byte legacy JSON payload**, preserving `input_hash` and render cache/golden parity (`test_render.py` and `test_render_golden.py` passed in the `4502` container suite). When overlays exist, `overlay_sig` includes `(s.id, asset_id, position, start_s, end_s, role)` so overlay edits produce a distinct `input_hash`.
3. **`renderer/app/studio/application/render.py:326-356` (`RunRender._overlay_layers`):** Projects `scene_assets(role='overlay')` to `OverlayLayer`, failing closed with `RenderRefused` on missing asset or blank license, clamping `[start_s, end_s]` to `[0, length]`. Note: `publication_gate.license_block_reason` (`publication_gate.py:46-59`) already enforces `verify_license_provenance` fail-closed on `scene_assets`, and `ImportExternalMedia` enforces it at import.
4. **Ruling on Declared Limitations (`Multitrack 3+` ambience/SFX and `xfade` `DEFERRED` at Studio HTTP layer):**
   - Checked against `RECOVERY-BACKLOG.md:20`, `prompts/REC-04-pilot-release.md:2`, and `PROFESSIONAL-PILOT-SPEC.md:3` (*"Vertical slice de 60–90s após fundações mínimas: voz, 4 shots, música ducking, caption, um motion, alteração de fundo/trim e cache"*).
   - **Verdict: ACCEPTABLE (non-blocking for `REC-04.01`).** Why: (a) `REC-04.01` genuinely exercises the new V4 capabilities end-to-end through Studio HTTP + `ProductionCoordinator` + `PlanFfmpegRenderer` — real 60–90s Piper PT-BR, real PNG/MP4 import with `CC0-1.0`/CAS, PNG overlay + animated MP4 video PiP, `CreativeBrief` -> Ken Burns + moving MP4 base, real 2-track multitrack audio (voice + music bed with `sidechaincompress` ducking + `loudnorm`), `RenderPlan` subtitles + `render.caption_sync`, Scene 3 edit + selective regeneration cache reuse, real `FfmpegQa` + `FfmpegOverlayVerifier`, kill switch `BLOCKED`, `$0.00`; (b) 3+ track `MultitrackAudioPlan` (ambience/SFX) and inter-shot `xfade` (`crossfade`/`slide`/`wipe`) were already verified with real FFmpeg MP4/PCM/pixel proofs in `PlanFfmpegRenderer` during `REC-02.01`/`REC-02.02` (`ef367fc`, `9.43/10`); (c) exposing new HTTP schemas/DB tables for audio tracks and `visual_style.TRANSITION_KINDS` was not in `REC-03.01`/`REC-03.03` scope and is not mandated by `PROFESSIONAL-PILOT-SPEC.md` §2; (d) the executor did not fabricate coverage and honestly declared both `DEFERRED` in evidence and `manifest.json`. Per `QUALITY-GATES.md:G1`, explicit risk/owner/operator sign-off must be reconciled in `TRACEABILITY-MATRIX.md` (tracked as P2-4).

---

## 3. Rubric Scoring (`QUALITY-RUBRIC.md`)

| Dimensão | Peso | Nota (0–10) | Evidência Verificada | Achado |
|---|---:|---:|---|---|
| **Correção funcional e integração** | 25% | **9.2** | Slice real `67.36s`/`66.92s` 1080p integralmente pelas rotas HTTP do Studio + `ProductionCoordinator` + `PlanFfmpegRenderer`; Piper PT-BR real (`mean_volume=-18.7 dB`, `0%` silêncio); import PNG+MP4 `CC0-1.0`/CAS; overlay PNG + PiP MP4 animado + Ken Burns + MP4 base; multitrack 2 faixas com ducking (`-16.1/-15.9 LUFS`, `-1.4 dBTP`); legendas `RenderPlan` + `caption_sync`; edição Cena 3 + regeneração seletiva (`4/4` nar + `10/10` vis, `-42.5%`/`-41.7%`); `FfmpegQa` + `FfmpegOverlayVerifier` (`10` checks, `0` bloqueios). | **P2-1** (colisão de layout do PiP par com safe-zone superior esquerda); `PRE-1` (bug preexistente de legenda dupla na Cena 2, fora do diff); `DEFERRED` HTTP de 3+ faixas/`xfade` justificado e não bloqueante. |
| **Arquitetura e simplicidade** | 20% | **9.5** | Mudança cirúrgica (`+59/-2` em `render.py`); zero duplicação de coordenador/renderer/cache/registry; zero migrações novas (`49/49`); `StartRender.execute` preserva payload JSON byte-a-byte sem overlays; `test_architecture.py` `9/9` passou; rollback limpo. | **P2-1** (heurística de coordenada `position_y=0.14` para `position` par em `render.py:353-354`). |
| **Testes e regressão** | 20% | **9.3** | Suíte canônica completa `4502 passed, 26 skipped, 0 failed` (exit `0`, skips estruturais conciliados); host `101 passed` (exit `0`); focada `12 passed` (exit `0`); novo run `./scripts/run-rec04-slice.sh` `1 passed` (exit `0`); `test_int_06_pilot.py` reclassificado `SMOKE` com `0` asserts relaxados; `3/3` mutações fora do repo (M1/M2/M3) **KILLED** (exit `1`). | **P2-2** (faltam testes unitários/negativos dedicados para os novos ramos em `render.py:151-166, 326-356` e ajuste menor de timestamp `1.20s` vs `1.40s` em `test_rec_04_vertical_slice.py:859,869,885`). |
| **Segurança, orçamento e confiabilidade** | 20% | **9.6** | `$0.00` comprovado em `usage_ledger` e `GET /cost-breakdown`, `budget_guard=True`, `max_cost_*=0.0`, ElevenLabs desabilitado; kill switch `STUDIO_PUBLICATION_ENABLED=0` -> `BLOCKED`; zero autoaprovação (`AWAITING_APPROVAL` / `WAITING_HUMAN`); `CC0-1.0` + `publication_gate` fail-closed para `scene_assets`; Postgres efêmero `tmpfs` sem portas no host; `8000`/`5678`/`main` intocados; MP4 gitignored. | Defesa em profundidade opcional: usar `verify_license_provenance` também em `render.py:336` (import e `publication_gate` já bloqueiam). |
| **Evidências e operação** | 15% | **9.1** | Todos os hashes SHA-256 (MP4, SRT/VTT/ASS, 5 frames, 7 arquivos de código/evidência) e métricas (`ffprobe`, `ebur128`, `FfmpegQa`) revalidados com `100%` de correspondência; runner reproduzível `./scripts/run-rec04-slice.sh` com diretórios exclusivos; classificação honesta sem simular revisão humana. | **P2-3** (`rec-04-01-slice-evidence.md:153` rotula erroneamente legenda Pillow duplicada na Cena 2 como `"lower-third"`); **P2-4** (`versions.piper` capturou texto `usage:` em `manifest.json:14` e formalização G1 de risco/owner dos `DEFERRED` HTTP na matriz). |

- **Cálculo exato da média ponderada:**
  `(9.2 × 0.25) + (9.5 × 0.20) + (9.3 × 0.20) + (9.6 × 0.20) + (9.1 × 0.15) = 2.300 + 1.900 + 1.860 + 1.920 + 1.365 = 9.345 / 10`
- **Gates Aplicáveis:** `G0` PASS, `G1` PASS (com nota P2-4 para reconciliação na matriz), `G2` PASS, `G3` PASS, `G4` PASS, `G6` PASS (`4502/0` container + `101/0` host), `G7` PASS técnico (vertical slice 60–90s concluído; documentário 5–8min pendente em `REC-04.02`; revisão audiovisual humana pendente em `AWAITING_HUMAN_REVIEW`).

---

## 4. Achados Classificados (`P0` / `P1` / `P2` + Bug Preexistente)

### Bloqueadores (`P0` / `P1`)
- **Nenhum (`0` P0, `0` P1).**

### Melhorias Não-Bloqueantes (`P2`)
1. **`P2-1` — Defeito objetivo de composição: PiP/overlay em `position` par colide com a safe-zone do disclosure de IA e selo `"FATO"`**
   - **Local:** `renderer/app/studio/application/render.py:353-354` (interagindo com `renderer/app/studio/adapters/render_plan_ffmpeg.py:259-265`).
   - **Evidência:** Para `position=2` (`position_x=0.06, position_y=0.14, scale=0.45`), o overlay ocupa `x=[63..927], y=[83..569]` sobre a zona do HUD superior esquerdo (`"Ilustração gerada por IA"` em `y=96..130` e `"FATO"` em `y=160..245`), visível em `scene1_mp4_pip.png`, `frame_15.20.png` e `frame_16.30.png`. O z-order mantém o HUD acima do overlay (`render_plan_compiler.py:399`), razão pela qual não bloqueia `REC-04.01`, mas degrada a legibilidade do disclosure sobre PiPs claros/magenta.
   - **Recomendação (antes de `REC-04.02`):** Ajustar `position_y` para overlays à esquerda para `>= 0.46` (`y >= 273px`, abaixo da safe-zone `y=245px`) ou aceitar coordenadas explícitas em `scene_assets`.
2. **`P2-2` — Ausência de testes unitários/negativos dedicados para os novos ramos em `render.py` + inconsistência menor de timestamp no teste do slice**
   - **Local:** `renderer/app/studio/application/render.py:151-166, 326-356`; `tests/test_rec_04_vertical_slice.py:859, 869, 885`.
   - **Evidência:** Não foram adicionados testes unitários em `tests/test_render.py` cobrindo mudança de `StartRender.input_hash` ao anexar overlay, `RenderRefused` em `ov_asset is None` ou licença em branco, e descarte de janela `end_s <= start_s`. Adicionalmente, em `test_rec_04_vertical_slice.py`, `f_s1_pip_a` é extraído em `+1.20s` e `f_s1_pip_b` em `+2.30s`, enquanto a mensagem em `:869` menciona `"entre 1.4s e 2.75s"` e `:885` registra `+1.40s` no manifesto.
   - **Recomendação:** Adicionar testes unitários negativos/de hash para `_overlay_layers`/`StartRender` e alinhar o timestamp em `test_rec_04_vertical_slice.py`.
3. **`P2-3` — Imprecisão descritiva na evidência visual da Cena 2**
   - **Local:** `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-01-slice-evidence.md:153`.
   - **Evidência:** O texto afirma que `scene2_imported_mp4.png` possui `lower-third "Alan Turing e John von Neumann" e legenda sincronizada`. A inspeção visual de `scene2_imported_mp4.png` (`28.56s`) e `frame_34.00.png` (`34.00s`) prova que a caixa escura arredondada NÃO é um lower-third: ela replica textualmente a legenda ativa (efeito do bug preexistente `PRE-1`).
   - **Recomendação:** Corrigir a descrição na evidência ou registrar a ressalva na próxima atualização documental.
4. **`P2-4` — Versão CLI do Piper no manifesto e formalização G1 de itens `DEFERRED` na camada HTTP**
   - **Local:** `tests/test_rec_04_vertical_slice.py:957`, `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-01/manifest.json:14,258-262`.
   - **Evidência:** `versions.piper` gravou a linha `usage: piper [-h] ...` (já reconhecido honestamente em `rec-04-01-slice-evidence.md:160`; `importlib.metadata.version('piper-tts')` retorna a versão real). Os dois itens `DEFERRED` na camada HTTP (`Multitrack 3+` ambiência/SFX e `xfade`) devem constar com risco, owner e decisão do operador em `TRACEABILITY-MATRIX.md` até `REC-04.04` (regra `G1`).

### Bug Preexistente Registrado Separadamente (Fora do Escopo/Diff de `REC-04.01`)
- **`PRE-1` — Duplicação de legendas queimadas (Pillow `caption_overlay` + ASS `-vf subtitles`) em cenas de shot único (ex.: vídeo MP4 base na Cena 2)**
  - **Local:** `renderer/app/studio/application/render_compiler.py:216-219` + `renderer/app/studio/adapters/render_plan_compiler.py:240-294` (arquivos **não** alterados em `REC-04.01`).
  - **Evidência:** Em `scene2_imported_mp4.png` (`t=28.56s`) e `frame_34.00.png` (`t=34.00s`), a cena de vídeo base tem `len(scene.base_shots) == 1`, fazendo `render_compiler.py:219` manter `shot_subtitles = subtitles` (queimando a caixa escura Pillow no segmento) enquanto `render_plan_compiler.py:290` também queima `subtitles.ass` globalmente na saída final — resultando em duas legendas simultâneas idênticas empilhadas.
  - **Impacto / Ação:** Registrado para correção antes ou durante `REC-04.02` (documentário 5–8min com múltiplos B-rolls em vídeo), sem alterar o comportamento nesta revisão de `REC-04.01`.

---

## 5. Decisão Final

- **Decisão Técnica `REC-04.01`:** **`APPROVED`** (`9.345 / 10`, mínimo por dimensão `9.1 / 10`, `0` P0, `0` P1, `4502` container + `101` host + novo slice reproduzido + `3/3` mutações eliminadas).
- **Status Audiovisual:** **`AWAITING_HUMAN_REVIEW`** — o operador humano deve assistir `storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4` para avaliação estética/editorial; nenhuma autoaprovação foi concedida.
- **Próximo passo autorizado após commit atômico de `REC-04.01`:** avançar para **`REC-04.02`** (documentário 5–8min pareado com V4-00), idealmente endereçando `P2-1` (safe-zone do overlay à esquerda) e `PRE-1` (legenda dupla em shots únicos de vídeo) para evitar regressão visual no documentário.
