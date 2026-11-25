# V4-04 — Composition Core
Status: proposto. Dependências: 00,01 contratos.

## Atividades
- [ ] V4-04.01 — Versionar RenderPlan. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.02 — Compatibilidade v1/v2. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.03 — Remover limite de overlay gradualmente. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.04 — Overlays simultâneos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.05 — Overlays entre shots. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.06 — Vídeo sobre vídeo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.07 — Textos e gráficos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.08 — Transformações. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.09 — Keyframes. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.10 — Transições entre shots. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.11 — Crossfade visual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.12 — Eventos de áudio. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.13 — Ticks determinísticos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.14 — Evoluir compilador. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.15 — Evoluir FFmpeg. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.16 — Validar capabilities. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.17 — Fingerprints. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.18 — Invalidação dependente. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.19 — Preview baixa resolução. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-04.20 — Testar duração e determinismo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Golden fixtures antigas e novas; múltiplas camadas e transição com duração correta; erros explícitos para capacidades ausentes.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-04 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.
