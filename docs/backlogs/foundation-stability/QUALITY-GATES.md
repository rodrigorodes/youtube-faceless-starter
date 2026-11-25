# Quality Gates locais e Definition of Done
Sem CI/CD; preservar higiene de segredos existente. Executar com o plano de testes canônico, não duplicar a campanha. Evidências ligadas ao SHA e configuração efetivos.

| Gate | Critério de saída | Bloqueio |
|---|---|---|
| G0 — preflight | SHA e diff limpos para baseline; autorização; ambiente/DB/volumes descartáveis; secrets sanitizados; publication false; zero custo salvo piloto explicitamente aprovado | Qualquer destino não comprovado, risco de gasto/upload |
| G1 — regressão | FS-01: zero falhas não justificadas, skips motivados, crítica coberta; UI aprovada; comando e exit code | Falha crítica, asserção enfraquecida, teste ignorado sem decisão |
| G2 — contratos/config | FS-04: paridade, kill switch, budget, provider mode, paths; contratos/schema/arquitetura via testes existentes | Segredo, bypass, drift não explicado |
| G3 — E2E/isolamento | FS-02: jornada em stack descartável, browser/JS, QA, aprovação/invalidação e recuperação; zero efeito externo | DB ou storage real, publicação, efeito duplicado |
| G4 — capacidade e diagnóstico | FS-05/06: readiness, observabilidade e limites mínimos proporcionais | P1 deferível com risco explícito, exceto segurança/custo/efeito crítico |
| G5 — baseline | FS-07: fixture reproduzível e referência audiovisual 5–8 min; resultados reais, não meta; autorização e mídia licenciada | Se real indisponível, marcar BLOCKED; não alegar qualidade validada |
| G6 — estrutura | FS-08 por recorte: imports/API/states/timeline preservados, testes de caracterização, rollback | Mudança funcional não aprovada, duplicidade de core |
| G7 — transição | P0 aplicáveis aprovados, P1 aceitos/deferidos, evidências entregues a V4-00/FI-00 | Gate específico de V4/FI não dispensado |

Comandos de referência (confirmar runner e pré-condições; não rodar contra DEV):
- git status --short; git rev-parse HEAD
- scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q
- scripts/test-container.sh tests/test_architecture.py -q
- scripts/test-container.sh tests/test_compose_env.py -q
- bash scripts/run-e2e-full.sh somente após exclusividade e guarda de destino/publicação; runner atual requer adequação FS-02.
- scripts/render_benchmark.py em ambiente canônico com dependências e PYTHONPATH conforme script; fixture sintética não prova profissionalização.
- python3 docs/plano-de-testes-faceless/validar.py conforme dependências do plano.

## Definition of Done por incremento
- Escopo mínimo aprovado, testes existentes reaproveitados, código/contrato/documentação coerentes.
- Evidência de antes/depois, status e exceções; sem segredos ou dados reais desnecessários.
- Review independente para mudança crítica; validação humana de UX/audiovisual quando aplicável.
- Risco, rollback e dependências explícitos; commit pequeno e PR sem merge automático.
- Parar em upload/gasto inesperado, vazamento, destino não descartável, duplicação de efeito, perda de estado ou falha crítica.

## Evidência mínima
run_id, phase_id, git_sha, dirty, environment, command, timestamp, duration, exit_code, passed/failed/skipped, skip_reasons, artifact_refs, cost_estimate vs actual, limits, reviewer, decision, residual_risks. Arquivos pesados/MP4 fora do git por padrão, com hash e local seguro; versionar resumo sanitizado. Não atribuir dados da RUN-08 dirty ao HEAD limpo.
