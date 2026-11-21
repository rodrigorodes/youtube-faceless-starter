# PROD-03 — o boot religa a produção: runs em voo órfãos são re-dirigidos automaticamente

- **Branch:** `feat/prod03-boot-recovery`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod03-boot-recovery`
- **Base:** `main` @ `8de68c1` (`docs(atividades): IA-01 concluida (merge 1b98ddd, verificada ao vivo); PROD-03 e PROD-04 em execucao; achado 5 absorvido no PROD-04`)
- **Postgres dedicado:** `integ-pg-d` (o PROD-04 usa o `integ-pg-c`; não houve contenção)
- **Escopo:** no boot do app, re-dirigir os runs de produção **em voo** que ficaram **órfãos**. Porta
  de leitura + regra pura + gatilho no serviço + chamada no `lifespan`. **Sem** tocar em
  `panel.py`, `application/panel.py` nem no repositório de tendências (são do PROD-04).

## A causa (diagnóstico já confirmado, herdado do PROD-02)

Uma produção é dirigida por um laço **em processo**: `ProductionWorker.work` (o próprio docstring
diz *"quando o coordenador pausa, o laço encerra e libera a thread"*), lançado por
`Production.submit` → `composition.py` (`ThreadPoolExecutor`). Não existe varredor/reaper de run de
produção — `grep -rniE 'sweep|reap|recover|orphan|stale' renderer/app/studio --include=*.py | grep -v test`
só encontra o fluxo de `render_jobs`, que é outro. E o `lifespan` (`renderer/app/main.py`) só
migrava o schema e fazia `shutdown`: **não varria nada**.

Consequência: um deploy/queda no meio de uma produção **abandonava** o run. O `PROD-02` (merge
`59c32da`) entregou a recuperação **manual** — `Production.resume/retry` relançam o worker e um
`RUNNING` sem lease vivo é recuperável pela tela — mas **nada sobrevivia a um restart**.

## O que mudou (antes → depois)

### 1) Porta: `list_in_flight()` (leitura dos runs em voo com suas etapas)

- `renderer/app/studio/application/ports.py`: novo Protocol **`ProductionRunInFlightReader`** com
  `list_in_flight() -> tuple[tuple[ProductionRun, tuple[StageExecution, ...]], ...]`. Porta de
  **leitura** separada da porta de escrita; o mesmo repositório satisfaz as duas. Cada run vem com
  as suas etapas na **mesma leitura**, para a subida não pagar N+1.
- `renderer/app/studio/adapters/postgres/production_repo.py`: `PostgresProductionRunRepository.list_in_flight()`
  — **duas queries no total** (runs `CREATED`/`RUNNING` e as etapas de todos eles, `WHERE run_id = ANY(...)`).
  Ordem estável (mais antigos primeiro, desempate por `run_id`; etapas na ordem topológica do DAG).
  Estados terminais nunca aparecem.

### 2) Regra pura: `orphan_in_flight(in_flight, now)`

`renderer/app/studio/application/production.py` (ao lado de `has_live_lease`, que **reusa**):

- Recebe `(run, stages)` e `now` e devolve os `run_id` **órfãos** — **sem I/O**, `now` é parâmetro:
  - `CREATED` → órfão (nunca passou pelo `submit`; ex.: fila indisponível no `start`).
  - `RUNNING` → órfão **somente** se `has_live_lease(stages, now)` é falso (nenhuma etapa com lease
    vivo). Com lease vivo o dono ainda pode escrever; re-dirigir ficaria de fora.
  - Qualquer outro estado (`FAILED`/`SUCCEEDED`/`CANCELLED`/`WAITING_HUMAN`/`PAUSED`) **nunca** entra,
    mesmo que a leitura os traga: recuperar não é retomar nem retentar.

### 3) Gatilho no serviço: `Production.recover_in_flight(now=None)`

`Production` ganhou o campo injetado `in_flight: ProductionRunInFlightReader | None = None` e o
método `recover_in_flight`, que lê pela porta, filtra pelos `orphan_in_flight` e chama o **mesmo
`submit` do `start`** para cada órfão (nenhum caminho novo de execução). É **idempotente** e
**não escreve estado**: só relança o worker. Sem porta é no-op; falha de um `submit` não impede os
outros nem propaga (`_enqueue`, a tolerância de fila que o `start`/`resume` já usavam).

`renderer/app/studio/composition.py`: a fiação passa `in_flight=run_repo` ao `Production` e o
`Studio` ganhou `recover_in_flight()`, que delega ao serviço (sem banco/sem produção → vazio).

### 4) Boot: `lifespan` chama a recuperação em thread

`renderer/app/main.py`, **depois** da migração:

```python
await asyncio.to_thread(studio.use_cases)          # migra o schema; falha não derruba o app
try:
    recovered = await asyncio.to_thread(studio.recover_in_flight)
    if recovered:
        logger.warning("production: %d run(s) em voo orfao(s) re-dirigido(s) no boot", len(recovered))
except Exception:                                  # banco indisponível/erro: no-op, nunca derruba
    logger.warning("production: recuperacao de runs em voo indisponivel no boot", exc_info=True)
```

Regras atendidas: em `asyncio.to_thread` (não bloqueia a subida), `try/except` + `logger.warning`
(o app **sobe** mesmo com a varredura falhando), banco indisponível = no-op (`Studio.use_cases()`
devolve `None` e `recover_in_flight` devolve vazio) e idempotente (rodar duas vezes não faz mal).

## A limitação real: duas instâncias re-dirigem os órfãos que cada uma vê

Com **duas instâncias** do app no mesmo banco, cada `lifespan` varre os runs em voo e re-dirige os
órfãos que vê por inteiro: **sem coordenação entre instâncias**, o mesmo `run_id` pode ser
submetido nas duas. Não há duas execuções da mesma etapa — `claim_stage` reivindica a etapa
**atomicamente com lease/fencing** e o perdedor recebe `BUSY`/`LOST` — mas **há workers ociosos**
(um deles fica girando sem nada que reivindicar até encerrar o laço). A recuperação é um *best
effort* de subida, não uma eleição de líder. Resolver isso exigiria um lock de partição/single-flight
por run (fora do escopo: "não implementar heartbeat/timeout de lease novo").

## Testes (o que rodou)

- **Puro** (`tests/test_production_service.py`):
  - `orphan_in_flight`: `RUNNING` com lease vivo (futuro) **não** entra; lease expirado entra;
    **limite** `expires == now` entra (mesma semântica de `has_live_lease`); lease ausente
    (etapas `PENDING`) entra; `CREATED` entra; `FAILED`/`SUCCEEDED`/`CANCELLED` **não** entram;
    ordem preservada.
- **Serviço** (`tests/test_production_service.py`): com dublês, só os órfãos são submetidos (com o
  `run_id`), os não-órfãos **não**; exceção de um `submit` não impede o outro nem propaga; sem porta
  é no-op.
- **Boot** (`tests/test_main_boot.py`, que já existia): com studio dublê o `lifespan` chama a
  recuperação (com órfão), não quebra sem runs e **sobe mesmo quando a recuperação levanta**.
- **Integração (Postgres dedicado)** (`tests/test_production_coordinator.py`, handlers-stub, sem rede):
  - `test_list_in_flight_returns_only_active_runs_with_their_stages`: cria um run e confirma que a
    leitura traz o run com **todas** as etapas; um `SUCCEEDED` sai da leitura.
  - `test_boot_recovery_redrives_a_running_run_left_without_any_lease`: insere um run **`RUNNING`
    sem lease** (thread morta), chama `service.recover_in_flight()` e prova que o run **avança** —
    o `script` sai de `PENDING` para `SUCCEEDED`. **É a prova de que o deploy não abandona mais a
    produção.**
  - `test_boot_recovery_is_idempotent_and_skips_a_run_with_a_live_lease`: `WAITING_HUMAN` não está
    em voo; `RUNNING` com lease vivo não é re-dirigido; repetir não faz mal.

### Falsificação

Sob o defeito (curto-circuitando `recover_in_flight` para devolver `()` antes de ler), o teste de
integração falha exatamente no ponto:

```
tests/test_production_coordinator.py:399: AssertionError: assert () == ('6ae9666a637...cc710ba03c9',)
```

### Comando e resultado

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod03-boot-recovery
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-d:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-d:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_production_service.py tests/test_production_api.py tests/test_production_coordinator.py \
  tests/test_main_boot.py tests/test_architecture.py tests/test_composition.py \
  tests/test_production_repo.py tests/test_production_flow_db.py tests/test_production_run.py \
  tests/test_production_handlers.py
```

**158 passed, 1 warning** (Postgres dedicado `integ-pg-d`; sem contenção). `test_architecture.py`
verde: `domain`/`application` puros e a fiação só em `composition.py` (a regra pura importa apenas
`Iterable`; a leitura mora no adaptador e no Protocol de `application/ports.py`).

## O que mudou (por arquivo)

| Arquivo | Mudança |
| --- | --- |
| `renderer/app/studio/application/ports.py` | Protocol `ProductionRunInFlightReader.list_in_flight()`. |
| `renderer/app/studio/adapters/postgres/production_repo.py` | `list_in_flight()` (2 queries, runs `CREATED`/`RUNNING` + etapas). |
| `renderer/app/studio/application/production.py` | Regra pura `orphan_in_flight`; campo `in_flight` e `Production.recover_in_flight()`. |
| `renderer/app/studio/composition.py` | Fiação `in_flight=run_repo`; `Studio.recover_in_flight()`. |
| `renderer/app/main.py` | `lifespan` chama a recuperação em thread, depois da migração, com `try/except`+`logger.warning`. |
| `tests/test_production_service.py` | Regra pura + serviço (spy no submit, órfãos vs. não-órfãos, falha isolada, no-op). |
| `tests/test_production_coordinator.py` | +3 integrações: `list_in_flight`, recuperação que avança o run, idempotência/lease vivo. |
| `tests/test_main_boot.py` | +3 testes de `lifespan` com studio dublê (órfão, sem runs, exceção). |
| `tests/test_composition.py` | `Studio.recover_in_flight()` é no-op sem banco. |

## Escopo respeitado / o que **não** foi feito

- **Não** toquei `renderer/app/studio/api/panel.py`, `application/panel.py` nem o repositório de
  tendências (são do PROD-04, que roda em paralelo).
- **Não** implementei heartbeat/timeout de lease novo nem mudei a máquina de estados do domínio:
  a recuperação **não escreve estado**, só relança o worker pelo `submit` existente. Um run
  `CREATED` passa a `RUNNING` naturalmente no primeiro `claim_stage`.
- **Não** implementei eleição de líder / single-flight entre instâncias (a limitação acima fica
  documentada, não "resolvida").
- **Não** toquei `docker-compose.yml` nem `render_jobs`.
- Sem `git add -A` (caminhos exatos), sem push/merge; não rodei a suíte inteira.
- Limitação de verificação: os testes rodaram no harness de container (o env do host não tem todas
  as dependências do painel); não exercitei a varredura contra um Postgres real do app em execução —
  a prova de avanço é a integração com handlers-stub no banco descartável.
