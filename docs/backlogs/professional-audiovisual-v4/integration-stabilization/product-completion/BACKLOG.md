# Backlog PC — todos PENDING

Proposta de fechamento do produto local. Cada tarefa exige nota >=9 por dimensão, consumidor real e review independente. IDs não substituem V4/GAI. Ver SCOPE-MATRIX para cobertura dos 44 adiamentos.

| ID | Prioridade | Dep. | Entrega objetiva |
|---|---|---|---|
| PC-00.01 | P0 | — | Reconciliar baseline, 44 V4 + 6 GAI, 2 humanos, 1 status final; confirmar contratos e bloqueios |
| PC-00.02 | P0 | 00.01 | Plano test-first, call graph, matriz e reviewer; nenhum código de produto |
| PC-01.01 | P0 | 00.02 | Reproduzir perda de overlays/trim no replace base; transação única e CAS de revisão |
| PC-01.02 | P0 | 01.01 | Corrida, falha parcial, undo/redo, reload, isolamento e cache seletivo; browser real |
| PC-02.01 | P1 | 01.02 | Importação áudio autorizada e persistida, probe/limites/licenças e preview |
| PC-02.02 | P1 | 02.01 | CRUD de trilhas voz/música/ambiência/SFX com timeline, volume, fades e ducking |
| PC-02.03 | P1 | 02.02 | EQ/compressão parametrizados e mix preview/render, dBTP real e regressão |
| PC-03.01 | P1 | 01.02 | Catálogo e identidade vocal por canal com seleção validada e snapshot |
| PC-03.02 | P1 | 03.01 | Dicionário, pausas/ritmo/intenção suportada, preview e sync; sem emoção simulada |
| PC-03.03 | P1 | 03.01 | Direção criativa por cena, intensidade, objetivo e shots editáveis |
| PC-04.01 | P1 | 01.02,03.03 | Editor de camadas no painel existente, z-index/posição/scale/alpha/trim, reload |
| PC-04.02 | P1 | 04.01 | Transições reais configuráveis, duração/sync, validação e preview |
| PC-04.03 | P1 | 04.02 | Templates animados, lower thirds, mapas/timelines, ícones/infográficos |
| PC-04.04 | P1 | 04.03 | Blur/LUT/vinheta/grain com presets e limites, render real |
| PC-05.01 | P1 | 02.03,04.04 | Capabilities reais e presets preview baixa resolução/produção; cache coerente |
| PC-05.02 | P1 | 01.02 | Tags acervo persistente, pesquisa/isolamento, licença e restart |
| PC-05.03 | P1 | 05.01,05.02 | Inventário módulos sem consumidor; integrar ou aposentar de forma justificada, não duplicar |
| PC-06.01 | P1 | 02–05 mínimos | QA técnico/semântico honesto, ação seletiva autorizada, caps de retries e falha fechada |
| PC-06.02 | P0 | 06.01 | Segurança de edição/licença, regressão de trim/overlays, timeout/restart/zero cobrança, kill switch |
| PC-07.01 | P1 | 03.02 | Viabilidade offline segunda voz e comparação real; se indisponível, evidência e decisão do operador |
| PC-07.02 | P2 opt. | 05.01 | Avaliar engines/hardware/storage/align externos com inventário local; nenhum install/gasto sem autorização |
| PC-07.03 | P1 opt. | 06.01 | Plano de ativação GAI e demais opcionais com custo/consentimento/licença; sem chamada paga |
| PC-08.01 | P0 | 02–06 obrigatórios | Slice 60–90s pelo Studio com todas capacidades essenciais, browser e manifests |
| PC-08.02 | P0 | 08.01 | Documentário 5–8min econômico e equilibrado local quando viável, benchmark pareado e regeneração |
| PC-08.03 | P0 | 08.02 | Jornada usuário desktop/mobile, reload/undo/redo/export; handoff dos vídeos e rubrica humana |
| PC-09.01 | P0 | 08.03 | Regressão completa final e revisão independente, nenhum P0/P1 obrigatório |
| PC-09.02 | P0 | 09.01 | Matriz reconciliada, escopo opcional/pendências aceitas pelo operador, avaliação humana e decisão separada de merge |

PC-07 pode rodar como diagnóstico sem alterar core, em paralelo apenas se recursos/arquivos não conflitam. Gates de PC-08 não dependem de gasto/instalação externa; falta de recurso obrigatório deve ser reportada, não renomeada opcional. PC-09 técnico pode preparar relatório antes de decisão humana, mas não finalizar release. Atividades opcionais autorizadas posteriormente exigem nova rodada de gates.
