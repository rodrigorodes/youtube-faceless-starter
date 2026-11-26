# V4-08 — Render Extensibility
Status: concluído. Dependências: 04,12 fundação.

## Atividades
- [x] V4-08.01 — Contrato capabilities. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.02 — Consolidar FFmpeg. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.03 — Separar compilação e execução. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.04 — Preflight. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.05 — Render por segmentos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.06 — Cache de segmentos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.07 — Progresso. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.08 — Cancelamento. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.09 — Concorrência recursos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.10 — Presets preview produção. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.11 — Avaliar hardware. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.12 — Homologar Remotion assets. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.13 — Avaliar segundo renderer. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [x] V4-08.14 — Benchmarks. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
FFmpeg principal; render real com cancelamento, cache e preflight; equivalência de segmentos e render integral.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-08 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
Homologar Apple Silicon/macOS com benchmark local, fontes, codecs e fallback; não declarar suporte antes de render real. Preview e render por segmentos conforme dependências, não exigir Remotion como renderer principal.

## Complemento render de mídia externa
FFmpeg local, staging e cache por hash/escopo; teste real de vídeo importado e áudio quando suportado; render sem rede. Não chamar geração paga dentro do compilador. [GAI](../GAI-EXECUTION-PLAN.md).
