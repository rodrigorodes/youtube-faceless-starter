# FS-08 — Modularização incremental do Core (P1)
Objetivo: preparar extensões sem transformar Foundation em reescrita. Fonte: [evolução estrutural](../STRUCTURAL-EVOLUTION.md), [backlog](../EXECUTION-BACKLOG.md), [gates](../QUALITY-GATES.md). Dependência: FS-01/02 aprovadas para extrações; preflight para inspeção/teste. FS-08 não é um bloqueio geral para V4/Finder.

## FS-08.01 — antes da evolução
Mapear imports e ciclos, rotas e precedência, contratos reexportados, composição de instâncias/lifecycle, StageHandlers e transições, outputs do compiler. Identificar pontos de mudança esperados V4/FI. Criar apenas testes de caracterização faltantes. Entregar mapa, recortes, ordem e justificativa; se nada justificar extração imediata, deferir.

## FS-08.02–06 — recortes vinculados ao consumidor
Para cada recorte, verificar testes focados antes; extrair responsabilidade sem alterar comportamento; preservar fachada/imports; executar testes e comparação; revisar diff; registrar rollback. API antes de UX/Finder quando necessário, ports/wiring na V4-01, compiler na V4-04, production na V4-12 ou necessidade comprovada FS-06. Não criar arquitetura paralela.

## FS-08.07 — critérios por recorte
- [ ] API: método/path/prefixo/precedência/status/headers/OpenAPI/auth/CSRF/idempotência equivalentes.
- [ ] Ports: identidade de tipos, signatures e exceptions compatíveis; testes de arquitetura.
- [ ] Wiring: um lifecycle/registry/budget/DB/executor conforme configuração; shutdown e frozen provider selection preservados.
- [ ] Compiler: mesma estrutura, ticks, duração, validações/erros e render golden dentro de tolerância documentada.
- [ ] Production: CAS, lease, heartbeat, fencing, retry, recovery, checkpoints, idempotência, approval e reconciliação preservados; nenhum efeito duplicado.
- [ ] Regressão local, review, evidência por SHA, rollback por revert; sem alteração funcional misturada.

Estimativa adicional de mapeamento: 0,5–1 dia; extrações completas não estimadas sem recortes aprovados. Não somar a mesma extração duas vezes em FS-08 e fases V4/FI. GO/NO-GO humano. Nenhuma atividade marcada PASS nesta documentação.
