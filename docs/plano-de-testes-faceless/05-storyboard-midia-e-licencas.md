# Storyboard, mídia e licenças

**Prefixo dos cenários:** `MID`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

Storyboard exige FACT_CHECKED e cenas. ProduceAssets serializa por vídeo, gera somente cenas sem vínculo e consulta cache por conteúdo/aspecto. Busca combina prompt e até duas queries extras, deduplica e ranqueia candidatos. Swap usa id estável e CAS. RenderPlan admite múltiplos shots por cena, manifesto e duração em ticks.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `MID.R01` | Transição de storyboard só a partir de FACT_CHECKED com cenas, mediante comparação do estado. | `renderer/app/studio/application/media.py:32-43` | [MID-01](#mid-01) |
| `MID.R02` | Produção trava por vídeo, pula cenas vinculadas, calcula chave por modelo/prompt/aspecto, vincula condicionada ao prompt e só avança ao fim. | `renderer/app/studio/application/media.py:60-90` | [MID-02](#mid-02), [MID-03](#mid-03), [MID-05](#mid-05) |
| `MID.R03` | Imagem gerada exige licença não branca e MIME PNG/JPEG/WebP; store precede registro; retorno preserva atribuição e URL. | `renderer/app/studio/application/media.py:92-121` | [MID-03](#mid-03), [MID-04](#mid-04) |
| `MID.R04` | Busca usa prompt sem estilo, orientação do formato e até duas queries extras, deduplica por media_id/URL e limita resultado ranqueado a per_page. | `renderer/app/studio/application/media.py:164-226` | [MID-06](#mid-06) |
| `MID.R05` | Swap aceita asset ou candidato, nunca ambos; sem escolha é no-op. Verifica licença, versão opcional e CAS do vínculo; materialização faz fetch antes de consultar cache. | `renderer/app/studio/application/media.py:255-308` | [MID-06](#mid-06), [MID-07](#mid-07), [MID-08](#mid-08) |
| `MID.R06` | Shots devem existir no manifesto; sub-tick é recusado; resíduo até max(2 ticks, 0.2 s em ticks) ajusta último shot sem deixá-lo vazio. | `renderer/app/studio/domain/render_plan_builder.py:341-400` | [MID-09](#mid-09) |
| `MID.R07` | B-roll normaliza nota e limita a 200 caracteres; preview resolve arquivo dentro da raiz e recusa fuga/ausência. | `renderer/app/studio/application/media.py:332-376` | [MID-10](#mid-10) |

## Resumo dos cenários

Total: 10 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [MID-01](#mid-01) | Preparar storyboard com estado e cenas válidos | feliz/erro | MID.R01 | `A_PROJETAR` |
| [MID-02](#mid-02) | Cache por prompt e aspecto em lote | feliz/volume/regressao | MID.R02 | `A_PROJETAR` |
| [MID-03](#mid-03) | Retomar falha parcial sem repetir cenas concluídas | erro/regressao | MID.R02, MID.R03 | `A_PROJETAR` |
| [MID-04](#mid-04) | Recusar licença vazia, MIME indevido e store inválido | erro/borda | MID.R03 | `A_PROJETAR` |
| [MID-05](#mid-05) | Duas produções e alteração concorrente de prompt | concorrencia | MID.R02 | `A_PROJETAR` |
| [MID-06](#mid-06) | Busca ranqueada, deduplicação e ausência de candidato | feliz/erro/volume | MID.R04, MID.R05 | `A_PROJETAR` |
| [MID-07](#mid-07) | Swap por id estável com replay e conflito | feliz/concorrencia/regressao | MID.R05 | `A_PROJETAR` |
| [MID-08](#mid-08) | Cache de candidato ainda exige fetch | regressao/erro | MID.R05 | `A_PROJETAR` |
| [MID-09](#mid-09) | Multishot contínuo e limites de arredondamento | feliz/borda/erro | MID.R06 | `A_PROJETAR` |
| [MID-10](#mid-10) | B-roll e preview restrito à raiz | feliz/borda/erro | MID.R07 | `A_PROJETAR` |

## Cenários

### MID-01 — Preparar storyboard com estado e cenas válidos

- **Tipo:** feliz/erro
- **Regras:** MID.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Respeitar gate editorial.
- **Pré-condições:** Vídeo sintético e repositórios dublês.
- **Dados:** FACT_CHECKED com 3 cenas; variantes SCRIPTED e lista vazia.
- **Passos:**
  1. Preparar caso válido.
  2. Repetir nas variantes e simular transition_video=false.
- **Esperado:** Somente caso válido passa a STORYBOARDED; demais levantam conflito e não produzem imagens.
- **Limitações:** Transição não avalia semântica visual.
- **Automação:** camada `mock`; referência `Existente: tests/test_media.py:139-153.`

### MID-02 — Cache por prompt e aspecto em lote

- **Tipo:** feliz/volume/regressao
- **Regras:** MID.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Distinguir número de cenas de número de gerações.
- **Pré-condições:** Modelo determinístico; 20 cenas sem vínculo; cache vazio.
- **Dados:** 20 cenas, 4 prompts distintos; repetir em outro vídeo short e depois long.
- **Passos:**
  1. Produzir primeiro short e contar chamadas/links.
  2. Produzir segundo short idêntico.
  3. Produzir long com mesmos prompts e modelo.
- **Esperado:** Primeiro gera 4 e reutiliza 16; segundo gera zero e reutiliza 20; aspecto diferente produz chaves distintas; todos os vínculos correspondem à cena.
- **Limitações:** Cache do caso de uso consulta registro, não valida arquivo físico em cada hit; não prometer recuperação de corrupção nesta camada.
- **Automação:** camada `mock`; referência `Existentes: tests/test_media.py:175-193; lote de 20 proposto.`

### MID-03 — Retomar falha parcial sem repetir cenas concluídas

- **Tipo:** erro/regressao
- **Regras:** MID.R02, MID.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Conservar progresso e licenças após falha.
- **Pré-condições:** 3 cenas com prompts diferentes; provider falha na segunda geração.
- **Dados:** c1/c2/c3; primeiro asset válido com licença CC0-1.0.
- **Passos:**
  1. Produzir até falha na segunda cena.
  2. Reexecutar com provider saudável.
  3. Comparar chamadas e vínculos antes/depois.
- **Esperado:** Falha mantém STORYBOARDED e vínculo c1; retomada gera c2/c3 e chega a ASSETS_READY; c1 não é regenerada.
- **Limitações:** Se houve cobrança ambígua, guard pago pode exigir reconciliação em vez de retry; cenário base usa provider gratuito.
- **Automação:** camada `mock`; referência `Existente: tests/test_media.py:204.`

### MID-04 — Recusar licença vazia, MIME indevido e store inválido

- **Tipo:** erro/borda
- **Regras:** MID.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não vincular saída recusada como asset válido.
- **Pré-condições:** Cena STORYBOARDED; spies de store, repository e usage.
- **Dados:** Licença '', '   ', CC0-1.0; MIME image/svg+xml; bytes que store rejeita.
- **Passos:**
  1. Gerar cada variante isoladamente.
  2. No caso válido registrar attribution='Autor sintético' e source_url=https://exemplo.org/foto.
  3. Inspecionar efeitos no store, ledger e vínculo.
- **Esperado:** Licença/MIME inválidos bloqueiam store e vínculo; rejeição pelo store impede asset; válido preserva créditos. Ledger legado registra chamada antes da recusa; guard pago pode marcar UNCERTAIN.
- **Limitações:** String de licença não comprova direitos autorais; revisão jurídica/visual é manual proposta.
- **Automação:** camada `mock`; referência `Existente: tests/test_media.py:215-231 e :310.`

### MID-05 — Duas produções e alteração concorrente de prompt

- **Tipo:** concorrencia
- **Regras:** MID.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Impedir dupla geração no mesmo vídeo e vínculo obsoleto.
- **Pré-condições:** Lock controlado por barreira e provider espião.
- **Dados:** Vídeo V, cena S com prompt A; segunda requisição de V; alteração para prompt B durante chamada.
- **Passos:**
  1. Reter lock da primeira produção e iniciar segunda.
  2. Liberar primeira após mudar prompt no repositório.
  3. Comparar contagem de geração e estado final.
- **Esperado:** Segunda recusa antes do provider; link condicionado ao prompt antigo falha e vídeo não avança.
- **Limitações:** Lock por vídeo não impede duas gerações do mesmo conteúdo em vídeos diferentes; deduplicação de asset não significa cobrança única global.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_media.py:274-296 e tests/test_asset_repo.py; barreira no banco proposta.`

### MID-06 — Busca ranqueada, deduplicação e ausência de candidato

- **Tipo:** feliz/erro/volume
- **Regras:** MID.R04, MID.R05
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Preservar mídia atual quando busca não oferece alternativa.
- **Pré-condições:** Cena vinculada; search dublê; assets de outras cenas conhecidos.
- **Dados:** Prompt oceanos; 3 queries extras; per_page=10; candidatos repetidos com media_id=42.
- **Passos:**
  1. Buscar e inspecionar chamadas e orientação.
  2. Repetir com lista vazia e chamar swap sem escolha.
  3. Simular search não configurado.
- **Esperado:** No máximo query principal e duas extras são consultadas; resultado deduplicado tem até 10 candidatos; vazio não remove asset; ausência do serviço é explícita.
- **Limitações:** Ranking não prova relevância factual; vídeo stock não deve ser descrito como registro real do evento sem revisão.
- **Automação:** camada `mock`; referência `Existentes: tests/test_media_search.py e tests/test_media_ranker.py; matriz integrada proposta.`

### MID-07 — Swap por id estável com replay e conflito

- **Tipo:** feliz/concorrencia/regressao
- **Regras:** MID.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Trocar apenas cena alvo sem sobrescrever outra edição.
- **Pré-condições:** 3 cenas; S2 ligada a A; assets B/C licenciados; roteiro v2.
- **Dados:** expected_asset_id=A; expected_version=2; swap A→B.
- **Passos:**
  1. Aplicar B e repetir B.
  2. Concorrer troca B→C com pedido esperando A.
  3. Tentar asset e candidate juntos, asset sem licença e versão 1.
- **Esperado:** Só S2 muda; repetir B retorna already-linked; expectativa antiga ou CAS perdido conflita; entradas ambíguas e licença ausente recusam.
- **Limitações:** Verificação de versão é leitura anterior ao CAS do vínculo; atomicidade conjunta com edição de roteiro é risco a investigar, não garantia afirmada.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_media_swap.py e tests/test_media_swap_api.py; interleaving com roteiro proposto.`

### MID-08 — Cache de candidato ainda exige fetch

- **Tipo:** regressao/erro
- **Regras:** MID.R05
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Caracterizar cache de asset sem prometer cache de rede.
- **Pré-condições:** Mesmo candidato já materializado e asset registrado; fetcher espião.
- **Dados:** candidate.media_id=42; URL https://exemplo.org/42.png; aspecto 9:16.
- **Passos:**
  1. Aplicar candidato uma vez e reaplicar em outra cena.
  2. Na terceira aplicação simular timeout do fetcher antes da consulta ao cache.
- **Esperado:** Segunda aplicação chama fetch novamente, mas pode reutilizar registro existente; timeout anterior ao lookup impede reaproveitamento por esse caminho.
- **Limitações:** Otimizar para consultar cache antes do download é proposta, não comportamento atual; não atribuir cobrança duplicada sem dados do provider.
- **Automação:** camada `mock`; referência `Proposto: extensão de tests/test_media_swap.py para ordem fetch/find.`

### MID-09 — Multishot contínuo e limites de arredondamento

- **Tipo:** feliz/borda/erro
- **Regras:** MID.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Preencher a cena sem lacunas, sobreposição ou referência perdida.
- **Pré-condições:** Builder puro; manifesto com A/B/C; timebase=25000.
- **Dados:** Fala 6.8 s, cena 7.6 s, shots 2+3+2.6 s; variantes sub-tick, asset ausente e soma 8 s.
- **Passos:**
  1. Construir plano e conferir início/fim de cada shot.
  2. Variar resíduo em um tick e acima de 0.2 s.
  3. Comparar shots=None e lista vazia com caminho de uma mídia.
- **Esperado:** Base shots contíguos somam duração da cena; pequeno resíduo ajusta último shot; sub-tick, manifesto incompleto e divergência excessiva recusam; fallback mantém paridade.
- **Limitações:** Contrato não demonstra FFmpeg exibindo todos os shots; validar execução em REN.
- **Automação:** camada `unit`; referência `Existente: tests/test_render_plan_builder_multishot.py:66-122, :171, :205, :421-465.`

### MID-10 — B-roll e preview restrito à raiz

- **Tipo:** feliz/borda/erro
- **Regras:** MID.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Manter edição leve e impedir leitura fora do armazenamento de teste.
- **Pré-condições:** Cena existente; raiz temporária isolada e arquivo sintético.
- **Dados:** Nota '  mar  ', notas de 200/201 caracteres; asset.path='../fora.png'.
- **Passos:**
  1. Ativar B-roll, repetir valor e testar notas limite.
  2. Solicitar preview de arquivo válido, ausente e caminho externo.
  3. Usar symlink sintético que aponta para fora da raiz temporária.
- **Esperado:** Nota normalizada; replay changed=false; 201 recusa; preview só retorna arquivo regular resolvido dentro da raiz; demais retornam ausência.
- **Limitações:** Teste futuro deve criar apenas arquivos descartáveis; não usar arquivos reais externos nem segredos.
- **Automação:** camada `local-integrado`; referência `Existentes: tests/test_scene_broll.py e tests/test_media_swap.py; matriz de symlink proposta.`

## Resumo do capítulo

10 cenários A_PROJETAR, exclusivamente documentais; execução direta sem workflow. Testes existentes indicam pontos de automação, não resultado. Integrações futuras usam banco e arquivos descartáveis; provedores são dublês.
