# V4-00 — Baseline & Stability
Status: proposto. Dependências: Nenhuma.

## Atividades
- [ ] V4-00.01 — Mapear módulos e responsabilidades. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.02 — Validar dependências. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.03 — Executar regressão. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.04 — Renderizar piloto de referência. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.05 — Medir CPU RAM tempo custo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.06 — Avaliar vídeo e áudio humanamente. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.07 — Mapear capabilities FFmpeg. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.08 — Identificar limites de contratos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.09 — Validar checkpoints e recuperação. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-00.10 — Documentar AS-IS. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Relatório reproduzível com comandos, métricas, hashes e falhas; nenhuma regressão crítica.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-00 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.
