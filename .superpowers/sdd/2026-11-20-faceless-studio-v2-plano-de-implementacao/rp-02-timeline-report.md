# RP-02 — Timeline e sincronização (fatia 3)

**Fatia:** 3 (RP-02) da fundação **Render Plan** — RP-010 a RP-014.
**Branch:** `faceless-v2-impl` · **Worktree:** `…/39a258/faceless-v2-implementation`.
**Base ao iniciar:** `c466d4a` (relatório RP-01). Concorrência observada enquanto eu
trabalhava: `1daa6af` (mockup produto) e `7a94ce9` (status de aprovação) entraram na
branch por outros agentes; a fatia **D2** segue com `application/production.py`,
`application/ports.py`, `application/use_cases.py`, `composition.py`, `api/routes.py`,
`adapters/postgres/production_repo.py` e `tests/test_production_*.py` modificados/novos
— **não tocados**. Commits por caminho exato; sem push/merge.

## Escopo entregue

Timebase racional e sincronização da timeline, no **contrato** (`domain/`), puro e sem
I/O. Não há builder, persistência, API, painel nem FFmpeg (fatias 4–6). A fatia B
(`VisualBeat`/`beat_plan`) fica intacta; a ponte segundos↔ticks é nova e testada.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `eadb938` | RP-010 — ponte exata segundos→ticks sem deriva | `renderer/app/studio/domain/ticks.py` (+125), `tests/test_ticks.py` (+181) |
| `5e1e0ed` | RP-010..RP-014 — timebase racional, tracks, intervalos e sincronização | `renderer/app/studio/domain/render_plan.py` (+305/−…), `contracts/v1/renderplan.schema.json` (regenerado, +163/−30), `tests/test_render_plan.py` (ajustado), `tests/test_render_plan_timeline.py` (+404) |

`git diff --stat contracts/` mostra **somente** `contracts/v1/renderplan.schema.json`
(163 inserções, 30 remoções). `docs/10-arquitetura.md` não mudou (a tabela de entidades
continua com a mesma linha `RenderPlan`). Nenhum outro schema foi afetado.

## O que foi entregue

### RP-010 — timebase racional e ticks inteiros

- Novo modelo `Timebase` (`ticks_per_second` **obrigatório** e explícito, `fps_num`,
  `fps_den` com default 25/1). Propriedades `fps` (float, exibição) e
  `ticks_per_frame` (inteiro).
- **Invariante central:** reduzido, `fps_num` precisa dividir `ticks_per_second`
  (`gcd(fps_num, fps_den)`), senão uma fronteira de quadro cai entre dois ticks e a
  duração deixa de ser reproduzível. `Timebase` é rejeitada com erro claro. Ex.:
  `30000/1001` com `ticks_per_second=30000` → `ticks_per_frame=1001`; `30 fps` com
  `25 ticks/s` → rejeitado.
- Módulo novo `domain/ticks.py`: `seconds_to_ticks` converte o **valor binário exato**
  do float (`Fraction(float)`) e arredonda ao inteiro mais próximo (empate ao par),
  sem multiplicação em ponto flutuante intermediária; `ticks_to_seconds` só para
  exibição; `tick_windows` converte janelas contíguas, rejeita span < meio tick
  (**nunca** emite janela de span 0) e confere a cobertura contra `duration_s`.
- `Output` **perde** o `fps` inteiro (a taxa passou para `Timeline.timebase`).

### RP-011 — cenas, shots e tracks

- Novo modelo `Track` (`track_id`, `kind` ∈ `visual|narration|subtitle`).
  `Timeline.tracks` exige ao menos uma faixa; `track_id` únicos.
- Shot referencia faixa **declarada** e de tipo `visual` (shot em faixa de narração é
  rejeitado). `Scene` continua com `shots` (mín. 1) e ganha validação de encaixe e
  ids únicos (RP-006 preservado).

### RP-012 — sobreposição, contiguidade e lacunas por track

- Shots da **mesma** faixa não se sobrepõem (ordenação por `start_tick`).
- As **cenas** tilegam a timeline: contíguas a partir de 0, sem lacuna nem
  sobreposição.
- Cada cena é **coberta ponta a ponta** pelo conjunto de shots visuais: camadas em
  faixas diferentes podem se sobrepor (é o sentido de tracks), mas nenhum tick fica
  descoberto. Lacuna real ("zero lacunas não intencionais") é rejeitada.

### RP-013 — narração e legendas na timeline

- Novos modelos `NarrationCue` (`scene_id`, `track_id`, `source_ref`, intervalo) e
  `SubtitleCue` (`scene_id`, `track_id`, `text`, intervalo), em `Timeline.narration`
  e `Timeline.subtitles`. Cada cue ancora mídia/texto a uma **cena** e a um intervalo
  em ticks, sobre a faixa do seu tipo (narração↔narration, legenda↔subtitle).
- `source_ref` da narração resolve no manifesto ∪ áudio gerado (validado no
  `RenderPlan`).

### RP-014 — duração, lacunas e alinhamento

- **Duração:** teto por formato de saída (`MAX_SECONDS`) e **piso** (`MIN_SECONDS`,
  hoje só no QA do legado).
- **Lacunas:** cenas e shots visuais sem buraco; narração/legenda podem ter silêncio
  (lacuna intencional).
- **Alinhamento por tipo de mídia** (`alignment_tolerance_ticks`): visual = 0 tick
  (exato — a timebase garante quadro = tick); narração = **1 quadro**
  (`ticks_per_frame`), porque a fala é arredondada a quadros em `scene_length`;
  legenda = `SUBTITLE_ALIGNMENT_S = 0.5 s`. Cue fora da cena além da tolerância é
  rejeitada; e cada legenda tem de estar dentro da janela de narração da sua cena
  dentro da tolerância.

## Decisões de timebase (explícitas)

1. **Ticks no plano, segundos na autoria** (R1): `VisualBeat`/`beat_plan` continuam em
   float; a ponte é `domain/ticks.py`.
2. **Timebase agrupada em `Timeline.timebase`** (e não `fps` no `Output` + `ticks` na
   `Timeline`, como no JSON ilustrativo do writing-block §5). Motivo: uma única fonte
   para o tempo, e a `Timeline` valida o próprio alinhamento sem depender do `Output`.
3. **25 fps por default** (`FPS`), decisão §5.2 do design — mantida; a taxa é
   parametrizável e racional.
4. **Contagem por `ticks_per_second` explícito**, não por “fps inteiro”.
5. **Empate de arredondamento ao par** (semântica de `round`), documentado; o valor
   binário exato do float é usado para evitar erro de multiplicação.

## Ponte com a fatia B — por que não reintroduz deriva

`beat_plan` acumula sequencialmente e **fecha a última janela exatamente em
`scene.duration_s`** (ou rejeita o não representável em float). A conversão converte
cada fronteira float **independentemente** com o valor binário exato — e como as
janelas contíguas do `beat_plan` **compartilham a fronteira float**, elas viram o
**mesmo** tick: a contiguidade e a cobertura em ticks são preservadas. Provado por:

- `test_round_trip_is_identity_for_a_range_of_rates` e
  `test_round_trip_fuzz_is_identity` (5.000 casos, taxas 1..30000) — idempotência.
- `test_beat_plan_windows_convert_without_drift` — janelas da fatia B → ticks exatos.
- `test_beat_plan_conversion_keeps_contiguity_and_coverage_under_fuzz` — 1.500 planos
  de cena com duração alinhada a quadro; contiguidade, cobertura e round-trip bit-exatos.
- `test_tick_windows_reject_a_span_below_half_a_tick` — um beat > 0 s que arredonda
  para 0 tick é **rejeitado**, espelhando a política da fatia B.

## Evidências (comandos reais)

Python 3.12 em `faceless-v2-hygiene-test-local:latest`, `--network none`, workspace
`:ro`, `-p no:cacheprovider`.

- **RED:** `… pytest -q tests/test_ticks.py tests/test_render_plan_timeline.py` →
  `ModuleNotFoundError: app.studio.domain.ticks` e
  `ImportError: cannot import name 'NarrationCue' from app.studio.domain.render_plan`.
- **GREEN (área):**
  `… tests/test_architecture.py tests/test_contracts_snapshot.py tests/test_render_plan.py tests/test_render_plan_timeline.py tests/test_beat_plan.py tests/test_visual_beat.py tests/test_ticks.py`
  → **239 passed**. Domínio segue sem imports proibidos (`test_architecture`).
- **Contagens novas:** `tests/test_ticks.py` **36**, `tests/test_render_plan_timeline.py`
  **35**, `tests/test_render_plan.py` **23** (era 23; ajustadas ao modelo estendido).
- **Gerador sem drift:** `… scripts/export_contracts.py --check` → `exit=0`.
- **`git diff --stat contracts/`** → só `contracts/v1/renderplan.schema.json`.
- **Suíte completa (com o `.git` externo montado):**
  `… -v /Users/rodrigomendes/youtube-faceless-starter/.git:…:ro … -m pytest -q` →
  **1324 passed, 418 skipped, 1 warning**.
- **Suíte completa (sem o gitdir):** **2 failed, 1323 passed, 419 skipped** — as
  **mesmas 2 falhas ambientais** já qualificadas no RP-01
  (`test_real_starter_archive_is_safe_and_keeps_scripts_executable`,
  `test_extracted_starter_runs_contract_snapshot_and_backup_import`): `secret_hygiene.py`
  usa `git ls-files` e o `.git` do worktree é um *arquivo* (gitfile) ausente no
  container. Com o gitdir montado, passam.

Nota de empacotamento: enquanto `domain/ticks.py` estava **untracked**, o
`package-starter.sh` (que usa `git ls-files`) o omitia do arquivo e o teste
`test_extracted_starter_runs_contract_snapshot_and_backup_import` falhava. Após o
commit, a suíte completa passa — mesmo fenômeno já documentado no RP-01 para o schema.

## Onde o código/contrato real contradisse o design

1. **RP-012 não estava “pronto” no nível do plano.** O design §6 diz “Sobreposição e
   intervalos (RP-12) … **pronto** — é o núcleo de RP-12 já fechado (fatia B)”. O que
   a fatia B fechou foi a distribuição **contígua de janelas numa faixa única**
   (`plan_beat_windows`). As regras pedidas em RP-012 são **por track**, com múltiplas
   faixas (camadas) e cobertura por cena — isso **não** existia e foi implementado aqui.
2. **Timebase no `Output` vs. `Timeline`.** O JSON ilustrativo do writing-block §5 põe
   `fps_num`/`fps_den` no `output` e `ticks_per_second` na `timeline`. Agrupei ambos em
   `Timeline.timebase` e removi o `Output.fps` (que a fatia 2 já havia marcado como
   provisório: “timebase é RP-010”). Registrar como divergência do exemplo do doc.
3. **`Scene.narration_refs`/`subtitle_refs` foram substituídos por cues.** O writing-block
   §4 lista esses campos na `Scene` e a fatia 2 os implementou (resolvendo refs). RP-013
   pede associar narração/legenda **à timeline**; troquei-os por `NarrationCue`/
   `SubtitleCue` no nível da timeline, ancorados por `scene_id` e intervalo, para **não
   criar duas verdades** (anti-objetivo §2 do design). Os testes da fatia 2 correspondentes
   foram atualizados (`test_narration_cue_referencing_missing_media_is_rejected`).
4. **Limite de representabilidade em duas resoluções.** O design §7.2 só previa o limite
   em float (`ulp`): “a conversão não pode reintroduzir a deriva”. Na prática há um
   **segundo** limite — o de **granularidade do tick**: um span > 0 s pode arredondar
   para 0 tick em uma timebase grossa. A ponte rejeita isso com erro claro, e a tolerância
   de narração (**1 quadro**) nasce exatamente desse arredondamento de `scene_length`.
5. **“Zero lacunas não intencionais” precisa de um predicado.** O contrato não conhece
   intenção; codifiquei como: **visual** tem de cobrir cada cena ponta a ponta, mas
   narração/legenda **podem** ter silêncio. É uma escolha de política, não do doc.
6. **Piso de duração.** O design/writing-block só falam do teto por formato
   (`MAX_SECONDS`); o QA do legado também aplica `MIN_SECONDS = 2 s`. Trago esse piso
   para RP-014.
7. **ADR-001 ficou desatualizado.** A seção “Consequências” de
   `docs/adr/ADR-001-render-plan.md` ainda afirma que “a régua de sobreposição por track
   (RP-012/RP-014) e a sincronização por tipo de mídia (RP-013) **não fazem parte deste
   contrato**”. A fatia 3 as implementa. **Não toquei no ADR** por respeitar a lista de
   arquivos autorizados; fica como correção de documentação sugerida.

## Limitações desta entrega

- Sem **produtor** de plano, persistência ou execução: nada foi plugado no `RunRender`
  (R2/§11 é das fatias 4–6). Nenhum outro módulo importa `render_plan` hoje.
- Cues têm `scene_id` único: narração/legenda que atravesse várias cenas não é
  representável (a cena é a unidade de TTS/`make_cues`). Fica para quando o builder
  (RP-015/RP-025) precisar.
- A **calibração** da legenda por TTS (alinhamento forçado por modelo) continua fora:
  o contrato representa e valida a sincronização, mas não a produz (decisão §7.5).
- Tolerâncias são constantes de política (`SUBTITLE_ALIGNMENT_S=0.5`, narração=1 quadro),
  não campos do plano; um ajuste fino por canal seria de outra fatia.
- O contrato não verifica licença/proveniência/disponibilidade nem codec/resolução de
  asset (RP-020/RP-022).
- `Track.kind` não inclui `music`: a trilha continua em `GeneratedAudioSource` (global),
  sem cue por faixa.

## Arquivos desta fatia

- `renderer/app/studio/domain/ticks.py` (novo)
- `renderer/app/studio/domain/render_plan.py` (editado)
- `contracts/v1/renderplan.schema.json` (regenerado)
- `tests/test_ticks.py`, `tests/test_render_plan_timeline.py` (novos)
- `tests/test_render_plan.py` (ajustado)
