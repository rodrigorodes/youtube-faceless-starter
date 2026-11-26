# REC-02.03 & REC-02.04 Evidence — External Media Import Security, Deduplication & CAS Persistence

- **Branch:** `develop` (base HEAD `ef367fc66b9b888f7ef7fec78fd8e48991c41bad`)
- **Executor:** `Gemini 4 Hydrogen Medium` (`rec02-media`)
- **External API Spend:** `$0.00` (zero paid API calls; offline FFmpeg/Pillow + disposable PostgreSQL only)
- **Dev Stack / Publication:** Ports `8000` / `5678` untouched; `publication_enabled=False`

---

## 1. Test-First (Red -> Green) Proof

### 1.1 Red Phase
Command:
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh tests/test_rec_02_media_import.py
```
Observed output (exit code `2`):
```text
ERROR collecting tests/test_rec_02_media_import.py
tests/test_rec_02_media_import.py:24: in <module>
    from app.studio.adapters.media_probe import FfmpegMediaProbe
E   ModuleNotFoundError: No module named 'app.studio.adapters.media_probe'
```

### 1.2 Green Phase (Canonical Container Verification)
Command:
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh tests/test_rec_02_media_import.py tests/test_int_05_studio_assets.py tests/test_v4_asset_management.py tests/test_media.py tests/test_media_swap.py tests/test_asset_repo.py tests/test_storage.py tests/test_scene_assets_repo.py tests/test_db.py tests/test_schema_docs.py tests/test_architecture.py
```
Observed output (exit code `0`):
```text
== alinhamento (checkout x imagem)
HEAD=ef367fc alterações_em_renderer/tests=sim
hash renderer/app: checkout=10e8fdb9d4403e36 imagem=10e8fdb9d4403e36
migrações: checkout=49 imagem=49
== PostgreSQL descartável
============================= 141 passed in 20.88s =============================
== pytest saiu com código 0
```
Breakdown:
- `tests/test_rec_02_media_import.py`: 15 passed
- `tests/test_int_05_studio_assets.py`: 5 passed (fake `ftyp`+zeros replaced by real FFmpeg-generated MP4)
- `tests/test_v4_asset_management.py`: 18 passed
- `tests/test_media.py`: 28 passed
- `tests/test_media_swap.py`: 16 passed
- `tests/test_asset_repo.py`: 6 passed
- `tests/test_storage.py`: 19 passed
- `tests/test_scene_assets_repo.py`: 6 passed
- `tests/test_db.py`: 15 passed
- `tests/test_schema_docs.py`: 4 passed
- `tests/test_architecture.py`: 9 passed (Clean Architecture boundaries preserved: zero `subprocess`/`PIL`/`os`/vendor names in `domain/` and `application/`)

---

## 2. REC-02.03 (`R06`) — Sandboxed Probe/Decode, Storage Extensions & Security Matrix

### 2.1 Adapter & Port Design
- **Port (`renderer/app/studio/application/ports.py`):** `ProbedMedia` dataclass + `MediaProbe` protocol.
- **Adapter (`renderer/app/studio/adapters/media_probe.py`):** `FfmpegMediaProbe`:
  - **Images (`image/png`, `image/jpeg`, `image/webp`):** Magic bytes check + `PIL.Image.open()` format match + dimension/pixel bounds (`<= 8192x8192`, `<= 25_000_000` pixels, `<= 20 MB`) + `img.verify()` + full `img.load()` decode.
  - **Videos (`video/mp4`, `video/webm`):** `<= 100 MB` size check, isolated `tempfile.TemporaryDirectory`, `ffprobe -v error -protocol_whitelist file -print_format json -show_format -show_streams` with `stdin=DEVNULL` (10s timeout), container-vs-MIME coherence (`mp4`/`mov` vs `webm`/`matroska`), per-container allowed codecs (`video/mp4`: `h264`/`hevc`/`av1`; `video/webm`: `vp8`/`vp9`/`av1`), positive bounded dimensions (`<= 4096x4096`), finite positive duration (`0 < duration_s <= 3600.0`), and 1-frame `ffmpeg -v error -protocol_whitelist file -xerror -err_detect explode -threads 1 -i <tmp> -frames:v 1 -f null -` decode check with `stdin=DEVNULL` (15s timeout).
- **Coherent Storage (`renderer/app/studio/adapters/storage.py`):**
  - `FileAssetStore.put_video(cache_key, data, mime="video/mp4")` persists `.mp4` for `video/mp4` and `.webm` for `video/webm` atomically via temp file + `os.replace`.
  - `FileAssetStore.delete(relative_path)` safely unlinks only regular files inside `storage_root` for compensation.
- **License & Provenance (`renderer/app/studio/domain/asset_registry.py` + `application/media.py`):**
  - Enforces `verify_license_provenance` allowlist (`CC0`, `CC0-1.0`, `CC-BY`, `CC-BY-4.0`, `CC-BY-SA`, `CC-BY-SA-4.0`, `Public Domain`, `Free Stock`, `Commercial Stock`, `Studio Generated`, `OWN_ORIGINAL`, `COMMERCIAL_LICENSED`, `Proprietary Commercial`).
  - Requires `attribution` or `source_url` for `CC-BY-4.0`, `CC-BY-SA-4.0`, and `COMMERCIAL_LICENSED`, and validates `http://`/`https://` scheme on `source_url`.

### 2.2 Negative Test Matrix (All Verified Green)
| Negative Case | Expected Behavior | Test Function |
|---|---|---|
| 80-byte `ftyp` + zeros fake MP4 | Rejected (`AssetRefused`) | `test_rec02_03_rejects_fake_ftyp_zeros_and_arbitrary_bytes` |
| Arbitrary `>= 16 bytes` text as `video/mp4` or `video/webm` | Rejected (`AssetRefused`) | `test_rec02_03_rejects_fake_ftyp_zeros_and_arbitrary_bytes` |
| Truncated valid MP4 & truncated valid PNG | Rejected (`AssetRefused`) | `test_rec02_03_rejects_truncated_mp4_and_truncated_png` |
| PNG as `video/mp4`, WebM as `video/mp4`, MP4 as `video/webm` | Rejected (`AssetRefused`) | `test_rec02_03_rejects_false_mime_and_polyglot_zip` |
| ZIP archive masquerading as PNG / WebP | Rejected (`AssetRefused`) | `test_rec02_03_rejects_false_mime_and_polyglot_zip` |
| Payload `> 100 MB` & `6000x5000` (`30 MP`) decompression bomb | Rejected before disk write | `test_rec02_03_rejects_oversized_and_decompression_bomb_before_disk_write` |
| Path traversal (`../../etc/passwd.png`, `..\evil.png`) & NUL byte | Sanitized inside root / NUL rejected | `test_rec02_03_path_traversal_and_nul_byte_protection` |
| Empty, `unknown`, `my-random-license`, `proprietary`, missing attribution on `CC-BY-4.0` | Rejected (`AssetRefused`) | `test_rec02_03_license_and_provenance_policy_and_invalid_ids` |
| Non-existent `video_id`, missing `scene_id`, cross-project `scene_id` | Rejected (`VideoNotFound` / `SceneNotFound`) | `test_rec02_03_license_and_provenance_policy_and_invalid_ids` |

---

## 3. REC-02.04 (`R07`) — Scoped Deduplication, CAS, Compensation & Consumer Proof

1. **Content + Scope Deduplication (`application/media.py`):**
   - `cache_key` computed from `(kind, "import", video.project_id, content_sha256, {"license": norm_license, "size": len(data), ...})` — filename removed from identity.
   - Proven in `test_rec02_04_dedup_by_content_and_scope_no_cross_project_or_license_leak`: same MP4 bytes under two filenames in Project A + `CC0-1.0` deduplicate to the same `Asset.id`; Project B or `COMMERCIAL_LICENSED` produces distinct rows and files.
2. **Real CAS (`expected_asset_id`) & Atomic Single-Transaction Compensation:**
   - `ImportExternalMedia.execute(..., expected_asset_id: str | None = None)` verifies `scene.asset_id == expected_asset_id` before disk write and executes `PostgresAssetRepository.add_and_swap_scene_asset(...)` in a **single PostgreSQL transaction** under `pg_advisory_xact_lock(hashtextextended(cache_key, 0))` with full `conn.rollback()` on CAS mismatch (never exposing an uncommitted-intent asset row to concurrent `find(key)` dedup).
   - Compensation (`_compensate_failed_import`) fails closed on DB errors and only unlinks `path` when `assets.find(cache_key) is None` (never deletes a shared/live file).
   - Verified in `test_rec02_04_cas_conflict_preserves_previous_asset_and_compensates`, `test_rec02_04_compensation_on_post_write_cas_race`, and `test_rec02_04_cas_conflict_on_shared_cache_key_preserves_existing_file_and_concurrent_same_content`.
3. **Concurrency & Restart Durability (`test_rec02_04_restart_durability_and_concurrent_cas`):**
   - Two threads synchronized via `threading.Barrier(2)` racing on disposable PostgreSQL with `expected_asset_id=base_asset.id`: **exactly 1 succeeds and 1 raises `StateConflict`**.
   - Fresh repository/storage instances read back the persisted `Asset` and scene binding cleanly.
4. **End-to-End Consumer Proof (`test_rec02_04_import_associate_render_consumer_proof`):**
   - Imported a real FFmpeg-generated H.264 MP4 (`scene 1`) and a real PIL-generated PNG (`scene 2`) via `ImportExternalMedia`, read back scene bindings from `PostgresScriptRepository` + `PostgresAssetRepository`, and rendered a real MP4 through `PlanFfmpegRenderer.render()`.
   - `ffprobe` on rendered output verified: 1 `h264` video stream, `1080x1920`, `duration >= 2.0s`.
   - **Scope Note:** HTTP upload route (`POST /studio/videos/{video_id}/scenes/{scene_id}/media/import`) and Studio storyboard preview UI wiring for `GAI-01` remain scoped to `REC-03.01` (`R08`).

---

## 4. Modified / Added Files & Rollback

### Modified
- `renderer/app/studio/domain/asset_registry.py`
- `renderer/app/studio/application/ports.py`
- `renderer/app/studio/application/media.py`
- `renderer/app/studio/adapters/storage.py`
- `renderer/app/studio/adapters/postgres/media_repo.py`
- `renderer/app/studio/composition/wiring.py`
- `tests/test_int_05_studio_assets.py`

### Added
- `renderer/app/studio/adapters/media_probe.py`
- `tests/test_rec_02_media_import.py`
- `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-02/rec-02-03-04-media-evidence.md`

### Rollback Plan
- Before commit: `git checkout -- renderer/app/studio tests/test_int_05_studio_assets.py` and remove the 3 untracked files.
- After commit: `git revert <commit_sha>` (zero schema migrations added).
