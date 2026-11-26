# V4-11 — Asset Management
Status: concluído. Dependências: 00; fundação antes de 02–05.

## Atividades
- [x] V4-11.01 — Consolidar registry. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.02 — Hash. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.03 — Deduplicação. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.04 — Provider modelo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.05 — Autor licença origem. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.06 — Evidência licença. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.07 — Bloquear licença desconhecida. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.08 — Versionar assets. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.09 — Indexar tags. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.10 — Cache geração. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.11 — Cache render. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.12 — Limpeza órfãos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.13 — Backup. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-11.14 — Storage alternativo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Licença desconhecida bloqueia publicação; hash e referências preservados; restauração testada.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-11 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Complemento GAI-01/07
Ingestão genérica com validação, licença, hash/escopo, mídia tipada e paths seguros; storage local canônico para render. Drive P2 como cópia complementar com OAuth próprio, escopo mínimo, verificação e restore. Não substituir backup integral. [GAI](../GAI-EXECUTION-PLAN.md).
