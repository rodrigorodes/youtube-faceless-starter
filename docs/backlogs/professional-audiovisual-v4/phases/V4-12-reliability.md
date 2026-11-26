# V4-12 — Reliability & Scale
Status: concluído. Dependências: 00; transversal.

## Atividades
- [x] V4-12.01 — Checkpoints. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.02 — Idempotência. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.03 — Lease. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.04 — Restart. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.05 — Concorrência. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.06 — Backpressure. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.07 — Budget etapa. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.08 — Budget canal. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.09 — Timeout. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.10 — Retry limitado. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.11 — Evitar cobrança duplicada. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.12 — Métricas logs. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.13 — Readiness. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.14 — CI gates. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.15 — Restore backup. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-12.16 — Isolamento tenant antes SaaS. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Testes de falha e restart; nenhuma cobrança duplicada em fixture; limites e readiness verificáveis.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-12 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Complemento GAI-09/06
Reusar Budget Guard e UsageRepository; separar billing local/assistido/API, estimativa, reserva e custo efetivo/subsídio, sem dupla contagem. Operação Veo assíncrona: reconciliar antes de retry, sem segundo submit pago. [GAI](../GAI-EXECUTION-PLAN.md).
