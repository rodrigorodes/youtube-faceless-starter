# REC-00 — Preflight Verification & Repository Inventory Evidence

**Campaign:** V4 Integration & Stabilization Recovery (`PROMPT-MASTER.md`)  
**Wave / Tasks:** `REC-00.01`, `REC-00.02`  
**Executor:** `Gemini 4 Neon (High)` (`rec00-auditor`)  
**Observed Timestamp (UTC):** `2026-11-26T13:55Z–14:05Z`  
**Repository:** `/Users/rodrigomendes/youtube-faceless-starter`  
**Code Modifications Made:** **ZERO** (read-only audit + documentation artifacts under `docs/backlogs/professional-audiovisual-v4/integration-stabilization/` only)  
**External API Cost:** `$0.00` (zero paid calls, zero network calls)  
**Publication Kill Switch:** Verified (`RunPublication.enabled=False` blocks before claim/token/upload; `docker-compose.e2e.yml` sets `STUDIO_PUBLICATION_ENABLED="0"`)

---

## 1. Git & Branch State (G0 Preflight)

**Command:**
```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD HEAD~1 main main^1 main^2
git merge-base develop main
git status --short
git diff --shortstat da1056b..72438e9
git diff --shortstat 0257c04..72438e9
```
**Exit Code:** `0`

**Observed Output:**
```text
branch:       develop (tracking origin/develop)
HEAD:         5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd  (docs(v4): reopen integration recovery with strict 9-point gates and model routing)
HEAD~1:       72438e9ea215bbec12bd350d8c2606ca62bc7d94  (chore(int-07): regressao canonica completa e homologacao dos achados a01-a13)
main:         42700cb331165a68455173a91c463d4733292cfd  (Merge branch 'develop' into main: integracao e estabilizacao V4 (INT-01 a INT-07))
main^1:       be0c463edc55ff567f9149d26c8fd350c803d745  (previous main base referenced in PROMPT-MASTER.md & RECOVERY-REVIEW.md)
main^2:       72438e9ea215bbec12bd350d8c2606ca62bc7d94  (INT-07 tip merged into main)
merge-base:   72438e9ea215bbec12bd350d8c2606ca62bc7d94
git status:   (clean working tree prior to writing REC-00 docs)
diff da1056b..72438e9: 27 files changed, 1376 insertions(+), 72 deletions(-)
diff 0257c04..72438e9: 41 files changed, 1522 insertions(+), 72 deletions(-)
```

**Important Factual Note (G0 Transparency):**
- Historical reopening docs (`PROMPT-MASTER.md:3`, `RECOVERY-REVIEW.md:3`) reference `main` at `be0c463edc55ff567f9149d26c8fd350c803d745`.
- Real repository observation shows `main` is currently at `42700cb331165a68455173a91c463d4733292cfd` (a merge commit of `be0c463` + `72438e9`).
- **Rule Enforcement:** Branch `main` is strictly NOT touched by this recovery campaign. All recovery work proceeds on `develop` (`5800f4618d6ff5afa3fac81a07c60e9e7a89f9bd`+). Any future merge to `main` requires separate explicit operator authorization after REC-04.04.

---

## 2. Host & Container Runtimes Inventory

### 2.1 macOS Host Runtimes (with `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`)

| Runtime / Tool | Observed Path / Status | Observed Version / Detail | Exit Code |
|---|---|---|---|
| Python (pyenv) | `/Users/rodrigomendes/.pyenv/shims/python3` | `Python 3.11.9` | `0` |
| pytest (host) | Python module | `pytest 8.2.0` | `0` |
| Node.js (Homebrew) | `/opt/homebrew/bin/node` | `v26.0.0` | `0` |
| npm / npx (Homebrew) | `/opt/homebrew/bin/npm`, `/opt/homebrew/bin/npx` | `11.12.1` | `0` |
| Playwright (Python) | `/Users/rodrigomendes/.pyenv/versions/3.11.9/lib/python3.11/site-packages/playwright/` | Installed & importable (`playwright.sync_api.sync_playwright`) | `0` |
| Playwright Browsers | `~/Library/Caches/ms-playwright/` | `chromium-1255`, `chromium_headless_shell-1255`, `ffmpeg-1013` present | `0` |
| FFmpeg (host) | `/opt/homebrew/bin/ffmpeg` | `ffmpeg version 9.1` | `0` |
| Piper (host) | Not installed on host (`piper: command not found`) | Available inside Docker container | `127` |
| Docker Engine | `/usr/local/bin/docker` | `Docker 29.1.3` (`Docker Desktop`, `aarch64`) | `0` |

**Key Finding vs Historical Reports:**
- Both `V4-00-BASELINE-REPORT.md:28` and `INT-07-FINAL-REPORT.md:77` assumed Node.js and Playwright were absent on the host.
- **Observed Reality:** Node `v26.0.0`, Playwright Python, and Chromium `1255` ARE installed on the macOS host, and `scripts/run-e2e-full.sh` / `scripts/run-e2e-tests.sh` + `docker-compose.e2e.yml` run real browser tests against an isolated Docker stack on port `8100` (tmpfs DB + tmpfs storage). Browser E2E is **EXECUTABLE**, not blocked by environment!

### 2.2 Canonical Test Container (`faceless-renderer-pytest:test` / `faceless-renderer:test`)

**Command:**
```bash
docker run --rm --entrypoint sh faceless-renderer-pytest:test -c '
python3 --version; pytest --version; ffmpeg -version | head -n 1; ffprobe -version | head -n 1;
which piper; ls -la /opt/voices;
python3 -c "import importlib.util; print(\"kokoro spec:\", importlib.util.find_spec(\"kokoro\"))";
which node && node --version || echo "node: not in container"
'
```
**Exit Code:** `0`

| Runtime / Component | Observed Value |
|---|---|
| Container Image (`faceless-renderer-pytest:test`) | Image ID `cbeba9e7b44c` (`1.42GB`) |
| Base Image (`faceless-renderer:test`) | Image ID `5a018a272ede` (`1.29GB`) |
| Postgres Image (`postgres:16-alpine`) | Image ID `81e77a483348` (`412MB`) |
| Checkout vs Image Tree Hash (`renderer/app/*.py,*.sql`) | `HOST_TREE=02efa18bc76d3e9d` == `IMAGE_TREE=02efa18bc76d3e9d` (**MATCH**) |
| Checkout vs Image Migrations Count | `HOST_MIG=48` == `IMAGE_MIG=48` (**MATCH**) |
| Python | `Python 3.12.16` |
| pytest | `pytest 8.3.5` |
| FFmpeg | `ffmpeg version 7.1.5-0+deb13u1` (with `--enable-libass`, `ebur128`, `silencedetect`, `blackdetect`, `freezedetect`) |
| FFprobe | `ffprobe version 7.1.5-0+deb13u1` |
| Piper | `/usr/local/bin/piper` + `/opt/voices/pt_BR-faber-medium.onnx` (`63,221,984` bytes) + `.onnx.json` (`6,257` bytes) |
| Kokoro | `importlib.util.find_spec("kokoro")` → `None` (NOT installed, zero local weights) |
| Node.js | Not installed in Debian slim container (explains the 17 Node-dependent skips inside container; executable on host!) |

---

## 3. Environment Isolation, Ports, Disposable DB & Kill Switch Verification

### 3.1 Host Dev Ports (Read-Only Check — Untouched)
```text
lsof -nP -iTCP:8000 -sTCP:LISTEN -> com.docker PID 32812 TCP 127.0.0.1:8000 (LISTEN)
lsof -nP -iTCP:5678 -sTCP:LISTEN -> com.docker PID 32812 TCP 127.0.0.1:5678 (LISTEN)
```
- **Policy:** Dev stack ports `8000` (Studio DEV) and `5678` (n8n DEV) are active on host and MUST NEVER be touched.
- **Isolation Enforcement:**
  - `scripts/test-container.sh` creates an ephemeral Docker network `faceless-test-net-$$` and `postgres:16-alpine` container on `--tmpfs /var/lib/postgresql/data` with NO host port exposed, mounts checkout `:ro`, and tears everything down in `trap cleanup EXIT`.
  - `scripts/run-e2e-full.sh` and `scripts/run-e2e-tests.sh` (`tests/e2e_ux/conftest.py:24-30`) explicitly refuse port `8000` unless `STUDIO_E2E_ALLOW_DEV=1` and run an isolated Compose project (`faceless-e2e-$$`, `docker-compose.e2e.yml`) on port `8100` with tmpfs Postgres and tmpfs storage.

### 3.2 Disposable DB Guard Proof
- Verified in `scripts/test-container.sh:74-110` and `tests/conftest.py:10-46,78-107`:
  - `scripts/test-container.sh` generates a 64-hex random proof mounted read-only into Postgres at `/budget-test-proof/proof` and into the test runner at `/proof/proof`, setting `STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN`, and `STUDIO_BUDGET_TEST_PROOF_FILE=/proof/proof`.
  - `tests/conftest.py::verified_test_connect()` enforces single explicit host, forbids `PGHOSTADDR`/`PGSERVICE` redirection, executes `SELECT pg_read_file('/budget-test-proof/proof')` on every physical connection, and verifies constant-time equality (`secrets.compare_digest`) before allowing `DROP SCHEMA IF EXISTS studio CASCADE` or any write.

### 3.3 Publication Kill Switch & $0.00 Budget Ceiling
- **Kill Switch (`RunPublication.execute`):**
  - `renderer/app/studio/composition/wiring.py:702-705`: passes `enabled=s.publication_enabled` into `RunPublication`.
  - `renderer/app/studio/application/publication_execution.py:271-273`: checks `if not self.enabled: return PublicationRun(PublicationResult.BLOCKED, detail="publication is disabled by configuration (STUDIO_PUBLICATION_ENABLED=0)")` **before** `_claimed()`, `_prepare()`, token retrieval, or `YouTubeUploader.upload()`.
  - `docker-compose.e2e.yml:41`: sets `STUDIO_PUBLICATION_ENABLED: "0"`.
  - **Config Caution Noted:** `renderer/app/studio/composition/settings.py:71,101` defaults `publication_enabled=True` (`STUDIO_PUBLICATION_ENABLED` default `"1"`) and `budget_guard=False` (`STUDIO_BUDGET_GUARD` default unset). All REC tests/pilots MUST explicitly pass `publication_enabled=False` (`STUDIO_PUBLICATION_ENABLED=0`), `budget_guard=True` (`STUDIO_BUDGET_GUARD=1`), and `max_cost_video=0.0`, `max_cost_month=0.0` (note: `docker-compose.e2e.yml:40` currently has `STUDIO_BUDGET_GUARD: "0"` — REC-03/04 isolated runs should explicitly verify `STUDIO_BUDGET_GUARD=1` & $0.00 ceiling where applicable).

---

## 4. Quantitative Codebase, Migration, Test & Phase Inventory

### 4.1 Counts Verified by Direct Inspection
| Category | Verified Count | Command / Source |
|---|---:|---|
| Original V4 Phase Docs (`phases/V4-00`..`V4-13`, excl. `REPORT.md`) | **14** | `V4-00`..`V4-13` |
| Original V4 Activity IDs (`V4-XX.YY`) | **227** | Python regex extraction across all 14 phase files (`225` checked `[x]` historically, `2` unchecked `[ ]`: `V4-00.06`, `V4-13.11`) |
| GAI Backlog Items (`GAI-01`..`GAI-09`) | **9** | `GAI-EXECUTION-PLAN.md` |
| Historical Audit Findings (`A01`..`A13`) | **13** | `AUDIT-FINDINGS.md` |
| Historical INT Backlog Items (`INT-01.01`..`INT-07.02`) | **21** | `EXECUTION-BACKLOG.md` |
| Recovery Review Findings (`R01`..`R13`) | **13** | `RECOVERY-REVIEW.md` |
| Recovery Backlog Items (`REC-00.01`..`REC-04.04`) | **17** | `RECOVERY-BACKLOG.md` |
| PostgreSQL Migrations (`renderer/app/studio/adapters/postgres/migrations/*.sql`) | **48** | `0001_init.sql` .. `0053_usage_ledger_category.sql` (numbering gaps at 0009, 0024, 0025, 0029, 0030) |
| Test Files (`tests/**/test_*.py`) | **276** | `find tests -name 'test_*.py' \| wc -l` |
| Canonical Container Collected Tests (`--collect-only`, excl. `e2e_full`/`e2e_ux`) | **4,416** | `docker run ... pytest tests --ignore=tests/e2e_full --ignore=tests/e2e_ux --collect-only -q` (`exit 0`, `5.97s`) |
| Host Browser E2E Collected Tests (`tests/e2e_ux` + `tests/e2e_full`) | **26** | `pytest tests/e2e_ux tests/e2e_full --collect-only -q` (`exit 0`, `0.03s`) |

### 4.2 Original V4 Activity Breakdown by Phase (Exact Real Count = 227)
| Phase | File | Activity ID Range | Real Count | Historically `[x]` | Historically `[ ]` |
|---|---|---|---:|---:|---:|
| V4-00 | `phases/V4-00-baseline.md` | `V4-00.01`..`V4-00.10` | 10 | 9 | 1 (`V4-00.06`) |
| V4-01 | `phases/V4-01-providers.md` | `V4-01.01`..`V4-01.12` | 12 | 12 | 0 |
| V4-02 | `phases/V4-02-voice.md` | `V4-02.01`..`V4-02.15` | 15 | 15 | 0 |
| V4-03 | `phases/V4-03-audio.md` | `V4-03.01`..`V4-03.18` | 18 | 18 | 0 |
| V4-04 | `phases/V4-04-composition.md` | `V4-04.01`..`V4-04.20` | 20 | 20 | 0 |
| V4-05 | `phases/V4-05-visual-motion.md` | `V4-05.01`..`V4-05.32` | 32 | 32 | 0 |
| V4-06 | `phases/V4-06-intelligence.md` | `V4-06.01`..`V4-06.12` | 12 | 12 | 0 |
| V4-07 | `phases/V4-07-synchronization.md` | `V4-07.01`..`V4-07.12` | 12 | 12 | 0 |
| V4-08 | `phases/V4-08-render.md` | `V4-08.01`..`V4-08.14` | 14 | 14 | 0 |
| V4-09 | `phases/V4-09-quality.md` | `V4-09.01`..`V4-09.18` | 18 | 18 | 0 |
| V4-10 | `phases/V4-10-studio-ux.md` | `V4-10.01`..`V4-10.20` | 20 | 20 | 0 |
| V4-11 | `phases/V4-11-assets.md` | `V4-11.01`..`V4-11.14` | 14 | 14 | 0 |
| V4-12 | `phases/V4-12-reliability.md` | `V4-12.01`..`V4-12.16` | 16 | 16 | 0 |
| V4-13 | `phases/V4-13-pilot.md` | `V4-13.01`..`V4-13.14` | 14 | 13 | 1 (`V4-13.11`) |
| **TOTAL** | **14 phase files** | **All real IDs** | **227** | **225** | **2** |

---

## 5. Baseline Artifacts in `storage/output/` (Observed SHA-256 & Sizes)

**Command:**
```bash
find storage/output -maxdepth 3 -type f | sort | while read -r f; do
  sz=$(stat -f%z "$f"); sha=$(shasum -a 256 "$f" | awk '{print $1}'); echo "$sz $sha $f";
done
```
**Exit Code:** `0`

| File Path | Size (Bytes) | SHA-256 | Notes |
|---|---:|---|---|
| `storage/output/.gitkeep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Empty placeholder |
| `storage/output/frames_pilot_v4/frame_01_17s.png` | 161,392 | `28891a41df2727af4792bcaa94ae1d573012db22c6f18956bff857cfd0031f7c` | Baseline frame 17s |
| `storage/output/frames_pilot_v4/frame_02_69s.png` | 153,106 | `c98f8d50c4f8dfbdcbee4dc91c1aadd68a3c028a00e7e75a9050ab5803f67769` | Baseline frame 69s |
| `storage/output/frames_pilot_v4/frame_03_138s.png` | 181,196 | `7990cccb5570aa87d905d071f362902ef6c79c424644dc63f49bf090f2c79d08` | Baseline frame 138s |
| `storage/output/frames_pilot_v4/frame_04_207s.png` | 178,320 | `b4420c18483f3dc61b3a7b617d02ab22e4d7876b65a4b8881a6f012c55dd891b` | Baseline frame 207s |
| `storage/output/frames_pilot_v4/frame_05_276s.png` | 163,269 | `7bef3a522a28a020e37f7432edd5215724f7f74b961318dc5f6a1e4473db4091` | Baseline frame 276s |
| `storage/output/frames_pilot_v4/frame_06_328s.png` | 173,169 | `61f23743f6f5512216b0e5cd86edc8cd61bfc312b4032ac0c4b3273a86c014a5` | Baseline frame 328s |
| `storage/output/runs/run_20261125_213805/v4_baseline_metrics.json` | 4,344 | `24bd8b69d2e866651b12bde2aaffecebbaff7da6e8c77ea64ff1003e890560d5` | Matches `phases/v4_baseline_metrics.json` (2026-11-25) |
| `storage/output/runs/run_20261125_213805/v4_fixture_tecnica_60s.mp4` | 9,167,665 | `904eb8c9b801251ba222cd8f93d180c74c98900c0f1f03cd35399ac656516c04` | V4-00 Report 63.52s fixture |
| `storage/output/runs/run_20261125_213805/v4_piloto_audiovisual_5min.mp4` | 47,798,249 | `9b20e2e749127ccd6ce6aeb4f1d5cf029d31840b338b807aa0aba71b45a1ba6f` | V4-00 Report 345.60s pilot |
| `storage/output/runs/run_20261126_132447_198e47cb/v4_baseline_metrics.json` | 4,720 | `f22a729799468b32674e538a50f13104b593772b220a39b90e5a25163ab98b24` | Re-run 2026-11-26 (63.48s / 345.80s) |
| `storage/output/runs/run_20261126_132447_198e47cb/v4_fixture_tecnica_60s.mp4` | 9,188,011 | `30cd262d2cd3e9f3891edb91dcb33b5d5ec846627acda0067ee4f259e59738d6` | Re-run 63.48s fixture (-16.5 LUFS, -3.0 dBTP) |
| `storage/output/runs/run_20261126_132447_198e47cb/v4_piloto_audiovisual_5min.mp4` | 47,709,601 | `48886a202a8b3ae205d9e0681019786b269a65455dbcb40de3f5c7ed14e70756` | Re-run 345.80s pilot (-15.6 LUFS, -1.3 dBTP) |
| `storage/output/v4_baseline_metrics.json` | 4,720 | `f22a729799468b32674e538a50f13104b593772b220a39b90e5a25163ab98b24` | Copy of `run_20261126_132447_198e47cb` |
| `storage/output/v4_fixture_tecnica_60s.mp4` | 9,188,011 | `30cd262d2cd3e9f3891edb91dcb33b5d5ec846627acda0067ee4f259e59738d6` | Copy of `run_20261126_132447_198e47cb` |
| `storage/output/v4_piloto_audiovisual_5min.mp4` | 47,709,601 | `48886a202a8b3ae205d9e0681019786b269a65455dbcb40de3f5c7ed14e70756` | Copy of `run_20261126_132447_198e47cb` |

**Baseline Note for REC-04.02:** Both V4-00 baseline runs exist locally on disk (`run_20261125_213805` cited in `V4-00-BASELINE-REPORT.md` and `run_20261126_132447_198e47cb` current root copy). Neither has human audiovisual approval yet (`V4-00.06` remains `AWAITING_HUMAN_REVIEW`). Paired comparison in `REC-04.02` must lock the exact baseline run SHA and hardware/config (or execute a controlled rebaseline on the same SHA/container).
