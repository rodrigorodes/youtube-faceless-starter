# Backlog de recuperação — todos PENDING

Base 72438e9. Não repetir toda V4; reabrir IDs INT/V4/GAI atingidos. A matriz REC-00 deve confirmar requisitos restantes não listados e acrescentar tarefas mínimas no escopo original sem inventar IDs V4. Cada item exige rubrica >=9 e gates aplicáveis. Dependências abaixo são mínimas, não autorização para pular gate.

| ID | Prioridade | Dependência | Alvo / aceite obrigatório |
|---|---|---|---|
| REC-00.01 | P0 | — | Reconciliar R01–R13, todos IDs V4/GAI, call sites e estado real; inventário de testes/artefatos |
| REC-00.02 | P0 | 00.01 | Plano test-first, limites de escopo, baseline, evidências e review independente |
| REC-01.01 | P0 | 00.02 | Remover/desabilitar PostgresOperationStore inseguro; preservar BudgetGuard existente, identidade real e teto zero |
| REC-01.02 | P0 | 01.01 | Admissão/settlement atômicos; concorrência, retry, restart, operation ID, ledger exatamente uma vez por confirmação local |
| REC-01.03 | P0 | 01.02 | Reconciliação pré-retry e timeout/cancelamento no coordenador existente; teste de efeito incerto e isolamento multi-vídeo |
| REC-02.01 | P0 | 01.03 | RenderPlan/compilador/executor consistentes; camadas, PiP vídeo, transformações e crossfade real ou rejeição explícita conforme requisitos |
| REC-02.02 | P1 | 02.01 | Multitrack, SFX/ambiente/voz, ducking, fades, motion e dBTP real; golden/pixels/sync |
| REC-02.03 | P0 | 01.03 | Import PNG/MP4 reproduzível, probe/decode e limites; negativos de MIME, corrupção, licença e traversal |
| REC-02.04 | P0 | 02.03 | Dedup por conteúdo/escopo, CAS/revisão real, conflito, persistência/restart, atomicidade/compensação |
| REC-02.05 | P1 | 01.03 | Kokoro completo offline comprovado ou indisponível; Piper real; ElevenLabs desabilitado |
| REC-03.01 | P1 | 02.01–05 | Upload/preview/associação no Studio, modo assistido genérico, undo/redo/reload, edição/gerar faltantes |
| REC-03.02 | P1 | 03.01 | Browser Node/Playwright isolado, desktop/mobile, caminho real e negativos; nenhuma perda de edição |
| REC-03.03 | P1 | 02.01–05 | Integrar lacunas de creative/captions/cache/QA/regeneração/licença no pipeline existente; prova seletiva e restart |
| REC-04.01 | P0 | 03.01–03 | Slice 60–90s via Studio, capacidades novas reais, artefatos e métricas observadas |
| REC-04.02 | P0 | 04.01 | Documentário 5–8min, comparação controlada V4-00, econômico/segundo perfil local quando viável, evidência de regeneração |
| REC-04.03 | P0 | 04.02 | Regressão canônica completa pós última alteração, browser, SHA/log/JUnit e reconciliação de contagens |
| REC-04.04 | P0 | 04.03 | Review final independente >=9 técnico sem bloqueios, matriz reconciliada, avaliação humana pendente até operador |

A ordem de REC-02 pode aproveitar dependências independentes, mas evitar edição simultânea do mesmo arquivo. REJECTED/BLOCKED em um item impede dependentes. Não usar implementação opcional de API paga para atingir 9. Resolver pendências obrigatórias originais identificadas na matriz antes de REC-04.03. Premium/15–20min/GAI opcionais somente conforme escopo e autorização, registrar risco e DEFERRED. Nenhum merge automático.
