# Matriz de escopo — 44 IDs V4 adiados + 6 GAI

Extraída da matriz em 2e8b153. Proposta: OBRIGATÓRIO_LOCAL = concluir sem API paga; VIABILIDADE = diagnóstico local e decisão explícita se não viável; OPCIONAL_AUTORIZAÇÃO = não executar integração externa sem consentimento/recursos/licença. Não declarar implementado por diagnóstico. Aceite humano e de redução de escopo exclusivamente operador.

| IDs originais | Qtd | PC | Tratamento |
|---|---:|---|---|
| V4-02.05, .06 | 2 | 03.01 | OBRIGATÓRIO_LOCAL catálogo/identidade |
| V4-02.07, .08, .09 | 3 | 03.02 | OBRIGATÓRIO_LOCAL controle honesto de intenção/ritmo/pronúncia; se motor não suporta emoção, explicitar, não fingir |
| V4-02.15, V4-13.05 | 2 | 07.01 | VIABILIDADE segunda voz e comparação cega real |
| V4-03.02, .15, .16, V4-10.06 | 4 | 02.01–02.03 | OBRIGATÓRIO_LOCAL áudio UI e preview |
| V4-03.13 | 1 | 02.03 | OBRIGATÓRIO_LOCAL EQ/compressão |
| V4-03.05 | 1 | 07.02 | OPCIONAL_AUTORIZAÇÃO Freesound |
| V4-04.19, V4-08.01, .10 | 3 | 05.01 | OBRIGATÓRIO_LOCAL capabilities/preview |
| V4-05.17, .18, .20, .22 | 4 | 04.03 | OBRIGATÓRIO_LOCAL motion/templates/infográficos |
| V4-05.27, .28, .29, .30 | 4 | 04.04 | OBRIGATÓRIO_LOCAL pós-processamento |
| V4-05.02, .23, .24 | 3 | 07.02 | OPCIONAL_AUTORIZAÇÃO ComfyUI/Remotion/Blender |
| V4-05.15 | 1 | 07.03 | OPCIONAL_AUTORIZAÇÃO vídeo generativo |
| V4-06.03, .04, .05 | 3 | 03.03 | OBRIGATÓRIO_LOCAL direção por cena/shots |
| V4-07.03 | 1 | 07.02 | OPCIONAL_AUTORIZAÇÃO Whisper/WhisperX |
| V4-08.11, .12, .13 | 3 | 07.02 | VIABILIDADE hardware local / OPCIONAL_AUTORIZAÇÃO Remotion/segundo renderer |
| V4-09.10, .11 | 2 | 06.01,07.03 | QA técnico obrigatório; multimodal externo OPCIONAL_AUTORIZAÇÃO, não alegar semântico verificado sem provedor |
| V4-10.07, .09 | 2 | 04.01–04.02 | OBRIGATÓRIO_LOCAL camadas/transições |
| V4-11.09 | 1 | 05.02 | OBRIGATÓRIO_LOCAL tags persistentes |
| V4-11.14 | 1 | 07.02–03 | OPCIONAL_AUTORIZAÇÃO storage externo |
| V4-12.14 | 1 | 07.02 | OPCIONAL_AUTORIZAÇÃO CI; não implementar nesta campanha |
| V4-13.03 | 1 | 08.02 | VIABILIDADE equilibrado local real, sem fingir perfil |
| V4-13.04 | 1 | 07.03,08.02 | OPCIONAL_AUTORIZAÇÃO premium/15–20min |
| **Total** | **44** | | IDs abreviados .xx pertencem ao prefixo anterior |

| GAI | PC | Escopo |
|---|---|---|
| GAI-03 Text | 07.03 | API oficial BYOK opcional |
| GAI-04 Image | 07.03 | API oficial opcional |
| GAI-05 TTS | 07.03 | API oficial opcional |
| GAI-06 Video | 07.03 | Async com reserva/reconcile, opcional |
| GAI-07 Drive | 07.02–03 | Cloud storage opcional |
| GAI-08 QA | 06.01,07.03 | Semântico real opcional; UNKNOWN explícito |
| GAI-01/02/09 já verificadas na matriz | 01,02,04,06,08 | Proteger import/assistido/orçamento contra regressão |

Adicional: PC-01 e PC-06 corrigem P1 de integridade de camadas (não é um novo ID V4; vincular V4-04/10/11 e REC-02/03 por IDs confirmados). PC-09 reconcilia V4-13.14 e R13/A13/INT-07.02/REC-04.03–04 divergentes entre matriz e review final; V4-00.06/V4-13.11 humanos pendentes. A matriz PC-00 deve expandir todos IDs completos e verificar 44 únicos (sem presumir contagem), evidência/impacto/status por ID. O operador não aprovou os 44 adiamentos apenas por pedir execução de correções.
