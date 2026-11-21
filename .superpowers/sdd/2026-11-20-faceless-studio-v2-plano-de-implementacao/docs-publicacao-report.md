# Docs de publicação — migração para o padrão novo (F8) (relatório)

Worktree isolada `docs-publicacao`, branch `feat/docs-publicacao`, base `00a1a28`. Sem push/merge.
Outras duas fatias rodam em paralelo; nenhum arquivo fora desta worktree foi escrito.

## Escopo executado
1. Reescrevi `docs/15-publicacao.md` para o **fluxo nativo F8** como padrão.
2. Arquivei e removi `docs/08-publicar-no-youtube.md` (corpo 100% de endpoints mortos).
3. Arquivei e removi `examples/ade-2026-publish.json` (órfão) e tirei a entrada de
   `scripts/secret_hygiene.py` (`ALLOWED_FILES`).
4. Varri `README.md` e docs vivos por links para `docs/08` / `webhook/faceless-publish`.

## Prova obrigatória — endpoint → existe em `renderer/app/studio/api/routes.py`

Todo endpoint citado no `docs/15` novo foi conferido por `grep`. Nenhum 404/410 inventado.

| Endpoint citado no doc | Existe? | `routes.py` (linha) |
|---|---|---|
| `GET /studio/videos/{id}/publication` | sim | 1370 |
| `POST /studio/videos/{id}/publication/publish` | sim | 1401 |
| `POST /studio/publications/{id}/reconcile` | sim | 1416 |
| `POST /studio/publications/{id}/uploaded` | sim | 1389 |
| `POST /studio/videos/{id}/publication/retry` (409) | sim | 1374 |
| `POST /studio/publications/claim` (legado) | sim | 1378 |
| `POST /studio/publications/{id}/upload-uri` (legado) | sim | 1385 |
| `POST /studio/publications/{id}/failed` (legado) | sim | 1393 |
| `POST /studio/publications/{id}/thumbnail-set` (legado) | sim | 1397 |
| `GET/PUT/DELETE /studio/projects/{id}/youtube-channel` | sim | 1678 / 1683 / 1692 |
| `POST /studio/projects/{id}/youtube-oauth/authorize` | sim | 1699 |
| `POST /studio/projects/{id}/youtube-oauth/callback` | sim | 1704 |
| `POST /studio/projects/{id}/youtube-oauth/refresh` | sim | 1709 |
| `POST /studio/projects/{id}/youtube-oauth/revoke` | sim | 1714 |
| `GET /studio/videos/{id}/preview` | sim | 1358 |
| `POST /studio/videos/{id}/approve` / `/reject` | sim | 1344 / 1353 |
| `GET /studio/videos/{id}/render` | sim | 1313 |
| `GET /studio/videos/{id}/file?output_asset_id=` | sim | 1324 (query em 1318/1325) |
| `POST /studio/videos/{id}/transition` (403 p/ aprovar/publicar) | sim | 904 |

Evidência (`grep -n` em `routes.py`):

```
1370: @router.get("/videos/{video_id}/publication", ...)
1374: @router.post("/videos/{video_id}/publication/retry", ...)
1378: @router.post("/publications/claim", ...)
1385: @router.post("/publications/{publication_id}/upload-uri", ...)
1389: @router.post("/publications/{publication_id}/uploaded", ...)
1393: @router.post("/publications/{publication_id}/failed", ...)
1397: @router.post("/publications/{publication_id}/thumbnail-set", ...)
1401: @router.post("/videos/{video_id}/publication/publish", ...)
1416: @router.post("/publications/{publication_id}/reconcile", ...)
1699: @router.post("/projects/{project_id}/youtube-oauth/authorize", ...)
```
(e OAuth/channel em 1678/1683/1692/1704/1709/1714; prévia/decisão/render/file em
1358/1344/1353/1313/1324.)

## O que foi arquivado
- `docs/08-publicar-no-youtube.md` → `archive/docs/08-publicar-no-youtube.md` (`git add -f`,
  cópia verbatim) e `git rm` do original.
- `examples/ade-2026-publish.json` → `archive/docs/ade-2026-publish.json` (`git add -f`) e
  `git rm` do original.
- Diretório de arquivo:
  `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/docs/`.

Por que o corpo do `08` é legado (verificado): importa `workflows/02-create-and-publish.json`
(ausente), chama `POST /webhook/faceless-publish` (não existe) e baixa de
`http://renderer:8000/videos/<id>/file` (410 Gone). O banner do topo do próprio doc já apontava
para 15/18.

## O que decidi **manter** no `15` (e por quê)
- **Aviso curto do n8n inativo**, citando `workflows/README-publish-approval.md`: o workflow 03 usa
  `POST /studio/publications/claim` (legado F6), que não exige `publication_intent`/gate de QA, e está
  `"active": false` por design. Não reativar sem migrar para `publish`/`reconcile`.
- **Máquina de estados** `AWAITING_APPROVAL → APPROVED → publish nativo → PUBLISHED`.
- **Gate de QA por `publication_intents`** (render_id/checksum imutáveis + `idempotency_key`).
- **Confirmação extra para publicação pública**: default `private`; `visibility="public"` exige
  `confirm_publication=true` na aprovação; agendamento usa `private`+`publishAt` (e `unlisted`
  agendado é recusado).
- **Endpoints legados** listados como legado (claim/upload-uri/failed/thumbnail-set) para não
  mentir sobre o que ainda está registrado.
- **Avisos de segurança** que continuam valendo: não logar segredo/`upload_uri`; link para
  `17-studio-auth.md`.

**Portei do `08` o que ainda é vivo** (não estava no `15`): a conexão do canal por OAuth
**nativo** — endpoints `.../youtube-oauth/{authorize,callback,refresh,revoke}`, CLI
`scripts/youtube_oauth_consent.py`, env `STUDIO_GOOGLE_CLIENT_SECRET_FILE`/
`STUDIO_GOOGLE_OAUTH_REDIRECT_URI` (default `http://localhost:8000/studio/oauth/callback`), escopo
mínimo `youtube.upload` (sem `youtube`/`force-ssl` não apaga/altera), caveat do modo *Testing* (7
dias) e cota de `videos.insert` (~100/dia). A parte de n8n/Google-Cloud do `08` (redirect
`localhost:5678`) é morta e ficou só no arquivo. A seção "provider de roteiro" do `08` é concern de
geração de texto, não de publicação, e é coberta por `07-openai-luna-oauth.md`.

## Outras edições
- `README.md`: removido o link para `docs/08` (arquivado); descrição do `15` atualizada.
- `scripts/secret_hygiene.py`: removida `"examples/ade-2026-publish.json"` de `ALLOWED_FILES`.
- Nenhum outro link vivo para `docs/08` ou `webhook/faceless-publish` restou (varredura em
  `*.md`/`*.py`/`*.sh`/`*.json`, exceto histórico em `.superpowers/` e `docs/backlogs/`); o único
  `faceless-publish*` remanescente é o webhook do próprio workflow legado, que não foi tocado.

## Restrições respeitadas
- Não toquei `renderer/**`, `contracts/`, `workflows/`, `backups/`, `credentials/`, nem os docs
  12/14/16/17/20.
- `git rm` por caminho exato; **nenhum** `git add -A`.

## Higiene e testes
- `python3 scripts/secret_hygiene.py scan` → **`Secret hygiene check passed.`** (após mexer no
  `ALLOWED_FILES`).
- `tests/test_secrets_hygiene.py`: **31 passed, 1 failed** —
  `test_extracted_starter_runs_contract_snapshot_and_backup_import`. A falha é **ambiental e
  pré-existente**: o teste empacota o starter e roda `tests/test_contracts_snapshot.py`, que falha com
  `contracts/v1/project.schema.json desatualizado` (`"minimum": 0.0` vs `0`) por diferença de versão
  do pydantic do host. Reproduz direto no worktree (`tests/test_contracts_snapshot.py::`
  `test_committed_contracts_match_code`), sem qualquer alteração minha em `contracts/` ou `renderer/`.
- Subset de publicação (`tests/test_publication_api.py`, `tests/test_workflow_publish.py`) **não
  coletou** neste host: `routes.py` importa `preview.py`, cujo f-string com `\` exige Python ≥ 3.12
  (host tem 3.11.9; o runner da F8 usa 3.12). Limitação ambiental, não do diff (docs + scanner).
