# RP-03 — Builder e compilador puro do Render Plan (fatia 4)

**Fatia:** 4 (RP-03) da fundação **Render Plan** — RP-015, RP-016 e o compilador puro **RP-023**.
**Branch:** `feat/rp-03-builder` · **Worktree:** `…/39a258/rp-03-builder`.
**Base ao iniciar:** `e83af72`. Concorrência: três fatias em paralelo (tela de Canais, Analytics, SaaS);
nenhum arquivo fora desta worktree foi tocado. Commits locais por caminho exato; **sem push e sem merge**.

**Escopo entregue:** o **builder** (storyboard medido → `RenderPlan` válido) e o **compilador puro**
(`RenderPlan` + assets resolvidos → plano de execução FFmpeg determinístico). Nada de mídia, banco,
`subprocess` nem FFmpeg — isso é RP-05. RP-017/RP-018 (porta `VisualStyle` e preset
`cinematic-documentary`) ficaram **fora por decisão R4** do design (ver §Contradições).

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `0982a08` | RP-015/RP-016 — builder puro storyboard → plano | `renderer/app/studio/domain/render_plan_builder.py` (novo, +339), `tests/test_render_plan_builder.py` (novo) |
| `1bead3f` | RP-023 — compilador puro plano → execução FFmpeg | `renderer/app/studio/application/render_compiler.py` (novo, +560), `tests/test_render_compiler.py` (novo) |

Um commit por artefato lógico + suíte própria. `git status` não tem nenhuma alteração em arquivo existente:
o RP-03 é **aditivo**.

## O que foi entregue

### RP-015 — storyboard existente → plano (`domain/render_plan_builder.py`)

- `StoryboardScene` (cena editorial + **fala medida pós-TTS**, R1) e
  `storyboard_scene(row, speech_seconds=…)`, que projeta a linha real `studio.scenes`
  (narração, selo, `asset_id`) — `duration_s` do banco não existe, a fala entra como parâmetro.
- `asset_reference_for(asset, content_sha256=…)`: projeta `Asset` + hash do conteúdo em
  `AssetReference` do manifesto. O hash é **do conteúdo e explícito** (C1): nunca derivado do
  `assets.cache_key`.
- `build_render_plan(...)`: valida entradas, converte as fronteiras de cena com a **ponte da fatia 3**
  (`tick_windows` sobre as janelas contíguas de `scene_length`) e monta o plano:
  - **1 shot visual por cena** (R1/C4) em `visual-main`, cobrindo a cena ponta a ponta, com
    `effects.motion` **explícito** por cena (default `none`, sem o `index % 4` do legado);
  - **narração** por cena (`NarrationCue` + `GeneratedAudioSource(kind="voice")`, a unidade real de TTS);
  - **legendas** por trecho, de `make_cues` (a mesma distribuição do renderer legado), em `subtitle-main`;
  - **trilha gerada** `GeneratedAudioSource(kind="music")` com os parâmetros determinísticos da síntese
    (`bpm=122`, `seed=7`); `music=False` vira trilha **silenciosa** de mesmo comprimento (C2);
  - `Output` com resolução do formato e `disclosure`; `Provenance` com versão do builder.
- `style_snapshot_for_channel(profile)` (RP-016/R4): a identidade do canal entra por **chave + versão**
  (`ChannelProfile.id`/`version`); o texto livre de `visual_identity` não é carregado.

### RP-023 — compilador puro (`application/render_compiler.py`)

`compile_render_plan(plan, assets, work_dir, labels=…)` devolve `CompiledRender`, determinístico e sem I/O:

- **um segmento por shot** (suporta multi-shot **contíguo**; R1/C4);
- **imagem/gráfico** → `scale` 1.5× lanczos + `zoompan` (Ken Burns) com as expressões do legado escolhidas
  pelo `motion` do plano; **vídeo** → `trim`/`scale`/`fps`; **texto** → card local isento de mídia externa
  (o executor o renderiza; exige `metadata["text"]`);
- **selo + disclosure** e **legenda queimada por trecho** como `OverlayImage` que o executor materializa
  (Pillow), com a janela `enable='gte(t,·)*lt(t,·)'` do legado e índices de input corretos (0 mídia,
  1 selo, 2.. legendas);
- **narração** na ordem das cenas (WAVs `speech_NNN.wav` + `narration.wav`) e **trilha gerada**;
- **concat** `-c copy` e **mixagem** com `sidechaincompress` (ducking) e `loudnorm=I=-16:TP=-1.5:LRA=11`
  — o mesmo grafo do legado, inclusive no modo silencioso (C2);
- `digest()` sha256 do plano de execução canônico (JSON `sort_keys`) — mesma entrada, mesmo digest;
- **recusa** camadas sobrepostas de tracks diferentes (`CompileError`; composição é RP-024), asset não
  resolvido/indisponível/hash divergente e legenda que atravessa shot — nunca gera um vídeo errado.

## Validações obrigatórias (todas com teste)

| Exigência | Teste |
|---|---|
| Plano válido sem conhecer o renderer (RP-03 aceite) | `test_builder_produces_a_valid_render_plan_from_the_storyboard`, `test_builder_lays_scenes_contiguously_in_frame_aligned_ticks` |
| Sem deriva na ponte segundos↔ticks | `test_builder_does_not_reintroduce_rounding_drift_in_the_seconds_bridge` |
| Ticks inteiros / timebase explícita | `test_builder_uses_the_declared_ticks_per_second_and_rejects_a_bad_one` |
| `content_sha256` do conteúdo, não `cache_key` (C1) | `test_builder_keeps_the_content_hash_it_is_given_and_never_derives_it_from_cache_key`, `test_asset_reference_for_never_uses_the_cache_key_as_content_hash` |
| Trilha silenciosa de mesmo comprimento (C2) | `test_builder_represents_music_false_as_a_silent_track_of_the_same_length`, `test_silent_music_still_compiles_the_mix_graph_with_a_silent_track` |
| Motion explícito, sem `index % 4` (R3) | `test_builder_propagates_explicit_motion_and_paid_operation_keys`, `test_explicit_motion_compiles_to_the_legacy_ken_burns_expressions` |
| Disclosure no plano (R3) | `test_builder_disclosure_lives_in_the_output_and_defaults_to_the_ai_notice` |
| `style_snapshot` por chave + versão (R4/RP-016) | `test_style_snapshot_consumes_the_versioned_channel_identity_by_key_and_version` |
| Custo por chave (R5) | `test_builder_propagates_explicit_motion_and_paid_operation_keys` |
| Multi-shot hospedado (R1/C4) | `test_compiler_supports_a_multi_shot_scene_with_contiguous_shots` |
| Paridade visual (Ken Burns/fade/x264) | `test_still_image_compiles_to_ken_burns_with_legacy_geometry_and_encoding`, `test_explicit_motion_compiles_to_the_legacy_ken_burns_expressions` |
| Legenda por trecho com `enable` | `test_caption_overlays_are_burned_per_chunk_with_absolute_times_made_relative`, `test_caption_graph_windows_match_the_contract_ticks` |
| Áudio (ducking + loudnorm -16) | `test_audio_mix_reproduces_ducking_and_loudnorm_from_the_legacy_renderer` |
| Concat/final com os flags do legado | `test_concat_and_final_commands_use_the_same_flags_as_the_legacy_assembly` |
| Determinismo | `test_compiler_is_pure_and_deterministic`, `test_digest_changes_when_the_plan_changes` |
| Recusas claras (camada/asset/texto) | `test_compiler_rejects_an_asset_that_was_not_resolved`, `test_compiler_rejects_a_shot_whose_asset_is_unavailable`, `test_compiler_refuses_layered_visual_tracks_instead_of_producing_a_wrong_video`, `test_compiler_rejects_a_text_asset_without_text_metadata` |
| Núcleo puro (sem mídia/SDK) | `tests/test_architecture.py::test_render_core_has_no_media_or_provider_sdks` (verde) |

## Evidências (comandos reais)

Python 3.12.16 / pytest 8.3.5 na imagem `faceless-v2-hygiene-test-local:latest`, `PYTHONPATH=/workspace/renderer`,
`-p no:cacheprovider`.

**Postgres próprio (obrigatório):** container `rp3-pg` na rede `rp3-net` (e `rp3-net-internal`), com
`--tmpfs /var/lib/postgresql/data` e `--tmpfs /budget-test-proof`; a prova de 64 hex é lida por
`pg_read_file('/budget-test-proof/proof')` **dentro** do container e conferida localmente. As **duas**
variáveis foram passadas (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) mais
`STUDIO_BUDGET_TEST_PROOF_FILE`; `verified_test_connect` exige host único explícito (`rp3-pg`).

- **RED:** com os módulos novos ausentes,
  `… -m pytest -q tests/test_render_plan_builder.py tests/test_render_compiler.py` →
  `ModuleNotFoundError: No module named 'app.studio.domain.render_plan_builder'` (erro na coleta).
- **Contagem nova:** `tests/test_render_plan_builder.py` + `tests/test_render_compiler.py` = **51 testes**.
- **GREEN (área, com o Postgres próprio):**
  `… tests/test_render_plan_builder.py tests/test_render_compiler.py tests/test_architecture.py
  tests/test_contracts_snapshot.py tests/test_render_plan.py tests/test_render_plan_timeline.py
  tests/test_asset_resolver.py tests/test_ticks.py tests/test_beat_plan.py tests/test_visual_beat.py tests/test_db.py`
  → **347 passed**.
- **Gerador de contratos sem drift:** `… scripts/export_contracts.py --check` → `exit=0`.
  `git diff --stat contracts/` → **vazio** (nenhum contrato mudou; o builder/compilador não adicionam modelo
  versionado). `docs/10-arquitetura.md` intacto.
- **Arquitetura:** `test_domain_has_no_outward_or_io_imports`, `test_application_only_imports_domain` e
  `test_render_core_has_no_media_or_provider_sdks` verdes — `domain/` e `application/` seguem sem
  `PIL`/`numpy`/`ffmpeg`/`subprocess`/SDK.
- **Sem migração:** `0024` **não** foi usado e `tests/test_db.py` ficou intacto (o builder/compilador não
  persistem nada; persistência do plano é RP-06).
- **Higiene:** `python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (exit 0) **depois**
  dos commits, com os arquivos novos já rastreados. Na worktree o `.git` é *gitfile*, então o veredito final
  continua sendo o do `main` com gitdir real.
- **Suíte completa (serial, com o `.git` externo montado e o Postgres próprio):**
  `… -m pytest -q -p no:cacheprovider` → **1975 passed, 35 skipped, 2 failed** (ver qualificação abaixo).

### Falhas da suíte completa — qualificadas, não mascaradas

As **2** falhas da execução final são a família conhecida de render/publish sensível a carga:
`tests/test_publish_api.py::test_qa_failed_rerender_rejects_stale_approval_even_if_status_unchanged` e
`tests/test_publish_api.py::test_full_flow_approve_twice_publishes_once_and_records_the_id`. Nenhuma toca
arquivo desta fatia (o RP-03 é aditivo; `git status` limpo nos existentes).

O motivo é **pressão de memória da VM Docker** (compartilhada com as três fatias em paralelo): os dois testes,
rodados sozinhos com os mesmos args, **passam**:
`… "tests/test_publish_api.py::test_qa_failed_rerender_rejects_stale_approval_even_if_status_unchanged"
"tests/test_publish_api.py::test_full_flow_approve_twice_publishes_once_and_records_the_id"` → **2 passed**.

Numa execução anterior, com a VM mais apertada, a mesma suíte teve **1957 passed, 35 skipped, 19 failed** —
de novo só `test_render_adapters`/`test_render_api`/`test_publish_api` — e o subconjunto exato das falhas
passou isolado (**4 passed**). Erros observados: `RuntimeError: ffmpeg failed: ` (stderr vazio = processo
filho morto) e `TypeError: 'NoneType'`; sob memória folgada, `tests/test_render_api.py tests/test_publish_api.py`
→ **29 passed in 139s**. Um run chegou a derrubar o próprio Postgres (`the database system is in recovery mode`)
por contenção; após redimensionar o `rp3-pg` (1 GB, `shared_buffers=128MB`), a suíte rodou de ponta a ponta.

Conclusão: as falhas são **ambientais/instáveis, todas com reprodução verde isolada**; nenhuma regressão desta
fatia. Não alterei assertions para mascarar nada.

## Onde o código real contradisse o design (R1–R7 / C1–C4)

1. **RP-017 e RP-018 estão no backlog, mas o design R4 os adia.** O `writing-block.md` §6 lista, na fatia
   RP-03, "implementar a porta `VisualStyle`" (RP-017) e "criar o primeiro preset `cinematic-documentary`"
   (RP-018). O design (R4) decide o contrário: *"o preset estruturado (RP-17/18) **não** entra na fundação:
   precisa de estilo estruturado que não existe. `VisualStyle` como porta estruturada fica adiada."*
   **Fonte de verdade = design**: implementei só a referência por chave + versão (`StyleSnapshot`/
   `style_snapshot_for_channel`) e **não** criei a porta nem o preset. É a contradição mais relevante.
2. **R1 confirmado no código: a duração não existe no storyboard.** `build_render_plan` só recebe
   `speech_seconds` (a fala medida); o builder **não** lê `Scene.duration_s` (que segue sem produtor).
   O plano é montado no ponto em que a fala existe — como o design manda.
3. **R2 não foi fiado.** O design previa `RunRender` construindo o plano atrás de flag; isso é a fatia do
   executor (RP-05). Entreguei o builder/compilador **puros** e testados; nenhum módulo existente importa os
   novos (o caminho legado está intacto por construção).
4. **R3 — paridade exige dois bits que o contrato não carrega.** O compilador preserva o núcleo visual do
   legado (Ken Burns, `loudnorm -16`, ducking), mas:
   - o **selo** (`Scene.label`) e o **fade** por segmento (`FADE_S`) **não** estão no contrato do plano.
     O `label` entra no compilador por parâmetro explícito (`labels=…`, apresentação do storyboard, nunca
     inventado) e o **fade in/out é constante de política do compilador** (`FADE_S` do domínio), documentado —
     o `Transition` modela o encontro entre shots, não o fade interno do segmento. Divergência registrada.
5. **R5 sem tabela lateral nesta fatia.** O design previa `plan_scene_costs` (plano+cena+chave). O plano
   **referencia** a operação paga (`paid_operation_key` em cena e shot), mas a tabela liga plano persistido a
   cena — e persistir o plano é RP-06. Sem persistência, criar `0024` seria uma tabela órfã; **não criei**.
   R5 fica satisfeito no contrato; a persistência do custo rotulado fica para a fatia de versionamento.
6. **C1 respeitado ao pé da letra.** `content_sha256` é entrada explícita; o builder/compilador nunca tocam
   `assets.cache_key` (nem o `sha256("video|…|job.id")`). Teste dedicado.
7. **C2 no compilador.** `music=False` gera `GeneratedAudioSource(silent=True, params={})` e o compilador
   **mantém** o grafo de mixagem (trilha silenciosa), igual ao `render_ffmpeg.py:119-122`.
8. **C4 confirmado.** O builder produz **um shot por cena**; o multi-shot fica hospedado no contrato e é
   compilado (shots contíguos) quando o produtor de beats existir — não inventei beats do storyboard.
9. **Nomes de cena colidiam de novo.** `render_plan.Scene` (do plano) vs `contracts.Scene` (editorial):
   importei a editorial como `StoryboardRow` no builder, sem colisão no contrato exportado (`scene.schema.json`
   vs `renderplan.schema.json`).

## Limitações desta entrega

- **Sem fiação e sem execução:** nada foi plugado no `RunRender`/`composition.py`; o executor que roda o
  `CompiledRender` é RP-05. Também não há persistência do plano (RP-06) — logo, nada de `plan_scene_costs`.
- **Compilador é o esqueleto (RP-023):** recusa composição de **camadas** (tracks visuais sobrepostos) e
  legenda que atravessa shot; composições/transições ricas são RP-024 e a integração de áudio/legenda do
  executor é RP-025.
- **Selo e fade fora do contrato** (item 4): `labels` explícito e `FADE_S` como política do compilador.
- **Metadado técnico de vídeo** continua **declarado** no manifesto (RP-04); a sondagem real (`ffprobe`) é
  do executor.
- **Sem calibração de TTS:** a legenda usa a distribuição proporcional de `make_cues` (limitação já
  registrada no design §7.5), não alinhamento forçado.

## Arquivos desta fatia

- `renderer/app/studio/domain/render_plan_builder.py` (novo) — `StoryboardScene`, `storyboard_scene`,
  `asset_reference_for`, `style_snapshot_for_channel`, `build_render_plan`, `PlanBuildError`.
- `renderer/app/studio/application/render_compiler.py` (novo) — `compile_render_plan`, `CompiledRender`,
  `ShotExecution`, `OverlayImage`, `NarrationTrack`, `MusicTrack`, `AudioMix`, `ConcatExecution`, `CompileError`.
- `tests/test_render_plan_builder.py` (novo), `tests/test_render_compiler.py` (novo) — **51 testes**.

**Sem migração** (`0024` segue livre), **sem mudança de contrato** (snapshot intacto), **sem tocar**
`scripts/export_contracts.py`, `contracts/`, `tests/test_db.py` nem qualquer arquivo existente.