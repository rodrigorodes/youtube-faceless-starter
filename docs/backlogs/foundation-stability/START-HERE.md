# Comece aqui — Foundation
1. Leia [README](README.md), [AUDIT-AS-IS](AUDIT-AS-IS.md), [PLAN](PLAN.md) e [QUALITY-GATES](QUALITY-GATES.md).
2. Confirme HEAD, leia [plano de testes](../../plano-de-testes-faceless/CONTINUITY.md), faça preflight FS-02.01 antes de qualquer execução mutável.
3. Use [MASTER-PROMPT](MASTER-PROMPT.md) e [EXECUTION-BACKLOG](EXECUTION-BACKLOG.md); autorize FS-01 como primeiro recorte depois do preflight. Não autorize todos os itens juntos.
4. Execute gates locais e guarde evidência por SHA. Não construir CI/CD.
5. Após regressão confiável, avaliar [FS-08](phases/FS-08-modularization.md) e extrair apenas o que for necessário à fase consumidora. P0 original 2,5–4 dias estimados, Foundation original 4–7 dias, mapa FS-08 adicional 0,5–1 dia; extrações futuras não contabilizadas duas vezes.
6. Entregar evidências à V4-00 e FI-00; completar requisitos próprios sem duplicação.

Nenhum PASS é inferido desta documentação. Sem alterações de código, gasto, publicação ou merge automático.
