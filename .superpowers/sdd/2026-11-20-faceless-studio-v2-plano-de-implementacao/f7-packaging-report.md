# F7 — fatias de contrato do pacote editorial e das variantes (F7-01/F7-02)

## Escopo

Contrato de domínio puro, imutável e versionado para o pacote de apresentação
do vídeo (título, descrição, tags, capítulos, fontes citadas e CTA) e para três
conceitos de thumbnail/título com justificativa editorial. Não há I/O, banco,
API, UI, geração de imagem, chamada ao YouTube, escolha automática nem
persistência. A entrega é composta por dois arquivos próprios:

- `renderer/app/studio/domain/packaging.py`
- `tests/test_packaging.py`

Nenhum arquivo de outra fatia foi alterado (`composition.py`, `api/`,
`adapters/`, `application/`, `beat_plan.py`, `visual_beat.py`, `insight.py`,
`channel.py`, `production_run.py`, `budget.py`, `test_db.py` permanecem
intocados). Arquivos não rastreados de outros agentes no worktree não foram
adicionados.

## Contrato

Todos os modelos usam `extra="forbid"` e são `frozen=True`; coleções são
`tuple`, então a imutabilidade é profunda (modelos aninhados também congelados).

| Tipo | Papel |
|---|---|
| `VideoPackaging` | pacote completo: `revision`, título, descrição, tags, capítulos, fontes, CTA e variantes |
| `PackagingVariant` | conceito de thumbnail/título com `variant_id`, justificativa e declaração de promessa |
| `TitleClaim` | declaração explícita: `verifiable_promise`, `declared_sensational_claim` ou `no_claim` |
| `UnverifiedPerformanceEstimate` | estimativa rotulada `unverified_estimate`, com `guarantees_performance=False` |
| `HumanVariantDecision` | aceite ou recusa por revisor identificado, com `automatic=False` |
| `Chapter` | `start_seconds` inteiro e `timestamp` derivado |
| `SourceCitation` | fonte declarada (nome e URL opcional) |
| `PackagingLimits` | limites passados explicitamente, não verdade da API |

### Decisões de fronteira

- **Limites configurados, não verificados.** `CONFIGURED_TITLE_MAX_CHARS`,
  `CONFIGURED_DESCRIPTION_MAX_CHARS`, `CONFIGURED_TAG_MAX_CHARS`,
  `CONFIGURED_MAX_TAGS` e `CONFIGURED_TOTAL_TAG_CHARS` são política local,
  documentada no módulo como não conferida contra a API/documentação vigente do
  YouTube. `VideoPackaging.limit_violations(limits)` devolve violações apenas
  quando o chamador passa `PackagingLimits` (ou usa os defaults configurados);
  não há consulta externa. A contagem é em code points, não em grafemas.
- **Invariantes estruturais sempre aplicadas.** Título não vazio, sem espaço
  sobrando nem caractere de controle (quebra de linha/tabulação incluídas);
  descrição não vazia, aceitando `\n`; capítulos com primeiro em zero e
  timestamps estritamente crescentes, sem repetição de segundo nem de título
  (comparação sem caixa/espaços extras); tags canônicas, sem `#`, sem vazias e
  sem duplicatas após normalização; CTA obrigatório.
- **Fontes são declaradas, não certificadas.** `sources` tem mínimo 1 porque
  toda afirmação factual exige fonte. O contrato não consegue decidir se uma
  afirmação é factual nem se as fontes bastam, são legítimas ou acessíveis: a
  suficiência não é verificada aqui.
- **Anti-clickbait é declaração, não julgamento.** Cada variante obriga uma
  `TitleClaim` preenchida. O contrato aceita `declared_sensational_claim`
  (preservando a afirmação) e não decide se ela é enganosa; a recusa é
  representável em `HumanVariantDecision(decision="reject")`, com autor humano e
  instante com fuso. Não há campo `chosen`/`auto_selected` na variante.
- **Desempenho não é fato.** Não existe campo de CTR garantido. Estimativa só
  existe como `UnverifiedPerformanceEstimate`, com rótulo fixo e
  `guarantees_performance` `Literal[False]`; campos como `guaranteed_ctr` ou
  `ctr` são recusados por `extra="forbid"`.
- **Três variantes quando aplicável.** `variants` aceita zero (conceitos ainda
  não gerados) ou exatamente três; ids e títulos das variantes são únicos.
- **Versionamento.** `schema_version` usa o validador do projeto (recusa valor
  diferente de 1) e `revision` é inteiro estrito positivo, distinto da versão de
  schema, para a revisão editorial do conteúdo.

## Evidências

### TDD (RED antes de GREEN)

1. Teste criado antes do módulo e executado contra o módulo inexistente:

   `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_packaging.py`

   Resultado: erro de coleta
   `ImportError: cannot import name 'packaging' from 'app.studio.domain'`.

2. Após implementar o módulo:

   mesmo comando — **60 passed**.

3. Fatia + arquitetura (o teste global varre todos os imports da camada de
   domínio, incluindo o módulo novo):

   `... -m pytest -q -p no:cacheprovider tests/test_packaging.py tests/test_architecture.py`

   Resultado: **64 passed**.

### Suíte completa

`docker run --rm --network none -v "$PWD:/workspace:ro" -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`

Resultado: **1001 passed, 359 skipped, 1 warning**, sem falhas. O aviso é a
depreciação Starlette/AnyIO já conhecida. A montagem somente leitura do `.git`
externo é necessária para os testes de empacotamento, como nas fatias
anteriores. PostgreSQL e serviços externos não foram configurados; os testes
ignorados não foram validados. Nenhuma falha de outra fatia apareceu nesta
execução.

### Cobertura pedida

- pacote válido com todas as partes e round-trip JSON;
- título vazio, com espaços nas bordas e com controle/quebra recusado;
- limite de título/descrição/tags aplicado por `PackagingLimits` explícito;
- tags com duplicata normalizada (caixa e espaços), `#` e vazias recusadas;
- capítulos fora de ordem, primeiro não-zero, segundo repetido e título
  duplicado recusados; `timestamp` derivado testado;
- fontes obrigatórias e CTA presente;
- variante sem justificativa/título/conceito/id e variantes em quantidade
  diferente de zero ou três recusadas; ids e títulos duplicados recusados;
- tentativa de marcar variante como escolhida automaticamente recusada
  (`chosen`, `auto_selected` e `HumanVariantDecision(automatic=True)`);
- declaração de promessa verificável, afirmação sensacionalista declarada e
  ausência de promessa, sem julgamento de engano pelo contrato;
- estimativa explicitamente não verificada; `guarantees_performance=True`,
  rótulo "guaranteed" e campos de CTR recusados;
- imutabilidade profunda (atribuição em pacote, capítulo e variante);
- versão de schema desconhecida e `load_versioned` sem versão recusados;
- arquitetura: `packaging.py` sem imports de I/O ou de camadas externas.

## Riscos e limites

- O contrato não verifica se as fontes existem, são acessíveis ou bastam; a
  declaração é o máximo que o domínio puro pode exigir.
- Não há julgamento semântico de clickbait. Uma afirmação declarada como
  sensacionalista é aceita pelo contrato; rejeitá-la depende de revisão humana,
  que este módulo representa mas não executa.
- `limit_violations` não conhece os limites reais vigentes da API do YouTube;
  F7-06 continua responsável por validar dimensões/formato/peso e regras da API.
- Sem templates gráficos, UI de comparação, persistência da escolha ou
  integração com `publication_intent` (F7-03/F7-04/F7-05), sem experimentos de
  SEO (F7-07 além dos testes de contrato).

**F7 não está concluída.** Esta fatia entrega somente os contratos de F7-01
(pacote editorial) e F7-02 (três variantes com justificativa), sem UI, imagem,
persistência, publicação ou validação contra a API.