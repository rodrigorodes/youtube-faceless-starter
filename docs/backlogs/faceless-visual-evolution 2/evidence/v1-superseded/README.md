# Faceless Studio — Visual Evolution (VE-001)

**Status:** proposta; nenhuma alteração de produção foi executada.  
**Fonte:** `youtube-faceless-starter(4).zip`, inspecionado em 22/11/2026.  
**Objetivo:** elevar a qualidade visual sem reescrever o pipeline, com custo previsível e extensão por contratos.

## Baseline verificado
- `renderer/app/studio/domain/render_plan.py`: contrato canônico versionado, timeline, tracks, shots, cues e estilo.
- `renderer/app/studio/application/render_compiler.py`: compilador puro, com `_require_single_layer()`; principal limitação a remover incrementalmente.
- `renderer/app/studio/adapters/render_plan_ffmpeg.py`: executor FFmpeg, efeitos, narração, overlays e publicação atômica do arquivo.
- `renderer/app/studio/application/production.py`: coordenação, stages, checkpoints e aprovação.
- `renderer/app/studio/domain/quality.py`: QA determinístico; multimodal é explicitamente não verificado.
- `renderer/app/studio/domain/visual_style.py`: estilos e patches existentes; reutilizar.
- `docs/backlogs/faceless-studio-v31/`: evolução paralela de Settings, identidade e estilos. Evitar colisões de contrato.

## Resultado esperado
Um `RenderPlan` versionado, capaz de expressar camadas simultâneas e compor B-roll, textos, imagens, efeitos e áudio em uma timeline reproduzível. Seleção híbrida de mídia e QA semântico serão módulos opcionais, não pré-requisitos do render.

## Arquitetura
Ver [diagramas](diagrams/architecture.md) e [regras](RULES.md).

## Roadmap (não executar fases futuras automaticamente)
| Fase | Entrega | Critério de aceite |
|---|---|---|
| VE-00 | Baseline e golden render | Testes e hashes/artefatos registrados, sem modificar produção |
| VE-01 | Compilador multilayer mínimo | 1 camada base + 1 overlay temporal; planos antigos preservados |
| VE-02 | FFmpeg compositor | Overlay determinístico, sem gaps, render de teste reprodutível |
| VE-03 | B-roll e seleção híbrida | Seleção por contrato, custo/licença/proveniência; fallback local |
| VE-04 | Estilos e tipografia | Presets por nicho, motion/caption em allowlist; fallback compatível |
| VE-05 | QA visual opcional | Evidências e cobertura explícita; falhas não viram aprovação silenciosa |
| VE-06 | Scene Organizer mínimo | Troca de asset por cena, nova versão, preview e reaprovação |

### Escopo deliberadamente excluído do MVP
Editor de timeline completo, geração ilimitada por IA, SaaS multi-tenant, reescrita de n8n, segundo renderer e novo workflow obrigatório.

## Como executar
1. Copiar esta pasta para `docs/backlogs/faceless-visual-evolution/` do repositório.
2. Executar `prompts/00-master.md` no OpenCode, apontando para o repositório real.
3. Autorizar **somente VE-00**. Após evidências, autorizar VE-01 e assim sucessivamente.
4. Não assumir que os testes existentes passam; medir primeiro.

## Indicadores de sucesso
- Paridade: render legado sem regressão em áudio, duração, legendas, disclosure e aprovação.
- Composição: pelo menos duas camadas visuais coexistindo em intervalos determinados.
- Reprodutibilidade: mesmo plano + mesmos assets + mesmo ambiente => mesma timeline e comando compilado.
- Custo: nenhuma operação paga sem orçamento, chave idempotente e registro de provenance.
- Qualidade: QA técnico permanece bloqueante; QA semântico não verificado aparece como tal.

## Atualização 22/11/2026 — VE-00 investigada e VE-07 proposta

**Atenção:** este README inicial é histórico. O OpenCode produziu a revisão de VE-00 (`evidence/ve-00-review.md`) e um plano detalhado (`PLAN-VE00-VE06-AS-RECEIVED.md`) que foram incorporados **sem alterar seu conteúdo**. O plano registra limpeza de dados já executada pelo operador e aponta imagem Docker desatualizada. Nenhuma implementação VE-01+ foi comprovada por estes documentos.

O plano recebido contém **contradições residuais**: D4 abandona digest legado, mas VE-01 ainda o exige; D6 elimina feature flag, mas testes ainda a referenciam; D2 dispensa migração de dados antigos, mas há requisitos antigos de rollback. **Consolidar antes de codificar**, preservando compatibilidade funcional do fluxo sem overlays.

| Fase adicional | Entrega | Documento |
|---|---|---|
| **VE-07** | Production Workspace: modo Automático/Assistido, roteiro por cena, narração, storyboard, mídia, render, QA, aprovação e publicação | [`phases/VE-07-production-workspace.md`](phases/VE-07-production-workspace.md) |

### Abrir o protótipo HTML
Abra `prototype/index.html` no navegador (duplo clique, sem servidor). Contém 10 telas navegáveis e interações simuladas. **Não é uma aplicação funcional:** não conecta API, não gera MP4/voz, não realiza QA real nem publica. Veja [`ux/UX-SPEC.md`](ux/UX-SPEC.md).

### Ordem sugerida
1. Fechar VE-00b/VE-00, corrigir plano recebido e registrar baseline Docker/Postgres.
2. Implementar e validar VE-01 a VE-06 em gates independentes.
3. Executar investigação VE07-00 e subfases VE07-01 a VE07-07, autorizadas separadamente.
4. Usar [`prompts/02-VE07-opencode.md`](prompts/02-VE07-opencode.md) para instruir OpenCode.
