# F1 — execução persistida: ProductionRun, lease/fencing e outbox (fatia D1)

Commit **`3a7bb8d`** — "feat: add persisted production run domain, lease/fencing CAS and outbox
(F1-01/F1-02/F1-06 core)". A fatia entrega a espinha dorsal **persistida** da execução; **não**
implementa coordenador, handlers, provedores, HTTP/UI nem publicação. Não afirmo F1 concluído.

Base do worktree no início: `59b7502` (branch `faceless-v2-impl`). Durante a execução, outras
fatias commitaram no mesmo worktree (`aae03ad`, `eb707a1`); nada foi rebaseado nem sobrescrito.

## O que foi implementado

- `renderer/app/studio/domain/production_run.py` (domínio puro, sem I/O):
  - `ProductionRun` (`run_id`, `video_id`, `channel_id` opcional, `state`, `idempotency_key`,
    `schema_version`, `reason`, timestamps) com validação de IDs e chave.
  - `StageExecution` (`run_id`, `stage_id`, `state`, `attempt`, `lease_owner`, `lease_expires_at`,
    `fencing_token`, `checkpoint`, `error`, timestamps) com invariante: só `RUNNING` tem lease.
  - `StageDag` declarativo: validação topológica na construção, ordem determinística, dependência
    desconhecida/auto-dependência/ciclo/vazio rejeitados; `validate_stages` exige conjunto não vazio,
    sem repetição e **fechado sob dependências**; `STANDARD_DAG` cobre research → script → factcheck
    → storyboard → assets → render → qa → approval → publish (F1-05), sem handlers.
  - `RunState`, `StageState`, `ProgressEventType`, `Checkpoint`, `OutboxEvent`, mapas de transição.
  - Resultados explícitos (enum) com `__bool__` que levanta `TypeError`: `StageClaimResult`,
    `StageTransitionResult`, `LeaseResult`, `RunTransitionResult`, `CreateRunResult`, `AckResult`.
- `renderer/app/studio/adapters/postgres/production_repo.py`:
  - `PostgresProductionRunRepository` com exatamente a porta pedida; **factory**
    `build_postgres_production_run_repository(connect, *, dag=STANDARD_DAG)` para o controlador.
- `renderer/app/studio/adapters/postgres/migrations/0018_production_runs.sql` (quatro dígitos;
  `0016_channel_profiles` e `0017_paid_operations` já existiam): `production_runs`,
  `stage_executions`, `production_outbox` com CHECKs, FKs e índices.
- `renderer/app/studio/application/ports.py`: `ProductionRunRepository` (Protocol).
- `tests/test_production_run.py` (15 testes, domínio puro) e `tests/test_production_repo.py`
  (22 testes, PostgreSQL descartável com duas conexões reais).

## Decisões de design (e o porquê)

1. **Idempotência**: `idempotency_key` é `UNIQUE`. `create_run` usa `INSERT ... ON CONFLICT DO
   NOTHING RETURNING`; replay devolve `EXISTING` com o mesmo `run_id`. Chave com vídeo, canal ou
   conjunto de estágios diferente levanta `ProductionIdempotencyConflict`; nada é duplicado.
2. **CAS**: toda escrita abre transação, trava a linha do run (`SELECT ... FOR UPDATE`) e só então
   lê/escreve a etapa. A decisão usa o estado lido **na mesma transação travada**; `complete`/`fail`
   exigem ainda dono + `fencing_token` + lease não vencido no `UPDATE`. Recusas retornam enum
   (`LOST`, `NOT_RUNNING`, `NOT_ALLOWED`, `CHECKPOINT_REJECTED`, `UNKNOWN`) e não escrevem nada.
   A ordem de lock é sempre run → etapa, inclusive no heartbeat, para não haver ciclo.
3. **Lease/fencing**: `claim_stage` incrementa `attempt` e `fencing_token` e grava expiração.
   Etapa `RUNNING` com lease vencido é retomável por novo dono (novo token); o dono antigo não
   renova nem conclui. `renew_lease` só vale para o token atual e lease ainda válido.
4. **Checkpoint**: `complete_stage` e `fail_stage` aceitam `Checkpoint` (payload JSON + versão).
   A versão é monotônica por etapa (`CHECKPOINT_REJECTED` se não avançar) e sobrevive ao retry.
   `fail_stage` aceita checkpoint porque é o único caminho, nesta fatia, de persistir progresso de
   uma tentativa que não terminou — sem ele a recuperação por checkpoint não teria uso alcançável.
5. **Outbox**: `RUN_CREATED`, `RUN_STATE_CHANGED`, `STAGE_CLAIMED`, `STAGE_COMPLETED`,
   `STAGE_FAILED`, sempre inseridos na mesma transação da mudança de estado, com `event_version = 1`
   e payload JSON documentado no docstring do enum. `read_outbox` lê só não confirmados, em ordem
   de `id`; `ack_outbox` é idempotente (`ACKED`/`ALREADY_ACKED`/`UNKNOWN`).
6. **Pausa humana**: `pause_run` grava `WAITING_HUMAN` no run **e** na etapa em execução, com
   `lease_owner`/`lease_expires_at` NULL — nenhum worker fica bloqueado; a retomada é
   `resume_run` (etapa `WAITING_HUMAN` volta a `PENDING`), e um novo claim gera novo token/tentativa.
7. **Falha**: `fail_stage` marca a etapa `FAILED`, libera o lease e marca o run `FAILED` na mesma
   transação; retomar é explícito (`resume_run`), e a etapa `FAILED` é retomável por `claim_stage`.
8. **Sucesso**: o run só vira `SUCCEEDED` quando todas as etapas do run estão `SUCCEEDED`/`SKIPPED`
   (inclusive em pipeline reduzido).

## TDD — evidência real

- **RED**: com os testes escritos antes do código, a coleta falhou com
  `ModuleNotFoundError: No module named 'app.studio.domain.production_run'` (mesmo erro para a
  migração/adaptador inexistentes).
- **GREEN**: 37 testes focados passando (`15 + 22`).
- Ciclos intermediários reais, corrigidos e revalidados (não mascarados):
  - a migração falhou com `DuplicateObject: check constraint "production_runs_reason_check" already
    exists` — colisão entre nome explícito e nome automático da constraint da coluna `reason`
    (idem em `stage_executions_checkpoint_check`); renomeei as constraints de tabela;
  - `renew_lease` usava `_one()` sobre um `UPDATE` sem `RETURNING` →
    `ProgrammingError: the last operation didn't produce records`; adicionei `RETURNING stage_id`;
  - `stage_executions` não tem coluna `id`; o `RETURNING` passou a usar `stage_id`;
  - a guarda de escrita checava o run antes da etapa e devolvia `LOST` quando a etapa em pausa não
    estava `RUNNING`; inverti a ordem para o diagnóstico correto (`NOT_RUNNING`);
  - um teste meu de pipeline reduzido usava o token errado (`2` em vez de `1`) — corrigi o teste,
    não a implementação.

## Comandos e resultados (reais)

Imagem local `faceless-v2-hygiene-test-local:latest` (Python 3.12.16, pytest 8.3.5), rede Docker
isolada `f1d-net`, PostgreSQL 16-alpine descartável `f1d-pg` (tmpfs) e prova aleatória de 64 hex
montada somente leitura em `/budget-test-proof` no banco e no runner. Worktree montado somente
leitura, `-p no:cacheprovider`.

```
docker run --rm --network f1d-net \
  -v "$PWD":/workspace:ro \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro \
  -v "$PROOF_DIR":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1d-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1d-pg:5432/postgres \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest -q -p no:cacheprovider <alvos>
```

- `tests/test_production_run.py tests/test_production_repo.py`: **37 passed**.
- Foco ampliado (`+ tests/test_architecture.py tests/test_disposable_db_guard.py tests/test_db.py`):
  **63 passed, 2 failed** — as duas falhas são as listas desatualizadas de `tests/test_db.py`
  (ver abaixo), não a lógica da migração; `test_architecture.py` (pureza do domínio e da aplicação)
  e `test_disposable_db_guard.py` passaram.
- Suíte completa: **1422 passed, 35 skipped, 11 failed** no estado do worktree naquele momento.
  Atribuição:
  - **2 falhas minhas de integração de lista** (`test_migrate_applies_once`,
    `test_failed_migration_rolls_back_and_is_not_recorded`): o teste espera a lista sem
    `0018_production_runs`. Outra fatia já acrescentou `0019_ledger_estimate_and_attribution` à
    mesma lista e **esqueceu a 0018**; por isso o diff aparece como
    `At index 16 diff: '0018_production_runs' != '0019_ledger_estimate_and_attribution'`.
  - **9 falhas de outra fatia em curso** (`tests/test_budget_guard.py` 2,
    `tests/test_budget_http.py` 6 — arquivo novo não rastreado —, `tests/test_budget_reservations.py`
    1): todos em arquivos modificados/não rastreados por outra sessão, nenhum importa
    `production_run`/`production_repo`, e o conjunto de falhas **mudou entre duas execuções** da
    suíte (6 → 11) conforme esses arquivos mudavam, enquanto os meus 37 testes focados
    permaneceram verdes. Não são regressão desta fatia.
  - Os 35 `skipped` são os testes que exigem DSN/limites opcionais; não os investiguei como se
    fossem desta fatia.

### Valor exato que `tests/test_db.py` precisa (NÃO editei o arquivo; outra fatia o mantém)

Nas **duas** listas (linhas 25 e 37), inserir `"0018_production_runs"` imediatamente depois de
`"0017_paid_operations"`:

```
..., "0015_ledger_cost_confirmation", "0016_channel_profiles", "0017_paid_operations",
"0018_production_runs", "0019_ledger_estimate_and_attribution"]
```

Se o controlador quiser, `test_creates_all_tables` pode também listar `production_runs`,
`stage_executions` e `production_outbox` (a ausência não quebra o teste hoje).

## Fiação pendente para o controlador

- `renderer/app/studio/composition.py` **não foi editado** (arquivo em disputa). O adaptador expõe
  `build_postgres_production_run_repository(connect, *, dag=STANDARD_DAG)` no próprio módulo.
  Falta: instanciar no `Settings`/`create_*`, injetar no futuro `ProductionCoordinator` (D2) e
  registrar a migração no fluxo de inicialização já existente (`migrate` já a aplica).
- Nenhum endpoint/UI, nenhum provider, nenhum handler de estágio.

## Migração, rollout e rollback

- Migração **aditiva**: apenas `CREATE TABLE`/`CREATE INDEX` novos; nada existente muda. Código
  antigo ignora as tabelas. Rollout: aplicar a migração e só depois implantar o código que a usa.
- Rollback manual (ordem reversa das FKs), registrado no fim do `.sql`:

```
DROP TABLE studio.production_outbox;
DROP TABLE studio.stage_executions;
DROP TABLE studio.production_runs;
```

- Não há backfill nem reescrita de dados; executar o rollback com a outbox já consumida e sem
  consumidores ativos. As tabelas são novas, então o rollback é seguro antes de qualquer consumidor
  depender dos eventos.
- `channel_id` referencia `channel_profiles(id)` com `ON DELETE RESTRICT`: apagar um perfil de canal
  com runs é recusado (preserva a trilha).

## Limitações e riscos (explícitos)

- **Sem coordenador/handlers**: não há execução de estágios, chamada de provedor, nem efeito
  irreversível. O que existe é o estado persistido e o CAS.
- **Lease não expira sozinho**: não há reaper; a retomada só acontece quando um worker chama
  `claim_stage`. Um run pode ficar `RUNNING` com etapa órfã até alguém reivindicar.
- **Concorrência por run**: transições do mesmo run são serializadas pelo lock da linha do run
  (trade-off consciente por simplicidade e ausência de deadlock); runs distintos rodam em paralelo.
- **Outbox simples**: sem retry/DLQ, sem cursor por consumidor (o `ack` é global), sem poda/partição
  e sem ordenação por estágio além da ordem de gravação (`id`). `event_version = 1` é o contrato;
  alterações de payload exigem nova versão.
- **Checkpoint**: só é gravado em `complete_stage`/`fail_stage`; não há gravação intermediária de
  progresso nesta fatia (fica para D2), e a versão monotônica só é exercitável nesses caminhos.
- **`PAUSED`**: existe no domínio (e `resume_run` o aceita), mas nenhuma transição desta fatia o
  produz; a pausa implementada é a humana (`WAITING_HUMAN`).
- **Recuperação**: run `FAILED` exige `resume_run` explícito; não há política de retry/backoff nem
  limite de tentativas.
- **Pipeline fixo na criação**: os estágios de um run são definidos no `create_run`; não há adição
  de estágio depois. O DAG aceita fan-in declarado, mas o `STANDARD_DAG` é sequencial e só ele é
  exercitado.
- **Limites de tamanho**: `idempotency_key` ≤ 200, `owner` ≤ 200, `reason`/`error` ≤ 2000 (erro
  combinado no motivo do run é truncado em 2000), `lease_seconds` 1–86400, `read_outbox` 1–1000.
- **Testes de PostgreSQL** exigem banco exclusivamente descartável + prova privada; sem
  `STUDIO_BUDGET_DISPOSABLE_DSN`/`STUDIO_BUDGET_TEST_PROOF_FILE` são **skipped**, não aprovados.
  A prova usada aqui é nova e não foi reutilizada de outra fatia.
- **Números da suíte confundidos**: a contagem absoluta inclui testes e mudanças de outras fatias
  não commitadas (budget/ChargeEvidence, packaging, canal). Qualifiquei acima o que é desta fatia.

## Arquivos desta fatia

```
renderer/app/studio/domain/production_run.py                                  (novo)
renderer/app/studio/adapters/postgres/production_repo.py                      (novo)
renderer/app/studio/adapters/postgres/migrations/0018_production_runs.sql     (novo)
renderer/app/studio/application/ports.py                                      (+53: Protocol)
tests/test_production_run.py                                                  (novo)
tests/test_production_repo.py                                                 (novo)
```

Não toquei em `composition.py`, `tests/test_db.py`, `domain/beat_plan.py`,
`domain/visual_beat.py`, `api/`, `application/channels.py` nem adapters de canal. As demais
modificações/arquivos não rastreados no worktree pertencem a outras fatias.