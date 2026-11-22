# W5.1 (PUB-01) — formulário de aprovação na aba Publicação + invalidação da intenção

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado no worktree `ve-w5-1-publication` e **portado** para o checkout principal.
**Testes:** container, tags `faceless-renderer:w43`.

## 1. O que mudou

**Domínio/aplicação**
- `domain/publication_policy.py`: `metadata_fingerprint(título, descrição, tags, visibilidade)` (sha256 estável), `PublicationIntentObsolete`, `verify_publication_intent(...)`; `PublicationIntentEvidence` ganhou `youtube_channel_id`/`metadata_fingerprint` opcionais (aditivo — registros legados seguem válidos).
- `application/publication_execution.py`: `_confirmed_destination(...)` + chamada de `verify_publication_intent` em `_prepare`, antes do gate de render/QA; divergência bloqueia (DLQ `PERMANENT`) sem upload.
- `adapters/postgres/publish_repo.py`: `decide` grava destino + impressão na mesma transação; `intent()`/`reopen` leem/preservam no histórico.
- Migração `0045_publication_intent_destination_metadata.sql` (colunas anuláveis em `publication_intents` e `approval_history`).

**UI/API**
- `api/approval_form.py` (novo): HTML/JS do formulário numa única fonte, com `html.escape(..., quote=True)` e listener de `submit` (sem handler inline bloqueado por CSP).
- `api/preview.py` passa a reusar `approval_form`; `api/panel_video_workspace.py` renderiza o mesmo bloco na área `publicacao` (JS só nessa área); `api/routes.py` injeta o `Preview` quando `area == "publicacao"`.

## 2. Evidência (container, checkout principal)

| Comando | Resultado |
|---|---|
| `test_publication_policy + test_publication_execution + test_video_workspace + test_publish_api + test_reopen + test_schema_docs` | **126 passed** em 52.82 s |

`docs/schema/studio.sql` e `docs/22-modelo-de-dados.md` regenerados (`scripts/export_schema.py --build`); migrações `40 = 40`.

## 3. Lacunas / riscos (registrados)

- **Reconfirmação:** o guard impede publicar com dados diferentes, mas não há caminho de "confirmação nova" sem reabrir (W4.2), e uma publicação dead-letter bloqueia o reopen (`IN_FLIGHT`). `ConfirmPublication`/reconciliação fica para fatia própria.
- **Caminho legado (n8n):** `ClaimPublication` não consulta a intenção (escopo da W5.2).
- **Intenção legada sem destino (NULL):** o check de destino é pulado; transição "sem destino → destino" não é detectada em intenções antigas.
- **Visibilidade:** entra na impressão; mudá-la exige nova intenção.
