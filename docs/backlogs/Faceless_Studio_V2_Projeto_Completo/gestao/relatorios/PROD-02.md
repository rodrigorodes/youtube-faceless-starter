# PROD-02 — o gate humano é transponível: retomar/retentar **relança o worker** e o `RUNNING` órfão é recuperável

- **Branch:** `feat/prod02-rdrive-after-gate`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod02-redrive-after-gate`
- **Base:** `main` @ `77d8c88` (`docs(atividades): PROD-01 concluida (merge efd697b, re-verificada) + IA-01 em execucao`)
- **Postgres dedicado:** `integ-pg-d` (a IA-01 usa `integ-pg-c`; não houve contenção)
- **Escopo:** Relançar o worker depois de um gate humano e tornar recuperável um run `RUNNING` órfão.
  **Sem** tocar em `panel.py` (é da IA-01 em curso) e **sem** recuperação automática no boot.

## A causa raiz (diagnóstico confirmado no código)

O dono rodou uma produção (`run_id 04260fa5ed8f5fdfb4ab0b7a23d1456c`) e, depois do "Continuar"
(202 `OK` → `RUNNING`), o run **morreu parado**: nenhuma etapa com lease, todas `PENDING`, sem
erro e sem traceback. O estado no banco confirmou 20+ min depois.

- `renderer/app/studio/application/production.py`:
  - `ProductionWorker.work` (antes, linha ~690; hoje `:705`) é o laço que chama `coordinator.step`;
    o próprio docstring diz *"quando o coordenador pausa, o laço encerra e libera a thread"*.
  - `Production.start` (antes `:706`, hoje `:723`) é o **único** gatilho do worker
    (`self.submit(creation.run.run_id)`), disparado só na criação.
  - `grep -rn '\.submit(' renderer/app/studio --include=*.py | grep -v test` devolvia **só**
    `production.py:713` (`start`): nenhum endpoint relançava o worker.
- `renderer/app/studio/api/routes.py`: os endpoints `POST .../resume` (antes `:1643`) e
  `.../retry` (antes `:1654`) chamavam `production_service(uc).coordinator.resume(...)` /
  `.coordinator.retry(...)` **direto** e **nunca** o `submit`.
- Wiring em `composition.py:598-600`: `worker = ProductionWorker(coordinator)` …
  `submit=lambda run_id: self._executor.submit(worker.work, run_id)` (ThreadPoolExecutor in-process).

**Consequência:** no modo `INTERACTIVE` (o do dono) o gate após o roteiro dispara **sempre**, então
**nenhum run passava do primeiro gate**: "Continuar" devolvia 200, o estado virava `RUNNING` e
nenhuma etapa era executada. O **"Tentar novamente"** (PROD-01, merge `efd697b`) tinha o mesmo
defeito — só trocava o estado. Como não havia varredor/reaper de run órfão e o `lifespan` do app
(`renderer/app/main.py`) não recupera runs em voo, **reiniciar o app também não destravava**.

## O que mudou (antes → depois)

### A) O serviço `Production` relança o worker

`renderer/app/studio/application/production.py` — `Production` (hoje `:716`) passou a expor:

- `resume(run_id, *, expected_state=None) -> RunTransition` (`:729`): chama o coordenador **como
  hoje** e, **somente quando a transição é `APPLIED`**, chama `submit(run_id)`; depois, se a
  transição foi recusada, tenta o **re-drive** do `RUNNING` órfão (item B).
- `retry(run_id) -> RunTransition` (`:746`): mantém `expected_state=RunState.FAILED` e também
  relança o worker quando `APPLIED`.
- `_enqueue(run_id)` (`:766`): o gatilho com a **mesma** tolerância de `start` — `submit is None`
  não faz nada; qualquer exceção vira `logger.warning` ("fila indisponível não pode perder o run").
  `start` foi refatorado para usar o mesmo helper (semântica idêntica).

`renderer/app/studio/api/routes.py`:

- `/resume` (`:1644`) e `/retry` (`:1666`) passam a chamar **`production_service(uc).resume(...)`**
  e **`.retry(...)`**, não o coordenador direto.
- Semântica de erro preservada: `NOT_ALLOWED` → **409** e **nada é submetido** (o `submit` só
  ocorre no caminho `APPLIED`/re-drive).

**Antes:** `coordinator.resume(run_id)` trocava `WAITING_HUMAN → RUNNING` e o laço nunca mais rodava.
**Depois:** a transição `APPLIED` chama o executor (`self._executor.submit(worker.work, run_id)`),
a etapa seguinte sai de `PENDING` e o run avança.

### B) `RUNNING` órfão é recuperável (o run morto do dono)

- **Predicado puro na aplicação:** `has_live_lease(stages, now)` (`production.py:476`) — verdadeiro
  se **alguma** etapa tem `lease_owner` **e** `lease_expires_at` **estritamente no futuro**. Lease
  ausente ou expirado (inclusive `expires == now`) **não** conta: o dono anterior já não pode
  escrever, logo o run está órfão. Não há I/O nem relógio implícito — `now` é parâmetro.
- **Re-drive sem escrever estado:** `Production._orphan_running(run_id)` (`:753`) lê a projeção do
  coordenador; se o run é `RUNNING` **e** `has_live_lease(...)` é falso, devolve
  `RunTransition(APPLIED, run)` — e o `resume` chama `submit`. Com lease vivo devolve `None`, e o
  `NOT_ALLOWED` original é preservado → **409**, sem worker duplicado.
- **Página de execução** (`renderer/app/studio/api/panel_production.py`):
  - `available_actions(state, next_action, *, live_lease=True)` (`:238`): em `RUNNING` sem lease
    vivo oferece **"Continuar"** (primária) **além** de "Pausar"; com lease vivo permanece **só
    "Pausar"**. O default `live_lease=True` é conservador (nunca oferece continuação sem prova).
  - `_rail_actions_html` (`:616`) calcula `has_live_lease(view.stages, view.now)` a partir da
    própria `ExecutionView` (que já carrega `StageExecution` com lease e `now`).
  - O botão "Continuar" posta em `POST /studio/videos/{video}/production-runs/{run}/resume` (mesmo
    JS `data-run-action`), então cai no caminho novo.
- **Adapter intacto:** `_RESUMABLE_RUN_STATES` (`adapters/postgres/production_repo.py:60`) continua
  recusando `RUNNING` para escrita — o re-drive **não** passa por ele (não escreve estado).

## O teste que teria pegado o bug

`tests/test_production_coordinator.py::test_gate_after_script_is_crossed_when_the_service_resumes`
(Postgres real + `_StubHandler`, sem rede): cria o run pelo **serviço** (submit roda o worker de
verdade), confirma `WAITING_HUMAN` com `factcheck PENDING`, e chama `service.resume(run_id)`.
Assere `APPLIED` **e** `factcheck == SUCCEEDED` **e** run `SUCCEEDED`.

**Prova de que pega o bug:** simulando o defeito antigo (removendo o `self._enqueue(run_id)` do
caminho `APPLIED`), o teste falha exatamente no sintoma do dono:

```
tests/test_production_coordinator.py:187: in test_gate_after_script_is_crossed_when_the_service_resumes
    assert _stages(conn, run_id)["factcheck"] == StageState.SUCCEEDED.value
E   AssertionError: assert 'PENDING' == 'SUCCEEDED'
```

## Testes (o que rodou)

Novos:

- `tests/test_production_service.py` (novo, unitário, sem banco):
  - **spy no `submit`**: `resume` de `WAITING_HUMAN` → `submit` chamado **com o `run_id`**;
    `resume` `NOT_ALLOWED` → **não** chamado; `retry` `APPLIED` → chamado (com `expected_state=FAILED`);
    `retry` `NOT_ALLOWED` → não chamado; `submit` que levanta exceção é tolerado (transição mantida).
  - **re-drive**: `RUNNING` sem lease vivo → `APPLIED` e `submit`; `RUNNING` com lease vivo →
    `NOT_ALLOWED` e **sem** submit; run não-`RUNNING` → sem re-drive.
  - **`has_live_lease`**: vazio/ausente/expirado → falso; limite `expires == now` → falso;
    `now + 1s` → verdadeiro; uma etapa viva no meio de pendentes → verdadeiro.
- `tests/test_production_coordinator.py`: `test_gate_after_script_is_crossed_when_the_service_resumes`
  e `test_orphan_running_with_an_expired_lease_is_recovered_by_the_service` (o órfão é simulado com
  `lease_expires_at = statement_timestamp() - interval '1 minute'`, e o `resume` o recupera).
- `tests/test_panel_production_render.py`: `test_orphan_running_offers_continue_to_relaunch_the_worker`
  (RUNNING órfão → "Continuar" presente; ordem `resume/pause/cancel`). Ajuste determinístico: o
  `_execution_view` agora fixa `now=NOW` (antes usava o relógio real e a lease fixa do fixture
  "expirava", mudando a UF sem intenção). O caso com lease vivo continua exigindo **só** "Pausar".
- `tests/test_production_api.py`: o dublê `_Production` ganhou `resume`/`retry` (as rotas agora
  chamam o serviço); os casos de 409/200 seguem iguais.

Nada existia com o nome `tests/test_production_worker.py` — o laço do worker é coberto por
`tests/test_production_coordinator.py` (que importa `ProductionWorker`), e é lá que o teste de
integração entrou.

### Comando e resultado

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod02-redrive-after-gate
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-d:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-d:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_production_service.py tests/test_production_api.py tests/test_production_coordinator.py \
  tests/test_panel_production_page.py tests/test_panel_production_render.py tests/test_architecture.py tests/test_composition.py
```

**104 passed, 1 warning** (Postgres dedicado `integ-pg-d`). Sem contenção de schema. `test_architecture.py`
verde: `domain`/`application` puros, wiring só em `composition.py`, executor/thread não vaza para o
coordenador (segue o padrão do `submit` injetado).

## O que mudou (por arquivo)

| Arquivo | Mudança |
| --- | --- |
| `renderer/app/studio/application/production.py` | `has_live_lease` (puro); `Production.resume`/`retry` que relançam o worker em `APPLIED`; `_orphan_running` (re-drive sem escrever estado); `_enqueue` com a tolerância do `start` (que passa a usá-lo). |
| `renderer/app/studio/api/routes.py` | `/resume` e `/retry` passam a chamar `Production.resume`/`.retry` (não o coordenador direto); `NOT_ALLOWED → 409` preservado. |
| `renderer/app/studio/api/panel_production.py` | `available_actions(..., live_lease=)`; `_rail_actions_html` calcula o lease vivo da projeção e oferece "Continuar" ao `RUNNING` órfão. |
| `tests/test_production_service.py` | **Novo**: spy no `submit`, re-drive e `has_live_lease` (sem banco). |
| `tests/test_production_coordinator.py` | +2 integrações: o gate transposto pelo serviço e a recuperação do `RUNNING` órfão. |
| `tests/test_panel_production_render.py` | +1 teste de órfão; `now=NOW` determinístico no `_execution_view`. |
| `tests/test_production_api.py` | Dublê `_Production` ganhou `resume`/`retry`. |

## Escopo respeitado / não feito

- **`renderer/app/studio/api/panel.py` não foi alterado** (é da IA-01 em curso) — o ajuste de
  página ficou só em `panel_production.py`.
- **Não** implementei recuperação automática de runs órfãos no boot (`lifespan`/`main.py`); fica
  como item aberto do dono, conforme o pedido. O "Continuar" do painel resolve o caso atual.
- **Não** alterei a máquina de estados do domínio (`domain/production_run.py`) nem `_RESUMABLE_RUN_STATES`:
  o re-drive **não escreve estado**, então não precisou de nova transição.
- **Não** toquei `docker-compose.yml`, allowlist nem telas de Estilos/Conexões/Canais.
- Sem `git add -A` (caminhos exatos), sem push/merge; não rodei a suíte inteira.
- Não foi possível rodar local (fora do Docker): o env do host está sem `numpy` (imports do painel) e
  com `httpx` incompatível com o `TestClient` — os testes rodaram no harness de container, como pedido.
