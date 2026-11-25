# V4-10 — Studio UX
Status: proposto. Dependências: 01–09 incremental.

## Atividades
- [ ] V4-10.01 — Preservar Studio V3. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.02 — Storyboard integrado. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.03 — Múltiplos assets. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.04 — Biblioteca mídia. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.05 — Voice Studio. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.06 — Audio Studio. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.07 — Editor camadas. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.08 — Timeline simplificada. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.09 — Transições. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.10 — Efeitos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.11 — Legendas. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.12 — Undo redo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.13 — Preview cena. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.14 — Regeneração seletiva. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.15 — Relatório QA. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.16 — Custos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.17 — Providers por canal. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.18 — Channel Identity. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.19 — Aprovação publicação. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-10.20 — Responsividade acessibilidade. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Fluxo real de edição persistente, undo/redo, adicionar cena na mesma bancada, gerar faltantes, preview e render; testes navegador.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-10 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
[Timeline editável](../EDITABLE-TIMELINE-SPEC.md): trim/split, substituir mídia, fundo/fonte/volume, autosave, undo/redo, zero LLM em edits determinísticos; alternativas até três quando disponíveis. Reconciliar Packaging F7 (3 thumbnails, revisão e seleção) sem duplicar adapter. Preservar UX existente.

## Complemento GAI-02
UX mínimo incremental: selecionar origem, editar/copiar prompt, abrir ferramenta oficial, importar/preview/aplicar asset na cena, preservar revisões e aprovação. Sem login de assinatura dentro do Studio, scraping, worker bloqueado ou quota inventada. [GAI](../GAI-EXECUTION-PLAN.md).
