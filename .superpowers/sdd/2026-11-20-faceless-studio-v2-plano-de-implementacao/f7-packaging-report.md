# F7 — contrato do pacote editorial e das variantes (F7-01/F7-02)

## Escopo

Contrato de domínio puro, imutável e versionado para o pacote de apresentação
do vídeo (título, descrição, tags, capítulos, fontes citadas e CTA) e para três
conceitos de thumbnail/título com justificativa editorial. Não há I/O, banco,
API, UI, geração de imagem, chamada ao YouTube, escolha automática nem
persistência. A entrega é composta por:

- `renderer/app/studio/domain/packaging.py`
- `tests/test_packaging.py`
- `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/f7-packaging-report.md`

Nenhum arquivo de outra fatia foi alterado (`composition.py`, `api/`,
`adapters/`, `application/`, `beat_plan.py`, `visual_beat.py`, `insight.py`,
`channel.py`, `production_run.py`, `qa_report.py`, `budget.py`, `test_db.py`
permanecem intocados). Arquivos de outros agentes no worktree não foram
adicionados.

## Correções aplicadas (revisão → reverificação)

### Rodada 1 (gaps iniciais)

| Gap | Correção |
|---|---|
| Duplicatas NFC/NFD | Chave canônica com NFKC + espaços + `casefold`; tags armazenadas em NFC |
| Controle fora de título/descrição | `IdentityText`/`DisplayText` em tags, fontes, CTA, capítulos, rationale, ids e nomes |
| Bidi no título | U+202E, U+200E/U+200F, U+2066–U+2069 e BOM recusados |
| Anti-clickbait não alcançava o título publicado | `VideoPackaging.title_claim` obrigatório; `decisions` + `unreviewed_sensational_variant_ids()` |
| Menores | id canônico para duplicidade; conceito de thumbnail único; docstring de limites corrigida; aviso de `model_construct`/`model_copy` |

### Rodada 2 (defeito funcional e spoofing — esta entrega)

| Gap | Correção | Teste |
|---|---|---|
| Emoji composto (`👨‍👩‍👧`, `👩‍💻`, bandeira) recusado como falso positivo | Regra explícita de **exibição x identidade**: ZWJ (U+200D) é aceito em texto de exibição e proibido em identidade. A bandeira é aceita porque a sequência de *tag characters* (U+E0020–U+E007F) passa somente logo após U+1F3F4; nenhum controle bidi entra nessa heurística, então não há caminho para RLO. Demais `Cf` (bidi, BOM) continuam proibidos em todos os campos | `test_composed_emoji_is_accepted_in_display_text`, `test_emoji_tag_characters_are_only_accepted_after_a_flag_base`, `test_control_and_format_characters_are_rejected_in_every_public_text` |
| Separadores de linha Zl/Zp aceitos | U+2028/U+2029 (e qualquer `Zl`/`Zp`) recusados em todos os campos, inclusive descrição; quebra de linha só existe como `\n` na descrição | `test_line_and_paragraph_separators_are_rejected_everywhere` (14 casos) |
| Docstring incorreto | Docstring reescrita para o escopo real: exibição vs identidade, ZWJ/tag characters, Zl/Zp, NFKC, schema 2 | `test_contract_documents_the_zwj_display_identity_asymmetry` |
| `variant_id` de decisão inconsistente | Casar **exato**: a decisão precisa do `variant_id` idêntico ao armazenado (canônico só para duplicidade); recusa `V1` e `ｖ１` | `test_decisions_must_use_the_exact_stored_variant_id` |
| `schema_version` indistinguível | `VideoPackaging.schema_version = 2` (`PACKAGING_SCHEMA_VERSION`), já que `title_claim` passou a ser obrigatório; `1`, `0`, `3`, `99` recusados; ausente assume 2 e um payload v1 sem `title_claim` é recusado | `test_package_schema_version_is_two_because_title_claim_became_required`, `test_unknown_schema_version_is_rejected`, `test_absent_schema_version_defaults_to_two_and_old_payloads_are_rejected` |

## Contrato

Todos os modelos usam `extra="forbid"` e são `frozen=True`; coleções são
`tuple`, então a imutabilidade é profunda (modelos aninhados também congelados).

| Tipo | Papel |
|---|---|
| `VideoPackaging` | pacote completo: `schema_version=2`, `revision`, título, `title_claim`, descrição, tags, capítulos, fontes, CTA, variantes e decisões |
| `PackagingVariant` | conceito de thumbnail/título com `variant_id`, justificativa e declaração de promessa |
| `TitleClaim` | declaração explícita: `verifiable_promise`, `declared_sensational_claim` ou `no_claim` |
| `UnverifiedPerformanceEstimate` | estimativa rotulada `unverified_estimate`, com `guarantees_performance=False` |
| `HumanVariantDecision` | aceite ou recusa por revisor identificado, com `automatic=False` e `variant_id` exato |
| `Chapter` | `start_seconds` inteiro e `timestamp` derivado |
| `SourceCitation` | fonte declarada (nome e URL opcional) |
| `PackagingLimits` | limites passados explicitamente, não verdade da API |

### Classificação de texto

- **Exibição** (`DisplayText`/`TitleText`): título, descrição, CTA, título de
  capítulo, título e justificativa de variante, rationale de decisão, prosa de
  `TitleClaim` e de estimativa. Aceitam ZWJ e a sequência de tag characters da
  bandeira.
- **Identidade** (`IdentityText`): tags, `variant_id`, `thumbnail_concept`,
  nome/URL de fonte e `decided_by`. Recusam ZWJ e tag characters.
- Em ambos: `Cc`, `Cs`, `Zl`, `Zp` e os demais `Cf` (bidi, BOM) são recusados.

### Decisões de fronteira

- **Limites configurados, não verificados.** `CONFIGURED_*` mantêm os mesmos
  valores e são política local, não conferida contra a API/documentação vigente
  do YouTube. `limit_violations` usa os defaults ou o `PackagingLimits`
  explícito, sem consulta externa; contagem em code points.
- **NFKC é trade-off declarado.** `Ⅻ`/`XII`, `①`/`1` e `ﬁm`/`fim` contam como
  duplicados: conservador para tags, falso positivo para títulos de
  capítulo/variante. A cobertura de compatibilidade é de um único teste.
- **Fontes são declaradas, não certificadas.** Mínimo 1 fonte; suficiência,
  legitimidade e acessibilidade não são verificadas.
- **Anti-clickbait é declaração, não julgamento.** Título publicado e cada
  variante obrigam `TitleClaim`. `declared_sensational_claim` é aceita e
  preservada; o contrato não decide se é enganosa. Decisão humana é registrada
  em `HumanVariantDecision`; `unreviewed_sensational_variant_ids()` lista o que
  ainda não passou por revisão. Gate de publicação e edição (`edit`) são
  pendência de F7-04/F7-05/F7-07.
- **Desempenho não é fato.** Sem CTR garantido; estimativa só como
  `UnverifiedPerformanceEstimate` com rótulo fixo e `guarantees_performance`
  `Literal[False]`.
- **Três variantes quando aplicável.** Zero ou exatamente três; ids, títulos e
  conceitos únicos por chave canônica.
- **Schema 2 e revalidação.** O validador global de `contracts` continua schema
  1 para outras entidades e não é o loader do pacote. Carregue com
  `VideoPackaging.model_validate`/`model_validate_json`; `model_construct` e
  `model_copy(update=...)` não revalidam e podem furar `Literal[False]`, a regra
  de zero ou três variantes e o schema 2.

## Evidências

### TDD (RED antes de GREEN)

1. Testes novos escritos antes da correção e executados contra o módulo da
   rodada anterior:

   `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_packaging.py`

   Resultado medido: **23 failed, 97 passed**, com as falhas pela regra que cada
   teste pretendia provar: emoji composto aceito na exibição (3), Zl/Zp recusado
   (14), `variant_id` exato na decisão (1), `schema_version = 2` (2), docstring
   de exibição/identidade (1) e o round-trip com schema 2 (1) e ausência de
   versão (1).

   Correção do registro anterior: o número "32 failed, 60 passed" era um estado
   intermediário da rodada 1, em que o helper de teste já enviava `title_claim`
   contra um módulo que ainda não tinha o campo; aquelas falhas vinham do
   `extra="forbid"`, não da regra pretendida. Nesta rodada o helper e o módulo
   já têm `title_claim`, então cada falha acima ocorre pela regra que o teste
   cobre.

2. Após a correção:

   `tests/test_packaging.py` — **120 passed**.

3. Fatia + arquitetura:

   `... -m pytest -q -p no:cacheprovider tests/test_packaging.py tests/test_architecture.py`

   Resultado: **124 passed**.

### Suíte completa

Sem o `.git` externo montado (ambiente padrão desta fatia):

`docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`

Resultado: **2 failed, 1169 passed, 373 skipped, 1 warning**. As duas falhas são
`tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable`
e `...::test_extracted_starter_runs_contract_snapshot_and_backup_import`, ambas
por falta do `.git` externo necessário ao empacotamento — falha ambiental, não
mascarada.

Com o `.git` externo somente leitura:

`... -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro ...`

Resultado: **1171 passed, 373 skipped, 1 warning**, sem falhas. O aviso é a
depreciação Starlette/AnyIO já conhecida. PostgreSQL e serviços externos não
foram configurados; os testes ignorados não foram validados.

Nota de concorrência: durante a sessão, execuções intermediárias mostraram
falhas transitórias em `tests/test_budget_guard.py`/`tests/test_budget_http.py`
e em `tests/test_qa_report.py` enquanto outros agentes editavam
`application/budget.py`, `api/routes.py`, `domain/qa_report.py` e os próprios
testes. As execuções seguintes passaram sem essas falhas, `test_qa_report.py`
passa isolado e esta fatia não tocou nesses arquivos.

### Cobertura pedida

- pacote válido com todas as partes e round-trip JSON com schema 2;
- emoji composto (`👨‍👩‍👧`, `👩‍💻`, 🏴󠁧󠁢󠁥󠁮󠁧󠁿) aceito em
  título, descrição, CTA, capítulo, título e justificativa de variante; ZWJ e
  tag characters recusados em tag, `variant_id`, `thumbnail_concept`, fontes,
  URL e `decided_by`; tag character solto recusado; RLO/bidi/BOM recusados;
- U+2028/U+2029 recusados em título, descrição, CTA, capítulo, tag, título de
  variante e rationale;
- título vazio, com espaços nas bordas e com controle recusado; limite por
  `PackagingLimits` explícito e defaults configurados;
- tags com duplicata NFC/NFD e NFKC de compatibilidade, caixa, espaços, `#` e
  vazias recusadas; armazenamento canônico em NFC;
- capítulos fora de ordem, primeiro não-zero, segundo repetido e título
  duplicado (inclusive NFC/NFD) recusados; `timestamp` derivado testado;
- fontes obrigatórias, nome/URL sem controle e CTA presente;
- variante sem justificativa/título/conceito/id, quantidade diferente de zero ou
  três, ids/conceitos/títulos duplicados canonicamente recusados;
- título publicado com `title_claim` obrigatório e preservado no round-trip;
- decisão que referencia variante inexistente, repetida ou com forma não
  idêntica (`V1`, `ｖ１`) recusada; afirmação sensacionalista sem decisão listada
  por `unreviewed_sensational_variant_ids`;
- tentativa de marcar variante como escolhida automaticamente recusada;
- estimativa explicitamente não verificada; `guarantees_performance=True`,
  rótulo "guaranteed" e campos de CTR recusados;
- imutabilidade profunda; versões desconhecidas recusadas; arquitetura sem
  imports de I/O ou de camadas externas.

## Riscos e limites

- O contrato não verifica se as fontes existem, são acessíveis ou bastam.
- Não há julgamento semântico de clickbait; o gate de publicação e o fluxo de
  edição (`decision="edit"`) permanecem em F7-04/F7-05/F7-07.
- NFKC é conservador e tem falso positivo para títulos de capítulo/variante; a
  cobertura de compatibilidade é de um único teste.
- A aceitação de ZWJ e da sequência de tag characters na exibição permite
  caracteres invisíveis ali, aceitos para emoji; a heurística de bandeira exige
  U+1F3F4 e não abre caminho para bidi, mas é uma heurística.
- `limit_violations` não conhece os limites reais vigentes da API do YouTube;
  F7-06 continua responsável por validar dimensões/formato/peso.
- `model_construct`/`model_copy(update=...)` não revalidam; consumidores devem
  revalidar pelo caminho de validação.
- Sem templates gráficos, UI, persistência da escolha ou integração com
  `publication_intent` (F7-03/F7-04/F7-05).

**F7 não está concluída.** Esta fatia entrega somente os contratos de F7-01
(pacote editorial) e F7-02 (três variantes com justificativa), sem UI, imagem,
persistência, publicação ou validação contra a API.