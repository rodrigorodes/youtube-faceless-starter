# REC-04.02 (`R11`) — Independent Review (`Gemini 4 Neon High`) — Round 1 & Round 2 (Final)

**Data (UTC):** `2026-11-26T23:47Z` (Round 1: `23:41Z` → Round 2: `23:47Z`)  
**Reviewer Independente:** `rec04-doc-rev` (`Gemini 4 Neon High`, sessão separada do executor `rec04-doc`)  
**Branch / Base HEAD:** `develop` @ `ea07c0cae71ba49b2269bc3a6d1abb922aa3698b` (+ diff local não commitado, `hash renderer/app = b677160103d832a3`, `49` migrações)  
**Escopo Auditado:** `REC-04.02` (`R11` — Documentário real 5–8 min pareado com V4-00) + pré-requisitos `P2-1`, `PRE-1`, `P2-4` + correção `facts.py` (`KeyError: 'zero'`)  
**Decisão Final (Round 2):** **`APPROVED` (Técnico)** — Média Ponderada Exata **`9.400 / 10`** (mínimo por dimensão: **`9.3 >= 9.0`**, **0 P0 / 0 P1 / 3 P2 não-bloqueantes**)  
**Histórico de Rounds:** Round 1 `REJECTED` (`9.190/10`, `Testes e regressão = 8.5 < 9.0`, 1 P1: `P1-1` sem teste unitário em `tests/test_facts.py`) → Round 2 `APPROVED` (`9.400/10`, `P1-1` fechado com mutação morta e `P2-A`/`P2-B` documentados com transparência)  
**Homologação Audiovisual Humana:** **`AWAITING_HUMAN_REVIEW`** *(nunca autoaprovada; requer avaliação real >= 9,0/10 do operador humano)*

---

## 1. Tabela de Rubrica Final (`QUALITY-RUBRIC.md` — Round 2, sem arredondamento)

| Dimensão | Peso | Round 1 | Round 2 (Final) | Ponderada R2 | Evidência Verificada | Achados R2 |
|---|---:|---:|---:|---:|---|---|
| Correção funcional e integração | 25% | 9.3 | **9.3** | 2.325 | MP4 real `309.80s` (25 cenas, 1080p25 H.264/AAC, `-16.1 LUFS`, `-1.9 dBTP`, `0.1632` frozen_ratio vs `0.4937` V4-00, `336ms` drift) via rotas HTTP do Studio, Postgres 16 tmpfs, Piper real, regeneração seletiva (`-57.41%`, 24/24 narrações e 66/66 shots reusados), `GET /thumbnail` 1280x720 JPEG (`67,870` B), `P2-1` e `PRE-1` confirmados visualmente em frames | `P2-A`, `P2-C` |
| Arquitetura e simplicidade | 20% | 9.4 | **9.4** | 1.880 | Correções mínimas e cirúrgicas em `render.py` (`_overlay_placement`), `render_compiler.py` (`use_global_ass_only`) e `facts.py` (`word in _WORDS`); `tests/rec04_helpers.py` bem fatorado; `test_architecture.py` e `test_render_golden.py` verdes | `P2-C` |
| Testes e regressão | 20% | 8.5 | **9.4** | 1.880 | Suíte container `182 passed in 83.61s` (exit `0`), zero asserts relaxados; **`P1-1` fechado** (`test_numbers_in_and_check_narration_handle_word_zero` em `tests/test_facts.py`); **todas as 3 mutações isoladas em `/tmp` mortas** (`P2-1`, `PRE-1`, `facts.py`) | `P2-A` |
| Segurança, orçamento e confiabilidade | 20% | 9.6 | **9.6** | 1.920 | `$0.00` confirmado (`usage_ledger` + `/cost-breakdown`), `STUDIO_PUBLICATION_ENABLED=0` → `BLOCKED` (`youtube_video_id=null`), `AWAITING_HUMAN_REVIEW` honesto (`auto_approved_in_test=false`), 100% `CC0-1.0`, zero MP4/PNG rastreados no Git (`storage/output/*` gitignored), negativos fail-closed em `_overlay_layers`, Postgres descartável com proof guard | — |
| Evidências e operação | 15% | 9.1 | **9.3** | 1.395 | `scripts/run-rec04-documentary.sh` executável, `manifest.json` idêntico entre run dir e versão versionada, 100% dos hashes SHA-256 / `ffprobe` / `ebur128` e baseline V4-00 reconciliados, `piper-tts==1.8.0` (`P2-4`), `PRE-1` classificado como bug preexistente, `balanced_local` `DEFERRED` / `premium` `OUT_OF_SCOPE` honestos, `P2-A` e `P2-B` documentados transparentemente em `rec-04-02-documentary-evidence.md` | `P2-A`, `P2-B` |
| **Média Ponderada Exata** | **100%** | 9.190 *(REJ)* | — | **9.400** | **Mínimo por dimensão: `9.3 >= 9.0` — APROVADO (TÉCNICO)** | **0 P0 / 0 P1 / 3 P2** |

---

## 2. Verificação Independente Executada

### 2.1 Integridade do Artefato MP4 e Manifesto em Disco
Verificação direta sobre `storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4`:
- **Preservação de integridade no Round 2:** `renderer/` não sofreu nenhuma alteração entre Round 1 e Round 2 (`hash renderer/app = b677160103d832a3` inalterado), preservando 100% a validade do MP4 já gerado e auditado.
- **`shasum -a 256`:** `62eb3b8e335cac167bce65e5a0e4c6c9a6560cc4cd03f018a7418e82f554daa9` (`232,080,906` bytes) — **confere exatamente** com `manifest.json` e `rec-04-02-documentary-evidence.md`.
- **Demais artefatos:** Todos os 8 PNGs em `frames/`, 3 legendas em `subtitles/` (`164` cues `Dialogue:` em `.ass`, última cue `.srt` encerrando em `00:05:09,340` = `309,340 ms`) e 4 JPEGs em `thumbnails/` conferem byte a byte com `manifest.json`. `diff -u` entre `storage/output/runs/.../manifest.json` e `evidence/rec-04/rec-04-02/manifest.json` retornou vazio.
- **`ffprobe` direto no MP4:**
  - `duration`: `309.800000s` (5m09.8s, dentro de 300–480s)
  - Vídeo: `h264`, `1920x1080`, `r_frame_rate=25/1`, `nb_frames=7745`, `pix_fmt=yuv420p`, `bit_rate=5827249 bps`
  - Áudio: `aac`, `96000 Hz`, `stereo` (`2` canais), `duration=309.799000s`, `bit_rate=159156 bps`
  - Container: `bit_rate=5993051 bps` — **todos idênticos ao manifesto**.
- **FFmpeg `ebur128=peak=true` independente:**
  - Integrated loudness: **`-16.1 LUFS`** (LRA `4.8 LU`)
  - True peak: **`-1.9 dBFS`** (`-1.9 dBTP <= -1.0 dBTP`) — **idêntico ao manifesto**.
- **Baseline V4-00 (`storage/output/runs/run_20261126_132447_198e47cb/v4_baseline_metrics.json`):** todos os campos pareados conferidos contra o arquivo real em disco (`345.8s`, `18` cenas, `48886a20...`, `-15.6 LUFS`, `-1.3 dBTP`, `frozen_ratio 0.4937`, `cpu 675.804s`, `rss 1346.53/1544.03 MB`). Rebaseline controlado (18 → 25 cenas) claramente justificado.
- **Git hygiene:** `git check-ignore -v` confirmou `storage/output/*` ignorado pelo `.gitignore`; nenhum MP4/PNG/JPEG/WAV presente em `git status -s`.

### 2.2 Inspeção Visual de Frames (6 PNGs + 3 JPEGs lidos via `read_file`)
- **`frames/scene01_mp4_pip.png` (`P2-1`):** Selo "Ilustração gerada por IA" e pílula magenta "FATO" no canto superior esquerdo totalmente íntegros, **zero sobreposição**. Caixa PiP ciano posicionada com folga abaixo do HUD (`y=297..783`) e acima da legenda ASS única ("Na Revolução Científica,").
- **`frames/scene02_imported_mp4.png` e `frames/scene18_imported_mp4.png` (`PRE-1`):** Cenas de vídeo base importado exibem **uma única legenda ASS limpa** na base (com realce amarelo por palavra ativa na cena 18: *"pesquisadores criaram a interface gráfica"*), sem qualquer duplicação Pillow.
- **`frames/scene00_png_overlay.png`:** HUD superior esquerdo intacto, badge PNG amarelo à direita sem colisão, legenda ASS única na base.
- **`frames/scene15_edited_v2.png`:** Reflete a edição seletiva da Cena 15 (nova imagem circuito roxo/dourado e legenda *"A integração em silício evoluída por Noyce"*).
- **`frames/scene21_studio_generated.png`:** Cena gerada localmente pelo `AssetsHandler` com disclosure e legenda ASS ativa.
- **`thumbnails/thumbnail_http_primary.jpg`, `thumbnail_option_2.jpg`, `thumbnail_option_3.jpg`:** Todos válidos `1280x720` JPEG (`thumbnail_option_2.jpg` e `thumbnail_option_3.jpg` compartilham paleta `idx % 5 == 4`, agora explicitamente documentado em `rec-04-02-documentary-evidence.md`).

### 2.3 Suíte de Regressão Independente no Container (Round 2)
Comando executado:
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh \
  tests/test_render.py \
  tests/test_render_plan_compiler_v2.py \
  tests/test_render_compiler.py \
  tests/test_render_golden.py \
  tests/test_rec_04_vertical_slice.py \
  tests/test_architecture.py \
  tests/test_facts.py -ra
```
- **Resultado Round 2:** **`182 passed, 1 warning in 83.61s (0:01:23)`**, **exit code `0`** (Round 1: `181 passed in 84.02s`).
- **Alinhamento checkout x imagem:** `hash renderer/app: checkout=b677160103d832a3 imagem=b677160103d832a3`, `migrações: checkout=49 imagem=49`.

### 2.4 Testes de Mutação Isolados (Cópias em `/tmp`, fora do repositório)
1. **Mutação 1 (`P2-1` — `render.py` revertendo `(0.06, 0.50)` → `(0.06, 0.14)`):** **MORTA** (`FAILED tests/test_render.py::test_overlay_layers_never_overlap_top_left_hud_or_bottom_caption_safe_zones`).
2. **Mutação 2 (`PRE-1` — `render_compiler.py` revertendo `use_global_ass_only` para `len(scene.base_shots) == 1`):** **MORTA** (`2 failed`: `test_pre1_single_shot_video_scene_v2_uses_only_ass_subtitles_no_pillow_duplication` e `test_pre1_paced_mixed_plan_v2_uses_only_ass_subtitles_across_all_scenes`).
3. **Mutação 3 (`facts.py` — revertendo linha 97 para `_WORDS.get(word) or _ARTICLE_UNITS[word]`):**
   - Round 1: **SOBREVIVEU** (`64 passed in 0.08s`) → abriu `P1-1`.
   - Round 2: **MORTA** (`FAILED tests/test_facts.py::test_numbers_in_and_check_narration_handle_word_zero`, `KeyError: 'zero'`, `1 failed, 64 passed in 0.08s`) → **`P1-1` FECHADO**.

---

## 3. Rastreamento de Achados (P0 / P1 / P2)

### Fechado no Round 2
- **`P1-1` (FECHADO):** Adicionado `test_numbers_in_and_check_narration_handle_word_zero` em `tests/test_facts.py:188-195` cobrindo `numbers_in("zero") == {"0"}`, `numbers_in("sistema binário de zero e um") == {"0"}` e casos positivo/negativo em `check_narration`. Mutação reversa em `/tmp` morta com `KeyError: 'zero'`.

### Não-Bloqueantes (P2 — Documentados, sem impacto de bloqueio)
- **`P2-A` (Documentado):** Em `tests/test_rec_04_documentary.py:754-755`, os índices sintéticos `(0, 9, 24) % 5` produziram `(0, 4, 4)`, fazendo `thumbnail_option_2.jpg` e `thumbnail_option_3.jpg` compartilharem o mesmo JPEG (`53,757` B, `df9a0eed...`) enquanto as 3 variantes de domínio `VideoPackaging` são distintas e `GET /thumbnail` produz `thumbnail_http_primary.jpg` (`67,870` B, `1280x720`). Documentado honestamente em `rec-04-02-documentary-evidence.md:70`.
- **`P2-B` (Documentado):** Offsets exatos de extração dos frames 0 e 1 (`scene_starts[0]+1.60s` e `scene_starts[1]+1.10s`) vs rótulos gravados no manifesto (`1.80s` e `13.80s`) agora documentados explicitamente em `rec-04-02-documentary-evidence.md:81-82`.
- **`P2-C` (Registrado):** Caso residual em `PRE-1` para planos `v2` sem pacing (`has_pacing=False`) compostos exclusivamente de cenas de imagem de shot único (`render_compiler.py:221-225` preserva `shot_subtitles` para compatibilidade de golden/hashes enquanto `render_plan_compiler.py:240` anexa `-vf subtitles`). Não afeta fluxos reais do Studio (`has_pacing=True`) nem cenas de vídeo base (`reference.media_type == "video"`).

---

## 4. Veredicto Final e Gate
- **Decisão Técnica:** **`APPROVED` (`9.400 / 10`, mínimo `9.3 >= 9.0`, 0 P0 / 0 P1)** — apto para reconciliação de docs de estado e commit atômico de `REC-04.02` em `develop` (sem merge em `main`, sem push, sem publicação).
- **Gate Audiovisual Humano:** **`AWAITING_HUMAN_REVIEW`** — o operador humano deve assistir `storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4` e emitir nota audiovisual real (`>= 9,0/10`).
