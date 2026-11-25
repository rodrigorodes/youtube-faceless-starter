# Produção assíncrona e custos

**Prefixo dos cenários:** `PRO`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

O coordenador de produção orquestra a execução assíncrona das etapas do vídeo através de um DAG acíclico canônico (research -> script -> factcheck -> storyboard -> assets -> render -> qa -> approval -> publish). Cada execução é representada por um ProductionRun com máquina de estados fechada. A concorrência entre workers é regulada por leases com fencing tokens monótonos e batimentos periódicos (heartbeat). Operações de ciclo de vida (pause, resume, retry, regenerate) controlam se o snapshot de configuração é congelado ou reavaliado. O BudgetGuard intercepta operações pagas, exige reserva prévia contra tetos configurados no canal e reconcilia confirmações ou estornos no usage_ledger.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `PRO.R01` | DAG de produção é fechado, acíclico e segue topologia obrigatória; transições de RunState e StageState são restritas à matriz canônica. | `renderer/app/studio/domain/production_run.py:35-57`, `renderer/app/studio/domain/production_run.py:246-255` | [PRO-01](#pro-01), [PRO-10](#pro-10) |
| `PRO.R02` | Chave de idempotência deve ser canônica ASCII em [a-z0-9._:-] com até 128 chars; repetição com mesmo payload devolve execução existente; payload divergente dispara ProductionIdempotencyConflict. | `renderer/app/studio/domain/production_run.py:195-220`, `renderer/app/studio/adapters/postgres/production_repo.py:194-253` | [PRO-02](#pro-02), [PRO-03](#pro-03), [PRO-04](#pro-04) |
| `PRO.R03` | Leases de estágio usam fencing tokens monótonos; expiração de lease ou batimento perdido revoga posse (LeaseLost) e impede que worker obsoleto grave resultado. | `renderer/app/studio/domain/production_run.py:390-420`, `renderer/app/studio/application/lease_heartbeat.py:21-50` | [PRO-05](#pro-05), [PRO-11](#pro-11) |
| `PRO.R04` | Operações de ciclo de vida: resume e retry preservam estritamente o snapshot congelado do run; regenerate e new_run criam novo run e resolvem nova configuração. | `renderer/app/studio/domain/production_run.py:59-98` | [PRO-06](#pro-06), [PRO-07](#pro-07) |
| `PRO.R05` | BudgetGuard valida limites por canal (teto por vídeo e mensal); operações pagas exigem reserva antecipada e são recusadas com BudgetDenied quando o saldo é insuficiente. | `renderer/app/studio/domain/channel_budget.py:23-125`, `renderer/app/studio/application/budget.py:61-120` | [PRO-08](#pro-08), [PRO-09](#pro-09) |
| `PRO.R06` | Reservas de orçamento confirmadas gravam lançamento no usage_ledger; falhas e cancelamentos estornam reservas pendentes impedindo cobrança órfã. | `renderer/app/studio/application/budget.py:400-475`, `renderer/app/studio/adapters/postgres/budget_repo.py:263-394` | [PRO-09](#pro-09) |
| `PRO.R07` | Cancelamento transiciona run para CANCELLED, encerra leases ativos e marca estágios pendentes como SKIPPED/CANCELLED sem derrubar o processo do worker. | `renderer/app/studio/domain/production_run.py:246-259`, `renderer/app/studio/adapters/postgres/production_repo.py:596-618` | [PRO-10](#pro-10) |
| `PRO.R08` | CostBreakdown projeta custos por provedor antes da execução e consolida valores reais gastos e economizados via cache. | `renderer/app/studio/application/panel.py:82-117`, `renderer/app/studio/domain/channel_budget.py:118-140` | [PRO-12](#pro-12) |

## Resumo dos cenários

Total: 12 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [PRO-01](#pro-01) | Execução de estágios respeita topologia e dependências do DAG | feliz | PRO.R01 | `A_PROJETAR` |
| [PRO-02](#pro-02) | Reenvio de solicitação com mesma chave de idempotência retorna o mesmo run | feliz | PRO.R02 | `A_PROJETAR` |
| [PRO-03](#pro-03) | Chave de idempotência reutilizada com payload divergente causa conflito | erro | PRO.R02 | `A_PROJETAR` |
| [PRO-04](#pro-04) | Chave de idempotência com caracteres proibidos ou formato inválido | borda/erro | PRO.R02 | `A_PROJETAR` |
| [PRO-05](#pro-05) | Expiração de lease impede commit de estágio por worker obsoleto | concorrencia/erro | PRO.R03 | `A_PROJETAR` |
| [PRO-06](#pro-06) | Retry e Resume mantêm snapshot de configuração inalterado | regressao | PRO.R04 | `A_PROJETAR` |
| [PRO-07](#pro-07) | Regenerate cria nova execução e resolve configuração atual | feliz | PRO.R04 | `A_PROJETAR` |
| [PRO-08](#pro-08) | Operação paga é bloqueada quando saldo ou teto do canal é excedido | erro/borda | PRO.R05 | `A_PROJETAR` |
| [PRO-09](#pro-09) | Falha de estágio cancela e estorna reserva de orçamento pendente | feliz/erro | PRO.R05, PRO.R06 | `A_PROJETAR` |
| [PRO-10](#pro-10) | Cancelamento interrompe pipeline e marca estágios pendentes | borda | PRO.R01, PRO.R07 | `A_PROJETAR` |
| [PRO-11](#pro-11) | Disputa simultânea de dois workers pelo mesmo estágio elege um único executor | concorrencia | PRO.R03 | `A_PROJETAR` |
| [PRO-12](#pro-12) | CostBreakdown reflete custos previstos e consolida economia de cache | volume/regressao | PRO.R08 | `A_PROJETAR` |

## Cenários

### PRO-01 — Execução de estágios respeita topologia e dependências do DAG

- **Tipo:** feliz
- **Regras:** PRO.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Garantir que nenhum estágio seja acionado antes da conclusão satisfatória dos seus predecessores no grafo.
- **Pré-condições:** Pipeline padrão instanciado em ambiente descartável com repositório em memória.
- **Dados:** Vídeo recém-criado disparado para produção completa.
- **Passos:**
  1. Criar run com estágios do pipeline canônico.
  2. Verificar que apenas 'research' ou 'script' tornam-se elegíveis inicialmente.
  3. Completar 'script' e confirmar liberação de 'factcheck' e 'storyboard'.
  4. Tentar avançar 'render' enquanto 'assets' ainda está PENDING.
- **Esperado:** Estágios executam na ordem topológica; tentativa de pular predecessores lança InvalidProductionTransition; estado do run passa de CREATED para RUNNING.
- **Limitações:** Teste com pipeline simulado não executa lógica interna dos adapters reais.
- **Automação:** camada `unit`; referência `tests/test_production_flow_db.py:20-60`

### PRO-02 — Reenvio de solicitação com mesma chave de idempotência retorna o mesmo run

- **Tipo:** feliz
- **Regras:** PRO.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar duplicação acidental de execuções quando clientes realizam retentativas de rede idênticas.
- **Pré-condições:** Canal e vídeo válidos; repositório de produção ativo.
- **Dados:** Idempotency-Key: 'prod.video-123.run-1' com payload idêntico.
- **Passos:**
  1. Enviar POST /studio/videos/123/production/start com a chave.
  2. Capturar run_id gerado na primeira resposta.
  3. Repetir a requisição com o mesmo payload e a mesma chave exata.
- **Esperado:** Segunda requisição retorna HTTP 200/201 com exatamente o mesmo run_id; nenhum novo registro de run é criado no banco.
- **Limitações:** Não testa alta concorrência de milissegundos entre nós distintos.
- **Automação:** camada `mock`; referência `tests/test_production_api.py:45-75`

### PRO-03 — Chave de idempotência reutilizada com payload divergente causa conflito

- **Tipo:** erro
- **Regras:** PRO.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Bloquear reaproveitamento indevido de chave para ações ou parâmetros diferentes.
- **Pré-condições:** Run previamente criado com chave 'k-alpha'.
- **Dados:** Chave 'k-alpha' enviada primeiro com pipeline 'standard', depois com pipeline 'custom_fast'.
- **Passos:**
  1. Registrar solicitação inicial com sucesso.
  2. Enviar nova requisição usando 'k-alpha' mas alterando o corpo da requisição.
- **Esperado:** Serviço rejeita com erro explícito ProductionIdempotencyConflict ou HTTP 409 Conflict; a execução original não é alterada.
- **Limitações:** Validação de hash do payload depende do serializador canônico.
- **Automação:** camada `unit`; referência `tests/test_production_run.py:80-110`

### PRO-04 — Chave de idempotência com caracteres proibidos ou formato inválido

- **Tipo:** borda/erro
- **Regras:** PRO.R02
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Impedir poluição e vulnerabilidades de injeção ou colisão por caracteres invisíveis ou Unicode.
- **Pré-condições:** Cliente de API configurado para chamar endpoint de início de produção.
- **Dados:** Variantes: 'PROD_KEY_UPPER', 'chave com espaço', 'chave-com-emoji-🚀', chave com 129 caracteres.
- **Passos:**
  1. Submeter cada variante no header Idempotency-Key ou campo correspondente.
  2. Observar validação sintática antes de acessar banco.
- **Esperado:** Todas as chaves não canônicas são recusadas com erro de validação (HTTP 400 ou InvalidIdempotencyKey); nenhuma transação é aberta.
- **Limitações:** Não cobre headers malformados no nível de proxy HTTP reverso.
- **Automação:** camada `unit`; referência `tests/test_production_run.py:120-145`

### PRO-05 — Expiração de lease impede commit de estágio por worker obsoleto

- **Tipo:** concorrencia/erro
- **Regras:** PRO.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Garantir integridade do estado e evitar escrita dupla quando um worker perde conectividade temporariamente.
- **Pré-condições:** Estágio 'render' alocado para Worker-1 com lease TTL de 5 segundos.
- **Dados:** Worker-1 assume render; tempo avança 10 s sem heartbeat; Worker-2 adquire o lease com fencing token superior.
- **Passos:**
  1. Worker-1 adquire lease (fencing_token=1).
  2. Simular congelamento/atraso do Worker-1.
  3. Worker-2 detecta lease expirado e assume o estágio (fencing_token=2).
  4. Worker-1 acorda e tenta submeter conclusão do estágio com fencing_token=1.
- **Esperado:** Tentativa de escrita do Worker-1 é rejeitada com LeaseLost / fencing conflict; Worker-2 permanece como único proprietário legítimo.
- **Limitações:** Requer relógio simulado ou manipulação direta de timestamp de lease no banco de teste.
- **Automação:** camada `local-integrado`; referência `tests/test_lease_heartbeat.py:30-85 e tests/test_lease_recovery_concurrency.py:40-95`

### PRO-06 — Retry e Resume mantêm snapshot de configuração inalterado

- **Tipo:** regressao
- **Regras:** PRO.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Assegurar reproducibilidade estrita da execução sem que mudanças concorrentes na configuração viva afetem um run em andamento.
- **Pré-condições:** Run falho no estágio 'qa', criado com estilo visual 'dark_cinematic' e voz 'faber'.
- **Dados:** Configuração ativa do canal é alterada para estilo 'bright_minimal' e voz 'vitoria'.
- **Passos:**
  1. Alterar a configuração do canal no banco.
  2. Disparar RunOperation.RETRY para o run falho.
  3. Inspecionar a configuração efetiva injetada no handler de retry.
- **Esperado:** O handler de retry recebe exatamente o snapshot gravado na criação do run ('dark_cinematic'/'faber'); as novas preferências vivas do canal são ignoradas.
- **Limitações:** Não testa migração de esquema de snapshot entre versões do software.
- **Automação:** camada `mock`; referência `tests/test_production_service.py:110-145`

### PRO-07 — Regenerate cria nova execução e resolve configuração atual

- **Tipo:** feliz
- **Regras:** PRO.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Permitir que o operador gere uma versão alternativa adotando as alterações recentes do canal.
- **Pré-condições:** Run-1 concluído ou em pausa; canal teve estilo visual atualizado.
- **Dados:** POST /studio/videos/123/production/regenerate com nova chave de idempotência.
- **Passos:**
  1. Atualizar estilo do canal.
  2. Disparar regenerate a partir do Run-1.
  3. Comparar run_id e config_snapshot entre Run-1 e Run-2.
- **Esperado:** Run-2 é gerado com identificador inédito, estado CREATED e snapshot refletindo as configurações recém-atualizadas; Run-1 permanece preservado no histórico.
- **Limitações:** Não invalida artefatos já gerados do Run-1.
- **Automação:** camada `local-integrado`; referência `tests/test_production_api.py:90-125`

### PRO-08 — Operação paga é bloqueada quando saldo ou teto do canal é excedido

- **Tipo:** erro/borda
- **Regras:** PRO.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Proteger o operador contra custos excessivos antes de invocar APIs de IA pagas.
- **Pré-condições:** Canal com limite mensal de R$ 50,00 e gasto acumulado de R$ 48,00 no mês.
- **Dados:** Estágio de geração de imagem com custo estimado de R$ 3,50.
- **Passos:**
  1. Tentar iniciar reserva para geração de imagens da cena.
  2. Verificar retorno do BudgetGuard.
  3. Conferir se o provedor externo foi acionado.
- **Esperado:** BudgetGuard lança BudgetDenied com motivo 'monthly_limit_exceeded'; estágio falha com erro orçamentário; nenhuma chamada de rede é feita ao provedor.
- **Limitações:** Valores monetários dependem da tabela de preços configurada no mock.
- **Automação:** camada `unit`; referência `tests/test_budget_guard.py:40-80 e tests/test_channel_budget.py:30-65`

### PRO-09 — Falha de estágio cancela e estorna reserva de orçamento pendente

- **Tipo:** feliz/erro
- **Regras:** PRO.R05, PRO.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Garantir que custos não incorridos não permaneçam bloqueando o saldo do canal após erros técnicos.
- **Pré-condições:** Reserva de R$ 2,00 criada em estado RESERVED para o estágio 'script'.
- **Dados:** Adapter de roteiro falha com timeout de rede.
- **Passos:**
  1. Criar reserva orçamentária para a etapa.
  2. Simular exceção no handler de geração de roteiro.
  3. Verificar reconciliação de orçamento no bloco finally/error handler.
- **Esperado:** A reserva passa para o estado RELEASED/CANCELLED; saldo disponível do canal é restaurado; nenhuma entrada confirmada é gravada no usage_ledger.
- **Limitações:** Falhas catastróficas com queda repentina de processo exigem worker de reconciliação de reservas órfãs.
- **Automação:** camada `local-integrado`; referência `tests/test_budget_reservations.py:50-95`

### PRO-10 — Cancelamento interrompe pipeline e marca estágios pendentes

- **Tipo:** borda
- **Regras:** PRO.R01, PRO.R07
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Assegurar que um cancelamento voluntário do operador interrompa o consumo de recursos.
- **Pré-condições:** Run com 'script' em andamento e demais estágios PENDING.
- **Dados:** Operador solicita cancelamento via POST /studio/runs/123/cancel.
- **Passos:**
  1. Disparar cancelamento durante o processamento de 'script'.
  2. Observar encerramento do worker e atualização de estados.
- **Esperado:** Run transiciona para CANCELLED; estágios subsequentes são marcados como CANCELLED/SKIPPED; lease ativo é liberado imediatamente.
- **Limitações:** Operações atômicas de I/O em andamento (ex: escrita de arquivo em disco) podem concluir antes da interrupção.
- **Automação:** camada `mock`; referência `tests/test_falha_producao.py:35-66`

### PRO-11 — Disputa simultânea de dois workers pelo mesmo estágio elege um único executor

- **Tipo:** concorrencia
- **Regras:** PRO.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar execução redundante ou sobrescrita competitiva do mesmo estágio por instâncias paralelas.
- **Pré-condições:** Dois workers assíncronos prontos e concorrendo pela fila de estágios elegíveis.
- **Dados:** Estágio 'assets' torna-se elegível simultaneamente para Worker-A e Worker-B.
- **Passos:**
  1. Disparar tentativa de claim/lock no mesmo instante com barreira de sincronização.
  2. Verificar resposta do repositório de leases para ambos os workers.
- **Esperado:** Exatamente um worker obtém o lease com sucesso; o segundo worker recebe conflito (None ou LeaseUnavailable) e não inicia processamento.
- **Limitações:** Exige suporte a lock atômico ou cláusula FOR UPDATE / SKIP LOCKED no banco relacional.
- **Automação:** camada `local-integrado`; referência `tests/test_lease_recovery_concurrency.py:20-65`

### PRO-12 — CostBreakdown reflete custos previstos e consolida economia de cache

- **Tipo:** volume/regressao
- **Regras:** PRO.R08
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Validar cálculo consolidado de custos por categoria, provedor e economia gerada por reúso.
- **Pré-condições:** Run contendo 10 cenas, das quais 4 reaproveitaram áudio e imagem do cache.
- **Dados:** Preços sintéticos: R$ 0,10 por imagem gerada, R$ 0,05 por narração.
- **Passos:**
  1. Executar montagem do plano de custos.
  2. Consultar CostBreakdown gerado para o vídeo.
  3. Comparar custo total sem cache vs custo faturado com cache.
- **Esperado:** Relatório exibe detalhamento correto por provedor; campo de economia (saved_by_cache) reflete exatamente o valor das 4 cenas reutilizadas; total faturado corresponde à diferença.
- **Limitações:** Cálculo matemático puro; não valida débito financeiro bancário.
- **Automação:** camada `unit`; referência `tests/test_cost_breakdown_api.py:25-63`

## Resumo do capítulo

12 cenários A_PROJETAR. Plano documental direto, sem workflow e sem executar chamadas reais nem consumir provedores pagos. Avalia integridade do DAG, idempotência, isolamento de leases, persistência de snapshots, guardas orçamentárias e estornos.
