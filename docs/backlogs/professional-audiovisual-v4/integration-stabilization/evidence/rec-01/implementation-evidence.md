# REC-01 Implementation Evidence — Financial Safety & Resilience (`REC-01.01`, `REC-01.02`, `REC-01.03`)

**Branch:** `develop` | **Base HEAD:** `031811f420ea74376f9a76ad461437b40db76405`  
**Executor:** `rec01-dev` (`Gemini 4 Hydrogen Medium`)  
**External API Spend:** `$0.00` (100% offline/disposable PostgreSQL doubles)  
**Publication Kill Switch:** `publication_enabled=False` (`PublicationResult.BLOCKED` verified before token lookup or upload)  

---

## 1. Red (Pre-Fix) Reproduction on `HEAD 031811f`

Before modifying any production code, a reproduction suite (`tests/test_rec_01_repro_red.py`, subsequently retired) was executed in the canonical disposable PostgreSQL container:

- **Command:** `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh tests/test_rec_01_repro_red.py`
- **Exit Code:** `1` (`3 failed in 0.87s`)
- **Observed Failures:**
  1. **R01:** `AssertionError: R01 REPRO: esperava video_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, mas gravou em aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa com tetos (1000.0, 100.0)` — `PostgresOperationStore.save()` ran `SELECT id FROM studio.videos LIMIT 1` and hardcoded `1000.0/100.0` caps.
  2. **R02:** `AssertionError: R02 REPRO: key drift entre attempt=1 (f3008e34) e attempt=2 (5b6f7f13)` — `compute_deterministic_idempotency_key` included `attempt`, breaking deduplication across retries.
  3. **R03:** `AssertionError: R03 REPRO: ResilientStageExecutor.execute_stage ainda expõe mock_duration_seconds` — parallel unwired executor retained simulated timeout `mock_duration_seconds` and never called `reconciler`.

---

## 2. Files Modified, Added, and Removed

| Status | File | Summary |
|---|---|---|
| **REMOVED** | `renderer/app/studio/adapters/postgres/operation_store.py` | Deleted unsafe INT-04 adapter (`SELECT id FROM studio.videos LIMIT 1`, hardcoded `1000/100` caps, unconditional `UPSERT`, duplicate `usage_ledger` inserts). |
| **ADDED** | `renderer/app/studio/adapters/postgres/migrations/0054_paid_operation_external_ref.sql` | Additive nullable columns `external_reference_id text` and `submitted_at timestamptz` on `studio.paid_operations` with explicit rollback SQL. |
| **MODIFIED** | `renderer/app/studio/application/budget.py` | Added `record_external_ref` and `external_reference_id` to `PaidOperationRepository` and `PaidOperationGuard`. |
| **MODIFIED** | `renderer/app/studio/adapters/postgres/budget_repo.py` | Implemented `record_external_ref` (under `pg_advisory_xact_lock(726002)` + `FOR UPDATE`, idempotent on same ref, `IdempotencyConflict` on mismatch, `InvalidOperationTransition` on terminal states), `external_reference_id`, idempotent `confirm()` on exact settlement replay, and cleared `external_reference_id`/`submitted_at` when reopening `RELEASED`. |
| **MODIFIED** | `renderer/app/studio/domain/resilience.py` | Removed `attempt` from `compute_deterministic_idempotency_key` so retries of the same intent share one stable logical key. |
| **MODIFIED** | `renderer/app/studio/application/resilience.py` | Removed unsafe parallel `OperationStoreProtocol`, `InMemoryOperationStore`, `OperationReconciler`, and `ResilientStageExecutor` (including `mock_duration_seconds`); preserved `SystemReadinessReport` and `ReadinessChecker`. |
| **MODIFIED** | `renderer/app/studio/application/production.py` | Added cooperative timeout/cancellation (`StageContext.cancel_event`, `deadline_monotonic`, `ensure_active()`, bounded thread wait in `_execute_claimed`) and pre-retry reconciliation (`_check_pre_retry_reconciliation` blocking `RESERVED`/`UNCERTAIN` paid ops fail-closed). |
| **MODIFIED** | `renderer/app/studio/composition/wiring.py` | Wired `paid_ops=PostgresPaidOperationRepository(connect) if s.budget_guard else None` into `ProductionCoordinator`. |
| **ADDED** | `tests/test_rec_01_financial_safety.py` | 8 disposable-PostgreSQL tests covering `REC-01.01`, `REC-01.02`, and `REC-01.03` (including 2-connection concurrency barrier, 2-project/2-video isolation, `$0.00` cap, restart, duplicate confirm, stale CAS, unknown cost, pre/post-effect failure, cooperative timeout, late-handler fencing, pre-retry uncertain block, and kill switch). |
| **MODIFIED** | `tests/test_int_04_pipeline.py` | Migrated to canonical `PaidOperationGuard` + `PostgresPaidOperationRepository` + `ProductionCoordinator` cooperative timeout test. |
| **MODIFIED** | `tests/test_v4_reliability_scale.py` | Updated to test stable attempt-free logical keys and `LeaseHeartbeat` fencing without removed parallel classes. |

---

## 3. SQL Constraints & Real Consumer Call Sites Verified

- **PostgreSQL Constraints & Locks:**
  - `pg_advisory_xact_lock(726002)` (`_lock_budget`) serializes `begin`, `confirm`, `release`, `mark_uncertain`, `record_external_ref`, and `reconcile_actual`.
  - `paid_operations_settlement_check` preserved intact (`RESERVED`, `CONFIRMED`, `RELEASED`, `UNCERTAIN`).
  - `usage_ledger_project_attribution` trigger (`assign_ledger_project()`) enforces authoritative `project_id` from `studio.videos`.
  - `0054_paid_operation_external_ref.sql`: `external_reference_id text`, `submitted_at timestamptz` (image migration count aligned: `49` == `49`).
- **Real Consumer Call Sites (`renderer/app/studio/composition/wiring.py`):**
  - `wiring.py:530`: `PaidOperationGuard(PostgresPaidOperationRepository(connect), Decimal(str(s.max_cost_month)), Decimal(str(s.max_cost_video)), limits_for=channel_guard_limits(repo, budget_repo))`
  - `wiring.py:702-705`: `RunPublication(..., enabled=s.publication_enabled)`
  - `wiring.py:744-746`: `ProductionCoordinator(run_repo, ..., paid_ops=paid_ops_repo)`

---

## 4. Negative Test Matrix (All Verified in Disposable PostgreSQL)

| Negative Case | Expected Behavior | Verified Test |
|---|---|---|
| Import `PostgresOperationStore` / `ResilientStageExecutor` / `OperationReconciler` | `ModuleNotFoundError` / absent | `test_rec_01_01_unsafe_operation_store_and_parallel_executor_removed` |
| Paid op (`$0.01`) under `$0.00` ceiling | `BudgetDenied` (`ceiling_usd == 0.00`), 0 submits, 0 ledger rows | `test_rec_01_01_project_video_isolation_and_zero_ceiling` |
| Unknown `video_id` or cross-video key reuse | `ValueError("unknown video...")` / `IdempotencyConflict` | `test_rec_01_01_project_video_isolation_and_zero_ceiling` |
| 2 concurrent PG connections racing same key | Exactly 1 `CREATED`, 1 `IN_PROGRESS` | `test_rec_01_02_concurrent_connections_exclusive_admission_and_budget_race` |
| 2 concurrent PG connections racing `$1.00` cap (`$0.60` each) | Exactly 1 `CREATED`, 1 `DENIED` | `test_rec_01_02_concurrent_connections_exclusive_admission_and_budget_race` |
| Divergent `external_reference_id` or stale state after `CONFIRMED` | `IdempotencyConflict` / `InvalidOperationTransition` | `test_rec_01_02_durable_external_ref_restart_idempotent_confirm_and_stale_cas` |
| Duplicate `confirm()` replay | Idempotent, `COUNT(usage_ledger) == 1` | `test_rec_01_02_durable_external_ref_restart_idempotent_confirm_and_stale_cas` |
| Unknown / `None` cost in `settle` | `OperationUncertain` (`UNCERTAIN`), never `$0.00`, 0 ledger rows | `test_rec_01_02_unknown_cost_never_becomes_zero_and_pre_vs_post_effect_failures` |
| Post-effect ambiguous failure + retry | Moves to `UNCERTAIN`, blocks retry (`double_submit_count == 1`) | `test_rec_01_02_unknown_cost_never_becomes_zero_and_pre_vs_post_effect_failures` |
| Stage retry while paid op is `UNCERTAIN` | Coordinator fails closed before handler (`external_submits == 1`) | `test_rec_01_03_pre_retry_reconciliation_blocks_uncertain_paid_op` |
| Slow handler exceeding `stage_timeouts` | `WorkerStepResult.FAILED`, late handler fenced (`0` ledger rows, `complete_stage` returns `NOT_RUNNING`/`LOST`) | `test_rec_01_03_late_handler_fenced_after_lease_loss_and_timeout` |
| `RunPublication(enabled=False)` | `PublicationResult.BLOCKED`, `token_calls == 0`, `upload_calls == 0` | `test_rec_01_03_publication_kill_switch_blocks_before_token_or_upload` |

---

## 5. Green (Post-Fix) Canonical Container Verification

- **Command:**
  ```bash
  PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh \
    tests/test_rec_01_financial_safety.py \
    tests/test_int_04_pipeline.py \
    tests/test_v4_reliability_scale.py \
    tests/test_paid_operations.py \
    tests/test_budget_reservations.py \
    tests/test_budget_guard.py \
    tests/test_budget_guard_wiring.py \
    tests/test_budget_http.py \
    tests/test_production_coordinator.py \
    tests/test_production_flow_db.py \
    tests/test_lease_heartbeat.py \
    tests/test_lease_recovery_concurrency.py \
    tests/test_publication_execution.py \
    tests/test_db.py \
    tests/test_schema_docs.py \
    tests/test_architecture.py
  ```
- **Container Alignment:** `HEAD=031811f`, `hash renderer/app: checkout=d95e281af8d0ab89 imagem=d95e281af8d0ab89`, `migrações: checkout=49 imagem=49`
- **Result:** `302 passed, 1 warning in 103.60s (0:01:43)`
- **Exit Code:** `0`

---

## 6. Rollback Plan

1. Revert code changes on `develop`: `git revert <commit_sha>` (or `git checkout` of modified files prior to commit).
2. Revert additive migration `0054_paid_operation_external_ref.sql` if applied to a database:
   ```sql
   ALTER TABLE studio.paid_operations DROP COLUMN IF EXISTS submitted_at;
   ALTER TABLE studio.paid_operations DROP COLUMN IF EXISTS external_reference_id;
   DELETE FROM studio.schema_migrations WHERE version = '0054_paid_operation_external_ref';
   ```
