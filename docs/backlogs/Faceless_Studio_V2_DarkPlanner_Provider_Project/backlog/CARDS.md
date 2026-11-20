# Backlog executável — DarkPlanner Audio Provider

| ID | Fase | Prioridade | Card | Entregável | Critério de aceite | Dependências |
|---|---|---|---|---|---|---|
| DPA-01 | F0 | P0 | Validar API oficial, preços, quotas, termos e uso SaaS | Checklist discovery + decisão GO/NO-GO | Nenhum endpoint fictício; docs oficiais obtidos e aprovados | — |
| DPA-02 | F0 | P0 | Auditar fluxo atual e segurança de credenciais | Baseline Piper/Voice/Render + riscos | Secrets fora de ZIP/logs/config de domínio | DPA-01 |
| DPA-03 | F1/F5 | P0 | Definir e aprovar ADR, contrato e capabilities | ADR + tests de contrato fake | Sem imports do fornecedor em core | DPA-02 |
| DPA-04 | F5 | P0 | Implementar harness de contrato e FakeVoice | Testes parametrizados Piper/fake | WAV+duração; regressão Piper zero | DPA-03 |
| DPA-05 | F5 | P1 | Implementar HTTP client e auth isolados | Client mockado, timeout, allowlist | HTTP erros tipificados; tokens ocultos | DPA-01,DPA-04 |
| DPA-06 | F5 | P1 | Implementar DarkPlanner adapter e WAV normalization | Adapter + registry em composition | voice spec troca sem mudança em RunRender | DPA-05 |
| DPA-07 | F1/F5 | P0 | Tratar jobs remotos, checkpoint e reconciliação | Workflow de job se API async | Sem duplicar submits após crash | DPA-01,DPA-06 |
| DPA-08 | F1/F10 | P1 | Integrar metering, budget, cache e fallback opt-in | Métricas por provider e vídeo | Reserva antes de gastos; fallback desativado | DPA-06 |
| DPA-09 | F10 | P1 | Configurar provider e voz por canal | Formulário e endpoint protegido | Dados públicos sem keys; validação provider | DPA-06 |
| DPA-10 | F6 | P1 | Preview de voz e regeneração por cena | UI de teste e regen granular | Somente cena escolhida regenerada | DPA-08,DPA-09 |
| DPA-11 | F11 | P1 | BYOK e isolamento por organização | Secret resolver + RBAC + quotas | A não lê keys, mídia ou jobs de B | DPA-09 |
| DPA-12 | F5/F11 | P0 | Testar E2E, documentar rollback e habilitar por flag | QA, runbook, rollout e decisão release | Canal piloto validado; rollback Piper | DPA-07,DPA-08,DPA-10,DPA-11 |

## Estratégia de PRs
- **PR1** Discovery + ADR + contract harness (sem chamadas comerciais).
- **PR2** Adapter HTTP e WAV com sandbox ou mocks; integração à composition root.
- **PR3** Persistência/recuperação/custos (se API assíncrona).
- **PR4** UI seleção/preview e settings por canal.
- **PR5** BYOK + QA E2E + rollout.

## Regras
Cards externos dependem da documentação oficial; estágio sem suporte API vira `BLOCKED` com justificativa. Não converter hipótese comercial em funcionalidade implementada.
