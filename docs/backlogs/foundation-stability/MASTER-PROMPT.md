# Master Prompt — Foundation & Stability
Você é responsável pela estabilização enxuta do Faceless Studio. Leia README, AUDIT-AS-IS, PLAN, plano de testes canônico e AGENTS.md se existir. Princípio: melhorar o produto, não construir infraestrutura corporativa antes de validar valor comercial.

1. Confirme HEAD limpo, diferenças em relação a b642f44, decisão de UI, ambiente e fase autorizada. Reutilize código, runners e evidências existentes; apresente delta mínimo e critérios.
2. Execute somente FS autorizado; CI/CD FS-03 adiado, nenhum workflow novo, deploy, broker, Kubernetes, multi-tenant ou refactor geral. Não antecipe funcionalidades V4/FI.
3. Antes de qualquer teste mutável, prove isolamento, DB descartável e destino. Sem acesso a volumes de uso, uploads ou custos não autorizados. Não enfraqueça guardas, asserts ou gates.
4. Registre comandos, SHA, resultados, skips, falhas, métricas, artefatos sanitizados e limitação; dados ausentes explícitos. Regressão, review independente e browser/render onde necessário. Não invente PASS, custo ou qualidade.
5. Se gate P0 falhar, interrompa evolução dependente e apresente correção mínima. P1 deferível com aprovação e risco explícito. Entregue evidências reutilizáveis por V4-00/FI-00; não repetir trabalho já comprovado.
6. Solicite GO/NO-GO por incremento; nenhum merge, publicação ou gasto automático. Não criar uma plataforma de testes paralela.

## Revisão 2 — detalhe operacional
Leia START-HERE, EXECUTION-BACKLOG, QUALITY-GATES e STRUCTURAL-EVOLUTION. Preflight FS-02.01 antes de teste mutável. Para cada ID, registrar estado, evidência, SHA, comando, impacto, decisão e rollback; não promover testes de plano sem evidência própria. FS-08.01 após regressão; extrações apenas em recortes autorizados e fases consumidoras, sem mudança de comportamento, preservar fachada/imports/guards/estados/RenderPlan e testes de caracterização. Não duplicar Registry, coordinator, ports ou runner. Manter FS-03 adiado; nenhuma automação de CI/CD. Pare em falha crítica e não altere main diretamente.
