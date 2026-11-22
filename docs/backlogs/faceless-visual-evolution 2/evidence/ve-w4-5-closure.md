# W4.5 (EDIT-04) — histórico recuperável de revisões de cena

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado no worktree `ve-w4-5-history` e **portado** para o checkout principal.
**Testes:** container, tags `faceless-renderer:w43`.

## 1. O que foi entregue

- Migração aditiva **`0046_scene_revisions.sql`** (renumerada de 0045 para não colidir com a 0045 da W5.1): tabela `studio.scene_revisions` com PK `(video_id, version, scene_id)`, FK a `studio.scripts(video_id, version)` e **sem FK em `asset_id`** (mídia apagada permanece no histórico); backfill da versão corrente.
- `editorial_repo.py`: captura do snapshot ao escrever cada versão (`_write_script` → `_refresh_current_revision` + `_capture_revision`), `revision_scenes`/`revision_summaries`/`save_restore`/`_restore_scenes`.
- `longform.py`: `ScriptRevisionView`, `ListScriptRevisions`, `GetScriptRevision`, `RestoreScriptRevision` (CAS + idempotência).
- `ports.py`: `SceneRevision`, `ScriptRevisionSummary` + 3 métodos; `errors.py`: `ScriptRevisionUnavailable`.
- `routes.py`: `GET/POST /videos/{id}/script/revisions[...]`, modelos e 409.
- `script_view.py` (`editable`/`restorable`/`scene_count`/`media_pending`), `editorial.py` e `composition.py` (fiação), `panel_video_workspace.py` (cartão de histórico + JS de restauração honesto).
- Testes: `test_script_revision_restore.py` (novo), `test_script_page.py`, `test_db.py`.

**Restaurar cria uma NOVA revisão** com texto + ordem + `asset_id` da revisão escolhida; asset inexistente vira `media_review_required` com `asset_id = NULL`. Nada é apagado.

## 2. Evidência (container, checkout principal)

| Comando | Resultado |
|---|---|
| `test_script_revision_restore + test_script_page + test_video_workspace + test_db` | **64 passed** em 11.93 s |
| `test_editorial_repo + test_longform_repo + test_longform_editorial` (rodada anterior) | 102 passed no agregado |

## 3. Lacunas / riscos

- Revisões legadas sem snapshot devolvem **409** (`ScriptRevisionUnavailable`) em vez de reconstruir do estado vivo (deliberado; a UI diz "sem snapshot recuperável").
- `asset_id` sem FK por desenho — tolera asset apagado; o custo é não ter integridade referencial na coluna.
- Clique real no botão de restauração não exercitado em navegador (JS coberto por asserção de estrutura).
- Vazamento pré-existente de `_REGISTRY` entre `test_editorial_api` e `test_port_contracts` (achado #11) — não corrigido aqui.
