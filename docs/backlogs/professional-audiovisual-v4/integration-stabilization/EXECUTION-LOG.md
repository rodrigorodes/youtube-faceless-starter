# EXECUTION-LOG — V4 Integration & Stabilization Recovery

Chronological audit trail per `PROMPT-MASTER.md` §5. Every entry records task IDs, base/HEAD SHA, real model, commands/exit codes, diff scope, evidence paths, cost, rubric status, and rollback.

---

## Entry 001 — `REC-00.01` & `REC-00.02` (Audit, Inventory, Traceability Matrix & Test-First Plan)

- **Timestamp (UTC):** `2026-11-26T13:55Z–14:10Z`
- **Task IDs:** `REC-00.01`, `REC-00.02` (reconciles `R01–R13`, `A01–A13`, `INT-01.01–INT-07.02`, `GAI-01–GAI-09`, all 227 real `V4-00.01–V4-13.14` IDs)
- **Git Base / HEAD:** `develop` `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd` (parent `72438e9ea215bbec12bd350d8c2606ca62bc7d94`; `main` observed at `42700cb331165a68455173a91c463d4733292cfd`, untouched)
- **Executor Model:** `Gemini 4 Neon (High)` (`rec00-auditor`)
- **Independent Reviewer Assigned:** `Gemini 4 Carbon (High)` (`rec00-reviewer`)
- **Diff Scope:** Documentation artifacts ONLY under `docs/backlogs/professional-audiovisual-v4/integration-stabilization/`:
  - `TRACEABILITY-MATRIX.md`
  - `REC-00-AUDIT-AND-PLAN.md`
  - `evidence/rec-00/preflight-and-inventory.md`
  - `EXECUTION-STATE.md`
  - `EXECUTION-LOG.md`
  - `MODEL-USAGE.md`
  - Zero edits to `renderer/`, `tests/`, `scripts/`, `contracts/`, root config, or `evidence/rec-00/independent-review-carbon-high.md`.
- **Commands & Exit Codes (Read-Only):**
  1. Git branch/SHA/diff inspection (`git rev-parse`, `git status`, `git diff --shortstat`) → exit `0`
  2. Host runtime check (`python3`, `node v26.0.0`, `npm 11.12.1`, `docker 29.1.3`, `ffmpeg 9.1`, `playwright` + `chromium-1255`) → exit `0` (`piper` on host exit `127`, confirmed in container)
  3. Container runtime & tree alignment check (`faceless-renderer-pytest:test` ID `cbeba9e7b44c`, `HOST_TREE=IMAGE_TREE=02efa18bc76d3e9d`, `HOST_MIG=IMAGE_MIG=48`, Python `3.12.16`, FFmpeg `7.1.5`, Piper `/opt/voices/pt_BR-faber-medium.onnx`, `kokoro` spec `None`, `node` absent in container) → exit `0`
  4. Read-only port check (`lsof` 8000/5678 listening on dev stack — untouched) → exit `0`
  5. Baseline artifact inventory (`storage/output/` 16 files with sizes & SHA-256) → exit `0`
  6. AST/call-site tracing across `renderer/app/` + 48 SQL migration inspection + 227 V4 activity ID extraction → exit `0`
  7. Container read-only test collection (`pytest tests --ignore=tests/e2e_full --ignore=tests/e2e_ux --collect-only -q`) → `4,416 tests collected`, exit `0`
  8. Host read-only browser E2E collection (`pytest tests/e2e_ux tests/e2e_full --collect-only -q`) → `26 tests collected`, exit `0`
- **API Cost:** `$0.00` | **Compute Cost:** Local macOS host + read-only Docker container queries
- **Key Findings Confirmed by Code:**
  - `R01`–`R13` all verified with exact `file:line` citations and consumer tracing.
  - Existing transactional financial architecture (`PaidOperationGuard`, `PostgresPaidOperationRepository`, `pg_advisory_xact_lock(726002)`, `budget_reservations`, `paid_operations`, `usage_ledger`, `channel_budgets`, `ProductionCoordinator`, `LeaseHeartbeat`) fully inventoried so REC-01 reuses it and removes unsafe `PostgresOperationStore` & duplicate `ResilientStageExecutor`.
  - Node `v26.0.0` + Playwright Chromium `1255` confirmed present on host, unblocking real browser E2E against isolated port `8100`.
  - `main` confirmed merged at `42700cb` (`be0c463` + `72438e9`); documented transparently and strictly untouched.
  - `INT-07-FINAL-REPORT.md` 4416 vs 4389+10+20=4419 discrepancy, 228/228 partial retest, and `8a01c34` vs `72438e9` SHA mismatch documented via traceable corrigendum.
- **Status:** `IMPLEMENTED` — Pending independent review by `Gemini 4 Carbon (High)` (`evidence/rec-00/independent-review-carbon-high.md`).
- **Executor Self-Assessment (Non-Approving):** `9.50/10` (see `REC-00-AUDIT-AND-PLAN.md` §7).
- **Rollback:** Remove the 6 newly created documentation files under `docs/backlogs/professional-audiovisual-v4/integration-stabilization/` (no code or schema changes).
- **Next Item:** Independent review by `@rec00-reviewer`; upon `VERIFIED` + coordinator commit, proceed to `REC-01.01`.


---

## Entry 002 — `REC-00` Independent Review Verdict & Gate Closure

- **Timestamp (UTC):** `2026-11-26T14:21Z`
- **Task IDs:** `REC-00.01`, `REC-00.02`
- **SHA Reviewed:** `develop` `5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd`
- **Independent Reviewer:** `Gemini 4 Carbon (High)` (`rec00-reviewer`)
- **Review Artifact:** `evidence/rec-00/independent-review-carbon-high.md` (sha256 `720d3279e2028fb705ad0bc18cf679a1ec8e857adbfe305a92c6f93c41175341`)
- **Scores (`QUALITY-RUBRIC.md`):**
  - `REC-00.01`: **9.51 / 10** (Functional `9.6`, Architecture `9.7`, Tests `9.2`, Security/Budget/Reliability `9.6`, Evidence/Ops `9.4`; min `9.2 >= 9.0`)
  - `REC-00.02`: **9.54 / 10** (Functional `9.5`, Architecture `9.6`, Tests `9.5`, Security/Budget/Reliability `9.6`, Evidence/Ops `9.5`; min `9.5 >= 9.0`)
  - Wave Mean: **9.525 / 10** | Open P0/P1 Blockers: **0** (3 minor P2 notes carried forward to `REC-01`..`REC-04`).
- **Decision:** **APPROVED (`VERIFIED`)** — Atomic commit on `develop` authorized; proceed to Wave `REC-01` (`REC-01.01`..`REC-01.03`) with `Gemini 4 Hydrogen (Medium)` executor + `Gemini 4 Neon (High)` mandatory reviewer.
- **Observed Quota Reading:** `43%` remaining (resets `2026-11-26T15:00:59Z`) | **External API Cost:** `$0.00`.


---

## Entry 003 — Wave `REC-01` (`REC-01.01`, `REC-01.02`, `REC-01.03`) Implementation, Round 1 Rejection & Round 2 Approval

- **Timestamp (UTC):** `2026-11-26T14:24Z–14:50Z`
- **Task IDs:** `REC-01.01`, `REC-01.02`, `REC-01.03` (closes `R01`, `R02`, `R03`, `A08`/`A11`, `INT-04.03`, `GAI-09` minimum financial safety)
- **Base HEAD:** `develop` `031811f420ea74376f9a76ad461437b40db76405` (`hash renderer/app: d95e281af8d0ab89`, 49 migrations)
- **Executor Model:** `Gemini 4 Hydrogen (Medium)` (`rec01-dev`) — 2 rounds (Round 1 implementation + Round 2 fixes for 3 P1/P2 findings)
- **Independent Reviewer Model:** `Gemini 4 Neon (High)` (`rec01-reviewer`)
- **Diff Summary:**
  - Removed unsafe `renderer/app/studio/adapters/postgres/operation_store.py` (`SELECT id FROM studio.videos LIMIT 1`, hardcoded `1000/100`).
  - Added additive migration `0054_paid_operation_external_ref.sql` (`external_reference_id`, `submitted_at`, fixed rollback SQL `version = '0054_paid_operation_external_ref'`), regenerated `docs/schema/studio.sql` & `docs/22-modelo-de-dados.md`.
  - Updated `budget_repo.py`, `budget.py`, `lease_heartbeat.py` (`revoke()`), `production.py` (cooperative `StageContext.ensure_active`, `stage_timeouts`, pre-retry reconciliation with cross-month `stale_reservation` + DB state re-check), `resilience.py` (removed duplicate `ResilientStageExecutor`/`InMemoryOperationStore`/`OperationReconciler`/`mock_duration_seconds`), `domain/resilience.py` (attempt-free logical key), `wiring.py`.
  - Added `tests/test_rec_01_financial_safety.py`, updated `tests/test_int_04_pipeline.py`, `tests/test_v4_reliability_scale.py`, `tests/test_db.py`.
- **Verification Results:**
  - Executor full REC-01 run (`./scripts/test-container.sh` 16 suites): **302 passed**, exit code `0`.
  - Independent Neon High reviewer run (`./scripts/test-container.sh` 9 focused suites): **166 passed in 86.22s**, exit code `0`.
- **Independent Rubric Scores (`evidence/rec-01/independent-review-neon-high.md`):**
  - `REC-01.01`: **9.50 / 10** (all 5 dims `9.5`) — **APPROVED (`VERIFIED`)**
  - `REC-01.02`: **9.50 / 10** (all 5 dims `9.5`) — **APPROVED (`VERIFIED`)**
  - `REC-01.03`: **9.50 / 10** (all 5 dims `9.5`) — **APPROVED (`VERIFIED`)**
- **Observed Quota Reading:** `21%` remaining (resets `2026-11-26T15:00:59Z`) | **External API Cost:** `$0.00` | **Publication Kill Switch:** `BLOCKED` verified.
- **Rollback:** `git revert <rec-01-sha>` + SQL rollback in `0054_paid_operation_external_ref.sql` (`ALTER TABLE studio.paid_operations DROP COLUMN IF EXISTS external_reference_id, DROP COLUMN IF EXISTS submitted_at; DELETE FROM studio.schema_migrations WHERE version = '0054_paid_operation_external_ref';`).
- **Next Item:** Wave `REC-02`, starting with `REC-02.05` (`Flash 3.8` executor + `Carbon High` independent reviewer).


---

## Entry 004 — `REC-02.05` (`R09` Voice Sanitation) Implementation, Round 1 Rejection & Round 2 Approval

- **Timestamp (UTC):** `2026-11-26T14:53Z–15:26Z`
- **Task IDs:** `REC-02.05` (closes `R09`, `A01`, `A02`, `INT-02.01`, `INT-02.02`)
- **Base HEAD:** `develop` `d9fd1cd2f731de138070394718a2f2b733bf49cf` (`hash renderer/app: 72f8c9da952644d3`, 49 migrations)
- **Executor Model:** `Gemini 3.8 Flash (High)` (`rec02-voice`) — 2 rounds (Round 1 impl + Round 2 remediation of 4 P1 findings)
- **Independent Reviewer Model:** `Gemini 4 Carbon (High)` (`rec02-voice-rev`)
- **Verification Results:**
  - Independent container run (6 canonical suites): **105 passed in 12.05s**, exit code `0`, `0` skips.
  - Adjacent 4 suites (`test_v4_provider_extensibility.py`, `test_panel_domain.py`, `test_composition.py`, `test_tts_calibration.py`): **67 passed in 29.85s**, exit code `0` (**172/172 total passed**).
- **Independent Rubric Score (`evidence/rec-02/rec-02-05-independent-review-carbon-high.md`):**
  - `REC-02.05`: **9.50 / 10** (all 5 dims `9.5`) — **APPROVED (`VERIFIED`)**
- **Observed Quota Reading:** Window 2 `74%` remaining (resets `2026-11-26T20:00:59Z`) | **External API Cost:** `$0.00`.
- **Rollback:** `git revert <rec-02-05-sha>`.
- **Next Item:** `REC-02.01` & `REC-02.02` (`Hydrogen Medium` executor + `Neon High` independent reviewer).


---

## Entry 005 — `REC-02.01` & `REC-02.02` (`R04`, `R05`) Implementation, Round 1 Rejection & Round 2 Approval

- **Timestamp (UTC):** `2026-11-26T15:28Z–15:56Z`
- **Task IDs:** `REC-02.01`, `REC-02.02` (closes `R04`, `R05`, `A03`, `A04`, `A06`, `INT-03.01`–`04`)
- **Base HEAD:** `develop` `4ece073164251d0dfb6f6b01bbf4ae787e82fc55` (`hash renderer/app: 357fa45cf4168927`, 49 migrations)
- **Executor Model:** `Gemini 4 Hydrogen (Medium)` (`rec02-av`) — 2 rounds (Round 1 impl + Round 2 fixes for 4 P1 findings)
- **Independent Reviewer Model:** `Gemini 4 Neon (High)` (`rec02-av-rev`)
- **Verification Results:**
  - Independent container run (13 suites): **`164 passed in 42.97s`**, exit code `0`, `0` relaxed assertions, real FFmpeg `xfade` blended pixel proof, moving PiP video proof, real `ebur128` dBTP <= -1.0, observable > 1.5 dB ducking proof, stereo R-channel preservation, multitrack cache isolation.
- **Independent Rubric Scores (`evidence/rec-02/rec-02-01-02-independent-review-neon-high.md`):**
  - `REC-02.01`: **9.440 / 10** (`9.5 / 9.5 / 9.2 / 9.5 / 9.5`) — **APPROVED (`VERIFIED`)**
  - `REC-02.02`: **9.425 / 10** (`9.5 / 9.3 / 9.5 / 9.4 / 9.4`) — **APPROVED (`VERIFIED`)**
- **Observed Quota Reading:** Window 2 `43%` remaining (resets `2026-11-26T20:00:59Z`) | **External API Cost:** `$0.00`.
- **Rollback:** `git revert <rec-02-01-02-sha>`.
- **Next Item:** `REC-02.03` & `REC-02.04` (`Hydrogen Medium` executor + `Neon High` independent reviewer).


---

## Entry 006 — `REC-02.03` & `REC-02.04` (`R06`, `R07`) Implementation, Round 1 Rejection & Round 2 Approval (Wave `REC-02` Complete)

- **Timestamp (UTC):** `2026-11-26T15:58Z–16:16Z`
- **Task IDs:** `REC-02.03`, `REC-02.04` (closes `R06`, `R07`, `A10`, `A12`, core `GAI-01` ingest/dedup/CAS; routes/preview in `REC-03.01`)
- **Base HEAD:** `develop` `ef367fc66b9b888f7ef7fec78fd8e48991c41bad` (`hash renderer/app: 10e8fdb9d4403e36`, 49 migrations)
- **Executor Model:** `Gemini 4 Hydrogen (Medium)` (`rec02-media`) — 2 rounds (Round 1 impl + Round 2 fixes for 5 P1 findings)
- **Independent Reviewer Model:** `Gemini 4 Neon (High)` (`rec02-media-rev`)
- **Verification Results:**
  - Independent container run (11 suites): **`141 passed in 19.63s`**, exit code `0`, zero relaxed assertions, `test_architecture.py` `9/9`.
- **Independent Rubric Scores (`evidence/rec-02/rec-02-03-04-independent-review-neon-high.md`):**
  - `REC-02.03`: **9.425 / 10** (`9.5 / 9.5 / 9.5 / 9.5 / 9.0`) — **APPROVED (`VERIFIED`)**
  - `REC-02.04`: **9.440 / 10** (`9.5 / 9.5 / 9.5 / 9.2 / 9.5`) — **APPROVED (`VERIFIED`)**
- **Wave `REC-02` Complete:** All 5 tasks (`REC-02.01`..`REC-02.05`) `VERIFIED` with min score `9.425/10`.
- **Observed Quota Reading:** Window 2 `24%` remaining (resets `2026-11-26T20:00:59Z`) | **External API Cost:** `$0.00`.
- **Rollback:** `git revert <rec-02-03-04-sha>`.
- **Next Item:** Wave `REC-03`, starting with `REC-03.01–02` (`Flash 3.8` executor + `Carbon High` reviewer, with quota reserve monitoring at `15%`).


---

## Entry 007 — `REC-03.01` & `REC-03.02` Implemented + Safe Quota Reserve Checkpoint (`10%`)

- **Timestamp (UTC):** `2026-11-26T16:18Z–16:55Z`
- **Task IDs:** `REC-03.01`, `REC-03.02` (addresses `R08`, `A09`, `GAI-01` routes/preview, `GAI-02` assisted mode, `G5` browser UX)
- **Base HEAD:** `develop` `3ca1f8512eb4681b97c4e5ecf3ee9ba61fae95b8` (working tree uncommitted, pending independent review)
- **Executor Model:** `Gemini 3.8 Flash (High)` (`rec03-ux`)
- **Diff Scope (Uncommitted):**
  - `renderer/app/studio/api/routes.py`
  - `renderer/app/studio/api/panel_video_workspace.py`
  - `renderer/app/studio/api/panel_video_storyboard_js.py`
  - `tests/test_rec_03_studio_routes.py`
  - `tests/e2e_ux/test_rec_03_studio_browser.py`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-03/rec-03-01-02-ux-browser-evidence.md`
- **Observed Executor Verification:**
  - Host Node JS tests: **95 passed**, exit code `0`.
  - Isolated Playwright E2E (`tests/e2e_ux/test_rec_03_studio_browser.py`, port `8100`, `tmpfs`, Desktop `1280x800` + Mobile `390x844`, stack torn down): **1 passed in 9.83s**, exit code `0`.
  - Container API/security/architecture tests: **74 passed in 20.77s**, exit code `0`.
- **Status:** `IMPLEMENTED` — **NOT committed / NOT `VERIFIED` yet** (independent `Gemini 4 Carbon (High)` review mandatory before commit).
- **Checkpoint Trigger:** Observed Google quota reached **`10%`** remaining (5-hour reserve threshold per `PROMPT-MASTER.md` §6; resets `2026-11-26T20:00:59Z`). Saved clean checkpoint without overage and without skipping independent review.
- **External API Cost:** `$0.00` | **`main` SHA:** `42700cb` untouched | **Publication Kill Switch:** `BLOCKED`.

## Resume attempt — BLOCKED_REVIEW (2026-11-26, sessão OpenCode)
- Ação: tentativa de despachar review independente de `REC-03.01–02` via subagent `google/gemini-4-neon#high` (substituto de `Carbon High`, ausente do catálogo; `Hydrogen` também ausente).
- Resultado real: `API key not valid. Please pass a valid API key.` Repetido com `google/gemini-3.8-flash#high` (teste trivial) — falha idêntica, ou seja, credencial Google inválida para todo o provider.
- Decisão: `BLOCKED_REVIEW` conforme `PROMPT-MASTER.md` §2 e `MODEL-ROUTING.md`; não houve review simulado nem substituição por modelo não-Google. Dependentes (`REC-03.03`, `REC-04.*`) parados. Nenhum commit, nenhuma alteração de código, `main` intocada, custo externo `$0.00`.
- Pendência do operador: corrigir/renovar a API key Google no OpenCode (ou autorizar explicitamente outro provedor para reviewer), e confirmar qual alias substitui Carbon/Hydrogen.

---

## Entry 008 — `REC-03.01` & `REC-03.02` Round 2 Remediation Complete (`ROUND_3_READY`)

- **Timestamp (UTC):** `2026-11-26T17:35Z`
- **Task IDs:** `REC-03.01`, `REC-03.02` (Round 3 re-review prep)
- **Base HEAD:** `develop` `3ca1f8512eb4681b97c4e5ecf3ee9ba61fae95b8` (uncommitted working tree)
- **Remediations Completed:**
  - **P1-1:** Rewrote `tests/test_storyboard_js.py` to evaluate the real production `STORYBOARD_JS` string inside a Node.js VM with lightweight `FakeElement` DOM harness (6/6 passing, mutation failure proved and restored).
  - **P1-2:** Clean Architecture scope and traversal isolation for `GET /studio/assets/{asset_id}/file`. Added `list_by_project` to `VideoRepository` (ports and Postgres), added `belongs_to_scope` to `AssetRepository` (ports and Postgres). `AssetFile` usecase validates scope existence first (`VideoNotFound` -> 404), scope authorization before asset lookup (preventing existence oracle, 403), and traversal root escape prevention (`resolve()` + `relative_to(root)` -> 404).
  - **P1-3:** Extracted scene trim query logic into `GetSceneTiming` application usecase wired in `wiring.py`, eliminating direct repo calls in routes. Trim save and atomic clearance moved into `ImportExternalMedia` usecase.
  - **P1-4:** Hardened assertions in `tests/test_rec_03_studio_routes.py` (replaced relaxed status tuples with exact codes, added traversal/NUL/cross-project/unscoped tests). Hardened `tests/e2e_ux/test_rec_03_studio_browser.py` (removed conditional guards on `#btn-gerar-faltante` and `#import-attribution`, replaced `or "?v=" in ...` with exact `assert f"?v={asset_id}" in src`, asserted added scene persists across reload).
  - **P2-1–P2-4:** MIME params stripped (`.split(";")[0].strip()`), `math.isfinite` check on trim floats, `0.0` truthiness check fixed, and frontend prompt/trim preservation updated.
- **Verification Results:**
  - Host Node JS suite: **6 passed in 5.60s** (`tests/test_storyboard_js.py`), **101 passed in 8.76s** (full host suite).
  - Container suite: **27 passed in 15.85s** (`tests/test_rec_03_studio_routes.py`), **90 passed in 29.59s** (full container integration & architecture suite).
  - Isolated Playwright E2E: **1 passed in 9.29s** (port 8100, `down -v` executed, zero dangling containers).
- **Status:** `ROUND_3_READY` (uncommitted, ready for Round 3 independent review).
- **Governance:** Port 8000 and 5678 untouched, `$0.00` API spend (`STUDIO_PUBLICATION_ENABLED=0`), clean git status (no commits, no pushes).

## REC-03.01–02 — review Rounds 1–3 e fechamento (2026-11-26, OpenCode)
- Operador autorizou GitHub Copilot; provider `google` seguia com API key inválida. Reviewer: `github-copilot/gemini-4-neon` high (substitui Carbon ausente, desvio registrado); executor: `github-copilot/gemini-3.8-flash` high; sessões separadas.
- Round 1 REJECTED (6.850/6.550, 5 P1) → correções (Flash, tentativa 1) → Round 2 REJECTED (7.475/7.750, 4 P1) → correções (Flash, tentativa 2) → Round 3 APPROVED (**9.290 / 9.355**, 0 P0/P1, 6 P2).
- Verificação independente Round 3: host `101 passed`; container focado `90 passed`; canônica completa `4491 passed, 26 skipped` exit 0 (807s); Playwright isolado porta 8100 `1 passed`, `down -v` feito; mutação do STORYBOARD_JS em cópia temporária falhou 4/5.
- Custo externo `$0.00`; `main` `42700cb` intocada; publicação `BLOCKED`.
