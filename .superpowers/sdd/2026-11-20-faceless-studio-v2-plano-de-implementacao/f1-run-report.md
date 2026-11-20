# F1 — execução persistida: ProductionRun, lease/fencing e outbox (fatia D1)

- Implementação: **`3a7bb8d`** — domínio, repositório, migração `0018` e porta.
- Correção da revisão (round 1): **`09ea44b`** — chave canônica, tradução de erros, revogação de
  leases no resume, `expected_state`, índices mortos e rollback.
- Correção da reverificação (round 2, final): **`34cc9c5`** — whitelist ASCII da chave de
  idempotência com CHECK no banco, eventos `stage.revoked`, redação corrigida.

A fatia entrega a espinha dorsal **persistida** da execução; **não** implementa coordenador,
handlers, provedores, HTTP/UI nem publicação. A reverificação aceitou R1/R2/S2/M com sondas reais
(CAS/fencing/outbox/lease: 10/10 disputas com um único `CLAIMED`; lease real expirando com o dono
antigo sem escrever; outbox atômica por gatilho de rollback; ordenação por run; DAG 200/200 ciclos
e 400 DAGs sem violação). Esta rodada fecha o furo de Unicode na chave, corrige a redação e
adiciona observabilidade de revogação.

## Rodada final (round 2)

### 1. Furo real — Unicode na `idempotency_key`

**Problema medido:** `café-42` (NFC) e `cafe\u0301-42` (NFD) criavam runs distintos; VS16
(`\uFE0F`) e CGJ (`\u034F`) são categoria `Mn` e passavam; fullwidth, en dash e homóglifo cirílico
também passavam. O filtro anterior (`Cc/Cf/Cs/Zl/Zp` + `casefold`) não cobria marcas nem
normalização.

**Decisão: whitelist ASCII fechada.** A chave canônica é exatamente
`[a-z0-9._:-]+`, até 200 caracteres. Nada é normalizado; variante é recusada com
`InvalidIdempotencyKey`. Justificativa:

- uma **blacklist Unicode é interminável** (marcas `Mn/Mc/Me`, controles, formatos, separadores,
  confusáveis, formatação bidi, novas categorias em versões futuras). A whitelist é finita,
  auditável e **subsume (a), (b) e (c)** do pedido: ASCII não tem marcas (`Mn/Mc/Me`), é sua própria
  forma **NFC** (portanto NFC e NFD divergentes não coexistem), é minúsculo por construção e não
  admite fullwidth nem homóglifos;
- a chave é um identificador opaco de protocolo, não texto humano: restringir o alfabeto não perde
  informação útil e elimina ambiguidade de caixa/normalização/confusão visual;
- não há clientes em produção nesta fatia; clientes futuros devem enviar a chave já canônica
  (UUID/hex minúsculo e `a-z0-9._:-` são aceitos).

Aceitos: `order-42`, `a.b_c:d`, hex de 32, até 200 caracteres. Recusados e testados: `ORDER-42`,
`Order-42`, `order-42 `, ` order-42`, `order 42`, tab, `café-42` (NFC), `cafe\u0301-42` (NFD),
`order-\uFE0F-42` (VS16), `order-\u034F-42` (CGJ), `ｏｒｄｅｒ-42` (fullwidth), `order\u201342`
(en dash), `оrder-42` (cirílico), `straße-42`, `ﬁle-42`, `ς-42`, `""`, > 200, não-string.

**Defesa em profundidade no banco** (`0018`): a coluna agora repete a regra —

```
idempotency_key text NOT NULL UNIQUE
    CHECK (length(idempotency_key) BETWEEN 1 AND 200 AND idempotency_key ~ '^[a-z0-9._:-]+$')
```

O regex ASCII minúsculo implica `lower(key) = key`, ausência de espaço/controle/invisível e NFC; não
é necessário `normalize()`. Um `INSERT` direto com `ORDER-99`, NFC/NFD, VS16, fullwidth, en dash,
cirílico ou espaço é recusado por `CheckViolation` (testado). Isso fecha o caminho que antes gravava
`'ORDER-99'` e quebrava `get_run` na leitura (`InvalidIdempotencyKey` no construtor da entidade).

### 2. Redação corrigida

- O relatório/porta/migração não dizem mais "sem invisível": a regra real é **ASCII canônico
  `[a-z0-9._:-]`** (a whitelist cobre também invisíveis, marcas, NFC/NFD, fullwidth e homóglifos).
- **`LOST` x `NOT_RUNNING`:** `resume_run` incrementa o token apenas das etapas `WAITING_HUMAN`/
  `RUNNING`; para essas, o dono antigo recebe `LOST` (mesmo que a etapa já esteja `PENDING`). Uma
  etapa que saiu de `RUNNING` **sem** revogação — por exemplo `FAILED` intocada num resume de run
  `FAILED`, ou etapa pausada/cancelada — mantém o token e devolve **`NOT_RUNNING`** ao dono antigo
  (e nada é escrito). A afirmação anterior de que "a geração anterior sempre recebe `LOST`" estava
  imprecisa e foi corrigida aqui e nos docstrings.
- **`casefold`:** a mensagem anterior recusava `straße`, `ς` e `ﬁ` como "variantes de caixa" embora
  já fossem minúsculas. Com a whitelist ASCII, a recusa é por **forma canônica** e a mensagem é
  exata ("must be canonical lowercase ASCII in [a-z0-9._:-]"); `straße` é testado e a mensagem não
  menciona caixa/casefold.

### 3. Observabilidade — evento por etapa revogada

Novo `ProgressEventType.STAGE_REVOKED = "production.stage.revoked"` (payload: `run_id`,
`stage_id`, `from`, `to = "PENDING"`, `attempt`, `fencing_token` novo). `resume_run` agora seleciona
as etapas `WAITING_HUMAN`/`RUNNING` (`ORDER BY stage_id ... FOR UPDATE`), revoga uma a uma e emite um
evento **por etapa na mesma transação**, antes do `run.state_changed`. Assim consumidores sabem
exatamente quais etapas voltaram a `PENDING`.

Testes: `resume` de run `FAILED` com irmão `RUNNING` (fan-out) emite exatamente um `stage.revoked`
(`from RUNNING`, token 2) antes do evento do run; `pause` → `resume` emite `stage.revoked`
(`from WAITING_HUMAN`, token 2); e um gatilho que rejeita `stage.revoked` prova que a revogação, o
run e os eventos são uma transação só (run e etapa continuam `WAITING_HUMAN`, token inalterado).

### 4. Limite documentado (não corrigido)

`40P01` (deadlock detected) e `57014` (`statement_timeout`/query canceled) também herdam
`OperationalError` e, nesta fatia, caem em `ServiceUnavailable` (503). Não há ciclo de lock no
desenho atual (ordem única run → etapa), então não há deadlock esperado; D2 (ou qualquer aumento de
paralelismo/mais workers) deve revisitar a tradução e mapear deadlock/timeout para conflito/retry,
como já é feito para `55P03` (`ProductionRunLockTimeout`).

## Rodada anterior (round 1), mantida

- S2(a): `ForeignKeyViolation` em `create_run` → `ProductionRunReferencedEntityNotFound`.
- S2(b): `LockNotAvailable` (55P03) → `ProductionRunLockTimeout` (não `ServiceUnavailable`); o
  adaptador **não impõe** `lock_timeout` (limite; ver abaixo).
- R1: `resume_run` revoga leases de `WAITING_HUMAN`/`RUNNING`, zera lease e incrementa o token.
- R2: `resume_run(run_id, expected_state)` recusa estado divergente sem escrever. **A prova de
  aprovação humana versionada é D2**, com ponto de integração nomeado: gate de
  `domain/qa_report.py` no checkpoint da etapa `approval`.
- M: índices mortos removidos (`production_runs_video_idx`, `stage_executions_active_lease_idx`);
  `production_outbox_unacked_idx` permanece (a consulta usa). Rollback inclui
  `DELETE FROM studio.schema_migrations WHERE version = '0018_production_runs';`.

## Design (contrato)

1. **Idempotência**: `idempotency_key UNIQUE` canônica; `INSERT ... ON CONFLICT DO NOTHING
   RETURNING`; replay devolve `EXISTING`; mesma chave com pedido diferente →
   `ProductionIdempotencyConflict`.
2. **CAS**: toda escrita trava a linha do run (`FOR UPDATE`) antes das etapas, na mesma transação;
   `complete`/`fail` exigem dono + token + lease válido. Ordem única de lock (run → etapa).
3. **Lease/fencing**: claim incrementa `attempt` e `fencing_token`; etapa órfã (lease vencido) é
   retomável por novo dono; o dono antigo não renova nem conclui.
4. **Checkpoint** monotônico em `complete`/`fail`; sobrevive ao retry.
5. **Outbox** na mesma transação: `run.created`, `run.state_changed`, `stage.claimed`,
   `stage.completed`, `stage.failed`, `stage.revoked`; `event_version = 1`; `read_outbox` só não
   confirmados, por `id`; `ack` idempotente.
6. **Pausa humana**: `WAITING_HUMAN` no run e na etapa, sem lease — worker livre.
7. **Falha**: etapa `FAILED` + run `FAILED` na mesma transação; retomada explícita.
8. **Sucesso**: run `SUCCEEDED` quando todas as suas etapas estão `SUCCEEDED`/`SKIPPED`.
9. **DAG**: dependências declarativas, ordem topológica determinística; ciclo, dependência
   desconhecida e conjunto não fechado rejeitados; `STANDARD_DAG` sequencial e fan-out exercitado.

## TDD — evidência real (rodada final)

- **RED**: 7 falhas com os testes escritos antes do código — `ProgressEventType.STAGE_REVOKED`
  inexistente, chave Unicode aceita, `CHECK` do banco ausente (insert direto passava), eventos
  `stage.revoked` ausentes e o gatilho de atomicidade do resume sem o que rejeitar.
- **GREEN**: 56 testes focados (`18` domínio + `38` repositório).
- Ciclos anteriores (round 1): guarda de escrita passou a comparar token → estado → dono para
  distinguir `LOST` (token revogado) de `NOT_RUNNING` (token atual em etapa já encerrada/pausada).

## Validação (real)

Imagem `faceless-v2-hygiene-test-local:latest` (Python 3.12.16, pytest 8.3.5), rede Docker isolada
`f1d3-net`, PostgreSQL 16-alpine descartável `f1d3-pg` (tmpfs) e prova aleatória de 64 hex montada
somente leitura em `/budget-test-proof` no banco e no runner. Worktree somente leitura,
`-p no:cacheprovider`.

```
docker run --rm --network f1d3-net \
  -v "$PWD":/workspace:ro \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro \
  -v "$PROOF_DIR":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1d3-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1d3-pg:5432/postgres \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest -q -p no:cacheprovider <alvos>
```

- Focados: **56 passed** (`8,4 s`).
- `+ tests/test_db.py tests/test_architecture.py tests/test_disposable_db_guard.py`: **84 passed**.
  `tests/test_db.py` já contém `0018`/`0019` (corrigido por outra fatia); não editei o arquivo.
- Suíte completa (árvore atual, metadata Git montada e `safe.directory`): **1528 passed, 35 skipped,
  1 warning, 0 failed**.
- **2 falhas ambientais de `test_secrets_hygiene`** fora da suíte completa: sem o mount de `.git`,
  `test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
  `test_extracted_starter_runs_contract_snapshot_and_backup_import` falham com “Secret hygiene check
  could not complete safely” (o empacotador precisa do metadata Git). Reproduzidas isoladamente
  (2 failed / 30 passed sem mount; passam com o mount).

Registro histórico corrigido: na árvore de `3a7bb8d` a revisão mediu **1359 passed / 35 skipped /
4 failed** (2 de `test_db`, já corrigidos por outra fatia, + 2 ambientais de `test_secrets_hygiene`).

## Migração, rollout e rollback

- Aditiva: só tabelas/índices novos; código antigo ignora. Aplicar a migração e depois o código.
- Rollback manual (fim de `0018`): `DROP TABLE production_outbox`, `stage_executions`,
  `production_runs` (ordem reversa das FKs) e
  `DELETE FROM studio.schema_migrations WHERE version = '0018_production_runs';`.
- Migração editada in place nas rodadas de revisão (ainda não liberada); sem backfill.
- `channel_id` referencia `channel_profiles(id)` com `ON DELETE RESTRICT` (preserva a trilha).

## Cobertura e limites

Fechadas: relógio do banco (lease real de 2 s + teste estrutural que proíbe relógio do processo),
outbox atômica em 7 caminhos (create, claim, fail, complete, pause, cancel e revogação no resume),
fan-out no repositório, confronto adaptador x `Protocol` (11 métodos) e CHECK canônico no banco.

Limites explícitos (não corrigidos nesta fatia; o que resta vira limitação documentada):

- **Sem coordenador/handlers/provedores/HTTP/UI/publicação**: só estado persistido e CAS.
- **Sem reaper de lease**: a retomada depende de um worker chamar `claim_stage`.
- **Sem prova de aprovação humana**: `resume_run` aceita só `expected_state`; o gate de QA
  versionado entra em D2 (ponto nomeado: checkpoint da etapa `approval`).
- **Transições do mesmo run serializadas** pelo lock da linha do run (trade-off; runs distintos em
  paralelo).
- **Outbox simples**: `ack` global (sem cursor por consumidor), sem retry/DLQ/poda; ordem por `id`.
- **Erros sem mapeamento HTTP**: D2/G deve mapear `InvalidIdempotencyKey` (422),
  `ProductionRunReferencedEntityNotFound` (422/404) e `ProductionRunLockTimeout` (409/retry).
  `40P01`/`57014` continuam caindo em `ServiceUnavailable` (ver item 4).
- **`lock_timeout` não é imposto** pelo adaptador; sem configuração, uma disputa espera.
- **Whitelist ASCII é deliberadamente estrita**: chaves não-ASCII (mesmo legíveis) são recusadas;
  clientes futuros devem enviar `[a-z0-9._:-]`. `PAUSED` existe no domínio mas não é produzido aqui.
- Limites de tamanho: chave ≤ 200, `owner` ≤ 200, `reason`/`error` ≤ 2000, `lease_seconds` 1–86400,
  `read_outbox` 1–1000.
- Testes de PostgreSQL exigem banco descartável + prova privada; sem isso são **skipped**.

## Arquivos desta fatia

```
renderer/app/studio/domain/production_run.py                                  (domínio; rounds 1-2)
renderer/app/studio/adapters/postgres/production_repo.py                      (adaptador; rounds 1-2)
renderer/app/studio/adapters/postgres/migrations/0018_production_runs.sql     (migração; rounds 1-2)
renderer/app/studio/application/ports.py                                      (ProductionRunRepository)
tests/test_production_run.py                                                  (18 testes)
tests/test_production_repo.py                                                 (38 testes)
```

Não toquei em `composition.py`, `tests/test_db.py`, `api/`, `application/budget.py` nem em
`domain/{channel,qa_report,packaging,insight}.py` ou arquivos de outras fatias. A fiação em
`composition.py` segue pendente para o controlador:
`build_postgres_production_run_repository(connect, *, dag=STANDARD_DAG)`. **Não afirmo F1
concluído.**