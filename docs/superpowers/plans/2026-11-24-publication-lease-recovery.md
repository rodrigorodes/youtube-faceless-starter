# Contingência de Publicação, Heartbeat de Lease e Recuperação Periódica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os três achados P1 do review de arquitetura: (R01) o interruptor de contingência da publicação chega ao container pelo Compose; (R02) o worker renova o lease de 300 s enquanto a etapa roda, sem ressuscitar lease expirado nem deixar um worker obsoleto escrever; (R03) runs órfãos são recuperados periodicamente, não só no boot, sem duplicar efeitos externos (upload).

**Architecture:** Nenhuma fila, broker ou scheduler novo. R01 é encaminhamento de variável no Compose com default seguro. R02 reaproveita o `renew_lease` já existente em `PostgresProductionRunRepository` (CAS por dono + `fencing_token` + lease vivo, relógio do banco) e acrescenta só o consumidor: uma thread de heartbeat por etapa reivindicada, fora do pool de render. R03 reaproveita `recover_in_flight`/`orphan_in_flight`/`_enqueue` e o claim com fencing (`claim_stage`): acrescenta um laço no `lifespan`, uma consulta SQL limitada de candidatos e uma guarda contra re-despacho de runs já ativos no processo. Como R02/R03 tornam o re-claim de uma etapa `publish` mais frequente, um passo de reconciliação no `PublishHandler` impede que o re-claim reenvie um vídeo cujo resultado remoto é ambíguo.

**Tech Stack:** Python 3.12 (imagem do renderer; o host local é 3.11 e **não** é ambiente de teste válido para DB), FastAPI/lifespan, `threading`, psycopg 3 (PostgreSQL 16), pytest, Docker Compose.

**Spec:** não há spec separada. Fonte dos requisitos: `docs/reviews/2026-11-24-architecture-review.md` (R01, R02, R03) + seção *Decisões do plano* abaixo. Contexto de arquitetura: `docs/11-arquitetura-operacional.md`, `docs/04-variaveis-de-ambiente.md`.

## Fatos confirmados no código (2026-11-24, `main` @ `2beb90e`)

| # | Fato | Evidência |
|---|------|-----------|
| F1 | `Settings.from_env` lê `STUDIO_PUBLICATION_ENABLED` com default `"1"`; `_flag("")` é **falso** (só `1/true/yes/on` ligam). Chave presente porém vazia **desliga** a publicação. | `renderer/app/studio/composition/settings.py:27-28, 89`; `renderer/app/studio/composition/wiring.py:630-632` |
| F2 | O Compose do `renderer` não declara `STUDIO_PUBLICATION_ENABLED`. | `docker-compose.yml:44-88`; `tests/test_compose_env.py` não cobre |
| F3 | `RunPublication.execute` com `enabled=False` devolve `BLOCKED` antes de claim/token/upload. | `renderer/app/studio/application/publication_execution.py:269-273`; `tests/test_publication_execution.py:610-618` |
| F4 | Lease do coordenador: `lease_seconds=300` por default; a composição não o sobrescreve. | `renderer/app/studio/application/production.py:650-661`; `composition/wiring.py:670-672` |
| F5 | `renew_lease` existe na porta e no repositório (CAS: `state='RUNNING'`, `lease_owner`, `fencing_token`, `lease_expires_at > statement_timestamp()`), com resultado `RENEWED/LOST/UNKNOWN`. **Nenhum consumidor** em `renderer/app`. | `application/ports.py:1051`; `adapters/postgres/production_repo.py:363-385`; `domain/production_run.py:152-155`; `tests/test_production_repo.py:282` |
| F6 | `claim_stage` incrementa `fencing_token` e `attempt` a cada claim e só toma etapa `RUNNING` com lease expirado (relógio do banco). `complete_stage`/`fail_stage` passam por `_write_guard` (token, dono, run `RUNNING`, lease vivo) → `LOST`. | `production_repo.py:312-361, 695-715` |
| F7 | O `ProductionWorker` tem **um único `owner` por processo** (`worker-<hex>`), compartilhado por todas as threads. O discriminador real entre tentativas é o `fencing_token`, não o dono. | `production.py:1005-1010` |
| F8 | O handler roda síncrono entre o claim e o `complete_stage`; não há renovação. | `production.py:892-924` |
| F9 | O pool de execução é `ThreadPoolExecutor(max_workers=RENDER_CONCURRENCY)` (default 1, máx. 4), **compartilhado** entre render jobs e `worker.work`. | `composition/wiring.py:312, 589, 676`; `composition/settings.py:80` |
| F10 | Recuperação só no boot: `lifespan` chama `studio.recover_in_flight` uma vez. `orphan_in_flight` trata como órfão qualquer run `RUNNING` sem **nenhum** lease vivo — inclusive o run entre dois passos do worker e o run enfileirado no executor (sem lease). | `renderer/app/main.py:15-27`; `production.py:621-637, 1133-1149` |
| F11 | `list_in_flight()` lê **todos** os runs `CREATED/RUNNING` e suas etapas (sem `LIMIT`). | `production_repo.py:286-308` |
| F12 | `PublishHandler` delega a `RunPublication.execute`, que só reivindica publicação `PENDING/FAILED` (`claim_retry`) ou vídeo sem publicação (`claim`). Publicação `UPLOADING` com lease vencido (processo morreu no upload) **não é reivindicável** por nenhum dos dois e o handler falha com “no approved publication is pending”. Publicação com `youtube_video_id` já gravado também cai em `IDLE` no `claim_*` (filtrada) e o handler falha. | `application/production.py:501-525`; `adapters/postgres/publish_repo.py:115-176`; `publication_execution.py:174-177` |
| F13 | Exceção/resultado ambíguo do uploader já vira `remote_state='UNKNOWN'` + `RECONCILE`; `claim_retry` nunca devolve `UNKNOWN`; só `ReconcilePublication` (rota manual `POST /publications/{id}/reconcile`) o resolve. | `publication_execution.py:296-304, 345-355`; `publish_repo.py:206-231`; `api/routes.py:2336` |
| F14 | Timeout do uploader pode chegar a 30 min; lease da **publicação** é 1800 s e `UPLOADING` não é reivindicável por `claim_retry` (logo sem risco de segundo claimant durante o upload). | `adapters/youtube_publisher.py:103`; `publication_execution.py:269` |
| F14b | O modelo `Publication` e o `SELECT` `_PUB` **não** expõem `lease_until` nem `remote_state`; só `PublicationLease` (`application/reopen.py:46-55`, lido por `_LEASE` em `publish_repo.py:343`) os traz, e fica na porta de *reopen*, não na fila. O handler `publish` hoje não consegue ver lease/estado remoto. | `domain/contracts.py:140-150`; `publish_repo.py:20, 343-352` |
| F15 | Migrações vão até `0049_saved_trends.sql`. Este plano **não precisa de migração**. | `renderer/app/studio/adapters/postgres/migrations/` |
| F16 | Comando canônico de teste com banco: `scripts/test-container.sh <paths> -q` (imagem do renderer + Postgres efêmero com prova de descartabilidade, checkout read-only). Testes de DB fazem `skip` sem `STUDIO_BUDGET_DISPOSABLE_DSN`. O Postgres compartilhado de dev **não** deve ser usado. | `scripts/test-container.sh:1-20`; `tests/conftest.py` |

## Decisões do plano (propostas — não são fatos)

- **D1 — Interruptor:** reaproveitar `STUDIO_PUBLICATION_ENABLED` (sem flag nova). No Compose, default **`1`** (`${STUDIO_PUBLICATION_ENABLED:-1}`), nunca vazio (por F1, `:-` vazio desligaria a publicação em silêncio — regressão grave). Escopo só publicação; `STUDIO_RENDER_PLAN_ENABLED`, `STUDIO_AUTO_RESEARCH`, `STUDIO_TREND_SOURCES`, `STUDIO_TOKEN_ENV_PATH` ficam fora (registrar como follow-up do R01).
- **D2 — Heartbeat:** thread daemon por etapa reivindicada (não usa o executor — F9, evita inanição com `RENDER_CONCURRENCY=1`), intervalo `lease_seconds/3` (100 s), renova com o `fencing_token` do claim. Lease permanece 300 s (sem env nova; YAGNI).
- **D3 — Perda de posse:** `LOST` ou `UNKNOWN` do banco ⇒ lease perdido, definitivo (sem retry de renovação). Falha de banco (exceção) ⇒ retenta a cada ≤ 5 s; se passar `lease_seconds − 10%` desde o **início** do último `RENEWED` (relógio monotônico, medido antes de enviar o pedido ⇒ conservador) ⇒ auto-cerco local (“considerar perdido”) mesmo sem confirmação do banco. Nunca “ressuscita”: o `UPDATE` exige `lease_expires_at > statement_timestamp()`.
- **D4 — Handlers são síncronos e não interrompíveis:** o heartbeat não mata `ffmpeg`/upload. O que ele garante: (a) não renova depois de perder; (b) o worker não chama `complete_stage`/`fail_stage` nem avança se perdeu (o CAS já recusaria — F6); (c) o handler `publish` checa `lease.ensure_held()` **antes** do efeito externo irreversível. Cancelamento cooperativo de render/ffmpeg fica **fora** do escopo (limitação registrada).
- **D5 — Recuperação periódica:** laço asyncio no `lifespan` (`sleep → to_thread(recover_orphans)`), sequencial por construção ⇒ sem sobreposição no processo; `STUDIO_RECOVERY_INTERVAL_SECONDS` (default `60`, `0` = só boot, inválido ⇒ default, mínimo `5`). Rollback operacional sem redeploy de código: `0`.
- **D6 — Candidatos órfãos:** consulta SQL com relógio do banco, `LIMIT` (50/tick), ordem estável (`created_at, run_id`), excluindo ids ativos no processo (`ActiveRuns`) e exigindo *grace* de inatividade (`max(updated_at)` da run/etapas ≥ 30 s) para não pegar run entre passos nem recém-enfileirado. O `orphan_in_flight` puro continua sendo a regra de decisão (dupla checagem); no boot o grace é 0 (comportamento atual preservado).
- **D7 — Réplicas:** sem advisory lock. A atomicidade entre réplicas vem do `claim_stage` (CAS + fencing): dois processos que re-despacham o mesmo run produzem um `CLAIMED` e um `BUSY`. Custo aceito: uma thread ociosa momentânea. Hoje o Compose tem 1 réplica do renderer.
- **D8 — Publicação e re-claim:** o `PublishHandler` ganha um passo de reconciliação *antes* de chamar `RunPublication.execute`: (1) `youtube_video_id` já gravado ⇒ conclui a etapa com checkpoint (sem tocar a rede); (2) `UPLOADING` com lease **vencido** ⇒ CAS para `UNKNOWN` (`mark_stale_ambiguous`) e segue para (3); (3) `remote_state='UNKNOWN'` ⇒ `ReconcilePublication.execute`: `UPLOADED` conclui; `RETRY` (sessão viva sem vídeo — provado) segue para `execute`; qualquer outro ⇒ `StageExecutionFailed` (humano). `UPLOADING` com lease **vivo** ⇒ `StageExecutionFailed` (tentativa anterior ainda ativa). Timeout/ACK nunca são lidos como sucesso nem como rollback.
- **D9 — Estados terminais/cancelados:** a recuperação nunca toca `FAILED/SUCCEEDED/CANCELLED/WAITING_HUMAN/PAUSED` (regra atual de `orphan_in_flight`, mantida e coberta por teste). Aprovação humana fica fora do redrive.

## Global Constraints

- Somente estas 3 melhorias. Sem refatoração geral, sem fila/scheduler novo, sem migração.
- `docker-compose.yml`: default seguro (`1`), nunca valor vazio para a flag; nenhum segredo interpolado nem impresso em teste.
- Nenhuma escrita em ambiente compartilhado: testes de banco **somente** via `scripts/test-container.sh`. Nenhum upload real, OAuth real ou chamada ao YouTube (dublês).
- Preservar comportamento existente: boot continua recuperando como hoje; `renew_lease` e `claim_stage` não mudam de contrato; nenhuma assertion existente é enfraquecida.
- Python sem dependência nova. Testes unitários rodam sem banco; testes de integração fazem `skip` sem DSN descartável (padrão do repositório).
- Concorrência: toda transição de posse continua CAS no banco; relógio de lease é o do banco (`statement_timestamp()`/`clock_timestamp()`), nunca o do processo.
- Sem `git push`, merge, deploy ou rebuild neste plano de documentação; a execução do plano terá commits locais por tarefa.

## Review Focus

1. **Lease vencido não ressuscita; posse perdida para a renovação.** `LOST`/`UNKNOWN` encerram o heartbeat sem nova tentativa; `renew_lease` com lease vencido devolve `LOST` mesmo para o dono com token atual. Testes: Task 2 (unitário com clock/renew falsos) e Task 8 (DB: lease 2 s, heartbeat parado ⇒ outro claim vence; token antigo recebe `LOST`).
2. **Worker obsoleto não finaliza nem altera estado.** Após perder o lease: nenhum `complete_stage`/`fail_stage` é chamado, `WorkerStep` = `LOST`; no DB o CAS recusa token antigo (F6). Testes: Task 3 (coordenador) e Task 8.
3. **Falha de banco, cancelamento e shutdown no heartbeat.** Exceção na renovação ⇒ retenta, auto-cerca no prazo `lease − 10%`; `stop()` é idempotente e não deixa thread viva; thread daemon não bloqueia SIGTERM; processo morto ⇒ lease expira ⇒ recuperação periódica assume. Testes: Task 2 e Task 6/7.
4. **Recuperação periódica sem duplicar efeito.** Run entre passos, enfileirado ou com lease vivo não é re-despachado; falha de submit/consulta não derruba o laço; dois `Production` sobre o mesmo DB produzem um único `CLAIMED`; `publish` re-claimado não reenvia vídeo com resultado ambíguo nem com id já gravado. Testes: Tasks 5, 6, 7, 8.
5. **Contingência efetiva ponta a ponta, default seguro.** Valor resolvido do Compose → `Settings.from_env` → `RunPublication(enabled=...)` ⇒ `BLOCKED` e uploader intocado quando `0`; sem variável ⇒ publicação continua ligada; default vazio é proibido por teste. Testes: Task 1.

## Mapa de arquivos e interfaces

| Arquivo | Ação | Interface exata |
|---|---|---|
| `docker-compose.yml` | Modify | `STUDIO_PUBLICATION_ENABLED: ${STUDIO_PUBLICATION_ENABLED:-1}`; `STUDIO_RECOVERY_INTERVAL_SECONDS: ${STUDIO_RECOVERY_INTERVAL_SECONDS:-60}` |
| `.env.example` | Modify | `STUDIO_PUBLICATION_ENABLED=1`, `STUDIO_RECOVERY_INTERVAL_SECONDS=60` com comentário |
| `tests/test_compose_env.py` | Modify | helper `_resolve_compose(value, env)`; testes de encaminhamento/efeito |
| `renderer/app/studio/application/lease_heartbeat.py` | **Create** | `class LeaseLost(Exception)`; `class StageLease` (`lost: bool`, `ensure_held() -> None`); `class LeaseHeartbeat(renew: Callable[[], LeaseResult], *, lease_seconds: int, interval_seconds: float \| None = None, clock: Callable[[], float] = time.monotonic, wait: Callable[[float], bool] \| None = None)` com `__enter__() -> StageLease` / `__exit__` / `stop()` |
| `renderer/app/studio/application/production.py` | Modify | `StageContext.lease: StageLease \| None = None`; `_execute_claimed` usa `LeaseHeartbeat`; `PublishHandler(publish, reconcile=None, pubs=None)`; `orphan_in_flight(..., grace: timedelta = timedelta(0))`; `ActiveRuns`; `Production.recover_orphans(...)` |
| `renderer/app/studio/application/ports.py` | Modify | `PublicationQueueRepository.lease_state(video_id: str) -> PublicationLease \| None` (reuso de `PublicationLease` de `application/reopen.py`; importar sob `TYPE_CHECKING` se houver ciclo); `PublicationQueueRepository.mark_stale_ambiguous(publication_id: str, attempt: int, error: str) -> bool`; `ProductionRunInFlightReader.list_orphan_candidates(*, grace_seconds: int, limit: int, exclude_run_ids: Collection[str] = ()) -> tuple[tuple[ProductionRun, tuple[StageExecution, ...]], ...]` |
| `renderer/app/studio/adapters/postgres/publish_repo.py` | Modify | `PostgresPublicationRepository.lease_state` (mesmo `SELECT _LEASE` + `_lease()` do reopen, sem `FOR UPDATE`) e `mark_stale_ambiguous` (CAS) |
| `renderer/app/studio/adapters/postgres/production_repo.py` | Modify | `list_orphan_candidates` |
| `renderer/app/studio/composition/settings.py` | Modify | `Settings.recovery_interval_seconds: float = 60.0` (último campo, com default) |
| `renderer/app/studio/composition/wiring.py` | Modify | `submit` rastreado por `ActiveRuns`; `Studio.recover_orphans()`; `PublishHandler` recebe `reconcile` e `pubs` |
| `renderer/app/main.py` | Modify | `_recovery_loop(studio, interval)` no `lifespan` |
| `tests/test_lease_heartbeat.py` | **Create** | unitários do heartbeat |
| `tests/test_production_service.py`, `tests/test_main_boot.py`, `tests/test_production_coordinator.py`, `tests/test_production_repo.py`, `tests/test_publication_execution.py` | Modify | testes novos por tarefa |
| `tests/test_lease_recovery_concurrency.py` | **Create** | integração de concorrência (DB descartável) |
| `docs/04-variaveis-de-ambiente.md`, `docs/11-arquitetura-operacional.md`, `docs/reviews/2026-11-24-architecture-review.md` | Modify | refletir o novo comportamento (Task 9) |

## Sequência, dependências e paralelismo

```
Task 1 (Compose) ─────────────────────────────────────────────┐
Task 2 (heartbeat puro) → Task 3 (coordenador) → Task 5 (PublishHandler) → Task 6 (recuperação periódica: núcleo) → Task 7 (laço + config) ─┐
Task 4 (publish_repo.mark_stale_ambiguous) ───────────────────→ Task 5                                                                      ├→ Task 8 (concorrência DB) → Task 9 (docs/rollout)
```

- **Paralelo seguro:** Task 1 ∥ Task 2 ∥ Task 4 (arquivos disjuntos).
- **Serializar:** Tasks 3 → 5 → 6 (todas editam `application/production.py`); Task 7 depende de 6; Task 8 depende de 3, 5, 6, 7.
- Commit por tarefa; nenhum commit mistura R01 com R02/R03.

---

### Task 1: Encaminhar a contingência de publicação pelo Compose (R01)

**Files:**
- Modify: `docker-compose.yml` (bloco `renderer.environment`, junto de `STUDIO_PRODUCTION_MODE`)
- Modify: `.env.example`
- Test: `tests/test_compose_env.py`

**Interfaces:**
- Produces: `_resolve_compose(value: str, env: Mapping[str, str]) -> str` (helper de teste; resolve `${VAR:-default}` e `${VAR}`).

- [ ] **Step 1 (RED): testes**

```python
# tests/test_compose_env.py (acrescentar)
import re as _re
from app.studio.composition import Settings


def _resolve_compose(value, env):
    """Resolve `${VAR:-padrão}` como o Compose: vazio/ausente usa o padrão."""
    def sub(match):
        name, default = match.group(1), match.group(3) or ""
        return env.get(name) or default
    return _re.sub(r"\$\{([A-Z0-9_]+)(:-([^}]*))?\}", sub, value)


def _renderer_env(env):
    declared = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    return {key: _resolve_compose(value, env) for key, value in declared.items()}


def test_compose_forwards_the_publication_switch_with_a_safe_default():
    declared = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    assert declared["STUDIO_PUBLICATION_ENABLED"] == "${STUDIO_PUBLICATION_ENABLED:-1}"


def test_publication_default_is_never_empty_because_empty_disables_it():
    # `_flag("")` é falso: um default vazio desligaria a publicação em silêncio.
    assert Settings.from_env({"STUDIO_PUBLICATION_ENABLED": ""}).publication_enabled is False
    assert _renderer_env({})["STUDIO_PUBLICATION_ENABLED"] == "1"
    assert Settings.from_env(_renderer_env({})).publication_enabled is True


def test_env_zero_reaches_settings_through_compose_and_blocks_the_uploader(tmp_path):
    from test_publication_execution import use  # fábrica de dublês já usada nos testes F01.T04
    from app.studio.application.publication_execution import PublicationResult
    settings = Settings.from_env(_renderer_env({"STUDIO_PUBLICATION_ENABLED": "0"}))
    assert settings.publication_enabled is False
    run, pubs, uploads, tokens = use(tmp_path, enabled=settings.publication_enabled)
    assert run.execute().result is PublicationResult.BLOCKED
    assert uploads.uploads == [] and tokens.calls == 0 and pubs.calls == []


def test_env_example_documents_the_publication_switch_enabled_by_default():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert _re.search(r"^STUDIO_PUBLICATION_ENABLED=1$", text, flags=_re.M)
```

Se o `import` de `test_publication_execution` não resolver, usar o mesmo mecanismo de `from conftest import ...` (rootdir `tests/` no `sys.path`) ou mover a fábrica para o `conftest`; não duplicar os dublês.

- [ ] **Step 2: rodar e ver falhar**

Run: `python3 -m pytest tests/test_compose_env.py -q` (sem DB; roda no host). Esperado: falha em `KeyError: 'STUDIO_PUBLICATION_ENABLED'` e no `.env.example`.

- [ ] **Step 3 (GREEN): implementar**

`docker-compose.yml`, após `STUDIO_PRODUCTION_MODE`:

```yaml
      # R01: contingência de publicação. 1 = ligada (default seguro, igual ao código); 0 desliga o
      # executor de upload (BLOCKED antes de claim/token/upload). NUNCA usar default vazio: vazio = desligado.
      STUDIO_PUBLICATION_ENABLED: ${STUDIO_PUBLICATION_ENABLED:-1}
```

`.env.example` (junto das flags do estúdio): `STUDIO_PUBLICATION_ENABLED=1` + comentário (`0` desliga upload; vale após `docker compose up -d renderer`).

- [ ] **Step 4: verde**

Run: `python3 -m pytest tests/test_compose_env.py tests/test_publication_execution.py -q`. Esperado: todos passam. Conferir também `docker compose config --quiet` **sem** imprimir valores (`POSTGRES_PASSWORD` é obrigatório: se não houver `.env` local, exportar um valor dummy só para esse comando; não rodar `docker compose config` sem `--quiet`).

- [ ] **Step 5: commit** — `feat(compose): forward STUDIO_PUBLICATION_ENABLED with a safe default`

---

### Task 2: Primitiva de heartbeat do lease (puro, sem banco)

**Files:**
- Create: `renderer/app/studio/application/lease_heartbeat.py`
- Test: `tests/test_lease_heartbeat.py`

**Interfaces:**
- Produces: `LeaseLost`, `StageLease`, `LeaseHeartbeat` (ver mapa). Depende só de `LeaseResult` (`domain/production_run.py`).
- Semântica: `interval = interval_seconds or lease_seconds / 3`. Laço: `base = clock()`; `result = renew()`; `RENEWED` ⇒ `last_ok = base`; `LOST/UNKNOWN` ⇒ `lost=True` e encerra; exceção ⇒ próxima espera `min(interval, 5.0)`; a cada iteração, se `clock() - last_ok >= lease_seconds * 0.9` ⇒ `lost=True` e encerra. `wait` injetável (`Event.wait` por padrão) para testar sem dormir. `stop()` seta o evento e faz `join(timeout=2)`; idempotente. `ensure_held()` levanta `LeaseLost` se `lost`.

- [ ] **Step 1 (RED): testes** (todos com `renew`/`clock`/`wait` falsos, sem sleep real)
  - `RENEWED` repetido mantém `lost is False` e chama `renew` a cada intervalo (`lease/3`).
  - `LOST` ⇒ `lost is True`, **uma** chamada de `renew`, sem retry; `ensure_held()` levanta `LeaseLost`.
  - `UNKNOWN` idem a `LOST`.
  - Exceção em `renew` ⇒ retenta; ao passar `0.9 * lease_seconds` desde o início do último `RENEWED` ⇒ `lost is True` (auto-cerco) mesmo sem `LOST` do banco.
  - Exceção seguida de `RENEWED` dentro do prazo ⇒ continua mantendo posse e `last_ok` avança.
  - `stop()` duas vezes não levanta; após `__exit__` a thread não está viva.
  - Não renova depois de `lost` (contagem de chamadas estável).

- [ ] **Step 2: rodar e ver falhar** — `python3 -m pytest tests/test_lease_heartbeat.py -q` ⇒ `ModuleNotFoundError`.
- [ ] **Step 3 (GREEN): implementar** `lease_heartbeat.py` conforme a semântica acima (thread `daemon=True`, nome `lease-heartbeat`, log `warning` sem segredo ao perder).
- [ ] **Step 4: verde** — mesmo comando. Esperado: todos passam.
- [ ] **Step 5: commit** — `feat(production): add lease heartbeat primitive`

---

### Task 3: Coordenador renova o lease e não finaliza sem posse (R02)

**Files:**
- Modify: `renderer/app/studio/application/production.py` (`StageContext`, `_execute_claimed`)
- Test: `tests/test_production_coordinator.py` (DB descartável) e `tests/test_production_service.py` (unitário)

**Interfaces:**
- `StageContext(run, execution, lease: StageLease | None = None)` — default `None` preserva construções existentes.
- `_execute_claimed`: abre `LeaseHeartbeat(renew=lambda: self.runs.renew_lease(run.run_id, execution.stage_id, owner, execution.fencing_token, self.lease_seconds), lease_seconds=self.lease_seconds)` em volta de `handler.execute`; fecha (`stop`) **antes** de `complete_stage`/`fail_stage`/`pause`.
- Se `lease.lost` ao fim do handler (retorno **ou** exceção): não chama `complete_stage`, `fail_stage` nem `pause_run`; devolve `WorkerStep(WorkerStepResult.LOST, run=run, stage=..., execution=execution, detail="lease lost during stage execution")`.

- [ ] **Step 1 (RED): testes**
  - Unitário (repositório falso que registra chamadas): etapa longa com `renew_lease` ⇒ `RENEWED` é chamado com `(run_id, stage, owner, fencing_token, lease_seconds)` exatos; `complete_stage` só depois do `stop`.
  - Unitário: `renew_lease` ⇒ `LOST` durante o handler ⇒ handler retorna normalmente ⇒ `complete_stage` **não** é chamado; resultado `LOST`.
  - Unitário: handler levanta `StageExecutionFailed` depois de perder o lease ⇒ `fail_stage` **não** é chamado; resultado `LOST`.
  - Unitário: sem perda, comportamento idêntico ao atual (os testes existentes continuam verdes sem alteração).
  - DB (`db` fixture, `lease_seconds=3`): handler dorme 7 s, heartbeat ativo ⇒ etapa `SUCCEEDED`, `attempt == 1`, `fencing_token` inalterado (nunca houve takeover). Controle negativo: o mesmo cenário com heartbeat desabilitado (monkeypatch do `LeaseHeartbeat` para no-op) ⇒ `complete_stage` devolve `LOST` (comportamento de hoje, prova de que o teste detecta a lacuna).
  - O handler recebe `context.lease` não nulo.
- [ ] **Step 2: rodar e ver falhar** — unitários: `python3 -m pytest tests/test_production_service.py -q`; DB: `scripts/test-container.sh tests/test_production_coordinator.py -q`.
- [ ] **Step 3 (GREEN): implementar** conforme as interfaces.
- [ ] **Step 4: verde** — os dois comandos, mais `scripts/test-container.sh tests/test_production_repo.py -q` (nenhum contrato do repositório mudou).
- [ ] **Step 5: commit** — `feat(production): renew the stage lease while a handler runs`

---

### Task 4: Leitura de lease/estado remoto e CAS de publicação travada em `UPLOADING` (base de D8)

**Files:**
- Modify: `renderer/app/studio/application/ports.py` (`PublicationQueueRepository`)
- Modify: `renderer/app/studio/adapters/postgres/publish_repo.py`
- Test: `tests/test_publication_execution.py` (dublê `Pubs`) e `tests/test_publication_resilience_repo.py` (DB; já cobre `claim_retry`/`mark_ambiguous`)

**Interfaces:**
- `lease_state(video_id: str) -> PublicationLease | None`: publicação ativa (não invalidada) do vídeo com `lease_until` e `remote_state` do banco (F14b). Só leitura.
- `mark_stale_ambiguous(publication_id: str, attempt: int, error: str) -> bool`:
```sql
UPDATE studio.publications SET status='PENDING', lease_until=NULL, next_attempt_at=NULL,
       remote_state='UNKNOWN', failure_class='AMBIGUOUS', error=%s, updated_at=now()
WHERE id=%s AND attempt=%s AND status='UPLOADING' AND youtube_video_id IS NULL
  AND invalidated_at IS NULL AND lease_until IS NOT NULL AND lease_until <= clock_timestamp()
```
  Retorna `rowcount == 1`. Relógio do banco; `attempt` como fencing da publicação.

- [ ] **Step 1 (RED): testes (DB descartável)**
  - `lease_state` devolve `lease_until`, `remote_state`, `youtube_video_id` e `status` corretos; `None` sem publicação ou invalidada.
  - Publicação `UPLOADING` com `lease_until` no passado ⇒ `True`; fica `PENDING` + `remote_state='UNKNOWN'` + `failure_class='AMBIGUOUS'`; `claim_retry` **não** a devolve (F13).
  - Lease no futuro ⇒ `False`, linha intacta.
  - `attempt` diferente ⇒ `False`. `youtube_video_id` já gravado ⇒ `False`. Chamar duas vezes ⇒ 2ª `False` (idempotente).
  - Concorrência: duas threads chamam ao mesmo tempo ⇒ exatamente uma `True`.
- [ ] **Step 2: rodar e ver falhar** — `scripts/test-container.sh tests/test_publication_resilience_repo.py -q` ⇒ `AttributeError`.
- [ ] **Step 3 (GREEN): implementar** porta + repositório; atualizar os dublês `Pubs` de `tests/test_publication_execution.py` com o método (registra chamada).
- [ ] **Step 4: verde** — `scripts/test-container.sh tests/test_publication_execution.py tests/test_publication_resilience_repo.py tests/test_publish_repo.py -q`.
- [ ] **Step 5: commit** — `feat(publication): expire stale uploading publications into the ambiguous state`

---

### Task 5: `PublishHandler` reconcilia antes de reenviar e respeita o lease (D8, R02/R03)

**Files:**
- Modify: `renderer/app/studio/application/production.py` (`PublishHandler`, `build_stage_handlers` — novos kwargs opcionais `reconcile`, `publications`)
- Modify: `renderer/app/studio/composition/wiring.py` (injeção: `reconcile` já existe na linha ~633 e `pubs` na composição; passar para `build_stage_handlers`)
- Test: `tests/test_production_handlers.py` (já cobre `PublishHandler`)

**Interfaces:**
- `PublishHandler(publish: RunPublication, reconcile: ReconcilePublication | None = None, pubs: PublicationQueueRepository | None = None)`. Sem `pubs`/`reconcile` ⇒ comportamento atual exato (compatibilidade).
- Algoritmo em `execute` (ordem fixa, D8):
  1. `context.lease.ensure_held()` se houver lease (levanta `LeaseLost` ⇒ tratado como perda no coordenador, não como falha de negócio).
  2. `pub = pubs.get(video_id)` e `state = pubs.lease_state(video_id)` (F14b); se `pub` e `pub.youtube_video_id` ⇒ `StageOutcome` com checkpoint `{"stage","youtube_video_id","publication_id"}`.
  3. `pub.status == UPLOADING`: `state.lease_until` vencido (comparar com `clock()` do handler apenas para decidir a tentativa; a decisão real é o CAS do banco) ⇒ `pubs.mark_stale_ambiguous(pub.id, pub.attempt, "stage re-claimed after the previous executor stopped; upload outcome unknown")`; se devolver `False` reler `lease_state` e reavaliar uma vez; lease vivo ⇒ `StageExecutionFailed("a previous upload attempt is still active; wait for its lease or reconcile")`.
  4. `state.remote_state == "UNKNOWN"` (relido após o passo 3): sem `reconcile` ⇒ `StageExecutionFailed("publication outcome is ambiguous; reconcile before retrying")`; com `reconcile` ⇒ `reconcile.execute(pub.id)`: `UPLOADED` ⇒ checkpoint; `RETRY` ⇒ segue; demais ⇒ `StageExecutionFailed(...)` com o resultado.
  5. `context.lease.ensure_held()` de novo e só então `publish.execute(video_id=...)` (caminho atual).
- `coordinator._execute_claimed` trata `LeaseLost` levantado pelo handler como `LOST` (sem `fail_stage`).

- [ ] **Step 1 (RED): testes** (dublês sem rede; assertar `uploads.uploads == []` onde couber)
  - Publicação já com `youtube_video_id` ⇒ etapa conclui com checkpoint, **zero** chamadas ao uploader (hoje falha com IDLE — F12; este teste prova a correção).
  - `UPLOADING` com lease vencido ⇒ `mark_stale_ambiguous` chamado uma vez, `reconcile.execute` chamado, uploader de upload **não** chamado; reconcile `UPLOADED` ⇒ etapa conclui.
  - Reconcile `RETRY` ⇒ segue para `publish.execute` (único upload), `remote_state` não permanece `UNKNOWN`.
  - Reconcile `RECONCILE`/`DEAD_LETTER`/`BLOCKED` ⇒ `StageExecutionFailed`; nenhum upload.
  - `UPLOADING` com lease vivo ⇒ `StageExecutionFailed`; nenhum upload nem `mark_stale_ambiguous`.
  - `remote_state='UNKNOWN'` sem `reconcile` injetado ⇒ `StageExecutionFailed`; sem upload.
  - Lease já perdido (`lease.lost=True`) antes do upload ⇒ `LeaseLost`, upload **não** chamado.
  - Sem `pubs`/`reconcile` (construção antiga) ⇒ comportamento idêntico ao atual.
- [ ] **Step 2: rodar e ver falhar** — `python3 -m pytest tests/test_production_service.py -q`.
- [ ] **Step 3 (GREEN): implementar** + ajustar `_execute_claimed` para `except LeaseLost: return LOST`.
- [ ] **Step 4: verde** — `python3 -m pytest tests/test_production_service.py tests/test_publication_execution.py -q` e `scripts/test-container.sh tests/test_production_coordinator.py -q`.
- [ ] **Step 5: commit** — `fix(production): reconcile an ambiguous publication before the publish stage retries`

---

### Task 6: Núcleo da recuperação periódica (R03)

**Files:**
- Modify: `renderer/app/studio/application/production.py` (`orphan_in_flight`, `ActiveRuns`, `Production`)
- Modify: `renderer/app/studio/application/ports.py` (`ProductionRunInFlightReader.list_orphan_candidates`)
- Modify: `renderer/app/studio/adapters/postgres/production_repo.py`
- Modify: `renderer/app/studio/composition/wiring.py` (`submit` rastreado; `Studio.recover_orphans`)
- Test: `tests/test_production_service.py`, `tests/test_production_repo.py`, `tests/test_composition.py`

**Interfaces:**
- `orphan_in_flight(in_flight, now, grace: timedelta = timedelta(0))`: para `RUNNING` sem lease vivo, exige `latest_activity <= now - grace`, com `latest_activity = max(run.updated_at, *stage.updated_at)` ignorando `None` (todos `None` ⇒ elegível). `CREATED` segue elegível (mesma regra; também respeita `grace` por `updated_at`/`created_at`).
- `class ActiveRuns`: thread-safe, contador por `run_id` — `acquire(run_id) -> None`, `release(run_id) -> None`, `snapshot() -> frozenset[str]`.
- `Production.recover_orphans(*, now: datetime | None = None, grace_seconds: int = 30, limit: int = 50, active: ActiveRuns | None = None) -> tuple[str, ...]`: `in_flight.list_orphan_candidates(grace_seconds=..., limit=..., exclude_run_ids=active.snapshot())` → `orphan_in_flight(..., grace)` → `_enqueue` para cada um. Sem porta ⇒ `()`. Exceção de leitura propaga (o laço captura — Task 7); falha de `submit` fica isolada em `_enqueue` (como hoje). `recover_in_flight` (boot) permanece **inalterado**.
- `PostgresProductionRunRepository.list_orphan_candidates(*, grace_seconds, limit, exclude_run_ids=())`: mesma projeção de `list_in_flight`, filtrando no SQL com relógio do banco: `state='CREATED'` **ou** (`state='RUNNING'` e `NOT EXISTS` etapa com `lease_owner IS NOT NULL AND lease_expires_at > statement_timestamp()`), e `GREATEST(run.updated_at, max(stage.updated_at)) <= statement_timestamp() - make_interval(secs => grace)`, `NOT (run_id = ANY(%s))`, `ORDER BY created_at, run_id LIMIT %s`. `limit` validado `1 ≤ limit ≤ 500`.
- `wiring.py`: `active = ActiveRuns()`; `submit=` vira função que faz `active.acquire(run_id)`, `future = self._executor.submit(worker.work, run_id)`, `future.add_done_callback(lambda _f: active.release(run_id))`; se `submit` levantar ⇒ `release` e relança (o `_enqueue` já captura). **Não descarta** submits explícitos (`start/resume/retry`): só registra. `Studio.recover_orphans() -> tuple[str, ...]` delega a `cases.production.recover_orphans(active=...)` (no-op sem banco/fiação).

- [ ] **Step 1 (RED): testes**
  - Puro: run `RUNNING` sem lease mas com `updated_at = now - 5 s` e `grace=30 s` ⇒ **não** é órfão; com `updated_at = now - 31 s` ⇒ órfão; `grace=0` reproduz os testes atuais (suíte existente intacta).
  - Puro: estados `FAILED/SUCCEEDED/CANCELLED/WAITING_HUMAN/PAUSED` nunca entram, mesmo que o leitor os devolva (D9).
  - Serviço: ids em `ActiveRuns` são passados em `exclude_run_ids`; ids órfãos são submetidos uma vez; falha de `submit` de um não impede os outros; leitor sem porta ⇒ `()`; `limit` respeitado (leitor falso devolve ≤ limit).
  - `ActiveRuns`: dois `acquire` + um `release` ainda reporta ativo; thread-safety básica (N threads, snapshot final vazio).
  - DB: run `RUNNING` com lease vivo ⇒ fora; lease expirado + inatividade ≥ grace ⇒ dentro; lease expirado mas atividade recente ⇒ fora; `exclude_run_ids` exclui; `LIMIT` e ordem estável; run `PAUSED`/`WAITING_HUMAN` ⇒ fora; relógio é do banco (ajustar `lease_expires_at`/`updated_at` por SQL, sem sleep).
  - Composição: `Studio.recover_orphans()` sem banco ⇒ `()`; `submit` registra e libera `ActiveRuns` ao terminar o worker e também quando o executor falha.
- [ ] **Step 2: rodar e ver falhar** — `python3 -m pytest tests/test_production_service.py tests/test_composition.py -q`; `scripts/test-container.sh tests/test_production_repo.py -q`.
- [ ] **Step 3 (GREEN): implementar**; atualizar os dublês `_Reader` existentes com `list_orphan_candidates`.
- [ ] **Step 4: verde** — mesmos comandos + `scripts/test-container.sh tests/test_production_coordinator.py -q`.
- [ ] **Step 5: commit** — `feat(production): bounded orphan candidate query and active-run guard for periodic recovery`

---

### Task 7: Laço periódico no `lifespan` e configuração (R03)

**Files:**
- Modify: `renderer/app/studio/composition/settings.py`, `renderer/app/main.py`
- Modify: `docker-compose.yml`, `.env.example`
- Test: `tests/test_main_boot.py`, `tests/test_composition.py` (ou teste de Settings existente), `tests/test_compose_env.py`

**Interfaces:**
- `Settings.recovery_interval_seconds: float = 60.0` (**último** campo; `from_env`: `STUDIO_RECOVERY_INTERVAL_SECONDS`; ausente/vazio/inválido/negativo/NaN ⇒ `60`; `0` ⇒ desabilitado; `0 < x < 5` ⇒ `5`).
- `main._recovery_loop(studio, interval: float) -> None`:
```python
async def _recovery_loop(studio, interval):
    while True:
        await asyncio.sleep(interval)
        try:
            recovered = await asyncio.to_thread(studio.recover_orphans)
            if recovered:
                logger.warning("production: %d run(s) orfao(s) re-dirigido(s) pela varredura periodica", len(recovered))
        except Exception:   # nunca derruba o laço; próxima rodada tenta de novo
            logger.warning("production: varredura periodica indisponivel", exc_info=True)
```
  No `lifespan`: após o boot sweep, se `interval > 0` ⇒ `task = asyncio.create_task(_recovery_loop(...))`; no shutdown ⇒ `task.cancel()` + `await` com `suppress(asyncio.CancelledError)` **antes** de `studio.shutdown()`. Sequencial ⇒ nunca sobrepõe no processo (R8: não espera, não empilha).
- Compose: `STUDIO_RECOVERY_INTERVAL_SECONDS: ${STUDIO_RECOVERY_INTERVAL_SECONDS:-60}`.

- [ ] **Step 1 (RED): testes**
  - Settings: default `60`; `"0"` ⇒ `0`; `"2"` ⇒ `5`; `"abc"`/`""`/`"-1"`/`"nan"` ⇒ `60`.
  - Lifespan com `_FakeStudio` (estender com `settings.recovery_interval_seconds` e `recover_orphans`) e intervalo injetável/monkeypatch para ~0,01 s: varredura chamada ≥ 2 vezes; exceção na varredura não mata o laço (chamadas continuam); `interval == 0` ⇒ nenhuma tarefa criada; no shutdown a tarefa termina (cancelada) e `shutdown` é chamado; a subida não bloqueia.
  - Não sobrepõe: `recover_orphans` falso bloqueia em `threading.Event`; enquanto bloqueado, o contador de chamadas concorrentes nunca passa de 1.
  - Compose: encaminhamento exato `${STUDIO_RECOVERY_INTERVAL_SECONDS:-60}`; `.env.example` documenta.
- [ ] **Step 2: rodar e ver falhar** — `python3 -m pytest tests/test_main_boot.py tests/test_compose_env.py tests/test_composition.py -q`.
- [ ] **Step 3 (GREEN): implementar**.
- [ ] **Step 4: verde** — mesmos comandos (o `test_boot_imports_app_and_health_responds` existente precisa continuar passando).
- [ ] **Step 5: commit** — `feat(production): periodic orphan recovery loop with kill switch`

---

### Task 8: Prova de concorrência com banco descartável

**Files:**
- Create: `tests/test_lease_recovery_concurrency.py` (fixtures no padrão de `tests/test_production_coordinator.py`: `dsn`/`conn`/`db`, `skip` sem DSN descartável)

- [ ] **Step 1 (RED→GREEN, escrever contra a implementação pronta; cada teste precisa falhar se a peça correspondente for removida)**
  1. **Heartbeat segura a posse:** dois workers (owners distintos) disputam a mesma etapa; `lease_seconds=3`, handler do primeiro dorme 8 s; o segundo faz `claim` a cada 0,5 s ⇒ sempre `BUSY`; ao fim, uma única execução (`attempt == 1`).
  2. **Takeover legítimo após morte:** handler do primeiro é interrompido sem `stop` (simular: heartbeat falso nunca renova); lease vence; o segundo faz claim com `fencing_token` maior; o primeiro, ao tentar `complete_stage` com o token antigo, recebe `LOST` e **nada** muda (estado, checkpoint, tentativa).
  3. **Sem ressurreição:** após o lease vencer, `renew_lease` do dono antigo (token antigo) devolve `LOST`; do dono com token atual mas lease vencido também `LOST`.
  4. **Duas réplicas, um claim:** dois `Production` (com `ActiveRuns` próprios) sobre o mesmo DB chamam `recover_orphans` simultaneamente (Barrier) para o mesmo run órfão ⇒ handler contador executa **uma** vez; o outro `step` devolve `NOTHING_READY`/`BUSY`.
  5. **Recuperação após efeito concluído:** `publish` com publicação já `UPLOADED` e etapa `RUNNING` com lease vencido ⇒ recuperação conclui a etapa sem chamar o uploader (liga Task 5 + 6).
  6. **Terminais preservados:** runs `CANCELLED`/`FAILED`/`SUCCEEDED`/`PAUSED`/`WAITING_HUMAN` com leases antigos nunca são re-despachados por `recover_orphans`.
  7. **Falha de submit e de banco:** `submit` que levanta não impede os demais órfãos; leitor que levanta propaga e o laço (`_recovery_loop` com `studio` falso) segue na rodada seguinte.
- [ ] **Step 2: rodar** — `scripts/test-container.sh tests/test_lease_recovery_concurrency.py -q`. Esperado: todos passam; registrar a saída real.
- [ ] **Step 3: suíte relacionada** — `scripts/test-container.sh tests/test_production_repo.py tests/test_production_coordinator.py tests/test_production_service.py tests/test_publication_execution.py tests/test_main_boot.py tests/test_compose_env.py tests/test_composition.py -q`. Esperado: verde; comparar com o baseline do `main` (executar a mesma lista antes de começar e anotar falhas preexistentes — não corrigir bug preexistente nesta tarefa, apenas registrar).
- [ ] **Step 4: commit** — `test(production): concurrency proofs for lease heartbeat and periodic recovery`

---

### Task 9: Documentação, observabilidade mínima e rollout

**Files:**
- Modify: `docs/04-variaveis-de-ambiente.md` (linha de `STUDIO_PUBLICATION_ENABLED`: agora **chega** pelo Compose, default `1`, `0` desliga; nova linha de `STUDIO_RECOVERY_INTERVAL_SECONDS`)
- Modify: `docs/11-arquitetura-operacional.md` (fluxos: heartbeat, varredura periódica, reconciliação do `publish`; limitação D4)
- Modify: `docs/reviews/2026-11-24-architecture-review.md` (marcar R01–R03 como endereçados pelo plano/commit, sem apagar a evidência original)
- Modify: `docs/reviews/2026-11-24-progress.md` (entrada própria)

- [ ] **Step 1:** atualizar os quatro arquivos; manter exemplos sem valores secretos.
- [ ] **Step 2:** conferir links/âncoras e referências `arquivo:linha` com os mesmos checks usados no review (`git diff --check`; links locais por script).
- [ ] **Step 3: commit** — `docs: describe heartbeat, periodic recovery and the publication switch`

**Observabilidade (sem stack nova):** logs `warning` estruturados já previstos (`lease lost`, `varredura periodica`); a contagem de órfãos recuperados por tick sai no log. Alerta operacional sugerido (fora do código): `lease lost` recorrente ⇒ revisar duração real das etapas (p95 não foi medido — hipótese) antes de elevar o TTL.

## Rollout / Rollback (descrição; nada é executado por este plano)

1. **Task 1 sozinha** (config): `docker compose up -d renderer`; verificar `docker compose exec renderer printenv STUDIO_PUBLICATION_ENABLED` (valor `1`, não segredo). Rollback: reverter a linha do Compose.
2. **Tasks 2–5** (heartbeat + reconciliação): rebuild do renderer em janela sem produção em andamento (`docker compose up -d --build renderer`); aguardar `healthy`. Sem flag própria: rollback = imagem/commit anterior. Comportamento degrada para o atual se o banco ficar indisponível (auto-cerco local, nunca renovação cega).
3. **Tasks 6–7** (varredura): entra com `STUDIO_RECOVERY_INTERVAL_SECONDS=60`. **Kill switch sem rebuild:** `STUDIO_RECOVERY_INTERVAL_SECONDS=0` + `docker compose up -d renderer` ⇒ volta a só-boot.
4. Pós-subida: observar logs do renderer por 1 hora (sem `lease lost` espúrio, sem rajada de re-despacho); não executar testes de integração no Postgres de dev.

## Critérios de aceite

- [ ] `docker compose` encaminha `STUDIO_PUBLICATION_ENABLED` com default `1`; `0` ⇒ `RunPublication` `BLOCKED`, uploader e token intocados (teste ponta a ponta de Settings).
- [ ] Etapa de 7 s com lease de 3 s termina `SUCCEEDED` na tentativa 1; sem heartbeat o mesmo teste prova `LOST`.
- [ ] Lease perdido ⇒ nenhum `complete_stage`/`fail_stage`/`pause_run`; resultado `LOST`; token antigo recebe `LOST` no banco.
- [ ] Run órfão é re-despachado periodicamente; run entre passos, enfileirado, com lease vivo ou em estado terminal/humano **não**; no máximo `limit` por tick; kill switch `0` desliga o laço.
- [ ] Dois `Production` no mesmo banco ⇒ uma execução da etapa.
- [ ] `publish` re-claimado nunca reenvia vídeo com id gravado ou resultado `UNKNOWN`; reconciliação precede qualquer retry.
- [ ] Nenhuma assertion existente enfraquecida; nenhuma migração; suíte relacionada verde no container de teste, com baseline comparado.

## Limitações e riscos conhecidos

- Handlers não são interrompíveis: um render/upload já em curso continua até terminar mesmo após perder o lease; só o estado fica protegido (D4). Cancelamento cooperativo é trabalho futuro.
- Sem advisory lock: duas réplicas podem despachar o mesmo run; o claim evita execução dupla, ao custo de uma thread momentânea (D7).
- O p95 de duração das etapas **não foi medido** (hipótese: ≥ 5 min em render/publish). O heartbeat torna isso irrelevante para a posse, mas não altera a duração.
- `RENDER_CONCURRENCY=1` serializa runs e render jobs; recuperação periódica não aumenta throughput.
- O grace de 30 s e o `limit` de 50 são valores iniciais propostos, não medidos.
- Fora de escopo (registrar para avaliação futura): demais flags não encaminhadas pelo Compose (R01 completo), healthcheck de domínio (R04), cancelamento cooperativo, snapshots defasados (R06).

## Self-review do plano

- **Cobertura:** R01 → Task 1; R02 → Tasks 2, 3, 5 (parte do lease), 8; R03 → Tasks 6, 7, 8; ambiguidade de upload/reconciliação → Tasks 4, 5; rollout/rollback e docs → Task 9. Cada Review Focus tem teste nomeado.
- **Consistência de assinaturas:** `StageLease`/`LeaseHeartbeat` (Task 2) são consumidos por `StageContext.lease` (Task 3) e `PublishHandler` (Task 5); `mark_stale_ambiguous` (Task 4) é consumido na Task 5; `list_orphan_candidates`/`ActiveRuns`/`recover_orphans` (Task 6) são consumidos por `Studio.recover_orphans` e `_recovery_loop` (Task 7) e provados na Task 8; `Settings.recovery_interval_seconds` é o último campo com default (não quebra construções posicionais).
- **Verificado ao escrever o plano:** `complete_stage` grava `updated_at = statement_timestamp()` (`production_repo.py:406-407`), então a regra de grace da Task 6 é válida; `use(tmp_path, ..., enabled=...)` existe em `tests/test_publication_execution.py:234`; `tests/test_production_handlers.py` cobre `PublishHandler`; `Publication` **não** tem `lease_until`/`remote_state` (corrigido pela leitura `lease_state` da Task 4).
- **A confirmar na execução (não presumido):** que `from test_publication_execution import use` resolve a partir de `tests/test_compose_env.py` (caso contrário mover a fábrica para o `conftest`); possível ciclo de import `ports` ↔ `reopen` ao tipar `lease_state`; assinatura completa de `use(...)` para o dublê `Pubs` ganhar `lease_state`/`mark_stale_ambiguous`.
