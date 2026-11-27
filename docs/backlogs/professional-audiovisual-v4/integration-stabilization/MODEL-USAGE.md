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
| 10 | `2026-11-26T16:05Z` | Google Antigravity Pool | `33%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-02.03–04 Round 1 impl (`Hydrogen Medium`, 10% delta); launching `Neon High` independent review |
| 11 | `2026-11-26T16:16Z` | Google Antigravity Pool | `24%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-02.03–04 Round 1→2 review (`VERIFIED` 9.425/9.44, 141/141 passed); Wave `REC-02` 100% closed; launching `REC-03.01–02` on `Flash 3.8` |
| 12 | `2026-11-26T16:55Z` | Google Antigravity Pool | `10%` | `2026-11-26T20:00:59Z` | `$0.00` | Post-REC-03.01–02 impl (`Flash 3.8`, `IMPLEMENTED`); reached 10% 5h safety reserve -> safe checkpoint saved, pausing before independent `Carbon High` review until window reset or operator override |
| 13 | `2026-11-26T22:47Z` | Google Antigravity Pool | `100%` | `2026-11-27T03:47:25Z` | `$0.00` | Window 3 reset (`100%`) after OpenCode session completed `REC-03.01–03` & `REC-04.01`; resuming `REC-04.02` on `Hydrogen Medium` |
| 14 | `2026-11-26T23:37Z` | Google Antigravity Pool | `83%` | `2026-11-27T03:47:25Z` | `$0.00` | Post-REC-04.02 impl & real 309.80s documentary render (`Hydrogen Medium`, 17% delta); launching `Neon High` independent review |
| 15 | `2026-11-26T23:48Z` | Google Antigravity Pool | `77%` | `2026-11-27T03:47:25Z` | `$0.00` | Post-REC-04.02 Round 1→2 review (`APPROVED 9.400/10`, 6% delta); launching `REC-04.03` on `Carbon High` |
| 16 | `2026-11-27T00:22Z` | Google Antigravity Pool | `55%` | `2026-11-27T03:47:25Z` | `$0.00` | Mid-REC-04.03: caught 3 legacy browser E2E mismatches (`6a55f1f` test-only alignment committed) |
| 17 | `2026-11-27T00:55Z` | Google Antigravity Pool | `24%` | `2026-11-27T03:47:25Z` | `$0.00` | Post-REC-04.03/04 full clean-SHA regression (`4510+101+27+20`, 0 failures) + matrix & final report; launching `Neon High` final review |
| 18 | `2026-11-27T01:00Z` | Google Antigravity Pool | `19%` | `2026-11-27T03:47:25Z` | `$0.00` | Campaign technical gates 100% CLOSED (`REC-04.03 = 9.585`, `REC-04.04 = 9.470`; `TECHNICAL GO / AWAITING HUMAN REVIEW`) — safely above reserve |

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
| `REC-02.03`–`04` | Executor | `rec02-media` (retired) | `Gemini 4 Hydrogen (Medium)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 5 P1 findings (`141 passed`) |
| `REC-02.03`–`04` | Independent Reviewer | `rec02-media-rev` (retired) | `Gemini 4 Neon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (5 P1 bugs); Round 2 APPROVED `9.425/10` & `9.440/10` |
| `REC-02.05` | Executor | `rec02-voice` (retired) | `Gemini 3.8 Flash (High)` | 2 | `VERIFIED` | Round 1 impl + Round 2 fixes for 4 P1 findings (105 tests pass) |
| `REC-02.05` | Independent Reviewer | `rec02-voice-rev` (retired) | `Gemini 4 Carbon (High)` | 2 | `VERIFIED` | Round 1 REJECTED (4 P1 bugs); Round 2 APPROVED `9.50/10` (`172/172` passed) |
| `REC-03.01`–`02` | Executor | `rec03-ux` (via `github-copilot/gemini-3.8-flash`) | `Gemini 3.8 Flash (High)` | 3 | `VERIFIED` | Round 2 findings remediated (P1-1 Node VM real STORYBOARD_JS, P1-2 Clean Arch scope & traversal, P1-3 GetSceneTiming/trim, P1-4 hardened asserts); 6 Node + 101 host + 90 container + Playwright E2E passing |
| `REC-03.01`–`02` | Independent Reviewer | 3 sessões separadas (`github-copilot/gemini-4-neon`, substitui Carbon ausente) | `Gemini 4 Neon (High)` | 3 | `VERIFIED` | Round 1 REJECTED (6.85/6.55, 5 P1); Round 2 REJECTED (7.475/7.75, 4 P1); Round 3 APPROVED `9.290/10` & `9.355/10` |
| `REC-03.03` | Executor | Flash 3.8 (tentativa 1) → `github-copilot/gemini-4-neon` high (escalado; Hydrogen/Carbon ausentes) | `Gemini 3.8 Flash` / `Neon High` | 2 | `VERIFIED` | Round 1 impl (Flash) REJECTED 3.95; fixes (Neon) APPROVED 9.44 |
| `REC-03.03` | Independent Reviewer | 2 sessões separadas `github-copilot/gemini-4-neon` | `Gemini 4 Neon (High)` | 2 | `VERIFIED` | R1 REJECTED 3.95; R2 APPROVED 9.44 |
| `REC-04.01` | Executor | `github-copilot/gemini-4-neon` high (desvio: Flash previsto) | `Gemini 4 Neon (High)` | 1 | `VERIFIED` (técnico) | slice 67.36s real via Studio |
| `REC-04.01` | Independent Reviewer | sessão separada `github-copilot/gemini-4-neon` | `Gemini 4 Neon (High)` | 1 | `VERIFIED` | R1 APPROVED 9.345 |
| `REC-04.02` | Executor | `rec04-doc` (retired) | `Gemini 4 Hydrogen (Medium)` | 2 | `VERIFIED` (técnico) | Prerequisites `P2-1`/`PRE-1`/`P2-4`/`facts.py` + 309.80s 25-scene documentary + `-57.41%` selective regen (`182 passed`) |
| `REC-04.02` | Independent Reviewer | `rec04-doc-rev` (retired) | `Gemini 4 Neon (High)` | 2 | `VERIFIED` (técnico) | Round 1 REJECTED `9.190` (1 P1 `test_facts.py`); Round 2 APPROVED `9.400/10` (6 frames + SHA/ffprobe/ebur128 + 3 `/tmp` mutations) |
| `REC-04.03`–`04` | Executor | `rec04-release` (retired) | `Gemini 4 Carbon (High)` | 1 | `VERIFIED` | Clean-SHA `6a55f1f` 4-campaign regression (`4510+101+27+20`, 0 failures) + reconciled `TRACEABILITY-MATRIX.md` + `FINAL-REPORT.md` |
| `REC-04.03`–`04` | Independent Reviewer | `rec04-release-rev` (retired) | `Gemini 4 Neon (High)` | 1 | `VERIFIED` (técnico) | Approved `REC-04.03 = 9.585/10` & `REC-04.04 = 9.470/10`; `TECHNICAL GO / AWAITING HUMAN REVIEW` (operator audiovisual review pending) |

---

## 3. Verification Rules Checklist
- [x] Separate executor (`Gemini 4 Neon High`) and independent reviewer (`Gemini 4 Carbon High`) sessions confirmed for REC-00.
- [x] Zero token counts fabricated from percentage quota.
- [x] Zero paid external API calls executed (`$0.00`).
- [x] No overage enabled.
