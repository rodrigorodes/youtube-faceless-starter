# V4-05 — Visual & Motion
Status: proposto. Dependências: 04,11 fundação.

## Atividades
- [ ] V4-05.01 — Consolidar Pexels Pixabay. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.02 — Homologar ComfyUI. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.03 — Normalizar imagem. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.04 — Relevância contextual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.05 — Detectar repetição. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.06 — Detectar baixa qualidade. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.07 — Consistência estética. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.08 — Upload imagem. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.09 — Seleção vídeo contextual. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.10 — Selecionar trechos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.11 — Duração e velocidade. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.12 — Evitar repetição. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.13 — Normalizar codecs FPS. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.14 — Múltiplos B-rolls. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.15 — Preparar vídeo generativo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.16 — Upload vídeo. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.17 — Templates animados. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.18 — Lower thirds. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.19 — Gráficos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.20 — Mapas e timelines. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.21 — Texto animado. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.22 — Ícones e infográficos. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.23 — Remotion como asset opcional. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.24 — Avaliar Blender. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.25 — Ken Burns. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.26 — Zoom pan. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.27 — Blur. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.28 — Color grading LUT. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.29 — Vinheta. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.30 — Grain. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.31 — Transições. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.
- [ ] V4-05.32 — Presets. Identificar implementação existente, definir delta mínimo, implementar ou validar, registrar teste e evidência.

## Aceite
Cena demonstrativa com B-roll, gráfico, título e movimento; sem repetição indevida; fontes e dados verificáveis.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-05 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Aceite complementar V4.1
Aplicar [Semantic Media](../SEMANTIC-MEDIA-SPEC.md) às atividades .04/.09/.10/.14 e [catálogo](../PROFESSIONAL-STYLE-CATALOG.md) às .17–32. Primeiro Documentary e Whiteboard; ranking explicável e alternativas persistidas. Reusar scene_media_intelligence e MediaSearch; teste real de mídia autorizada ou fixture, sem download indevido.

## Complemento GAI-04/06
Nano Banana API e Veo API são candidatos opcionais. Veo atual é stub; vídeo exige capability explícita e operação assíncrona persistida/reconciliada. Flow exportado por humano usa importação genérica GAI-01. [GAI](../GAI-EXECUTION-PLAN.md).
