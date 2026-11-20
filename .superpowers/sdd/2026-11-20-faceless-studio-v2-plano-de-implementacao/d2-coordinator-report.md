# D2 — ProductionCoordinator, worker, handlers, modos e HTTP (relatório)

Branch `faceless-v2-impl`, sem push/merge. Dependências usadas, não refeitas: D
(`ProductionRun`/`StageExecution`/lease/fencing/outbox/CAS/idempotência — `34cc9c5`) e A (guard de
custo `ESTIMATE`/`ACTUAL`/`FREE` — `e8f6b52`, `d4db3cd`).

## Commits

- `9d5ab2c` `feat(production): porta de leitura de etapas (list_stages) no repositório D`
- `241be24` `feat(production): ProductionCoordinator, worker e handlers (D2)`
- `3419f04` `feat(api): endpoints de production-runs com erros de domínio mapeados`
- `e7b13ff` `test(production): coordenador/worker (DB), handlers, HTTP e fluxo pelo painel`
- (este relatório + linha no `progress.md`) em commit de docs.

Nenhuma migração nova; `0016`–`0021` e `tests/test_db.py` intocados. `render_plan.py`,
`scripts/export_contracts.py` e `contracts/` intocados (a fatia 2 estava lá).

## O que foi entregue

**Coordenador só com portas.** `application/production.py` depende de
`ProductionRunRepository`, `ProductionRunStageReader`, `RunRender`/`StartRender` e das portas de
vídeo/render/asset/approval — nunca de adaptadores (o `tests/test_architecture.py` continua verde).

**Worker com lease/fencing/checkpoint.** `ProductionWorker.work(run_id)` chama
`ProductionCoordinator.step` até `NOTHING_READY`/`TERMINAL`/`FAILED`/`PAUSED`. Cada passo reivindica a
próxima etapa pronta (CAS do repositório D), executa o handler, e conclui/falha com o dono e o
`fencing_token` do claim. `LOST` do repositório vira `WorkerStepResult.LOST` (o coordenador não marca
sucesso quando a fence recusa).

**Handlers e capacidades.** Registrados os **nove** estágios:

| Etapa | Estado | Base |
|---|---|---|
| `research` | **indisponível** (motivo explícito) | não existe `ResearchPort` (F3) |
| `script` | disponível | `GenerateScript` |
| `factcheck` | disponível | `RunFactCheck` (falha se o relatório não passa) |
| `storyboard` | disponível | `PrepareStoryboard` |
| `assets` | disponível | `ProduceAssets` |
| `render` | disponível | `StartRender` (enqueue no-op) + `RunRender` em linha |
| `qa` | disponível | gate técnico sobre o QA persistido (exige render OK e `qa_report.passed`) |
| `approval` | disponível | gate humano + **gate F6** (`domain.qa_report.approve`) |
| `publish` | **indisponível** (motivo explícito) | publicação é a fatia F; nunca auto-aprova |

**Dois modos.** `INTERACTIVE` pausa o run logo após `script` (revisão humana obrigatória) e sempre no
`approval`. `BUDGET_GUARDED` dispensa a pausa do roteiro **só** quando a projeção injetada
(`ProductionBudget`) existe e não passa do teto; projeção desconhecida ou acima do teto volta a
pausar (falha fechada). **Publicação nunca auto-aprova em nenhum modo** — `approval` pausa pelo
próprio handler.

**Pausa humana libera o worker.** `pause_run` persiste `WAITING_HUMAN` sem lease; o laço encerra e
solta a thread. Retomada re-reivindica com `fencing_token` novo.

**HTTP (F1-04/F2-03/F2-05).**
- `POST /studio/videos/{video_id}/production-runs` → **202** com `run_id`/`state`/`created`,
  `Idempotency-Key` (ou campo no corpo); ausência → **400**; replay → 202 `created:false`.
- `GET .../production-runs/{run_id}` → projeção (run, etapas, `next_action`, `next_stage`,
  capacidades) + eventos da outbox **sem segredos**.
- `pause`/`resume`/`cancel`/`retry` validados por estado, `RunNotFound` → 404, run de outro vídeo → 404.
- Erros de domínio mapeados: `ProductionIdempotencyConflict`→409, `InvalidIdempotencyKey`→422,
  `ProductionRunLockTimeout`→409, `ProductionRunReferencedEntityNotFound`→404,
  `InvalidPipeline`/`InvalidProductionTransition`→422, `StageCapabilityUnavailable`→409,
  `RunNotFound`→404. **Nenhum erro de negócio sai como 500.**

**Fiação.** `composition.py` constrói `build_postgres_production_run_repository(connect, COORDINATOR_DAG)`,
`build_stage_handlers(...)`, `ProductionCoordinator`/`ProductionWorker` e expõe `UseCases.production`.

## Provas e contagens reais

Docker `faceless-v2-hygiene-test-local:latest` (Python 3.12, pytest 8.3.5), `-p no:cacheprovider`,
rede `g1-net` com Postgres descartável (`g1-pg`) e prova montada em `/budget-test-proof`,
**as duas** variáveis `STUDIO_TEST_DSN` e `STUDIO_BUDGET_DISPOSABLE_DSN` + `STUDIO_BUDGET_TEST_PROOF_FILE`.

- Focados novos: `test_production_coordinator.py` 12, `test_production_handlers.py` 11,
  `test_production_api.py` 17, `test_production_flow_db.py` 4 → **44 passed** (com
  `test_architecture.py`, 4, o conjunto foi 48).
- Suíte completa: **1713 passed, 35 skipped, 2 failed** em 161 s.
  As 2 falhas são `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable`
  e `::test_extracted_starter_runs_contract_snapshot_and_backup_import` — **ambientais**: o
  `package-starter.sh` não consegue listar os arquivos rastreados porque `/workspace` é montado do
  worktree, cujo `.git` é um *gitfile* apontando para fora do mount. Não é regressão desta fatia
  (mesmo par de falhas em todas as fatias anteriores sem `.git` montado).
- `tests/test_db.py` passa (as duas listas já contêm `0018`); nenhuma migração nova.

## O que o código real obrigou a mudar do plano

1. **`run_id` determinístico pela chave.** O repositório D (`_existing_run`) compara `run_id` no
   replay: a mesma chave com outro `run_id` é `ProductionIdempotencyConflict`, não `EXISTING`. O
   coordenador deriva `run_id = uuid5(video_id, idempotency_key)`, então o replay apresenta a mesma
   identidade e não duplica run. (Sem isso, o teste de idempotência virou vermelho — foi o RED real.)
2. **Pipeline sem `research`.** Não existe `ResearchPort`; `script` depende de fontes já adicionadas
   ao vídeo. Também não há `skip` no repositório, e o DAG padrão encadeia
   `research→script→factcheck→storyboard→assets→render→qa→approval→publish`. Por isso o coordenador
   usa um `COORDINATOR_DAG` (do `script` ao `approval`) e declara `research`/`publish` indisponíveis.
3. **`factcheck` e `storyboard` ficaram disponíveis, não indisponíveis.** O texto do escopo citava
   `factcheck`/`storyboard` na lista de "capacidades que ainda não existem", mas os casos de uso
   determinísticos **existem** (`RunFactCheck`, `PrepareStoryboard`) e a máquina de estados do vídeo
   os **exige** entre o roteiro e os assets. Declará-los indisponíveis quebraria o fechamento de
   dependências e o fluxo ponta-a-ponta. As capacidades genuinamente ausentes são `research` (F3) e
   `publish` (F8) — essas sim ficaram indisponíveis e nunca fingem sucesso.
4. **Porta de leitura de etapas.** A porta D não lê etapas; a projeção de status precisa delas.
   Adicionei `ProductionRunStageReader.list_stages` como porta **separada** para não mexer na
   contagem do teste de forma da porta D (`test_postgres_adapter_matches_the_production_run_port`,
   que continua contando 11 métodos de escrita/leitura da D).
5. **Identidade do gate F6 sem contrato novo de render.** O gate F6 pede `render_id`/`checksum`, mas
   os `RenderJob` legados só expõem `id`/`input_hash`/`output_asset_id`. Mapeei
   `render_id = job.id` e `checksum = cache_key do asset de saída`; `latest = latest_output` e
   `requested = asset aprovado`. Assim um render novo **depois** da aprovação diverge e o gate recusa
   (`RenderSuperseded`) em vez de aprovar a versão errada. O relatório versionado declara
   `coverage=verified` com o check `studio.render.qa` (o QA já rodou dentro do render); sem QA ou com
   QA reprovado é `not_verified`/bloqueante e o gate recusa.
6. **Modo é configuração do servidor, não do corpo.** O modo do run não é persistido no schema (não
   criei migração). O modo vem de `STUDIO_PRODUCTION_MODE` (`Settings.production_mode`) e o corpo do
   POST não o reescreve. Escolha consciente para não abrir migração fora do escopo.
7. **`BUDGET_GUARDED` sem previsão de custo.** Não existe porta de projeção. Sem `production_budget`
   injetado o modo guardado **pausa** (falha fechada). A composição liga um **piso medido**
   (`spent_month` contra o teto) apenas quando `STUDIO_BUDGET_GUARD=1`; a proteção dura por operação
   continua sendo o guard hard da fatia A. É um piso, não um forecast — documentado no código.

## Limitações e o que ficou de fora (por escopo)

- `publish` (F8) e `research` (F3) continuam ausentes; o coordenador os recusa explicitamente.
- DLQ e trilha de auditoria dedicada (F1-08) não entram aqui; cancelamento e retry seletivo sim.
- Wizard `Novo vídeo` (F2-02) e UI de execução (F2-04) não fazem parte desta fatia (a API já expõe o
  necessário: 202 + projeção + próxima ação + ações por estado).
- Sem validação em navegador/leitor de tela (não há UI nova aqui).
