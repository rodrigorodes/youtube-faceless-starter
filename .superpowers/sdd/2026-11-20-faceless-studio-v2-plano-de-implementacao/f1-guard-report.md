# F1 — guard de orçamento nos caminhos pagos (fatia A)

Commit: `822334a` —"feat: guard paid provider calls behind the budget reservation lifecycle".

Esta fatia liga as chamadas pagas (roteiro/editorial, imagem e voz) ao protocolo de reserva de
orçamento já existente e fecha o ciclo de vida da operação paga. **Não** substitui o ledger legado,
não integra reconcilição automática e **não** garante hard limit; os limites continuam dependendo
dos argumentos fornecidos pelo chamador.

## O que foi implementado

- `renderer/app/studio/application/budget.py`
  - `PaidOperationState` (`RESERVED`, `CONFIRMED`, `RELEASED`, `UNCERTAIN`).
  - `BeginResult` (`CREATED`, `IN_PROGRESS`, `CONFIRMED`, `RELEASED`, `UNCERTAIN`, `DENIED`), não booleano.
  - `CostConfirmation` com `ACTUAL` (positivo) ou `FREE` (zero), referência e responsável obrigatórios.
  - Porta `PaidOperationRepository` (`begin`/`confirm`/`release`/`mark_uncertain`/`state`).
  - `PreEffectFailure(ModelUnavailable)`: falha comprovadamente sem efeito externo.
  - `PaidOperationGuard.run`: reserva, executa uma única vez, e encerra em CONFIRMED, RELEASED ou UNCERTAIN.
- `renderer/app/studio/adapters/postgres/budget_repo.py`: lógica de reserva extraída para `_reserve_within`
  (mesmo lock consultivo `726002` e mesma checagem de limites do `PostgresBudgetRepository`) e novo
  `PostgresPaidOperationRepository`, que grava a intenção na mesma transação da reserva.
- `migrations/0017_paid_operations.sql` (quatro dígitos; **0016** já havia sido usado pela fatia C — canais):
  tabela com CHECK de estado/confirmação, FK para `usage_ledger` e índices.
- Wiring (parâmetro opcional `paid`): `GenerateScript` (roteiro), `ProduceAssets` (imagem) e `RunRender` (voz).
- `composition.py`: cria o guard quando `Settings.budget_guard` (env `STUDIO_BUDGET_GUARD`) está ligado;
  **desligado por padrão**, preservando o comportamento atual.
- `adapters/text_opencode.py` e `adapters/image_opencode.py`: 4xx imediato, conexão nunca estabelecida e
  divergência de modelo passam a levantar `PreEffectFailure` (subtipo de `ModelUnavailable`).

## Regras não negociáveis — como ficaram

1. Só a chamada que recebeu `CREATED` executa o provedor. Replay (`IN_PROGRESS`/`CONFIRMED`/`RELEASED`/`UNCERTAIN`)
   levanta erro explícito e **não** chama o provedor de novo.
2. Custo só é aceito com confirmação estruturada; sem confirmação a reserva continua ativa bloqueando o valor.
   `confirm` grava o lançamento confirmado e apaga a reserva **na mesma transação**.
3. Resultado ambíguo (timeout, conexão interrompida, custo ilegível) → `mark_uncertain`, a reserva permanece e
   novas execuções da chave são recusadas até `confirm`/`release` explícito (reconciliação).
4. Falha conhecida antes de efeito externo → `release` com motivo registrado.
5. Nenhuma chave de API, chamada de rede real ou publicação: testes usam provedores e repositórios falsos;
   a integração PostgreSQL usa banco descartável com prova privada.

## TDD

- RED: `tests/test_budget_guard.py` e `tests/test_paid_operations.py` foram escritos antes da implementação e
  falharam na coleta (`ImportError: cannot import name 'BeginResult' from 'app.studio.application.budget'`),
  além da migração inexistente.
- GREEN: após a implementação, `38 passed` nos dois arquivos novos.

## Testes — comandos e resultados reais

Imagem local `faceless-v2-hygiene-test-local:latest` (Python 3.12.16 + pytest), rede Docker isolada
própria (`f1-guard-net`), PostgreSQL 16 descartável (`f1-guard-pg`, tmpfs) e prova de 32 bytes montada
em `/budget-test-proof` (leitura apenas) no banco e no runner:

```
docker network create f1-guard-net
docker run -d --name f1-guard-pg --network f1-guard-net -e POSTGRES_PASSWORD=test \
  -v <proof_dir>:/budget-test-proof:ro --tmpfs /var/lib/postgresql/data postgres:16-alpine
docker run --rm --network f1-guard-net \
  -v "$PWD":/workspace:ro \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro \
  -v <proof_dir>:/budget-test-proof:ro -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@f1-guard-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f1-guard-pg:5432/postgres \
  -w /workspace faceless-v2-hygiene-test-local:latest python -m pytest ...
```

- `tests/test_budget_guard.py tests/test_paid_operations.py`: **38 passed**.
- Suites focadas (editorial, media, render, reservas, composição, arquitetura, ports, ideias, adaptadores de
  texto/imagem, alertas, APIs e provedores, guard/pagas): **89 passed**.
- Suíte completa: **1157 passed, 35 skipped, 4 warnings** (uma delas depreciação do Starlette; as demais são
  avisos do pytest por o worktree estar montado somente leitura). Nenhuma falha.

Os testes cobrem: replay sem segunda chamada; limite global mensal e por vídeo respeitando reservas ativas;
bloqueio e reconciliação de resultado incerto; `ACTUAL` gravando custo e liberando; `FREE` liberando sem custo;
liberação em falha conhecida; recusa por autocommit/prova inválida; e o wiring dos três caminhos pagos com o
guard injetado.

## Limitações e riscos (explícitos)

- **Precisão do ledger legado**: `usage_ledger.cost_usd` é `numeric(12,6)` e o domínio legado usa `float`;
  valores podem já ter sido arredondados ou subestimados, inclusive custos muito pequenos representados como
  zero. Zero não prova gratuidade e positivo não prova custo real (o `OpenCodeImage` grava estimativa).
- **Sem reconciliação automática**: um estado `UNCERTAIN` permanece gravado e bloqueando até que um operador
  chame `confirm` ou `release`. Não há API, fila, trilha imutável nem runbook nesta fatia; essas operações
  existem apenas no repositório.
- **O teto não é hard limit**: os limites são argumentos por chamada; o ledger legado ainda pode receber
  despesas sem reservar e não verifica limites (o trigger só serializa a escrita). Com o guard desligado
  (padrão), nada muda no comportamento atual. Um chamador que informe limites maiores pode furar a política.
- **ScoreIdeas (pontuação de ideias)** continua usando só a checagem prévia `CostGuard`, não o ciclo de reserva.
- **Voz**: o Piper real é local/gratuito → confirmação `FREE`. Uma voz futura que informe estimativa positiva
  mas não devolva custo real fica `UNCERTAIN` (não se presume `ACTUAL` a partir de estimativa).
- **Atomicidade**: reserva + intenção são gravadas numa transação sob o lock; confirmação (ledger + estado +
  remoção da reserva) também. Se o banco cair no meio, a operação pode permanecer `RESERVED`/`UNCERTAIN` e
  exigir reconciliação — não é resolvida automaticamente nem há dupla contagem intencional.
- **Testes de PostgreSQL** exigem banco exclusivamente descartável e prova privada; sem isso os testes são
  ignorados, não aprovados.
- **Arquivos compartilhados**: `composition.py` e `tests/test_db.py` também recebem a fatia C (perfil de canal,
  ainda não commitada). Para não arrastar trabalho de outro agente, o commit gravou versões que contêm apenas
  as minhas mudanças; o worktree preserva as mudanças de C. A ativação do guard em `composition.py` está no
  commit, mas com `STUDIO_BUDGET_GUARD` desligado por padrão.

## Fora de escopo desta fatia

- Preços de provedor verificados, chamadas reais, publicação YouTube/n8n.
- Reconciliação automática, expiração de reservas, política central de limites e UI/API de reconciliação.
- Ledger legado: nenhuma promoção automática de registros a confirmados.

Não afirmo "F1 concluído" nem "hard limit garantido".
