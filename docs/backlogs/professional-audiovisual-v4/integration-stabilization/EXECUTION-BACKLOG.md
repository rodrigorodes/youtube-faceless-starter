# Backlog incremental (todos PENDING)

Os IDs INT organizam a recuperação das entregas existentes; não substituem os IDs V4/GAI e não adicionam escopo de produto. INT-01 reconcilia a matriz original de 227 atividades declaradas (verificar quantidade real; não inventar IDs). Cada item depende da aprovação anterior ou dependência indicada.

| ID | Prioridade | Escopo | Dependência | Aceite objetivo |
|---|---|---|---|---|
| INT-01.01 | P0 | Inventário de commits, contratos e call sites | — | AS-IS confirmado por código |
| INT-01.02 | P0 | Matriz V4/GAI requisito a requisito | .01 | Cada ID com evidência ou lacuna, sem PASS por inferência |
| INT-01.03 | P0 | Plano e testes mínimos, riscos/rollback | .02 | aprovação do operador |
| INT-02.01 | P0 | Desabilitar Kokoro simulado e preservar Piper | 01 | Não selecionável como voz real, erro/fallback auditável |
| INT-02.02 | P1 | Kokoro real se viável offline; ElevenLabs opcional indisponível | .01 | Fala inteligível PT-BR ou indisponibilidade explícita |
| INT-02.03 | P0 | Registry, snapshot, erro/fallback e orçamento | .01 | seleção congelada, zero chamadas pagas |
| INT-03.01 | P0 | RenderPlan/LayerExecution/compilador | 02 | múltiplos overlays, compatibilidade e erros explícitos |
| INT-03.02 | P0 | Transformações, PiP, transições | .01 | pixels/duração medidos em MP4 real |
| INT-03.03 | P1 | Multitrack, fades, ducking, QA áudio | .01 | voz/música/ambiência/SFX reais, licença e dBTP |
| INT-03.04 | P1 | Motion e presets | .02 | cena demonstrativa real, efeito observável |
| INT-04.01 | P1 | Direção criativa, captions e sincronização | 03 | brief→timeline editável, export e áudio sincronizado |
| INT-04.02 | P1 | Cache, progresso, cancelamento e QA seletivo | .01 | alterar uma cena e provar reúso/invalidação |
| INT-04.03 | P0 | Resiliência no coordenador existente | 02 | CAS, restart, timeout real, operações/retry sem duplicidade |
| INT-05.01 | P0 | GAI-01 importação PNG/MP4 | 03.01,04.03 | import→preview→render, negativos de segurança e CAS |
| INT-05.02 | P1 | Catálogo e licenças persistentes | .01 | restart, isolamento, dedup, bloqueio publicação |
| INT-05.03 | P1 | GAI-02 e UX storyboard, undo/redo | .01 | browser real, reload, sem perda de edição |
| INT-06.01 | P0 | Vertical slice 60–90s | 03–05 mínimos | artefato real pelo Studio; zero API |
| INT-06.02 | P0 | Documentário 5–8min pareado | .01 | métricas reais, hashes, metodologia |
| INT-06.03 | P1 | Comparação equilibrado e avaliação humana | .02 | perfil real local ou autorizado; bloqueado se não viável |
| INT-07.01 | P0 | Regressão canônica e auditoria de gates | 06 | resultados rastreáveis, nenhum P0 aberto |
| INT-07.02 | P0 | Revisão independente e decisão | .01 | operador aceita qualidade e riscos, autoriza merge separadamente |

## Ordem de entrega
01 → 02 → 03 → 04/05 em slices com dependências explícitas → 06 → 07. Provar o primeiro slice assim que capacidades mínimas existirem; não esperar toda a expansão. Não implementar API paga para fechar gate; GAI-03–08/Drive continuam opcionais. Aprovação humana anterior V4-00 não presumida.
