# REC-03.01 & REC-03.02 Independent Review — Round 2 (`github-copilot/gemini-4-neon`, High)

- **Reviewer / Real Model:** Independent Reviewer (Round 2, fresh session) — `github-copilot/gemini-4-neon` (high)
- **Target Slice:** `REC-03.01` & `REC-03.02` (`R08`, `GAI-01` routes/preview, `GAI-02` assisted mode, `G5` browser UX)
- **Repository / Branch:** `/Users/rodrigomendes/youtube-faceless-starter` on `develop` (`main` untouched @ `42700cb331165a68455173a91c463d4733292cfd`)
- **Base HEAD:** `3ca1f8512eb4681b97c4e5ecf3ee9ba61fae95b8` + uncommitted working tree (strictly read-only review; zero production/test edits, zero commits/pushes)
- **Reviewed Artifact Hashes (SHA-256):**
  - `git diff` (full working tree): `06c1a61edc331bf9adeed5cf49353ef175c9bbd32900a1bc223860883a51c727`
  - `git diff renderer/`: `3e03d3f5c531a3a0455ac86f38bf5f72d21a149706eaee3247a8daac9ec5d46b`
  - `tests/test_rec_03_studio_routes.py`: `d188d0e8aae3ecb56ca16dac11093a59b03e76b7abff79c73e1f10629da43466`
  - `tests/test_storyboard_js.py`: `242702b6d450af2f73ed87b1a99bbd511622cb15fd840ed5d1c57eb269a44dce`
  - `tests/e2e_ux/test_rec_03_studio_browser.py`: `80f0415e9033560e55f7a5d14949b28b06f909d0b6e0c8cd96db7665347a1b3a`
  - `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-03/rec-03-01-02-ux-browser-evidence.md`: `ac7925a8e25e43d015f35b1d9259871991e8132770f57131e9a45d5937d34841`
- **External Paid API Spend:** `$0.00` | **Publication Kill Switch:** `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`) | **DEV Ports (`8000`/`5678`):** untouched
- **Review Round:** Round 2 (re-evaluation after Round 1 `REJECTED` in `rec-03-01-02-independent-review-neon-high.md`)
- **Final Decision:** **`REJECTED`**
  - `REC-03.01`: **`7.475 / 10`** (min dimension `7.0` < `9.0`)
  - `REC-03.02`: **`7.750 / 10`** (min dimension `5.5` < `9.0`)
  - Open Blockers: **`0` P0, `4` P1** (including **2 absolute rubric blocks**: tautological Node JS tests in `tests/test_storyboard_js.py` that never execute `STORYBOARD_JS`, and relaxed status tuples / conditional guards in `tests/test_rec_03_studio_routes.py` & `tests/e2e_ux/test_rec_03_studio_browser.py`), plus **`6` P2** items.

---

## 1. Independent Verification Re-Executed

All commands were executed independently on the exact working tree above with:
`export PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`

### 1.1 Host Node.js / Panel Suite + JS Syntax Check
- **Command 1 (Host pytest):**
  ```bash
  python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
    tests/test_falha_producao.py tests/test_publicacao_acao.py tests/test_workflow_analytics.py \
    tests/test_workflow_publish.py tests/test_workflow_trends.py -v
  ```
  - **Observed Result:** `100 passed in 3.41s` | **Exit code:** `0`
- **Command 2 (Direct `node --check` on production JS strings):**
  ```bash
  python3 -c "import subprocess, sys; sys.path.insert(0, 'renderer'); from app.studio.api.panel_video_storyboard_js import STORYBOARD_JS, RUN_JS; [print(n, subprocess.run(['node', '--check'], input=c, text=True, capture_output=True).returncode) for n, c in [('STORYBOARD_JS', STORYBOARD_JS), ('RUN_JS', RUN_JS)]]"
  ```
  - **Observed Result:** `STORYBOARD_JS exit= 0`, `RUN_JS exit= 0` | **Exit code:** `0`
- **Forensic Note:** Although all 100 host tests passed, `tests/test_storyboard_js.py` **never executes `STORYBOARD_JS` in Node.js** — all 3 Node eval tests run copy-pasted toy functions defined inside the test file (see §4, P1 #1).

### 1.2 Focused Container Suite (API / Security / Architecture)
- **Command:**
  ```bash
  ./scripts/test-container.sh \
    tests/test_rec_03_studio_routes.py tests/test_media_api.py tests/test_media_swap_api.py \
    tests/test_video_storyboard_v3.py tests/test_panel_scene_multimedia.py tests/test_v4_studio_ux.py \
    tests/test_ux_contract.py tests/test_studio_browser_security.py tests/test_architecture.py
  ```
- **Alignment Check:** `HEAD=3ca1f85 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=ebc3edc8a63d3fe4 imagem=ebc3edc8a63d3fe4`, `migrações: checkout=49 imagem=49`
- **Observed Result:** `86 passed, 1 warning in 23.17s` | **Exit code:** `0`

### 1.3 Full Canonical Container Suite (Regression Sweep)
- **Command:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alignment Check:** `HEAD=3ca1f85 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=ebc3edc8a63d3fe4 imagem=ebc3edc8a63d3fe4`, `migrações: checkout=49 imagem=49`
- **Observed Result:** `4487 passed, 25 skipped, 1 warning in 797.02s (0:13:17)` | **Exit code:** `0`
- **Skip Reconciliation (`25 skipped`):** Zero unexpected skips and zero regressions across the entire canonical suite. All 25 skips are environment-specific inside the Python-only container image:
  - `22` Node.js-only host tests (`test_erro_js.py` [6], `test_storyboard_js.py` [5], `test_publicacao_acao.py` [4], `test_workflow_analytics.py` [2], `test_workflow_trends.py` [2], `test_falha_producao.py` [1], `test_panel.py` [1], `test_workflow_publish.py` [1] — all executed on host in §1.1).
  - `3` Playwright-only tests (`test_reference_browser.py` [1], `tests/ve08/test_composition_functional.py` [1], `tests/ve08/test_storyboard_functional.py` [1]).

### 1.4 Isolated Playwright Chromium E2E (`docker-compose.e2e.yml`, Port `8100`, `tmpfs`)
- **Commands:**
  ```bash
  E2E_PORT=8100 docker compose -p faceless-e2e-rec03r2 -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 \
  STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
  STUDIO_E2E_USER="e2e" \
  STUDIO_E2E_PASSWORD="e2e-senha-descartavel" \
  python3 -m pytest tests/e2e_ux/test_rec_03_studio_browser.py -v -s
  docker compose -p faceless-e2e-rec03r2 -f docker-compose.e2e.yml down -v
  lsof -i :8100
  ```
- **Observed Result:** `1 passed in 8.60s` | **Exit code:** `0`
- **Teardown Proof:** Containers `faceless-e2e-rec03r2-renderer-e2e-1`, `faceless-e2e-rec03r2-postgres-e2e-1` and network `faceless-e2e-rec03r2_default` stopped and removed (`down -v`); `lsof -i :8100` returned empty (`PORT_8100_CLOSED`); `lsof -i :8000 -i :5678` confirmed DEV stack untouched.

---

## 2. Round 1 Finding-by-Finding Verification Matrix

| Round 1 Finding | Status in Round 2 | Forensic Verification (`file:line`) |
|---|---|---|
| **P1 #1:** Browser E2E tautologies (`readyState >= 0`, empty `if undo_btn.is_enabled()`, missing add/reorder/CAS/Node tests) | **PARTIALLY RESOLVED → NEW P1** | `test_rec_03_studio_browser.py:198-200, 222-224` now strictly asserts `readyState >= 1` & `videoWidth > 0` before & after reload, plus `video/mp4` + `Accept-Ranges`; `lines 260-300` strictly test Undo/Redo/Reload via `_flush_sb(page)`; `lines 226-258, 320-395` test add/reorder, `CC-BY-4.0`, corrupt upload, and CAS 409. **Still blocked:** `tests/test_storyboard_js.py` never executes `STORYBOARD_JS` in Node (P1 #1), and `test_rec_03_studio_browser.py:156, 204, 306, 332` retain conditional guards (`if btn_gerar_faltante...`) and weakened `or "?v="` asserts (P1 #4). |
| **P1 #2:** Relaxed `in (413, 422)` assert & unbounded RAM read | **RESOLVED** | `routes.py:1690-1698` implements `_read_stream_with_cap` aborting immediately upon `total > max_bytes`; `routes.py:1712` accounts for multipart overhead (`+64KB`) while capping `len(file_bytes) > MAX_IMPORT_BYTES` (`line 1814`). `test_rec_03_studio_routes.py:244-273` strictly asserts `== 413` for both `Content-Length` and chunked streaming (`monkeypatch` cap `500` bytes). |
| **P1 #3:** Dead `mute_audio`, broken trim re-import (`uq_scene_asset_pos`), unusable `CC-BY-4.0` UI | **PARTIALLY RESOLVED → RESIDUAL P1** | `mute_audio` cleanly removed across `renderer/` (0 residual refs, v1/v2 intact); `CC-BY-4.0` `attribution`/`source_url` inputs wired in inline (`panel_video_workspace.py:738-745`) & modal (`panel_video_storyboard_js.py:485-486`) and tested (`test_rec_03_studio_routes.py:647-696`). Trim validation & re-import with trim (`save_scene_assets`) works (`lines 586-645`). **Residual P1 #3:** re-importing a scene *without* trim leaves stale `studio.scene_assets` pointing to the old `asset_id` & old trim (`routes.py:1867-1881`), hydrating stale trim on reload and keeping `AssetFile` authorization open for the replaced asset; direct `uc.editorial.get_script.scripts` repo access and `except Exception: pass` remain in `routes.py:1877-1881, 2327-2334`. |
| **P1 #4:** Security & Clean Architecture (`AssetFile` scope, CRLF, MIME spoofing, malformed JSON, traversal tests) | **PARTIALLY RESOLVED → RESIDUAL P1** | CRLF rejected with `400` (`routes.py:1708-1709`), `boundary=` checked & specific exceptions caught (`1733-1739`), malformed/non-dict JSON returns `422` (`1774-1779`), `text/plain` no longer rewritten (`1829`), `AssetFile` extracted to `application/media.py:383-443` and wired in `wiring.py:581` (`test_architecture.py` `9/9`). **Residual P1 #2 & #4:** `AssetFile` `project_id`-only branch calls non-existent `self.videos.list_by_project` (`media.py:424`, always returns `403`), `self.assets.get(asset_id)` runs before scope check (existence oracle), `test_rec_03_studio_routes.py:510, 514, 538` still use relaxed `in (404, 422)` / `in (415, 422)`, and real `AssetFile` storage-root traversal & `import-media` NUL/traversal filename tests are missing. |
| **P1 #5:** Stale preview cache, `assisted-prompt` overwrite, `9:16` hardcoded, `asset_kind` loss, `queue`/`tmp-*` race | **RESOLVED** (minor P2 polish) | `?v=<asset_id>` added (`panel_video_storyboard_js.py:43`, `panel_video_workspace.py:687-693`); dirty `assisted-prompt` preserved (`118-128, 402-407`); `D.format === 'long'` → `16:9` vs `9:16` (`panel_video_workspace.py:705, 886, 898`, JS `122, 472`); `asset_kind` preserved across `applyScript`/`reconcile`/`pickAsset`/`pickCandidate`/`doImportMedia` and `<video>` used in `mediaTab === 'video'` (`461-467`); `doImportMedia` serialized on `queue` with `tmp-*` resolution (`612-619`) and modal reads explicit `modal-*` fields (`570-591`). |

---

## 3. Rubric Scoring (`QUALITY-RUBRIC.md`)

> Threshold: `>= 9.0` on **every** applicable dimension, weighted mean `>= 9.0` (no rounding), and **zero** P0/P1 blockers or absolute blocks.

### 3.1 `REC-03.01` — Studio Upload/Preview/Association, Assisted Mode (`GAI-02`), Editing/Missing Generation

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 7.5 | Forte avanço vs Round 1: `mute_audio` removido sem resíduos/quebra de v1/v2; `CC-BY-4.0` com `attribution`/`source_url` (inline + modal); `?v=<asset_id>` cache-busting; `assisted-prompt` com dirty-tracking e `16:9`/`9:16` dinâmico; `asset_kind` preservado; `doImportMedia` na `queue`; `PlanFfmpegRenderer` validado em MP4 real; 4487/4487 testes canônicos sem regressão. **Bloqueado por P1s:** `GET /studio/assets/{id}/file?project_id=...` falha sempre com `403` pois `VideoRepository` não implementa `list_by_project` (`application/media.py:424`); reimportação de cena **sem** trim mantém linha obsoleta em `studio.scene_assets` do asset anterior (`routes.py:1867-1881`), reidratando trim antigo no reload (`routes.py:2327-2334`). |
| Arquitetura e simplicidade | 20% | 7.5 | `AssetFile` extraído para `application/media.py` e conectado em `wiring.py`; `test_architecture.py` `9/9`; sem nova SPA nem serviço paralelo; CSP-safe. **Penalizado (P1 #2, #3):** `routes.py:1867-1881` ainda persiste `SceneAsset` diretamente via `uc.editorial.get_script.scripts` fora do caso de uso/transação de `ImportExternalMedia`; `routes.py:2327-2334` volta a acessar `uc.editorial.get_script.scripts.get_scene_assets` dentro de `except Exception: pass`; `AssetFile` usa `hasattr(self.videos, "list_by_project")` para método inexistente no port `VideoRepository`. |
| Testes e regressão | 20% | 7.0 | Reexecução independente: Host `100 passed` (exit `0`), Container focado `86 passed` (exit `0`), Suíte canônica completa `4487 passed, 25 skipped` (exit `0`, zero regressões). Streaming `413`, CRLF `400`, JSON malformado `422`, `CC-BY-4.0` e trim re-import cobertos. **Bloqueado por P1 #4:** `test_rec_03_studio_routes.py:510, 514, 538` ainda usam tuplas relaxadas `in (404, 422)` e `in (415, 422)`; teste de `project_id` (`line 475`) passa `video_id` junto e mascara a quebra do ramo `elif project_id:`; faltam testes reais de traversal em `AssetFile` (`asset.path = "../../etc/passwd"`), filename traversal/NUL em `import-media`, e limpeza de `scene_assets` ao reimportar sem trim. |
| Segurança, orçamento e confiabilidade | 20% | 7.5 | `_read_stream_with_cap` aborta streaming sem estourar memória (`routes.py:1690-1698`); CRLF rejeitado (`400`); `text/plain` não é mais reescrito; auth `401`/`403`, ownership `404`, CAS `409`, `$0.00` gasto, kill switch `STUDIO_PUBLICATION_ENABLED=0`. **Bloqueado por P1 #2, #3:** `scene_assets` obsoleto após reimportação sem trim permite que `AssetFile` (`media.py:413-417`) continue autorizando download de asset já substituído; `AssetFile.execute` (`media.py:398-406`) consulta `self.assets.get(asset_id)` antes de validar o escopo, criando oráculo `403` vs `404` entre projetos/vídeos. |
| Evidências e operação | 15% | 8.0 | Evidência de Round 2 documenta comandos, saídas, isolamento de portas (`8000`/`5678` intactas) e `$0.00`. **Penalizado:** afirma que escopo `project_id` e traversal em `AssetFile` estão validados e que `test_storyboard_js.py` valida `STORYBOARD_JS` em Node; `EXECUTION-LOG.md` e `MODEL-USAGE.md` ainda mantêm contagens antigas de Round 1 (`95`/`74`). |

- **Média ponderada exata (`REC-03.01`):**
  `7.5*0.25 + 7.5*0.20 + 7.0*0.20 + 7.5*0.20 + 8.0*0.15 = 1.875 + 1.500 + 1.400 + 1.500 + 1.200 =` **`7.475 / 10`**
- **Gates aplicáveis:** G0 (PASS), G1 (FAIL), G2 (FAIL), G4 (FAIL), G6 (PASS na regressão canônica `4487 passed, 0 failed`)
- **Decisão `REC-03.01`:** **`REJECTED`**

---

### 3.2 `REC-03.02` — Isolated Browser E2E (Node/Playwright, Desktop + Mobile, Real Path & Negatives, Zero Edit Loss)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 8.5 | Grande avanço no Playwright real (`docker-compose.e2e.yml` porta `8100`, `tmpfs`, Desktop `1280x800` + Mobile `390x844`, `1 passed in 8.60s`): prova upload PNG + reload, upload MP4 com `readyState >= 1` & `videoWidth > 0` antes e após reload + `video/mp4` + `Accept-Ranges: bytes`, Add/Reorder de cenas, Undo (`orig_text`) / Redo (`new_text`) / reload com `window.__sbFlush()` e assets irmãos intactos, e negativos de browser (`CC-BY-4.0`, arquivo corrompido, CAS `409`). **Lacunas:** Step 6 (`#btn-gerar-faltante`) protegido por `if ...` (`line 306`) e Step 4 não afirma persistência da cena adicionada após reload. |
| Arquitetura e simplicidade | 20% | 8.5 | Reúsa `docker-compose.e2e.yml`, `Journey`, `helpers.py` e `window.__sbFlush()` com teardown determinístico (`down -v`, porta `8100` fechada) sem tocar `8000`/`5678` nem `main`. Penalizado porque `tests/test_storyboard_js.py` duplica trechos de JS no próprio teste em vez de executar o `STORYBOARD_JS` real. |
| Testes e regressão | 20% | 5.5 | **Bloqueio absoluto (`QUALITY-RUBRIC.md` — teste tautológico/relaxado):** `tests/test_storyboard_js.py` **nunca executa `STORYBOARD_JS` em Node.js** — os 3 testes Node (`lines 58-100, 103-145, 164-213`) rodam funções copiadas dentro do próprio teste e `lines 44-56` constroem uma string com `STORYBOARD_JS` sem nunca passá-la ao `node`! Adicionalmente, `test_rec_03_studio_browser.py` mantém guardas condicionais `if btn_gerar_faltante.is_visible() and btn_gerar_faltante.is_enabled():` (`line 306`), `if attribution_input.is_visible():` (`line 332`) e asserts enfraquecidos `or "?v=" in img_src`/`vid_src` (`lines 156, 204`). |
| Segurança, orçamento e confiabilidade | 20% | 8.5 | Stack 100% descartável (`faceless-e2e-rec03r2`), `STUDIO_PUBLICATION_ENABLED=0`, `$0.00`, `j.assert_clean()` sem erros de console/página, negativos de licença/corrupção/CAS `409` reais no Chromium. Pequena dedução pela guarda condicional em `attribution_input` e ausência de execução Node real do `STORYBOARD_JS`. |
| Evidências e operação | 15% | 7.5 | Comandos, saída e fechamento da porta `8100` corretos; penalizado porque `rec-03-01-02-ux-browser-evidence.md:76-96` apresenta `tests/test_storyboard_js.py` como validação Node real do `STORYBOARD_JS` apesar de zero linhas do `STORYBOARD_JS` serem executadas pelo Node. |

- **Média ponderada exata (`REC-03.02`):**
  `8.5*0.25 + 8.5*0.20 + 5.5*0.20 + 8.5*0.20 + 7.5*0.15 = 2.125 + 1.700 + 1.100 + 1.700 + 1.125 =` **`7.750 / 10`**
- **Gates aplicáveis:** G0 (PASS), G1 (FAIL), G5 (FAIL pelo bloqueio absoluto nos testes Node/condicionais)
- **Decisão `REC-03.02`:** **`REJECTED`**

---

## 4. Detailed Findings (P0 / P1 / P2)

### P0 Findings (Critical)
- None.

### P1 Findings (Mandatory Blockers — Must Be Fixed Before Round 3 Re-Review)

1. **[P1 — Absolute Block: Tautological Node.js Tests That Never Execute Production `STORYBOARD_JS` (`REC-03.02`, `G5`)]**
   - **Locations:**
     - `tests/test_storyboard_js.py:44-56` (`test_storyboard_js_thumb_html_renders_video_for_video_and_img_for_image` builds a `script` string containing `STORYBOARD_JS` and never calls `_run_node_script`)
     - `tests/test_storyboard_js.py:58-100` (`test_node_eval_thumb_html_and_asset_url` hardcodes its own copy of `assetUrl` and `thumbHtml`)
     - `tests/test_storyboard_js.py:103-145` (`test_storyboard_js_preserves_dirty_assisted_prompt_in_node` invents a standalone `fillAssistedPrompt` helper inside the test)
     - `tests/test_storyboard_js.py:164-213` (`test_storyboard_js_apply_script_preserves_asset_kind_and_trim_in_node` hardcodes its own copy of `applyScript`)
   - **Evidence:** Zero lines of the real `STORYBOARD_JS` string are parsed or executed by Node.js anywhere in `tests/test_storyboard_js.py` (contrast with `tests/test_erro_js.py:21-26`, which runs the real `ERRO_JS` directly in `node -e`). Even introducing a syntax error or breaking `thumbHtml`/`assetUrl`/`applyScript`/`fillCard` inside `panel_video_storyboard_js.py` would still leave those 3 Node tests green.
   - **Required Fix:**
     - Run `node --check` on `STORYBOARD_JS` and `RUN_JS`.
     - Execute the **actual** `STORYBOARD_JS` inside Node.js (using a lightweight DOM/fetch harness or exposing testable hooks from `STORYBOARD_JS` initialized with `#storyboard`, `#storyboard-data`, `#storyboard-cards`, `#scene-card-template`) to verify real behavior of `assetUrl` (`?v=<asset_id>`), `thumbHtml` (`<video>` vs `<img>` vs empty), `fillCard` dirty `assisted-prompt` preservation & `16:9` vs `9:16` format, `applyScript`/`pickAsset` preserving `asset_kind` and trim, and `doImportMedia` error/queue/success behavior.

2. **[P1 — Broken `project_id`-Only Scope & Asset Existence Oracle in `AssetFile` (`REC-03.01`, `G1`, `G4`)]**
   - **Locations:**
     - `renderer/app/studio/application/media.py:393-436` (`AssetFile.execute`, specifically `lines 398-406` and `418-433`)
     - `renderer/app/studio/application/ports.py:146-174` & `renderer/app/studio/adapters/postgres/repo.py` (`list_by_project` does not exist)
     - `tests/test_rec_03_studio_routes.py:474-476` (only tests `?video_id=...&project_id=...`, never `?project_id=...` alone)
   - **Evidence:**
     - `AssetFile.execute` checks `if hasattr(self.videos, "list_by_project"):` (`media.py:424`), which is always `False` on `PostgresVideoRepository`. Therefore, `GET /studio/assets/{asset_id}/file?project_id={PROJECT_ID}` **always returns HTTP `403`** even for valid assets owned by that project (and the dead branch also omits `scene_assets`).
     - `asset = self.assets.get(asset_id)` (`media.py:398`) runs *before* scope authorization, returning `404` if `asset_id` does not exist and `403` if it exists in another video/project — an `asset_id` existence oracle across tenants/projects.
   - **Required Fix:**
     - Either implement real project-scoped lookup via a declared port method on `VideoRepository`/`AssetRepository` (checking both `studio.scenes.asset_id` and `studio.scene_assets.asset_id` joined to `studio.videos.project_id`) and test `?project_id={PROJECT_ID}` alone (`200`) + another project (`403`), OR make `video_id` mandatory on `GET /studio/assets/{asset_id}/file` (removing dead `project_id`-only branching).
     - Validate scope (`video_id`/`project_id`) before distinguishing missing vs unauthorized assets, or ensure cross-scope requests do not leak existence of arbitrary `asset_id`s.

3. **[P1 — Stale `scene_assets` / Trim & Cross-Asset Access Leak on Re-Import Without Trim + Direct Repo Bypass in `routes.py` (`REC-03.01`, `G1`, `G2`, `G4`)]**
   - **Locations:**
     - `renderer/app/studio/api/routes.py:1867-1882` (writes `scene_assets` directly via `uc.editorial.get_script.scripts` only when trim is present, in a separate transaction after `import_media.execute`)
     - `renderer/app/studio/api/routes.py:2327-2334` (reads `uc.editorial.get_script.scripts.get_scene_assets(sc.id)` directly in the route handler inside bare `except Exception: pass`)
     - `renderer/app/studio/application/media.py:413-417` (`AssetFile` authorizes any `asset_id` present in `scene_assets`)
   - **Evidence:**
     - Importing `aid1` on `SCENE_1` with trim `(0.5, 2.5)` writes `(SCENE_1, aid1, 0.5, 2.5)` to `studio.scene_assets`. Re-importing `aid2` on `SCENE_1` **without** trim skips `save_scene_assets`, leaving `(SCENE_1, aid1, 0.5, 2.5)` in place. On reload, the workspace hydrates `aid1`'s stale trim `(0.5, 2.5)` onto `aid2` (`routes.py:2330-2332`), AND `GET /studio/assets/{aid1}/file?video_id={VIDEO_ID}` continues to succeed (`200`) for the replaced asset!
     - Re-introduces direct `uc.editorial.get_script.scripts` access from `routes.py` (bypassing use-case boundaries) and bare `except Exception: pass` (`routes.py:2333-2334`).
   - **Required Fix:**
     - Move trim save/clear into `ImportExternalMedia` (or a dedicated use case), clearing stale `scene_assets` when media is replaced without trim (and matching `sa.asset_id == sc.asset_id` when reading timing for the workspace).
     - Remove bare `except Exception: pass` and direct `uc.editorial.get_script.scripts` calls from `routes.py:1877-1881, 2327-2334`.
     - Add a test proving that re-importing a scene without trim clears stale `studio.scene_assets` and revokes `AssetFile` access to the replaced `asset_id`.

4. **[P1 — Absolute Block: Relaxed Assertions, Conditional E2E Guards & Missing Real Traversal Tests (`REC-03.01` & `REC-03.02`, `G4`, `G5`)]**
   - **Locations:**
     - `tests/test_rec_03_studio_routes.py:505-515` (`assert res_trav.status_code in (404, 422)` and `assert res_nul.status_code in (404, 422)`)
     - `tests/test_rec_03_studio_routes.py:538` (`assert resp.status_code in (415, 422)` inside `test_import_media_text_plain_declared_is_422`)
     - `tests/e2e_ux/test_rec_03_studio_browser.py:156, 204` (`assert f"?v={asset_1_id}" in img_src or "?v=" in img_src` and `assert f"?v={asset_2_id}" in vid_src or "?v=" in vid_src`)
     - `tests/e2e_ux/test_rec_03_studio_browser.py:306` (`if btn_gerar_faltante.is_visible() and btn_gerar_faltante.is_enabled():`)
     - `tests/e2e_ux/test_rec_03_studio_browser.py:332` (`if attribution_input.is_visible():`)
   - **Evidence:**
     - Accepting status tuples (`in (404, 422)`, `in (415, 422)`) and `or "?v=" in ...` violates strict assertion discipline.
     - `GET /studio/assets/../../etc/passwd/file` is path-normalized by the client/router to `/etc/passwd/file` before reaching `asset_file_by_id`; there is no test exercising `AssetFile`'s `target.relative_to(root)` check (e.g., DB `studio.assets.path = "../../etc/passwd"` → `404`) nor `POST .../import-media` filename NUL/dot-traversal rejection (`filename="bad\x00.png"` or `filename=".."` → `422`).
     - Wrapping Step 6 ("Gerar faltantes") in `if btn_gerar_faltante.is_visible() and btn_gerar_faltante.is_enabled():` silently passes if the button ever becomes hidden or disabled.
   - **Required Fix:**
     - Replace every `in (...)` tuple with exact status codes (`== 422` for `text/plain`, `== 404` for invalid ID / storage-root escape).
     - Add real traversal/NUL tests for both `AssetFile` (`asset.path = "../../etc/passwd"` linked to `SCENE_1_ID` → `404`) and `POST .../import-media` (`filename="a\x00.png"` and `filename=".."` → `422`).
     - In `test_rec_03_studio_browser.py`, make Step 6 (`#btn-gerar-faltante`) and `attribution_input` unconditional `expect(...).to_be_visible()` / `.to_be_enabled()`, remove `or "?v=" in ...` so exact `?v={asset_id}` is asserted, and assert `expect(page.locator(".scene")).to_have_count(initial_scene_count + 1)` after `page.reload()` to prove the newly added scene persisted.

### P2 Findings (Non-Blocking / Polish)
1. **`renderer/app/studio/api/routes.py:1818-1826, 1758, 1765`:** `trim_start_s`/`trim_end_s` validation lacks `math.isfinite(...)` (`NaN`/`inf` pass `< 0`, `<= 0`, `<= trim_start_s` comparisons), and multipart trim fields call `.decode()` without `errors="replace"`.
2. **`renderer/app/studio/api/routes.py:1810`:** Raw binary fallback sets `file_mime = content_type` without stripping MIME parameters (e.g., `image/png; charset=utf-8` is rejected instead of normalized via `.split(";")[0].strip()`).
3. **`renderer/app/studio/api/panel_video_workspace.py:572-573`:** `getattr(s, "trim_start_s", None) or ...` treats `0.0` as falsy when `scene_timing` is absent (prefer explicit `is not None`).
4. **`renderer/app/studio/api/panel_video_storyboard_js.py:395, 476, 488-489, 613-619`:** Modal `files` tab does not display `m.custom_assisted_prompt` if edited on the card nor prefill `m.trim_start_s`/`m.trim_end_s`; `commitText` clears `m.asset_id`/`m.asset_tag` without clearing `m.asset_kind`; `doImportMedia` does not bail early with a user message if a `tmp-*` scene is still unsaved after queue drain.
5. **`renderer/app/studio/application/media.py:524-525`:** `(root / existing.path).is_file()` in `ImportExternalMedia` does not verify `.resolve().relative_to(root)` before probing disk.
6. **`docs/.../{EXECUTION-LOG.md,EXECUTION-STATE.md,MODEL-USAGE.md}`:** Reconcile stale `BLOCKED_REVIEW` / `PAUSED_QUOTA_CHECKPOINT` / Round 1 test counts (`95`/`74`) before committing once Round 3 is `APPROVED`.

---

## 5. Exact Checklist to Reach `APPROVED` (`>= 9.0/10` All Dimensions) in Round 3

1. Replace the self-mocked snippets in `tests/test_storyboard_js.py` with real Node.js execution of `STORYBOARD_JS` (plus `node --check` on `STORYBOARD_JS` and `RUN_JS`).
2. Fix `AssetFile` (`application/media.py`): either implement real `project_id`-only scoping via a proper port/repo method (and test `?project_id=...` alone + cross-project `403`) or require `video_id`, and eliminate the `403`/`404` asset existence oracle.
3. Move trim save/clear into `ImportExternalMedia` (or a dedicated use case), clear stale `scene_assets` when re-importing without trim, remove direct `uc.editorial.get_script.scripts` access and `except Exception: pass` from `routes.py`, and add a test for re-import without trim + `math.isfinite` guard.
4. Remove all relaxed assertions (`in (404, 422)`, `in (415, 422)`, `or "?v=" in ...`) and conditional browser guards (`if btn_gerar_faltante...`, `if attribution_input...`), add real `AssetFile` storage-root escape & `import-media` NUL/traversal filename tests, and assert added-scene persistence after `page.reload()`.
5. Re-run Host Node suite, Container suite, and Isolated Playwright Desktop+Mobile E2E (`docker-compose.e2e.yml` port `8100`, `down -v`), update `rec-03-01-02-ux-browser-evidence.md`, and dispatch Round 3 independent review.
