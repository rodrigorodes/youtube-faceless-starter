# Aprovação e publicação (P05)

Fluxo: `AWAITING_APPROVAL` → (humano) `APPROVED` → (n8n) upload privado → `PUBLISHED`.

> **Não habilite a publicação automática ainda.** Lease vencido não cancela uma
> execução anterior; ainda não existe garantia de publicação única. Configure a
> [autenticação local](17-studio-auth.md) e consulte [riscos e pendências](p05-p07-continuation.md).

## Prévia e decisão
- `GET /studio/videos/{id}/preview`: página com player, legenda, QA, roteiro, fontes e créditos. HTML escapado, CSP com nonce.
- `POST /studio/videos/{id}/approve` exige `output_asset_id` do render revisado, além dos campos opcionais título, descrição, tags, `publish_at` e `override_reason`; `/reject` recebe `reason`. A prévia anexa a revisão do player. Clientes da API podem obter o ID do job concluído em `GET /studio/videos/{id}/render` e devem visualizar o arquivo com `GET /studio/videos/{id}/file?output_asset_id=<id>` antes de enviar a decisão. Se outro render terminar, a aprovação antiga retorna 409. Repetir uma decisão já gravada é seguro (`changed: false`).
- Vídeo `RENDERED` (QA reprovado) só é aprovado com `override_reason`; fica gravado em `studio.approvals`.
- Título ≤ 100, descrição ≤ 4000, ≤ 15 tags, sem `<` ou `>`. `publish_at` precisa de fuso e ficar entre 15 min e 1 ano.
- A transição genérica `/transition` não aprova nem publica (403).

## Fila de publicação (Postgres)
| Rota | Função |
|---|---|
| `POST /studio/publications/claim` | reivindica apenas `APPROVED` sem publicação prévia; `FOR UPDATE SKIP LOCKED` |
| `POST /studio/publications/{id}/upload-uri` | grava a sessão resumable (só `https://www.googleapis.com/upload/youtube/v3/videos?...upload_id=`) |
| `POST /studio/publications/{id}/uploaded` | grava o ID (`[A-Za-z0-9_-]{11}`, único) e `PUBLISHED` numa transação; mesmo ID = no-op, outro ID = 409 |
| `POST /studio/publications/{id}/failed` | registra erro; não habilita outra tentativa, mesmo se `retryable` |
| `POST /studio/videos/{id}/publication/retry` | desabilitada: retorna 409; exige reconciliação humana |
| `POST /studio/publications/{id}/thumbnail-set` | marca a miniatura |

O claim retorna o caminho do asset aprovado, não o último render arbitrário. Aprovações legadas sem referência confiável retornam 409 e exigem reconciliação humana. Um agendamento vencido retorna 409 antes do claim, sem criar publicação; o erro é informado na resposta, não há registro de auditoria separado nem endpoint de reagendamento.

O corpo do YouTube é sempre `private` (com `publishAt` quando agendado), `selfDeclaredMadeForKids=false`, `containsSyntheticMedia=true`. A descrição final acrescenta aviso de IA, créditos de imagem e fontes, com limite de 5.000 bytes UTF-8. Se os créditos e fontes não couberem integralmente, a preparação falha em vez de cortá-los.

## Workflow n8n `workflows/03-publish-approved.json`
1. Importe pela interface do n8n (a CLI não importa estes JSONs) e vincule a credencial `youTubeOAuth2Api` nos nós Check session, New session, Upload e Set thumbnail. Vincule também a credencial separada `studio_worker` nos nós do renderer conforme [autenticação local](17-studio-auth.md).
2. O workflow vem inativo. Quando os riscos documentados estiverem resolvidos, poderá rodar a cada 2 min ou por `POST /webhook/faceless-publish-approved` (envie `Content-Type: application/json`).
3. A retomada automática está bloqueada no servidor, inclusive para `PENDING` legado. Os ramos de consulta da sessão no workflow não são uma autorização para recomeçar.
4. Miniatura (JPEG 1280×720 da 1ª cena) 60 s depois do upload; falha não é fatal.

O workflow usa lease de 5.400 segundos e ignora parâmetros do webhook para
alterar o lease ou introduzir pausas de depuração. Isso reduz sobreposições,
mas **não impede** que um processo antigo continue após vencer o lease.

## Histórico de validação real (antes do bloqueio de retomada)
- Queda do n8n com a sessão de upload já gravada: ao reiniciar, a mesma publicação foi reivindicada (tentativa 2), a consulta à sessão voltou concluída com o ID e o vídeo virou `PUBLISHED`, privado, sem duplicar.
- Só esse ramo ("sessão já concluída") foi exercitado de ponta a ponta, antes das mudanças posteriores no workflow. Os ramos 308 e 404/410 têm teste da classificação (`tests/test_workflow_publish.py`), mas não rodaram contra o YouTube.
- Miniatura: o YouTube recusou por falta de permissão para miniaturas personalizadas. A causa exata não foi comprovada; verificar a elegibilidade do canal é uma possibilidade. A falha não é fatal e `thumbnail_set` fica `false`.
- Ao testar o webhook, envie `Content-Type: application/json`; sem ele o corpo é ignorado e `debug_wait_after`/`lease_seconds` não valem.

## Não verificado
- Expiração do token OAuth fora do modo Testing (em Testing expira em 7 dias).
- Efeito real de `publishAt`.
