# V4-09 — Multimodal Quality
Status: concluído. Dependências: 03,05,07,08.

## Atividades
- [x] V4-09.01 — Evoluir QaReport. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.02 — FFprobe. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.03 — Frames pretos congelados. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.04 — Repetição. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.05 — Enquadramento. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.06 — Clipping loudness. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.07 — Silêncio. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.08 — Sync legenda. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.09 — Amostragem frames. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.10 — Provider multimodal. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.11 — Roteiro versus imagem. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.12 — Consistência visual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.13 — Ritmo editorial. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.14 — Severidade. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.15 — Sugestões estruturadas. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.16 — Regeneração seletiva. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.17 — Limites de correção. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-09.18 — Aprovação humana. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Fixtures com defeitos conhecidos; relatório com evidência e localização; avaliação humana calibrada; sem autopublicação.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-09 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
Separar gate editorial pré-produção (V4-06) e QA pós-render. Calibrar correspondência semântica com avaliação humana, fixtures de época/local incorretos, reconstrução IA e repetição; evidência por shot. Nenhum score de viralização.

## Complemento GAI-08
Gemini multimodal via API autorizada e orçamento, reusar SemanticChecker e QA report, evidência temporal e revisão humana; not_verified não equivale a pass. [GAI](../GAI-EXECUTION-PLAN.md).
