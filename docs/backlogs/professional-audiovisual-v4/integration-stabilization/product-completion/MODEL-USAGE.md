# MODEL-USAGE — V4 Product Completion (`PC-00`..`PC-09`)

**Policy:** Gemini models only (`gemini-3.8-flash-high`, `gemini-4-hydrogen-medium`, `gemini-4-carbon-high`, `gemini-4-neon-high`). Never infer tokens from quota percentages. Never enable overage or external paid APIs (`$0.00` ceiling). Safety reserve guideline: `15%` weekly / `10%` 5h window.

## 1. Observed Quota Readings

| Reading # | Timestamp (UTC) | Scope / Provider | Observed Quota Remaining | Reset Time (UTC) | External Paid API Spend (USD) | Notes |
|---:|---|---|---:|---|---:|---|
| 1 | `2026-11-27T01:44Z` | Google Antigravity Pool | `16%` | `2026-11-27T03:47:25Z` | `$0.00` | Campaign entry reading immediately after REC-04.03/04 closure; paused cleanly before `PC-00` (`Neon High` + `Carbon High`) to respect 15%/10% safety reserve |
| 2 | `2026-11-27T09:47Z` | Google Antigravity Pool (all Gemini models) | `100%` | `2026-11-27T14:43:55Z` | `$0.00` | Fresh post-reset session; verified via `swarm models` (`gemini-3.8-flash-low/high`, `gemini-4-hydrogen-medium`, `gemini-4-carbon-high`, `gemini-4-neon-high` all at `100%`). Launching `PC-00.01` & `PC-00.02`. |
| 3 | `2026-11-27T10:07Z` | Google Antigravity Pool (all Gemini models) | `89%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc00-auditor` (`gemini-4-neon-high`) completed `PC-00.01` & `PC-00.02` deliverables + live repro (`-11%`). |
| 4 | `2026-11-27T10:31Z` | Google Antigravity Pool (all Gemini models) | `64%` | `2026-11-27T14:47:04Z` | `$0.00` | After `pc00-reviewer` (`gemini-4-carbon-high`) completed independent review (`9.585`/`9.540`, `APPROVED`, `-25%`). Both workers killed; `64%` remaining (`49%` above `15%` weekly reserve). |

## 2. Task Routing Ledger
| Task | Role | Worker Name | Effective Model | Status | Notes |
|---|---|---|---|---|---|
| Swarm Monitor | Monitor | `monitor` | `gemini-3.8-flash-low` | `ACTIVE` | Stall monitor per native swarm skill |
| `PC-00.01`, `PC-00.02` | Executor (Auditor) | `pc00-auditor` | `gemini-4-neon-high` | `VERIFIED / KILLED` | Delivered audit, matrix, test-first plan, live PC-01 repro |
| `PC-00.01`, `PC-00.02` | Independent Reviewer | `pc00-reviewer` | `gemini-4-carbon-high` | `APPROVED / KILLED` | `9.585/10` (`PC-00.01`), `9.540/10` (`PC-00.02`), `0` P0/P1 |
