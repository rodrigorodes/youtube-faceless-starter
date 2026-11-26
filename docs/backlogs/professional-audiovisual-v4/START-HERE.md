# Faceless Studio V4
Projeto de evolução, não implementação. Base auditada: 352dfd7b60392abf6d3e9e543ed8c42c14b5a7e6.
Leia MASTER-PROMPT.md, PLAN.md, CURRENT-VS-TARGET.md, ARCHITECTURE.md e QUALITY-GATES.md. Execute somente V4-00 inicialmente. Não publique vídeos nem execute serviços pagos sem autorização. Registre evidências em cada fase e solicite aprovação antes de avançar. As fases são propostas; confirme os símbolos e testes no checkout atual.

## Revisão V4.1 (2026-11-25)
Leia [consolidação](V4.1-CONSOLIDATION.md), [pilotos](PROFESSIONAL-PILOT-SPEC.md) e [Finder Intelligence](../finder-intelligence-v1/README.md) antes da V4-00. Escopo documental; nenhuma fase autorizada automaticamente.

## Preparação enxuta (25/11/2026)
Antes de iniciar novas funcionalidades, executar a [Foundation & Stability](../foundation-stability/README.md). Sem CI/CD nesta etapa; gates locais obrigatórios. Reutilizar plano de testes da main e evidências na V4-00.

## Google AI Pro — complemento audiovisual
Após Foundation/V4-00, leia [integração](GOOGLE-AI-PRO-INTEGRATION.md) e [backlog GAI](GAI-EXECUTION-PLAN.md). Priorizar importação genérica + modo assistido, sem API paga obrigatória. Não usar autenticação de assinatura em ferramentas não autorizadas. APIs/Drive são opt-in por fase.

## Recuperação de integração — develop (26/11/2026)
A develop contém V4-01–13 implementadas em diferentes níveis de maturidade. Não tratar relatórios GO como homologação do produto. A entrada para continuar nessa branch é [Integration & Stabilization](integration-stabilization/README.md), começando exclusivamente pela auditoria INT-01 quando autorizada. O fluxo original e IDs V4 permanecem válidos; main preservada e merge bloqueado até gate final e autorização.

## Recuperação REC — gate >=9/10 (26/11/2026)
A develop 72438e9 segue NO-GO. A entrada ativa é [PROMPT-MASTER de recuperação](integration-stabilization/PROMPT-MASTER.md), com [backlog REC](integration-stabilization/RECOVERY-BACKLOG.md), [roteamento](integration-stabilization/MODEL-ROUTING.md) e [rubrica](integration-stabilization/QUALITY-RUBRIC.md). Não usar GO histórico como aceite; execução técnica contínua apenas quando operador iniciar a campanha, sem merge/publicação/gasto e com gates independentes.
