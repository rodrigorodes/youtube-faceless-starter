# FINAL-REPORT — V4 Integration & Stabilization Recovery (`REC-00`..`REC-04`)

**Date (UTC):** `2026-11-27`  
**Repository / Branch:** `/Users/rodrigomendes/youtube-faceless-starter` — branch `develop`  
**Reopening Base Commit:** `72438e9ea215bbec12bd350d8c2606ca62bc7d94` (recovery opened at `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd`)  
**Final Functional Code Commit:** `a1e3640b96330da2f981983117ccf1ab66735e2a` (`hash renderer/app = b677160103d832a3`, `49/49` SQL migrations)  
**Final Clean Regression Commit (`develop` HEAD):** `6a55f1f296d1d34bad64d2adcaad3bc0eafce011` (`hash renderer/app = b677160103d832a3` unchanged; 3 browser test contract/selector alignments)  
**Protected `main` Branch SHA:** `42700cb331165a68455173a91c463d4733292cfd` (**strictly untouched** across the entire recovery campaign)  
**External Paid API Spend:** **`$0.00` USD** (`budget_guard=True`, `max_cost_per_video_usd=0.0`, `max_cost_per_month_usd=0.0`, zero paid keys)  
**YouTube Publication Kill Switch:** **`BLOCKED`** (`STUDIO_PUBLICATION_ENABLED=0`, zero OAuth token or upload calls)

---

## 1. Executive Release Gate Verdict

| Gate Scope | Official Verdict | Authorization Boundary |
|---|---|---|
| **Overall Campaign Gate (`REC-04.04` / `R13`)** | **`TECHNICAL GO / AWAITING HUMAN REVIEW`** | All mandatory technical defects (`R01`–`R12`, `A01`–`A13`) are closed on `develop`, every completed technical slice (`REC-00.01`..`REC-04.02`) achieved independent reviewer scores **`9.290/10` to `9.540/10`** (`0` open `P0`/`P1` blockers), and clean-SHA full regression (`6a55f1f`) passed `100%` across all 4 isolated campaigns (`exit 0`). Subject to final independent `Gemini 4 Neon (High)` release-gate sign-off on `REC-04.03`/`REC-04.04`. |
| **Human Audiovisual Sign-Off (`V4-00.06`, `V4-13.11`)** | **`AWAITING_HUMAN_REVIEW`** | Aesthetic/editorial quality is **never** simulated or auto-approved via `POST /approve`. Both rendered pilot MP4s (`67.36s` slice and `309.80s` 25-scene documentary) remain in `AWAITING_APPROVAL` / `WAITING_HUMAN` awaiting real inspection (`>= 9.0/10` across all 6 dimensions in §6) by the human operator. |
| **Merge `develop` → `main` (`42700cb`)** | **`NO-GO` (Blocked Until Operator Approval)** | No automatic merge is permitted (`PROMPT-MASTER.md` §7, `RECOVERY-BACKLOG.md:25`). Requires: (1) independent `Neon High` `APPROVED` (`>= 9.0/10`) on `REC-04.03` & `REC-04.04`, (2) human operator audiovisual score `>= 9.0/10`, and (3) separate explicit merge authorization from the operator. |
| **External YouTube Publication** | **`BLOCKED`** | Enforced unconditionally as 1st guard in `RunPublication` (`STUDIO_PUBLICATION_ENABLED=0` → `PublicationResult.BLOCKED`, `youtube_video_id=None`). |

### Historical Corrigendum to `INT-07-FINAL-REPORT.md`
`INT-07-FINAL-REPORT.md` is preserved in the repository purely as a historical record (with its 26/11/2026 addendum) and **does not represent homologation**. As audited in `REC-00` (`REC-00-AUDIT-AND-PLAN.md`, `031811f`), `INT-07-FINAL-REPORT.md` contained:
1. A commit reference mismatch (claimed `HEAD 8a01c34` while committed in `72438e9`);
2. Unreconciled test arithmetic (`4,416` collected vs `4,389 passed + 10 fixed + 20 skipped = 4,419`) followed by only a `228/228` partial retest rather than a clean full-suite run;
3. Zero real browser E2E runs (`tests/e2e_ux` and `tests/e2e_full` unexecuted); and
4. Ten open `P0`/`P1` runtime/security/integration defects (`R01`–`R11`) in financial safety, media probe/CAS, voice offline validation, `xfade`/video-PiP/multitrack rendering, Studio upload UX, selective QA regeneration, and real observed pilots.

All 13 findings (`R01`–`R13`) have now been resolved and verified with real code, real PostgreSQL/FFmpeg/Piper/Playwright execution, and independent multi-round reviews.

---

## 2. Wave-by-Wave & Task-by-Task Execution and Independent Rubric Table (`REC-00.01`..`REC-04.04`)

> **Rubric Weights (`QUALITY-RUBRIC.md`):** Functional & Integration `25%` | Architecture & Simplicity `20%` | Tests & Regression `20%` | Security, Budget & Reliability `20%` | Evidence & Operations `15%`. Every `VERIFIED` task scored **`>= 9.0/10` in every applicable dimension** and **`>= 9.0/10` weighted mean** without rounding, audited by a separate independent reviewer session (`0` open `P0`/`P1` blockers).

| Task ID | Wave | Prio | Atomic Commit (`develop`) | Executor Model (Real) | Independent Reviewer Model (Real) | Rounds | Dimension Scores `[Func, Arch, Test, Sec, Evid]` | Exact Weighted Mean | Status | Evidence & Independent Review Links |
|---|---|---|---|---|---|---:|---|---:|---|---|
| `REC-00.01` | REC-00 | P0 | `031811f` | `Gemini 4 Neon (High)` | `Gemini 4 Carbon (High)` | 1 | `[9.6, 9.7, 9.2, 9.6, 9.4]` | **9.510 / 10** | `VERIFIED` | [REC-00-AUDIT-AND-PLAN.md](REC-00-AUDIT-AND-PLAN.md), [preflight-and-inventory.md](evidence/rec-00/preflight-and-inventory.md), [independent-review-carbon-high.md](evidence/rec-00/independent-review-carbon-high.md) |
| `REC-00.02` | REC-00 | P0 | `031811f` | `Gemini 4 Neon (High)` | `Gemini 4 Carbon (High)` | 1 | `[9.5, 9.6, 9.5, 9.6, 9.5]` | **9.540 / 10** | `VERIFIED` | [REC-00-AUDIT-AND-PLAN.md](REC-00-AUDIT-AND-PLAN.md), [independent-review-carbon-high.md](evidence/rec-00/independent-review-carbon-high.md) |
| `REC-01.01` | REC-01 | P0 | `d9fd1cd` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 REJ)* | `[9.5, 9.5, 9.5, 9.5, 9.5]` | **9.500 / 10** | `VERIFIED` | [implementation-evidence.md](evidence/rec-01/implementation-evidence.md), [independent-review-neon-high.md](evidence/rec-01/independent-review-neon-high.md) |
| `REC-01.02` | REC-01 | P0 | `d9fd1cd` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 REJ)* | `[9.5, 9.5, 9.5, 9.5, 9.5]` | **9.500 / 10** | `VERIFIED` | [implementation-evidence.md](evidence/rec-01/implementation-evidence.md), [independent-review-neon-high.md](evidence/rec-01/independent-review-neon-high.md) |
| `REC-01.03` | REC-01 | P0 | `d9fd1cd` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 REJ)* | `[9.5, 9.5, 9.5, 9.5, 9.5]` | **9.500 / 10** | `VERIFIED` | [implementation-evidence.md](evidence/rec-01/implementation-evidence.md), [independent-review-neon-high.md](evidence/rec-01/independent-review-neon-high.md) |
| `REC-02.01` | REC-02 | P0 | `ef367fc` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 8.575 REJ)* | `[9.5, 9.5, 9.2, 9.5, 9.5]` | **9.440 / 10** | `VERIFIED` | [rec-02-01-02-av-evidence.md](evidence/rec-02/rec-02-01-02-av-evidence.md), [rec-02-01-02-independent-review-neon-high.md](evidence/rec-02/rec-02-01-02-independent-review-neon-high.md) |
| `REC-02.02` | REC-02 | P1 | `ef367fc` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 8.050 REJ)* | `[9.5, 9.3, 9.5, 9.4, 9.4]` | **9.425 / 10** | `VERIFIED` | [rec-02-01-02-av-evidence.md](evidence/rec-02/rec-02-01-02-av-evidence.md), [rec-02-01-02-independent-review-neon-high.md](evidence/rec-02/rec-02-01-02-independent-review-neon-high.md) |
| `REC-02.03` | REC-02 | P0 | `3ca1f85` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 REJ)* | `[9.5, 9.5, 9.5, 9.5, 9.0]` | **9.425 / 10** | `VERIFIED` | [rec-02-03-04-media-evidence.md](evidence/rec-02/rec-02-03-04-media-evidence.md), [rec-02-03-04-independent-review-neon-high.md](evidence/rec-02/rec-02-03-04-independent-review-neon-high.md) |
| `REC-02.04` | REC-02 | P0 | `3ca1f85` | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 REJ)* | `[9.5, 9.5, 9.5, 9.2, 9.5]` | **9.440 / 10** | `VERIFIED` | [rec-02-03-04-media-evidence.md](evidence/rec-02/rec-02-03-04-media-evidence.md), [rec-02-03-04-independent-review-neon-high.md](evidence/rec-02/rec-02-03-04-independent-review-neon-high.md) |
| `REC-02.05` | REC-02 | P1 | `4ece073` | `Gemini 3.8 Flash (High)` | `Gemini 4 Carbon (High)` | 2 *(R1 8.025 REJ)* | `[9.5, 9.5, 9.5, 9.5, 9.5]` | **9.500 / 10** | `VERIFIED` | [rec-02-05-voice-evidence.md](evidence/rec-02/rec-02-05-voice-evidence.md), [rec-02-05-independent-review-carbon-high.md](evidence/rec-02/rec-02-05-independent-review-carbon-high.md) |
| `REC-03.01` | REC-03 | P1 | `7ded0f5` | `Gemini 3.8 Flash (High)` *(Copilot)* | `Gemini 4 Neon (High)` *(Copilot)* | 3 *(R1 6.85, R2 7.475 REJ)* | `[9.3, 9.2, 9.4, 9.4, 9.1]` | **9.290 / 10** | `VERIFIED` | [rec-03-01-02-ux-browser-evidence.md](evidence/rec-03/rec-03-01-02-ux-browser-evidence.md), [rec-03-01-02-independent-review-neon-high-round3.md](evidence/rec-03/rec-03-01-02-independent-review-neon-high-round3.md) |
| `REC-03.02` | REC-03 | P1 | `7ded0f5` (+ `6a55f1f`) | `Gemini 3.8 Flash (High)` *(Copilot)* | `Gemini 4 Neon (High)` *(Copilot)* | 3 *(R1 6.55, R2 7.75 REJ)* | `[9.5, 9.3, 9.2, 9.5, 9.2]` | **9.355 / 10** | `VERIFIED` | [rec-03-01-02-ux-browser-evidence.md](evidence/rec-03/rec-03-01-02-ux-browser-evidence.md), [rec-03-01-02-independent-review-neon-high-round3.md](evidence/rec-03/rec-03-01-02-independent-review-neon-high-round3.md) |
| `REC-03.03` | REC-03 | P1 | `4fa225b` | `Flash 3.8` → `Gemini 4 Neon (High)` *(Copilot)* | `Gemini 4 Neon (High)` *(Copilot)* | 2 *(R1 3.95 REJ)* | `[9.5, 9.5, 9.5, 9.2, 9.5]` | **9.440 / 10** | `VERIFIED` | [rec-03-03-pipeline-evidence.md](evidence/rec-03/rec-03-03-pipeline-evidence.md), [rec-03-03-independent-review-neon-high-round2.md](evidence/rec-03/rec-03-03-independent-review-neon-high-round2.md) |
| `REC-04.01` | REC-04 | P0 | `5097b98` | `Gemini 4 Neon (High)` *(Copilot)* | `Gemini 4 Neon (High)` *(Copilot)* | 1 | `[9.2, 9.5, 9.3, 9.6, 9.1]` | **9.345 / 10** | `VERIFIED` *(tech)* / `AWAITING_HUMAN_REVIEW` | [rec-04-01-slice-evidence.md](evidence/rec-04/rec-04-01-slice-evidence.md), [manifest.json](evidence/rec-04/rec-04-01/manifest.json), [rec-04-01-independent-review-neon-high.md](evidence/rec-04/rec-04-01-independent-review-neon-high.md) |
| `REC-04.02` | REC-04 | P0 | `a1e3640` *(after `ea07c0c`)* | `Gemini 4 Hydrogen (Medium)` | `Gemini 4 Neon (High)` | 2 *(R1 9.190 REJ)* | `[9.3, 9.4, 9.4, 9.6, 9.3]` | **9.400 / 10** | `VERIFIED` *(tech)* / `AWAITING_HUMAN_REVIEW` | [rec-04-02-documentary-evidence.md](evidence/rec-04/rec-04-02-documentary-evidence.md), [manifest.json](evidence/rec-04/rec-04-02/manifest.json), [rec-04-02-independent-review-neon-high.md](evidence/rec-04/rec-04-02-independent-review-neon-high.md) |
| `REC-04.03` | REC-04 | P0 | `6a55f1f` (+ docs) | `Gemini 4 Carbon (High)` | `Gemini 4 Neon (High)` *(pending)* | 1 | Pending independent `Neon High` review | *Self-eval: 9.50 (non-approving)* | `IMPLEMENTED` *(all 4 suites `exit 0`)* | [rec-04-03-regression-evidence.md](evidence/rec-04/rec-04-03-regression-evidence.md), `evidence/rec-04/rec-04-03/` |
| `REC-04.04` | REC-04 | P0 | Working tree on `6a55f1f` | `Gemini 4 Carbon (High)` | `Gemini 4 Neon (High)` + Operator | 1 | Pending independent `Neon High` + Operator | *Self-eval: 9.50 (non-approving)* | `IMPLEMENTED` *(pending review + human)* | [TRACEABILITY-MATRIX.md](TRACEABILITY-MATRIX.md), [FINAL-REPORT.md](FINAL-REPORT.md) |

- **Wave Means Across All 15 Independently Verified Tasks (`REC-00.01`..`REC-04.02`):**
  - **Wave `REC-00`:** `9.525 / 10` (`9.510`, `9.540`)
  - **Wave `REC-01`:** `9.500 / 10` (`9.500`, `9.500`, `9.500`)
  - **Wave `REC-02`:** `9.446 / 10` (`9.440`, `9.425`, `9.425`, `9.440`, `9.500`)
  - **Wave `REC-03`:** `9.362 / 10` (`9.290`, `9.355`, `9.440`)
  - **Wave `REC-04` (`04.01`–`04.02` technical):** `9.3725 / 10` (`9.345`, `9.400`)
- **Documented Model Routing Deviations (`MODEL-USAGE.md` & `SESSION-HANDOFF.md` §2):** During the intermediate OpenCode window (`REC-03.01`..`REC-04.01`), the operator explicitly authorized `github-copilot/gemini-4-neon` (high) and `github-copilot/gemini-3.8-flash` (high) when the OpenCode `google/*` provider key failed and `Carbon`/`Hydrogen` aliases were absent in OpenCode; executor and reviewer were strictly isolated in separate fresh sessions throughout, and non-Google models were never used.

---

## 3. Quality Gates Reconciliation (`G0`–`G7`)

| Gate | Requirement Summary (`QUALITY-GATES.md`) | Verified Status | Observed Proof & Direct Relative Evidence Links |
|---|---|---|---|
| **G0 — Preflight & Isolation** | Clean git status/SHA, isolated disposable PostgreSQL with cryptographic proof guard, unique ports/storage (`tmpfs`), zero real credentials, `publication_enabled=False` wired, `$0.00` ceiling, DEV/PRD untouched. | **`VERIFIED`** | Disposable `postgres:16-alpine` on `tmpfs` with 64-hex `/budget-test-proof/proof` (`tests/conftest.py:16-53`); isolated `docker-compose.e2e.yml` on `127.0.0.1:8100` (`tmpfs`, torn down via `down -v`); DEV ports `8000`/`5678` and `main` (`42700cb`) untouched. Evidence: [preflight-and-inventory.md](evidence/rec-00/preflight-and-inventory.md), [rec-04-03-regression-evidence.md](evidence/rec-04/rec-04-03-regression-evidence.md). |
| **G1 — Evidence per Requirement** | Exact `file:symbol` → real consumer → persistence/artifact → positive & negative tests → observed output; honest distinction between `VERIFIED`, `DEFERRED`, `AWAITING_HUMAN_REVIEW`; zero silent `P0` deferrals. | **`VERIFIED`** *(pending final `Neon High` sign-off on `REC-04.04`)* | Reconciled across `R01–R13` (`13`), `A01–A13` (`13`), `INT-01.01–07.02` (`21`), `GAI-01–09` (`9`), all `227` real V4 IDs (`180 VERIFIED`, `44 DEFERRED` `P1`/`P2` with risk/owner/basis, `2 AWAITING_HUMAN_REVIEW`, `1 IMPLEMENTED`, `0 P0` deferred), and `REC-00.01–04.04` (`17`). Evidence: [TRACEABILITY-MATRIX.md](TRACEABILITY-MATRIX.md). |
| **G2 — Contracts & Compatibility** | Preserve v1/v2 persisted schemas, legacy data, render cache hashes when behavior unchanged, project/channel isolation, fail-closed unimplemented capabilities, explicit rollback. | **`VERIFIED`** | `test_contracts_snapshot.py` (`3/3`), `test_render_plan_v2_contract.py` (`21/21`), `test_render_golden.py` (`8/8`), `test_schema_docs.py` (`4/4`), `test_architecture.py` (`9/9`); additive migration `0054_paid_operation_external_ref.sql` with verified rollback SQL; `KokoroVoice`, `ElevenLabsVoice`, `image_veo`, and `NotVerifiedSemanticChecker` fail closed. Evidence: [independent-review-neon-high.md](evidence/rec-01/independent-review-neon-high.md), [rec-02-01-02-independent-review-neon-high.md](evidence/rec-02/rec-02-01-02-independent-review-neon-high.md). |
| **G3 — Real Canonical Execution** | Produce real artifacts via canonical Studio path (`routes` + `ProductionCoordinator` + `PlanFfmpegRenderer`) and measure via `ffprobe`/`FfmpegQa`/`ebur128` + pixel/PCM content checks. | **`VERIFIED`** | Real `xfade`/PiP/multitrack MP4s (`REC-02`), real PNG/MP4 probe & render (`REC-02.03–04`), real `67.36s` slice (`REC-04.01`), and real `309.80s` 25-scene documentary (`REC-04.02`) measured directly on disk via `ffprobe`, `ebur128=peak=true`, `blackdetect`, `freezedetect`, `silencedetect`, and RGB frame diffs. Evidence: [rec-04-01-slice-evidence.md](evidence/rec-04/rec-04-01-slice-evidence.md), [rec-04-02-documentary-evidence.md](evidence/rec-04/rec-04-02-documentary-evidence.md). |
| **G4 — Security, Budget & Reliability** | Verifiable license allowlist, fake-MIME/traversal/corrupt/oversized rejection, real CAS/leases/fencing, restart & 2-connection concurrency, pre-retry reconciliation, zero duplicate ledger charges, kill switch `0` token/upload calls. | **`VERIFIED`** | Closed `R01–R03` (`9.50/10`), `R06–R07` (`9.425/9.440`), `R08` (`AssetFile` zero existence oracle + streaming cap `413` + CRLF `400`), and `R10` (`license_block_reason` across `Approve`, `publication_block_reason`, `ClaimPublication`, `RunPublication`; `/direction` CLI-injection `422`). Evidence: [independent-review-neon-high.md](evidence/rec-01/independent-review-neon-high.md), [rec-02-03-04-independent-review-neon-high.md](evidence/rec-02/rec-02-03-04-independent-review-neon-high.md), [rec-03-03-independent-review-neon-high-round2.md](evidence/rec-03/rec-03-03-independent-review-neon-high-round2.md). |
| **G5 — Browser & Node UX** | Execute Node JS & Playwright Chromium in disposable isolated environment (`8100`) across Desktop (`1280x800`), Tablet (`768x1024`), and Mobile (`390x844`): upload/preview/swap/add/reorder/undo/redo/reload/generate-missing/approval & negatives. | **`VERIFIED`** | Host Node (`101 passed` incl. real `STORYBOARD_JS` VM), Isolated Playwright E2E on port `8100` (`27 passed` across `tests/e2e_ux` + `tests/e2e_full`, stack torn down via `down -v`), and Host Playwright UI Contract Modules (`20 passed` across `test_reference_browser.py` + `tests/ve08/`). Evidence: [rec-03-01-02-ux-browser-evidence.md](evidence/rec-03/rec-03-01-02-ux-browser-evidence.md), [rec-04-03-regression-evidence.md](evidence/rec-04/rec-04-03-regression-evidence.md). |
| **G6 — Full Canonical Regression** | Full canonical container suite + host Node + isolated browser E2E on clean final SHA after last functional change; image hash & migrations verified; sanitized logs/JUnit; skips & exclusions reconciled separately without summing overlapping runs. | **`VERIFIED`** *(executed on clean `6a55f1f`; pending final `Neon High` review)* | Clean `HEAD=6a55f1f` (`hash renderer/app = b677160103d832a3`, `49/49` migrations, empty `git status -s`): Container `4510 passed, 26 skipped, 0 failed` (`1063.12s (17m43s)`, `exit 0`); Host Node `101 passed` (`exit 0`); Isolated Browser E2E `27 passed` (`exit 0`); Host Playwright Modules `20 passed` (`exit 0`). Evidence: [rec-04-03-regression-evidence.md](evidence/rec-04/rec-04-03-regression-evidence.md). |
| **G7 — Observed Pilots & Human Review** | `60–90s` vertical slice first, then `5–8min` (`>=25` scenes) documentary via Studio paired with `V4-00`; `economic_local` (`$0.00`), exclusive run dirs, SHA-256 manifests, selective regen savings, kill switch `BLOCKED`, operator human audiovisual review (`>= 9.0/10`). | **`VERIFIED` (Technical) / `AWAITING_HUMAN_REVIEW` (Audiovisual)** | `67.36s` slice (`5097b98`, **9.345/10**) & `309.80s` 25-scene documentary (`a1e3640`, **9.400/10**) verified on disk; human evaluation (`V4-00.06`, `V4-13.11`) strictly pending (§5 & §6). Evidence: [rec-04-01-independent-review-neon-high.md](evidence/rec-04/rec-04-01-independent-review-neon-high.md), [rec-04-02-independent-review-neon-high.md](evidence/rec-04/rec-04-02-independent-review-neon-high.md). |

---

## 4. `REC-04.03` (`R12`) Clean Final-SHA Full Regression Summary (`6a55f1f`)

### 4.1 Stop-and-Remediate Discipline on `a1e3640` → Clean Re-Run on `6a55f1f`
During the initial `REC-04.03` execution on clean `a1e3640`:
- Campaign 1 (Canonical Container: `4510 passed, 26 skipped, 0 failed`, `exit 0`) and Campaign 2 (Host Node/Panel: `101 passed`, `exit 0`) passed `100%`.
- Executing **all 27** isolated Playwright E2E tests (`tests/e2e_ux` + `tests/e2e_full`) and **all 20** host Playwright contract tests (`test_reference_browser.py` + `tests/ve08/`) uncovered **3 stale pre-V4 test expectations/selectors** (`0` product defects; `renderer/` `100%` untouched):
  1. `tests/e2e_ux/test_e2e_journey_workspace.py`: hardcoded 5 V3 tabs, missing `("Direção criativa", "/direcao")` added in `panel_video_nav.py` (`9f300cf`);
  2. `tests/e2e_full/test_journey_piloto.py:107`: pre-V4 `findings == []` rejected non-blocking post-V4-09 `warning`/`info` findings (`render.frozen_frames` on static `placeholder:v4` Short images and `semantic-not-verified`) even though `qa_report` had `0` `blocking` findings (`coverage.status == "verified"` and approval succeeded);
  3. `tests/ve08/test_storyboard_functional.py:33,44,125`: unscoped `.scene textarea` matched the collapsed GAI-02 `<textarea data-f="assisted-prompt">` added in `REC-03.01` (`7ded0f5`) instead of `.scene textarea[data-a="text"]`.
- Following Mandatory Rule #1 (`QUALITY-GATES.md:G6`), execution stopped immediately without touching `REC-04.04`, aligned ONLY those 3 test files (`3 files changed, +9/-5`, `renderer/` untouched), committed atomically as **`6a55f1f296d1d34bad64d2adcaad3bc0eafce011`**, and re-executed **all 4 campaigns from scratch** on the clean `6a55f1f` working tree (`git status -s` empty throughout).

### 4.2 Reconciled Results on Clean Final SHA `6a55f1f` (Separate Campaigns — Never Summed)

| Campaign | Execution Environment | Exact Command Scope | Collected | Passed | Skipped | Failed | Duration | Exit Code | Sanitized Log & JUnit Artifacts |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| **1. Canonical Container Suite** | Docker `faceless-renderer-pytest:test` (`hash renderer/app = b677160103d832a3`, `49/49` migrations) + disposable `postgres:16-alpine` (`tmpfs` + proof guard) | `./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q` | **4,536** | **4,510** | **26** | **0** | `1063.12s (17m43s)` | **`0`** | [canonical-pytest.log](evidence/rec-04/rec-04-03/canonical-pytest.log), [canonical-pytest-junit.xml](evidence/rec-04/rec-04-03/canonical-pytest-junit.xml) |
| **2. Host Node.js / Panel Suite** | macOS Host (`Python 3.11.9`, `Node v26.0.0`) | `pytest` on 8 JS/panel/workflow modules *(incl. all 23 Node tests skipped in Campaign 1)* | **101** | **101** | **0** | **0** | `8.21s` | **`0`** | [host-node.log](evidence/rec-04/rec-04-03/host-node.log), [host-node-junit.xml](evidence/rec-04/rec-04-03/host-node-junit.xml) |
| **3. Isolated Playwright Browser E2E** | Isolated `docker-compose.e2e.yml` (`faceless-e2e-rec0403final`, `127.0.0.1:8100`, `tmpfs`, torn down via `down -v`) + Chromium `1255` | `pytest tests/e2e_ux tests/e2e_full -v -ra` *(the 2 directories excluded via `--ignore` in Campaign 1)* | **27** | **27** | **0** | **0** | `64.26s` | **`0`** | [browser-e2e.log](evidence/rec-04/rec-04-03/browser-e2e.log), [browser-e2e-junit.xml](evidence/rec-04/rec-04-03/browser-e2e-junit.xml) |
| **4. Host Playwright UI Contract Modules** | macOS Host (`PYTHONPATH=renderer`, Chromium `1255`) | `pytest tests/test_reference_browser.py tests/ve08/test_composition_functional.py tests/ve08/test_storyboard_functional.py` *(the 3 Playwright module skips in Campaign 1)* | **20** | **20** | **0** | **0** | `7.48s` | **`0`** | [host-playwright-modules.log](evidence/rec-04/rec-04-03/host-playwright-modules.log), [host-playwright-modules-junit.xml](evidence/rec-04/rec-04-03/host-playwright-modules-junit.xml) |

- **100% Skip & Exclusion Closure:** Every single skip (`23` Node tests + `3` Playwright module-level skips = `26`) and every `--ignore` path (`tests/e2e_ux` [`23`] + `tests/e2e_full` [`4`] = `27`) in Campaign 1 was executed and passed (`0` skips, `0` failures) in Campaigns 2, 3, and 4 on the exact same clean commit `6a55f1f`. Full details and SHA-256 hashes are recorded in [rec-04-03-regression-evidence.md](evidence/rec-04/rec-04-03-regression-evidence.md).

---

## 5. Paired Pilot Comparison Table (`V4-00` Baseline vs `REC-04.01` Slice vs `REC-04.02` Documentary)

| Metric (Measured via `ffprobe` / `FfmpegQa` / `ebur128` / `getrusage`) | `V4-00` Baseline (`run_20261126_132447_198e47cb`) | `REC-04.01` Vertical Slice (`rec04_slice_20261126_213537_4fa225b`) | `REC-04.02` Paired Documentary (`rec04_doc_20261126_233034_ea07c0c`) | Comparison / Gate Verdict |
|---|---:|---:|---:|---|
| **Execution Path** | Standalone `scripts/render_v4_baseline.py` (`PlanFfmpegRenderer` direct) | **Canonical Studio HTTP + `ProductionCoordinator` + `PlanFfmpegRenderer`** | **Canonical Studio HTTP + `ProductionCoordinator` + `PlanFfmpegRenderer`** | Full E2E Studio path proven (`R11`) |
| **Theme / Script Lineage** | *"História da Computação"* (18 scenes) | *"História da Computação"* (5 scenes, PT-BR) | *"A História da Computação: Da Mecânica aos Cérebros de Silício"* (**25 scenes**, PT-BR) | Controlled rebaseline `18 → 25` scenes (`>= 25`, `300–480s`) |
| **Observed Duration (`ffprobe`)** | `345.800 s` (`5m45.8s`) | **`67.360 s`** (`1m07.4s`, target `60–90s`) | **`309.800 s`** (`5m09.8s`, target `300–480s`) | Within exact target windows |
| **Video Stream (`ffprobe`)** | `1920x1080`, `h264` (`yuv420p`), `25/1 fps` | `1920x1080`, `h264` (`yuv420p`), `25/1 fps` (`1,684` frames) | `1920x1080`, `h264` (`yuv420p`), `25/1 fps` (`7,745` frames) | Exact format parity (`16:9` 1080p25) |
| **Audio Stream (`ffprobe`)** | `aac`, `96,000 Hz`, stereo | `aac`, `96,000 Hz`, stereo (`158.6 kbps`) | `aac`, `96,000 Hz`, stereo (`159.2 kbps`) | Exact audio codec parity |
| **File Size & MP4 SHA-256** | `48886a20...` | `53,226,343 B` (`50.76 MiB`) — `088c11300a2b7f67...ea92fcc3` | `232,080,906 B` (`221.33 MiB`) — `62eb3b8e335cac16...554daa9` | Verified on disk (gitignored) |
| **Voice Provider (Offline)** | `piper:pt_BR-faber-medium` | `piper:pt_BR-faber-medium` (`piper-tts==1.8.0`) | `piper:pt_BR-faber-medium` (`piper-tts==1.8.0`) | `100%` real local neural speech |
| **Visual Capabilities Exercised** | Static generated cards + Ken Burns | Imported 1080p PNGs + 1080p MP4 + PNG badge overlay + animated MP4 PiP + Ken Burns + Studio-generated scene | 17 imported 1080p PNGs (`CC0-1.0`) + 3 moving 1080p MP4 B-rolls (`PRE-1` single ASS) + 5 local Studio scenes + 2 PNG overlays + 1 safe-zone MP4 PiP (`P2-1`) + `V2-F7` JPEG thumbnail (`1280x720`, `67,870 B`) | Major visual richness upgrade (`frozen_ratio` `-66.9%` relative) |
| **Integrated Loudness (`ebur128`)** | `-15.6 LUFS` | **`-16.1 LUFS`** | **`-16.1 LUFS`** | Target `-16.0 ± 1.5 LUFS` hit |
| **True Peak (`ebur128=peak=true`)** | `-1.3 dBTP` | **`-1.4 dBTP`** | **`-1.9 dBTP`** | Strictly `<= -1.0 dBTP` (`0` clipping) |
| **`black_ratio` / `silence_ratio`** | `0.00%` / `0.00%` | **`0.00%` / `0.00%`** | **`0.00%` / `0.00%`** | Zero black frames or dead air |
| **`frozen_ratio` (`freezedetect`)** | `0.4937` (`49.37%`) | **`0.1455`** (`14.55%`) | **`0.1632`** (`16.32%`) | **`-0.3305` improvement** (`< 20%` QA threshold) |
| **Audio–Caption Sync Drift** | Not persisted in V4-00 JSON | `render.caption_sync` verified (`37` cues, `0` warnings) | **`336 ms`** vs speech end (`164` cues, limit `<= 500 ms`) | Verified within `500 ms` threshold |
| **Run #1 Production Wall Time** | `126.28 s` (renderer only, 18 scenes) | **`26.778 s`** (full Studio DAG + QA, 5 scenes) | **`141.841 s`** (full Studio DAG + PG + Piper + FFmpeg + QA, 25 scenes) | Full 7-stage Studio pipeline in `2.36 min` for `5.16 min` video (`0.46x` realtime) |
| **Run #2 Selective Regen (1 Scene Edited)** | N/A | **`15.391 s`** (**`-11.386 s` / `-42.5%`**, `4/4` nar + `10/10` vis reused) | **`60.409 s`** (**`-81.433 s` / `-57.41%`**, `24/24` nar + `66/66` vis reused) | Proven persistent PostgreSQL + disk segment cache |
| **CPU Total (`user + sys`, parent + children)** | `675.804 s` (1 run) | `211.770 s` (Run #1 + Run #2 + QA) | `1,027.749 s` (Run #1 + Run #2 + QA + frame probes) | Consistent multi-core `libx264` scaling |
| **Peak RSS (`getrusage` Linux caveat)** | Parent `1,346.5 MB` / Child `1,544.0 MB` | Parent `889.7 MB` / Child `1,499.1 MB` | Parent `1,402.1 MB` / Child `1,618.5 MB` *(theoretical upper bound `3,020.6 MB`)* | Stable memory footprint across 25 scenes |
| **External API Cost & Cost / Minute** | `$0.00` (`$0.00/min`) | **`$0.00`** (`$0.00 / 1.123 min = $0.00/min`) | **`$0.00`** (`$0.00 / 5.163 min = $0.00/min`) | Confirmed in `usage_ledger` & `/cost-breakdown` |
| **Kill Switch & Approval State** | Script output only | `BLOCKED` / `AWAITING_APPROVAL` (`auto_approved=false`) | `BLOCKED` / `AWAITING_APPROVAL` (`auto_approved=false`) | Zero publication, zero fake human approval |

---

## 6. Operator Human Audiovisual Evaluation Guide (`V4-00.06` & `V4-13.11`)

Per `PROMPT-MASTER.md` §7 and `QUALITY-RUBRIC.md:28`, **no AI agent may score aesthetic/editorial quality on behalf of the human operator**. Before authorizing any merge to `main`, run the commands below on macOS from `/Users/rodrigomendes/youtube-faceless-starter`:

### 6.1 Verify SHA-256 Integrity & Open Both Preserved MP4s on macOS

```bash
# 1. Verify SHA-256 integrity of both preserved MP4 artifacts
shasum -a 256 \
  storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4 \
  storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4
# Expected:
# 088c11300a2b7f6737b13d2095741d3313bd27a487ff86e6876e2634ea92fcc3  .../rec04_01_vertical_slice.mp4
# 62eb3b8e335cac167bce65e5a0e4c6c9a6560cc4cd03f018a7418e82f554daa9  .../rec04_02_documentary.mp4

# 2. Watch Pilot #1 — REC-04.01 Vertical Slice (67.36s, 1080p25, 5 scenes)
open storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4

# 3. Watch Pilot #2 — REC-04.02 Paired Documentary (309.80s / 5m09.8s, 1080p25, 25 scenes)
open storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4

# (Optional) Watch V4-00 Reference Baseline for side-by-side comparison
open storage/output/runs/run_20261126_132447_198e47cb/v4_piloto_5min.mp4
```

### 6.2 Mandatory Human Audiovisual Rubric (`>= 9.0 / 10` Required in Every Dimension)

| # | Audiovisual Dimension (`QUALITY-RUBRIC.md:28`) | What to Inspect in Player | Minimum Gate | `REC-04.01` Slice (67.36s) Operator Score | `REC-04.02` Documentary (309.80s) Operator Score |
|---:|---|---|---:|---|---|
| 1 | **Speech Intelligibility (`Inteligibilidade`)** | Clarity, naturalness, pronunciation of PT-BR narration (`piper:pt_BR-faber-medium`), absence of robotic artifacts or cut-offs across scene boundaries. | `>= 9.0 / 10` | `[ PENDING HUMAN ]` | `[ PENDING HUMAN ]` |
| 2 | **Visual Composition (`Composição`)** | Framing, safe-zones of top-left HUD (`"Ilustração gerada por IA"` / `"FATO"`), right/left PNG & MP4 PiP overlays (`P2-1` non-overlap verified in `REC-04.02` Scene 1), absence of visual clutter. | `>= 9.0 / 10` | `[ PENDING HUMAN ]` *(note P2-1 fixed in REC-04.02)* | `[ PENDING HUMAN ]` |
| 3 | **Editorial Pacing & Rhythm (`Ritmo`)** | Scene cadence (~12–14s/scene), breathing room (`TAIL_S`), visual movement (Ken Burns + moving MP4 B-rolls), engagement across 5+ minutes. | `>= 9.0 / 10` | `[ PENDING HUMAN ]` | `[ PENDING HUMAN ]` |
| 4 | **Media Relevance (`Relevância da Mídia`)** | Coherence between spoken historical milestones and visual cards/B-rolls/overlays; clean selective regeneration transition on edited Scene 3 (slice) and Scene 15 (documentary). | `>= 9.0 / 10` | `[ PENDING HUMAN ]` | `[ PENDING HUMAN ]` |
| 5 | **Audio Mix & Loudness (`Áudio`)** | Balance between voice and ducked background music bed (`-16.1 LUFS`, `-1.4`/`-1.9 dBTP`), smooth fades, zero clipping, clicks, or dead silence. | `>= 9.0 / 10` | `[ PENDING HUMAN ]` | `[ PENDING HUMAN ]` |
| 6 | **Captions & Sync (`Legenda`)** | Readability, contrast, bottom safe-area placement, active-word ASS karaoke highlight timing, single clean subtitle layer (`PRE-1` fixed in `REC-04.02`). | `>= 9.0 / 10` | `[ PENDING HUMAN ]` *(note PRE-1 fixed in REC-04.02)* | `[ PENDING HUMAN ]` |

---

## 7. Formal `DEFERRED` & Non-Blocking `P2` Register Summary

All `44` `DEFERRED` original V4 activities (`0` `P0`s; exclusively `P1`/`P2`) and `6` `DEFERRED` optional GAI items (`GAI-03`..`GAI-08`) are itemized with explicit **Risk, Owner, Reason, and Scope Basis** in [TRACEABILITY-MATRIX.md §6](TRACEABILITY-MATRIX.md):

1. **Canonical Renderer Capabilities Deferred at Studio HTTP / V3 UI Layer (`P1`, Low Risk, Owner: Operator):**
   - **3+ Track Multitrack Audio (`V4-03.02`, `03.15`, `03.16`, `10.06`):** `MultitrackAudioPlan` + `AudioCatalog` + `verify_audio_licenses` are `VERIFIED` in `PlanFfmpegRenderer` (`REC-02.02` `ef367fc`); Studio HTTP runs 2-track voice+music ducking while HTTP/UI CRUD for extra ambience/SFX tracks is deferred.
   - **Inter-Shot `xfade` HTTP Exposure (`V4-10.09`):** Real FFmpeg `tpad`+`xfade` (`crossfade`, `slide_left`/`right`, `wipe_left`/`right`) is `VERIFIED` in `PlanFfmpegRenderer` (`REC-02.01` `ef367fc`); `visual_style.TRANSITION_KINDS` conservatively exposes `none`/`fade` at HTTP until multi-shot UI duration guards are added.
   - **Interactive Layer-Canvas UI (`V4-10.07`):** Trim UI (`7ded0f5`) and `POST /scenes/{sid}/assets` (`role="overlay"`, `5097b98`/`a1e3640`) are `VERIFIED`; visual canvas SPA deferred per `PROMPT-MASTER.md` §7.
2. **Unused Legacy In-Memory Services & Uncalled Domain Helpers (`P1`, `0` Production Callers, Low Risk, Owner: Operator):**
   - `application/render_engine.py`, `application/asset_registry.py`, and `application/studio_workbench.py` have `0` callers in `renderer/app/` (canonical Postgres/FFmpeg equivalents are wired and `VERIFIED`), retained intact until a post-V4 cleanup slice retires them alongside `tests/test_v4_{render_engine,asset_management,studio_ux}.py`.
   - Uncalled domain/composition helpers (`voice_catalog`, `voice_preprocessing`, `voice_audio`, `audio_dsp` PCM limiter, `motion_effects` `PostProcessingEffects`/`ColorGrading`/`LowerThirdGraphic`/`InfographicOverlay`, per-scene `SceneCreativeDirection`/`ShotIntent`, `render_hardware`) are honestly classified `DEFERRED` (`MODEL_ONLY`) rather than claimed as `VERIFIED`.
3. **Optional Paid APIs, Profiles & External Engines (`P1 opt.`/`P2 opt.`, Zero Financial Risk, Owner: Operator):**
   - Paid cloud APIs (`GAI-03`..`GAI-06`, `GAI-08`, `V4-05.15`, `V4-09.10–11`), Google Drive (`GAI-07`, `V4-11.14`), `balanced_local` (`V4-13.03` — `BLOCKED_LOCAL_PAID_DEPENDENCY`), `premium` & 15–20min pilot (`V4-13.04`), 2-voice offline comparison (`V4-02.15`, `V4-13.05` — 1 offline voice shipped; Kokoro fail-closed), external engines (`ComfyUI`, `Freesound`, `Remotion`, `Blender`, `WhisperX`, `VideoToolbox`, second renderer), and cloud CI/CD (`V4-12.14`) are deferred per `PROMPT-MASTER.md` §6–§7 (`$0.00` ceiling, no CI/CD).
4. **Non-Blocking `P2` Polish Register (`SESSION-HANDOFF.md` §6):**
   - `P2-1` (left PiP HUD safe-zone) and `P2-4` (`piper-tts==1.8.0` version capture) from `REC-04.01` were **resolved** in `REC-04.02` (`a1e3640`).
   - Preexisting `PRE-1` (double-burned Pillow+ASS subtitles) was **resolved** for all Studio (`has_pacing=True`) and video-base plans in `a1e3640` (with residual `P2-C` preserving legacy golden hashes on synthetic `has_pacing=False` image-only `v2` plans).
   - Remaining non-blocking `P2` polish items (`ai-generated:` slug regex tightening in `domain/asset_registry.py`, intentional `scene_repair=None` under `$0.00` in `wiring.py`, 2-step trim transaction / `GetSceneTiming` narrowing / optional FK indexes from `REC-03.01–02`, and synthetic thumbnail palette index modulo in `test_rec_04_documentary.py`) are documented in [TRACEABILITY-MATRIX.md §6.4](TRACEABILITY-MATRIX.md).

---

## 8. Financial Safety (`$0.00`), Protected `main` Proof & Rollback Guide

### 8.1 `$0.00` External API Spend & Kill Switch Proof
- **Observed External API Spend Across Entire Campaign (`REC-00`..`REC-04.04`):** **`$0.00` USD** (`MODEL-USAGE.md`, `usage_ledger`, and `GET /studio/videos/{id}/cost-breakdown` in `REC-04.01` & `REC-04.02`).
- **Active Runtime Guards:** `PaidOperationGuard` + `PostgresPaidOperationRepository` (`pg_advisory_xact_lock(726002)`), `max_cost_per_video_usd=0.0`, `max_cost_per_month_usd=0.0`, `ElevenLabsVoice` (`validated=False`), `image_veo` (`validated=False`), `KokoroVoice` (`offline_environment_guard()`), `NotVerifiedSemanticChecker` (`not_verified`), and `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`).

### 8.2 Protected `main` Branch Proof
- `git rev-parse main` == **`42700cb331165a68455173a91c463d4733292cfd`** (identical to preflight reading in `REC-00` `preflight-and-inventory.md`; `0` commits, `0` merges, `0` pushes on `main`).

### 8.3 Atomic Rollback Guide (`develop`)
Every recovery wave was committed atomically on `develop` above reopening base `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd`:
- **`REC-04.03` browser test alignments (`6a55f1f`):** `git revert 6a55f1f` (test-only commit; `0` production/DB impact).
- **`REC-04.02` documentary & `P2-1`/`PRE-1`/`facts.py` (`a1e3640`):** `git revert a1e3640` (`0` DB migrations).
- **`REC-04.01` vertical slice & HTTP overlay wiring (`5097b98`):** `git revert 5097b98` (`0` DB migrations; legacy render cache hashes untouched).
- **`REC-03.03` pipeline integration (`4fa225b`):** `git revert 4fa225b` (`0` DB migrations).
- **`REC-03.01–02` Studio upload/assisted UX (`7ded0f5`):** `git revert 7ded0f5` (`0` DB migrations).
- **`REC-02.03–04` media probe/dedup/CAS (`3ca1f85`):** `git revert 3ca1f85` (`0` DB migrations).
- **`REC-02.01–02` `xfade`/PiP/multitrack/dBTP (`ef367fc`):** `git revert ef367fc` (`0` DB migrations).
- **`REC-02.05` voice sanitation (`4ece073`):** `git revert 4ece073` (`0` DB migrations).
- **`REC-01.01–03` financial safety & migration `0054` (`d9fd1cd`):** `git revert d9fd1cd` + non-destructive SQL rollback documented in `renderer/app/studio/adapters/postgres/migrations/0054_paid_operation_external_ref.sql`:
  ```sql
  ALTER TABLE studio.paid_operations
    DROP COLUMN IF EXISTS external_reference_id,
    DROP COLUMN IF EXISTS submitted_at;
  DELETE FROM studio.schema_migrations
   WHERE version = '0054_paid_operation_external_ref';
  ```

## Próxima campanha — Product Completion (26/11/2026)
A revisão externa de 2e8b153 identificou P1 de integridade da edição e 44 V4 adiadas. A nova entrada para execução técnica autorizada é [product-completion/MASTER-PROMPT.md](product-completion/MASTER-PROMPT.md), com 27 tarefas, mapeamento de todos 44 IDs e 6 GAI, rubrica >=9, gates reais e review independente. REC permanece histórico; não repetir REC integralmente. Não aceitar adiamentos em nome do operador, não publicar, não gastar, não fazer merge. O GO técnico anterior não equivale a V4 completa ou avaliação audiovisual humana.
