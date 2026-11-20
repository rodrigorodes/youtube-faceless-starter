# Aprovação e publicação (P05)

Fluxo: `AWAITING_APPROVAL` → (humano) `APPROVED` → (n8n) upload privado → `PUBLISHED`.

## Prévia e decisão
- `GET /studio/videos/{id}/preview`: página com player, legenda, QA, roteiro, fontes e créditos. HTML escapado, CSP com nonce.
- `POST /studio/videos/{id}/approve` (título, descrição, tags, `publish_at`, `override_reason`) e `/reject` (`reason`). Repetir é seguro (`changed: false`).
- Vídeo `RENDERED` (QA reprovado) só é aprovado com `override_reason`; fica gravado em `studio.approvals`.
- Título ≤ 100, descrição ≤ 4000, ≤ 15 tags, sem `<` ou `>`. `publish_at` precisa de fuso e ficar entre 15 min e 1 ano.
- A transição genérica `/transition` não aprova nem publica (403).

## Fila de publicação (Postgres)
| Rota | Função |
|---|---|
| `POST /studio/publications/claim` | reivindica um `APPROVED` (ou lease vencido); `FOR UPDATE SKIP LOCKED`, lease 1800 s, máx. 5 tentativas |
| `POST /studio/publications/{id}/upload-uri` | grava a sessão resumable (só `https://www.googleapis.com/upload/youtube/v3/videos?...upload_id=`) |
| `POST /studio/publications/{id}/uploaded` | grava o ID (`[A-Za-z0-9_-]{11}`, único) e `PUBLISHED` numa transação; mesmo ID = no-op, outro ID = 409 |
| `POST /studio/publications/{id}/failed` | `retryable` libera o lease; 4xx vira `FAILED` |
| `POST /studio/videos/{id}/publication/retry` | `FAILED` → `PENDING` (manual) |
| `POST /studio/publications/{id}/thumbnail-set` | marca a miniatura |

O corpo do YouTube é sempre `private` (com `publishAt` quando agendado), `selfDeclaredMadeForKids=false`, `containsSyntheticMedia=true`. A descrição final acrescenta aviso de IA, créditos de imagem e fontes.

## Workflow n8n `workflows/03-publish-approved.json`
1. Importe pela interface do n8n (a CLI não importa estes JSONs) e vincule a credencial `youTubeOAuth2Api` nos nós Check session, New session, Upload e Set thumbnail.
2. Ative. Roda a cada 2 min e também por `POST /webhook/faceless-publish-approved` (envie `Content-Type: application/json`).
3. Retomada: com sessão gravada, consulta `PUT Content-Range: bytes */N`. 200/201 = concluído; 308 = envia só o restante; 404/410 = nova sessão.
4. Miniatura (JPEG 1280×720 da 1ª cena) 60 s depois do upload; falha não é fatal.

Parâmetros de teste do webhook: `lease_seconds` (20–7200) e `debug_wait_after` (`init` ou `upload`, espera 45 s para simular queda).

## Validado em execução real
- Queda do n8n com a sessão de upload já gravada: ao reiniciar, a mesma publicação foi reivindicada (tentativa 2), a consulta à sessão voltou concluída com o ID e o vídeo virou `PUBLISHED`, privado, sem duplicar.
- Só esse ramo ("sessão já concluída") foi exercitado de ponta a ponta. Os ramos 308 (envia só o restante) e 404/410 (nova sessão) têm teste da classificação (`tests/test_workflow_publish.py`), mas não rodaram contra o YouTube.
- Miniatura: o YouTube recusou ("doesn't have permissions to upload and set custom video thumbnails"): **miniatura personalizada exige canal verificado**. A falha não é fatal; `thumbnail_set` fica `false`. Verifique o canal em youtube.com/verify para habilitar.
- Ao testar o webhook, envie `Content-Type: application/json`; sem ele o corpo é ignorado e `debug_wait_after`/`lease_seconds` não valem.

## Não verificado
- Expiração do token OAuth fora do modo Testing (em Testing expira em 7 dias).
- Efeito real de `publishAt`.
