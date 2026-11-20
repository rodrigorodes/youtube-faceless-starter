# F1 — fatia de reservas de orçamento

## Entrega e decisões

- Porta `BudgetReservationRepository` e adaptador PostgreSQL com migração `0013`.
- Lock consultivo transacional único antes das leituras serializa reservas entre vídeos e chaves; trigger no ledger usa o mesmo lock para suas escritas. Conexões em autocommit são recusadas e o snapshot é READ COMMITTED.
- Limite mensal global usa gastos do mês UTC no `usage_ledger`, inclusive lançamentos sem vídeo, mais **todas** as reservas ainda ativas, mesmo de meses anteriores. O limite por vídeo usa todo o gasto histórico daquele vídeo e suas reservas. Comparações e agregações usam `numeric` no banco, evitando arredondamento do contexto Decimal do Python.
- Chave de uma reserva bem-sucedida é única; repetição com vídeo, valor e limites iguais retorna sucesso, divergência gera `IdempotencyConflict`. Recusas por limite não criam registro de idempotência.
- A reserva permanece ativa indefinidamente: não há expiração automática, liberação nem reconciliação nesta fatia. Não há chamadas a fornecedores.
- O schema existente possui gastos `numeric(12,6)` e valor mensal por projeto, mas não um orçamento global persistido; limites são argumentos explícitos do chamador, que deverá fornecer valores consistentes e confiáveis. A regra pura `Budget` existente é trabalho não commitado de outro agente e não é dependência deste commit.

## Limitações e riscos

- Isto não integra o budget aos provedores nem completa F1. Não oferece contabilização atômica do custo real, reconciliação de respostas incertas, liberação de reservas ou transição de estado. A implementação futura deverá manter o mesmo lock e gravar ledger/reconciliação atomicamente, sem dupla contagem.
- O ledger legado ainda pode receber despesas sem reservar, inclusive depois de uma reserva, e não verifica limites; o trigger só serializa a escrita. Portanto não existe proteção global efetiva enquanto os caminhos pagos não forem integrados à porta.
- O limite é informado por chamada, não há configuração central autoritativa nem controle de alteração concorrente de política; um chamador que forneça limites maiores pode ultrapassar a política desejada.
- O lock global reduz paralelismo. Transações externas longas que escrevem no ledger podem bloquear reservas; escritores em lote devem observar a ordem de locks. A fixture global do projeto remove o schema `studio`: todos os testes com DSN foram executados exclusivamente em container PostgreSQL descartável com rede isolada.

## Testes

- TDD: testes de integração inicialmente falharam por ausência do adaptador; teste de precisão reproduziu arredondamento e teste de autocommit reproduziu transação insegura antes das correções.
- Concorrência com conexões distintas: vídeos disputando limite global, repetição concorrente da mesma chave e lançamento de ledger não commitado bloqueando reserva. Também cobertos limites, gastos, mês UTC, idempotência conflitante, precisão e valores inválidos.
- Suíte completa em Python 3.12.16 e PostgreSQL 16 descartável: **891 passed, 34 skipped**, uma advertência de depreciação do Starlette.
- A imagem solicitada `faceless-v2-local-test` não possui pytest. Foi usada `faceless-v2-hygiene-test-local`, disponível localmente e com Python 3.12.16 e pytest; nenhuma dependência foi instalada nem serviço compartilhado acessado.
- Na primeira execução da suíte, duas expectativas de migração precisaram ser atualizadas; dois testes de empacotamento falharam porque o metadata Git do worktree não estava montado no container. Com o metadata montado em leitura e configuração Git local ao processo, a suíte passou como acima.
