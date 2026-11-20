# F1 — execução persistida: ProductionRun, lease/fencing e outbox (fatia D1)

- Implementação: commit **`3a7bb8d`** — domínio, repositório, migração `0018` e porta.
- Correção da revisão (round 1): commit **`09ea44b`** — chave canônica, tradução de erros, revogação
  de leases no resume, `expected_state`, índices mortos e rollback.

A fatia entrega a espinha dorsal **persistida** da execução; **não** implementa coordenador,
handlers, provedores, HTTP/UI nem publicação. Não afirmo F1 concluído.

A revisão **aprovou o núcleo** (CAS/fencing/outbox/lease sob sondagens reais: 10/10 disputas com um
único `CLAIMED`; lease real expirando com o dono antigo sempre `LOST`; outbox atômica por gatilho
de rollback; outbox ordenada por run; DAG 200/200 ciclos e 400 DAGs sem violação). Esta rodada
corrige os defeitos de borda reproduzidos, listados abaixo.

## Correções desta rodada (TDD: RED → GREEN)

### S1 — `idempotency_key` sem normalização (4 runs para 4 grafias)

**Decisão:** a identidade é **byte-a-byte, canônica e minúscula**. Variantes com espaço nas bordas,
espaço interior, caractere invisível (`Cc`/`Cf`/`Cs`/`Zl`/`Zp`) ou caixa diferente são **recusadas**
com `InvalidIdempotencyKey` — nunca normalizadas silenciosamente. Motivo: uma variante pode ser um
retry acidental do mesmo pedido ou um pedido diferente, e os dois não podem colidir; como a chave
atravessa a rede, não há como distinguir. O cliente deve enviar a chave já canônica. A comparação e
a unicidade no banco continuam byte-a-byte (`UNIQUE`).

- `domain/production_run.py`: `canonical_idempotency_key` (usado por `ProductionRun` e pelo
  repositório) + `InvalidIdempotencyKey`.
- RED: `order-42`, `order-42 `, `ORDER-42` e ` order-42` criavam runs distintos. GREEN: só
  `order-42` é aceita; as outras três são recusadas e nenhuma linha é criada. Cobertura também de
  espaço interior, tab, ZWSP, NBSP, vazio, não-string e chave > 200.

### S2 — erros de banco mal traduzidos

(a) `ForeignKeyViolation` crua em `create_run` (vídeo/canal inexistente) agora vira
`ProductionRunReferencedEntityNotFound` (erro de domínio explícito, sem 500).

(b) `LockNotAvailable` (SQLSTATE `55P03`) era capturado por `_translated` como
`ServiceUnavailable` (503), porque herda `OperationalError`. O adaptador agora tem um tradutor
**interno** (`_production_errors`, entra depois e sai antes de `_translated`):

- `LockNotAvailable` → `ProductionRunLockTimeout` (contensão: repetir é seguro; nenhuma escrita foi
  confirmada);
- `ForeignKeyViolation` → `ProductionRunReferencedEntityNotFound`;
- indisponibilidade real continua `ServiceUnavailable`.

Teste com `lock_timeout = 200ms` numa conexão do repositório e a linha do run travada por outra
conexão: a chamada falha com `ProductionRunLockTimeout`, o run permanece `CREATED` e uma nova
chamada depois do rollback funciona. O adaptador **não impõe** `lock_timeout` global (decisão
desta fatia); quem chamar deve configurá-lo (ver limitações).

### R1 — `resume_run` após `FAILED` readmitia a geração anterior

`resume_run` agora atualiza as etapas `WAITING_HUMAN` **e `RUNNING`** para `PENDING`, zera
`lease_owner`/`lease_expires_at` e **incrementa o `fencing_token`**. A geração anterior recebe
`LOST` mesmo que a etapa já tenha mudado de estado: a guarda de escrita compara o token antes do
estado (`token antigo → LOST`; token atual fora de `RUNNING` → `NOT_RUNNING`).

Teste com DAG fan-out: `research → {script, factcheck}`, dois workers com token 1 em paralelo;
`script` falha, o run vira `FAILED` e `factcheck` continua `RUNNING` com lease. Após
`resume_run(RUN, FAILED)`: `factcheck` fica `PENDING` sem lease, token 2; o `complete` do worker
antigo com token 1 retorna **`LOST`** e não escreve; o novo claim gera token 3.

### R2 — retomada sem precondição de concorrência

`resume_run(run_id, expected_state: RunState)` exige o estado declarado explicitamente. Se o estado
persistido divergir do esperado (ou não for retomável), retorna `NOT_ALLOWED` sem escrever nada;
`expected_state` que não é `RunState` é `TypeError`.

**A prova de aprovação humana versionada fica para D2** e não foi implementada: o ponto de
integração nomeado é o gate de `domain/qa_report.py` (aprovação por hash/versão do render) gravado
no **checkpoint da etapa `approval`**; em D2, `resume_run` receberá a referência/versão aprovada e
recusará retomada de run `WAITING_HUMAN` sem prova. Hoje a pré-condição é só o estado — documentado
no docstring da porta e do adaptador.

### M — migração e operação

1. **Índices mortos removidos** (decisão: remover, não implementar consulta nova). `production_runs
   _video_idx` e `stage_executions_active_lease_idx` não serviam nenhuma consulta do repositório:
   o run é lido pela PK `run_id` e a etapa por `(run_id, stage_id)`, e o comentário prometia uma
   varredura de etapa órfã que não existe. Um índice para `video_id`/lease entra junto da consulta
   que o justificar (D2/painel). O `production_outbox_unacked_idx` permanece porque
   `read_outbox` faz `WHERE acked_at IS NULL ORDER BY id LIMIT`.
   Teste de schema trava a decisão (só PK + índice único da chave; outbox com o índice parcial).
2. **Rollback corrigido** no fim de `0018`: depois dos `DROP TABLE` (ordem reversa das FKs), o
   runbook inclui `DELETE FROM studio.schema_migrations WHERE version = '0018_production_runs';`
   — sem isso `migrate()` considera a versão aplicada e nunca recria as tabelas.
3. Migração editada no próprio `0018_production_runs.sql` (round de revisão, ainda não liberada);
   não há `0019` desta fatia.

## Cobertura de testes — lacunas apontadas pela revisão

Fechadas nesta rodada:

- **Relógio do banco x relógio do processo**: `test_lease_expiry_uses_the_database_clock` usa lease
  real de 2 s (`sleep` real): logo após o claim, um segundo worker recebe `BUSY`; depois do
  vencimento, o próprio banco responde `lease_expires_at <= statement_timestamp()` e o takeover é
  `CLAIMED`. Em complemento, `test_adapter_never_reads_the_process_clock` falha se o adaptador
  passar a usar `datetime.now`/`utcnow`/`time.time`/`monotonic`.
- **Outbox atômica em todos os caminhos**: gatilho de rollback rejeitando por `event_type`, cobrindo
  `create` (`run.created`), `claim` (`stage.claimed`), `fail` (`stage.failed`), `complete`
  (`stage.completed`), `pause` e `cancel` (`run.state_changed`). Em cada um, a mudança de estado é
  revertida junto com o evento; removido o gatilho, a transição funciona.
- **Fan-out no nível do repositório**: dois estágios irmãos em `RUNNING` com tokens independentes;
  conclusão de ambos leva o run a `SUCCEEDED`; dependência ainda pendente bloqueia o claim.
- **Adaptador x porta**: `test_postgres_adapter_matches_the_production_run_port` compara os 11
  métodos do `Protocol` com o adaptador (presença e forma dos parâmetros: nome, kind, default).

Lacunas que permanecem explícitas (não são regressão; ficam para D2/G):

- A prova de aprovação humana versionada (R2) não existe ainda; o gate de QA não participa.
- Não há reaper de lease: a retomada depende de um worker chamar `claim_stage`.
- Não há mapeamento HTTP dos novos erros; D2/G deve mapear `InvalidIdempotencyKey` (422),
  `ProductionRunReferencedEntityNotFound` (422/404) e `ProductionRunLockTimeout` (409/retry) em vez
  de 500/503.
- O teste de relógio não simula skew entre processos; ele prova que o adaptador só lê o relógio do
  banco (comportamental + estrutural).
- `lock_timeout` não é imposto pelo adaptador; sem configuração, uma disputa espera indefinidamente
  (o `pg_advisory`/row lock do Postgres não tem timeout padrão).

## TDD — evidência real desta rodada

- **RED**: coleta falhou com `ImportError: cannot import name 'InvalidIdempotencyKey' from
  'app.studio.domain.production_run'` (testes escritos antes da implementação).
- Ciclos intermediários reais, corrigidos e revalidados (sem mascarar):
  - após o `resume` revogar o lease, `complete` do dono antigo retornava `NOT_RUNNING`; a guarda
    passou a comparar o `fencing_token` antes do estado → `LOST` (geração anterior) mantendo
    `NOT_RUNNING` para o dono atual em etapa já encerrada/pausada (exigido pelos testes de pause e
    de conclusão repetida);
  - `pause` zera o dono, então comparar dono antes do estado dava `LOST` onde o caso é
    `NOT_RUNNING`; a ordem final é token → estado → dono → estado do run → validade do lease.
- **GREEN**: 50 testes focados (`17` domínio + `33` repositório).

## Comandos e resultados (reais)

Imagem `faceless-v2-hygiene-test-local:latest` (Python 3.12.16, pytest 8.3.5), rede Docker isolada
`f1d2-net`, PostgreSQL 16-alpine descartável `f1d2-pg` (tmpfs) e prova aleatória de 64 hex montada
somente leitura em `/budget-test-proof` no banco e no runner. Worktree somente leitura,
`-p no:cacheprovider`.

```
docker run --rm --network f1d2-net \
  -v "$PWD":/workspace:ro \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro \
  -v "$PROOF_DIR":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1d2-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1d2-pg:5432/postgres \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest -q -p no:cacheprovider <alvos>
```

- `tests/test_production_run.py tests/test_production_repo.py`: **50 passed** (`7,5 s`; inclui o
  lease real de 2 s).
- `+ tests/test_db.py tests/test_architecture.py tests/test_disposable_db_guard.py`: **78 passed**.
  `test_db.py` já foi corrigido por outra fatia no worktree (lista com `0017`, `0018`, `0019`);
  **não editei** o arquivo.
- Suíte completa (árvore atual, metadata Git do worktree montada em leitura e `safe.directory` no
  processo): **1522 passed, 35 skipped, 1 warning, 0 failed**.
- Sem o mount de `.git`, `tests/test_secrets_hygiene.py` falha exatamente 2 testes
  (`test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
  `test_extracted_starter_runs_contract_snapshot_and_backup_import`) com
  “Secret hygiene check could not complete safely”: são **ambientais** (o empacotador precisa do
  metadata Git do worktree), reproduzidos isoladamente. Com o mount, passam.

### Correção da aritmética do relatório anterior

Na árvore do commit `3a7bb8d`, a suíte completa medida pela revisão deu **1359 passed, 35 skipped,
4 failed**: 2 de `tests/test_db.py` (lista de migrações sem `0018`, já corrigida por outra fatia) e
2 ambientais de `tests/test_secrets_hygiene.py`. O número anterior deste relatório
(1422 passed / 11 failed) foi medido com arquivos de outras fatias **não commitados** no worktree e
não representa a árvore do commit; fica corrigido e atribuído.

## Decisões de design (mantidas)

1. **Idempotência**: `idempotency_key UNIQUE`; `create_run` usa `INSERT ... ON CONFLICT DO NOTHING
   RETURNING`; replay devolve `EXISTING` com o mesmo `run_id`. Chave canônica divergente é
   `InvalidIdempotencyKey`; mesma chave com vídeo/canal/conjunto de estágios diferente é
   `ProductionIdempotencyConflict`.
2. **CAS**: toda escrita trava a linha do run (`FOR UPDATE`) e só então lê/escreve a etapa, na
   mesma transação. Ordem única de lock: run → etapa (inclusive no heartbeat), sem ciclo.
   `complete`/`fail` exigem dono + `fencing_token` + lease não vencido.
3. **Lease/fencing**: `claim_stage` incrementa `attempt` e `fencing_token`; etapa `RUNNING` com
   lease vencido é retomável por novo dono; o dono antigo não renova nem conclui.
   `renew_lease` exige token atual e lease válido.
4. **Checkpoint**: `complete_stage` e `fail_stage` aceitam `Checkpoint` (payload JSON + versão
   monotônica, `CHECKPOINT_REJECTED` se não avançar); sobrevive ao retry.
5. **Outbox**: `RUN_CREATED`, `RUN_STATE_CHANGED`, `STAGE_CLAIMED`, `STAGE_COMPLETED`,
   `STAGE_FAILED`, sempre na mesma transação, `event_version = 1`; `read_outbox` só não
   confirmados, em ordem de `id`; `ack_outbox` idempotente.
6. **Pausa humana**: `pause_run` grava `WAITING_HUMAN` no run e na etapa em execução, sem lease.
7. **Falha**: `fail_stage` marca etapa `FAILED`, libera lease e marca o run `FAILED` na mesma
   transação; retomar é explícito.
8. **Sucesso**: run vira `SUCCEEDED` quando todas as suas etapas estão `SUCCEEDED`/`SKIPPED`.
9. **DAG**: dependências declarativas, ordem topológica determinística, ciclo/dependência
   desconhecida/conjunto não fechado rejeitados; `STANDARD_DAG` sequencial (F1-05) e fan-out
   aceito pelo domínio e exercitado no repositório.

## Migração, rollout e rollback

- Migração **aditiva**: apenas tabelas/índices novos; nada existente muda. Código antigo ignora as
  tabelas. Rollout: aplicar a migração e depois implantar o código.
- Rollback manual (no fim de `0018`): `DROP TABLE` da outbox, das etapas e dos runs (ordem reversa
  das FKs) **e** `DELETE FROM studio.schema_migrations WHERE version = '0018_production_runs';`.
- Sem backfill e sem reescrita de dados. `channel_id` referencia `channel_profiles(id)` com
  `ON DELETE RESTRICT` (preserva a trilha).

## Limitações e riscos (explícitos)

- Sem coordenador/handlers/provedores/HTTP/UI/publicação: só estado persistido e CAS.
- Lease não expira sozinho (sem reaper); a retomada depende de `claim_stage`.
- Transições do **mesmo run** são serializadas pelo lock da linha do run (trade-off consciente;
  runs distintos em paralelo).
- Outbox simples: `ack` global (sem cursor por consumidor), sem retry/DLQ/poda; ordem por `id`.
- `resume_run` aceita `PAUSED`, mas nenhuma transição desta fatia produz `PAUSED` (reservado a D2).
- Sem mapeamento HTTP dos erros novos (D2/G); sem prova de aprovação humana (D2).
- Limites: chave ≤ 200 (canônica), `owner` ≤ 200, `reason`/`error` ≤ 2000 (motivo do run truncado),
  `lease_seconds` 1–86400, `read_outbox` 1–1000.
- Testes de PostgreSQL exigem banco descartável + prova privada; sem isso são **skipped**.
- O adaptador não define `lock_timeout`; a tradução de `55P03` só é exercitada quando o chamador
  configura um limite.

## Arquivos desta fatia

```
renderer/app/studio/domain/production_run.py                                  (novo em 3a7bb8d; corrigido em 09ea44b)
renderer/app/studio/adapters/postgres/production_repo.py                      (novo em 3a7bb8d; corrigido em 09ea44b)
renderer/app/studio/adapters/postgres/migrations/0018_production_runs.sql     (novo em 3a7bb8d; corrigido em 09ea44b)
renderer/app/studio/application/ports.py                                      (ProductionRunRepository)
tests/test_production_run.py                                                  (17 testes)
tests/test_production_repo.py                                                 (33 testes)
```

Não toquei em `composition.py`, `tests/test_db.py`, `api/`, `application/budget.py`,
`domain/channel.py`, `domain/qa_report.py`, `domain/packaging.py`, `domain/insight.py` nem em
arquivos de outras fatias. A fiação em `composition.py` continua pendente para o controlador:
`build_postgres_production_run_repository(connect, *, dag=STANDARD_DAG)`. As demais modificações
do worktree pertencem a outras sessões.