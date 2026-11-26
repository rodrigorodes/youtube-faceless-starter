# REC-04.02 (`R11`) — Evidência do Documentário Real 5–8 min Pareado com V4-00

**Data (UTC):** 2026-11-26T23:34:45Z  
**Branch:** `develop` (HEAD base `ea07c0c`, com alterações locais não commitadas para review independente)  
**Requisito:** `R11` / `REC-04.02`  
**Status Técnico:** `PASS` | **Homologação Audiovisual Humana:** `AWAITING_HUMAN_REVIEW` *(nunca simulada)*  
**Custo Externo:** `$0.00` (`usage_ledger` e `GET /studio/videos/{id}/cost-breakdown`)  
**Kill Switch de Publicação:** `STUDIO_PUBLICATION_ENABLED=0` → `BLOCKED` (`youtube_video_id=null`, vídeo mantido em `AWAITING_APPROVAL`)

---

## 1. Pré-requisitos Executados (Tests-First)

1. **P2-1 — Geometria segura de PiP/overlays vs HUD/Disclosure (`render.py`):**
   - `_overlay_placement(position)` em [render.py](file:///Users/rodrigomendes/youtube-faceless-starter/renderer/app/studio/application/render.py#L141-L152) posiciona overlays ímpares à direita (`x=0.94, y=0.28`) e pares à esquerda abaixo da safe-zone do HUD/disclosure (`x=0.06, y=0.50`, evitando `x<=600, y<=260` e a faixa inferior de legendas em 1080p horizontal e vertical).
   - Verificado por testes determinísticos de geometria em [tests/test_render.py](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_render.py#L725-L780) e por medição de pixels na Cena 1 do documentário (`scene1_hud_top_left_during_pip_diff = 3.84 < 5.0` enquanto `scene1_mp4_pip_enter_diff = 124.04`).
   - Hashes e cache de vídeos sem PiP preservados integralmente (`tests/test_render_golden.py` verde).

2. **PRE-1 — Bug preexistente de legenda duplicada em cenas de vídeo base / planos mistos (`render_compiler.py`):**
   - **Classificação:** Bug preexistente (não regressão). Em planos `v2` com `reference.media_type == "video"` ou `has_pacing`, `shot_subtitles` permanecia preenchido em cenas de shot único, queimando simultaneamente `caption_overlay` (Pillow) no shot e `-vf subtitles=...` (ASS) na etapa final.
   - Correção mínima em [render_compiler.py](file:///Users/rodrigomendes/youtube-faceless-starter/renderer/app/studio/application/render_compiler.py#L204-L225): `use_global_ass_only = plan.schema_version >= 2 and (len(scene.base_shots) > 1 or reference.media_type == "video" or has_pacing)`.
   - **Impacto em hash de cache:** Muda apenas para planos `v2` com mídia base de vídeo ou planos com pacing que misturam cenas de shot único (onde antes havia duplicação errônea de Pillow + ASS). Planos `v1`, planos `v2` compostos só de imagens sem pacing e fixtures golden preservam exatamente os mesmos hashes (`tests/test_render_golden.py` verde; testes dedicados em [tests/test_render_plan_compiler_v2.py](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_render_plan_compiler_v2.py#L308-L398)).

3. **P2-4 — Versão real do pacote `piper-tts` (`tests/rec04_helpers.py`):**
   - `piper_version()` consulta `importlib.metadata.version("piper-tts")` em vez de `piper --version` (que imprimia `usage:`), registrando **`piper-tts==1.8.0`** nos manifestos de `REC-04.01` e `REC-04.02`.

4. **Bug adicional descoberto e corrigido durante o piloto (`facts.py`):**
   - Em [facts.py](file:///Users/rodrigomendes/youtube-faceless-starter/renderer/app/studio/domain/facts.py#L97), `_WORDS.get("zero")` retornava `0` (falsy), caindo em `_ARTICLE_UNITS["zero"]` e levantando `KeyError: 'zero'`. Corrigido para `current += _WORDS[word] if word in _WORDS else _ARTICLE_UNITS[word]`, com cobertura unitária dedicada em [tests/test_facts.py](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_facts.py#L188-L195).

---

## 2. Entrega do Documentário Real (`REC-04.02`) via Studio

- **Teste automatizado:** [tests/test_rec_04_documentary.py](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_rec_04_documentary.py) (`@pytest.mark.rec04_documentary`)
- **Runner reproduzível:** [scripts/run-rec04-documentary.sh](file:///Users/rodrigomendes/youtube-faceless-starter/scripts/run-rec04-documentary.sh)
- **Diretório exclusivo da execução (gitignored):** `storage/output/runs/rec04_doc_20261126_233034_ea07c0c/`
  - **MP4 final:** `storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4` (`232.080.906` bytes, ~221,3 MB)
  - **SHA-256 do MP4:** `62eb3b8e335cac167bce65e5a0e4c6c9a6560cc4cd03f018a7418e82f554daa9`
  - **Manifesto versionado:** [manifest.json](file:///Users/rodrigomendes/youtube-faceless-starter/docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-02/manifest.json)
- **Caminho executado:** Rotas HTTP reais do Studio (`POST /studio/projects`, `POST /studio/videos`, `PUT /direction`, `POST /sources`, `POST /script`, `POST /script/scenes/{idx}`, `POST /script/scenes`, `POST /scenes/{sid}/media/import`, `POST /scenes/{sid}/assets`, `POST /production-runs`, `GET /subtitles`, `/subtitles.vtt`, `/subtitles.ass`, `GET /thumbnail`, `GET /cost-breakdown`, `POST /publication/publish`, `GET /file`) + Postgres 16 efêmero em `tmpfs` + `ProductionCoordinator` + `PlanFfmpegRenderer` + `PiperVoice("pt_BR-faber-medium")` + `FfmpegQualityEvaluator`/`FfmpegQa`.

### Composição e Proveniência (100% `CC0-1.0`)
- **Tema e linhagem:** *"A História da Computação: Da Mecânica aos Cérebros de Silício"* (mesma linha cronológica de V4-00).
- **Rebaseline controlado vs V4-00:** V4-00 possuía 18 cenas em `345,80 s`; `REC-04.02` expande para **25 cenas** em **`309,80 s`** (estritamente dentro de 300–480 s e `>= 25` cenas conforme `SESSION-HANDOFF.md` §5), mantendo formato `1920x1080` (`16:9`), `25 fps`, H.264/AAC, `pt_BR-faber-medium` e `$0.00`.
- **Mídias:** 17 cenas com PNG 1080p importado via HTTP, **3 cenas com MP4 1080p 25fps em movimento contínuo** (cenas 2, 10 e 18 — exercitando `PRE-1` sem legenda duplicada), 5 cenas geradas localmente pelo `AssetsHandler` (cenas 20–24), e **3 overlays/PiP** (PNG badge cena 0 à direita, MP4 PiP cena 1 à esquerda com `P2-1`, PNG badge cena 12 à direita).

---

## 3. Métricas Medidas Diretamente no MP4 e Comparação Pareada com V4-00

| Métrica | Baseline V4-00 (`run_20261126_132447_198e47cb`) | `REC-04.02` (`rec04_doc_20261126_233034_ea07c0c`) | Delta / Observação |
|---|---:|---:|---|
| **Cenas** | 18 | **25** | `+7` (cumpre `>= 25`) |
| **Duração (`ffprobe`)** | 345,80 s | **309,80 s** | `-36,00 s` (dentro de 300–480 s) |
| **Resolução / FPS** | 1920x1080 / 25 fps (`h264`, `yuv420p`) | **1920x1080 / 25 fps** (`h264`, `yuv420p`, `7745` frames) | Paridade exata |
| **Áudio** | AAC, 96 kHz, stereo | **AAC, 96 kHz, stereo** (`159.156 bps`) | Paridade exata |
| **Loudness Integrado (`ebur128`)** | -15,6 LUFS | **-16,1 LUFS** | Alvo `-16.0 ± 1.5` atingido |
| **True Peak (`ebur128`)** | -1,3 dBTP | **-1,9 dBTP** | `<= -1.0 dBTP`, zero clipping |
| **Silence Ratio / Black Ratio** | 0,00% / 0,00% | **0,00% / 0,00%** | Zero silêncio/preto |
| **Frozen Ratio** | 0,4937 | **0,1632** | **`-0,3305`** (movimento real de B-rolls MP4 + PiP + Ken Burns) |
| **Drift Áudio–Legenda** | n/d no JSON V4-00 | **336 ms** (vs fim fala Piper) / **459 ms** (vs áudio MP4 com `TAIL_S=500ms`) | Dentro de `max_drift_ms=500ms`, `164` cues |
| **Tempo Run #1 (produção completa)** | 126,28 s (pipeline isolado) | **141,841 s** (Studio completo: DAG + Postgres + Piper + FFmpeg + QA) | Inclui E2E Studio + 25 cenas |
| **Tempo Run #2 (regeneração seletiva)** | n/a | **60,409 s** (**`-81,433 s` / `-57,41%`**) | **24/24 narrações e 66/66 shots visuais** intocados reusados do cache |
| **CPU Total (pai + filhos)** | 675,804 s | **1.027,749 s** (User `963,885 s`, Sys `63,864 s`) | Inclui Run #1 + Run #2 + QA + frames |
| **RAM Pico (`getrusage` Linux)** | Pai `1.346,53 MB` / Filhos `1.544,03 MB` (soma `2.890,56 MB`) | Pai **`1.402,08 MB`** / Filhos **`1.618,50 MB`** (soma **`3.020,58 MB`**) | Ressalva kernel `getrusage`: soma é limite superior teórico |
| **Custo API (`usage_ledger`)** | `$0.00` | **`$0.00`** | Zero chamadas pagas |

### Verificação `V2-F7` (Thumbnail) e Perfis
- **`GET /studio/videos/{id}/thumbnail`:** HTTP `200`, `image/jpeg`, `1280x720`, `67.870` bytes (`<= 2 MB`), SHA-256 `f06953f963016eeb9cdd6c690629f24244d4875f68190b30d81c02569d78f4db`.
- **`VideoPackaging` + `PillowThumbnail` (3 opções):** 3 variantes distintas validadas sem violações de limite (`limit_violations() == ()`) e 3 JPEGs 1280x720 gerados em `thumbnails/thumbnail_option_{1,2,3}.jpg`. *(Nota honesta: `GET /thumbnail` é a rota HTTP ativa em produção; `VideoPackaging` é verificado no domínio; e no gerador sintético de `test_rec_04_documentary.py`, as cenas 9 e 24 compartilham `idx % 5 == 4`, produzindo JPEGs idênticos para as opções sintéticas 2 e 3 enquanto os 3 conceitos `VideoPackaging` são distintos.)*
- **Perfis:**
  - `economic_local`: **EXECUTED** (`demo:v4`, `placeholder:v4`, `piper:pt_BR-faber-medium`, `ffmpeg`, `$0.00`).
  - `balanced_local`: **DEFERRED** (`BLOCKED_LOCAL_PAID_DEPENDENCY` — container offline sem APIs pagas nem GPU local; orçamento travado em `$0.00`).
  - `premium`: **OUT_OF_SCOPE** (requer autorização explícita do operador e orçamento pago).

---

## 4. Frames Extraídos para Inspeção Visual

Todos preservados em `storage/output/runs/rec04_doc_20261126_233034_ea07c0c/frames/`:
1. `scene00_png_overlay.png` (`scene_starts[0]+1.60s` extraído, `1.80s` rotulado no manifesto) — Cena 0 com overlay PNG à direita (`diff_enter=100.97`, `diff_exit=101.01`)
2. `scene01_mp4_pip.png` (`scene_starts[1]+1.10s` extraído, `13.80s` rotulado no manifesto) — Cena 1 com PiP MP4 à esquerda sem colisão com HUD (`diff_hud=3.84`, `diff_motion=157.63`)
3. `scene02_imported_mp4.png` (`28.24s`) — Cena 2 com MP4 base importado e ASS único (`PRE-1`, `diff_motion=87.16`)
4. `scene12_mid_overlay.png` (`154.72s`) — Cena 12 no meio do documentário com overlay PNG
5. `scene15_edited_v2.png` (`191.90s`) — Cena 15 após edição e regeneração seletiva
6. `scene18_imported_mp4.png` (`228.58s`) — Cena 18 com B-roll MP4 importado
7. `scene21_studio_generated.png` (`264.14s`) — Cena 21 gerada localmente pelo `AssetsHandler`
8. `scene24_end_doc.png` (`299.94s`) — Cena 24 encerramento do documentário

Para assistir ao MP4 no macOS:
```bash
open "storage/output/runs/rec04_doc_20261126_233034_ea07c0c/rec04_02_documentary.mp4"
```
