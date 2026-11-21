# RP-07b — QA único: o loop persiste o relatório novo e o gate usa o mesmo relatório

**Fatia:** fecha o gap declarado da RP-07 (o `QualityEvaluator` existia, provado E2E, mas o
loop ainda produzia/persistia o `contracts.QaReport` legado). Decisão do usuário: **manter a
versão nova, com o padrão novo, e remover o obsoleto**.
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/rp-07b-qa-unify`
· **Branch:** `feat/rp-07b-qa-unify` · **Base:** `7fdb607`.
**Restrições:** não toquei em `api/*.py` além do mínimo (tipo do `RenderStatusOut` e prévia),
nem em `renderer/app/rich.py`, `renderer/app/main.py`, `docs/`, `tests/test_providers.py`.
Sem `git add -A` (caminhos exatos), sem push, sem merge.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `ed406a3` | **Domínio: contrato único de QA** | `domain/schema.py` (novo), `domain/contracts.py`, `domain/qa_report.py`, `domain/render.py`, `domain/policy.py`, `contracts/v1/qareport.schema.json`, `contracts/v1/video.schema.json`, `scripts/export_contracts.py` |
| `71ef0a7` | **Loop persiste o QA novo; leitores migrados** | `application/ports.py`, `application/render.py`, `application/quality.py`, `application/production.py`, `application/publishing.py`, `application/publication_execution.py`, `adapters/render_plan_ffmpeg.py`, `adapters/render_disabled.py`, `adapters/postgres/{repo,render_repo,publish_repo}.py`, `api/preview.py`, `api/routes.py`, `composition.py` |
| `4f0ef4a` | **Testes adotam o contrato e provam o gate** | `tests/test_render.py`, `test_render_api.py`, `test_render_reuse.py`, `test_budget_guard.py`, `test_publication_execution.py`, `test_production_handlers.py`, `test_publishing.py`, `test_render_repo.py`, `test_publish_repo.py`, `test_contracts.py`, `test_qa_report.py` |
| `…` | **Relatório** (este arquivo, `git add -f`) | `.superpowers/sdd/…/rp-07b-qa-unify-report.md` |

## 1. O loop passa a produzir e persistir o QA novo (sem perder check)

`RunRender` deixa de medir com `self.analyzer`/`evaluate_qa` e passa a chamar a porta
`QualityEvaluator` (a instância montada em `composition.py`):

- **Plano + descriptors vêm do renderer** pelo método novo `Renderer.qa_inputs(spec)`
  (`RenderQaInputs`, `application/ports.py`). O renderer é o único ponto que lê os assets; o
  núcleo (`domain`/`application`) continua sem I/O de mídia (`test_architecture` verde).
- **Identidade real do render:** `render_id=job.id` e `checksum=cache_key` do asset de saída
  — **exatamente** a identidade que a F8 reutiliza no `PublicationIntent`
  (`render_repo.latest_output` → `o.cache_key`). A chave passou a ser calculada **antes** do QA.
- **Nenhum check perdido:** a política pura do QA (`domain/quality.py`) reusa o próprio
  `domain/render.evaluate_qa` (agora devolvendo o DTO `MediaQaResult`, não o contrato) e traduz
  cada falha em um `QaFinding` com `check_id`/severidade. `test_quality.py` prova que nenhuma
  mensagem do `evaluate_qa` cai fora da tabela.

**Bug de fiação corrigido de passagem:** `composition.py` montava
`FfmpegQualityEvaluator(self._analyzer)` — passando o `FfmpegQa` no lugar do **probe**, o que
quebraria `measure()`. Agora monta `FfmpegQualityEvaluator(FfmpegQualityProbe(self._analyzer))`.

## 2. Leitores migrados para o tipo novo (o antigo não é mais lido)

| Leitor | Antes | Agora |
|---|---|---|
| `adapters/postgres/repo.py::_video` | `contracts.QaReport.model_validate` | `domain.qa_report.QaReport.model_validate` |
| `adapters/postgres/render_repo.py::complete` | `AWAITING_APPROVAL if qa.passed` | `… if qa.is_publishable`; grava o `model_dump(mode="json")` novo |
| `adapters/postgres/publish_repo.py::decide` | `qa.get("passed") is True` | `publishable_payload(qa)` (shape novo via `is_publishable`; **compat** com linha legada `{passed,…}` gravada antes da adoção) |
| `application/publication_execution.py::_prepare` | `video.qa_report.passed` | `video.qa_report.is_publishable` no `verify_publication_gate` |
| `application/publishing.py::Approve` | `qa_report.failures` (mensagem) | `blocking_evidence(qa_report)` (evidência textual dos achados bloqueantes) |
| `application/production.py::QaHandler` / `RenderQaGate` | `report.passed`/`report.failures`; gate **remontava** o relatório | `report.is_publishable`; o gate **reusa o relatório persistido** |
| `api/routes.py` (`RenderStatusOut`), `api/preview.py` | shape `passed`/`failures`/`metrics` | tipo novo; a prévia mostra achados (`severity_counts`, evidência) e **não mostra métricas inventadas** (o relatório novo não carrega `metrics`) |

## 3. O tipo antigo foi **aposentado**

`contracts.QaReport` (`passed`/`failures`/`metrics`) **não existe mais** e nenhum consumidor
sobrou (verificado por grep: nenhum `from …contracts import … QaReport`). Para romper o ciclo
`contracts ↔ qa_report`, a base versionada (`_Model`/`SCHEMA_VERSION`) foi extraída para
`domain/schema.py` e é reexportada por `contracts.py` (todos os contratos seguem funcionando).
A régua de mídia `domain/render.evaluate_qa` **fica** (é a régua reusada pela política), mas
devolve o DTO interno `MediaQaResult` — não é o contrato persistido. `domain/policy.evaluate_qa`
também reusa `MediaQaResult`.

## 4. Fonte de verdade única (o gate usa o MESMO relatório)

`RenderQaGate.report` não remede nem remonta achados: devolve o relatório persistido e só
**reamarra a identidade** da versão que se pretende aprovar (`render_id`/`checksum` do render
aprovado), regra da F6. A decisão de QA (`coverage`, `findings`) é a do loop — uma só medição.

## 5. Como o gate de publicação foi preservado (arquivo:teste)

Fluxo F8 íntegro, ponta a ponta, com o relatório novo:

- **Loop → persistência:** `application/render.py::RunRender._render` (+ `render_repo.complete`)
  → provado por `tests/test_render_api.py` (render real, `qa_report` novo, `RENDERED` vs
  `AWAITING_APPROVAL`) e `tests/test_render.py`.
- **Bloqueio de QA (defeito):** `api`/`nosound` → `tests/test_render_api.py::test_video_without_audio_fails_qa_stays_rendered_and_can_be_rendered_again`
  (cobertura `verified` + achado `blocking` de áudio).
- **Intenção imutável (`qa_passed`):** `adapters/postgres/publish_repo.py::decide` +
  `publication_execution.py::_prepare` → `tests/test_publish_api.py::test_qa_failed_video_is_approved_only_with_a_recorded_override`,
  `tests/test_publish_api.py::test_full_flow_approve_twice_publishes_once_and_records_the_id`,
  `tests/test_publication_execution.py` (gate `verify_publication_gate`).
- **Aprovação humana/F6:** `application/production.py::RenderQaGate.report` / `QaHandler` /
  `ApprovalHandler` → `tests/test_production_handlers.py` (aprova; recusa superseded; recusa
  achados blocking) e `tests/test_render.py::test_the_loop_report_is_what_the_gate_blocks_or_approves`
  (**prova de mutação pela raiz:** o relatório do loop aprova o bom e é bloqueado pelo gate no
  defeituoso).
- **Override registrado:** `application/publishing.py::Approve` → `tests/test_publishing.py`.

## Validações reais (comandos e números)

Imagem `faceless-v2-hygiene-test-local:latest`, `-p no:cacheprovider`, `PYTHONPATH=/workspace/renderer`.
**Postgres próprio:** `rp7b-pg`, rede `rp7b-net`, `--tmpfs` do data dir, prova de 64 hex montada
com `-v <dir>:/budget-test-proof:ro` (lida por `pg_read_file` e conferida pelo runner). As **duas**
DSNs foram passadas (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

- **Partição exigida** (publication_api/execution/policy, publish_api, qa_report, quality, render,
  render_api, render_adapters, render_plan_executor, panel*, composition, db, architecture,
  contracts_snapshot) → **434 passed, 1 skipped** em 118,6 s.
- **Suíte completa** (`tests/`, com o `.git` do repo principal montado e o Postgres descartável)
  → **2403 passed, 35 skipped, 1 failed** em 315 s. O único `failed` é
  `tests/test_channel_api.py::test_youtube_association_never_returns_tokens`, **pré-existente e
  relógio-dependente**: ele fixa `token_expires_at=2026-11-21T12:00:00Z` e o relógio já passou
  das 12:00Z. **Provado no base:** o mesmo teste falha em `7fdb607` no mesmo horário (worktree
  temporária), ou seja, nada a ver com esta fatia.
- **Higiene:** `python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (exit 0) e
  `tests/test_secrets_hygiene.py` → **32 passed** (o `.git` do repo principal precisa estar montado
  dentro do container para o `git rev-parse`/`ls-files` de uma worktree; sem ele o scan não
  **completa** — "could not complete safely" — o que é artefato de ambiente, não código).
- **Contratos:** `scripts/export_contracts.py --check` → **exit 0** dentro do container.

## 6. O que mudou no contrato

`contracts/v1/qareport.schema.json` deixou de ser `{passed, failures, metrics}` e passou a ser o
relatório versionado da F6: `render_id`, `checksum`, `generated_at`, `coverage` (`verified`/
`not_verified` + motivo), `checks_run[]`, `findings[]` (com `$defs.QaCoverage` e `$defs.QaFinding`:
`finding_id`, `check_id`, `category`, `severity` ∈ blocking/warning/info, `evidence`,
`suggested_action`), `additionalProperties: false`. `contracts/v1/video.schema.json` mudou no
`$defs.QaReport` (mesma troca) — é o `Video.qa_report`. `docs/10-arquitetura.md` **não** mudou
(mesmos nomes de entidade) e não foi tocado à mão.

**Sem migração de banco:** `studio.videos.qa_report` é `jsonb` (`migrations/0001_init.sql:23`),
então o shape novo cabe sem DDL. Linhas gravadas **antes** da adoção continuam legíveis pela
compat `publishable_payload` (lê `passed`); o `repo._video` valida estritamente o tipo novo
(linhas legado pré-adoção não são reprocessadas — ver Limitações).

## Limitações (honestas)

- **Linhas pré-adoção:** `publish_repo.decide` ainda interpreta o shape antigo (`passed`) por
  compatibilidade, mas `repo._video` valida o tipo novo — um vídeo com `qa_report` legado no banco
  falharia a leitura estrita. Não há backfill nesta fatia (não pedido; o banco é descartável/novo).
- **`Ffmpeg SIGKILL`/rc 137 (OOM)** não foi observado nesta rodada; os clipes e os renders de teste
  são curtos (2 cenas).
- A **avaliação semântica multimodal** continua fora (sem provedor), como na RP-07; o QA
  determinístico não inventa cobertura.
- `RenderQaGate` reamarrando a identidade preserva o contrato da F6 (a versão aprovada é a
  publicável); em produção, no caminho normal de aprovação a identidade persistida já é a do
  render mais recente, então o reamarramento é um no-op.
