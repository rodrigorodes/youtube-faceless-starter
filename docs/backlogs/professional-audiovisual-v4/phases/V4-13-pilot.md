# V4-13 — Professional Pilot
Status: proposto. Dependências: Todas as fases aplicáveis.

## Atividades
- [ ] V4-13.01 — Roteiros referência. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.02 — Piloto econômico. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.03 — Piloto equilibrado. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.04 — Piloto premium opcional. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.05 — Comparar voz. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.06 — Comparar som. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.07 — Comparar visual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.08 — Custo por minuto. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.09 — Tempo produção. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.10 — Custo regeneração. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.11 — Avaliação humana. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.12 — Corrigir problemas. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.13 — Publicação controlada. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-13.14 — Relatório final. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Comparação pareada com mesmo roteiro de baseline; três estilos quando orçamento permitir; aprovação humana e licença antes de publicar.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-13 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
[Professional Pilot](../PROFESSIONAL-PILOT-SPEC.md): vertical slice antecipado, documentário 5min, 15–20min para tempo humano, Mac, comparação cega, custos e edição não destrutiva. Piloto integrado Finder/manual, nenhuma publicação sem aprovação. Metas propostas, não resultados.
