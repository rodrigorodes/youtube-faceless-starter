# VE-00 / W0A — Fechamento do baseline (W0A.2 e W0A.3)

**Data:** 22/11/2026 · **Repo:** `/Users/rodrigomendes/youtube-faceless-starter` · **Branch/HEAD:** `main` @ `a2e6a39`
**Ambiente:** só o container (`scripts/test-container.sh`); host macOS não é ambiente de teste.
**Comando (idêntico nas duas rodadas):** `scripts/test-container.sh tests -q -rfEs`

| | Baseline (antes das correções) | Rodada atual (W0A.1 + DSN de orçamento) |
|---|---|---|
| Log | `/private/var/folders/.../opencode/ve00/full2.log` (22/11 08:48) | `/private/var/folders/.../opencode/full1.log` (22/11 10:11) |
| Resultado | **5 failed, 2888 passed, 158 skipped** · 351,09 s | **0 failed, 3045 passed, 6 skipped** · 399,36 s |
| Coletados | 3051 | 3051 |
| `hash renderer/app` (checkout = imagem) | `263674812e6c7007` | `263674812e6c7007` |
| Migrações | 36 = 36 | 36 = 36 |
| Alterações em `renderer`/`tests` no checkout | sim | sim |

As duas rodadas usaram a mesma imagem (`faceless-renderer:test` reconstruída do mesmo `renderer/`) e o mesmo Postgres efêmero (tmpfs, rede própria, prova de descartabilidade). A única diferença de ambiente é que `scripts/test-container.sh` passou a exportar também `STUDIO_BUDGET_DISPOSABLE_DSN` (o mesmo Postgres efêmero do `STUDIO_TEST_DSN`).

## Reconciliação aritmética (3051 = 3051)

- 158 skips do baseline = **152 skips de banco** (`PostgreSQL descartável de orçamento/produção não configurado`) + **6 skips de Node**. Com o DSN presente, os 152 passaram a **executar e passar**.
- 2888 passed + 152 (skips de banco que agora rodam) + 5 (falhas corrigidas) = **3045 passed**.
- 6 skips restantes = exatamente os mesmos 6 skips de Node do baseline (nenhum skip novo).

## Classificação das 5 falhas do baseline

| Teste que falhava | Causa (evidência) | Correção aplicada |
|---|---|---|
| `tests/test_contracts_snapshot.py::test_committed_contracts_match_code` | O schema comitado estava **velho em relação ao código**: falta o bloco `ConfigSnapshot` (+40 linhas) no `contracts/v1/renderplan.schema.json` | Regenerado no container por `scripts/export_contracts.py` (W0A.1) |
| `tests/test_port_contracts.py::test_every_registered_provider_satisfies_its_port` | **Dependência de ordem**: o registro global de providers ficava poluído por fakes registrados em outros módulos de teste (`test_render_api`, `test_editorial_api`) | Fixture `registered_providers` esvazia `_REGISTRY` antes do `Studio` e **restaura** no fim (W0A.1) |
| `tests/test_port_contracts.py::test_catalog_and_registry_have_no_drift` | Mesma causa | Mesma correção |
| `tests/test_publish_api.py::test_preview_page_is_escaped_locked_down_and_complete` | **Expectativa velha no teste**: o rótulo da prévia virou `"QA Aprovado"` no commit `9188d0f` e o teste esperava `"QA aprovado"` | Asserção corrigida e dividida por marcador (W0A.1) |
| `tests/test_secrets_hygiene.py::test_extracted_starter_runs_contract_snapshot_and_backup_import` | **Mesma causa raiz da primeira falha**: o teste empacota o starter e, dentro do pacote extraído, roda `tests/test_contracts_snapshot.py` (`tests/test_secrets_hygiene.py:254-266`); com o schema velho ele falha lá também | Regeneração do schema (mesma correção) — verde nas duas rodadas seguintes |

Nenhuma falha ficou "não classificada".

## Skips restantes (6) — por motivo

Todos por **Node.js ausente da imagem do renderer** (os testes JavaScript/`node` não rodam no container Python):

| Arquivo:linha | Motivo relatado |
|---|---|
| `tests/test_panel.py:522` | Node.js necessário para exercitar o filtro JavaScript |
| `tests/test_workflow_publish.py:70` | node unavailable |
| `tests/test_workflow_analytics.py:42` e `:53` | node missing |
| `tests/test_workflow_trends.py:39` e `:69` | node missing |

Observação de honestidade sobre os caminhos `../workspace/tests/...` que aparecem no resumo: são **artefato de cache de bytecode no host**. O `tests/__pycache__` do checkout contém `.pyc` compilados por uma sessão anterior dentro de um container em que o checkout estava montado em `/workspace` (o `co_filename` gravado no `.pyc` é `/workspace/tests/test_workflow_trends.py`), e o pytest do container reaproveita esse `.pyc` por estar com a mesma versão (Python 3.12 / pytest 8.3.5). Os testes coletados são os mesmos `tests/...`; só o caminho exibido vem do cache.

## O que esta rodada NÃO prova

- Nada sobre o host macOS (o produto roda em Docker, com `ffmpeg` e fonte DejaVu; no host faltam ambos).
- Nada sobre W0B (orçamento, destino de publicação, snapshot, rótulos): essas mudanças têm teste próprio e relato próprio.
- Os 6 skips de Node continuam **sem execução**: exigiriam imagem com Node (fora do escopo desta onda).

## Reprodução

```bash
cd /Users/rodrigomendes/youtube-faceless-starter
scripts/test-container.sh tests -q -rfEs      # cabeçalho traz HEAD, hash renderer/app e nº de migrações
```
