# qa-legacy-read — leitura tolerante do `qa_report` legado

**Fatia:** QA de regressão RP-07b (linhas legadas de `videos.qa_report`).
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/qa-legacy-read`
**Branch:** `feat/qa-legacy-read` (base `d4ec5e6`)
**Sintoma real:** `GET /studio/videos/{id}/preview` → **HTTP 500** por `pydantic_core.ValidationError`
(7 erros) na validação do `qa_report` legado com o tipo novo.

## 1. O bug, reproduzido

`repo._video` fazia `QaReport.model_validate(row["qa_report"])` com o contrato **novo**
(`render_id`/`checksum`/`generated_at`/`coverage`/`checks_run`/`findings`). A linha legada
persistida antes da unificação (RP-07b) tem o shape **antigo**:

```json
{"passed": true, "failures": [], "metrics": {"width":1080,"height":1920,...}, "schema_version": 1}
```

O teste novo `tests/test_qa_legacy_read.py` reprova no código base com o traceback exato do
relatório (antes da correção):

```
FAILED tests/test_qa_legacy_read.py::test_get_video_reads_a_legacy_row - pyda...
FAILED tests/test_qa_legacy_read.py::test_preview_returns_200_for_a_legacy_row
E  pydantic_core._pydantic_core.ValidationError: 7 validation errors for QaReport
E  render_id / checksum / generated_at / coverage  → Field required (missing)
E  passed / metrics / failures                     → Extra inputs are not permitted
renderer/app/studio/adapters/postgres/repo.py:29: ValidationError
```

A linha real no banco do app (`studio.videos`, id `b68b62d9ad994bc5b1b6d9bf7675784f`,
`AWAITING_APPROVAL`) tem exatamente esse shape — ou seja, um vídeo pronto para aprovar
estava inacessível. Depois da correção: **7 passed**.

## 2. Onde a tolerância foi aplicada

**Borda (adapter), não no domínio** — a tolerância vive só em
`renderer/app/studio/adapters/postgres/repo.py`:

- `repo.py:42` `_legacy_qa_report(payload)` — upcast puro do shape legado para o contrato novo.
- `repo.py:76` `_qa_report(payload)` — tenta o contrato novo; se falhar e o payload for o
  shape legado **na versão conhecida**, faz o upcast; senão **relança** (`raise`).
- `repo.py:96-98` `_video` — ponto de leitura: `row["qa_report"] = _qa_report(row["qa_report"])`.

Regras do upcast (sem mentir e sem perder dado):

| Regra | Implementação |
|---|---|
| Cobertura honesta | `coverage = QaCoverage(status="not_verified", reason="legacy report from before the QA unification; ...")` — nunca `verified` |
| Registra um finding | `QaFinding(finding_id="legacy-qa-report", check_id="render.legacy_report", category="technical", severity="info", ...)` |
| Não perde `metrics` | o **payload legado inteiro** (inclusive `metrics`) vira `evidence` do finding: `json.dumps(payload, sort_keys=True, ensure_ascii=True)` |
| Não inventa identidade | `render_id = checksum = "legacy"` (marcador explícito; **não** casa com o `^[0-9a-f]{32}$`/`^[0-9a-f]{64}$` que o gate da F8 exige) |
| Não inventa instante | `generated_at = datetime(1970,1,1, tzinfo=utc)` (epoch sentinela) |
| Falha alta preservada | corrupção do formato **novo** e `schema_version` desconhecida continuam `raise` |

**Domínio (correção de um desvio fail-open):** `domain/qa_report.py:554` `publishable_payload`
passou a devolver `False` para o shape legado (`qa_report.py:568`). Antes devolvia
`payload.get("passed") is True` — um legado `passed: true` era tratado como publicável, ou
seja, *alegava* QA verificado. É uma função pura (sem I/O); não reintroduz o tipo antigo — só
corrige a leitura do jsonb persistido para falhar fechado. `publish_repo.decide` a usa para
gravar `qa_passed` na intenção de publicação, então agora a intenção de um legado sai com
`qa_passed = false` (consistente com o `is_publishable` do vídeo up-castado).

## 3. Auditoria de todos os leitores (grep)

Comando:

```
grep -rn "QaReport.model_validate\|\.qa_report\|publishable_payload" renderer/app/studio
```

| Leitor | Tolera legado? | Como |
|---|---|---|
| `adapters/postgres/repo.py` `_video` | ✅ (corrigido) | upcast na leitura |
| `adapters/postgres/publish_repo.py:33,50` (`decide` → `publishable_payload`) | ✅ | `publishable_payload` fail-closed para legado |
| `adapters/postgres/render_repo.py:79` (`complete`) | n/a | só **escreve** o shape novo (`Jsonb(qa.model_dump(mode="json"))`) |
| `api/routes.py:243,1317` (`RenderStatusOut`) | ✅ | recebe `QaReport` de `GetRender` ← `video.qa_report` (já up-castado no repo) |
| `api/preview.py` (`render_preview`) | ✅ | usa `p.qa.is_publishable`/`severity_counts`/`coverage.status` do `Preview` |
| `application/publishing.py:52,263` (`Approve`, `GetPreview`) | ✅ | leem `video.qa_report` do repo |
| `application/render.py:259-261` (`GetRender`) | ✅ | devolve `video.qa_report` do repo |
| `application/production.py:306,344` (`QaHandler`, `RenderQaGate`) | ✅ | leem `video.qa_report` do repo; `RenderQaGate` reamarra `render_id`/`checksum` ao render real, mas a cobertura `not_verified` continua recusando |
| `application/publication_execution.py:156` (`_prepare`) | ✅ | `video.qa_report.is_publishable` = `False` |
| painéis (`api/panel*.py`) | n/a | nenhum lê `qa_report` (grep sem resultado) |

Não há outro `model_validate` do `qa_report` fora de `repo.py`. Nenhum leitor volta a
interpretar `passed`/`failures`/`metrics`.

## 4. Migração de dados: **não** usei `0033`

`ls renderer/app/studio/adapters/postgres/migrations` → última é `0032_render_plan_cache.sql`
(o RP-07 **reservou** `0033` mas não criou migração — confirmado por `ls`). **Decisão: sem
migração.** Motivos:

1. A normalização é **uma só**, determinística e pura, na borda (`_legacy_qa_report`). Uma
   migração SQL teria que reimplementar o mesmo upcast em SQL — **duas verdades** sobre "como
   o legado mapeia para o novo" (a migração já teria que *hardcodar* os mesmos marcadores
   `legacy`/epoch) e poderia divergir de qualquer ajuste futuro do upcast Python.
2. A leitura tolerante cobre **toda** linha legada, em qualquer ambiente (dev/stg/prod e
   backups restaurados), não só as existentes no momento do deploy.
3. A migração reescreveria jsonb de forma irreversível sem ganho: a linha continua legível e
   o app já a normaliza. Como a tolerância é read-only, **`tests/test_db.py` ficou intacto**
   (nenhuma tabela/versão nova).
4. `metrics` fica preservado de qualquer forma (na evidência do finding). Uma migração SQL
   não acrescentaria retenção — teria que embutir o mesmo blob.

A leitura tolerante basta para o objetivo (o painel voltar a abrir e não publicar sem
override) e evita a segunda fonte de verdade que o próprio design do projeto proíbe.

## 5. Como provei que um legado **não** publica alegando QA verificado

Dois níveis:

- **Unitário/domínio:** `publishable_payload(LEGACY) is False` e
  `publishable_payload({"passed": True}) is False`; `upcast(...).is_publishable is False`.
- **Execução real do gate F8** (`RunPublication._prepare` → `verify_publication_gate`), com o
  `PostgresVideoRepository` **real** lendo a linha legada do banco descartável:
  - `test_legacy_video_cannot_publish_without_override` → `PublicationResult.BLOCKED`,
    `"QA"` no `detail`, `uploads == []`, `tokens.calls == 0` (nada chega ao provedor).
  - `test_legacy_video_publishes_only_with_a_recorded_override` → `UPLOADED` quando o intent
    traz `qa_override=True` — provando que a recusa é especificamente a ausência de override,
    não um bloqueio cego.

O gate usa `render_id`/`checksum` do job/asset reais (não do `qa_report`). O que impede o
legado é a **cobertura `not_verified`** (`is_publishable=False`) combinada com a ausência de
override. O `render_id`/`checksum="legacy"` do upcast não se disfarça de identidade válida
(não casa com os regex de 32/64-hex do `publication_policy`).

## 6. Teste de regressão (o que faltava)

`tests/test_qa_legacy_read.py` (novo, 8 testes):

1. `test_upcast_marks_legacy_as_not_verified_and_preserves_everything` — upcast puro: cobertura
   `not_verified`, marcador `legacy`, métricas preservadas na evidência, não publicável.
2. `test_upcast_does_not_touch_a_valid_new_report` — relatório novo round-trips **inalterado**
   (o upcast não sequestra o formato atual).
3. `test_corrupt_new_shape_still_fails_loud` / `test_unknown_schema_version_is_not_tolerated`
   — corrupção e versão desconhecida continuam falhando alto.
4. `test_get_video_reads_a_legacy_row` — leitura no Postgres descartável; confere que a linha
   **no banco não é reescrita** (tolerância é read-only).
5. `test_preview_returns_200_for_a_legacy_row` — `GET /studio/videos/{LEGACY_ID}/preview` = **200**
   com `not_verified` no HTML (usa o id real `b68b62d9ad994bc5b1b6d9bf7675784f`).
6. `test_legacy_video_cannot_publish_without_override` / `..._only_with_a_recorded_override`.

## 7. Prova no stack real (o que fiz e o que **não** fiz)

**Não rebuildar o container.** O `renderer` em `127.0.0.1:8000` roda a imagem já construída
(código antigo); rebuildá-lo reiniciaria o app que está em uso. Optei pelas alternativas mais
leves, sem escrever no banco compartilhado:

1. **Linha real, só leitura** — conectei o código **corrigido** ao Postgres do app
   (`youtube-faceless-starter-postgres-1`, apenas `SELECT`, sem `Studio`/`_wire`, portanto sem
   `fail_interrupted`) para ler o id real:

   ```
   status: AWAITING_APPROVAL
   qa.render_id: legacy | checksum: legacy
   qa.coverage: not_verified
   qa.is_publishable: False
   metrics preserved in evidence: True
   ```

2. **HTTP 200 com a linha replicada** — banco Postgres **descartável próprio** (`qlr-pg`, com
   prova `/budget-test-proof/proof`, sem tocar o `postgres-test`/`rb-pg`/`integ-pg` de outros)
   contendo a **mesma** linha legada (mesmo id, mesmo jsonb); `TestClient` do app com o código
   corrigido: `GET /studio/videos/b68b62d9ad994bc5b1b6d9bf7675784f/preview` → **200**.

O 500 na instância atual só some com rebuild/restart do renderer, que **não** executei por
decisão de não interromper quem usa o app. A prova de código na linha real + o 200 HTTP na
linha replicada cobrem o caminho.

## 8. Validações

Ambiente: Postgres descartável próprio (`qlr-pg`, 127.0.0.1:55437) + imagem de teste `yfs-test`
(ffmpeg presente), `STUDIO_TEST_DSN` e prova `/budget-test-proof/proof`.

| Suíte | Resultado |
|---|---|
| `test_qa_legacy_read` + `test_qa_report` + `test_repo` + `test_publishing` + `test_publish_domain` + `test_publish_repo` + `test_publication_api` + `test_publication_execution` + `test_publication_policy` + `test_publication_resilience_repo` + `test_db` + `test_architecture` + `test_contracts_snapshot` | **271 passed** |
| `test_render_api` + `test_publish_api` + `test_panel_production_render` + `test_render_repo` + `test_production_handlers` + `test_production_flow_db` + `test_quality` + `test_render_quality_e2e` | **117 passed** |
| `test_panel*` + `test_editorial*` + `test_production_{api,coordinator,repo,run}` | **237 passed, 49 skipped** |
| `test_render*` (plan, compiler, domain, adapters, cache, regeneration, reuse, rollout, benchmark) | **246 passed** |
| `scripts/export_contracts.py --check` | **exit 0** (sem contrato tocado) |
| `scripts/secret_hygiene.py scan` | **Secret hygiene check passed.** (exit 0) |
| `tests/test_architecture.py` (domain/application puros) | verde |

Suíte completa em partições: não rodei a suíte inteira (VM do Docker compartilhada com fatias
em paralelo); os focados acima cobrem tudo que lê `qa_report`, o gate, os contratos e a
arquitetura.

## 9. Arquivos e commits

- `renderer/app/studio/adapters/postgres/repo.py` — upcast na leitura (`_qa_report`/`_legacy_qa_report`/`_video`).
- `renderer/app/studio/domain/qa_report.py` — `publishable_payload` fail-closed para legado.
- `tests/test_qa_legacy_read.py` — regressão (novo).
- `tests/test_qa_report.py` — asserção de compatibilidade legada passa a esperar `False`.
- `tests/test_publication_resilience_repo.py` — o teste de intent imutável usa QA válido do contrato novo.

Commits:

- `232d77a` `fix(qa): tolera qa_report legado na leitura e nega publicacao sem override`
- `b588b0d` `test(qa): regressao do qa_report legado (200 na previa e gate)`
- (este relatório) `docs(qa): relatorio da leitura tolerante do qa_report legado`

Sem `0033`; sem `DROP`; nenhum arquivo de outra fatia tocado
(`renderer/app/rich.py`, `voice_piper.py`, `.env.example`, `docker-compose.yml`,
`scripts/doctor.py`, `docs/` intactos). Sem push/merge.

## 10. Limitações declaradas

- A instância em execução na porta 8000 continua com a imagem antiga (HTTP 500 no legado) até
  um rebuild explícito do `renderer`, que **não** fiz para não interromper o app em uso.
- Um vídeo legado em `AWAITING_APPROVAL` agora mostra QA **REPROVADO** (`not_verified`); como o
  `Approve` só registra override no estado `RENDERED`, um legado em `AWAITING_APPROVAL` aprovado
  pela UI fica **bloqueado na publicação** (DLQ fail-closed) até um override humano (via
  `RENDERED`) ou um re-render com o avaliador atual. Isso é intencional: o QA antigo não é
  confiável para publicar. Não mexi na máquina de estados da aprovação (fora do escopo).
