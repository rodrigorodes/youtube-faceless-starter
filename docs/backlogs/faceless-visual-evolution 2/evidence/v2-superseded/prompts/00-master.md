# Prompt mestre — implementar o projeto revisão 2

Você trabalha no repositório real youtube-faceless-starter. A proposta ativa está em `docs/backlogs/faceless-visual-evolution 2/`. Leia START-HERE.md, PROJECT-V2.md, DECISIONS.md, RULES.md, ux/UX-SPEC.md, architecture/DOMAIN-CONTRACTS.md, phases/BACKLOG-V2.md e qa/ACCEPTANCE.md. Leia README do repositório e o status/ADRs de faceless-studio-v31. Os documentos em evidence/v1-superseded e PLAN-VE00-VE06-AS-RECEIVED são históricos.

Objetivo: experiência simples, canal como contexto, vídeo como workspace, edição por cena, N providers e Clean Architecture já existente. Preservar identidade violeta. Um coordenador/RenderPlan/renderer; sem reescrever n8n ou impor SPA.

1. Reconheça escopo autorizado nesta sessão. Não repita pedidos de permissão para trabalho já autorizado. Se a tarefa for apenas análise/documentação, não altere produção.
2. Inventarie rotas, testes, ownership, config efetiva, custos, snapshots e contratos. Diferencie implementado/parcial/proposto/desconhecido.
3. Mapeie tasks do BACKLOG-V2 ao código real e implemente a menor fatia vertical autorizada, respeitando dependências. Sem classes/tabelas duplicadas.
4. Corrija a projeção APPROVED/Publicados na fase UX-01 com teste de comportamento. Não alterar enums sem necessidade.
5. Autosave não gera; comandos de geração respeitam quote/limite/reserva. Retry/resume preservam snapshot; nova geração cria execução conforme lifecycle existente.
6. CAS, idempotência, invalidação e autorização no servidor. Preview obsoleto explícito. Histórico de publicação preservado.
7. Reusar Shot, RenderSpec, effective_config, router e adapters. Sem fornecedor hardcoded no domínio. Capacidades reais controlam a UI.
8. Executar verificações adequadas no container renderer/Postgres conforme instruções reais do repositório. Registrar comandos e falhas pré-existentes; não inventar evidência.
9. Atualizar docs/status e resumir mudança, testes, limitações e próximo item. Não usar demo como prova de integração.

Não executar limpeza de banco, publicação real, chamadas pagas, deploy ou mudanças de credenciais por autorização histórica. Escopo solo não certifica isolamento SaaS: ISO-02 e RELEASE-01 são gates obrigatórios para clientes independentes.
