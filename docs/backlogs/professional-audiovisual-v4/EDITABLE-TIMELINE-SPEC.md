# Timeline editável — V4-04/07/08/10/12
Requisito mandatório: projeto audiovisual aberto no Studio, não apenas MP4. RenderPlan canônico versionado, edições persistidas e reversíveis; nenhuma chamada a LLM para edição determinística. Preservar Studio V3, StylePatch e revisões existentes.
## Operações
| Operação | Invalidação esperada |
|---|---|
| Fonte, cor, fundo, legenda | composição/segmentos dependentes |
| Troca de B-roll ou trim | shot, transições vizinhas e segmento dependente |
| Volume, música, SFX | mix e dependências de áudio |
| Narração | áudio, alinhamento e timeline downstream conforme duração |
| Roteiro | somente etapas semanticamente dependentes; reaprovação editorial |
Contratos propostos: EditCommand(project/run, expected_revision, operation, target_id, payload, idempotency_key); EditResult(revision, affected_nodes, estimated_cost, warnings). Operações trim/split/move, add/remove track/shot, style override, replace asset, volume, caption correction; validação ticks, overlap, z_order, capabilities, licenças e autorização. Undo/redo via revisões, optimistic concurrency, autosave e restauração após reload. Preview proxy; UI explicita recursos não aplicados.
## Aceite
- [ ] Teste de navegador: editar fonte, fundo e trim, reload, undo/redo, adicionar cena na mesma bancada, gerar faltantes.
- [ ] Asserção zero chamadas LLM/TTS em edits determinísticos; preservar assets não afetados e medir cache hit/re-render.
- [ ] Conflito de revisão, restart, cancelamento, transição cruzada, mudança de duração da voz; sem perda silenciosa de edição.
- [ ] Preview e export coerentes; comparação por tolerância documentada, não igualdade binária obrigatória.
Intercâmbio OTIO/FCPXML opcional posterior, não dependência do piloto. Mac Apple Silicon: testar dependências, fonts, codec, CPU e aceleração opcional com fallback; não prometer suporte até executar.
