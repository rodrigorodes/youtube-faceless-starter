# RP-00 — Baseline e compatibilidade do pipeline de render

**Fatia:** RP-00 (Baseline e compatibilidade) da fundação **Render Plan**.
**Fonte:** `docs/backlogs/writing-block.md` §6 — RP-00 (RP-001, RP-002, RP-004); design em
`docs/superpowers/specs/2026-11-20-render-plan-foundation-design.md` (§4, §6, §11).
**Data:** 2026-11-20 · **Branch:** `faceless-v2-impl` · **Worktree:** `…/39a258/faceless-v2-implementation`.
**Escopo desta entrega:** investigação + documento. Sem alteração de código de produto, sem FFmpeg,
sem Docker, sem vídeos de referência (RP-003 fica para depois).
**Método:** leitura direta do código em `renderer/app/studio/`; cada elo citado com `arquivo:linha`.
Fatos (`✓`) e hipóteses (`?`) estão separados.

---

## 1. RP-001 — Fluxo real `Storyboard → Assets → Render` (elo por elo)

Visão de uma linha:

```
GenerateScript ──(drafts)──▶ salva cenas (SEM duração) ──▶ PrepareStoryboard
      │                                                        │
      └─▶ ProduceAssets(image por cena; cache por conteúdo) ────┘
                   │
                   ▼
RunRender: voice.speak por cena ▶ scene_length ▶ RenderSpec(listas paralelas) ▶ FfmpegRenderer
                   │                                              │
                   ▼                                              ▼
          analyze(mp4, narration) ▶ evaluate_qa ▶ publish(mp4,srt) ▶ Asset(video) ▶ complete
```

### 1.1 Onde as cenas nascem (storyboard)

| Elo | Caminho exato | Observação |
|---|---|---|
| Nº de cenas por roteiro | `renderer/app/studio/application/editorial.py:21` | `MIN_SCENES, MAX_SCENES = 2, 20` |
| O modelo devolve `scenes[]` em JSON | `application/editorial.py:132-147` (`_SCHEMA`, `build_prompt`) | narração 5–400, `image_prompt` 10–500 |
| Parse para `SceneDraft` | `application/editorial.py:150-179` (`parse_drafts`) | exige `claim_ids`; valida limites |
| DTO de rascunho | `application/ports.py:90-97` (`SceneDraft`) | `narration/caption/label/image_prompt/claim_ids` |
| Gravação das cenas | `application/editorial.py:231` → `adapters/postgres/editorial_repo.py:42-60` | `save_and_advance` faz `DELETE` (55) + `INSERT` (56-59) na mesma transação que muda o estado |
| **Duração NÃO gravada** ✓ | `adapters/postgres/editorial_repo.py:57-59` | `INSERT` **não inclui** `duration_s`; a coluna fica `NULL` |
| Coluna existe no schema | `adapters/postgres/migrations/0001_init.sql:52-63` | `duration_s real CHECK (duration_s >= 0)` — **nullable**, linha 61 |
| Entidade `Scene` (banco) | `domain/contracts.py:109-119` | `duration_s: float \| None = None` (linha 119) |
| `PrepareStoryboard` (só transição) | `application/media.py:21-32` | `FACT_CHECKED → STORYBOARDED`; não cria cena |
| Leitura das cenas | `application/ports.py:108-113` (`ScriptRepository.scenes`) → `editorial_repo.py:62-65` | `ORDER BY idx` |

**Conclusão do elo:** as cenas nascem no `PostgresScriptRepository.save_and_advance` a partir de
`SceneDraft`s do LLM. Confirmado o que o design (§11/R1) afirma: **`studio.scenes.duration_s` nunca é
escrito** — só existe conteúdo de narração + prompt. A `Scene` do banco é a origem editorial, não a
cena do plano.

### 1.2 Onde os assets são produzidos

| Elo | Caminho exato | Observação |
|---|---|---|
| Caso de uso | `application/media.py:41-110` (`ProduceAssets`) | retomável; uma execução por vídeo (lock) |
| Loop por cena | `application/media.py:57-79` (`_run`) | pula cena já vinculada (65) |
| Chave de cache por conteúdo **de entrada** | `application/media.py:68` → `domain/ids.py:26-30` | `asset_cache_key(kind, provider, model, prompt, params)` = `sha256` do JSON canônico dos **parâmetros** |
| Cache hit | `application/media.py:69-74` (`assets.find`) → `adapters/postgres/media_repo.py:23-27` | `assets.cache_key` é `UNIQUE` |
| Geração | `application/media.py:81-110` (`_generate`) | licença obrigatória (102-105), mime raster (104) |
| Gravação do arquivo | `application/media.py:106` → `adapters/storage.py:47-74` (`FileAssetStore.put`) | PNG normalizado no aspecto; escrita atômica |
| Criação da entidade `Asset` | `application/media.py:107-110` | `kind=image`, `cache_key`, `path`, `provider`, `model`, `license` |
| Vínculo cena↔asset | `application/media.py:75` → `adapters/postgres/media_repo.py:44-49` (`link_scene`) | só se o vídeo ainda está `STORYBOARDED` |
| Transição | `application/media.py:77` | `STORYBOARDED → ASSETS_READY` |
| Adaptadores de imagem | `adapters/image_opencode.py:13-83`, `adapters/image_stock.py:27-70` (Pexels), `adapters/image_placeholder.py`, `adapters/image_veo.py` | provider define `license`/`attribution`/`source_url` |
| Entidade `Asset` | `domain/contracts.py:122-132` | `cache_key`, `path`, `provider`, `model`, `license`, `attribution`, `source_url`, `cost_usd` |
| **Voz NÃO é asset nesta fase** ✓ | `application/render.py:120-137` | `voice.speak` acontece **no render**, por cena |
| Adaptador de voz | `adapters/voice_piper.py:11-28` | envolve `rich.synthesize_speech`; falha se a voz sair em silêncio (26-27) |

**Conclusão do elo:** só **imagens** viram `Asset` na fase de assets. Voz é sintetizada dentro do
render; música é sintetizada em `rich.py` (ver §1.4). Não há asset de áudio persistido.

### 1.3 Onde o render consome

| Elo | Caminho exato | Observação |
|---|---|---|
| Enfileirar | `application/render.py:46-67` (`StartRender`) | exige `ASSETS_READY`/`RENDERED` (53); `input_hash` = `sha256` de `[format, [[narration,label,cache_key]…]]` (56-57) |
| Executar | `application/render.py:78-110` (`RunRender.execute`) | nunca levanta; falha vira job `FAILED` |
| Seleção cenas+assets | `application/render.py:33-43` (`_scenes_with_assets`) | cena sem asset → `StateConflict` (41) |
| Voz + duração por cena | `application/render.py:120-138` | `speech_wavs` + `scene_length(speech)` |
| Limite de duração | `application/render.py:139-141` | `sum(lengths) > MAX_SECONDS[fmt]` → `RenderRefused` |
| Legendas (cues) | `application/render.py:142-146` → `domain/render.py:85-97` (`make_cues`) | tempo **proporcional ao texto** dentro da fala |
| **Disclosure derivado do provider** ✓ | `application/render.py:147,150` | `stock` ⇒ `"Imagens ilustrativas"`, senão `"Ilustração gerada por IA"` |
| Monta o `RenderSpec` | `application/render.py:148-150` | **listas paralelas**: `scenes/images/speech_wavs/scene_seconds/cues` |
| Invoca o renderer | `application/render.py:151` | `renderer.render(spec, work/"final.mp4")` |
| QA | `application/render.py:152-153` | `analyzer.analyze(mp4, narration=work/NARRATION_FILE)` + `evaluate_qa` |
| Posse/publicação | `application/render.py:154-162` | `alive` → `publish(mp4, srt)` → `Asset(video)` → `complete` → `prune` |
| Renderer FFmpeg | `adapters/render_ffmpeg.py:102-137` (`FfmpegRenderer.render`) | narração (113), valida comprimentos (114-115), música (118), cena a cena (124-135) |
| Composição de cena | `adapters/render_ffmpeg.py:74-99` (`_scene`) | Ken Burns + selo + cadência de legenda por `enable` + fades |
| Montagem final | `adapters/render_ffmpeg.py:139-152` (`_assemble`) | concat + ducking + `loudnorm I=-16:TP=-1.5:LRA=11` |
| Analisador | `adapters/qa_ffmpeg.py:40-64` (`FfmpegQa.analyze`) | `ffprobe` + `ebur128`/`silencedetect`/`blackdetect` |
| Regra de QA | `domain/render.py:116-147` (`evaluate_qa`) | duração, resolução, LUFS, silêncio/preto; falha fechada |
| Persistência do job/asset | `adapters/postgres/render_repo.py:19-117`; `adapters/storage.py:77-160` (`FileRenderStorage`) | `final-<job>.mp4/.srt`, publicação atômica por job |

**Conclusão do elo:** o render consome `RenderSpec` (listas paralelas, POSIX `Path`) e devolve um MP4 +
`.srt`. A duração que alimenta a timeline nasce **depois do TTS** (`application/render.py:138`), o que
confirma a decisão de R1 ("o plano é construído no render, depois da síntese de voz").

### 1.4 Três coisas derivadas em código (pontos exatos, confirmados no design)

1. **Ken Burns escolhido por `index % 4`** ✓
   - `adapters/render_ffmpeg.py:74,78-86` (`mode = index % 4`; modos 0/1 = zoom in/out centrado,
     modos 2/3 = pan). O `index` é a **posição da cena na lista** — não há campo de movimento.
   - Duplicata legada para o `/videos`: `renderer/app/rich.py:194,197-205` (`render_scene`, mesmo
     `mode = index % 4`). Alterar um sem o outro quebra paridade entre os dois caminhos.

2. **Disclosure derivado do provider** ✓
   - `application/render.py:147,150`: `stock = any(a.provider == "stock" …)`. O default do `RenderSpec`
     é `"Ilustração gerada por IA"` (`application/ports.py:45`).

3. **Música sintetizada em processo** ✓
   - `renderer/app/rich.py:70-125` (`synth_music`), RNG semeado em `rich.py:75`
     (`np.random.default_rng(7)`), chamada em `adapters/render_ffmpeg.py:118`.
   - `music=False` **não remove a trilha**: grava um WAV silencioso do mesmo comprimento para manter o
     mesmo grafo de mixagem (`adapters/render_ffmpeg.py:119-122`). Ou seja, "trilha original sintetizada"
     é determinística pelos parâmetros, mas ainda materializada em arquivo dentro de `work/`; não é
     `Asset` persistido nem tem hash próprio.

---

## 2. RP-002 — Contratos e DTOs reutilizáveis (o que serve, o que adapta, o que é legado)

Legenda: **✔ serve como está** · **◐ precisa de adaptação** · **✖ legado a substituir**.

### 2.1 `domain/contracts.py`

| Entidade | Veredito | Nota |
|---|---|---|
| `_Model` / `SCHEMA_VERSION=1` / `load_versioned` (`58-67`, `221-225`) | ✔ | padrão de versionamento (`schema_version` int + `extra="forbid"`) a **reusar** no `RenderPlan` |
| `Video`, `VideoFormat`, `VideoStatus` (`30-32`, `86-98`) | ✔ | base da projeção de formato/estado |
| `Scene` (`109-119`) | ◐ | é a cena **editorial** (banco). Colide de nome com a `Scene` do plano; `duration_s` existe mas é `NULL`. Vira **entrada** do builder, não a cena do plano |
| `Asset` (`122-132`) | ◐ | base do asset físico. Falta `content_sha256` (hash do **conteúdo**), codec/resolução/disponibilidade (RP-22). O `cache_key` atual é hash de **entrada**, não de conteúdo (§4.2) |
| `RenderJob` (`135-142`) | ✔ | registro de execução; `input_hash` já é o fingerprint do job |
| `UsageEntry` (`168-177`) | ✔ | semântica de custo da fatia A preservada |
| `QaReport` (`70-73`) | ✔ | saída do QA; reusar no gate |
| `SourceSnapshot.content_sha256` (`184`) | ✔ | **único** hash de conteúdo existente — precedente do hash do manifesto (RP-20) |
| `Publication`, `Approval`, `Script`, `Claim`, `FactCheckReport` | ✔ | fora do caminho do plano; sem impacto |

### 2.2 `application/ports.py`

| Porta/DTO | Veredito | Nota |
|---|---|---|
| `RenderSpec` (`36-46`) | ✖ | **é o contrato implícito a substituir** pelo `RenderPlan`; o design (R2) o mantém como entrada do renderer **legado** |
| `Renderer` (`79-81`) | ✔ | vira a **costura da flag**: o caminho novo é uma **segunda implementação** de `Renderer` (R2) |
| `AssetRepository` (`128-134`) | ◐ | reusável; RP-04 pede uma porta `AssetResolver` por cima (hash de conteúdo, disponibilidade, codec) |
| `AssetStore` (`137-139`) | ◐ | `put` valida/grava **imagem**; estender para vídeo/gráfico/texto (RP-21) |
| `QaAnalyzer` (`147-151`) | ✔ | reusável; RP-30 quer `QualityEvaluator` como porta — da para envolver/renomear |
| `RenderStorage` (`173-183`) | ✔ | publicação atômica por job já existe (`storage.py:94-110`); serve quase como está |
| `Voice` (`74-76`) | ✔ | reusável como está |
| `ScriptRepository.scenes` (`112`) | ✔ | fonte das cenas para o builder |
| `ImageModel`, `TextModel`, `SourceFetcher`, etc. | ✔ | fora do plano |
| `ProductionRunRepository` (`318-379`) | ✔ | base da regeneração seletiva (RP-27..29) |

### 2.3 `domain/render.py`

| Item | Veredito | Nota |
|---|---|---|
| `FPS=25`, `scene_length`, `LEAD/TAIL`, `SIZE`, `MAX_SECONDS` (`8-22`) | ◐ | a matemática serve; o plano quer **ticks inteiros** + `ticks_per_second` (RP-10). Manter 25 fps por default (design §5.2) |
| `Cue`, `make_cues`, `to_srt`, `to_srt_time` (`78-109`) | ◐ | legendas existem, mas em **segundos float**; a fundação as associa à timeline (RP-13) |
| `evaluate_qa` (`116-147`) | ✔ | **barra de não-regressão** de R6; a tolerância ±1 s, LUFS e razões de silêncio/preto já são o aceite |
| `NARRATION_FILE` (`13`) | ✔ | contrato renderer↔QA (a voz isolada prova que há fala) |

### 2.4 `domain/visual_beat.py` + `domain/beat_plan.py`

| Item | Veredito | Nota |
|---|---|---|
| `VisualBeat` (`visual_beat.py:35-65`) | ◐ | unidade **editorial** em segundos (1 beat = 1 mídia). Falta `track_id`/conceito de **shot** (RP-11); o `effect` de movimento está explicitamente **fora** (docstring 10-12) e é o ponto onde o `index % 4` deveria virar campo |
| `plan_beat_windows` (`beat_plan.py:87-143`) | ✔ | **núcleo de RP-12 já fechado**: janelas contíguas, sem sobreposição, cobertura validada, sem deriva de arredondamento (fuzz em `tests/test_beat_plan.py`) |
| `plan_scene_beats` / `SceneBeatPlan` (`beat_plan.py:34-84`) | ✔ | reposiciona beats na cena; reusar como base da timeline do plano (ponte segundos↔ticks) |
| **Produtor/persistência** | ✖ (ausente) | ✓ confirmado: **nenhum consumidor de produto** usa `VisualBeat`/`plan_scene_beats`; só `domain/` + testes (`tests/test_visual_beat.py`, `tests/test_beat_plan.py`). O produtor de beats é fatia posterior (R1) |

### 2.5 `domain/production_run.py`

| Item | Veredito | Nota |
|---|---|---|
| `ProductionStage` (`35-46`) | ✔ | já contém `RENDER` e `QA` |
| `STANDARD_DAG` (`321-331`) | ✔ | `ASSETS → RENDER → QA → APPROVAL`; base do grafo de dependências (RP-28) |
| `StageDag`, `Checkpoint`, `StageExecution`, CAS/lease/fencing/outbox (`244-444`) | ✔ | reusar como está; a regeneração fina **por cena/shot** é extensão, não reescrita |
| `canonical_idempotency_key` (`150-171`) | ✔ | forma canônica já fechada |

### 2.6 `contracts/v1/*.schema.json`

- 13 entidades geradas (`project, video, script, scene, asset, renderjob, publication, usageentry,
  qareport, sourcesnapshot, claim, factcheckreport, approval`), a partir de
  `scripts/export_contracts.py:15` (lista `MODELS`).
- **Snapshot versionado**: `tests/test_contracts_snapshot.py:10-19` compara o JSON commitado com o
  gerado; editar JSON à mão quebra o teste. **Veredito:** ✔ reusar o mecanismo; o `renderplan.schema.json`
  entra na lista `MODELS` (RP-07) e o snapshot é regenerado — **nunca** escrito à mão.
- ⚠️ Colisão de nomes: `scene.schema.json` é a cena do **banco**. A cena do **plano** precisa de nome
  distinto (schema próprio dentro do plano), senão há "duas verdades" (anti-objetivo §2 do design).

---

## 3. RP-004 (PROPOSTA) — Testes de regressão do renderer ATUAL

> Proposta apenas. **Não implementar** nesta fatia (RP-003/RP-004 ficam para depois; sem FFmpeg/Docker
> agora). Objetivo: travar o comportamento observável do renderer legado **antes** de o compilador novo
> entrar, para a comparação do §11.

### 3.1 O que já existe hoje

| Arquivo | Natureza | Cobre |
|---|---|---|
| `tests/test_render_domain.py` | puro | `scene_length` (quadros inteiros), `split_chunks`, `make_cues` (proporcional, não sobrepõe), `to_srt`/`to_srt_time`, `evaluate_qa` (todas as reprovações), limites por formato |
| `tests/test_render_adapters.py` | **FFmpeg** (`needs_ffmpeg`) | MP4 com áudio/vídeo + tamanho por formato + duração `abs=0.35`; legenda queimada; mensagem de falha do ffmpeg; QA normal/mudo/preto/sem-áudio; E2E passa QA; narração muda reprova; cues adjacentes não compartilham quadro; `FileRenderStorage` (publicar atômico/prune/resolve/cleanup) |
| `tests/test_render.py` | fakes (caso de uso) | start/enqueue idempotente, guardas de estado, spec entregue ao renderer, disclosure `stock`, vídeo longo recusa antes de render, falha técnica, perda de posse, `_scenes_with_assets` |
| `tests/test_render_repo.py`, `tests/test_render_api.py` | repo/API | persistência e rotas |
| `tests/test_rich.py` | puro | `scene_length`, `build_narration_track` (alinhado ao vídeo), `synth_music` (duração/amplitude/não-silencioso), `make_overlay`, `cover_image` |
| `tests/test_beat_plan.py` | puro | janelas de beat / cobertura (fuzz) |
| `tests/test_visual_beat.py` | puro | contrato do beat |

### 3.2 Comportamentos a travar por teste (com nomes sugeridos)

**Duração**
- `test_total_duration_equals_sum_of_whole_frame_scene_lengths` — `sum(scene_seconds) == Σ ceil((LEAD+speech+TAIL)·FPS)/FPS` (reforça o que o E2E só checa com `abs=0.35`).
- `test_qa_expected_duration_is_the_rendered_duration_plus_tolerance` — `duration_s` dentro de `EXPECTED_TOLERANCE_S=1.0` do `expected_s` (`domain/render.py:142`).
- `test_video_above_format_limit_is_refused_before_ffmpeg` — já existe parcialmente (`test_render.py::test_too_long_video_fails_before_rendering`); manter e ampliar para `long`.

**Resolução**
- `test_output_resolution_is_1080x1920_short_and_1920x1080_long` — já coberto; travar também no `.srt`/asset.

**LUFS (lacuna real)**
- `test_integrated_lufs_lands_near_loudnorm_target_minus_16` — hoje **não existe**: o E2E só exige `-45 < LUFS < -9`. Travar `-16 ± 2` para o render normal é o contrato do `loudnorm` (`render_ffmpeg.py:149`).
- `test_music_false_keeps_the_mix_graph_with_a_silent_track` — travar que `music=False` **não** remove áudio, só silencia a trilha (`render_ffmpeg.py:119-122`), mantendo `integrated_lufs` alto pela voz.

**Silêncio / preto**
- `test_normal_render_has_low_black_ratio_and_passes_silence_gate` — `black_ratio < MAX_BLACK_RATIO`, `silence_ratio < MAX_SILENCE_RATIO`.
- `test_narration_is_measured_from_the_isolated_track` — já existe (`test_silent_narration_fails_qa_even_if_the_mix_has_music`); manter.

**Legendas `.srt`**
- `test_published_srt_equals_to_srt_of_the_render_cues` — o teste de caso de uso só checa `"-->" in srt`; travar **igualdade** com `to_srt(cues)` (tempos absolutos).
- `test_burned_caption_matches_the_cue_window` — já existe (`test_subtitles_are_burned_into_the_frames`).

**Fades (lacuna real)**
- `test_scene_graph_has_fade_in_at_zero_and_fade_out_at_scene_end` — extrair um construtor puro do grafo e travar `fade=t=in:st=0:d=0.25` e `fade=t=out:st=seconds-0.25` (`render_ffmpeg.py:93`).
- `test_first_and_last_frames_are_darkened_by_the_fade` — smoke de frame (opcional; custo alto, roda sob `needs_ffmpeg`).

**Ken Burns**
- `test_ken_burns_mode_cycles_by_index_modulo_four` — extrair `_ken_burns_mode(index)` puro e travar os 4 modos (`render_ffmpeg.py:78-86`); idealmente compartilhar com `rich.py:197-205`.
- `test_ken_burns_zoom_amount_is_stable_per_mode` — travar os fatores `1+0.10`, `1.10-0.10`, `1.12` (paridade com o `/videos`).

**Disclosure / selo**
- `test_stock_provider_switches_disclosure_to_imagens_ilustrativas` — já existe (`test_render.py`).
- `test_static_overlay_places_disclosure_and_label` — puro sobre `static_overlay` (Pillow, sem FFmpeg).

**Narração**
- `test_build_narration_track_pads_lead_and_tail_to_frame_lengths` — reforçar `tests/test_rich.py` com os mesmos `LEAD/TAIL/FPS` de `domain/render.py`.
- `test_renderer_refuses_when_narration_track_does_not_match_planned_lengths` — travar o `RuntimeError` de `render_ffmpeg.py:114-115`.

### 3.3 Regra de execução da suíte

- Testes puros (domínio, `rich`, overlay) **sem FFmpeg**; testes de mídia sob `@needs_ffmpeg`
  (`tests/test_render_adapters.py:22-23`). A fundação exige "contratos testáveis sem FFmpeg"; por isso
  os itens de fades/Ken Burns devem virar **funções puras** (o compilador de RP-23), testadas sem
  processo — os smokes de frame são complementares, não a fonte da verdade.

---

## 4. Descobertas (o que o mapeamento mudou/refinou em relação ao design)

### D1 (importante) — `cache_key` de asset é hash de **entrada**, não de **conteúdo**; o do vídeo inclui o `job.id`
- `domain/ids.py:26-30`: `asset_cache_key` = `sha256` de `{kind, provider, model, prompt, params}`.
  Mesmo **prompt** ⇒ mesma chave, **independentemente** dos bytes gerados.
- Asset de imagem: `application/media.py:68` usa essa chave; `assets.add` é idempotente por ela (`media_repo.py:35-42`).
- Asset de vídeo (render): `application/render.py:157` → `sha256("video|<renderer.name>|<job.input_hash>|<job.id>")`. Como inclui `job.id`, **um re-render do mesmo conteúdo produz outra chave** — não é content-addressable.
- **Impacto no design:** o item R7 ("o hash já tem casa natural em `assets.cache_key`") é impreciso: `cache_key` identifica insumos, não conteúdo. RP-20 pede *hash do asset*; é preciso um **`content_sha256` novo** (o único precedente no domínio é `SourceSnapshot.content_sha256`, `contracts.py:184`). Sem isso, o "render hash" do mockup (§8) e o cache de RP-27..29 mediriam a coisa errada.

### D2 (importante) — a duração da cena não é persistida em lugar nenhum; nasce e morre no render
- `editorial_repo.py:57-59` insere a cena **sem** `duration_s`; a coluna é nullable (`0001_init.sql:61`).
- A duração só existe em `application/render.py:138` (`scene_length(speech)`), depois do TTS, e vive
  apenas no `RenderSpec`/`work/`.
- **Impacto:** confirma R1 e reforça que o **plano tem de ser construído no render**. Também significa
  que "regenerar cena" (RP-06) hoje **não tem** onde guardar a duração sem refazer o TTS — a tabela
  lógica do plano precisará carregar `duration` de fato (`scenes.duration_s` está ociosa).

### D3 (importante / contraria suposição) — `music=False` não remove a trilha, e a música é arquivo em `work/`
- `render_ffmpeg.py:117-122`: com `spec.music=False`, o renderer **grava um WAV silencioso** de mesmo
  comprimento e mantém o grafo de mixagem; o áudio resultante ainda tem faixa de trilha (muda).
- `rich.py:70-125` materializa `music.wav` em disco (determinística, seed 7), e `render_ffmpeg.py:118`
  a grava em `work/`.
- **Impacto:** a decisão R3 ("música sintetizada … não é arquivo, portanto não cabe em `asset_manifest`")
  está **parcialmente correta**: não é `Asset` persistido, mas **é um arquivo gerado** com parâmetros
  determinísticos. O plano precisa de uma **fonte de áudio gerada** (com `bpm`, seed, duração) e o
  compilador precisa reproduzir exatamente a equivalência "trilha silenciosa ≠ sem trilha" para a
  paridade do §11.

### Observações menores (não contradizem o design, mas restringem a fundação)
- **Dois consumidores do mesmo núcleo visual:** `render_ffmpeg.py` (estúdio) e `rich.py` (`/videos`)
  carregam a **mesma** lógica de `index % 4` e do `loudnorm -16` (`rich.py:197-225` vs
  `render_ffmpeg.py:78-98,146-152`). Qualquer paridade tem de valer para os dois, ou a fundação
  precisa declarar `/videos` explicitamente fora.
- **Nenhum consumidor real de `VisualBeat`/`plan_scene_beats`** (só `domain/` + testes): o "núcleo de
  RP-12" está pronto mas **não plugado** — é ativo latente, não pipeline.
- **A voz é o único ponto onde a duração entra** e é o único custo pago obrigatório por cena no render
  (`render.py:127-136`), com chave de conteúdo `paid_key(...)` — coerente com R5 (custo por chave).
- **`RenderSpec` já carrega o que R2 diz que o plano precisa transportar**: `format`, `music`,
  `disclosure`, `work_dir`, `cues` e a narração global (`ports.py:36-46`, `render.py:148-150`) — é a
  lista de campos que o `RenderPlan` precisa cobrir para paridade.

---

## 5. Limitações desta entrega

- RP-003 (vídeos de referência + hashes) **não** foi executado (sem FFmpeg/Docker, por ordem).
- Nada de produto foi alterado; nenhum teste foi rodado nesta fatia (a suíte da máquina está ocupada
  com Docker; a proposta de RP-004 é só texto).
- Os comportamentos de fades/Ken Burns/LUFS acima são **lacunas identificadas por leitura de código**,
  não confirmadas por execução — por isso a proposta prioriza extrair funções puras antes de medir.
- Paths citados são relativos à raiz do worktree; `docs/backlogs/writing-block.md` **não existe** neste
  worktree (existe em `/Users/rodrigomendes/youtube-faceless-starter/docs/backlogs/writing-block.md`);
  a fonte foi lida de lá.
