# MODEL-USAGE — V4 Product Completion (`PC-00`..`PC-09`)

**Policy:** Gemini models only (`gemini-3.8-flash-high`, `gemini-4-hydrogen-medium`, `gemini-4-carbon-high`, `gemini-4-neon-high`). Never infer tokens from quota percentages. Never enable overage or external paid APIs (`$0.00` ceiling). Safety reserve guideline: `15%` weekly / `10%` 5h window.

## 1. Observed Quota Readings

| Reading # | Timestamp (UTC) | Scope / Provider | Observed Quota Remaining | Reset Time (UTC) | External Paid API Spend (USD) | Notes |
|---:|---|---|---:|---|---:|---|
| 1 | `2026-11-27T01:44Z` | Google Antigravity Pool | `16%` | `2026-11-27T03:47:25Z` | `$0.00` | Campaign entry reading immediately after REC-04.03/04 closure; paused cleanly before `PC-00` (`Neon High` + `Carbon High`) to respect 15%/10% safety reserve |
| 2 | `2026-11-27T09:47Z` | Google Antigravity Pool (all Gemini models) | `100%` | `2026-11-27T14:43:55Z` | `$0.00` | Fresh post-reset session; verified via `swarm models` (`gemini-3.8-flash-low/high`, `gemini-4-hydrogen-medium`, `gemini-4-carbon-high`, `gemini-4-neon-high` all at `100%`). Launching `PC-00.01` & `PC-00.02`. |
| 3 | `2026-11-27T10:07Z` | Google Antigravity Pool (all Gemini models) | `89%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc00-auditor` (`gemini-4-neon-high`) completed `PC-00.01` & `PC-00.02` deliverables + live repro (`-11%`). |
| 4 | `2026-11-27T10:31Z` | Google Antigravity Pool (all Gemini models) | `64%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc00-reviewer` (`gemini-4-carbon-high`) completed independent review (`9.585`/`9.540`, `APPROVED`, `-25%`). Both workers killed; `64%` remaining (`49%` above `15%` weekly reserve). |
| 5 | `2026-11-27T11:13Z` | Google Antigravity Pool (all Gemini models) | `45%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc01-executor` (`gemini-4-hydrogen-medium`) delivered `PC-01.01`–`01.02` + 172 container tests + isolated Playwright Desktop/Mobile E2E (`-19%`). |
| 6 | `2026-11-27T11:20Z` | Google Antigravity Pool (all Gemini models) | `39%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc01-reviewer` (`gemini-4-neon-high`) Round 1 review (`REJECTED`, surfaced 1 P0 + 2 P1, `-6%`). |
| 7 | `2026-11-27T11:27Z` | Google Antigravity Pool (all Gemini models) | `36%` | `2026-11-27T14:47:04Z` | `$0.00` | After Round 2 fix + independent `Neon High` re-review (`APPROVED` `9.350`/`9.300`, `-3%`). Both workers killed; `36%` remaining (`21%` above `15%` weekly reserve). |
| 8 | `2026-11-27T12:14Z` | Google Antigravity Pool (all Gemini models) | `19%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc0502-executor` (`gemini-3.8-flash-high`) completed `PC-05.02` R1 + container/Node/E2E (`-17%`). |
| 9 | `2026-11-27T12:25Z` | Google Antigravity Pool (all Gemini models) | `11%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc0502-reviewer` (`gemini-4-carbon-high`) R1 review (`8.010/10` `REJECTED`, 1 P0 + 3 P1, `-8%`). Paused cleanly above `10%` 5h reserve; workers killed; auto-resume scheduled for `14:49Z`. |
| 10 | `2026-11-27T14:49Z` | Google Antigravity Pool (all Gemini models — **Weekly Cap**) | `10%` | `2026-12-03T10:00:59Z` | `$0.00` | Post-5h-reset check revealed the **weekly Gemini cap** at **`10%`** remaining (below `15%` weekly safety reserve; resets `2026-12-03T10:00:59Z` / `07:00:59` local). Halted cleanly with zero workers spawned and zero unauthorized non-Gemini provider usage. |

## 2. Task Routing Ledger
| Task | Role | Worker Name | Effective Model | Status | Notes |
|---|---|---|---|---|---|
| Swarm Monitor | Monitor | `monitor` | `gemini-3.8-flash-low` | `QUIET ([done])` | Silenced during quota-reset pause |
| `PC-00.01`, `PC-00.02` | Executor (Auditor) | `pc00-auditor` | `gemini-4-neon-high` | `VERIFIED / KILLED` | Delivered audit, matrix, test-first plan, live PC-01 repro |
| `PC-00.01`, `PC-00.02` | Independent Reviewer | `pc00-reviewer` | `gemini-4-carbon-high` | `APPROVED / KILLED` | `9.585/10` (`PC-00.01`), `9.540/10` (`PC-00.02`), `0` P0/P1 |
| `PC-01.01`, `PC-01.02` | Executor | `pc01-executor` | `gemini-4-hydrogen-medium` | `VERIFIED / KILLED` | Single-tx base replace + `0055` `edit_revision` CAS + undo/redo + E2E (2 rounds) |
| `PC-01.01`, `PC-01.02` | Independent Reviewer | `pc01-reviewer` | `gemini-4-neon-high` | `APPROVED / KILLED` | R1 REJECTED (caught 1 P0 + 2 P1) → R2 APPROVED (`9.350`/`9.300`, `0` P0/P1) |
| `PC-05.02` (R1) | Executor | `pc0502-executor` | `gemini-3.8-flash-high` | `R1_REJECTED / KILLED` | Escalate R2 fix to `Hydrogen Medium` post-reset per `MODEL-ROUTING.md` |
| `PC-05.02` (R1) | Independent Reviewer | `pc0502-reviewer` | `gemini-4-carbon-high` | `R1_DONE / KILLED` | `8.010/10` `REJECTED` (caught 1 P0 + 3 P1 real defects) |
