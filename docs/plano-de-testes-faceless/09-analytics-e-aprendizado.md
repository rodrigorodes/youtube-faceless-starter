# Analytics e aprendizado

**Prefixo dos cenários:** `ANA`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

A coleta exige canal conectado, escopo de leitura e publicação com ID remoto. Observações têm origem, janela, unidade e vínculo de versão. Dashboard deduplica observações e separa formatos; recomendações são propostas humanas, não mudanças automáticas.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `ANA.R01` | Sem prontidão, coleta não chama provedor; ausência não equivale a zero. | `renderer/app/studio/application/analytics_collection.py:148-192`, `renderer/app/studio/application/analytics_collection.py:203-232` | [ANA-01](#ana-01), [ANA-02](#ana-02), [ANA-05](#ana-05) |
| `ANA.R02` | ID determinístico por vídeo/métrica/janela/ID remoto permite persistência idempotente; pilar deve pertencer ao projeto. | `renderer/app/studio/application/analytics_collection.py:165-173`, `renderer/app/studio/application/analytics_collection.py:207-230`, `tests/test_analytics_repo.py:121-144` | [ANA-03](#ana-03), [ANA-04](#ana-04) |
| `ANA.R03` | Dashboard mantém recorte por vídeo/pilar/período, separa short e long, não faz média de taxas nem soma cobertura incompleta. | `renderer/app/studio/application/analytics_dashboard.py:1-10`, `tests/test_analytics_dashboard.py:226-272`, `tests/test_analytics_repo.py:144-155` | [ANA-04](#ana-04), [ANA-05](#ana-05), [ANA-07](#ana-07), [ANA-08](#ana-08) |
| `ANA.R04` | Amostra mínima é três vídeos comparáveis; recomendação tem revisão humana e não aplicação automática; versões ausentes recebem motivo. | `renderer/app/studio/application/analytics_dashboard.py:60`, `renderer/app/studio/application/analytics_dashboard.py:225-238`, `renderer/app/studio/application/analytics_collection.py:97-125` | [ANA-01](#ana-01), [ANA-07](#ana-07) |
| `ANA.R05` | Valores conhecidos precisam ser finitos, não negativos e percentuais até 100; observação mais recente vence dedupe. | `renderer/app/studio/application/analytics_collection.py:128-136`, `renderer/app/studio/application/analytics_dashboard.py:301-315` | [ANA-03](#ana-03), [ANA-06](#ana-06) |
| `ANA.R06` | Alerta bridge é local ao processo e expira em 300 s; expiração OAuth exige metadado confiável com timezone e não prova validade do token. | `renderer/app/studio/application/observability.py:11-54` | [ANA-08](#ana-08) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [ANA-01](#ana-01) | Coleta autorizada com origem e versões | feliz | ANA.R01, ANA.R04 | `A_PROJETAR` |
| [ANA-02](#ana-02) | Canal sem prontidão e dashboard vazio | erro/borda | ANA.R01 | `A_PROJETAR` |
| [ANA-03](#ana-03) | Repetição e concorrência de coleta | concorrencia/regressao | ANA.R02, ANA.R05 | `A_PROJETAR` |
| [ANA-04](#ana-04) | Filtros e isolamento de recortes | borda | ANA.R02, ANA.R03 | `A_PROJETAR` |
| [ANA-05](#ana-05) | Zero, ausência e agregação honesta | regressao | ANA.R01, ANA.R03 | `A_PROJETAR` |
| [ANA-06](#ana-06) | Limites numéricos e resposta inválida | erro/borda | ANA.R05 | `A_PROJETAR` |
| [ANA-07](#ana-07) | Recomendação exige amostra e decisão humana | borda/regressao | ANA.R03, ANA.R04 | `A_PROJETAR` |
| [ANA-08](#ana-08) | Alertas passivos e leitura em volume | volume/borda | ANA.R03, ANA.R06 | `A_PROJETAR` |

## Cenários

### ANA-01 — Coleta autorizada com origem e versões

- **Tipo:** feliz
- **Regras:** ANA.R01, ANA.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Rastrear métricas ao vídeo publicado.
- **Pré-condições:** Canal de fixture conectado com escopo; vídeo com script_version=2 e publicação/ID remoto.
- **Dados:** Janela de 7 dias terminada em instante UTC fixo; views=120.0 e ctr=3.5.
- **Passos:**
  1. Coletar pela porta mock.
  2. Consultar observações persistidas e dashboard.
  3. Inspecionar vínculos ausentes.
- **Esperado:** Valores medidos preservam origem API, unidade, janela e versões conhecidas; brief/packaging ausentes exibem motivo, sem versão inventada.
- **Limitações:** Texto atual de atribuição declara brief/packaging não persistidos; revisar se a persistência evoluir.
- **Automação:** camada `mock`; referência `Existentes: tests/test_analytics_collection.py:133; tests/test_analytics_dashboard.py:260.`

### ANA-02 — Canal sem prontidão e dashboard vazio

- **Tipo:** erro/borda
- **Regras:** ANA.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar números fictícios ou chamada não autorizada.
- **Pré-condições:** Fixtures separadas sem canal, sem escopo e sem publicação remota.
- **Dados:** Projeto vazio; vídeo local sem youtube_video_id.
- **Passos:**
  1. Solicitar coleta em cada variante.
  2. Abrir dashboard.
  3. Repetir com erro de autorização e timeout controlado na porta pronta.
- **Esperado:** Sem prontidão há zero chamadas; estado indisponível traz motivo e não 0%; falhas conhecidas da porta não viram métricas medidas; vazio informa ausência.
- **Limitações:** Timeout deve ser convertido para AnalyticsUnavailable pela porta; exceção arbitrária não está garantida pelo serviço.
- **Automação:** camada `mock`; referência `Existentes: tests/test_analytics_collection.py:111-174; tests/test_analytics_dashboard.py:179.`

### ANA-03 — Repetição e concorrência de coleta

- **Tipo:** concorrencia/regressao
- **Regras:** ANA.R02, ANA.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não multiplicar observações nem somar retries.
- **Pré-condições:** Postgres descartável; duas coletas sincronizadas com mesma chave lógica.
- **Dados:** Vídeo v1, mesma janela, views=100.0; terceira coleta em janela diferente com views=130.0.
- **Passos:**
  1. Coletar duas vezes sequencialmente e duas em paralelo.
  2. Consultar chaves/contagens persistidas.
  3. Inserir nova janela e consultar dedupe no dashboard.
- **Esperado:** Uma observação por chave lógica, sem erro de unicidade exposto; janela distinta é preservada; dashboard escolhe coleta mais recente sem somar duplicatas.
- **Limitações:** Concorrência é garantia desejada a ampliar; testes existentes de idempotência sequencial não a comprovam.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_analytics_collection.py:205; tests/test_analytics_repo.py:121; tests/test_analytics_dashboard.py:364; paralelo proposto.`

### ANA-04 — Filtros e isolamento de recortes

- **Tipo:** borda
- **Regras:** ANA.R02, ANA.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não misturar canais, vídeos, pilares ou períodos.
- **Pré-condições:** Projetos A/B; pilares próprios; medições dentro e fora da janela.
- **Dados:** A contém v1/p1 e v2/p2; B contém v3/p3; janela de 7 dias e observação de 30 dias atrás.
- **Passos:**
  1. Filtrar A por v1 e p1.
  2. Trocar período e conferir linhas e cobertura.
  3. Solicitar v3/p3 no contexto A.
- **Esperado:** Somente linhas pertencentes ao recorte; ausência tem motivo; vídeo/pilar estrangeiro é recusado em vez de atribuído a A.
- **Limitações:** Filtros analíticos não substituem revisão de autorização multiusuário; não afirmar isolamento completo de tenant.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_analytics_repo.py:144; tests/test_analytics_collection.py:192; tests/test_analytics_dashboard.py:356.`

### ANA-05 — Zero, ausência e agregação honesta

- **Tipo:** regressao
- **Regras:** ANA.R01, ANA.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Impedir agregado enganoso.
- **Pré-condições:** Medições sintéticas short/long, origens e cobertura controladas.
- **Dados:** Short s1 views=0; s2 views ausente; long l1 views=200; CTRs 2% e 20%.
- **Passos:**
  1. Consultar cada vídeo.
  2. Consultar agregado por formato com cobertura incompleta.
  3. Misturar origens e consultar CTR agregado.
- **Esperado:** Zero é exibido como zero; ausência não vira zero; short/long separados; views incompletas não somadas; CTR não é média simples 11%; origem mista é desconhecida.
- **Limitações:** Não inferir taxa ponderada sem denominadores; rótulos não comprovam estatística causal.
- **Automação:** camada `unit`; referência `Existentes: tests/test_analytics_dashboard.py:212-253; tests/test_analytics_learning.py:204-238.`

### ANA-06 — Limites numéricos e resposta inválida

- **Tipo:** erro/borda
- **Regras:** ANA.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar dados inválidos sem persistência parcial.
- **Pré-condições:** Porta mock e repositório espião; coleção inicialmente vazia.
- **Dados:** ctr=0.0/100.0/100.1; views=-1.0; NaN; infinito; métrica desconhecida; payload malformado.
- **Passos:**
  1. Coletar casos válidos de fronteira.
  2. Injetar cada inválido após um ponto válido.
  3. Inspecionar erro e chamadas de save_measurements.
- **Esperado:** Fronteiras válidas persistem; inválidos recusam lote sem salvar parte. Desejado na API: indisponibilidade explícita sem stack trace; verificar mapeamento antes de afirmar essa garantia.
- **Limitações:** Validação dos pontos ocorre fora do try da porta no serviço: resposta inválida pode propagar AnalyticsUnavailable; tratamento HTTP não comprovado nesta leitura.
- **Automação:** camada `mock`; referência `Existentes: tests/test_analytics_collection.py:271-282; extensão proposta ao serviço e API.`

### ANA-07 — Recomendação exige amostra e decisão humana

- **Tipo:** borda/regressao
- **Regras:** ANA.R03, ANA.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Separar aprendizagem de alteração automática.
- **Pré-condições:** Pilar com vídeos comparáveis e medições reais de fixture; configurações registradas antes.
- **Dados:** Dois vídeos, depois três do mesmo formato/pilar; decisão aceitar e depois recusar.
- **Passos:**
  1. Gerar dashboard com dois e três vídeos.
  2. Registrar decisão da recomendação elegível.
  3. Reabrir histórico e comparar configurações.
- **Esperado:** Dois vídeos não geram recomendação suficiente; três podem gerar proposta de baixa confiança com observações; decisão fica registrada sem mudar configuração; histórico não declara A/B nativo da plataforma.
- **Limitações:** Três é limiar de produto, não significância estatística; não promete ganho de audiência.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_analytics_dashboard.py:285-323; tests/test_analytics_repo.py:299.`

### ANA-08 — Alertas passivos e leitura em volume

- **Tipo:** volume/borda
- **Regras:** ANA.R03, ANA.R06
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Manter alertas precisos e medir custo de consulta sem inventar SLA.
- **Pré-condições:** Relógio fake; 100 vídeos sintéticos com cinco métricas por janela; sem rede.
- **Dados:** Falha bridge repetida; avanço de 299 e 300 s; expiração OAuth em 7 dias; 500 observações.
- **Passos:**
  1. Observar falha repetida e expiração do estado.
  2. Consultar dashboard 30 vezes após cinco aquecimentos.
  3. Medir p50/p95, contagens e consumo, com recursos da máquina registrados.
- **Esperado:** Alerta bridge não duplica na mesma sequência; aos 300 s estado unknown; expiração não declara autenticação válida. Meta exploratória proposta: p95 local até 2 s para esse conjunto, sem perda de linhas.
- **Limitações:** Meta depende do hardware e deve ser calibrada; não é SLA. Alerta é por processo, não consenso distribuído; desempenho ainda não medido.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_alerts_p06.py:17-111; benchmark de dashboard proposto.`

## Resumo do capítulo

Plano documental com oito cenários A_PROJETAR; referências existentes não significam testes executados.
