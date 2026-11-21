# RP-06 — Regeneração seletiva: grafo de dependências + cache (fatia 7)

**Fatia:** 7 (RP-06) da fundação **Render Plan** — RP-027 (versionar plano e assets), RP-028 (grafo de
dependências e invalidação seletiva) e RP-029 (reúso e política de cache) implementados.
**Branch:** `feat/rp-06-regen` · **Worktree:** `…/39a258/rp-06-regen` · **Base ao iniciar:** `2be7104`.
**Restrições respeitadas:** nada escrito fora da worktree; `domain/render_plan.py`, `domain/ticks.py`,
`application/render_compiler.py`, `adapters/render_plan_ffmpeg.py` **intactos**; `api/panel*.py`,
`application/channels_page.py`, `renderer/app/main.py`, `tests/test_providers.py` **intocados**.
Commit local por caminho exato; **sem push e sem merge**.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `73387a0` | RP-028/RP-029 — grafo de dependências e invalidação seletiva (núcleo puro) | `domain/render_cache.py` (novo), `application/render_cache.py` (novo), `application/ports.py` (porta), `tests/test_render_cache.py` (novo), `tests/test_render_regeneration.py` (novo) |
| `bf9307e` | RP-027 — persistência versionada do plano e índice de cache | `adapters/postgres/migrations/0032_render_plan_cache.sql` (novo), `adapters/postgres/render_plan_repo.py` (novo), `tests/test_render_plan_repo.py` (novo), `tests/test_db.py` |
| `b43f26e` | RP-029 — fiação na composição | `composition.py`, `application/use_cases.py` |

Ordem escolhida: o núcleo puro **primeiro** (é o que prova o aceite), a persistência **depois**, a
fiação **por último**. Nada de `git add -A`.

## Onde mora o quê (Clean Architecture, respeitado)

| Camada | Arquivo | Conteúdo |
|---|---|---|
| `domain` (puro) | `domain/render_cache.py` | `NodeId`, `CacheNode`, `DependencyGraph`, `plan_graph`, `selective_invalidation`, `CachePolicy`, `Invalidation`, `CacheEntry`, `PlanArtifact` |
| `application` (puro) | `application/render_cache.py` | `PlanRegeneration.decide/commit`, `Regeneration` |
| `application` (porta) | `application/ports.py` | `RenderPlanRepository` (Protocol) |
| `adapters` | `adapters/postgres/render_plan_repo.py` | `PostgresRenderPlanRepository` |
| wiring | `composition.py` | `PlanRegeneration(PostgresRenderPlanRepository(connect))` → `UseCases.plan_regeneration` |

`domain`/`application` **não importam** mídia/SDK/banco — provado por
`tests/test_architecture.py::{test_domain_has_no_outward_or_io_imports,test_application_only_imports_domain,test_render_core_has_no_media_or_provider_sdks}`
(verdes). O `subprocess`/PIL continuam só no `adapters/`.

## Como a invalidação seletiva é provada (arquivo:teste)

**Modelo.** O grafo tem um nó por elemento lógico: `narration:<scene>`, `visual:<shot>`, `music:<source>`,
`concat:video` e `final:video`. Cada nó carrega um `fingerprint` (sha256) do **conteúdo** — nunca da
posição absoluta na timeline. Identidade **lógica** = `NodeId(kind, key)` (plano/revisão/cena/shot);
identidade **física** = o fingerprint do conteúdo (design §5.5). `selective_invalidation` invalida um nó
quando o fingerprint mudou, quando o nó é novo, ou quando **algum nó do qual ele depende** foi invalidado
(propagação transitiva). `concat` depende de todos os `visual`; `final` depende de `concat`, das narrações
e da trilha.

**A prova da mutação — mudar A não invalida B, mudar B não invalida A, nada mudou = hit:**

| Teste (arquivo:teste) | O que prova |
|---|---|
| `tests/test_render_cache.py::test_changing_scene_a_reuses_scene_b_narration_and_visual` | alterar o texto da cena A invalida `narration/visual` de **A** e mantém `narration/visual` de **B** em `reusable` (cache hit) |
| `tests/test_render_cache.py::test_changing_scene_b_reuses_scene_a_narration_and_visual` | simétrico: alterar B não toca em A |
| `tests/test_render_cache.py::test_absolute_timeline_position_never_invalidates_a_downstream_scene` | **a prova mais forte**: esticar a duração de A desloca B no tempo; o fingerprint de B **não muda** e B segue reusável (o segmento é o mesmo quadro, só noutra posição) |
| `tests/test_render_cache.py::test_nothing_changed_is_a_full_cache_hit` | sem alteração, **todos** os nós são `reusable` (inclui `final`): cache acerta |
| `tests/test_render_cache.py::test_final_composition_is_invalidated_when_any_scene_changes` | mudar uma cena invalida `concat` e `final` — **a composição final é necessária**, o aceite admite isso |
| `tests/test_render_cache.py::test_dependency_propagates_even_when_the_aggregate_fingerprint_is_unchanged` | trocar o byte-hash do asset de A mantém o fingerprint do `concat` idêntico, mas ele é invalidado **por dependência** (propagação é load-bearing) |
| `tests/test_render_cache.py::test_added_and_removed_nodes_are_reported` | remover A e manter B: B continua reusável; A vira `removed` |
| `tests/test_render_cache.py::test_policy_can_disable_reuse_for_a_kind` | a política de cache é explícita e desliga o reúso por tipo |
| `tests/test_render_regeneration.py::test_changing_scene_a_reuses_scene_b_from_the_cache` | o mesmo aceite no caso de uso: A em `invalidated`, B em `cache_hits`, `final_recompose=True` |
| `tests/test_render_regeneration.py::test_commit_then_identical_revision_is_a_full_cache_hit` | ciclo real: commitar a revisão 1 e decidir a 2 idêntica → `invalidated=()`, `final_recompose=False`, tudo em `cache_hits` |
| `tests/test_render_regeneration.py::test_reusable_but_unrecorded_artifact_is_a_miss_not_a_hit` | honestidade do cache: conteúdo igual **sem** artefato registrado não é "hit", é `missing` (precisa gerar) |
| `tests/test_render_plan_repo.py::test_full_regeneration_cycle_against_the_repository` | o ciclo completo contra o **Postgres real** (não só o fake) |

**Prova de que os testes são load-bearing (mutação executada fora da worktree, em cópia descartável):**
1. desligar a propagação transitiva → 3 falhas, entre elas
   `test_dependency_propagates_even_when_the_aggregate_fingerprint_is_unchanged` e
   `test_final_composition_is_invalidated_when_any_scene_changes`;
2. trocar o fingerprint relativo pela **posição absoluta** → falha
   `test_absolute_timeline_position_never_invalidates_a_downstream_scene`.
Nenhuma das duas mutações passou silenciosa.

## RP-027 — versionamento (identidade lógica ≠ física) e migração 0032

**Migração usada: SIM — `0032_render_plan_cache.sql`** (a próxima livre após 0031; RP-07 usa 0033 se
precisar). Migração **aditiva**, nenhum `DROP`, nenhuma tabela existente alterada. Três tabelas:

| Tabela | Identidade | Papel |
|---|---|---|
| `studio.render_plans` | **lógica** | o documento do plano por `(plan_id, revision)` (JSONB); PK `(plan_id, revision)`; FK `video_id → studio.videos` |
| `studio.plan_artifacts` | **física** | artefato por `hash/codec/localização` (`content_sha256`, `location`), independente da revisão |
| `studio.render_cache_entries` | **lógica→física** | artefato produzido por `(plan_id, node_kind, node_key, fingerprint)`, com FK para a revisão persistida; `entries()` devolve o mais recente por nó |

`tests/test_db.py` atualizado nas **duas** listas do `migrate` **e** na lista de tabelas
(`test_migrate_applies_once`, `test_failed_migration_rolls_back_and_is_not_recorded`, `test_creates_all_tables`).

## RP-029 — política de cache e "render parcial"

- **Política explícita** em `CachePolicy.reusable_kinds` (default: todos os tipos reusáveis). `concat`/`final`
  só são reusados quando **nada** mudou; qualquer alteração de cena os invalida por dependência.
- **Reúso real, no grão certo:** o executor já produz **um segmento de vídeo por shot**, **um WAV por cena**
  (`speech_NNN.wav`), a faixa de narração, a trilha e a montagem. Portanto os pontos de reúso tecnicamente
  viáveis são exatamente esses segmentos/WAVs — e é isso que o cache identifica (`cache_hits`).
- **O que NÃO é feito — declarado, não prometido:** não há *patch* do MP4 final no lugar. Quando qualquer
  cena muda, `concat` e `final` são invalidados e a **recomposição** (concat + mixagem + `loudnorm`) roda.
  O aceite literal admite isso ("a composição final pode continuar necessária"). Reusar o MP4 final só
  quando **nada** mudou é seguro e está coberto (`test_nothing_changed_is_a_full_cache_hit`).

## O que ficou de fora / o que NÃO está ligado (honestidade)

- **A execução do reúso não está ligada ao executor.** `PlanRegeneration` **decide** o que reusar, mas o
  `adapters/render_plan_ffmpeg.py` está na lista de não-tocar desta fatia (RP-05, revisado). Logo, o caminho
  de produção ainda re-renderiza todos os segmentos; a decisão de reúso existe e é persistida, mas o
  consumo pela malha de render (pular o FFmpeg dos nós em `cache_hits`) é **trabalho do executor** — fatia
  posterior, com o mesmo rigor de paridade. Zero promessa de "render parcial do MP4" hoje.
- **Sem `plan_scene_costs`.** A atribuição de custo por cena (R5) é de outra fatia; esta não a toca.
- **Consumidor do caso de uso** (`UseCases.plan_regeneration`) é a tela Editor / botão "regenerar cena"
  (fatia posterior, design §8/§11-R7). A persistência e a decisão ficam prontas; a API não as expõe.
- **`plan_graph` recebe `labels`** porque o selo editorial não faz parte do contrato do plano (RP-05 o
  mantém fora); quem chamar com selo tem de passar o mesmo mapa do compilador.
- **Sem aceleração de I/O**: `plan_graph` recalcula sha256 por chamada (barato, puro). Se virar gargalo em
  planos muito grandes, memoizar é otimização posterior.

## Validações reais (comandos)

Imagem `faceless-v2-hygiene-test-local:latest`, `PYTHONPATH=/workspace/renderer`, `-p no:cacheprovider`.
**Postgres próprio:** container `rp6-pg` na rede `rp6-net`, `--tmpfs /var/lib/postgresql/data`, prova de
64 hex em `-v <dir>:/budget-test-proof:ro` (lida por `pg_read_file('/budget-test-proof/proof')`). As
**duas** DSNs foram passadas (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

| Partição | Comando (resumo) | Resultado |
|---|---|---|
| Núcleo + banco | `test_architecture test_contracts_snapshot test_render_cache test_render_regeneration test_render_plan_repo test_db test_render_plan test_render_plan_timeline test_render_plan_builder test_render_compiler test_render` | **191 passed** |
| Executor FFmpeg | `test_render_plan_executor` | **13 passed** |
| Regressão de render/API/composição | `test_render_api test_render_repo test_panel_production_render test_rich test_render_adapters` | **72 passed** |
| Contratos sem drift | `python scripts/export_contracts.py --check` | **EXIT=0** (nenhum modelo do plano mudou; `contracts/` e o snapshot intactos) |
| Higiene de segredos | `python3 scripts/secret_hygiene.py scan` | `Secret hygiene check passed.` (EXIT 0) |

**Testes novos: 31** — `tests/test_render_cache.py` **16**, `tests/test_render_regeneration.py` **7**,
`tests/test_render_plan_repo.py` **8**. Nenhuma asserção existente foi afrouxada.

**Memória:** clipes curtos no executor (13 testes, ~9 s), partições separadas, `rp6-pg` próprio. Nenhum
`ffmpeg SIGKILL`/rc 137 observado nesta execução.
