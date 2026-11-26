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
| 6 | `2026-11-26T15:08Z` | Google Antigravity Pool | `97%` | `2026-11-26T20:00:59Z` | `$0.00` | Window reset at 15:00:59Z! Post-REC-02.05 Round 1 impl (`Flash 3.8`); launching `Carbon High` independent review |
| 7 | `2026-11-26T15:27Z` | Google Antigravity Pool | `74%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-02.05 Round 1→2 review (`VERIFIED` 9.50/10, 172/172 passed); launching `REC-02.01–02` on `Hydrogen Medium` |
| 8 | `2026-11-26T15:39Z` | Google Antigravity Pool | `62%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-02.01–02 Round 1 impl (`Hydrogen Medium`, 12% delta); launching `Neon High` independent review |
| 9 | `2026-11-26T15:56Z` | Google Antigravity Pool | `43%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-02.01–02 Round 1→2 review (`VERIFIED` 9.44/9.425, 164/164 passed); launching `REC-02.03–04` on `Hydrogen Medium` |

---

## 2. Active Agents & Task Ledger

| Wave / Task | Role | Roster Agent | Real Model Used | Attempt # | Status | Escalation / Notes |
|---|---|---|---|---:|---|---|
| Campaign | Coordinator | `coordinator` | `Gemini 4 Carbon (High)` | 1 | `IN_PROGRESS` | Orchestration, atomic commits after independent review |
| `REC-00.01`, `REC-00.02` | Executor | `rec00-auditor` (retired) | `Gemini 4 Neon (High)` | 1 | `VERIFIED` | Read-only audit, 227-ID matrix, financial inventory, test-first plan |
| `REC-00.01`, `REC-00.02` | Independent Reviewer | `rec00-reviewer` (retired) | `Gemini 4 Carbon (High)` | 1 | `VERIFIED` | Approved `9.51/10` & `9.54/10` in `evidence/rec-00/independent-review-carbon-high.md` |
| `REC-01.01`–`03` | Executor | `rec01-dev` (retired) | `Gemini 4 Hydrogen (Medium)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 3 P1/P2 review findings (302 tests pass) |
| `REC-01.01`–`03` | Independent Reviewer | `rec01-reviewer` (retired) | `Gemini 4 Neon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (caught 3 real P1/P2 bugs); Round 2 APPROVED `9.50/10` (`166 passed`) |
| `REC-02.01`–`02` | Executor | `rec02-av` (retired) | `Gemini 4 Hydrogen (Medium)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 4 P1 findings (`164 passed`) |
| `REC-02.01`–`02` | Independent Reviewer | `rec02-av-rev` (retired) | `Gemini 4 Neon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (4 P1 bugs); Round 2 APPROVED `9.440/10` & `9.425/10` |
| `REC-02.03`–`04` | Executor | `rec02-media` | `Gemini 4 Hydrogen (Medium)` | 1 | `IN_PROGRESS` | External PNG/MP4 probe/decode import (`R06`) + content/scope dedup & CAS (`R07`) |
| `REC-02.03`–`04` | Independent Reviewer | `rec02-media-rev` (on handoff) | `Gemini 4 Neon (High)` | — | `PENDING` | Mandatory Neon High review on handoff |
| `REC-02.05` | Executor | `rec02-voice` (retired) | `Gemini 3.8 Flash (High)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 4 P1 findings (105 tests pass) |
| `REC-02.05` | Independent Reviewer | `rec02-voice-rev` (retired) | `Gemini 4 Carbon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (4 P1 bugs); Round 2 APPROVED `9.50/10` (`172/172` passed) |
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
