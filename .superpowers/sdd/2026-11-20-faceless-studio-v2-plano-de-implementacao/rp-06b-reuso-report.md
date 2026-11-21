# RP-06b — o executor consome o cache: reúso ponta a ponta (fatia 7, gap declarado da RP-06)

**Gap fechado:** na RP-06 o grafo de dependências e o cache **decidiam** o que reusar, mas o
executor (`adapters/render_plan_ffmpeg.py`) ainda re-renderizava **todos** os segmentos — o
reúso valia no núcleo, não ponta a ponta. Aqui o executor **consome** a decisão: um nó em
`cache_hits` com artefato físico íntegro não roda FFmpeg.

**Aceite da RP-029:** *"alterar uma cena não exige regenerar narrações, imagens ou vídeos de
outras cenas. A composição final pode continuar necessária para produzir o MP4 definitivo."*
Entregue para **vídeos** (segmentos por shot): mudar a cena A ⇒ re-renderiza A, reusa o
segmento de B do cache e **recompõe** `concat` + `final`. Nada de patch parcial do MP4.

**Branch:** `feat/rp-06b-reuso` · **Worktree:** `…/39a258/rp-06b-reuso` · **Base:** `0bf968a`.
Nada escrito fora da worktree. Commit local por caminho exato; **sem push e sem merge**.

## Commit

| Commit | Tema | Arquivos |
|---|---|---|
| `645c60d` | RP-06b — reúso consumido pelo executor + registro de artefatos | `adapters/render_plan_ffmpeg.py`, `adapters/postgres/render_plan_repo.py`, `application/ports.py`, `composition.py`, `tests/test_render_plan_executor.py`, `tests/test_render_plan_repo.py`, `tests/test_render_reuse.py` |

## O que mudou (e onde)

| Camada | Arquivo | Mudança |
|---|---|---|
| `adapters` (executor) | `adapters/render_plan_ffmpeg.py` | `PlanFfmpegRenderer` ganha `plans`/`cache_root`; `render()` decide o reúso, `execute()` pula o FFmpeg dos nós reusados, `_record()` registra os artefatos |
| `adapters` (repo) | `adapters/postgres/render_plan_repo.py` | `record_entries`/`record_artifacts`: grava o índice de uma revisão inteira numa transação |
| `application` (porta) | `application/ports.py` | `RenderPlanRepository.record_entries`/`record_artifacts` (Protocol) |
| wiring | `composition.py` | **único** lugar que injeta `PostgresRenderPlanRepository(connect)` + `cache_root=<storage_root>/render-cache` no renderer |

`domain/render_cache.py`, `domain/render_plan.py`, `domain/ticks.py` e
`application/render_compiler.py` **intactos**. `property`/`application/render.py` **intacto**:
o reúso acontece no executor, sem o `RunRender` precisar conhecer plano/revisão/repo.
`api/panel*.py`, `application/channels_page.py`, `renderer/app/main.py`, `tests/test_providers.py`,
`docs/` **intocados**.

## Como o reúso funciona

1. **Revisão por render.** Cada `render()` é uma revisão nova (`revision = última + 1`) do mesmo
   `plan_id` (`plan:<video_id>`). É isso que dá ao `PlanRegeneration.decide` uma revisão anterior
   para comparar **por fingerprint de conteúdo**.
2. **Decisão.** `PlanRegeneration.decide(plan)` aplica `plan_graph` + `selective_invalidation`
   (propagação de dependência: mudar uma cena invalida `concat`/`final`) e devolve `cache_hits`.
3. **Confirmação física.** Só entra em reúso o nó cujo artefato **existe** e cujo `sha256` do
   arquivo **bate** com `render_cache_entries.artifact_sha256`. Qualquer dúvida (arquivo ausente,
   hash divergente, erro de leitura) ⇒ **re-renderiza**.
4. **Execução.** Visual em hit ⇒ copia o segmento; narração em hit ⇒ usa o WAV do cache; música
   em hit ⇒ usa o WAV do cache. `concat`/`final` só são copiados quando **nada** mudou (senão o
   FFmpeg de montagem/mixagem roda de novo). Se `final` é hit, nem um FFmpeg roda.
5. **Registro.** Ao fim do render, `_record` copia cada artefato produzido para
   `<storage_root>/render-cache/<plan>/<kind>/<key>-<fingerprint[:16]>.<ext>` (fora do `work/<job>`
   descartável), grava `plan_artifacts` (`content_sha256` **do arquivo**, `codec`, `media_type`,
   `byte_size`, `location`) e `render_cache_entries` (nó → fingerprint → artefato), e persiste a
   revisão do plano. **Sem artefato físico não há registro** — nada de cache otimista.

## Como foi provado (arquivo:teste) — contagem de execuções do FFmpeg

O `runner` é injetado no `PlanFfmpegRenderer`; ele **conta e registra cada comando FFmpeg** sem
executá-lo (grava o arquivo de saída). A prova é **quais comandos rodaram**, pelo último argv
(o arquivo de saída) — não por bytes do MP4.

| Teste (arquivo:teste) | O que conta / prova |
|---|---|
| `tests/test_render_plan_executor.py::test_changing_one_scene_reuses_the_other_scene_without_running_ffmpeg` | executor: 1ª revisão = **4** comandos (A+B+concat+mix). Muda A ⇒ 2ª revisão = **3** comandos; `scene_000.mp4` (A) roda, `scene_001.mp4` (B) **não**; concat e final rodam |
| `tests/test_render_plan_executor.py::test_rendering_the_same_plan_again_reuses_the_final_mp4_without_ffmpeg` | nada mudou ⇒ **0** comandos no 2º render; o MP4 final sai do cache |
| `tests/test_render_plan_executor.py::test_a_corrupted_cached_artifact_is_not_reused` | artefato com hash divergente **não** é reusado: volta aos **3** comandos (re-renderiza) |
| `tests/test_render_reuse.py::test_changing_one_scene_does_not_run_ffmpeg_for_the_other_scene` | **caminho de produção** (`RunRender` → executor): 1º render 4 comandos, muda a cena A ⇒ 2º render **3** comandos; `work/<job>/scene_001.mp4` **não** aparece nas saídas, `scene_000.mp4` e `final.mp4` sim |
| `tests/test_render_reuse.py::test_render_is_registered_so_the_next_cycle_has_a_cache_hit` | o 1º render grava o índice (rev 1) com `artifact_uri` de arquivo real; 2º render idêntico ⇒ **0** comandos, revisões `[1, 2]` |
| `tests/test_render_plan_repo.py::test_executor_reuses_the_unchanged_scene_against_the_real_repository` | o mesmo fluxo contra o **Postgres real** (documento JSONB → grafo): 4 ⇒ **3** comandos, `scene_001.mp4` ausente |
| `tests/test_render_plan_repo.py::test_batch_registration_writes_entries_and_artifacts_idempotently` | `record_entries`/`record_artifacts` gravam índice lógico + físico, idempotentes |
| `tests/test_render_plan_executor.py::test_the_registered_ffmpeg_renderer_is_the_plan_renderer` | a fiação da `composition.py` injeta `plans` e `cache_root`; o kill-switch (`render_plan_enabled=False`) ainda devolve `DisabledRenderer` |

**Por que os testes são load-bearing (mutação executada e revertida):** forçar `_reuse_hits` a
devolver `{}` (desligar o consumo do cache) faz **4 falhas** — exatamente os testes de reúso
(unidade + produção), incluindo a asserção de `3` comandos. A mutação foi revertida; o arquivo
voltou byte-a-byte ao original.

## Limites explícitos (o que ainda fica fora)

- **Narração: o artefato é reusado, mas o TTS ainda roda.** O fingerprint do nó `narration:<scene>`
  (RP-06, `domain/render_cache.py`) depende de `duration_ticks` da fala — que é **saída do TTS**.
  Logo a decisão de reúso da narração só é possível **depois** de sintetizar a voz; o executor
  reusa o **WAV** (não regenera o artefato de áudio), mas o `Voice.speak` continua sendo chamado
  no `RunRender`. Pular o TTS exigiria um fingerprint de narração que não dependa da duração (ou
  comparar texto de forma não-lossless, que hoje não é segura) — fora do escopo desta fatia.
- **Imagens de outras cenas:** as imagens não são produzidas pelo executor; são geradas na etapa
  de mídia (`ProduceAssets`), que já deduplica por `cache_key`. O caminho de render só as **consome**.
- **Sem patch do MP4 final.** Quando qualquer cena muda, `concat` e `final` são invalidados por
  dependência e a **recomposição** roda (o aceite admite). O MP4 final só é reusado quando **nada**
  mudou — aí sim, zero FFmpeg.
- **Cache em disco cresce por fingerprint.** Cada revisão de um nó grava
  `<key>-<fingerprint[:16]>`; não há GC do diretório `render-cache/` (eviction é fatia futura).

## Validações reais (comandos)

Imagem `faceless-v2-hygiene-test-local:latest`, `PYTHONPATH=/workspace/renderer`, `-p no:cacheprovider`.
**Postgres próprio:** container `rp6b-pg` na rede `rp6b-net`, `--tmpfs /var/lib/postgresql/data`,
prova de 64 hex montada em `-v <dir>:/budget-test-proof:ro`. As **duas** DSNs foram passadas
(`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

| Arquivo | Resultado |
|---|---|
| `tests/test_architecture.py` | 6 passed |
| `tests/test_render_cache.py` | 16 passed |
| `tests/test_render_regeneration.py` | 7 passed |
| `tests/test_render_plan_repo.py` | 10 passed |
| `tests/test_db.py` | 15 passed |
| `tests/test_composition.py` | 8 passed |
| `tests/test_render_plan_executor.py` | 17 passed |
| `tests/test_render_reuse.py` (novo) | 2 passed |
| `tests/test_render.py` | 27 passed |
| `tests/test_render_adapters.py` | 16 passed |
| `tests/test_render_api.py` | 15 passed |
| **Total** | **139 passed** |
| `python scripts/export_contracts.py --check` | **EXIT=0** (nenhum modelo do plano mudou) |
| `python3 scripts/secret_hygiene.py scan` | `Secret hygiene check passed.` (**EXIT 0**) |

**Testes novos: 8** — `tests/test_render_plan_executor.py` **+4** (3 de reúso + 1 do kill-switch;
o `test_the_registered_ffmpeg_renderer_is_the_plan_renderer` foi estendido para checar a fiação),
`tests/test_render_reuse.py` **2**, `tests/test_render_plan_repo.py` **+2**. Nenhuma asserção
existente foi afrouxada.

**Memória:** partições separadas (núcleo/DB, executor+uso real, FFmpeg real); clipes curtos.
Nenhum `ffmpeg SIGKILL`/rc 137 observado nesta execução.
