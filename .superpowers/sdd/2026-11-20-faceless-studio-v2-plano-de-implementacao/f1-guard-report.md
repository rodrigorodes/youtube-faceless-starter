# F1 — guard de orçamento nos caminhos pagos (fatia A)

Commits desta linha de correção: `822334a` (fatia original), `18700e2` (crítico + 4 importantes) e
`e8f6b52` (correções operacionais I1–I6 + índices). Este relatório foi commitado em seguida.

Esta fatia liga as chamadas pagas (roteiro/editorial, imagem, voz e pontuação de ideias) ao protocolo
de reserva de orçamento já existente e fecha o ciclo de vida da operação paga. **Não** substitui o
ledger legado, não integra reconciliação automática e **não** garante hard limit; os limites continuam
dependendo dos argumentos fornecidos pelo chamador.

## Política de custo (crítico já resolvido)

Um terceiro tipo explícito `ESTIMATE` é contabilizado como **gasto aproximado** (não "desconhecido",
não `ACTUAL`).

- `CostConfirmation` aceita `ACTUAL` (positivo), `ESTIMATE` (positivo) e `FREE` (zero), sempre com
  referência e responsável não vazios.
- `provider_settlement(entry, *, settled_by, charge=None)`:
  - Sem `charge`: zero ⇒ `FREE`; positivo ⇒ `ESTIMATE` (nunca `ACTUAL`).
  - Com `charge` (`ChargeEvidence`: valor cobrado + referência + quem declara) ⇒ `ACTUAL` **no valor
    cobrado**, e o `UsageEntry` do ledger é atualizado para esse valor.
- `OpenCodeImage` grava `STUDIO_PAID_IMAGE_USD` como estimativa configurável ⇒ `ESTIMATE`; o gasto
  continua contando no teto, mas o mês não vira desconhecido.
- `reconcile_actual` troca `ESTIMATE` por `ACTUAL`, ou converte para `FREE` quando a cobrança
  comprovada é zero, numa transação, sem duplicar linha.

### `settled_by` é rótulo de call site (limitação explícita)

`settled_by` é obrigatório e nomeia o processo que encerra a operação (ex.: `studio:image:opencode`),
mas **é descartado no caminho `ACTUAL`**: quem assina a confirmação é `charge.declared_by` (o adapter
que declara a cobrança). Ou seja, em `ACTUAL`, `confirmed_by` no ledger é `charge.declared_by`, não o
`settled_by` passado pelo call site. Isso é intencional (a evidência manda), mas está documentado
porque o nome pode sugerir o contrário.

## Correções operacionais desta rodada (I1–I6)

1. **I1 — liberar devolve a chave.** `RELEASED` agora significa "nenhum efeito externo, seguro
   repetir": `begin` reabre a mesma chave como **nova tentativa** (`attempt + 1`), cria **nova
   reserva** e devolve `CREATED`. `CONFIRMED` continua **terminal** (retry recusado com
   `OperationSettled`) e `UNCERTAIN` continua bloqueado até reconciliação. Migração `0020` adiciona
   `paid_operations.attempt` (default 1; reabertura incrementa).
   - Consequência documentada: `CONFIRMED` com resultado perdido (crash após confirmar) **não** é
     reexecutado; reutilização de resultado/asset fica para o coordenador (D2). Não há replay pago.
   - Testes: `test_released_operation_can_retry_and_charges_only_once`,
     `test_released_operation_reopens_with_a_new_attempt_and_reservation`,
     `test_confirmed_operation_is_terminal_and_does_not_reopen`.
2. **I2 — órfão do mês corrente visível.** `pending_reconciliation(stale_after=...)` lista operações
   `RESERVED` paradas há mais de `STALLED_AFTER` (padrão **15 min**) como `stalled_operation`, com
   `stalled_for` (tempo desde `updated_at`) no item retornado. O limiar é injetável para teste/serviço.
   Não há heartbeat: uma chamada legítima mais longa que o limiar também aparece; a lista **não**
   encerra nem altera a operação. `KeyboardInterrupt`, crash e falha de `confirm` deixam de sumir.
   - Teste: `test_stalled_reserved_operation_is_reported_with_the_time_it_has_been_stuck` (força
     `updated_at` para 20 min atrás e também injeta `stale_after=2h`).
3. **I3 — `confirm` dentro de handler.** Falha ao confirmar (ex.: `CostConfirmationError`) marca a
   operação `UNCERTAIN` com motivo e relança. Se o próprio `mark_uncertain` falhar (banco fora), a
   exceção do mark é relançada **com a original como causa** (`raise mark_exc from exc`).
   - Testes: `test_confirm_failure_marks_the_operation_uncertain_and_reraises`,
     `test_confirm_failure_keeps_the_original_error_when_marking_uncertain_also_fails`.
4. **I4 — 500 residual e mensagens.** `IdempotencyConflict` → **409**, `CostConfirmationError` →
   **422** (é erro de conteúdo da confirmação, não conflito de estado), `UnknownPaidOperation` → 404.
   O 409 agora tem **mensagem por estado**: `CONFIRMED` → "already confirmed; reuse the existing
   result"; `RELEASED` → "was released and cannot be retried"; `in progress` e `uncertain/incompatible`
   têm mensagens próprias. Nenhuma inclui chave ou valor. Teste de contrato inclui 404 explícito
   (`tests/test_budget_http.py`).
5. **I5 — reconciliação mais ampla.** `reconcile_actual` aceita:
   - `CONFIRMED` + `ESTIMATE` (troca o lançamento existente);
   - `UNCERTAIN` (o caso natural: insere o lançamento que faltava, confirma e remove a reserva);
   - `charged_usd = 0` converte para `FREE`, eliminando o gasto fantasma da estimativa no teto.
   `CONFIRMED` + `ACTUAL` continua não reconciliável (evita reescrever histórico).
   - Testes: `test_reconcile_uncertain_operation_closes_it_with_actual_charge`,
     `test_reconcile_estimate_to_zero_converts_to_free_and_releases_the_ghost_spend`,
     `test_reconcile_actual_only_applies_to_an_estimate_or_uncertain_operation`.
6. **I6 — `ScoreIdeas` valida antes de confirmar.** A rubrica é parseada dentro de `validate=` do
   `paid.run`; saída inválida fica `UNCERTAIN` (dinheiro pago, resultado inutilizável), como roteiro e
   imagem. Teste: `test_invalid_ideas_after_a_successful_paid_call_stays_uncertain`.

## Performance e migração

Migração `0020_paid_operation_attempt_and_budget_indexes.sql` (quatro dígitos; `0019` é desta fatia,
`0018` é de D; não houve colisão):

- `paid_operations.attempt` (default 1, CHECK `attempt >= 1`).
- Índices: `usage_ledger(created_at)`, `usage_ledger(video_id)`,
  `budget_reservations(created_at)`, `paid_operations(state, updated_at)`.
- **Janelas de lock documentadas no arquivo**:
  - `ADD COLUMN ... DEFAULT constante` é metadata-only no PG >= 11, mas toma ACCESS EXCLUSIVE breve.
  - `CREATE INDEX` sem `CONCURRENTLY` toma SHARE lock e **bloqueia escritas** durante a construção;
    `CONCURRENTLY` não roda dentro da transação de migração. Com tabela grande, criar o índice
    concurrentemente fora da migração antes de aplicar a versão.
  - A `0019` já aplicada fez `DROP/ADD CONSTRAINT ... CHECK` em `usage_ledger` com ACCESS EXCLUSIVE e
    varredura completa. Para tabela grande, o padrão seguro é `ADD CONSTRAINT ... NOT VALID`
    (ACCESS EXCLUSIVE breve, sem varredura) + `VALIDATE CONSTRAINT` em migração separada
    (SHARE UPDATE EXCLUSIVE, permite leituras/escritas). Aqui a tabela ainda é pequena; não foi
    necessário.

## Regras reais do ciclo de vida

1. Só a chamada que recebeu `CREATED` executa o provedor.
2. `RELEASED` = seguro repetir: o próximo `begin` com as mesmas entradas reabre (`CREATED`, nova
   reserva, `attempt + 1`). Entradas diferentes continuam `IdempotencyConflict`.
3. `CONFIRMED` é terminal: replay levanta `OperationSettled` e **não** executa de novo. Reutilizar o
   resultado/asset perdido é responsabilidade do coordenador (D2).
4. `UNCERTAIN` mantém a reserva e bloqueia até `confirm`, `release` ou `reconcile_actual` explícitos.
5. `IN_PROGRESS` (RESERVED) não reexecuta concorrentemente.
6. Resultado ambíguo ou saída paga inválida → `UNCERTAIN`; falha comprovadamente pré-efeito →
   `RELEASED` com motivo.
7. `FREE` confirmado (voz Piper) pode ser reexecutado sem nova reserva no caminho de voz
   (`allow_free_replay`); `ESTIMATE`/`ACTUAL` não.
8. Nenhuma chave de API, chamada de rede real ou publicação nos testes; PostgreSQL só descartável com
   prova privada.

## TDD — RED e GREEN medidos

RED desta rodada contra o código anterior (com a migração `0020` já presente para o teste enxergar o
schema; comportamento ainda antigo):

- `test_budget_http.py` falhou na coleta: `TypeError: OperationSettled() takes no keyword arguments`
  (não havia mensagem por estado).
- 7 falhas de comportamento: reopen de `RELEASED` retornava `RELEASED`/não criava reserva;
  `reconcile_actual` um `UNCERTAIN` levantava `InvalidOperationTransition` e zero levantava
  `CostConfirmationError`; `pending_reconciliation` não listava `RESERVED` parada; `confirm` fora do
  handler deixava `RESERVED` órfão; `ScoreIdeas` confirmava antes de validar.

GREEN após a implementação: **115 passed** nos quatro focados
(`test_budget_guard.py`, `test_budget_http.py`, `test_paid_operations.py`,
`test_budget_reservations.py`).

## Testes — comandos e resultados reais

Imagem local `faceless-v2-hygiene-test-local:latest` (Python 3.12 + pytest), rede Docker isolada
(`f1c-net`), PostgreSQL 16 descartável (`f1c-pg`, tmpfs) e prova de 32 bytes montada em
`/budget-test-proof` (somente leitura) no banco e no runner. **Sem mount do `.git`** nesta rodada.

```
docker run --rm --network f1c-net \
  -v "$PWD":/workspace:ro \
  -v <proof_dir>:/budget-test-proof:ro -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1c-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1c-pg:5432/postgres \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest -p no:cacheprovider ...
```

- Focados (`test_budget_guard.py`, `test_budget_http.py`, `test_paid_operations.py`,
  `test_budget_reservations.py`): **115 passed**.
- `tests/test_db.py`: **13 passed, 2 failed** — falha esperada e **não corrigida de propósito**:
  a instrução desta rodada proíbe tocar em `tests/test_db.py`, e as duas listas de migração
  (`test_migrate_applies_once` e `test_failed_migration_rolls_back_and_is_not_recorded`, linhas 25 e
  37) ainda terminam em `"0019_ledger_estimate_and_attribution"`. Falta acrescentar
  `"0020_paid_operation_attempt_and_budget_indexes"` ao fim das duas listas. O controlador precisa
  aplicar essa linha; não alterei o arquivo proibido.
- Suíte completa: **1537 passed, 35 skipped, 4 failed, 1 warning**. As 4 falhas são:
  - 2 de `tests/test_db.py` (lista acima, arquivo fora do escopo autorizado);
  - 2 de `tests/test_secrets_hygiene.py` (`test_real_starter_archive_is_safe_and_keeps_scripts_executable`
    e `test_extracted_starter_runs_contract_snapshot_and_backup_import`), ambientais por **não haver
    mount do `.git`** no container: o empacotador não consegue listar os arquivos rastreados e aborta
    sem vazar conteúdo. Passam quando o `.git` é montado somente leitura; não é regressão desta fatia.

Os testes cobrem: estimativa não vira `ACTUAL`; `ACTUAL` exige evidência e usa o valor cobrado;
reconciliação `ESTIMATE`→`ACTUAL`, `UNCERTAIN`→`ACTUAL` e `ESTIMATE`→`FREE`; teto mensal por mês
corrente e teto por vídeo conservador; reserva antiga não bloqueia e é reportada; operação `RESERVED`
parada é reportada com `stalled_for`; legado finito conta e NaN bloqueia; operação de projeto sem
vídeo; HTTP 403/409/422/404 com mensagem por estado; `RELEASED` reabre e `CONFIRMED` não; erro de
`confirm` marca `UNCERTAIN` (preservando a causa quando o mark também falha); saída paga inválida
(roteiro, imagem e ideias) fica `UNCERTAIN`; falha pré-efeito libera; `KeyboardInterrupt` não é
engolido; voz por conteúdo sem cobrança dupla, com replay grátis só quando `FREE`.

## Limitações, riscos e pendências operacionais

- **`pending_reconciliation` não é acionável por si só**: lista reservas antigas, `UNCERTAIN`,
  `RESERVED` paradas (limiar 15 min, sem heartbeat) e legado não confirmado, mas não há API, fila,
  runbook nem expiração automática; a decisão é manual (`confirm`/`release`/`reconcile_actual`).
- **`legacy_unconfirmed_ledger` cresce para sempre**: toda linha histórica sem
  `cost_confirmation_kind` continua aparecendo na lista, sem forma de marcá-la como revisada. É uma
  pendência operacional explícita (política de arquivamento/aceite do legado ainda não existe); até
  então a lista cresce monotonicamente.
- **Parada é visibilidade, não heartbeat**: `stalled_operation` usa `updated_at`; uma chamada
  legítima mais longa que 15 min aparece como parada até terminar. Nada é encerrado automaticamente.
- **`CONFIRMED` sem resultado**: crash após confirmar deixa a operação terminal; o retry é recusado e
  a reutilização de resultado/asset não existe nesta fatia (D2).
- **`settled_by` descartado em `ACTUAL`**: ver seção própria acima; quem assina é
  `charge.declared_by`.
- **Precisão do ledger legado**: `numeric(12,6)` e domínio legado em `float`; zero não prova
  gratuidade e positivo sem evidência não prova custo real.
- **`ESTIMATE` pode divergir**: até a reconciliação, o teto usa o valor estimado; subestimação
  sistemática ainda pode furar o orçamento real.
- **O teto não é hard limit**: limites são argumentos por chamada; o ledger legado ainda pode receber
  despesas sem reservar e não verifica limites. Com o guard desligado (padrão), nada muda.
- **Voz `FREE`**: replay reexecuta a síntese (evita reserva/cobrança, não o custo local).
- **Atomicidade**: reserva + intenção e confirmação (ledger + estado + remoção da reserva) são
  transacionais; queda no meio deixa `RESERVED`/`UNCERTAIN` para reconciliação.
- **Índices**: a `0020` usa `CREATE INDEX` transacional (bloqueia escritas na construção); em tabela
  grande, criar concurrentemente fora da migração.
- **Testes de PostgreSQL** exigem banco exclusivamente descartável e prova privada; sem isso são
  ignorados, não aprovados.
- **Arquivos compartilhados**: `composition.py` não foi tocado nesta rodada; `tests/test_db.py` foi
  deliberadamente preservado (ver falha esperada). Mudanças de outros agentes no worktree
  (`api/panel.py`, `test_panel*.py`, `0018_*`, `production_repo.py`, `ports.py`,
  `domain/production_run.py`, `test_production_repo.py`, `test_production_run.py`,
  `0021_channel_pillars_constraints.sql`, `test_channel_migrations.py`) **não** entraram no commit.

## Fora de escopo desta fatia

- Preços de provedor verificados, chamadas reais, publicação YouTube/n8n.
- Reconciliação automática, expiração de reservas, heartbeat de operação, política central de
  limites e UI/API de reconciliação.
- Ledger legado: nenhuma promoção automática de registros a confirmados.
- Reutilização de resultado/asset de operação `CONFIRMED` (D2).

Não afirmo "F1 concluído" nem "hard limit garantido".