# Plano FI-00–11 (proposto)
Cada fase: reconciliar HEAD, testes existentes, delta mínimo, owner, custo, rollback, comandos e evidências. P0 necessário para POC aplicável, P1 após fundação, P2 opcional. Cada atividade abaixo pendente; não confundir com as 227 da V4.
| Fase | Entregas / atividades | Gate |
|---|---|---|
| FI-00 P0 | 00.01 mapear Trend/Research/VE/V2; 00.02 inventário dados/termos; 00.03 validação de aprovações; 00.04 default-deny capabilities | matriz assinada GO/NO-GO; fixture offline |
| FI-01 P0 | 01.01 ports/reuse Registry; 01.02 busca parametrizada idioma/região; 01.03 paginação e dedup; 01.04 quotas/cache; 01.05 proveniência | contratos e falhas, coleta real só autorizada |
| FI-02 P0 | 02.01 channel identity; 02.02 filtros formato/idade; 02.03 discovery por seed; 02.04 snapshots autorizados | distinção first_seen/created, resultados parciais |
| FI-03 P0 | 03.01 lifetime vs recent VPH; 03.02 coortes comparáveis; 03.03 confiança/amostra; 03.04 substituir heurística após validação | fixtures idade, correção views, zero, dados insuficientes |
| FI-04 P0 | 04.01 topic extraction; 04.02 queries EN/ES/PT; 04.03 semantic matching; 04.04 relatório de cobertura; 04.05 recheck | conjunto rotulado; precision/recall, falsos negativos, quota |
| FI-05 P0 | 05.01 sinais observáveis; 05.02 ranking explicável; 05.03 freshness/timing; 05.04 gate independente | backtest temporal permitido; não prever viralização |
| FI-06 P1 | 06.01 coleções; 06.02 recomendações; 06.03 dedup/filtros | salvar e recomendar com justificativa |
| FI-07 P0 | 07.01 contrato ContentBrief; 07.02 aprovação e idempotência; 07.03 integração Research/Studio; 07.04 entrada manual | E2E fixture sem gasto, Finder offline não bloqueia |
| FI-08 P1 | 08.01 cards/filters; 08.02 detalhe de evidências; 08.03 scanner; 08.04 salvar/enviar; 08.05 estados erro/parcial | browser e persistência, sem score enganoso |
| FI-09 P1 | 09.01 monitoramento consentido; 09.02 alertas dedup; 09.03 limites e exclusão | restart, quota, opt-out |
| FI-10 P2 | 10.01 contrato API; 10.02 extensão menor privilégio; 10.03 ações autorizadas; 10.04 segurança | sem scraping/segredo, aprovação distribuição |
| FI-11 P0 | 11.01 benchmark 30 canais (ou sintéticos); 11.02 avaliação cega scanner; 11.03 tempo garimpo; 11.04 piloto integrado; 11.05 relatório | meta proposta reduzir tempo >=50%, medir precisão/cobertura/custo, GO/NO-GO |
Dependências: 00→01→02→03; 01→04; 02/03/04→05; 05→07; 02→06; 04/05/06/07→08; 06→09; 08→10; 07 + fases aplicáveis→11. UX/testes incrementais. Dados reais somente após compliance específico; POC offline não comprova cobertura real. V4-00 e FI-00 podem avançar independentemente após autorização.

## Pré-requisito compartilhado
Reutilizar [Foundation](../foundation-stability/PLAN.md). Não duplicar testes/infraestrutura; completar somente lacunas FI-00, sem dispensar aprovação de dados derivados, armazenamento e providers. FS-03 CI/CD adiado.
