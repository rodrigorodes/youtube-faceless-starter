# Evidência de Integração e Testes: REC-03.03 (R10 — Lacunas de Pipeline, Rodada 2)

- **Data:** 26/11/2026
- **Branch:** `develop` (Base HEAD `7ded0f5d58d655df41df6dda32f479308489314b` + working tree não comitado; `main` intocada em `42700cb331165a68455173a91c463d4733292cfd`)
- **Status:** `IMPLEMENTED_PENDING_REVIEW` (Aguardando Revisão Independente — **NÃO** marcado como `VERIFIED`)
- **Segurança & Isolamento:**
  - Custo externo em APIs pagas: **`$0.00`**
  - Kill switch de publicação: **`STUDIO_PUBLICATION_ENABLED=0`** (`BLOCKED`, preservado como guarda prioritária em `RunPublication`)
  - Portas DEV (`8000`/`5678`): **intocadas**
  - Git: **sem commit, sem push, sem alteração em `main`**
- **Hashes SHA-256 dos Artefatos Verificados:**
  - `git diff` (20 arquivos rastreados, `+682 / -57`): `8f114b9f649d6e4e451b4218c2983d6f9cdfdbe63217989d0d2f7cc5ac2cdfea`
  - `git diff renderer/`: `61aa45f8fc231b1be2a5dcaa384b94cde9ac96cfaf90edf7445fecf73b34fdeb`
  - `renderer/app/studio/adapters/license_mapping.py` (novo): `1a4f72a161c90bb1a598bb47f8f4015b7ee7fe54ece2f696d8ae15af6afc8f59`
  - `tests/test_rec_03_pipeline_integration.py` (reescrito): `fb4bc357c885346f20c3eee35bbef01d21816ee5400467045b4ecff5520caeda`
  - Hash `renderer/app` alinhado checkout x imagem Docker: `94d8d9bcea2693a0` (migrações `49/49`)

---

## 1. Mapeamento AS-IS vs. TO-BE (Classificação Honesta por Requisito)

| Requisito | Classificação AS-IS | Integração Canônica & Call Sites Reais (TO-BE) | Classificação TO-BE |
|---|---|---|---|
| **(a) Cache segmentado por cena (vídeo + narração/TTS)** | `MOCK_ONLY` / parcial | `RunRender._cached_narration` (`application/render.py`) + `PlanFfmpegRenderer` (`adapters/render_plan_ffmpeg.py`) + `PostgresRenderPlanRepository` (`adapters/postgres/render_plan_repo.py`). Provado com Postgres descartável + FFmpeg real: alterar 1 cena chama TTS `1x` (apenas cena 0) e FFmpeg `3x` (1 shot + concat + audio), altera fingerprint/sha256 da cena 0 e preserva `artifact_sha256`, `artifact_uri` e `mtime_ns` de vídeo e narração das cenas 1 e 2. | **`INTEGRATED`** |
| **(a / REC-03.03b) Preflight, progresso por shot e cancelamento cooperativo** | `MODEL_ONLY` | `PlanFfmpegRenderer._preflight` (chama `evaluate_preflight` verificando manifesto de arquivos e espaço livre em disco), callbacks `RenderProgress` (`PREFLIGHT` → `RENDERING_SEGMENTS` → `CONCATENATING` → `MIXING_AUDIO` → `COMPLETED`/`CANCELLED`) e `cancel_check` cooperativo entre shots (`RenderCancelledError`), conectado a `RunRender._render` via `lambda: not self.jobs.alive(job.id)`. | **`INTEGRATED`** |
| **(b) QA defect detection → regeneração seletiva limitada + reavaliação (fail-closed no teto)** | `MODEL_ONLY` (0 call sites em `renderer/app/`) | `QaHandler.execute` (`application/production.py`), injetado via `build_stage_handlers` e `composition/wiring.py` com `plans=plan_repo`, `start_render`, `run_render` e `max_regeneration_attempts`. `FfmpegQa.analyze` (`adapters/qa_ffmpeg.py`) extrai `black_intervals` e `domain/quality.py` atribui `scene_id`/`shot_id` em `CHECK_BLACK` e `CHECK_ASSET`. Provado com `ProductionCoordinator` + `QaHandler` + Postgres + FFmpeg `blackdetect` reais: defeito preto sintético na cena 0 dispara `compute_selective_regeneration`, repara só cena 0, reusa cache das cenas 1 e 2, reavalia QA e aprova; defeito persistente esgota `max_attempts=2` e falha fechado (`RunState.FAILED`) no Postgres com `$0.00`. | **`INTEGRATED`** |
| **(c) Restart: estado, identidade congelada, legendas, coordenador e cache do renderer** | Parcial (repositórios isolados) | `PostgresVideoRepository.update_video_creative_brief`/`update_video_pacing_preset` com `conn.transaction()` (`adapters/postgres/repo.py`). Provado com novo `ProductionCoordinator`, novo `PlanFfmpegRenderer` e novas conexões Postgres pós-restart: relê `creative_brief`, cenas/legendas e `EffectiveConfig` (`content_hash` intacto), replay idempotente devolve `CreateRunResult.EXISTING` sem duplicar run, e novo render de plano idêntico executa `0` chamadas FFmpeg (100% cache hit do Postgres). | **`INTEGRATED`** |
| **(d.1) Creative Direction: sanitização + Brief → Short/Long Script → RenderPlan** | Parcial (`GenerateScript` engolia erros; ausente em `GenerateLongScript` e `RenderPlan`; falsos positivos PT-BR) | `domain/creative_director.py` usa fronteiras de token CLI/shell (`FORBIDDEN_COMMAND_PATTERNS`) aceitando prosa PT-BR/técnica legítima (`"auto-afirmação"`, `"pré-afirmação"`, `"re-afirmar"`, `"color-preset"`, `"Tutorial de comandos bash..."`, `"requisições com curl..."`, `"História do projeto FFmpeg..."`) e bloqueando injeções com HTTP `422` em `PUT/POST /studio/videos/{id}/direction`. `GenerateScript` (sem `except Exception: pass`), `GenerateLongScript` (`build_long_outline_prompt` e `build_long_scenes_prompt`), `RunRender._render` → `RenderSpec.creative_brief` → `PlanFfmpegRenderer._build_plan` propagam o `CreativeBrief` ao `RenderPlan` (pacing/motion/music params) preservando `config_snapshot` congelado idêntico entre regenerações. | **`INTEGRATED`** |
| **(d.2) Captions/Export via `RenderPlan` nas rotas + `render.caption_sync` fail-closed** | `MODEL_ONLY` (export) / defeituoso (`caption_sync`) | `ExportSubtitles` (`application/render.py`), injetado em `composition/wiring.py` com `export_captions_from_plan` (`adapters/captions_exporters.py`), servido por `GET /studio/videos/{id}/subtitles`, `/subtitles.vtt` e `/subtitles.ass` (`api/routes.py`, sem importar `adapters`), com fallback retrocompatível para `.srt` em disco em renders legados. `adapters/quality_ffmpeg.py` propaga erros de `_probe_duration` (nunca `0.0`), chama `check_audio_caption_sync` e registra `caption_sync_error` sem `except Exception: pass`; `domain/quality.py` só inclui `render.caption_sync` em `checks_run` quando há medição real e marca `coverage.status = "not_verified"` em erro de probe. Mutação deletando a medição é morta (`exit 1`). | **`INTEGRATED`** |
| **(d.3) Licença fail-closed em todos os gates + fronteira Clean Architecture** | Regressão P0 (bypass por substring + vendor no domínio + lacunas em `RunPublication`/`scene_assets`) | `domain/asset_registry.py::verify_license_provenance` reescrito com allowlist normalizada estrita (sem substring match, sem `pexels`/`pixabay`), sufixo exato `" (gerada localmente pelo estúdio)"` e formato estrito `ai-generated:<model>`. Normalização exata de rótulos de stock movida para `adapters/license_mapping.py::normalize_vendor_license` e injetada em `composition/wiring.py`. Validação centralizada em `application/publication_gate.py::license_block_reason` (checa `sc.asset_id`, `scene_assets` e falha fechado se `assets.get() is None`) aplicada em `publication_block_reason`, `Approve`, `ClaimPublication` e `RunPublication._prepare` (preservando kill switch `enabled=False` como 1ª guarda). `tests/test_architecture.py` verde. | **`INTEGRATED`** |
| **Consolidação / Remoção dos 3 módulos legados em memória (R10)** | Não executado | Ver Seção 2 abaixo: mantidos intactos intencionalmente para compatibilidade com os testes legados V4 (`test_v4_{render_engine,asset_management,studio_ux}.py`) e documentados honestamente como **`DEFERRED`** (0 chamadores em produção). | **`DEFERRED`** |

---

## 2. Módulos Legados em Memória — Status Honesto (`DEFERRED`)

Os três módulos em memória abaixo permanecem **intactos** neste slice (não foram removidos nem alterados) e têm **0 chamadores em código de produção** (`renderer/app/`):

1. `renderer/app/studio/application/render_engine.py` (`SegmentCacheManager` em memória) — referenciado apenas por `tests/test_v4_render_engine.py`. Caminho canônico em produção: `application/render_cache.py` (`PlanRegeneration`) + `adapters/postgres/render_plan_repo.py` + `adapters/render_plan_ffmpeg.py`.
2. `renderer/app/studio/application/asset_registry.py` (`AssetCatalogManager` em memória) — referenciado apenas por `tests/test_v4_asset_management.py`. Caminho canônico em produção: `adapters/postgres/media_repo.py` (`PostgresAssetRepository`) + `domain/asset_registry.py` (`verify_license_provenance`).
3. `renderer/app/studio/application/studio_workbench.py` (`StudioWorkbenchService` em memória) — referenciado apenas por `tests/test_v4_studio_ux.py`. Caminho canônico em produção: `api/routes.py` + `api/panel_video_workspace.py` + `adapters/postgres/editorial_repo.py`.

- **Classificação:** **`DEFERRED`** (não reivindica aposentadoria/remoção neste PR).
- **Risco:** Baixo em runtime (0 chamadores de produção), porém mantém risco de confusão arquitetural se algum desenvolvedor futuro importar um serviço em memória por engano.
- **Owner / Próximo Passo:** Backlog de limpeza pós-estabilização V4 (`REC-04` / depreciação formal): migrar ou aposentar `tests/test_v4_{render_engine,asset_management,studio_ux}.py` junto com a remoção dos 3 arquivos em slice dedicada.

---

## 3. Matriz de Resolução dos Achados da Revisão Independente (Rodada 1)

| Achado | Severidade | Resolução Aplicada |
|---|---|---|
| **P0-1** | P0 | `domain/asset_registry.py::verify_license_provenance` reescrito com allowlist normalizada estrita (zero substring match); rejeita todos os vetores de bypass (`"non-commercial"`, `"not commercial"`, `"prohibited commercial use"`, `"cc-by-nc-nd-4.0"`, `"cc-by-nc-4.0"`, `"stolen-cc0-pirated"`, `"not public domain"`, `"stolen from pexels"`, `"gerado por terceiro sem autorizacao"`, `"non-commercial ai-generated"`, `"ai-generated:"`, `"ai-generated:unknown"`, `"unknown (gerada localmente pelo estúdio)"`). |
| **P0-2** | P0 | Removidos todos os nomes de fornecedores (`pexels`/`pixabay`) de `domain/` e `application/`; criado `adapters/license_mapping.py::normalize_vendor_license` injetado via `composition/wiring.py`. `tests/test_architecture.py` 100% verde. |
| **P0-3** | P0 | Integrado `compute_selective_regeneration` em `QaHandler` (`application/production.py`) e `build_stage_handlers` / `composition/wiring.py` com loop limitado por `max_regeneration_attempts`, persistência do histórico no checkpoint Postgres, atribuição de cena em `CHECK_BLACK`/`CHECK_ASSET`, reuso de cache e falha fechada no teto. |
| **P1-1** | P1 | Criado `application/publication_gate.py::license_block_reason` fail-closed (inclui `scene_assets` e `assets.get() is None`) e conectado a `publication_block_reason`, `Approve`, `ClaimPublication` e `RunPublication._prepare` (preservando kill switch `enabled=False`). |
| **P1-2** | P1 | Removido `except Exception: pass` em `GenerateScript`; propagado `video.creative_brief` para `GenerateLongScript` (outline + scenes) e para `RunRender._render` → `RenderSpec` → `PlanFfmpegRenderer._build_plan` → `RenderPlan` preservando `config_snapshot` congelado. |
| **P1-3** | P1 | Criado `ExportSubtitles` em `application/render.py`, injetado `export_captions_from_plan` em `composition/wiring.py` e conectadas as rotas `/subtitles`, `/subtitles.vtt` e `/subtitles.ass` em `api/routes.py` com fallback legado e sem violar fronteira Clean Architecture. |
| **P1-4** | P1 | `_probe_duration` em `adapters/quality_ffmpeg.py` lança `RuntimeError` em erro (nunca `0.0`); `FfmpegQualityEvaluator` usa `check_audio_caption_sync` e registra `caption_sync_error` (sem `except Exception: pass`); `domain/quality.py` só adiciona `render.caption_sync` a `checks_run` quando efetivamente medido e registra gap (`not_verified`) em erro de probe. |
| **P1-5** | P1 | `FORBIDDEN_COMMAND_PATTERNS` em `domain/creative_director.py` ajustado para fronteiras de token CLI/shell; prosa legítima PT-BR/técnica retorna HTTP `200` e injeções reais retornam HTTP `422`. |
| **P1-6** | P1 | Fortalecidos testes (a) (narração/TTS + vídeo + hash alterado na cena 0 + contadores FFmpeg/TTS) e (c) (novo `ProductionCoordinator` + novo `PlanFfmpegRenderer` com 0 chamadas FFmpeg após restart); implementado `REC-03.03b` (preflight, `RenderProgress`, cancelamento cooperativo entre shots); módulos legados documentados honestamente como `DEFERRED`. |
| **P2-1** | P2 | Revertido o hack de inserção não escopada de `id`/`asset_id` em `adapters/postgres/editorial_repo.py::_persist_scenes` (arquivo limpo no `git diff`). |
| **P2-2** | P2 | Removidos fixtures/repositórios não utilizados em `tests/test_rec_03_pipeline_integration.py`; testes usam `SceneDraft` + `PostgresAssetRepository.swap_scene_asset` canônicos. |

---

## 4. Evidência Real de Execução de Testes (Rodada 2)

Todos os comandos foram executados com `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"` no repositório `/Users/rodrigomendes/youtube-faceless-starter`.

### 4.1 Suíte Focada REC-03 (Container Descartável + PostgreSQL Efêmero + FFmpeg Real)
- **Comando:**
  ```bash
  ./scripts/test-container.sh tests/test_rec_03_pipeline_integration.py tests/test_rec_03_studio_routes.py -ra
  ```
- **Alinhamento:** `HEAD=7ded0f5 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=94d8d9bcea2693a0 imagem=94d8d9bcea2693a0`, `migrações: checkout=49 imagem=49`
- **Resultado Observado:** **`37 passed, 1 warning in 39.35s`** (`10` em `test_rec_03_pipeline_integration.py` + `27` em `test_rec_03_studio_routes.py`) | **Exit code:** **`0`**

### 4.2 Suíte Canônica Completa do Container (Gate G6)
- **Comando:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alinhamento:** `HEAD=7ded0f5 alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=94d8d9bcea2693a0 imagem=94d8d9bcea2693a0`, `migrações: checkout=49 imagem=49`
- **Resultado Observado:** **`4501 passed, 26 skipped, 1 warning in 720.94s (0:12:00)`** (`0` falhas; total coletado: `4527`) | **Exit code:** **`0`**
- **Detalhamento dos 26 skips (estruturais do container slim, sem falhas):** `3` testes Playwright (`test_reference_browser.py`, `ve08/test_composition_functional.py`, `ve08/test_storyboard_functional.py` — `pytest_playwright` ausente na imagem slim) + `23` testes Node.js (executados no host em §4.3).

### 4.3 Suíte Node.js / Painel / Workflows no Host
- **Comando:**
  ```bash
  python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
    tests/test_falha_producao.py tests/test_publicacao_acao.py tests/test_workflow_analytics.py \
    tests/test_workflow_publish.py tests/test_workflow_trends.py -ra
  ```
- **Resultado Observado:** **`101 passed in 8.75s`** | **Exit code:** **`0`**

### 4.4 E2E Browser Isolado com Playwright Chromium (`docker-compose.e2e.yml`, Porta `8100`)
- **Comandos:**
  ```bash
  E2E_PORT=8100 docker compose -p faceless-e2e-rec0303x -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
    STUDIO_E2E_USER="e2e" STUDIO_E2E_PASSWORD="e2e-senha-descartavel" \
    python3 -m pytest tests/e2e_ux/test_rec_03_studio_browser.py -v -ra
  docker compose -p faceless-e2e-rec0303x -f docker-compose.e2e.yml down -v
  lsof -i :8100
  ```
- **Resultado Observado:** **`1 passed in 8.90s`** (`test_rec_03_studio_browser_desktop_and_mobile_e2e[chromium]`) | **Exit code:** **`0`**
- **Prova de Teardown:** Containers `faceless-e2e-rec0303x-renderer-e2e-1`, `faceless-e2e-rec0303x-postgres-e2e-1` e rede `faceless-e2e-rec0303x_default` removidos; `lsof -i :8100` retornou `PORT_8100_CLOSED`.

### 4.5 Prova de Resistência à Mutação (`render.caption_sync`)
- **Método:** Cópia temporária fora do repositório (`/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rec0303-mut-r2`, removida ao término) removendo todo o bloco de medição de `caption_sync` em `renderer/app/studio/adapters/quality_ffmpeg.py`.
- **Resultado Observado:** `FAILED tests/test_rec_03_pipeline_integration.py::test_pipeline_qa_caption_sync_measured_drift_and_fail_closed_probe` (`AssertionError: assert 'render.caption_sync' in (...)`) | **Exit code:** **`1`** (**MUTATION KILLED**).

---

## 5. Detalhamento dos 10 Testes em `tests/test_rec_03_pipeline_integration.py`

1. `test_pipeline_single_scene_change_reuses_unaffected_segments_and_narration`: prova reuso real de vídeo e narração/TTS com contadores (`voice.calls == 1`, `ffmpeg_calls == 3`), hash/fingerprint novos na cena 0 e `artifact_sha256`/`artifact_uri`/`mtime_ns` intactos nas cenas 1 e 2.
2. `test_pipeline_rec03_03b_preflight_progress_and_cooperative_cancel`: prova `evaluate_preflight`, eventos `RenderProgress` por shot e cancelamento cooperativo entre shots (`RenderCancelledError` após shot 0).
3. `test_pipeline_qa_known_defect_triggers_bounded_selective_regeneration`: prova `ProductionCoordinator` + `QaHandler` + Postgres + FFmpeg `blackdetect` reais — recuperação seletiva da cena 0 preta com reuso de cache das cenas 1/2 e falha fechada (`RunState.FAILED`) ao esgotar `max_attempts=2` com `$0.00`.
4. `test_pipeline_state_frozen_identity_captions_and_cache_survive_restart`: prova reconexão pós-restart com novo `ProductionCoordinator` e novo `PlanFfmpegRenderer` (`CreateRunResult.EXISTING`, `EffectiveConfig.content_hash` preservado, `0` chamadas FFmpeg no segundo render).
5. `test_pipeline_creative_direction_sanitization_ptbr_and_injections`: prova rejeição HTTP `422` de 9 injeções CLI/shell em `PUT` e `POST` e aceitação HTTP `200` de 7 frases legítimas PT-BR/técnicas.
6. `test_pipeline_creative_brief_flows_to_short_long_scripts_and_render_plan`: prova propagação de `video.creative_brief` em `GenerateScript` (incl. erro explícito para brief corrompido), `GenerateLongScript` (outline + scenes) e `RenderPlan` (pacing/motion/bpm/tone) mantendo `config_snapshot` congelado idêntico.
7. `test_pipeline_subtitles_routes_use_export_captions_from_plan_with_legacy_fallback`: prova `/subtitles`, `/subtitles.vtt` e `/subtitles.ass` via `export_captions_from_plan` com `RenderPlan` persistido e fallback `.srt`/`.vtt` em vídeo legado sem plano.
8. `test_pipeline_qa_caption_sync_measured_drift_and_fail_closed_probe`: prova `render.caption_sync` sincronizado (pass), dessincronizado `> 500ms` (warning), ausência de medição sem falso pass e erro de `ffprobe` fail-closed (`RuntimeError` + `not_verified`).
9. `test_pipeline_license_allowlist_no_bypass_and_vendor_boundary`: prova rejeição de todos os vetores de bypass, ausência de vendor no domínio e normalização exata na fronteira de adaptador (`normalize_vendor_license`).
10. `test_pipeline_license_blocks_all_publication_gates_including_scene_assets_and_missing`: prova bloqueio fail-closed em `Approve`, `publication_block_reason`, `RunPublication` e `ClaimPublication` para licença primária inválida, `scene_assets` inválido e asset ausente (`None`), preservando `RunPublication(enabled=False)` como 1ª guarda.
