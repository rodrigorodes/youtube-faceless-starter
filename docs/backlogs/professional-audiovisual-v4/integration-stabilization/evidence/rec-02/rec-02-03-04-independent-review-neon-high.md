# REC-02.03 & REC-02.04 Independent Review (`Gemini 4 Neon High`)

- **Reviewer:** `Gemini 4 Neon High` (`rec02-media-rev`)
- **Target Slice:** `REC-02.03` (`R06`) & `REC-02.04` (`R07`) — Media Import Probe/Decode Security, Content+Scope Deduplication, Real CAS & Restart/Concurrency
- **Branch / Base SHA:** `develop` @ `ef367fc66b9b888f7ef7fec78fd8e48991c41bad` + uncommitted working-tree diff (`7` modified files, `3` added files)
- **Review Rounds:** Round 1 (`REJECTED` → Fix Round 1 `#33`/`#34`) → **Round 2 (`APPROVED`)**
- **Final Decision:** **APPROVED (`VERIFIED`)** — `REC-02.03` = **`9.425 / 10`**, `REC-02.04` = **`9.44 / 10`** (every dimension `>= 9.0`, zero P0/P1 blockers)

---

## 1. Independent Verification Executed (Round 2 Final)

### 1.1 Canonical Container Test Re-Run
Command executed independently on the Round 2 working tree:
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh tests/test_rec_02_media_import.py tests/test_int_05_studio_assets.py tests/test_v4_asset_management.py tests/test_media.py tests/test_media_swap.py tests/test_asset_repo.py tests/test_storage.py tests/test_scene_assets_repo.py tests/test_db.py tests/test_schema_docs.py tests/test_architecture.py
```
Observed output:
- Image/checkout alignment: `HEAD=ef367fc`, `hash renderer/app: checkout=10e8fdb9d4403e36 imagem=10e8fdb9d4403e36`, `migrações: checkout=49 imagem=49`
- Result: **`141 passed in 19.63s`**, **`exit code 0`**
- Breakdown verified:
  - `tests/test_rec_02_media_import.py`: `15 passed`
  - `tests/test_int_05_studio_assets.py`: `5 passed` (strengthened from fake `ftyp`+zeros to real FFmpeg H.264 MP4)
  - `tests/test_v4_asset_management.py`: `18 passed`
  - `tests/test_media.py`: `28 passed`
  - `tests/test_media_swap.py`: `16 passed`
  - `tests/test_asset_repo.py`: `6 passed`
  - `tests/test_storage.py`: `19 passed`
  - `tests/test_scene_assets_repo.py`: `6 passed`
  - `tests/test_db.py`: `15 passed`
  - `tests/test_schema_docs.py`: `4 passed`
  - `tests/test_architecture.py`: `9 passed`
- Zero relaxed assertions in existing tests; zero paid API calls (`$0.00`).

### 1.2 Round 1 → Round 2 Finding Closure Verification
| Round 1 ID | Severity | Resolution Verified in Round 2 |
|---|---|---|
| Finding 1 (`REC-02.03`) | P1 | **CLOSED:** `media_probe.py` now passes `-protocol_whitelist file` + `stdin=subprocess.DEVNULL` to `ffprobe`/`ffmpeg`, `-xerror -err_detect explode -threads 1` to `_decode_first_frame`, and enforces per-container codec allowlists (`video/mp4`: `h264`/`hevc`/`av1`; `video/webm`: `vp8`/`vp9`/`av1`). `test_rec_02_media_import.py` now proves rejection of unsupported codec (`mpeg4` MP4), audio-only MP4, and invalid `source_url` schemes (`file://`, `javascript:`, `ftp://`). |
| Finding 2 (`REC-02.04`) | P1 | **CLOSED:** `_compensate_failed_import` in `application/media.py:304-318` no longer blindly unlinks `path` when `saved is None`; it fails closed on DB errors and verifies `self.assets.find(cache_key) is None` before calling `store.delete(path)`. |
| Finding 3 (`REC-02.04`) | P1 | **CLOSED:** `PostgresAssetRepository.add_and_swap_scene_asset` (`adapters/postgres/media_repo.py:68-101`) executes `pg_advisory_xact_lock(hashtextextended(cache_key, 0))`, `INSERT ... ON CONFLICT (cache_key) DO NOTHING`, canonical `SELECT`, and CAS `UPDATE studio.scenes` in **one PostgreSQL transaction**, executing `conn.rollback()` on CAS mismatch so uncommitted-intent rows are never visible to concurrent `find(key)` dedup. |
| Finding 4 (`REC-02.04`) | P1 | **CLOSED:** `test_rec_02_media_import.py` adds `test_rec02_04_cas_conflict_on_shared_cache_key_preserves_existing_file_and_concurrent_same_content` (shared `cache_key` preservation + 2-thread `Barrier(2)` same-content concurrency) and orphan-file cleanup assertion (`len(png_files) == 2`) in `test_rec02_04_restart_durability_and_concurrent_cas`. |

---

## 2. Final Rubric Scoring (`QUALITY-RUBRIC.md`)

> Threshold: `>= 9.0` in **every** applicable dimension, weighted mean `>= 9.0` (no rounding), and **zero** P0/P1 blockers.

### 2.1 `REC-02.03` (`R06` — Sandboxed Probe/Decode, Storage Coherence & License/Security)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | `FfmpegMediaProbe` implementa magic bytes + Pillow `verify()`/`load()` + bounds de dimensões/pixels (`<=8192`, `<=25MP`, `<=20MB`) para PNG/JPEG/WebP, e `ffprobe` + 1-frame `ffmpeg` decode com allowlist de codecs por container (`video/mp4`: `h264`/`hevc`/`av1`; `video/webm`: `vp8`/`vp9`/`av1`) e limites de duração/dimensão/tamanho; `FileAssetStore.put_video` persiste `.mp4`/`.webm` coerentemente; `verify_license_provenance` + `requires_attribution` + validação de esquema `http`/`https` em `source_url`; injetado em `Studio` (`wiring.py`). |
| Arquitetura e simplicidade | 20% | 9.5 | Port `MediaProbe`/`ProbedMedia` em `application/ports.py`, adapter isolado em `adapters/media_probe.py`, falha fechada se `probe=None`, `tests/test_architecture.py` `9/9` verde sem vazamento de `subprocess`/`PIL`/`os` em `domain/` ou `application/`. |
| Testes e regressão | 20% | 9.5 | `141 passed in 19.63s` (`exit code 0`) no container; matriz negativa completa (`ftyp`+zeros, bytes arbitrários `>16B`, MP4/PNG truncados, MIME falso PNG-como-MP4/WebM-como-MP4/MP4-como-WebM/ZIP-como-PNG/WebP, payload `>100MB` e bomba `6000x5000`, path traversal/NUL, licenças desconhecidas/sem atribuição, `source_url` inválido, codec `mpeg4` não suportado e MP4 audio-only); `test_int_05_studio_assets.py` fortalecido com MP4 real. |
| Segurança, orçamento e confiabilidade | 20% | 9.5 | `-protocol_whitelist file` + `stdin=subprocess.DEVNULL` em `ffprobe`/`ffmpeg`, `-xerror -err_detect explode -threads 1` no decode, timeouts (`10s`/`15s`), `tempfile.TemporaryDirectory`, allowlist de codecs por container, proteção contra traversal em `FileAssetStore.delete`, falha fechada sem probe, `$0.00` em APIs pagas. |
| Evidências e operação | 15% | 9.0 | Evidência completa em `rec-02-03-04-media-evidence.md` com Red→Green, comando canônico, hash alinhado (`10e8fdb9d4403e36`), rollback limpo e `$0.00` gasto. *(Detalhe menor P2: a tabela 2.2 da evidência do autor ainda não lista linha extra para `test_rec02_03_rejects_unsupported_video_codec_and_audio_only_mp4`, embora as seções 1.2 e 2.1 registrem os 15 testes e o hardening.)* |

- **Média ponderada exata (`REC-02.03`):** `9.5*0.25 + 9.5*0.20 + 9.5*0.20 + 9.5*0.20 + 9.0*0.15 = 9.425 / 10`
- **Gates aplicáveis:** G0, G1, G2, G4 — **PASS**
- **Bloqueios P0/P1 abertos:** `0`
- **Decisão `REC-02.03`:** **APPROVED (`VERIFIED`)**

---

### 2.2 `REC-02.04` (`R07` — Content+Scope Dedup, Real CAS, Atomic Compensation, Restart/Concurrency & Consumer Proof)

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | Dedup por `(kind, "import", project_id, content_sha256, license[, aspect])` sem `filename`, comprovando isolamento entre projetos e licenças; CAS real (`expected_asset_id`) com `StateConflict` e preservação do asset/arquivo anterior; prova E2E de consumidor real (import MP4+PNG reais → Postgres → `PlanFfmpegRenderer` → `ffprobe` H.264 `1080x1920`, `duration >= 2.0s`). |
| Arquitetura e simplicidade | 20% | 9.5 | `PostgresAssetRepository.add_and_swap_scene_asset` resolve `R07` ("persistência/vínculo separados") em uma única transação sem migração de schema, preservando fallback compatível para test doubles e fronteiras Clean Architecture (`9/9`). |
| Testes e regressão | 20% | 9.5 | `141 passed in 19.63s` (`exit code 0`) em PostgreSQL descartável; cobre dedup por conteúdo+escopo, CAS obsoleto e corrida pós-escrita, concorrência 2-threads com `Barrier(2)` + verificação de limpeza de órfão (`2` PNGs) + durabilidade pós-restart, preservação de `cache_key` compartilhado + corrida concorrente de mesmo conteúdo, e prova E2E de render real. |
| Segurança, orçamento e confiabilidade | 20% | 9.2 | `pg_advisory_xact_lock(hashtextextended(cache_key, 0))` + `conn.rollback()` completo em conflito CAS impede exposição de linha não vinculada ao dedup; `_compensate_failed_import` falha fechado em erro de DB e checa `assets.find(cache_key) is None` antes de `store.delete(path)`, preservando arquivos compartilhados/vivos. *(Nota P2 opcional: uma janela teórica cross-process entre `find(cache_key) is None` e `store.delete(path)` sem lock de arquivo no filesystem fica documentada como hardening futuro.)* |
| Evidências e operação | 15% | 9.5 | Evidência atualizada em `rec-02-03-04-media-evidence.md` com hash exato (`10e8fdb9d4403e36`), 141/141, nota explícita mantendo rota HTTP/preview UI de `GAI-01` para `REC-03.01` (`R08`), `$0.00` gasto e plano de rollback. |

- **Média ponderada exata (`REC-02.04`):** `9.5*0.25 + 9.5*0.20 + 9.5*0.20 + 9.2*0.20 + 9.5*0.15 = 9.44 / 10`
- **Gates aplicáveis:** G0, G1, G2, G4 — **PASS**
- **Bloqueios P0/P1 abertos:** `0`
- **Decisão `REC-02.04`:** **APPROVED (`VERIFIED`)**

---

## 3. Non-Blocking Observations (P2 — Informational)
- **Cross-process file-unlink hardening (P2):** `_compensate_failed_import` fails closed on DB error and verifies `assets.find(cache_key) is None` before calling `store.delete(path)`. Adding a filesystem lock (`flock`) or returning `created_file: bool` from `FileAssetStore.put*` would eliminate even the narrow theoretical cross-process race between `find(cache_key) is None` and `unlink`.
- **Path traversal sanitization vs rejection (P2):** `../../etc/passwd.png` is sanitized via `PurePosixPath(...).name` and never used in disk paths (SHA-256 `cache_key` inside `storage_root`), preserving backwards compatibility with `test_int_05_studio_assets.py`; NUL bytes and dotfiles are rejected and `FileAssetStore.delete` enforces strict `storage_root` containment.
- **`GAI-01` scope boundary:** HTTP upload route and Studio storyboard preview UI remain scoped to `REC-03.01` (`R08`) as explicitly tracked.

---

## 4. Round 1 Audit Trail (Historical)
- Round 1 scored `REC-02.03` = `8.80 / 10` and `REC-02.04` = `8.40 / 10` (`REJECTED`, 139/139 passed) due to 4 P1 findings (FFmpeg `-protocol_whitelist`/`-xerror` & unsupported codec test; blind `store.delete(path)` on `saved is None`; separate `add`+`swap` transactions TOCTOU; missing shared-asset/same-content concurrency tests). All 4 P1 findings were resolved and independently re-verified in Round 2 (`141 passed`, `exit code 0`).
