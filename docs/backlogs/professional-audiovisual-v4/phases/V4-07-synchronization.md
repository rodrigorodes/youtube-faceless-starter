# V4-07 — Captions & Sync
Status: concluído. Dependências: 02,04.

## Atividades
- [x] V4-07.01 — Preservar ASS. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.02 — Alinhamento por palavra. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.03 — Homologar Whisper WhisperX. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.04 — Legendas dinâmicas. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.05 — Destacar palavras. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.06 — Estilos por canal. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.07 — Safe area Shorts. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.08 — Evitar sobreposição. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.09 — Exportar SRT VTT. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.10 — Validar voz e legenda. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.11 — Recalcular timeline. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-07.12 — Correção manual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Fixture com timestamps e mudança de duração da voz; legenda legível e sincronizada; exportações válidas.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-07 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Complemento mídia externa
Preservar ticks, duração de voz e captions; voz externa medida/alinhada, vídeo externo trim/loop/crop por política, sem mudar timeline silenciosamente. [GAI](../GOOGLE-AI-PRO-INTEGRATION.md).
