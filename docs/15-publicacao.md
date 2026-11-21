# Aprovação e publicação (F8)

Fluxo padrão: `AWAITING_APPROVAL` → (humano) `APPROVED` → publicação **nativa** → `PUBLISHED`.

A publicação é executada pelo **caminho nativo** do Studio — o executor pela porta
`YouTubeUploader` (`application/publication_execution.py`, `adapters/youtube_publisher.py`) — e
**não** pelo n8n. O workflow `workflows/03-publish-approved.json` continua inativo por design
(veja [o motivo](../workflows/README-publish-approval.md) e o aviso no fim desta página).

> **Segredos:** nunca registre tokens, o `upload_uri` ou o arquivo de client secret em logs, capturas
> ou tickets. O `upload_uri` é omitido nas respostas da API. Configure a
> [autenticação local](17-studio-auth.md) antes de expor `/studio`.

## Prévia e decisão
- `GET /studio/videos/{id}/preview`: página com player, legenda, QA, roteiro, fontes e créditos. HTML escapado, CSP com nonce.
- `POST /studio/videos/{id}/approve` exige `output_asset_id` do render revisado, além dos campos opcionais título, descrição, tags, `publish_at`, `override_reason`, `visibility` (padrão `private`) e `confirm_publication` (padrão `false`). `/reject` recebe `reason`. A prévia anexa a revisão do player. Clientes da API obtêm o ID do job concluído em `GET /studio/videos/{id}/render` e devem baixar o arquivo com `GET /studio/videos/{id}/file?output_asset_id=<id>` antes de enviar a decisão. Se outro render terminar, a aprovação antiga retorna 409. Repetir uma decisão já gravada é seguro (`changed: false`).
- Vídeo `RENDERED` (QA reprovado) só é aprovado com `override_reason`; fica gravado em `studio.approvals`.
- Título ≤ 100, descrição ≤ 4000, ≤ 15 tags, sem `<` ou `>`. `publish_at` precisa de fuso e ficar entre 15 min e 1 ano.
- A transição genérica `/transition` não aprova nem publica (403).

## Intenção de publicação e gate de QA
A aprovação grava, **na mesma transação**, a intenção em `publication_intents` com `render_id` (job) e
`checksum` (cache_key do asset) **imutáveis**, mais uma `idempotency_key` determinística
(`pub-<video>-<render>-<checksum>`). O executor só publica se `render_id`, `checksum`,
`output_asset_id` e a aprovação coincidirem com o render atual e o QA tiver passado (ou houver
`qa_override` **registrado** na aprovação). Um render novo depois da aprovação bloqueia (`BLOCKED`).

## Caminho nativo (padrão)
| Rota | Função |
|---|---|
| `GET /studio/videos/{id}/publication` | estado da publicação do vídeo (`upload_uri` omitido) |
| `POST /studio/videos/{id}/publication/publish` | executa um passo do caminho nativo: claim por lease → gate de QA → token do canal → upload pela porta `YouTubeUploader`. Corpo `PublishIn`: `lease_seconds` (20–7200) e `max_attempts` opcional. |
| `POST /studio/publications/{id}/reconcile` | reconcilia um resultado externo desconhecido; **nunca** presume sucesso |
| `POST /studio/publications/{id}/uploaded` | grava o ID do YouTube (`[A-Za-z0-9_-]{11}`, único) e marca `PUBLISHED` numa transação; mesmo ID = no-op, outro ID = 409 |

`publish` e `reconcile` devolvem `result` ∈ `IDLE` (nada pendente), `UPLOADED`, `RETRY` (falha
transiente, agenda backoff com teto de tentativas), `RECONCILE` (estado externo ambíguo — exige
reconciliação; retry tem prioridade sobre publicação nova na mesma sessão), `DEAD_LETTER` (falha
permanente ou tentativas esgotadas) ou `BLOCKED` (gate de QA/identidade impede qualquer upload).

O ID do YouTube é registrado uma única vez (`mark_uploaded` idempotente). A sessão resumível é a
única identidade do upload: repetir dentro dela não cria um segundo vídeo.

O corpo do YouTube usa privacidade `private` por padrão (com `publishAt` quando agendado),
`selfDeclaredMadeForKids=false` e `containsSyntheticMedia=true`. A descrição final acrescenta aviso
de IA, créditos de imagem e fontes, com limite de 5.000 bytes UTF-8; se os créditos e as fontes não
couberem integralmente, a preparação falha em vez de cortá-los. Um agendamento vencido (`EXPIRED`)
ou a menos de 15 min (`TOO_LATE`) bloqueia antes do upload.

## Publicação pública exige confirmação extra
O padrão é `private`. Para publicar como `public`, envie na **aprovação** `visibility="public"` **e**
`confirm_publication=true`; sem a confirmação explícita a resposta é erro
(`PublicConfirmationRequired`). A visibilidade desejada fica gravada na intenção — o endpoint de
publicação não recebe visibilidade. Agendar usa `private` + `publishAt`; agendamento `unlisted` é
recusado em vez de prometer um comportamento falso.

## Conectar o canal do YouTube (OAuth)
O canal é consentido pelo app OAuth do projeto, não por credencial dentro do n8n:
- Endpoints: `POST /studio/projects/{id}/youtube-oauth/authorize`, `.../callback`, `.../refresh` e
  `.../revoke`; o estado atual vem de `GET /studio/projects/{id}/youtube-channel`.
- Ou pela CLI: `PYTHONPATH=renderer python3 scripts/youtube_oauth_consent.py url|exchange|status|revoke
  --project-id <id>` (grava o refresh token no cofre; nunca o imprime).
- Configuração: `STUDIO_GOOGLE_CLIENT_SECRET_FILE` e `STUDIO_GOOGLE_OAUTH_REDIRECT_URI` (padrão
  `http://localhost:8000/studio/oauth/callback`).
- O escopo `https://www.googleapis.com/auth/youtube.upload` basta para publicar. Sem
  `youtube`/`youtube.force-ssl` a API **não** apaga nem altera vídeos depois do upload.
- Modo *Testing* do Google: o refresh token expira em 7 dias (reconecte). `videos.insert` tem bucket
  próprio de ~100 chamadas/dia, segundo a documentação.

## Caminho legado (n8n) — inativo
> O workflow `workflows/03-publish-approved.json` usa `POST /studio/publications/claim` (caminho
> legado do F6), que **não** exige a `publication_intent` nem o gate de QA. Ele está
> **`"active": false`** por design; não o reative sem migrar para `.../publication/publish` e
> `.../publications/{id}/reconcile`. Condições e motivos verificados:
> [`workflows/README-publish-approval.md`](../workflows/README-publish-approval.md).

Os endpoints do fluxo legado continuam registrados apenas para o workflow inativo: `claim`,
`upload-uri`, `uploaded`, `failed` e `thumbnail-set`. `POST /studio/videos/{id}/publication/retry`
está **desabilitada** (retorna 409); a retomada exige reconciliação humana.

## Não verificado
- Publicação **pública/agendada** real: o smoke da F8 sobe `private`; público é coberto só por teste offline.
- Efeito real de `publishAt` e expiração do token OAuth fora do modo *Testing*.
- Concorrência real entre dois workers contra o YouTube (coberta com fake, não contra a API).
