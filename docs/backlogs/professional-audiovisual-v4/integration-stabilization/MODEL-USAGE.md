# MODEL-USAGE — V4 Integration & Stabilization Recovery

Tracking real Google model assignments, observed quota readings, retries/escalations, and external API spend per `PROMPT-MASTER.md` §6 and `MODEL-ROUTING.md`.  
**Policy:** Google models only. Never infer token counts from quota percentages. Never enable overage or paid external APIs (`$0.00` ceiling).

---

## 1. Observed Quota & Cost Baseline

| Reading # | Timestamp (UTC) | Scope / Provider | Observed Quota Remaining | Reset Time (UTC) | External Paid API Spend (USD) | Notes |
|---:|---|---|---:|---|---:|---|
| 1 | `2026-11-26T13:55Z` | Google Antigravity Pool | `81%` | `2026-11-26T15:00:59Z` | `$0.00` | Campaign start reading; safety reserve guideline: 15% weekly / 10% 5h window |
| 2 | `2026-11-26T13:57Z` | Google Antigravity Pool | `73%` | `2026-11-26T15:00:59Z` | `$0.00` | Mid-REC-00 reading during `rec00-auditor` (`Neon High`) |
| 3 | `2026-11-26T14:21Z` | Google Antigravity Pool | `43%` | `2026-11-26T15:00:59Z` | `$0.00` | Post-REC-00 review (`VERIFIED`); retired REC-00 workers; launching `REC-01` on `Hydrogen Medium` to conserve quota before 15:00:59Z reset |
| 4 | `2026-11-26T14:37Z` | Google Antigravity Pool | `28%` | `2026-11-26T15:00:59Z` | `$0.00` | Post-REC-01 implementation (`Hydrogen Medium`, 15% delta); launching `Neon High` independent review |
| 5 | `2026-11-26T14:51Z` | Google Antigravity Pool | `21%` | `2026-11-26T15:00:59Z` | `$0.00` | Post-REC-01 Round 1→2 review (`VERIFIED` 9.50/10, only 7% delta); launching `REC-02.05` on `Flash 3.8` ahead of 15:00:59Z quota reset |

---

## 2. Active Agents & Task Ledger

| Wave / Task | Role | Roster Agent | Real Model Used | Attempt # | Status | Escalation / Notes |
|---|---|---|---|---:|---|---|
| Campaign | Coordinator | `coordinator` | `Gemini 4 Carbon (High)` | 1 | `IN_PROGRESS` | Orchestration, atomic commits after independent review |
| `REC-00.01`, `REC-00.02` | Executor | `rec00-auditor` (retired) | `Gemini 4 Neon (High)` | 1 | `VERIFIED` | Read-only audit, 227-ID matrix, financial inventory, test-first plan |
| `REC-00.01`, `REC-00.02` | Independent Reviewer | `rec00-reviewer` (retired) | `Gemini 4 Carbon (High)` | 1 | `VERIFIED` | Approved `9.51/10` & `9.54/10` in `evidence/rec-00/independent-review-carbon-high.md` |
| `REC-01.01`–`03` | Executor | `rec01-dev` (retired) | `Gemini 4 Hydrogen (Medium)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 3 P1/P2 review findings (302 tests pass) |
| `REC-01.01`–`03` | Independent Reviewer | `rec01-reviewer` (retired) | `Gemini 4 Neon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (caught 3 real P1/P2 bugs); Round 2 APPROVED `9.50/10` (`166 passed`) |
| `REC-02.01`–`04` | Executor / Reviewer | Planned | `Hydrogen Medium` / `Neon High` | — | `PENDING` | Starts right after `REC-02.05` (and 15:00:59Z reset) |
| `REC-02.05` | Executor | `rec02-voice` | `Gemini 3.8 Flash (High)` | 1 | `IN_PROGRESS` | Voice sanitation (`R09`): Kokoro offline fail-closed + Piper real + ElevenLabs disabled |
| `REC-03.01`–`02` | Executor / Reviewer | Planned | `Flash 3.8` / `Carbon High` | — | `PENDING` | Starts after REC-02 `VERIFIED` |
| `REC-03.03` | Executor / Reviewer | Planned | `Hydrogen Medium` / `Neon High` | — | `PENDING` | Starts after REC-02 `VERIFIED` |
| `REC-04.01`–`02` | Executor / Reviewer | Planned | `Flash 3.8` / `Carbon High` | — | `PENDING` | Starts after REC-03 `VERIFIED` |
| `REC-04.03`–`04` | Executor / Reviewer | Planned | `Carbon High` / `Neon High` + Operator | — | `PENDING` | Final regression + independent review + human audiovisual review |

---

## 3. Verification Rules Checklist
- [x] Separate executor (`Gemini 4 Neon High`) and independent reviewer (`Gemini 4 Carbon High`) sessions confirmed for REC-00.
- [x] Zero token counts fabricated from percentage quota.
- [x] Zero paid external API calls executed (`$0.00`).
- [x] No overage enabled.
