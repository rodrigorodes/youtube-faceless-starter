# F01 — publicação unificada, orçamento e contingência (onda 2, sem commit)

Todas as rodadas usam o PostgreSQL descartável da F00
(`postgresql://postgres:test@127.0.0.1:55433/postgres`) e as mesmas variáveis do baseline:
`STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN`, `STUDIO_BUDGET_TEST_PROOF_FILE`.

## F01.T01 — token do canal de destino (integrada)

- `application/channel_grant.py`: `EnsureGrantAccessToken` devolve o token **do grant do canal de
  destino** e `TargetChannelTokenProvider` escolhe entre grant e legado de forma explícita.
- Sem destino configurado o caminho legado continua; com destino, não existe fallback silencioso.
- `tests/test_channel_grant_token.py` — 13 passed (arquivo novo da fatia).

## F01.T03 — escopo e atribuição de orçamento (integrada)

- Escopos de reserva por projeto/canal/vídeo; `0038_budget_scope_attribution.sql` (aditiva).
- `tests/test_budget_guard.py`, `tests/test_budget_reservations.py`, `tests/test_channel_budget_service.py`
  — 201 passed no grupo.
- Efeito colateral tratado: `tests/test_db.py` passou a exigir a migração 0038 e o schema
  documentado (`docs/schema/studio.sql`, `docs/22-modelo-de-dados.md`) foi regenerado.

## F01.T02 — unificar publicação e analytics (integrada)

Desenho: **o Core executa; o n8n só orquestra.**

- `POST /studio/publications/execute` (aditivo, protegido pelo header do worker) roda
  claim por lease → preparação (QA/intenção/arquivo) → token do **grant** → gate de identidade →
  upload → settle (`UPLOADED` / `RETRY` / `RECONCILE` / `DEAD_LETTER` / `BLOCKED` / `IDLE`).
- `workflows/03-publish-approved.json` reescrito: 10 nós, **nenhum** com `youTubeOAuth2Api`,
  nenhum `googleapis.com`; o único caminho de upload é o endpoint do Core.
  `Result` separa `UPLOADED`/`IDLE`/`RECONCILE` e manda todo o resto (inclusive `BLOCKED` e
  `DEAD_LETTER`) para `Bloqueado ou DLQ` — nunca para sucesso.
- Analytics: `AccessToken.scopes` (novo, opcional, sem expor o token); `ChannelAnalyticsAdapter`
  usa o **grant do canal de destino** quando há destino e recusa sem o escopo
  `yt-analytics.readonly`; sem destino, mantém o cofre legado. Nunca mistura identidades.
- `workflows/README-publish-approval.md` reescrito: por que continua `"active": false` e as
  condições obrigatórias para ativar.

Evidência (com banco): `tests/test_publication_execution.py`, `test_publication_api.py`,
`test_workflow_publish.py`, `test_workflow_analytics.py`, `test_analytics_collection.py`,
`test_publication_resilience_repo.py`, `test_channel_grant_token.py` — **147 passed** no grupo
com DSN (o arquivo de workflow roda 10 testes e falha se algum nó voltar a carregar credencial
do YouTube ou a apontar para host fora do renderer).

## F01.T04 — ativação e contingência (integrada)

- `Settings.publication_enabled` (`STUDIO_PUBLICATION_ENABLED`, padrão ligado) fia
  `RunPublication(enabled=...)`.
- Desligado, `execute()` devolve `BLOCKED` **antes** do claim: sem token, sem upload e sem
  marcar nada como enviado. Ligado, o comportamento é o de antes (teste explícito).
- Testes novos: `test_disabled_publication_blocks_before_claim_and_never_uploads`,
  `test_disabled_publication_does_not_mark_anything_as_sent`,
  `test_enabled_by_default_preserves_the_existing_behavior`,
  `test_publication_flag_is_read_from_the_environment`.

## Limites e riscos residuais

- O workflow 03 continua inativo: falta exercitá-lo numa instância n8n real (dois workers,
  lease vencido, timeout após envio, callback atrasado). Sem essa prova, ativar seria declarar
  operação não medida.
- `budget_guard` continua desligado por padrão; a política de ativação é decisão operacional
  (registrada em `decisions-needed.md`).