# Plano

| Fase | Entrega | Dependências | Gate |
|---|---|---|---|
| V4-00 | Baseline & Stability | Nenhuma | Relatório reproduzível com comandos, métricas, hashes e falhas; nenhuma regressão crítica. |
| V4-01 | Provider Extensibility | 00 | Piper e FFmpeg continuam funcionando; adapter fake comprova extensão sem mudança no domínio. |
| V4-02 | Professional Voice | 01,11 fundação | Mesmo roteiro PT-BR em dois providers locais quando viável; avaliação cega e custo registrados; capacidades não suportadas explícitas. |
| V4-03 | Professional Audio | 01,04 fundação,11 fundação | Fixture com voz, duas músicas, ambiência e SFX; sem clipping; licença comprovada; duração preservada. |
| V4-04 | Composition Core | 00,01 contratos | Golden fixtures antigas e novas; múltiplas camadas e transição com duração correta; erros explícitos para capacidades ausentes. |
| V4-05 | Visual & Motion | 04,11 fundação | Cena demonstrativa com B-roll, gráfico, título e movimento; sem repetição indevida; fontes e dados verificáveis. |
| V4-06 | Creative Intelligence | 02,03,05 contratos | Brief estruturado por cena, validado e editável; identidade congelada; sem comandos FFmpeg no LLM. |
| V4-07 | Captions & Sync | 02,04 | Fixture com timestamps e mudança de duração da voz; legenda legível e sincronizada; exportações válidas. |
| V4-08 | Render Extensibility | 04,12 fundação | FFmpeg principal; render real com cancelamento, cache e preflight; equivalência de segmentos e render integral. |
| V4-09 | Multimodal Quality | 03,05,07,08 | Fixtures com defeitos conhecidos; relatório com evidência e localização; avaliação humana calibrada; sem autopublicação. |
| V4-10 | Studio UX | 01–09 incremental | Fluxo real de edição persistente, undo/redo, adicionar cena na mesma bancada, gerar faltantes, preview e render; testes navegador. |
| V4-11 | Asset Management | 00; fundação antes de 02–05 | Licença desconhecida bloqueia publicação; hash e referências preservados; restauração testada. |
| V4-12 | Reliability & Scale | 00; transversal | Testes de falha e restart; nenhuma cobrança duplicada em fixture; limites e readiness verificáveis. |
| V4-13 | Professional Pilot | Todas as fases aplicáveis | Comparação pareada com mesmo roteiro de baseline; três estilos quando orçamento permitir; aprovação humana e licença antes de publicar. |

Ordem: 00; fundações 01/04/11/12; 02/03/05; 06/07/08; 09/10; 13. UX e QA incrementais desde a primeira entrega. Divida 04,11,12 em fundação e conclusão para evitar dependências circulares. Nenhuma estimativa de prazo é compromisso.

## Complemento V4.1
Preservar fases e IDs. Critérios vinculados em [consolidação](V4.1-CONSOLIDATION.md). Após fundações 01/04/11/12, entregar vertical slice 60–90s assim que capacidades mínimas 02/03/05/06/07/08 estiverem disponíveis; não esperar todas as atividades. V4-13 amplia para 5min e 15–20min, com benchmark humano e Mac. Reconciliar F3/F7; Finder FI-00–11 independente e integrado via ContentBrief. Ver [pilotos](PROFESSIONAL-PILOT-SPEC.md).

## Pré-requisito compartilhado — Foundation & Stability
[Plano mínimo](../foundation-stability/PLAN.md): 4–7 dias estimados, FS-01/02/04/07 P0; FS-05/06 P1 proporcionais ao uso local; FS-03 CI/CD adiado. Completar V4-00 com evidência reutilizada, sem repetir regressão/baseline quando válida. Não criar terceira iniciativa funcional nem antecipar V4-12 inteira.

## Complemento Google AI Pro / External Media
[Especificação](GOOGLE-AI-PRO-INTEGRATION.md) e [GAI-01–09](GAI-EXECUTION-PLAN.md). Reutilizar 14 fases/227 atividades originais, sem novo MVP. Priorizar GAI-01 (fundação 04/11) + GAI-02 (10 incremental) após Foundation/V4-00, com vertical slice real de imagem/vídeo importados. GAI-09 mínimo precede APIs pagas. GAI-03–08 opcionais nas fases consumidoras; Drive P2. Sem CI/CD e sem duplicar trabalho ou somar estimativas sobrepostas.

## Distribuição por fase

| Fase | Implementação | Review |
|---|---|---|
| **V4-00 — Baseline** | Flash 3.8 | Carbon |
| **V4-01 — Providers** | Flash 3.8 / Hydrogen | Neon |
| **V4-02 — Voice** | Flash 3.8 | Carbon |
| **V4-03 — Audio** | Flash 3.8 | Carbon |
| **V4-04 — Composition** | Hydrogen | Neon |
| **V4-05 — Visual Motion** | Flash 3.8 | Carbon |
| **V4-06 — Creative Intelligence** | Hydrogen | Carbon |
| **V4-07 — Synchronization** | Hydrogen / Carbon | Neon |
| **V4-08 — Render Engine** | Hydrogen / Carbon | Neon |
| **V4-09 — Quality** | Flash 3.8 | Carbon |
| **V4-10 — Studio UX** | Flash 3.8 | Carbon |
| **V4-11 — Assets** | Flash 3.8 | Carbon |
| **V4-12 — Reliability** | Hydrogen / Carbon | Neon |
| **V4-13 — Pilot** | Flash 3.8 | Carbon + Humano |

## Recuperação de integração — develop (26/11/2026)
Status de homologação V4-01–13: revalidação pendente após revisão estática de 0257c04; não autoriza merge. [Achados](integration-stabilization/AUDIT-FINDINGS.md), [backlog INT-01–07](integration-stabilization/EXECUTION-BACKLOG.md), [gates](integration-stabilization/QUALITY-GATES.md) e [prompts](integration-stabilization/README.md) organizam integração sem substituir IDs originais. Preservar main, corrigir P0, comprovar execução real incremental e avaliação humana. Não iniciar Finder nem novas APIs pagas nesta recuperação.
