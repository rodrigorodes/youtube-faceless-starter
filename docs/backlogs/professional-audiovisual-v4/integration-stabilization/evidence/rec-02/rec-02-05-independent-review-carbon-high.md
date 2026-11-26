# Independent Voice Sanitation Review — `REC-02.05` (`R09`)

- **Reviewer / Model:** `rec02-voice-rev` (`Gemini 4 Carbon High`)
- **Review Rounds:** Round 1 (REJECTED — `8.025/10`, 4 actionable P1 findings in `#21`) -> Round 2 (**APPROVED (`VERIFIED`)** — `9.50/10` after `#22`)
- **Branch / Base HEAD:** `develop` @ `d9fd1cd2f731de138070394718a2f2b733bf49cf` (uncommitted working tree diff from `#22`)
- **Reviewed App Hash / Migrations:** `hash renderer/app: 72f8c9da952644d3` (checkout == image), `migrações: 49/49`
- **`main` Branch Check:** `42700cb331165a68455173a91c463d4733292cfd` (untouched)
- **External API Spend:** `$0.00` (100% offline execution inside disposable container)
- **Publication Kill Switch:** Preserved (`publication_enabled=False`, `publication_execution.py` untouched)
- **Final Decision (Round 2):** **APPROVED (`VERIFIED`)** — **`REC-02.05`: `9.50/10`** (all 5 dimensions `9.5 >= 9.0`, zero P0/P1 blockers)

---

## 1. Round 1 Findings & Round 2 Verification Trail

All four Round 1 P1 findings (`#21`) were remediated by `@rec02-voice` (`#22`) and independently verified in code and container execution:

| Finding | Severity | Round 1 Defect (`hash=4b9534c218c9956b`) | Round 2 Resolution Verified (`hash=72f8c9da952644d3`) |
|---|---|---|---|
| **F1** | **P1** | `voice_kokoro.py:155-156` mutated `os.environ["HF_HUB_OFFLINE"] = "1"` and `os.environ["TRANSFORMERS_OFFLINE"] = "1"` globally without restoring prior state on exit/exception. | **RESOLVED:** Added `offline_environment_guard()` (`voice_kokoro.py:43-58`) wrapping `_synthesize_native` (`voice_kokoro.py:180`), snapshotting prior `os.environ.get(...)` values and restoring/popping them in `finally:`. Verified on both success and exception by `test_kokoro_native_zero_environ_leakage` (`test_v4_voice_professional.py:414-458`). |
| **F2** | **P1** | `_synthesize_native` (`voice_kokoro.py:170-218`) crashed on `bytes` chunks (`0-D \|S` array in `np.concatenate`), wrote silent WAVs when generator yielded zeros (`peak == 0`), and skipped peak headroom scaling when `soundfile` was installed. | **RESOLVED:** `_synthesize_native` (`voice_kokoro.py:193-260`) decodes `bytes`/`bytearray`/`memoryview` as `<i2` PCM (failing closed on odd byte length), supports `.detach().cpu().numpy()`, `list`, and `numpy`, flattens `.reshape(-1)` for `(N, 1)` 2D tensors, rejects non-finite (`~np.all(np.isfinite)`) values, normalizes integer (`/ 32768.0`) vs float32 uniformly, enforces headroom (`<= 30000 < 32760`), rejects silence (`peak_pcm < 300`) *before* creating `out_path` (`not out_path.exists()`), and writes deterministic 16-bit mono 24kHz WAV via stdlib `wave` (unnormalized `soundfile` branch removed). Verified by `test_kokoro_native_chunk_types_handling`, `test_kokoro_native_silence_fails_closed_and_leaves_no_file`, and `test_kokoro_native_overshoot_headroom_normalization`. |
| **F3** | **P1** | `KOKORO_WEIGHTS_EXTENSIONS` included `".json"` and `p.is_file()` skipped extension checks (`voice_kokoro.py:35,59`), allowing `config.json`-only dirs or `.txt` files to set `validated=True`; `"kokoro"` omitted from `FREE_PROVIDERS` and `local` in `_provider_probes`. | **RESOLVED:** Restricted `KOKORO_WEIGHTS_EXTENSIONS = {".onnx", ".pth", ".pt", ".bin", ".safetensors"}` (`voice_kokoro.py:39`), enforced binary extension + non-zero size check on `p.is_file()` (`voice_kokoro.py:82-85`), and added `"kokoro"` to `FREE_PROVIDERS` (`providers.py:18`) and `local` in `_provider_probes` (`providers.py:206`). Verified by `test_int_02_kokoro_json_or_txt_only_does_not_validate` and `test_int_02_kokoro_in_free_providers_and_local_probe`. |
| **F4** | **P1** | Residual `if not is_kokoro_installed():` conditional skips in `test_int_02_providers.py:25,39,65` and `test_v4_voice_professional.py:206`. | **RESOLVED:** Confirmed via `git grep -n "is_kokoro_installed" tests/` — zero `if not is_kokoro_installed():` guards remain; all assertions run unconditionally using deterministic `monkeypatch` (`_patch_kokoro_absent` and explicit `find_spec` / `KOKORO_WEIGHTS_DIR` / `KOKORO_DEFAULT_WEIGHTS_DIR` overrides). `rec-02-05-voice-evidence.md` updated to match Round 2 (`105 passed`, `hash=72f8c9da952644d3`). |

---

## 2. Independent Container Verification (Round 2 Observed)

### 2.1. Canonical `REC-02.05` Verification Suite (6 files)

Executed independently on the Round 2 working tree:

```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh \
  tests/test_int_02_providers.py \
  tests/test_v4_voice_professional.py \
  tests/test_channel_api.py \
  tests/test_provider_catalog.py \
  tests/test_provider_service.py \
  tests/test_architecture.py
```

- **Container Alignment:** `HEAD=d9fd1cd alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=72f8c9da952644d3 imagem=72f8c9da952644d3`, `migrações: checkout=49 imagem=49`
- **Result:** `105 passed, 1 warning in 12.05s` (0 failed, 0 skipped)
- **Exit Code:** `0`
- **Suite Breakdown:**
  - `tests/test_int_02_providers.py`: `8 passed`
  - `tests/test_v4_voice_professional.py`: `24 passed`
  - `tests/test_channel_api.py`: `19 passed`
  - `tests/test_provider_catalog.py`: `32 passed`
  - `tests/test_provider_service.py`: `13 passed`
  - `tests/test_architecture.py`: `9 passed`

### 2.2. Additional Adjacent Regression Verification (4 files)

Executed independently to verify zero side-effects on provider extensibility, panel cost classification (`FREE_PROVIDERS`), composition voice resolution, and Piper TTS calibration:

```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/test-container.sh \
  tests/test_v4_provider_extensibility.py \
  tests/test_panel_domain.py \
  tests/test_composition.py \
  tests/test_tts_calibration.py
```

- **Result:** `67 passed in 29.85s` (0 failed, 0 skipped)
- **Exit Code:** `0`
- **Combined Independent Container Total:** **`172 passed` (`105 + 67`), `0` failed, `0` skipped, `0` relaxed assertions**.

---

## 3. Technical Checklist Verification (`prompts/REC-02-av-media.md` & `RECOVERY-REVIEW.md` `R09`)

1. **Kokoro Offline Verification & Fail-Closed:**
   - Never marks `validated=True` via `find_spec("kokoro")` alone (`providers.py:151-152,175-178` & `voice_catalog.py:101-104` call `is_kokoro_offline_ready()`).
   - Verifies real local non-empty binary weight files (`.onnx`, `.pth`, `.pt`, `.bin`, `.safetensors`); `.json`/`.txt` rejected (`voice_kokoro.py:39,60-93`).
   - Enforces `HF_HUB_OFFLINE="1"` and `TRANSFORMERS_OFFLINE="1"` via `offline_environment_guard()` (`voice_kokoro.py:43-58,180`) with zero `os.environ` side-effect leakage.
   - Fails closed with `ModelUnavailable` when package or local weights are absent (`voice_kokoro.py:152-159`).
2. **`_synthesize_native` Multi-Chunk Concatenation & Edge Cases:**
   - Concatenates ALL chunks across generator (`np.concatenate(chunks, axis=0)`, `voice_kokoro.py:193-235`), verified (`54000` frames == `12000 + 24000 + 18000`, `2.25s`).
   - Handles empty generator (`ModelUnavailable`), `bytes`/`bytearray`/`memoryview` 16-bit PCM, `torch`-like `.detach().cpu().numpy()`, `list`, `numpy`, 2D `(N, 1)` tensors, `NaN`/`Inf` rejection, zero-amplitude/silence rejection (`peak_pcm < 300`, `not out_path.exists()`), and overshoot headroom scaling (`<= 30000 < 32760`).
   - Tested deterministically with zero conditional skips.
3. **`allow_synthetic_fixture` Production Guard:**
   - Defaults to `False` (`voice_kokoro.py:121`) and is never enabled in production `wiring.py:331` (`build("voice", "kokoro:pt_br-af_bella").allow_synthetic_fixture is False`).
4. **Real Offline `PiperVoice("pt_BR-faber-medium")` Synthesis:**
   - Verified inside `./scripts/test-container.sh` with `/opt/voices/pt_BR-faber-medium.onnx`: valid RIFF/WAV 16-bit mono 22050 Hz, real PT-BR narration (`duration > 1.0s`, `RMS > 300`, safe headroom `peak <= 30000`, `is_clipped=False`, `is_silent=False`, `$0.00` offline).
5. **Auditable `FallbackVoice`:**
   - Verified `KokoroVoice` (`ModelUnavailable`) -> `PiperVoice("pt_BR-faber-medium")` with `on_fallback` callback recording `("kokoro", "ModelUnavailable")` and `last_used == "piper"`.
6. **`ElevenLabsVoice` Disabled:**
   - Remains `validated=False` (`providers.py:179-181`, `voice_catalog.py:105-106`), `$0.00` spend, fails closed with `ProviderMissingCredential` / `NotImplementedError`.

---

## 4. Rubric Scoring Table (`QUALITY-RUBRIC.md` — Round 2 Final)

Threshold: **>= 9.0 in every applicable dimension**, **weighted mean >= 9.0** (no rounding), **zero P0/P1 blockers**.

| Dimensão | Peso | Nota | Evidência / Achado |
|---|---:|---:|---|
| Correção funcional e integração | 25% | 9.5 | `is_kokoro_offline_ready` exige pacote + pesos binários locais (`.onnx`/`.pth`/`.pt`/`.bin`/`.safetensors`); `_synthesize_native` concatena todos os chunks (`bytes`/`torch`/`list`/`numpy`/2D), normaliza headroom (`<= 30000`) e rejeita silêncio (`< 300`) sem criar arquivo; `PiperVoice("pt_BR-faber-medium")` sintetiza WAV PT-BR real em container; `FallbackVoice` audita contingência Kokoro -> Piper; `ElevenLabsVoice` permanece inativo (`validated=False`). *(Nota de escopo: integração de catálogo/pré-processamento vocal ao pipeline segue rastreada em `REC-03.03` conforme `TRACEABILITY-MATRIX.md`.)* |
| Arquitetura e simplicidade | 20% | 9.5 | Fronteiras Clean Architecture intactas (`test_architecture.py` `9/9`); `offline_environment_guard` sem vazamento em `os.environ`; `"kokoro"` registrado em `FREE_PROVIDERS` e `_provider_probes` (`LocalProviderProbe`); escrita WAV 16-bit unificada via stdlib `wave` sem dependência inconsistente de `soundfile`. |
| Testes e regressão | 20% | 9.5 | `105 passed` nas 6 suítes canônicas (`12.05s`, exit `0`) + `67 passed` em 4 suítes adjacentes (`29.85s`, exit `0`) = `172/172` aprovados, zero skips condicionais (`if not is_kokoro_installed()`), zero assertions relaxadas, cobertura determinística de sucesso, falha e fronteira. |
| Segurança, orçamento e confiabilidade | 20% | 9.5 | `$0.00` de gasto externo; `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1` isolados por context manager; falha fechada (`ModelUnavailable`) para ausência de pacote/pesos, `.json`/`.txt`, generator vazio, `NaN`/`Inf`, bytes ímpares e silêncio; `allow_synthetic_fixture=False` em produção; kill switch `publication_enabled=False` e `main` (`42700cb`) intactos. |
| Evidências e operação | 15% | 9.5 | Evidência completa em `rec-02-05-voice-evidence.md` com reprodução Red pré-fix, trilha de remediação F1–F4, matriz de casos negativos, métricas reais do WAV Piper, alinhamento de hash (`72f8c9da952644d3`, `migrações: 49/49`) e plano de rollback limpo. |

- **Média Ponderada Exata (`REC-02.05` — Round 2 Final):** `9.50` (`0.25*9.5 + 0.20*9.5 + 0.20*9.5 + 0.20*9.5 + 0.15*9.5 = 9.50`, sem arredondamento)
- **Gates Aplicáveis:** R09, A01, A02, INT-02.01–03, V4-02.01–04/14, Clean Architecture (`test_architecture.py`), `$0.00` offline
- **Bloqueios P0/P1:** Nenhum (`0` bloqueios)
- **Decisão Final (`REC-02.05`):** **APPROVED (`VERIFIED`)**
