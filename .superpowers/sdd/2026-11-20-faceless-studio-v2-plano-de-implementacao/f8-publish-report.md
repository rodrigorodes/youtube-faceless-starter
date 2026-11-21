# F8 — Publicação YouTube resiliente, OAuth e agenda (relatório)

Worktree `f8-publish`, branch `feat/f8-publish`, base `db8eebb`. Sem push/merge. Postgres
descartável próprio (`f8-pg`, rede `f8-net`, prova em `/budget-test-proof/proof`), com **as duas**
DSNs e `STUDIO_BUDGET_TEST_PROOF_FILE`. Migração `0028_publication_resilience` (nas duas listas de
`tests/test_db.py`). `domain/render_plan.py`, `domain/ticks.py`, `contracts/` e
`scripts/export_contracts.py` intocados. `git add` por caminho exato; scanner de higiene **passou**
no conjunto staged antes do commit.

## Commit

- `54a8d55` `feat(publish): OAuth real, publicação resiliente com gate de QA, retry/DLQ e reconciliação (F8)`
  (38 arquivos, +4036/−54)

## O que foi entregue (F8-01…F8-08)

| Card | Entrega | Onde/evidência |
|---|---|---|
| F8-01 | Fluxo mapeado e reescrito no caminho nativo; o legado (claim + n8n) fica estrito e separado | `application/publication_execution.py`, `adapters/postgres/publish_repo.py` |
| F8-02 | `publication_intents` gravada **na mesma transação da aprovação**, com `render_id` (job) e `media_checksum` (cache_key do asset) imutáveis + `idempotency_key` determinística | `domain/publication_policy.py`, migração `0028`, `tests/test_publication_resilience_repo.py` |
| F8-03 | Claim por lease com `claim_retry` (só retoma o que é seguro), sessão resumable gravada com offset e `remote_state` | repo + `test_publication_resilience_repo.py` (concorrência: 1 vencedor entre 8 threads) |
| F8-04 | Retry com backoff exponencial, teto de tentativas, DLQ, ambiguidade → `UNKNOWN` (nunca presumido sucesso) e reconciliação | `application/publication_execution.py`, `adapters/youtube_publisher.py` |
| F8-05 | OAuth real atrás da porta `OAuthClient` (code→token→refresh→revoke) com HTTP injetável; status do canal derivado do token real (expiração/revogação no cofre) | `application/youtube_oauth.py`, `adapters/google_oauth.py`, `tests/test_google_oauth_adapter.py`, `test_youtube_oauth_service.py` |
| F8-06 | Privado por padrão; público exige **confirmação extra** (`confirm_publication`), inclusive na API; agendamento usa `private`+`publishAt` | `domain/publication_policy.py`, `api/routes.py`, `test_publishing.py`, `test_publication_api.py` |
| F8-07 | Workflow automático **permanece desabilitado** com motivo e condições documentadas | `workflows/README-publish-approval.md`, `test_workflow_publish.py` |
| F8-08 | Smoke manual real (ver abaixo), com upload **private** de vídeo sintético | este relatório |

**Gate de QA ligado à publicação (limitação do F6):** o executor só publica se `render_id`,
`checksum`, `output_asset_id` e a aprovação coincidirem com o render atual e o QA tiver passado (ou
houver `qa_override` **registrado**). Um render novo depois da aprovação bloqueia. Provado em
`tests/test_publication_execution.py` (`test_a_stale_render_or_checksum_blocks_publication`,
`test_failed_qa_without_override_blocks_publication`) e no repositório.

**Estágio `publish` do coordenador:** deixou de ser `UnavailableStageHandler` e passou a executar via
`PublishHandler` → `RunPublication`, como última etapa do `COORDINATOR_DAG` (depois de `approval`). O
coordenador só conclui a etapa com id do YouTube confirmado; retry/reconcile/DLQ falham a etapa com o
motivo real, sem autoaprovação.

**Idempotência:** a chave é derivada de `(vídeo, render_id, checksum)`; a sessão resumable é a única
identidade do upload e repetir dentro dela não cria um segundo vídeo. O id do YouTube é registrado
uma vez (`mark_uploaded` idempotente; id diferente é conflito).

## F8-07 — decisão sobre o n8n

**Mantido `"active": false`.** Motivos verificáveis: (1) o workflow usa o `claim` legado, que **não**
exige a `publication_intent`/gate de QA que a F8 passou a exigir — ativá-lo burlaria o gate; (2) a
credencial YouTube dentro do n8n nunca foi exercitada de verdade; (3) a publicação real agora tem
caminho nativo testado. Condições para reabilitar (migrar o workflow para `/publication/publish`,
rodar falha/concorrência em n8n real, então ativar em PR próprio) estão em
`workflows/README-publish-approval.md`. Não foi ativado "para ficar pronto".

## Smoke manual real — o que foi validado de verdade

Executado fora da suíte (testes continuam offline), em container com o arquivo de client secret e o
`token.env` do starter montados **somente leitura** e o vídeo sintético gerado por ffmpeg
(320×240, 3 s). Nenhum token/segredo foi impresso, copiado ou adicionado ao git.

| Prova | Resultado |
|---|---|
| URL de autorização gerada a partir do client secret real | ok — host `accounts.google.com`, `access_type=offline`, PKCE `S256`; sem `client_secret` na URL |
| Leitura real com a API key (`videoCategories`, região BR) | HTTP **200**, 31 categorias — API key funciona |
| `refresh_token → access_token` real | **ok**, 269 ms, 2 escopos |
| Identidade do canal | **"Rodrigo Mendes"** (canal autorizado correto) |
| Upload real, **private**, vídeo sintético, título `[teste automatizado] CERC Studio — apagar` | `UPLOADED`, **`youtube_video_id = acE29V_YkP4`** |
| Confirmação pós-upload (`videos.list`) | existe, `privacyStatus = private`, título correto |
| Remoção (`videos.delete`) | **FALHOU — HTTP 403 `insufficientPermissions`** |

### ⚠️ Vídeo órfão a remover manualmente

**`acE29V_YkP4`** — privado, do teste automatizado, **não** foi possível apagar via API. O
consentimento concedido tem apenas `youtube.readonly` + `youtube.upload`; `videos.delete` exige
`youtube` (ou `youtube.force-ssl`). Remova em <https://studio.youtube.com/video/acE29V_YkP4/edit>
(ou reautorize com escopo maior). Era proibido rodar novo consentimento nesta execução, então o id
fica reportado conforme a instrução — **sem órfão silencioso**.

### O que **não** foi validado contra o YouTube real (e por quê)

- Publicação **pública/agendada** real: o smoke sobe `private` (regra). Público exige confirmação
  extra e só é coberto por teste offline (`test_publication_api.py`, `test_publishing.py`).
- **Remoção** real: bloqueada por escopo (acima).
- **Concorrência real entre dois workers** contra o YouTube: coberta no Postgres/adaptador com fake
  (`test_publication_resilience_repo.py`, `test_youtube_publisher.py`), não contra a API.
- Nenhum conteúdo do usuário (`storage/output/*.mp4`) foi tocado ou publicado.

## Contagens reais (Postgres `f8-pg`, as duas DSNs, prova)

Runner `faceless-v2-hygiene-test-local:latest` (Python 3.12), `-p no:cacheprovider`, rede `f8-net`.

- Focados F8 (domínio+adaptadores+execução+repo+HTTP+coordenação+composição+arquitetura):
  **206 passed, 30 skipped** (os skips são os testes de nó do n8n: `node` ausente na imagem).
- Suíte completa (final, após todos os ajustes): **2083 passed, 35 skipped, 2 failed** em 244 s.
  As **2 falhas são ambientais**: `tests/test_secrets_hygiene.py::test_real_starter_archive_...` e
  `::test_extracted_starter_...` — `package-starter.sh` aborta porque o `.git` da worktree é um
  *gitfile* apontando para fora do mount. Mesmo par de falhas em todas as fatias anteriores; não é
  regressão da F8. (O `python3 scripts/secret_hygiene.py scan` direto **passou** no conjunto staged.)
- **Flakiness qualificada:** numa rodada completa anterior, sob saturação da máquina (7 fatias em
  paralelo), falharam também `test_editorial_api.py::test_script_needs_sources_...`,
  `test_publish_api.py::test_qa_failed_video_...` e os dois `test_panel_production_page.py` que
  precisavam refletir a F8. Os dois primeiros **passam isolados** (render do ffmpeg falha sob carga);
  os dois de painel eram **regressão real** da F8 e foram corrigidos (publicação deixou de ser
  indisponível; stepper passou de 7 para 8 etapas). Rodada final: só as 2 ambientais.

## Checklist para a primeira publicação real (fora de teste)

1. Refresh token já existe; para o app publicar, aponte `STUDIO_GOOGLE_CLIENT_SECRET_FILE` para o
   arquivo original do starter e registre/set `STUDIO_GOOGLE_OAUTH_REDIRECT_URI` (o arquivo atual não
   declara `redirect_uris`; sem lista, o domínio valida só a forma https/loopback).
2. Para revogar/consentir pelo produto, rode a CLI `scripts/youtube_oauth_consent.py` (grava no
   `SecretStore`, nunca imprime token) ou use os endpoints `.../youtube-oauth/{authorize,callback,refresh,revoke}`.
3. Escopo `youtube.upload` (já concedido) basta para publicar. **Para apagar** vídeos via API é
   preciso escopo adicional (`youtube`/`youtube.force-ssl`).
4. Aprovar um vídeo com `render_id`/checksum (a aprovação grava a intenção) e publicar por
   `POST /studio/videos/{id}/publication/publish` (ou pela etapa `publish` do coordenador).
5. Para visibilidade pública, enviar `visibility="public"` **e** `confirm_publication=true`.

## Limitações e fora de escopo

- Publicação real **pública/agendada** não foi exercitada contra a API (regra do smoke = privado).
- Miniatura/autor do upload nativo não foram tratados (a F7 empacota; o n8n legado tratava e segue
  desabilitado).
- O fallback de token do ambiente (`YOUTUBE_REFRESH_TOKEN`) vale para o canal único deste deployment;
  em multiusuário cada projeto usará o consentimento próprio no cofre.
- `Lookup`/delete da API usam o mesmo access token do upload; a regra de menor privilégio mantém o
  escopo sem `youtube`, o que impede `videos.delete` (limitação aceita e reportada).