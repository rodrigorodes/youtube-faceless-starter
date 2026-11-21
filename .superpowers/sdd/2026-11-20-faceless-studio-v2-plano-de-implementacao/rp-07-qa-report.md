# RP-07 — QA e rollout (fatia 8) — RP-030 / RP-031 / RP-032

**Fatia:** 8 (RP-07) da fundação **Render Plan** — `QualityEvaluator` como porta + avaliador
determinístico (RP-030), E2E curto + benchmark audiovisual rotulado (RP-031) e rollout por
**kill-switch** com reescopo honesto (RP-032).
**Branch:** `feat/rp-07-qa` · **Worktree:** `…/39a258/rp-07-qa` · **Base:** `2be7104`
(RP-05 fechada). RP-06 rodou **em paralelo**, em worktree própria — nada foi escrito fora daqui.
**Restrições respeitadas:** `domain/render_plan.py`, `domain/ticks.py`,
`application/render_compiler.py` e `adapters/render_plan_ffmpeg.py` **intactos**;
`api/panel*.py`, `application/channels_page.py`, `renderer/app/main.py`,
`tests/test_providers.py` **intocados**. Commit por caminho exato; **sem push e sem merge**.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `05c8d8b` | RP-030 — porta `QualityEvaluator` + avaliador determinístico | `domain/quality.py` (novo), `application/quality.py` (novo), `adapters/quality_ffmpeg.py` (novo), `application/ports.py` (+20), `tests/test_quality.py` (novo) |
| `22d8f52` | RP-031 — E2E com mutação real + benchmark rotulado | `tests/test_render_quality_e2e.py` (novo), `application/benchmark.py` (novo), `scripts/render_benchmark.py` (novo), `tests/test_render_benchmark.py` (novo) |
| `3e6dd35` | RP-032 — kill-switch + composição do avaliador | `adapters/render_disabled.py` (novo), `composition.py` (+23/−3), `tests/test_render_rollout.py` (novo) |

Nada de `git add -A`. `composition.py` e `ports.py` foram os **únicos** arquivos existentes tocados.

## RP-030 — o que o `QualityEvaluator` avalia de fato (e o que fica declarado fora)

A porta vive em `application/ports.py` (`QualityEvaluator`), a **política** é pura
(`domain/quality.py::evaluate_quality`) e só o adaptador toca mídia
(`adapters/quality_ffmpeg.py`). O relatório de saída é o contrato versionado da F6
(`domain.qa_report.QaReport`, o "QualityReport" do design §7.5) — com severidade
`blocking`/`warning`/`info` e cobertura `verified`/`not_verified`. **Não** criei um tipo
novo: reaproveitei o contrato da F6, preservando `render_id`/`checksum` e o gate `approve`.

**Avaliado de fato (determinístico, reuso — sem duplicar régua):**

| Grupo | Check (`check_id`) | Severidade | Régua reusada |
|---|---|---|---|
| Métricas medidas | `render.media_metrics` | blocking / gap | `domain/render.evaluate_qa` + `adapters/qa_ffmpeg.FfmpegQa` (ffprobe/ebur128/silencedetect/blackdetect) |
| Duração vs. plano/formato | `render.duration` | blocking | `evaluate_qa` (mensagem → check) |
| Resolução | `render.resolution` | blocking | `evaluate_qa` |
| Presença de áudio | `render.audio_stream` | blocking | `evaluate_qa` |
| Loudness (mistura) | `render.loudness` | blocking | `evaluate_qa` |
| Narração isolada | `render.narration` | blocking | `evaluate_qa` |
| Silêncio / preto | `render.silence` / `render.black_frames` | blocking | `evaluate_qa` |
| Assets | `render.asset_resolution` | blocking | `domain/asset_resolver.verify_descriptor` (identidade, licença, disponibilidade) |
| Plano (avisório) | `render.manifest` (asset sem uso), `render.timeline` (duração a <5% do limite) | **warning** | regra pura |
| Plano (informativo) | `render.music` (trilha silenciosa por `music=False`) | **info** | regra pura |

**Cobertura verificada:** só fica `verified` quando a evidência está **completa** — todas as
métricas exigidas por `evaluate_qa` presentes **e** os descriptors de todos os assets
referenciados pelos shots. Sem métricas, sem a faixa de voz ou sem os descriptors, a
cobertura fica `not_verified` com motivo, e o gate da F6 recusa (`CoverageNotVerified`).
Fail-closed: ausência de evidência nunca vira aprovação; mensagem de falha desconhecida
mapeia para `blocking`.

**Declarado fora (sem score inventado):** a **avaliação semântica multimodal** — "a imagem
corresponde à narração?", "o enquadramento/legenda estão bons?" — exige um provedor/LLM de
visão que **não existe** nesta fatia. A constante `domain.quality.MULTIMODAL_EVALUATION =
"out_of_scope_without_provider"` declara isso, e um teste garante que nenhum check visual é
emitido. O `QualityEvaluator` determinístico **não** devolve score visual: quando o provedor
existir, ele entra como um avaliador adicional e a ausência continua virando cobertura não
verificada, nunca um número fabricado.

## RP-031 — E2E curto e offline + benchmark

**E2E** (`tests/test_render_quality_e2e.py`, 6 testes, FFmpeg): clipes curtos sintéticos.
O caminho bom renderiza pelo `PlanFfmpegRenderer` (o único), mede pelo
`FfmpegQualityEvaluator` e **aprova** pelo gate `domain.qa_report.approve`. Prova de
mutação real (clipes sintetizados com FFmpeg, 1080×1920, 1–3 s):

| Clipe | Defeito injetado | Resultado medido |
|---|---|---|
| `too-short` | 1,0 s de vídeo contra plano de ~3,8 s | cobertura `verified`; `blocking` em `render.duration`; **não aprova** (`BlockingFindings`) |
| `silent` | vídeo ok + trilha de áudio `anullsrc` (muda) | `blocking` em `render.loudness`/`render.silence`; **não aprova** |
| `black` | `color=black` + tom de áudio | `blocking` em `render.black_frames`; **não aprova** |
| `small` | 640×360 | `blocking` em `render.resolution`; **não aprova** |
| sem `narration.wav` | render bom sem faixa de voz | cobertura `not_verified`; **não aprova** (`CoverageNotVerified`) |

**Benchmark** (`scripts/render_benchmark.py`, `--scene-seconds 3.0 --runs 3`; artefato
`rp-07-benchmark.json`). Render local, clipes curtos sintéticos, imagem
`faceless-v2-hygiene-test-local:latest`:

| Métrica | Unidade | Rótulo | Valor medido | O que é |
|---|---|---|---|---|
| `render_seconds_per_video_minute` | s/min | **Real** | **24,151** | 3 amostras: vídeo 3,8 s; render 1,474 / 1,546 / 1,569 s |
| `failure_rate` | fração | **Real** | **0,000** (0/3) | QA aprovou as 3 amostras |
| `cost_per_video_minute` | USD/min | **Estimado** | — (não medido) | custo de provedor não é medido neste benchmark (render local `Free`); sem invenção |
| `cache_hit_rate` | fração | **Estimado** | — (não medido) | cache de render é **RP-06**, em outra fatia |

**Alvo ≠ medido.** O alvo do pedido §10 ("render de um vídeo de 8 minutos em 1080p") está
registrado como **alvo a medir**, não promessa (design §9) — o benchmark mede clipes de
3–4 s, não 8 min. Nenhum número foi extrapolado para 8 min.

## RP-032 — rollout (reescopo honesto)

O pedido pedia "feature flag, compatibilidade e rollback" com comparação com o **pipeline
anterior**. O legado foi **removido na RP-05** e a decisão de "manter os dois atrás de flag"
foi **revogada pelo usuário** (emenda §14 do design). Então:

- **Não** reintroduzi o caminho antigo e **não** prometo "rollback para o renderer legado" —
  ele não está no código.
- A flag `STUDIO_RENDER_PLAN_ENABLED` (default **ligada**) é **kill-switch/availability** do
  caminho novo, não dispatch dual. Desligada, `DisabledRenderer` **recusa** o render
  (`RenderPlanDisabled`, `name="ffmpeg"` inalterado) e o `RunRender` marca o job FAILED com a
  causa — a produção para sem publicar nada.
- **O rollback é o redeploy da imagem anterior.** A mensagem da exceção diz exatamente isso.
- **Compatibilidade com o pipeline anterior** = a **comparação documentada** da RP-05
  (tabela de paridade: resolução, duração ±1 s, LUFS, silêncio/preto, Ken Burns, selo,
  disclosure, legenda, ducking, `loudnorm -16`, 25 fps) **mais** o envelope de
  `evaluate_qa` que esta fatia passa a exercitar como gate. Não há A/B em runtime — o
  antigo não existe mais.

## Validações reais (comandos, com números medidos)

Imagem `faceless-v2-hygiene-test-local:latest`, `PYTHONPATH=/workspace/renderer`,
`-p no:cacheprovider`. **Postgres próprio:** container `rp7-pg` na rede `rp7-net`,
`--tmpfs /var/lib/postgresql/data`, prova de 64 hex montada com
`-v <dir>:/budget-test-proof:ro` (lida por `pg_read_file('/budget-test-proof/proof')` e
conferida localmente). As **duas** DSNs foram passadas (`STUDIO_TEST_DSN` **e**
`STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

- **Partição exigida** (`test_architecture`, `test_contracts_snapshot`,
  `test_render_plan{,_timeline,_builder,_executor}`, `test_render_compiler`, `test_render`,
  `test_render_adapters`, `test_db`, + os 4 novos) → **227 passed** em 39,35 s.
- **Novos testes:** `tests/test_quality.py` = **25** (política pura, sem FFmpeg),
  `tests/test_render_quality_e2e.py` = **6** (FFmpeg), `tests/test_render_benchmark.py` = **4**,
  `tests/test_render_rollout.py` = **3** → **38** no total.
- **Regressão de runtime:** `test_qa_report`, `test_render_api`, `test_render_repo`,
  `test_panel_production_render`, `test_publication_execution` → **160 passed**.
- **Banco descartável:** `test_budget_reservations`, `test_production_repo` → **73 passed**.
- **Gerador de contratos sem drift:** `scripts/export_contracts.py --check` → **exit 0**
  (nenhum modelo novo é exportado — o `QaReport` da F6 já **não** estava na lista de
  contratos; `contracts/` e `tests/test_contracts_snapshot.py` **intactos**).
- **Arquitetura:** `test_domain_has_no_outward_or_io_imports`,
  `test_application_only_imports_domain`, `test_render_core_has_no_media_or_provider_sdks`
  verdes — `subprocess`/PIL só em `adapters/`; a porta e a política são puras.
- **Higiene:** `python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (exit 0).
- **Contagem medida do benchmark:** 24,151 s de render por minuto de vídeo (Real),
  taxa de falhas 0,000 (Real) — ver `rp-07-benchmark.json`.

**Memória:** clipes curtos (≤3,8 s, 1080×1920), benchmark com 3 amostras, `rp7-pg`
próprio. Nenhum `ffmpeg … SIGKILL`/rc 137 observado nesta execução.

## Migração

**Nenhuma migração.** O `QualityReport` **não** é persistido nesta fatia. O runtime já
persiste o `contracts.QaReport` legado junto do render (`videos.qa_report`) e a F6 deriva o
relatório versionado dele em `RenderQaGate`; criar uma tabela paralela seria a **segunda
verdade** que o design proíbe (§2, anti-objetivo). Portanto: **sem `0033`**, sem tabela
órfã, `tests/test_db.py` intacto.

## O que ficou de fora / o que **NÃO** está ligado

- **Adoção do `QualityEvaluator` dentro do `RunRender`/`RenderQaGate`:** a instância é
  montada na raiz de composição (`Studio.quality_evaluator`) e provada E2E, mas o loop de
  render ainda persiste o `contracts.QaReport` legado. Trocar o tipo persistido muda o
  contrato do banco (migração + painel) e é a **próxima** adoção — declarada, não fingida.
  A composição é o **único** lugar que liga o adaptador (exigência de camadas).
- **Avaliação semântica multimodal:** fora, sem provedor (nada de score inventado).
- **Cache hit:** não medido — é RP-06 (regeneração seletiva), que rodou em paralelo.
- **fps 25 mantido** (decisão §5.2) — não mexi na timebase nem recalibrei o QA.
- **Multi-shot real:** o caminho de produção segue com um shot por cena (R1/C4); o
  contrato/QA hospedam multi-shot, mas o produtor de beats é fatia posterior.
