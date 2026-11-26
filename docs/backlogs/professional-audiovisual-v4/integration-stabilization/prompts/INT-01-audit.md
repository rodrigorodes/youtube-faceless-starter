# INT-01 — Prompt de auditoria (Gemini 4 Neon High)

Atue como Staff Software Architect independente. Trabalhe em develop, referência 0257c045dbff8ef3f78b4f8ffba76b20db226433; confirme HEAD e instruções AGENTS.md. Main be0c463 é baseline preservado. Leia ../README.md, ../AUDIT-FINDINGS.md, ../EXECUTION-BACKLOG.md, ../QUALITY-GATES.md, ../../PLAN.md, ../../MASTER-PROMPT.md, fases, GAI-EXECUTION-PLAN e PROFESSIONAL-PILOT-SPEC.

Execute apenas INT-01. Não altere código funcional, não execute chamadas pagas, não publique, não faça merge. Produza relatório de auditoria documental e plano. Não assuma que os 13 relatórios GO são homologação. Verifique cada achado A01–A13 por código e consumidores reais; procure imports/chamadas, composição, rotas, worker, SQL, compiladores, UI e testes. Distinga comportamento herdado de novo. Reproduza somente testes mínimos offline e isolados se necessários; não invente saídas.

Entregue:
1. Matriz de todos os IDs originais V4 e GAI (contagem real): requisito, símbolo/caminho, consumidor real, artefato, teste, evidência, status G1, lacuna/ação e prioridade. Se não puder completar, indique IDs não auditados e NO-GO para escopo não verificado.
2. AS-IS com caminho executável e TO-BE incremental, inventário de código desconectado/duplicado/simulado e decisão reusar/integrar/desabilitar/remover (remoção somente justificada).
3. Confirme P0: Kokoro senoidal, ElevenLabs stub, limites do compilador, transformações/transições, benchmark manual, reconciliação após restart. Avalie custo, autorização, isolamento, segurança, licenças e riscos de schema/hash.
4. Backlog refinado INT-02–07 com tarefas pequenas, teste falhando antes da correção, teste de consumidor e artefato real, dependências, rollback, modelo executor e review.
5. Evidências com SHA/estado/arquivo/linhas/comando/resultado real e riscos pendentes. Não declarar execução de teste que não ocorreu.
Pare ao entregar a auditoria e aguarde aprovação explícita. Não iniciar INT-02.
