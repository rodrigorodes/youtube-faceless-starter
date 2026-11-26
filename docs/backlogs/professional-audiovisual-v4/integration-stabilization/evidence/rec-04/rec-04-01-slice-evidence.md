# Evidência de Execução e Verificação: REC-04.01 (R11 — Vertical Slice Real 60–90s via Studio)

- **Data:** 26/11/2026
- **Branch:** `develop` (Base HEAD `4fa225b34853093097c40cce57b7a601ab753d2f` + working tree não comitado; `main` intocada em `42700cb331165a68455173a91c463d4733292cfd`)
- **Status:** `IMPLEMENTED_PENDING_REVIEW` (**NÃO** marcado como `VERIFIED`; homologação audiovisual permanece `AWAITING_HUMAN_REVIEW`)
- **Run ID do Artefato Preservado:** `rec04_slice_20261126_213537_4fa225b`
- **Governança, Custo & Isolamento:**
  - Custo externo em APIs pagas: **`$0.00`** (`usage_ledger` e `GET /studio/videos/{id}/cost-breakdown`; `budget_guard=True`, `max_cost_video=0.0`, `max_cost_month=0.0`, zero credenciais/chaves pagas, ElevenLabs desabilitado)
  - Kill switch de publicação: **`STUDIO_PUBLICATION_ENABLED=0`** → `POST /studio/videos/{id}/publication/publish` retornou `result="BLOCKED"`, `youtube_video_id=None`, `detail="publication is disabled by configuration (STUDIO_PUBLICATION_ENABLED=0)"`
  - Autoaprovação: **Nenhuma** (`POST /approve` nunca é chamado no slice; vídeo encerra em `AWAITING_APPROVAL` e run pausa em `WAITING_HUMAN` no estágio `approval`)
  - Portas DEV (`8000`/`5678`): **intocadas** (execução 100% em container isolado com Postgres efêmero em `tmpfs`, sem portas publicadas no host)
  - Git: **sem commit, sem push, sem alteração em `main`, sem binário MP4 rastreado** (`storage/output/runs/` está no `.gitignore`)

---

## 1. Artefatos e Hashes SHA-256

| Artefato | Caminho | Rastreado no Git? | SHA-256 |
|---|---|---|---|
| **MP4 Final (67.36s, 1080p)** | `storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4` (`53,226,343 bytes` / `50.76 MiB`) | Não (gitignored) | `088c11300a2b7f6737b13d2095741d3313bd27a487ff86e6876e2634ea92fcc3` |
| **Manifesto Versionado** | `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-01/manifest.json` | Sim (texto JSON) | `2165e8c731991e9e00d09a84abb0749e113aaa0d919bcc5c26cabbcd4ce8f676` |
| **Legendas Exportadas (SRT/VTT/ASS)** | `storage/output/runs/rec04_slice_20261126_213537_4fa225b/subtitles/subtitles.{srt,vtt,ass}` | Não (gitignored) | Ver `artifact.subtitles.*_sha256` no `manifest.json` |
| **Frames-Chave de Amostra (5 PNGs 640w)** | `storage/output/runs/rec04_slice_20261126_213537_4fa225b/frames/*.png` | Não (gitignored) | Ver `sampled_frames[].sha256` no `manifest.json` |
| **Wiring de Overlays no Studio** | `renderer/app/studio/application/render.py` | Sim | `f698a61472857f84e91e793912bf55d136b6b054ebabcf201c5cb2760d3fc32b` |
| **Marcadores Pytest** | `tests/conftest.py` | Sim | `69d9262a922c54daa0e2c64ed020894c267f819ca1bb433456c018f9d8b4011c` |
| **Reclassificação SMOKE (15s)** | `tests/test_int_06_pilot.py` | Sim | `d121c2038bd394525af90283612b72d22cc6dcbdcdf4a6d4009953e15bf07cf0` |
| **Teste Reproduzível REC-04.01** | `tests/test_rec_04_vertical_slice.py` | Sim | `77201f17bc4778d2e4241dfeff8652192775ab80a42e7c120ce0fd288183c66b` |
| **Runner Dedicado REC-04.01** | `scripts/run-rec04-slice.sh` | Sim | `207611f3f25b291c3efe97cfc06ef3623d1a9d0e389af785dd96c0fc7dff139b` |

- **Alinhamento checkout × imagem Docker:** `hash renderer/app = 8369da6e25579efe` (`checkout == imagem`), migrações `49/49`.
- **Versões no container:** `ffmpeg 7.1.5-0+deb13u1`, `ffprobe 7.1.5-0+deb13u1`, modelo Piper `/opt/voices/pt_BR-faber-medium.onnx`.

---

## 2. Como o Operador Reproduz e Assiste o MP4

### Assistir o artefato já preservado (Revisão Humana Audiovisual)
```bash
# macOS (QuickTime / player padrão)
open "storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4"

# Conferir integridade SHA-256 antes de assistir
shasum -a 256 "storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4"
# Esperado: 088c11300a2b7f6737b13d2095741d3313bd27a487ff86e6876e2634ea92fcc3
```

### Reproduzir do zero em container isolado (com preservação em `storage/output/runs/<run_id>/`)
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/run-rec04-slice.sh
```

### Executar apenas como pytest no container canônico (sem persistir MP4 no host)
```bash
PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" \
  ./scripts/test-container.sh tests/test_rec_04_vertical_slice.py -ra -v
```

---

## 3. Classificação Honesta por Requisito (R11 / REC-04.01)

| Requisito | Caminho Real Exercitado | Classificação | Evidência / Detalhe |
|---|---|---|---|
| **Caminho canônico HTTP do Studio + `ProductionCoordinator` + `PlanFfmpegRenderer`** | FastAPI `TestClient` + `make_router` + `Studio` + `POST /studio/videos/{id}/production-runs` (`script → factcheck → storyboard → assets → render → qa → approval`) | **`INTEGRATED`** | Run #1 e Run #2 executados pelas rotas HTTP reais do Studio com Postgres efêmero e `PlanFfmpegRenderer`; zero adaptadores isolados. |
| **Duração real 60–90s (1080p horizontal)** | `format="long"`, 5 cenas PT-BR | **`INTEGRATED`** | `ffprobe` mediu **`67.360 s`**, `1920x1080`, H.264 `yuv420p` (`25/1 fps`), AAC stereo (`6.32 Mbps`, `50.76 MiB`). |
| **Voz local real (Piper `pt_BR-faber-medium`, sem mock)** | `STUDIO_VOICE=piper:pt_BR-faber-medium` via `RunRender` + inspeção de WAV via `GET /scenes/{sid}/narration.wav` | **`INTEGRATED`** | 5 cenas sintetizadas localmente (`13.224s`, `11.714s`, `12.469s`, `14.408s`, `11.494s`; RMS PCM16 `3879.1–4639.7`, pico `30000`). |
| **Importação real de PNG e MP4 via rota HTTP (`REC-02.03/04`)** | `POST /studio/videos/{id}/scenes/{sid}/media/import` com licença `CC0-1.0`, CAS (`expected_asset_id`) e verificação de preview (`GET /scenes/{sid}/asset`) | **`INTEGRATED`** | PNGs 1080p (cenas 0, 1, 3), badge PNG 640x360, MP4 base 1080p 24s (cena 2) e MP4 PiP 640x360 5s importados com MIME validado (`image/png`, `video/mp4`). |
| **Overlays gráficos PNG e PiP vídeo MP4 via Studio HTTP** | `POST /studio/videos/{id}/scenes/{sid}/assets` (`role="overlay"`) → `RunRender._overlay_layers` → `RenderSpec.layers` → `PlanFfmpegRenderer` + `FfmpegOverlayVerifier` | **`INTEGRATED`** | Cena 0: overlay PNG (`enter_diff=88.56`, `exit_diff=88.59`). Cena 1: PiP MP4 animado (`enter_diff=107.92`, `motion_diff=134.38`, `exit_diff=94.01`). `render.overlay` em `qa_report.checks_run`. |
| **Motion (`CreativeBrief` → Ken Burns + MP4 em movimento)** | `PUT /studio/videos/{id}/direction` (`pacing="cinematic"`) propagado ao `RenderPlan` | **`INTEGRATED`** | Ken Burns na cena 0 (`motion_diff=8.74` entre `t=5.2s` e `t=8.0s`); MP4 base em movimento na cena 2 (`motion_diff=144.22`). |
| **Áudio multitrack com ducking (2 faixas: voz + trilha musical)** | `PlanFfmpegRenderer` (`music=True`, `sidechaincompress` ducking + `loudnorm`) | **`INTEGRATED`** | `integrated_lufs = -16.1 LUFS`, `true_peak_dbtp = -1.4 dBTP` (`ebur128=peak=true`); RMS durante fala `4203.7` e trilha presente na cauda entre cenas (`2894.7`). |
| **Áudio multitrack 3+ faixas (ambiência + SFX via `MultitrackAudioPlan` / `AudioCatalog`) nas rotas HTTP do Studio** | Sem rota HTTP/tabela no Studio para anexar faixas extras de ambiência/SFX | **`DEFERRED`** (`BLOCKED` na camada HTTP do Studio) | Motor validado em `PlanFfmpegRenderer` em `REC-02.02`, porém ainda não exposto em `routes.py`/`RunRender`. Não reivindicado como integrado no Studio. |
| **Transições inter-shot `xfade` (`crossfade`/`slide`/`wipe`) nas rotas HTTP do Studio** | `visual_style.TRANSITION_KINDS` aceita apenas `none`/`fade` | **`DEFERRED`** (`BLOCKED` na camada HTTP do Studio) | Motor validado em `PlanFfmpegRenderer` em `REC-02.01`, porém ainda não exposto nas rotas HTTP do Studio. |
| **Legendas derivadas do `RenderPlan` + `render.caption_sync`** | `GET /subtitles`, `/subtitles.vtt`, `/subtitles.ass` (`ExportSubtitles`) + `FfmpegQualityEvaluator` | **`INTEGRATED`** | 37 cues no `RenderPlan` v2; SRT/VTT/ASS refletem edição da cena 3 (`"microeletrônica"`); `render.caption_sync` executado e sem bloqueios. |
| **Edição de 1 cena + regeneração seletiva (`REC-03.03`)** | `POST /transition` (`AWAITING_APPROVAL → SCRIPTED`) → `POST /script/scenes/3` → `POST /media/import` cena 3 → Run #2 via `ProductionCoordinator` | **`INTEGRATED`** | Plano revisado `1 → 2`; **4/4** nós `narration` e **10/10** nós `visual` das 4 cenas intocadas (0, 1, 2, 4) preservaram exatamente `fingerprint`, `artifact_sha256`, `artifact_uri` e `mtime_ns`; cena 3 regenerada; tempo caiu de `26.778s` para `15.391s` (**`-11.386s` / `-42.5%`**). |
| **QA real (`ffprobe` + `ebur128` + `FfmpegQa` + `FfmpegQualityEvaluator`)** | `QaHandler` no `ProductionCoordinator` + `FfmpegQa().analyze(final_mp4)` | **`INTEGRATED`** | `coverage.status="verified"`, `is_publishable=True`, `0` achados bloqueantes, `10` checks executados; `black_ratio=0.0`, `silence_ratio=0.0`, `frozen_ratio=0.1455`. |
| **Avaliação semântica/estética multimodal automática** | Sem API paga configurada (`$0.00`) | **`BLOCKED`** (`not_verified`) | Registrado honestamente como `QaFinding(finding_id="semantic-not-verified", severity="info")`; requer revisão humana real. |
| **Reclassificação de `tests/test_int_06_pilot.py` como SMOKE** | Renomeado para `test_int_06_smoke_15s_studio_flow_with_ffmpeg_qa_and_kill_switch`, marcado `@pytest.mark.smoke`, docstring explícita | **`INTEGRATED`** | Todos os asserts originais preservados sem relaxamento; passou no container. |
| **Kill switch `BLOCKED` + custo `$0.00` + revisão humana pendente** | `STUDIO_PUBLICATION_ENABLED=0`, `budget_guard=True`, `max_cost_*=0.0`, sem `POST /approve` | **`INTEGRATED`** (governança técnica); **`AWAITING_HUMAN_REVIEW`** (aprovação audiovisual) | Publicação recusada com `BLOCKED`; custo observado `$0.00`; vídeo permanece em `AWAITING_APPROVAL`. |

---

## 4. Métricas Medidas (Origem & Unidades)

### 4.1 Mídia e Áudio (`ffprobe` + `FfmpegQa` / `ffmpeg ebur128=peak=true`)
- **Duração:** `67.360 s` (`ffprobe format.duration`)
- **Resolução / Codec Vídeo:** `1920x1080`, `h264`, `yuv420p`, `25/1 fps`, bitrate total `6,321,418 bps`
- **Codec Áudio:** `aac`, `96000 Hz`, `2 canais`, `158,554 bps`
- **Tamanho em disco:** `53,226,343 bytes` (`50.76 MiB`)
- **Loudness Integrado (`ebur128`):** **`-16.1 LUFS`** (alvo `-16 LUFS`, faixa esperada `[-20, -12]`)
- **True Peak (`ebur128=peak=true`):** **`-1.4 dBTP`** (teto `<= -1.0 dBTP`)
- **Defeitos estruturais (`FfmpegQa`):** `black_ratio = 0.0` (`0` intervalos), `silence_ratio = 0.0`, `frozen_ratio = 0.1455` (`14.55%`, abaixo do teto `20%`)

### 4.2 Verificações de Conteúdo de Pixels (diferença absoluta média RGB `0–255`)
- **Cena 0 — Overlay PNG (entrada / saída na região superior direita):** `88.56` / `88.59`
- **Cena 0 — Ken Burns (`t=5.2s` vs `t=8.0s`, frame inteiro):** `8.74`
- **Cena 1 — PiP MP4 (entrada / movimento ciano→magenta / saída na região superior esquerda):** `107.92` / `134.38` / `94.01`
- **Cena 2 — MP4 base importado (`t=2.0s` vs `t=6.0s`, frame inteiro):** `144.22`

### 4.3 Tempos por Etapa e Recursos (`time.monotonic` + Linux `resource.getrusage` no container)
| Etapa / Métrica | Valor Medido | Origem |
|---|---|---|
| Setup + Roteiro (5 cenas) | `0.343 s` | `time.monotonic` |
| Geração de fixtures + Import PNG/MP4 + Overlays | `3.562 s` | `time.monotonic` |
| **Run #1 (`ProductionCoordinator` completo: script→qa→pause)** | **`26.778 s`** | `time.monotonic` |
| Exportação de legendas v1 (SRT/VTT/ASS) | `0.036 s` | `time.monotonic` |
| Edição Cena 3 + Import PNG v2 | `0.137 s` | `time.monotonic` |
| **Run #2 (Regeneração seletiva via `ProductionCoordinator`)** | **`15.391 s`** (`-11.386 s` / `-42.5%`) | `time.monotonic` |
| Verificação de conteúdo (`ffprobe` + `ebur128` + frames + RMS) | `7.490 s` | `time.monotonic` |
| **Total wall-clock do slice** | **`54.093 s`** | `time.monotonic` |
| CPU processo Python (`ru_utime` / `ru_stime`) | `38.257 s` / `1.929 s` | `resource.getrusage(RUSAGE_SELF)` |
| CPU subprocessos FFmpeg/Piper (`ru_utime` / `ru_stime`) | `160.549 s` / `11.035 s` | `resource.getrusage(RUSAGE_CHILDREN)` |
| Pico RSS Python / Maior filho (`ru_maxrss`) | `911,100 KiB` (`889.7 MiB`) / `1,535,128 KiB` (`1.46 GiB`) | `resource.getrusage` (Linux container) |

---

## 5. Evidência Real de Verificação (Comandos & Resultados)

Todos os comandos executados em `/Users/rodrigomendes/youtube-faceless-starter` com `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`.

### 5.1 Runner Dedicado do Vertical Slice (`scripts/run-rec04-slice.sh`)
- **Comando:** `./scripts/run-rec04-slice.sh`
- **Resultado:** **`1 passed, 1 warning in 56.06s`** | **Exit code:** **`0`**
- **Saída:** MP4 + legendas + 5 frames + `manifest.json` gravados em `storage/output/runs/rec04_slice_20261126_213537_4fa225b/`.

### 5.2 Suíte Direcionada no Container Canônico (`scripts/test-container.sh`)
- **Comando:**
  ```bash
  ./scripts/test-container.sh \
    tests/test_rec_04_vertical_slice.py \
    tests/test_int_06_pilot.py \
    tests/test_v4_studio_real_flow_pilot.py \
    tests/test_architecture.py -ra -v
  ```
- **Resultado:** **`12 passed, 1 warning in 67.79s (0:01:07)`** (`0` falhas, `0` skips) | **Exit code:** **`0`**

### 5.3 Suíte Canônica Completa do Container (Regressão Total)
- **Comando:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q
  ```
- **Alinhamento:** `HEAD=4fa225b alterações_em_renderer/tests=sim`, `hash renderer/app: checkout=8369da6e25579efe imagem=8369da6e25579efe`, `migrações: checkout=49 imagem=49`
- **Resultado:** **`4502 passed, 26 skipped, 1 warning in 774.36s (0:12:54)`** (`0` falhas; total coletado: `4528`) | **Exit code:** **`0`**
- **Detalhamento dos 26 skips (estruturais da imagem slim, idênticos ao baseline REC-03.03):** `3` testes Playwright (`pytest_playwright` ausente na imagem slim) + `23` testes Node.js (`node` ausente na imagem slim).

---

## 6. Inspeção Visual dos Frames de Amostra & Limitações Honestas

Os 5 frames extraídos (`frames/scene0_png_overlay.png` .. `frames/scene4_studio_generated.png`) foram inspecionados visualmente:
- **Cena 0 (`scene0_png_overlay.png`):** grade escura com círculos concêntricos dourados, badge gráfico PNG visível no canto superior direito, disclosure `"Ilustração gerada por IA"`, selo `"FATO"` e legenda PT-BR ativa legível na base.
- **Cena 1 (`scene1_mp4_pip.png`):** gráfico de barras ciano ao fundo, PiP MP4 ciano com borda branca visível no canto superior esquerdo e legenda PT-BR ativa legível. **Achado visual honesto:** como `RunRender._overlay_layers` posiciona `position` par em `position_x=0.06, position_y=0.14`, o PiP da cena 1 sobrepõe parcialmente o selo `"FATO"` e o texto `"Ilustração gerada por IA"` no canto superior esquerdo — registrado como melhoria de layout (ex.: reservar safe-zone superior esquerda ou permitir coordenadas explícitas por overlay) para o próximo slice.
- **Cena 2 (`scene2_imported_mp4.png`):** vídeo MP4 1080p importado renderizado em tela cheia com lower-third `"Alan Turing e John von Neumann"` e legenda sincronizada.
- **Cena 3 (`scene3_edited_v2.png`):** imagem v2 (roxo/dourado) e legenda atualizada (`"1971 integrou milhares de transistores em"`) confirmando a regeneração seletiva.
- **Cena 4 (`scene4_studio_generated.png`):** imagem gerada localmente pelo `AssetsHandler` (`placeholder:v4`, gradiente limpo) com legenda sincronizada.

### Limitações conhecidas (não mascaradas)
1. **Multitrack 3+ faixas (ambiência/SFX)** e **transições inter-shot `xfade`** existem no `PlanFfmpegRenderer`, mas ainda não têm rotas HTTP/schema no Studio (`DEFERRED` na camada HTTP).
2. **Qualidade semântica/estética** permanece `not_verified` sob orçamento `$0.00`; o status deste artefato é **`AWAITING_HUMAN_REVIEW`** até o operador assistir e avaliar o MP4.
3. **`versions.piper`** no `manifest.json` capturou a linha de uso do binário (`piper --version` não é suportado pelo binário empacotado, que responde com usage); o modelo usado foi explicitamente `/opt/voices/pt_BR-faber-medium.onnx`.
4. **Sobreposição do PiP par sobre o selo superior esquerdo** na cena 1, observada na inspeção visual acima.

---

## 7. Plano de Rollback

Caso seja necessário reverter integralmente as mudanças de `REC-04.01` (working tree atual não comitado sobre `develop@4fa225b`):

```bash
git checkout -- \
  renderer/app/studio/application/render.py \
  tests/conftest.py \
  tests/test_int_06_pilot.py

rm -rf \
  tests/test_rec_04_vertical_slice.py \
  scripts/run-rec04-slice.sh \
  docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04 \
  storage/output/runs/rec04_slice_20261126_213537_4fa225b
```
- Impacto em banco de dados: **zero** (nenhuma migração nova; `49/49` preservadas).
- Impacto em compatibilidade de hashes de render: **zero** para vídeos sem `scene_assets(role='overlay')` (ramo `else` em `StartRender.execute` preserva o payload JSON byte a byte).
