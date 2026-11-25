# 03 — Tendências e ideias

**Prefixo dos cenários:** `TEN`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

Tendências são observações persistidas com fonte, janela, métrica e evidências. A ingestão valida o lote antes da escrita; favoritos guardam snapshots separados. Ideias usam modelo para notas e domínio para ordenação, com validação e controle de custo. Coleta n8n é coberta em OPS.C08.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `TEN.R01` | Ingestão exige projeto existente e lote de 1 a 50 itens; valida todo o lote antes do upsert. Fonte usa HTTPS e host permitido. | `renderer/app/studio/application/trends.py:13-17`, `renderer/app/studio/domain/trends.py:25-50` | [TEN.C01](#tenc01), [TEN.C02](#tenc02), [TEN.C03](#tenc03) |
| `TEN.R02` | Datas exigem timezone; observed_at admite até 300 segundos futuros; janela não pode inverter. Código compara timedelta.days > 31, portanto a fronteira efetiva difere de um máximo estrito de 31 dias. | `renderer/app/studio/domain/trends.py:52-62` | [TEN.C03](#tenc03) |
| `TEN.R03` | Upsert identifica projeto, tópico normalizado, fonte e fim de janela; atualiza métricas/evidências mas não source_url no conflito. Favoritos têm chave projeto e video_id. | `renderer/app/studio/adapters/postgres/trend_repo.py:106-149`, `renderer/app/studio/adapters/postgres/trend_repo.py:197-245` | [TEN.C04](#tenc04), [TEN.C05](#tenc05) |
| `TEN.R04` | Pontuação aceita 1 a 20 tópicos únicos, não vazios, de até 150 caracteres; resposta cobre exatamente todos os tópicos. Ordem é decrescente e empate preserva ordem de entrada. | `renderer/app/studio/application/ideas.py:45-60`, `renderer/app/studio/application/ideas.py:69-96` | [TEN.C06](#tenc06), [TEN.C07](#tenc07) |
| `TEN.R05` | Guard de custo antecede chamada paga; saída inválida não vira ranking parcial. Com PaidOperationGuard, validação antecede settlement; sem ele, uso já é registrado antes do parse. | `renderer/app/studio/application/ideas.py:81-94` | [TEN.C07](#tenc07), [TEN.C08](#tenc08) |
| `TEN.R06` | Evidência admite URL HTTP e até 10 entradas; a allowlist de source_url não valida o host de cada evidence.url. Ingestão não prova veracidade da fonte. | `renderer/app/studio/domain/trends.py:13-36`, `renderer/app/studio/domain/trends.py:47-50` | [TEN.C01](#tenc01), [TEN.C03](#tenc03) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [TEN.C01](#tenc01) | Ingerir tendência com fonte e evidência | feliz | TEN.R01, TEN.R06 | `A_PROJETAR` |
| [TEN.C02](#tenc02) | Recusar lote inteiro com fonte inválida | erro | TEN.R01 | `A_PROJETAR` |
| [TEN.C03](#tenc03) | Fronteiras de lote, evidências e datas | borda | TEN.R01, TEN.R02, TEN.R06 | `A_PROJETAR` |
| [TEN.C04](#tenc04) | Dois upserts da mesma tendência | concorrencia | TEN.R03 | `A_PROJETAR` |
| [TEN.C05](#tenc05) | Favorito isolado por projeto e atualizado por replay | regressao | TEN.R03 | `A_PROJETAR` |
| [TEN.C06](#tenc06) | Ranking estável com notas válidas | feliz | TEN.R04 | `A_PROJETAR` |
| [TEN.C07](#tenc07) | Limite de tópicos e resposta inválida | erro | TEN.R04, TEN.R05 | `A_PROJETAR` |
| [TEN.C08](#tenc08) | Budget bloqueia modelo e falha não confirma gasto válido | erro | TEN.R05 | `A_PROJETAR` |

## Cenários

### TEN.C01 — Ingerir tendência com fonte e evidência

- **Tipo:** feliz
- **Regras:** TEN.R01, TEN.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Persistir observação rastreável sem inventar métricas.
- **Pré-condições:** Projeto aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa existente em repositório fake; host www.googleapis.com permitido; relógio 2026-11-20T10:00:00Z.
- **Passos:**
  1. Ingerir tópico Energia solar, source_name=YouTube Data API, source_url=https://www.googleapis.com/youtube/v3/search, observed_at=2026-11-20T10:00:00Z, janela de 2026-11-13T10:00:00Z a 2026-11-20T10:00:00Z, metric_value=10.
  2. Anexar evidência title=Introdução, url=https://youtube.com/watch?v=abcdefghijk, views=null; reler resultado.
- **Esperado:** Um item aceito e fonte/janela/evidência preservadas; views desconhecido permanece null, não zero fabricado.
- **Limitações:** Não busca nem confirma conteúdo das URLs.
- **Automação:** camada `mock`; referência `tests/test_trends_domain.py:12-31; proposta de releitura com repositório fake`

### TEN.C02 — Recusar lote inteiro com fonte inválida

- **Tipo:** erro
- **Regras:** TEN.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar persistência parcial de lote inválido.
- **Pré-condições:** Projeto existente; spy no upsert; item válido de TEN.C01.
- **Passos:**
  1. Enviar lote com item válido e outro de source_url=https://evil.example/trends.
  2. Repetir com fonte http://www.googleapis.com/youtube/v3/search e depois projeto inexistente.
- **Esperado:** Host proibido, esquema inválido e projeto ausente são recusados; upsert não recebe lote parcial nem é chamado no erro.
- **Limitações:** Não testa SSRF de fetcher; ingestão apenas valida e persiste.
- **Automação:** camada `mock`; referência `tests/test_trends_domain.py:34-42,71-76; renderer/app/studio/application/trends.py:13-17`

### TEN.C03 — Fronteiras de lote, evidências e datas

- **Tipo:** borda
- **Regras:** TEN.R01, TEN.R02, TEN.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Documentar limites reais, inclusive truncamento de dias.
- **Pré-condições:** Relógio fixo em 2026-11-20T10:00:00Z; itens sintéticos válidos.
- **Passos:**
  1. Validar lotes de 0, 1, 50 e 51 itens; evidências com 10 e 11 entradas.
  2. Variar observed_at entre agora+300s, agora+301s e data sem timezone.
  3. Comparar janelas de 31 dias, 31 dias e 23 horas, 32 dias e janela invertida.
- **Esperado:** Aceita 1/50 itens e 10 evidências; recusa 0/51 e 11. Aceita +300s, recusa +301s/sem timezone. Código atual aceita 31d23h e recusa 32d/inversão; registrar diferença frente ao texto de máximo 31 dias.
- **Limitações:** Aceitação de 31d23h é caracterização de código, não regra de negócio aprovada.
- **Automação:** camada `unit`; referência `tests/test_trends_domain.py:45-68; extensão proposta para limites exatos`

### TEN.C04 — Dois upserts da mesma tendência

- **Tipo:** concorrencia
- **Regras:** TEN.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar unicidade sem presumir ordenação por observação mais nova.
- **Pré-condições:** Postgres descartável comprovado; duas conexões; mesma chave projeto/tópico/fonte/window_end.
- **Passos:**
  1. Disparar simultaneamente item Energia solar com metric_value=10 e outro com metric_value=20.
  2. Reenviar a chave com source_url diferente no mesmo host; consultar quantidade, métricas e URL.
- **Esperado:** Uma linha por chave; métrica final corresponde a uma escrita concluída, sem garantia de maior observed_at. source_url permanece o original no caminho de conflito, pois não participa do UPDATE.
- **Limitações:** Não há proteção de frescor no SQL lido; ordem final depende de concorrência.
- **Automação:** camada `local-integrado`; referência `Automação proposta; renderer/app/studio/adapters/postgres/trend_repo.py:118-131; base tests/test_trend_repo.py`

### TEN.C05 — Favorito isolado por projeto e atualizado por replay

- **Tipo:** regressao
- **Regras:** TEN.R03
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Preservar favoritos de outro canal sem tratar canal como tenant.
- **Pré-condições:** Projetos A e B em banco descartável; snapshot video_id=abcdefghijk.
- **Passos:**
  1. Salvar snapshot título Solar, views=10 em A; salvar novamente com views=20.
  2. Salvar o mesmo video_id em B; remover de A; listar favoritos de ambos.
- **Esperado:** A tem no máximo um favorito por vídeo antes da remoção; replay atualiza views e preserva created_at. Após remoção A não tem o item e B ainda o possui.
- **Limitações:** Isolamento de consulta não representa autorização entre usuários.
- **Automação:** camada `local-integrado`; referência `Automação proposta sobre renderer/app/studio/adapters/postgres/trend_repo.py:197-245`

### TEN.C06 — Ranking estável com notas válidas

- **Tipo:** feliz
- **Regras:** TEN.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Garantir ordem calculada pelo domínio e empate estável.
- **Pré-condições:** TextModel fake e usage em memória; nenhum provider real.
- **Passos:**
  1. Enviar tópicos B, A, C nessa ordem.
  2. Fake retorna todas as quatro notas de A=5, B=3 e C=3.
- **Esperado:** Ranking A, B, C; A tem score 5; B permanece antes de C no empate; todas as ideias cobertas.
- **Limitações:** Notas do fake não comprovam qualidade editorial do modelo.
- **Automação:** camada `unit`; referência `tests/test_ideas.py:74-77`

### TEN.C07 — Limite de tópicos e resposta inválida

- **Tipo:** erro
- **Regras:** TEN.R04, TEN.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar entrada e saída inválidas sem ranking parcial.
- **Pré-condições:** Modelo fake com contador; guard liberado para saída inválida.
- **Passos:**
  1. Enviar 20 tópicos distintos de 150 caracteres; depois 21 tópicos, um de 151 e duplicados após trim.
  2. Com entrada A,B válida, retornar apenas A; depois retornar nota 9 e JSON malformado.
- **Esperado:** Caso limite válido produz 20 resultados; entradas inválidas não chamam modelo. Saídas inválidas geram IdeasRejected sem ranking parcial; no caminho sem PaidOperationGuard, uso da chamada realizada permanece registrado.
- **Limitações:** PaidOperationGuard tem settlement distinto; não extrapolar contabilização do caminho legado.
- **Automação:** camada `unit`; referência `tests/test_ideas.py:80-119`

### TEN.C08 — Budget bloqueia modelo e falha não confirma gasto válido

- **Tipo:** erro
- **Regras:** TEN.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Separar recusa antes da chamada de resultado pago inválido.
- **Pré-condições:** Guard e modelo fake; ledger de teste; PaidOperationGuard no segundo caso.
- **Passos:**
  1. Configurar estimate=0.50 USD e orçamento já esgotado; pontuar A.
  2. Com reserva permitida, retornar rubric incompleta e observar estado do ledger.
- **Esperado:** Orçamento esgotado gera CostRefused com zero chamadas e zero uso novo. Saída inválida com guarda paga não confirma settlement bem-sucedido; verificar estado UNCERTAIN conforme contrato da operação paga.
- **Limitações:** Não executar cobrança nem provedor; concorrência de reservas pertence à suíte de budget.
- **Automação:** camada `mock`; referência `tests/test_ideas.py:115-119; extensão proposta para renderer/app/studio/application/ideas.py:88-94`

## Resumo do capítulo

8 cenários GC, todos A_PROJETAR e não executados. Inclui fonte e lote inválidos, fronteiras temporais, deduplicação concorrente, favoritos, ranking e orçamento; não comprova relevância editorial nem fonte live.
