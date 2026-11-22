# VE-01 — Render Overlay — evidência de fechamento

**Data:** 22/11/2026 · **Repo:** `/Users/rodrigomendes/youtube-faceless-starter`
**Branch/HEAD:** `main` / `a2e6a39`
**Ambiente:** somente container (`scripts/test-container.sh`); o host não é ambiente de teste.

> **Estado do workspace:** o checkout recebeu mudanças concorrentes durante a execução
> (hashes de `renderer/app` observados: `43489eedf465e75f`, `4cfb884a54fcd281`,
> `9514aa164cd3fce5`, `705a926abc228ad3`; migrações 37/38). As mudanças W1 existentes
> não foram revertidas nem commitadas. Esta evidência separa o que foi validado para
> VE-01 do que ficou instável por causa dessas mudanças.

## A0 — snapshot defasado

Comando:

```bash
scripts/test-container.sh tests/test_contracts_snapshot.py tests/test_secrets_hygiene.py
```

Resultado: **35 passed**. O diff do snapshot ficou limitado a `ConfigSnapshot` em
`contracts/v1/renderplan.schema.json`.

## A1–A7 — testes da fase

Comandos (todos no container):

```bash
scripts/test-container.sh tests/test_render_plan_timeline.py tests/test_render_plan.py \
  tests/test_render_plan_builder.py tests/test_render_compiler.py \
  tests/test_render_plan_repo.py tests/test_render_cache.py \
  tests/test_render_regeneration.py tests/test_render_plan_executor.py \
  tests/test_render_adapters.py -q
```

Resultados reais:

| Rodada | Resultado |
|---|---|
| A7 (`test_render_plan_executor.py` + `test_render_adapters.py`) | **47 passed** |
| Alvo VE-01 (15 arquivos, incluindo T01–T27) | **319 passed** |
| Reexecução após mudanças concorrentes | **320 passed, 1 failed** (T26 — snapshot de contrato) |

## A8 — T23/T24 (somente teste)

```bash
scripts/test-container.sh tests/test_asset_resolver.py tests/test_quality.py -q
```

Resultado: **67 passed**. Nenhuma alteração de produção foi necessária.

## A9 — contrato novo

```bash
docker run --rm -v "$PWD:/w" -w /w --entrypoint python faceless-renderer:test scripts/export_contracts.py
scripts/test-container.sh tests/test_contracts_snapshot.py -q
```

Resultado: **3 passed** no momento da regeneração. O diff de
`contracts/v1/renderplan.schema.json` contém `ConfigSnapshot` (A0) e `role`/`z_index` (A9).

## A10 — gate e suíte completa

```bash
scripts/test-container.sh tests/test_architecture.py tests/test_render_golden.py -q
```

Resultado: **55 passed**.

Suíte completa:

```bash
scripts/test-container.sh tests -q -rfEs
```

| Rodada | Resultado | Observação |
|---|---|---|
| Melhor rodada (`/tmp/ve01-full4.log`) | **1 failed, 3137 passed, 6 skipped** | falha `test_tts_calibration.py` (flaky; passou isolada) |
| Rodada com PGs residuais (`/tmp/ve01-full3.log`) | 17 failed, 3115 passed, 6 skipped | ffmpeg/PG mortos por pressão de memória |
| Rodada com PG morto (`/tmp/ve01-full5.log`) | 7 failed, 3091 passed, 60 errors | erros de conexão ao PG efêmero |

A suíte completa não fechou limpa em uma única execução no estado atual do host. As
rodadas por blocos (A/B/C) passaram: **531 + 514 + 665 = 1710 passed** antes do bloco D.
O bloco D (produção/publicação) falhou por PG efêmero morto (`Name or service not known`),
não por asserção de código.

## Matriz T01–T28

| ID | Arquivo | Status |
|---|---|---|
| T01–T08 | `test_render_plan_timeline.py`, `test_render_plan.py` | **pass** |
| T09–T16 | `test_render_compiler.py` (T09 sem edição) | **pass** |
| T17–T18 | `test_render_plan_builder.py` | **pass** |
| T19–T20 | `test_render_cache.py`, `test_render_regeneration.py` | **pass** |
| T21 | `test_render_plan_executor.py` | **pass** |
| T22 | `test_render_adapters.py` | **pass** |
| T23 | `test_asset_resolver.py` | **pass** |
| T24 | `test_quality.py` | **pass** |
| T25 | `test_architecture.py` | **pass** |
| T26 | `test_contracts_snapshot.py` | **fail** no estado atual: snapshot de contrato defasado por mudanças concorrentes (estado `APPROVED --> PUBLISHED` no diagrama) |
| T27 | `test_render_golden.py` | **pass** |
| T28 | suíte completa | **parcial**: melhor rodada 1 failed (TTS flaky); rodadas posteriores instáveis por memória/PG |

**Contagem:** 26 de 28 casos T passam; T26 falha; T28 não fechou limpo.

## `git diff --stat` (arquivos VE-01)

```
 contracts/v1/renderplan.schema.json                |  57 ++++++-
 renderer/app/studio/adapters/render_plan_ffmpeg.py |  36 +++-
 renderer/app/studio/application/ports.py           |  74 +++++++-
 renderer/app/studio/application/render_compiler.py | 126 +++++++++++--
 renderer/app/studio/domain/render_cache.py         |  30 +++-
 renderer/app/studio/domain/render_plan.py          |  62 ++++++-
 renderer/app/studio/domain/render_plan_builder.py  | 128 +++++++++++-
 tests/test_asset_resolver.py                       |  33 ++++
 tests/test_quality.py                              |  25 ++-
 tests/test_render_adapters.py                      |  41 +++++
 tests/test_render_cache.py                         |  80 +++++++++
 tests/test_render_compiler.py                      | 190 ++++++++++++++++++++-
 tests/test_render_plan.py                          |  61 +++++++
 tests/test_render_plan_builder.py                  |  50 ++++++
 tests/test_render_plan_executor.py                 |  52 ++++++
 tests/test_render_plan_repo.py                     |  29 +++-
 tests/test_render_plan_timeline.py                 | 124 ++++++++++++++
 tests/test_render_regeneration.py                  |  36 ++++
 18 files changed, 1207 insertions(+), 27 deletions(-)
```

O checkout completo tem 64 arquivos alterados (2404 inserções) por causa das mudanças W1
concorrentes; nenhuma delas foi revertida ou commitada.

## Achados e desvios

1. **Mudanças concorrentes no checkout.** O hash de `renderer/app` mudou durante a
   execução e as migrações passaram de 36 para 37/38. O snapshot de contrato ficou
   defasado (T26). A regeneração exigiria editar `docs/10-arquitetura.md` e outros
   contratos fora dos arquivos permitidos da VE-01; não foi feita.
2. **Pressão de memória do host.** Containers PostgreSQL efêmeros de execuções
   interrompidas ficaram vivos e consumiram ~2–5 GB; isso matou ffmpeg e o PG de rodadas
   seguintes. Foram removidos manualmente. A suíte completa é instável nesse ambiente.
3. **TTS calibration flaky.** `test_tts_calibration.py` falhou na rodada completa e passou
   isolada (58 s). Não toca o código da VE-01.
4. **T26 no estado atual.** O teste de contrato falha por mudança de estados concorrente
   (`APPROVED --> PUBLISHED`), não por `role`/`z_index`.
5. **Limpeza do script.** `scripts/test-container.sh` deixou o PG efêmero vivo em algumas
   execuções; removido manualmente. Não é arquivo da VE-01.

## O que não foi concluído

- Suíte completa limpa em uma única execução no estado atual (bloqueada por memória/PG e
  por mudanças concorrentes).
- Atualização do `PLAN.md` (A11) — não estava na lista de arquivos permitidos; a evidência
  foi registrada neste arquivo.

## Atualização pós-integração (sessão 3, 22/11/2026)

- **T26 resolvido:** o snapshot de contrato foi regenerado no checkout principal com
  `scripts/export_contracts.py` (container) depois da W4.2 (nova transição
  `APPROVED --> SCRIPTED`). `tests/test_contracts_snapshot.py` → **3 passed**.
- A regeneração tocou `contracts/v1/renderplan.schema.json` e `docs/10-arquitetura.md`;
  `role`/`z_index` da VE-01 seguem no contrato.
- O restante do relatório acima continua válido; a suíte completa limpa segue pendente
  (S8/W4.1 ainda em execução).
