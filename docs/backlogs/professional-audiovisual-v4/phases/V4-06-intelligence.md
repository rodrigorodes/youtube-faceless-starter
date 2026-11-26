# V4-06 — Creative Intelligence
Status: concluído. Dependências: 02,03,05 contratos.

## Atividades
- [x] V4-06.01 — Evoluir Creative Director. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.02 — Direção narrativa estruturada. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.03 — Objetivo por cena. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.04 — Emoção intensidade. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.05 — Planejar shots. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.06 — Planejar música SFX. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.07 — Pacing. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.08 — Channel Identity. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.09 — Versionar estilos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.10 — Overrides. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.11 — Validar saída LLM. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-06.12 — Validar capacidades renderer. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Brief estruturado por cena, validado e editável; identidade congelada; sem comandos FFmpeg no LLM.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-06 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
[Pesquisa editorial](../EDITORIAL-RESEARCH-SPEC.md): reconciliar V2-F3, claims e AutoResearch; gate antes de voz/mídia paga. Estilos Quick/Professional como política do mesmo core. ShotIntent e briefing do Finder opcional/manual, com evidência e originalidade.

## Complemento direção criativa assistida
Preparar prompt por cena/shot com intenção visual, estilo, formato e duração. Importar texto/fontes de Gemini Deep Research via gate editorial e SourceSnapshot, sem considerar fonte verificada automaticamente. [GAI](../GOOGLE-AI-PRO-INTEGRATION.md).
