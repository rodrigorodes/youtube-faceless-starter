# F1 — guard de orçamento nos caminhos pagos (fatia A)

Commits: `822334a` (fatia original) e o commit de correção desta rodada (revisão independente:
1 crítico + 4 importantes). O hash do commit de correção fica no histórico do worktree; este relatório
foi commitado em seguida.

Esta fatia liga as chamadas pagas (roteiro/editorial, imagem, voz e pontuação de ideias) ao protocolo
de reserva de orçamento já existente e fecha o ciclo de vida da operação paga. **Não** substitui o
ledger legado, não integra reconciliação automática e **não** garante hard limit; os limites continuam
dependendo dos argumentos fornecidos pelo chamador.

## Política de custo adotada (correção do crítico)

Foi escolhida a opção **(a)**: um terceiro tipo explícito `ESTIMATE`, contabilizado como **gasto
aproximado** (não "desconhecido", não `ACTUAL`).

- `CostConfirmation` aceita `ACTUAL` (positivo), `ESTIMATE` (positivo) e `FREE` (zero), sempre com
  referência e responsável não vazios.
- `provider_settlement(entry, *, settled_by, charge=None)`:
  - `settled_by` é obrigatório e nomeia o processo/ator que encerra a operação (sem constante sintética).
  - `charge` (`ChargeEvidence`: valor cobrado + referência + quem declara) ⇒ `ACTUAL` **no valor
    cobrado**; o `UsageEntry` do ledger é atualizado para esse valor.
  - Sem `charge`: zero ⇒ `FREE`; positivo ⇒ `ESTIMATE` (nunca `ACTUAL`).
- `OpenCodeImage` grava `STUDIO_PAID_IMAGE_USD` como estimativa configurável ⇒ agora `ESTIMATE`; o
  dinheiro gasto continua contando no teto, mas o mês **não** é marcado como desconhecido e a
  reconciliação (`reconcile_actual`) troca `ESTIMATE` por `ACTUAL` com evidência, atualizando o ledger
  e a operação na mesma transação (sem duplicar linha).
- Migração `0019_ledger_estimate_and_attribution.sql` (quatro dígitos; `0018` já era da fatia D):
  permite `ESTIMATE` nos CHECKs de `usage_ledger` e `paid_operations`, e permite `video_id NULL` em
  `paid_operations`/`budget_reservations` para operações de projeto.

## Correções desta rodada, item a item

1. **Crítico — estimativa virava `ACTUAL`**: resolvido com `ESTIMATE` + `ChargeEvidence`, conforme
   acima. Testes: `test_provider_settlement_never_promotes_an_estimate_to_actual`,
   `test_provider_settlement_accepts_actual_only_with_charge_evidence`,
   `test_confirm_estimate_counts_as_approximate_spend_and_is_not_unknown`,
   `test_reconcile_actual_replaces_the_estimate_with_evidence`.
2. **Reservas antigas bloqueavam o mês para sempre**: `_reserve_within` soma, no teto mensal, apenas
   ledger e reservas do mês corrente (UTC). Reservas de meses anteriores não consomem o mês atual, mas
   aparecem em `pending_reconciliation()` como `stale_reservation`. O teto por vídeo continua
   conservador (soma tudo do vídeo). Teste:
   `test_previous_month_reservation_does_not_block_the_current_month_and_is_reported`.
3. **`ScoreIdeas` contaminava o mês**: quando o guard está ligado, `ScoreIdeas` passa pelo mesmo ciclo
   de operação paga (com `video_id=None`, limitado só pelo teto mensal) e grava `ESTIMATE`/`ACTUAL`/
   `FREE` em vez de linha sem confirmação. Política do legado: só `cost_usd = NaN` é "desconhecido" e
   bloqueia; linha legada finita conta pelo valor gravado (zero inclusive) e é **reportada** como
   `legacy_unconfirmed_ledger`/`unknown_ledger_cost` em `pending_reconciliation()`. Não foi afrouxado
   fail-closed para NaN. Testes:
   `test_score_ideas_routes_through_the_paid_guard_without_a_video`,
   `test_finite_legacy_cost_counts_but_nan_is_still_unknown`,
   `test_finite_legacy_zero_is_not_unknown_but_nan_still_blocks`,
   `test_positive_legacy_cost_counts_as_provisional_spend`.
4. **HTTP 500**: `BudgetDenied` → 403; `OperationInProgress`/`OperationSettled`/`OperationUncertain`/
   `InvalidOperationTransition` → 409 (conflito com o estado persistido; 429 foi descartado porque não
   é limite de taxa); `UnknownPaidOperation` → 404. Mensagens públicas, sem vazar chave/estado interno.
   Teste de contrato: `tests/test_budget_http.py`.
5. **Voz paga impossível e retentativa cobrava de novo**: a chave passou a ser por conteúdo (`vídeo`,
   cena, voz, modelo, texto narrado), não por `job.id`. A liquidação segue a política acima:
   `FREE` comprovado, `ACTUAL` só com `charge_evidence` do adapter, senão `ESTIMATE` (sem `None`
   incondicional). `FREE` confirmado pode ser reexecutado sem nova reserva (`allow_free_replay`);
   `ESTIMATE`/`ACTUAL` reexecutado levanta `OperationSettled` e não cobra de novo. Testes:
   `test_two_jobs_with_the_same_narration_do_not_charge_twice`,
   `test_free_voice_retry_reexecutes_without_a_second_charge`,
   `test_confirmed_estimate_operation_cannot_replay_for_free`.
6. **Confirmação antes da validação**: `paid.run` ganhou `validate(result)`, executado depois da
   chamada paga e antes de encerrar o custo. Saída inválida (roteiro fora do contrato; imagem sem
   licença/mime inválido) ⇒ `UNCERTAIN` com motivo, sem `CONFIRMED` e sem liberar. Testes:
   `test_invalid_script_after_a_successful_paid_call_stays_uncertain`,
   `test_invalid_image_after_a_successful_paid_call_stays_uncertain`,
   `test_invalid_paid_output_stays_uncertain_not_confirmed`.
7. **`settle` deixava `RESERVED` eterno**: falha `PreEffectFailure` no `settle` (e também na
   validação) libera a reserva com motivo; qualquer outra exceção de liquidação marca `UNCERTAIN`.
   Teste: `test_pre_effect_failure_during_settlement_releases`,
   `test_unconfirmable_settlement_marks_uncertain`.
8. **`BaseException` largo demais**: `run` captura `Exception` para marcar `UNCERTAIN`/liberar e deixa
   `KeyboardInterrupt`/`SystemExit` subirem sem engolir; a reserva permanece `RESERVED` para
   reconciliação explícita (documentado). Teste:
   `test_keyboard_interrupt_is_not_swallowed_and_keeps_the_reservation`.
9. **`STUDIO_BUDGET_GUARD` documentado** em `.env.example`: `0`/`off` (padrão) não cria reserva
   alguma e vale só a pré-checagem antiga; `1`/`on` exige reserva e marca custo sem evidência como
   `ESTIMATE`.

## O que já existia na fatia original

- `PaidOperationState` (`RESERVED`, `CONFIRMED`, `RELEASED`, `UNCERTAIN`), `BeginResult` não booleano,
  porta `PaidOperationRepository`, `PreEffectFailure` e `PaidOperationGuard.run`.
- `0017_paid_operations.sql` (quatro dígitos; `0016` já era da fatia C — canais).
- Wiring opt-in (`paid` opcional) em `GenerateScript`, `ProduceAssets`, `RunRender` e, agora,
  `ScoreIdeas`; `composition.py` cria o guard quando `Settings.budget_guard` (env
  `STUDIO_BUDGET_GUARD`) está ligado, desligado por padrão.
- `text_opencode.py`/`image_opencode.py`: 4xx imediato, conexão não estabelecida e divergência de
  modelo levantam `PreEffectFailure` (subtipo de `ModelUnavailable`).

## Regras não negociáveis — como ficaram

1. Só a chamada que recebeu `CREATED` executa o provedor. Replay (`IN_PROGRESS`/`CONFIRMED`/`RELEASED`/
   `UNCERTAIN`) levanta erro explícito e não chama o provedor de novo — exceto replay de operação
   confirmada como `FREE` no caminho de voz, que reexecuta sem nova reserva.
2. Custo só é aceito com confirmação estruturada (`ACTUAL`/`ESTIMATE`/`FREE`); `confirm` grava o
   lançamento e apaga a reserva na mesma transação.
3. Resultado ambíguo ou saída paga inválida → `UNCERTAIN`, reserva permanece e novas execuções da
   chave são recusadas até reconciliação.
4. Falha comprovadamente pré-efeito → `release` com motivo registrado.
5. Nenhuma chave de API, chamada de rede real ou publicação: testes usam provedores/repositórios
   falsos; a integração PostgreSQL usa banco descartável com prova privada.

## TDD — RED e GREEN medidos

RED demonstrado contra o commit anterior (`git archive HEAD` em cópia isolada, sobreposta apenas com os
testes novos e a migração `0019`; implementação antiga intacta):

- 21 falhas, incluindo `provider_settlement() got an unexpected keyword argument 'settled_by'`,
  `assert ('confirm', ..., 'ESTIMATE', ...) in [...] ('confirm', ..., 'ACTUAL', ...)` (código antigo
  emitia `ACTUAL` para estimativa), ausência de `validate`/`allow_free_replay`,
  `PreEffectFailure` no `settle` deixando `RESERVED`, `KeyboardInterrupt` marcado `UNCERTAIN`, e
  `test_budget_http` falhando porque `BudgetDenied`/`OperationInProgress`/`OperationSettled`/
  `OperationUncertain`/`InvalidOperationTransition` não eram mapeados (saíam como erro não tratado).
- GREEN após a implementação: **117 passed** nos arquivos focados
  (`test_budget_guard.py`, `test_paid_operations.py`, `test_budget_reservations.py`, `test_db.py`,
  `test_budget_http.py`).
- Suíte completa: **1522 passed, 35 skipped, 1 warning** (depreciação do Starlette).

## Testes — comandos e resultados reais

Imagem local `faceless-v2-hygiene-test-local:latest` (Python 3.12 + pytest), rede Docker isolada
(`f1b-net`), PostgreSQL 16 descartável (`f1b-pg`, tmpfs) e prova de 32 bytes montada em
`/budget-test-proof` (somente leitura) no banco e no runner:

```
docker run --rm --network f1b-net \
  -v "$PWD":/workspace:ro \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro \
  -v <proof_dir>:/budget-test-proof:ro -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1b-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1b-pg:5432/postgres \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest -p no:cacheprovider ...
```

- Focados (`test_budget_guard.py`, `test_paid_operations.py`, `test_budget_reservations.py`,
  `test_budget_http.py`): **102 passed**.
- `tests/test_db.py`: **15 passed** (inclui `0018_production_runs` e `0019_...` nas duas listas e as
  tabelas `production_runs`/`stage_executions`/`production_outbox`).
- Suíte completa: **1522 passed, 35 skipped, 1 warning**. Nenhuma falha.

Os testes cobrem: estimativa não vira `ACTUAL`; `ACTUAL` exige evidência e usa o valor cobrado;
reconciliação `ESTIMATE`→`ACTUAL`; teto mensal por mês corrente e teto por vídeo conservador; reserva
antiga não bloqueia e é reportada; legado finito conta e NaN bloqueia; operação de projeto sem vídeo;
HTTP 403/409/404; saída paga inválida fica `UNCERTAIN`; falha pré-efeito no `settle` libera;
`KeyboardInterrupt` não é engolido; voz por conteúdo sem cobrança dupla, com replay grátis só quando
`FREE`; e o wiring dos caminhos pagos e de `ScoreIdeas`.

## Limitações e riscos (explícitos)

- **Precisão do ledger legado**: `usage_ledger.cost_usd` é `numeric(12,6)` e o domínio legado usa
  `float`; valores podem já ter sido arredondados ou subestimados, inclusive custos muito pequenos
  representados como zero. Zero não prova gratuidade e positivo sem evidência não prova custo real.
- **Estimativa pode divergir**: `ESTIMATE` é aproximação; até a reconciliação, o teto usa o valor
  estimado. Uma subestimação sistemática ainda pode furar o orçamento real.
- **Sem reconciliação automática**: `UNCERTAIN`, reservas antigas e linhas legadas não confirmadas
  aparecem em `pending_reconciliation()`, mas não há API, fila, trilha imutável nem runbook nesta
  fatia; a decisão é manual, chamando `confirm`/`release`/`reconcile_actual` no repositório.
- **O teto não é hard limit**: os limites são argumentos por chamada; o ledger legado ainda pode
  receber despesas sem reservar e não verifica limites (o trigger só serializa a escrita). Com o
  guard desligado (padrão), nada muda no comportamento atual. Um chamador que informe limites maiores
  pode furar a política.
- **Voz real**: o Piper é local/gratuito ⇒ `FREE` e replay sem nova reserva. Uma voz paga que só
  informe estimativa fica `ESTIMATE` (reconciliação posterior); uma voz que exponha
  `charge_evidence` pode declarar `ACTUAL`.
- **Replay de voz `FREE`**: reexecuta a chamada (não reusa o áudio do job anterior); o que se evita é
  nova reserva/cobrança, não o custo local de sintetizar.
- **Atomicidade**: reserva + intenção são gravadas numa transação sob o lock; confirmação (ledger +
  estado + remoção da reserva) também. Se o banco cair no meio, a operação pode permanecer
  `RESERVED`/`UNCERTAIN` e exigir reconciliação — não é resolvida automaticamente.
- **Testes de PostgreSQL** exigem banco exclusivamente descartável e prova privada; sem isso os testes
  são ignorados, não aprovados.
- **Arquivos compartilhados**: nesta rodada `composition.py` (linha `paid=paid_guard` em `ScoreIdeas`)
  e `tests/test_db.py` (listas de migração + três tabelas da fatia D) foram tocados deliberadamente,
  com apenas essas mudanças; o restante das mudanças de outros agentes no worktree
  (`production_repo.py`, `ports.py`, `domain/production_run.py`, `test_production_repo.py`,
  `test_production_run.py`, e o diff posterior de `0018_production_runs.sql`) **não** entrou no commit.
- **Flake ambiental**: numa execução anterior da suíte completa, 2 testes de `test_secrets_hygiene`
  falharam porque o `.git` compartilhado do worktree estava sendo escrito por outro agente durante o
  empacotamento (o script aborta sem vazar conteúdo). Os mesmos testes passam isolados, em repetição,
  e na execução completa final sem falhas.

## Fora de escopo desta fatia

- Preços de provedor verificados, chamadas reais, publicação YouTube/n8n.
- Reconciliação automática, expiração de reservas, política central de limites e UI/API de
  reconciliação.
- Ledger legado: nenhuma promoção automática de registros a confirmados.

Não afirmo "F1 concluído" nem "hard limit garantido".