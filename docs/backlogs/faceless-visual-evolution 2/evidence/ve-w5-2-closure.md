# W5.2 (PUB-02) — retry/reconciliação sem upload duplicado

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado no worktree `ve-w5-2-publish-reconcile` e **portado** para o checkout principal.
**Testes:** container, tags `faceless-renderer:w43` / `faceless-renderer-pytest:w43`.

## 1. O que mudou

**`application/publication_execution.py`**
- Guarda dura: publicação com `youtube_video_id` confirmado devolve `UPLOADED` sem tocar na rede.
- Exceção do adaptador não é mais `TRANSIENT`/retry: sem prova de ausência de efeito, vira `UNKNOWN`/reconciliação.
- `_settle`: `PublicationConflict` bloqueia; falha ao gravar o id do vídeo já subido vai para reconciliação (não DLQ); sessão resumable que não pôde ser registrada exige reconciliação em vez de reenviar.
- Docstring documenta idempotência e o caminho servidor × n8n.

**`api/preview.py`** — mensagem de sucesso corrigida: "A publicação é feita pelo servidor do Studio" (antes dizia n8n).

**`api/routes.py`** — docstring de `/publications/execute` marca o caminho efetivo; `/publications/claim` registra o achado (caminho legado fora do gate de identidade, sem consertar o n8n).

**`tests/test_publication_execution.py`** — 6 testes novos: confirmada não reenvia; segundo clique não reivindica; retry reusa sessão; exceção do adaptador não reenvia; sucesso sem id reconcilia; sessão não registrada não reenvia.

## 2. Evidência (container)

| Comando | Resultado |
|---|---|
| `tests/test_publication_execution.py` | 43 passed (no worktree) |
| `test_publication_execution + test_publication_api + test_publishing + test_publication_policy + test_publish_domain + test_workflow_publish` | **136 passed, 1 skipped** (checkout principal, portado) |
| `test_publication_resilience_repo + test_publish_repo + test_youtube_publisher + test_publish_api` | 76 passed (worktree) |
| `test_architecture + test_videos_v3 + test_ux_contract + test_contracts + test_contracts_snapshot` | 44 passed (worktree) |

## 3. Achados / lacunas (não corrigidos)

- `workflows/03-publish-approved.json` tem `"active": false` no JSON versionado; não foi consultada instância n8n viva.
- `/publications/claim` continua fora do gate de identidade do canal; se o workflow for reativado, precisa entrar no gate ou ser desativado.
- `PostgresPublicationRepository.retry()` continua devolvendo `None` (409) por desenho; o retry seguro é `claim_retry` via `/publications/execute`.
- Contrato `Publication` não expõe `remote_state`/`offset_bytes`; a defesa é o filtro do repositório + guarda de `youtube_video_id`.
