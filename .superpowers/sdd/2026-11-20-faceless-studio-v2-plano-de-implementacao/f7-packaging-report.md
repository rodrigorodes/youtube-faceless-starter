# F7 — contrato do pacote editorial e das variantes (F7-01/F7-02)

## Escopo

Contrato de domínio puro, imutável e versionado para o pacote de apresentação
do vídeo (título, descrição, tags, capítulos, fontes citadas e CTA) e para três
conceitos de thumbnail/título com justificativa editorial. Não há I/O, banco,
API, UI, geração de imagem, chamada ao YouTube, escolha automática nem
persistência. A entrega é composta por dois arquivos de código e este relatório:

- `renderer/app/studio/domain/packaging.py`
- `tests/test_packaging.py`
- `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/f7-packaging-report.md`

Nenhum arquivo de outra fatia foi alterado (`composition.py`, `api/`,
`adapters/`, `application/`, `beat_plan.py`, `visual_beat.py`, `insight.py`,
`channel.py`, `production_run.py`, `qa_report.py`, `budget.py`, `test_db.py`
permanecem intocados). Arquivos não rastreados ou modificados por outros
agentes no worktree não foram adicionados.

## Correções da revisão independente

| Gap apontado | Correção aplicada | Teste |
|---|---|---|
| Duplicatas NFC/NFD passavam | Comparações canônicas usam `NFKC` antes de colapsar espaços e aplicar `casefold`; tags são armazenadas em NFC. Aplicado a tags, títulos de capítulo, títulos de variante, `variant_id`, conceito de thumbnail e decisão | `test_tags_reject_nfc_nfd_duplicates_and_store_canonical_nfc`, `test_tags_reject_compatibility_variants_after_nfkc_normalization`, `test_chapter_titles_reject_nfc_nfd_duplicates`, `test_variant_ids_are_unique_after_unicode_and_case_normalization` |
| Controle aceito fora de título/descrição | `SafeText` (não vazio, sem espaços nas bordas e sem `Cc`/`Cf`/`Cs`) é usado em tags, fontes (nome e URL), CTA, título de capítulo, `variant_id`, conceito de thumbnail, justificativa, declaração de promessa, estimativa, autor da decisão e rationale | `test_control_and_format_characters_are_rejected_in_every_public_text` (19 casos) |
| Bidi/format aceito no título | `Cf` é recusado em todo texto público, incluindo U+202E (RLO), U+200C (ZWNJ) e U+200D (ZWJ), sem lista de `Cf` legítimo; emoji composto com ZWJ é recusado no título. Apenas `\n` é permitido na descrição | `test_title_rejects_bidi_override_and_format_joiners`, `test_description_accepts_multiline_but_rejects_blank_and_nul` |
| Anti-clickbait não alcançava o título publicado | `VideoPackaging.title_claim` é obrigatório: o título realmente publicado declara a natureza da promessa. O contrato não julga se é enganosa; `HumanVariantDecision` registra aceite/recusa humana, e `decisions` referencia variantes existentes | `test_published_title_carries_its_own_claim`, `test_published_title_claim_is_required`, `test_sensational_variant_is_flagged_for_human_review_until_decided` |
| `variant_id` case-sensitive; thumbnail sem unicidade; docstring de limites imprecisa; `model_copy`/`model_construct` furam `Literal[False]` | Ids e conceitos comparados por chave canônica; dois conceitos iguais são recusados (F7-02 exige três conceitos distintos); docstring de `limit_violations` corrigida; o módulo documenta que a garantia é do caminho `model_validate`/`load_versioned` e que consumidores devem revalidar | `test_variant_ids_are_unique_after_unicode_and_case_normalization`, `test_variant_thumbnail_concepts_must_be_distinct_after_normalization`, `test_limit_violations_documents_that_configured_defaults_are_used`, `test_contract_documents_that_consumers_must_revalidate` |

Sobre a recomendação adicional de exigir `decision="reject"|"edit"` antes de
publicar: este contrato não possui estado "publicável" nem fluxo de edição
(F7-04/F7-07). Ele expõe `unreviewed_sensational_variant_ids()`, que lista
variantes com `declared_sensational_claim` sem decisão humana registrada.
Transformar isso em gate de publicação e modelar `edit` continua sendo pendência
de F7-04/F7-05.

## Contrato

Todos os modelos usam `extra="forbid"` e são `frozen=True`; coleções são
`tuple`, então a imutabilidade é profunda (modelos aninhados também congelados).

| Tipo | Papel |
|---|---|
| `VideoPackaging` | pacote completo: `revision`, título, `title_claim`, descrição, tags, capítulos, fontes, CTA, variantes e decisões humanas |
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
  `CONFIGURED_MAX_TAGS` e `CONFIGURED_TOTAL_TAG_CHARS` continuam com os mesmos
  valores e são política local, documentada no módulo como não conferida contra
  a API/documentação vigente do YouTube. `VideoPackaging.limit_violations(limits)`
  usa os defaults `CONFIGURED_*` quando `limits` é omitido ou aplica o
  `PackagingLimits` explícito; não há consulta externa. A contagem é em code
  points, não em grafemas.
- **Texto público canônico.** Título, descrição, tags, fontes, CTA, capítulos,
  justificativas e nomes recusam `Cc`, `Cf` e `Cs`; apenas `\n` é permitido na
  descrição. A comparação de identidade usa NFKC (também dobra largura total,
  ligaduras e formas circuladas) + espaços colapsados + `casefold`, e as tags
  são armazenadas em NFC. Não há `Cf` legitimado, então ZWJ/ZWNJ são recusados.
- **Invariantes estruturais.** Título não vazio, sem espaço sobrando nem
  controle/formato; capítulos com primeiro em zero, timestamps estritamente
  crescentes e sem repetição de segundo nem de título; tags sem `#`, sem vazias
  e sem duplicatas canônicas; CTA obrigatório; fontes com mínimo 1.
- **Fontes são declaradas, não certificadas.** O contrato não consegue decidir
  se uma afirmação é factual nem se as fontes bastam, são legítimas ou
  acessíveis: a suficiência não é verificada aqui.
- **Anti-clickbait é declaração, não julgamento.** O título publicado e cada
  variante obrigam `TitleClaim` preenchida. `declared_sensational_claim` é
  aceita e preservada; o contrato não decide se é enganosa. A recusa humana é
  `HumanVariantDecision(decision="reject")`. Uma variante não tem campo
  `chosen`/`auto_selected`.
- **Desempenho não é fato.** Não existe campo de CTR garantido. Estimativa só
  existe como `UnverifiedPerformanceEstimate`, com rótulo fixo e
  `guarantees_performance` `Literal[False]`; campos de CTR são recusados por
  `extra="forbid"`.
- **Três variantes quando aplicável.** `variants` aceita zero ou exatamente
  três; ids, títulos e conceitos de thumbnail são únicos por comparação
  canônica.
- **Versionamento e revalidação.** `schema_version` recusa valor diferente de 1
  e `revision` é inteiro estrito positivo. `model_construct` e
  `model_copy(update=...)` **não revalidam**: podem furar `Literal[False]`, a
  regra de zero ou três variantes e as demais invariantes. A garantia é do
  caminho `model_validate`/`model_validate_json`/`load_versioned`; consumidores
  que recebem dados de fora devem revalidar antes de publicar.

## Evidências

### TDD (RED antes de GREEN)

1. Testes novos escritos antes da correção e executados contra o módulo anterior:

   `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_packaging.py`

   Resultado: **32 failed, 60 passed**, incluindo duplicatas NFC/NFD aceitas,
  `\x00`/U+202E/U+200C/U+200D aceitos em campos públicos, título publicado sem
  `title_claim`, ids `v1`/`V1` aceitos, conceitos de thumbnail repetidos,
  docstrings desatualizadas e ausência de `unreviewed_sensational_variant_ids`.

2. Após a correção:

   mesmo comando — **93 passed**.

3. Fatia + arquitetura (o teste global varre todos os imports da camada de
   domínio, incluindo o módulo novo):

   `... -m pytest -q -p no:cacheprovider tests/test_packaging.py tests/test_architecture.py`

   Resultado: **97 passed**.

### Suíte completa

Sem o `.git` externo montado (ambiente padrão desta fatia):

`docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`

Resultado: **2 failed, 1094 passed, 373 skipped, 1 warning**. As duas falhas são
`tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable`
e `...::test_extracted_starter_runs_contract_snapshot_and_backup_import`, ambas
por falta do `.git` externo necessário ao empacotamento — falha ambiental, não
mascarada.

Com o `.git` externo somente leitura:

`... -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro ...`

Resultado: **1096 passed, 373 skipped, 1 warning**, sem falhas. O aviso é a
depreciação Starlette/AnyIO já conhecida. PostgreSQL e serviços externos não
foram configurados; os testes ignorados não foram validados.

Nota de concorrência: uma execução intermediária da suíte apresentou 8 falhas em
`tests/test_budget_guard.py`/`tests/test_budget_http.py` enquanto outro agente
editava `application/budget.py`, `api/routes.py` e os próprios testes de budget.
As execuções seguintes passaram sem essas falhas e sem qualquer alteração desta
fatia nesses arquivos; as falhas não foram mascaradas nem atribuídas ao
packaging.

### Cobertura pedida

- pacote válido com todas as partes e round-trip JSON;
- título vazio, com espaços nas bordas e com controle/formato (U+202E,
  U+200C/U+200D) recusado;
- limite de título/descrição/tags aplicado por `PackagingLimits` explícito e
  defaults configurados documentados;
- tags com duplicata NFC/NFD, variante de compatibilidade NFKC, caixa, espaços,
  `#` e vazias recusadas; armazenamento canônico em NFC;
- capítulos fora de ordem, primeiro não-zero, segundo repetido e título
  duplicado (inclusive NFC/NFD) recusados; `timestamp` derivado testado;
- fontes obrigatórias, URL/nome sem controle e CTA presente;
- variante sem justificativa/título/conceito/id, quantidade diferente de zero ou
  três, ids/conceitos/títulos duplicados canonicamente recusados;
- título publicado com `title_claim` obrigatório e preservado no round-trip;
- afirmação sensacionalista declarada sem decisão humana listada por
  `unreviewed_sensational_variant_ids`; com decisão, sai da lista;
- decisões que referenciam variante inexistente ou repetem variante recusadas;
- tentativa de marcar variante como escolhida automaticamente recusada
  (`chosen`, `auto_selected` e `HumanVariantDecision(automatic=True)`);
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
  que este módulo representa mas não executa. O gate de publicação e o fluxo de
  edição (`decision="edit"`) permanecem em F7-04/F7-05/F7-07.
- `limit_violations` não conhece os limites reais vigentes da API do YouTube;
  F7-06 continua responsável por validar dimensões/formato/peso e regras da API.
- `model_construct`/`model_copy(update=...)` não revalidam; a garantia vale para
  o caminho de validação. Consumidores devem revalidar dados externos.
- Sem templates gráficos, UI de comparação, persistência da escolha ou
  integração com `publication_intent` (F7-03/F7-04/F7-05), sem experimentos de
  SEO (F7-07 além dos testes de contrato).

**F7 não está concluída.** Esta fatia entrega somente os contratos de F7-01
(pacote editorial) e F7-02 (três variantes com justificativa), sem UI, imagem,
persistência, publicação ou validação contra a API.