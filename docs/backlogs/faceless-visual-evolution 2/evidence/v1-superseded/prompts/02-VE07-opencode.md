# Prompt OpenCode — VE-07 Production Workspace

Você é responsável por preparar e executar **somente a fase VE-07 autorizada** do Faceless Studio. Leia, nesta ordem:
1. `README.md` e `RULES.md` deste backlog.
2. `PLAN-VE00-VE06-AS-RECEIVED.md`, `evidence/ve-00-review.md` e status real de VE-00 a VE-06.
3. `phases/VE-07-production-workspace.md`, `ux/UX-SPEC.md` e `prototype/index.html`.
4. Código atual (não assuma que o ZIP representa HEAD): shell V3, painéis, contratos, serviços, testes, migrations, ADRs V3.1.

## Missão
Construir um workspace por vídeo com dois modos (Automático/Assistido), sem segundo pipeline, sem editor NLE e sem provider pago implícito. Reutilizar a arquitetura atual. O HTML é referência UX, **não** código de produção nem especificação de backend.

## Primeira resposta (sem editar produção)
- Comparar protótipo com UI atual e funcionalidades realmente implementadas.
- Listar reuso, lacunas e contratos reais; marcar fatos vs hipóteses.
- Propor VE07-00 a VE07-07 com arquivos exatos, testes, critérios de aceite, dependências e riscos.
- Corrigir inconsistências residuais do PLAN original sem apagar seu histórico.
- Aguardar autorização explícita para a primeira fase de código.

## Regras de execução após autorização
- Implementar apenas uma subfase por vez; testes e evidências antes de próxima.
- Operações de edição versionadas (expected_revision + idempotency_key), invalidação de dependências, checkpoint seguro.
- Gate de aprovação validado no servidor com render_id/checksum; nenhuma mutação preserva aprovação obsoleta.
- Nenhum dado de custo, licença, QA ou progresso inventado.
- Testes no container e Postgres isolado; não apagar dados sem permissão.
- Não criar novo RenderPlan, renderer, coordinator, banco ou workflow.
- Não executar publicação externa, commits ou migrações destrutivas sem autorização.
- Fornecer relatório por subfase: arquivos, contratos, comandos, resultados, evidências e riscos.
