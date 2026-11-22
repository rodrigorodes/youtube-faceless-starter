# W4.2 — Reabrir vídeo aprovado (ADR-002 / P-04): fechamento

**Status:** implementado no worktree `ve-w4-2-reopen` e **portado para o checkout principal**.
Nada commitado. Nenhuma rota HTTP foi adicionada (decisão da fatia: a rota entra depois).

## O que mudou

| Arquivo | Mudança |
|---|---|
| `domain/states.py` | `APPROVED → SCRIPTED` declarada; `PUBLISHED` continua terminal |
| `application/reopen.py` (novo) | `ReopenForEditing`, guarda pura `publication_guard`, erros `PublicationAlreadyCompleted` / `PublicationInFlight` / `ReopenConflict` |
| `adapters/postgres/publish_repo.py` | `PostgresReopenRepository` (lease + transação de reopen) e filtros `invalidated_at IS NULL` em claim/upload/retry/mark_uploaded |
| `migrations/0043_reopen_approved_video.sql` (novo) | `approval_history`; `publications.invalidated_at`/`invalidation_reason`; índice único parcial de publicação ativa |
| `docs/schema/studio.sql`, `docs/22-modelo-de-dados.md` | regenerados com as 37 migrações (inclui 0042 da W4.0) |

## As 5 regras do ADR-002, como ficaram garantidas

1. **Sem publicação concluída.** `publication_guard` recusa `UPLOADED`/`PUBLISHED`/`youtube_video_id` presente.
2. **Sem upload em andamento.** Recusa lease ativo (`UPLOADING`, `PENDING` com lease), `upload_uri` ou DLQ; o `SELECT … FOR UPDATE` da linha do vídeo serializa com `claim`/`mark_uploaded`.
3. **Intenção pendente invalidada na mesma transação.** Aprovação e intenção são **movidas** para `approval_history`; a publicação que nunca subiu recebe `invalidated_at` (linha e `attempt` preservados).
4. **Aprovação anterior vai para o histórico.** `approval_history` guarda `render_id`, checksum, QA e motivo; a versão nova exige nova aprovação.
5. **Render/QA obsoletos.** `videos.qa_*` zerado; render/QA antigos não promovem a versão nova.

`PUBLISHED` não reabre; duplicar é o caminho. CAS final: `WHERE status = 'APPROVED'`.

## Evidência real

- No worktree: `tests/test_reopen.py tests/test_states.py` → **17 passed**; conjunto pedido
  (`test_states`, `test_publish_api`, `test_publication_execution`, `test_architecture`) →
  **61 passed, 1 failed** (a falha é a expectativa velha de `test_publish_api` sobre "QA Aprovado",
  já corrigida no checkout principal).
- **Portado para o checkout principal:** `test_reopen.py test_states.py test_db.py
  test_schema_docs.py` → **36 passed** (11 s), `hash renderer/app=9514aa164cd3fce5`,
  `migrações=38`. `test_publish_api.py` isolado → **14 passed**.

## Riscos e limitações registrados

1. **Ordem de locks:** `reopen` bloqueia vídeo → publicação; `mark_uploaded` bloqueia
   publicação → vídeo. Há risco teórico de deadlock se um upload e um reopen concorrerem no
   mesmo vídeo. Não exercitado por teste de concorrência; registrado para avaliação.
2. **Constraint removida:** a migração 0043 **remove** `publications_video_id_key` e a substitui
   por índice único parcial (`WHERE invalidated_at IS NULL`). É relaxamento de unicidade, não
   remoção de dado; toda consulta de publicação ativa ganhou o filtro. Revisar em code review.
3. **Sem rota HTTP:** `ReopenForEditing` não é acionável pelo produto ainda. A rota entra numa
   fatia seguinte (não autorizada nesta).
4. **Sem teste de concorrência** dos dois reopen simultâneos (o caso de CAS está coberto pelo
   `WHERE status = 'APPROVED'`, mas não por dois processos reais).
