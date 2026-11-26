# Independent Financial Safety Review — Wave REC-01 (`REC-01.01`, `REC-01.02`, `REC-01.03`)

- **Reviewer / Model:** `rec01-reviewer` (`Gemini 4 Neon High`)
- **Review Rounds:** Round 1 (REJECTED — 3 actionable findings) -> Round 2 (**APPROVED**)
- **Branch / Base HEAD:** `develop` @ `031811f420ea74376f9a76ad461437b40db76405` (uncommitted working tree diff from `#15`)
- **Reviewed App Hash / Migrations:** `hash renderer/app: d95e281af8d0ab89` (checkout == image), `migrações: 49/49`
- **`main` Branch Check:** `42700cb331165a68455173a91c463d4733292cfd` (untouched)
- **External API Spend:** `$0.00` (100% offline/disposable PostgreSQL doubles)
- **Publication Kill Switch:** Verified (`publication_enabled=False` -> `PublicationResult.BLOCKED`, `token_calls == 0`, `upload_calls == 0`, `publication_execution.py` untouched)
- **Final Decision (Round 2):** **APPROVED (`VERIFIED`)** — `REC-01.01: 9.50`, `REC-01.02: 9.50`, `REC-01.03: 9.50` (all dimensions `>= 9.0`, zero P0/P1 blockers)

---

## 1. Round 1 Findings & Round 2 Verification Trail

All three Round 1 findings (`#13`) were fixed by `@rec01-dev` (`#15`) and independently verified in code, SQL, and disposable PostgreSQL container tests:

| Finding | Severity | Round 1 Defect | Round 2 Resolution Verified |
|---|---|---|---|
| **#1** (`REC-01.03`) | **P1** | `LeaseHeartbeat.stop()` did not revoke/mark lease lost after timeout, leaving `ctx.lease.ensure_held()` (used by real `PublishHandler` at `production.py:589,595`) un-fenced for up to 270s (`0.9 * 300s`). | **RESOLVED:** Added `LeaseHeartbeat.revoke(reason)` (`lease_heartbeat.py:73-75`) invoked in `_execute_claimed` right after `lost = lease.lost` (`production.py:1178-1180`) whenever `failure is not None or lost`. Timeout still returns `WorkerStepResult.FAILED` while immediately raising `LeaseLost` on `ctx.lease.ensure_held()`. `StageContext.clock` also wired to `self._clock` (`production.py:228,238-243,1141`). |
| **#2** (`REC-01.02`) | **P1** | Rollback SQL in `0054_paid_operation_external_ref.sql:7` (`docs/schema/studio.sql:1671`, `implementation-evidence.md:113`) used `version = '0054_paid_operation_external_ref.sql'` instead of `'0054_paid_operation_external_ref'` (`db.py:19` records `path.stem`), leaving `schema_migrations` dirty on rollback. | **RESOLVED:** Updated `version = '0054_paid_operation_external_ref'` in `0054_paid_operation_external_ref.sql:7` and `implementation-evidence.md:109`, regenerated `docs/schema/studio.sql:1671`, and verified `test_schema_docs.py` passes (`4/4`). |
| **#3** (`REC-01.03`) | **P1/P2** | `_check_pre_retry_reconciliation` missed cross-month `UNCERTAIN`/`RESERVED` ops under `reason == "stale_reservation"`, did not re-verify DB state after `reconcile_operation() -> True`, and `tests/test_rec_01_financial_safety.py` used `time.sleep(0.05)` without asserting `LeaseLost` on `ensure_held()` or testing the `wiring.py` (`operation_key_for=None`) retry path. | **RESOLVED:** Added `_reconcile_key` (`production.py:1064-1071`) re-checking `paid_ops.state(op_key) not in (RESERVED, UNCERTAIN)`, extended `_check_pre_retry_reconciliation` (`production.py:1091-1109`) to inspect `stale_reservation` items against DB state, hardened `test_rec_01_03_late_handler_fenced_after_lease_loss_and_timeout` with `threading.Event` + `LeaseLost` + `StageTimeoutError` assertions, and added `test_rec_01_03_wiring_default_pre_retry_blocks_uncertain_without_operation_key_for`. |

---

## 2. Independent Container Verification (Round 2 Observed)

Executed independently on the final Round 2 working tree (`hash renderer/app: d95e281af8d0ab89`):

```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh \
  tests/test_rec_01_financial_safety.py \
  tests/test_int_04_pipeline.py \
  tests/test_v4_reliability_scale.py \
  tests/test_paid_operations.py \
  tests/test_budget_reservations.py \
  tests/test_production_coordinator.py \
  tests/test_lease_recovery_concurrency.py \
  tests/test_schema_docs.py \
  tests/test_architecture.py
```

- **Container Alignment:** `HEAD=031811f alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=d95e281af8d0ab89 imagem=d95e281af8d0ab89`, `migrações: checkout=49 imagem=49`
- **Result:** `166 passed in 86.22s (0:01:26)` (0 failed, 0 skipped)
- **Exit Code:** `0`
- **Suite Breakdown:**
  - `tests/test_rec_01_financial_safety.py`: `9 passed`
  - `tests/test_int_04_pipeline.py`: `2 passed`
  - `tests/test_v4_reliability_scale.py`: `10 passed`
  - `tests/test_paid_operations.py`: `35 passed`
  - `tests/test_budget_reservations.py`: `42 passed`
  - `tests/test_production_coordinator.py`: `43 passed`
  - `tests/test_lease_recovery_concurrency.py`: `12 passed`
  - `tests/test_schema_docs.py`: `4 passed`
  - `tests/test_architecture.py`: `9 passed`
- **Relaxed Assertions Audit:** Verified full diffs of `tests/test_int_04_pipeline.py`, `tests/test_v4_reliability_scale.py`, `tests/test_db.py`, and `tests/test_rec_01_financial_safety.py`. Zero assertions relaxed to mask defects.
- **Unsafe Remnants Grep (`git grep`):** Zero code occurrences of `operation_store`, `PostgresOperationStore`, `ResilientStageExecutor`, `InMemoryOperationStore`, `OperationReconciler`, `mock_duration_seconds`, or `SELECT id FROM studio.videos LIMIT 1` across `renderer/app` and `tests` (only a docstring note in `tests/test_int_04_pipeline.py:3`).

---

## 3. Technical Checklist Verification (`prompts/REC-01-financial-safety.md`)

- **R01 (`REC-01.01`):**
  - `renderer/app/studio/adapters/postgres/operation_store.py` deleted (`ModuleNotFoundError` verified).
  - Zero `SELECT id FROM studio.videos LIMIT 1` and zero hardcoded `1000/100` caps.
  - Authoritative `project_id` resolved from `studio.videos` in `budget_repo.py:_scope_project`; unknown `video_id` fails closed (`ValueError`); cross-video key reuse fails (`IdempotencyConflict`); `wiring.py:530` passes `channel_guard_limits`.
  - `$0.00` ceiling blocks paid ops before side-effect (`BudgetDenied`, `ceiling_usd == Decimal("0.00")`, `0` submits, `0` ledger rows).
  - Kill switch (`publication_enabled=False`) intact before token lookup or upload (`PublicationResult.BLOCKED`, `token_calls == 0`, `upload_calls == 0`).
- **R02 (`REC-01.02`):**
  - Exclusive transactional admission via `READ COMMITTED` + `pg_advisory_xact_lock(726002)` + `FOR UPDATE` + PK uniqueness on `idempotency_key`.
  - Monotonic state transitions (`RESERVED`, `CONFIRMED`, `RELEASED`, `UNCERTAIN`) with CAS; stale post-`CONFIRMED` transitions rejected (`InvalidOperationTransition`); `RELEASED` reopens with `attempt = attempt + 1` and clears `external_reference_id`/`submitted_at`.
  - Attempt-free logical idempotency key in `domain/resilience.py:compute_deterministic_idempotency_key`.
  - Durable `external_reference_id` + `submitted_at` via additive reversible migration `0054_paid_operation_external_ref.sql` (`v1/v2` compatible, exact `path.stem` rollback verified, `docs/schema/studio.sql` & `docs/22-modelo-de-dados.md` aligned).
  - Idempotent settlement (`confirm()` replay produces exactly `1` `studio.usage_ledger` row; divergent confirmation rejected).
  - Unknown/`None` cost moves to `UNCERTAIN` with `0` ledger rows (never silently `$0.00`).
  - Proven in disposable PostgreSQL across 2 concurrent connections (`Barrier(2)`), 2 projects/videos, `$0.00` cap, simulated crash/restart between `record_external_ref` and `confirm`, pre-effect (`PreEffectFailure` -> `RELEASED`) vs post-effect (`ConnectionError` -> `UNCERTAIN`, `double_submit_count == 1`).
- **R03 (`REC-01.03`):**
  - `ResilientStageExecutor`, `InMemoryOperationStore`, `OperationReconciler`, `OperationStoreProtocol`, and `mock_duration_seconds` removed from `application/resilience.py`.
  - Real cooperative timeout/cancellation (`StageContext.cancel_event`, `deadline_monotonic`, `clock`, `ensure_active()`, bounded worker wait) and immediate lease revocation (`LeaseHeartbeat.revoke`) in canonical `ProductionCoordinator`.
  - Late handler after timeout/lease loss cannot pass `ctx.ensure_active()`, cannot pass `ctx.lease.ensure_held()` (`LeaseLost`), writes `0` ledger rows, and is rejected by Postgres `complete_stage` (`NOT_RUNNING`/`LOST`).
  - Pre-retry reconciliation (`_check_pre_retry_reconciliation`, `_reconcile_key`) wired via `paid_ops` in `wiring.py:744-746`, blocks `RESERVED`/`UNCERTAIN` (including cross-month `stale_reservation`) fail-closed before calling handler (`external_submits == 1`).

---

## 4. Rubric Scoring Tables (`QUALITY-RUBRIC.md` — Round 2 Final)

Threshold: **>= 9.0 in every applicable dimension**, **weighted mean >= 9.0** (no rounding), **zero P0/P1 blockers**.

### `REC-01.01` — Unsafe Adapter Removal & Real Identity/Limits (R01)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | `operation_store.py` deletado (`ModuleNotFoundError`); zero `SELECT id FROM studio.videos LIMIT 1` ou tetos `1000/100`; `_scope_project` resolve `project_id` autoritativo via `studio.videos`; `wiring.py:530` injeta `channel_guard_limits`; teto `$0.00` bloqueia antes de efeito externo; kill switch intacto. |
| Arquitetura e simplicidade | 20% | 9.5 | Reuso estrito de `PaidOperationGuard`, `PostgresPaidOperationRepository` e `RunPublication`; sem ledger/guard paralelo. |
| Testes e regressão | 20% | 9.5 | `test_rec_01_01_*`, `test_paid_operations.py`, `test_budget_reservations.py`, `test_architecture.py` aprovados em PG descartável (166/166, exit `0`). |
| Segurança, orçamento e confiabilidade | 20% | 9.5 | Vídeo inexistente falha fechado (`ValueError`); chave cross-video falha (`IdempotencyConflict`); `$0.00` bloqueia (`0` submits, `0` ledger); kill switch antes de token/upload. |
| Evidências e operação | 15% | 9.5 | Repro Red pré-fix + Green pós-fix alinhados (`hash=d95e281af8d0ab89`, `migrações=49/49`) e rastreados em `implementation-evidence.md`. |

- **Média Ponderada Exata (`REC-01.01`):** `9.50`
- **Gates Aplicáveis:** R01, isolamento projeto/vídeo, teto `$0.00`, kill switch publicação
- **Bloqueios P0/P1:** Nenhum
- **Decisão (`REC-01.01`):** **APPROVED (`VERIFIED`)**

---

### `REC-01.02` — Transactional Admission, CAS, Logical Key, Durable External Ref & Idempotent Settlement (R02)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | `pg_advisory_xact_lock(726002)` + `FOR UPDATE`, `record_external_ref`/`external_reference_id`, `confirm()` idempotente (1 linha em `usage_ledger`, divergência rejeitada), chave sem `attempt`, custo desconhecido nunca vira `$0.00`, pré vs pós-efeito corretos. |
| Arquitetura e simplicidade | 20% | 9.5 | Migração `0054_paid_operation_external_ref.sql` aditiva (colunas anuláveis), compatível v1/v2, `paid_operations_settlement_check` preservada, rollback SQL exato (`version = '0054_paid_operation_external_ref'`, alinhado com `db.py:19` `path.stem`), `docs/schema/studio.sql` regenerado (`test_schema_docs.py` 4/4). |
| Testes e regressão | 20% | 9.5 | 2 conexões PG concorrentes (`Barrier(2)`), corrida de teto global `$1.00`, restart real entre `record_external_ref` e `confirm`, replay de `confirm` (`COUNT=1`), CAS stale, custo `None`, pré vs pós-efeito; 166/166 exit `0`. |
| Segurança, orçamento e confiabilidade | 20% | 9.5 | Admissão exclusiva sob `READ COMMITTED` + advisory lock 726002, estados monotônicos sem colapso, `UNCERTAIN` preserva reserva e bloqueia re-submit (`double_submit_count == 1`). |
| Evidências e operação | 15% | 9.5 | Rollback SQL consistente em `0054_paid_operation_external_ref.sql`, `docs/schema/studio.sql` e `implementation-evidence.md`; container hash `d95e281af8d0ab89`, 49/49 migrações, `$0.00` gasto externo. |

- **Média Ponderada Exata (`REC-01.02`):** `9.50`
- **Gates Aplicáveis:** R02, concorrência 2 conexões, restart, CAS, migração reversível
- **Bloqueios P0/P1:** Nenhum
- **Decisão (`REC-01.02`):** **APPROVED (`VERIFIED`)**

---

### `REC-01.03` — Cooperative Timeout, Lease Fencing & Pre-Retry Reconciliation in `ProductionCoordinator` (R03)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | Executor paralelo/reconciler/`mock_duration_seconds` removidos; timeout cooperativo (`StageContext.ensure_active`, `clock=self._clock`) + `LeaseHeartbeat.revoke` no `ProductionCoordinator`; `_check_pre_retry_reconciliation` e `_reconcile_key` fail-closed (incluindo `stale_reservation` cross-month) e `paid_ops` plugado em `wiring.py:744-746`. |
| Arquitetura e simplicidade | 20% | 9.5 | Eliminação de 240 linhas duplicadas em `application/resilience.py`; extensões mínimas e coesas sobre `LeaseHeartbeat` e `ProductionCoordinator` existentes. |
| Testes e regressão | 20% | 9.5 | `test_rec_01_03_*` determinístico via `threading.Event`, valida `LeaseLost` em `ctx.lease.ensure_held()` + `StageTimeoutError` + rejeição de `complete_stage` + caminho padrão `wiring.py` (`operation_key_for=None`, `attempt > 1`) + kill switch; 166/166 exit `0`. |
| Segurança, orçamento e confiabilidade | 20% | 9.5 | Revogação local imediata do lease após timeout/falha + fencing token CAS no Postgres + bloqueio fail-closed pré-retry (`external_submits == 1`) + kill switch antes de token/upload. |
| Evidências e operação | 15% | 9.5 | Trilha completa Round 1 -> Round 2, hash `d95e281af8d0ab89` verificado independentemente, `main` intacto, zero API paga. |

- **Média Ponderada Exata (`REC-01.03`):** `9.50`
- **Gates Aplicáveis:** R03, timeout cooperativo real, fencing pós-lease/timeout, reconciliação pré-retry, kill switch
- **Bloqueios P0/P1:** Nenhum
- **Decisão (`REC-01.03`):** **APPROVED (`VERIFIED`)**

---

## 5. Final Wave Summary & Non-Blocking Optional Improvements

- **Wave REC-01 Decision:** **APPROVED (`VERIFIED`)** across `REC-01.01` (`9.50`), `REC-01.02` (`9.50`), and `REC-01.03` (`9.50`) — zero P0/P1 blockers, every applicable rubric dimension `>= 9.0`.
- **Optional Future Improvements (Non-Blocking, P3):**
  1. Expose optional `stage_timeouts` / `default_stage_timeout_seconds` configuration in `composition/settings.py` + `wiring.py` when operational per-stage SLOs are finalized.
  2. When future async remote generators (e.g., paid video/image providers) are wired to `PaidOperationGuard`, ensure each adapter invokes `guard.record_external_ref(key, provider_job_id)` immediately upon submit confirmation.
