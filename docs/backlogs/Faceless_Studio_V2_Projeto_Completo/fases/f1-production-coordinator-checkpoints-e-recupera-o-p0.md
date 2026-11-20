# F1 — Production Coordinator, checkpoints e recuperação (P0)

**Prioridade:** P0  
**Dependências:** F0: baseline e segurança.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** implementar a jornada sob comando único sem acoplar o domínio ao orquestrador.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F1-01` | Criar `ProductionRun`/`StageExecution`/outbox e migrations. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-02` | Definir DAG de estágios, dependências e contratos I/O; manter checkpoints do vídeo atuais. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-03` | Criar `ProductionCoordinator` e executor/worker port; avaliar se aproveitar worker atual ou adapter assíncrono dedicado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-04` | Criar `POST production-runs`, status e eventos de progresso. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-05` | Implementar etapas research/script/factcheck/storyboard/assets/render/QA/approval/publish como handlers; nenhum efeito irreversível sem gate. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-06` | Idempotency key, CAS, lease, heartbeat, fencing, checkpoint e replay determinístico. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-07` | Pausa humana persistida: liberar worker e retomar com versão aprovada; sem processo aguardando bloqueado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-08` | Retry seletivo, cancelamento, DLQ e trilha de auditoria. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F1-09` | Testes de falha entre persistência, provider call, commit e recuperação; concorrência entre 2 workers. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

iniciar uma vez pela UI/API; reexecutar chamada não duplica vídeo ou custos; crash/restart retoma corretamente; etapa humana não ocupa worker; execução concorrente não corrompe estado.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Zero duplicação de execução em testes de replay; recuperação após crash com checkpoints válidos.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
