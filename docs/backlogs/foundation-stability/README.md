# Foundation & Stability — preparação enxuta
Status: abordagem aprovada pelo operador em 25/11/2026; implementação pendente. Baseline auditado: main b642f44. Esta iniciativa antecipa fundações de V4-00/V4-12/FI-00, não constitui um terceiro MVP.

## Princípio de produto
**Minha recomendação é manter essa preparação o mais enxuta possível.** Nosso objetivo principal é melhorar o produto, não construir uma infraestrutura corporativa antes de validar seu valor comercial.

Preservar monólito modular, PostgreSQL, Docker, FFmpeg, n8n, Registry/Budget Guard e RenderPlan. Reutilizar o [plano de testes existente](../../plano-de-testes-faceless/CONTINUITY.md) como fonte canônica, sem criar uma campanha concorrente. Priorizar estabilidade, capacidade de produzir vídeo e feedback do usuário.

## Escopo
FS-01 testes; FS-02 ambientes; FS-04 configurações e flags; FS-05 readiness; FS-06 observabilidade/capacidade mínima; FS-07 baseline. FS-03 CI/CD explicitamente adiado (ID reservado). Não adicionar GitHub Actions, deploy automatizado, branch protection obrigatória, Kubernetes, broker, microserviços, multi-tenancy SaaS, stack distribuída de observabilidade ou refactor generalizado nesta entrega. Preservar workflow de higiene existente.

## Sequência
[Auditoria](AUDIT-AS-IS.md) → [Plano e critérios](PLAN.md) → [Prompt de execução](MASTER-PROMPT.md). V4-00 e FI-00 reutilizam evidências da Foundation, sem repetir trabalho. P0 bloqueia evolução dependente; P1 pode ser entregue em paralelo ou deferido mediante decisão de risco documentada. Nenhuma implementação ou gasto começa automaticamente.
