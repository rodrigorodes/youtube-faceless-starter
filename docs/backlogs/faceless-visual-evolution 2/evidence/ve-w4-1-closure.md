# W4.1 (EDIT-01) — fechamento

**Frente:** edição de roteiro por cena com CAS e idempotência.
**Worktree de origem:** `ve-w4-1-edit` (branch `ve/w4-1-edit`).
**Portado para:** checkout principal `/Users/rodrigomendes/youtube-faceless-starter` (HEAD `a2e6a39`), **sem commit/push**.
**Data:** 22/11/2026.

## 1. O que entrou (portado do worktree)

| Arquivo | Mudança |
|---|---|
| `renderer/app/studio/domain/longform.py` | `chapter_for_position` e `with_chapter_scene_delta` (contagem de cenas e alvo redistribuído) |
| `renderer/app/studio/application/errors.py` | `ScriptEditIdempotencyConflict` |
| `renderer/app/studio/application/ports.py` | `ScriptEditOutcome`, `ScriptEditRecord`, `find_edit`/`save_edit` na `LongFormScriptRepository` |
| `renderer/app/studio/application/longform.py` | `_ScriptSceneMutation` + `EditScriptScene` (replay idempotente), `AddScriptScene`, `RemoveScriptScene`, `ReorderScriptScenes` |
| `renderer/app/studio/application/editorial.py` | campos `add_scene`, `remove_scene`, `reorder_scenes` |
| `renderer/app/studio/composition.py` | fiação dos três novos use cases |
| `renderer/app/studio/adapters/postgres/editorial_repo.py` | `find_edit`, `save_edit` (CAS + versão + registro idempotente na mesma transação), `_read_scenes`, `_outcome_to_json`/`_outcome_from_json` |
| `renderer/app/studio/api/routes.py` | rotas `POST /videos/{id}/script/scenes`, `POST .../scenes/{idx}`, `DELETE .../scenes/{idx}`, `POST .../scenes/reorder`; `_required_idempotency_key`; mapeamento 409 do conflito |
| `renderer/app/studio/adapters/postgres/migrations/0044_script_edit_requests.sql` | tabela aditiva `studio.script_edit_requests` (PK `video_id,idempotency_key`, hash do payload, resultado, FK CASCADE) |
| `docs/schema/studio.sql`, `docs/22-modelo-de-dados.md` | regenerados por `scripts/export_schema.py --build` contra Postgres real |
| `tests/test_longform_domain.py`, `test_longform_repo.py`, `test_editorial_repo.py`, `test_script_page.py` | testes de CAS, replay, conflito, add/remove/reorder, migração |

### Desvio de numeração (registrado)

O worktree usava `0043_script_edit_requests.sql`; no checkout principal `0043` já estava ocupado por `0043_reopen_approved_video.sql` (W4.2). A migração foi renumerada para **`0044_script_edit_requests.sql`** e o teste de migração foi ajustado para o novo nome. Nenhuma mudança de comportamento.

### Desvio de documentação (registrado)

O worktree editou os docs à mão. Aqui os docs foram **regenerados** com introspecção real: `python3 scripts/export_schema.py --dsn "postgresql://...@127.0.0.1:55421/studio" --build` → `39 migrações`, `script_edit_requests` presente no DDL e no modelo. O Postgres descartável foi removido depois.

## 2. Contrato de comportamento (inalterado do worktree)

- **Rotas** (ordem de registro importa: `/reorder` antes de `{scene_idx}`).
- **Obrigatórios:** `expected_version >= 1` e `Idempotency-Key` (header ou campo). Sem chave → `400`; fora do formato canônico → `422`.
- **CAS:** `save_edit` bloqueia a linha do vídeo com `FOR UPDATE`, confere status e `MAX(version)`; divergência → `None` → `409`. Nada é escrito quando o CAS falha.
- **Idempotência:** mesma chave + mesmo hash → resultado gravado (sem nova versão); mesma chave + hash diferente → `ScriptEditIdempotencyConflict` → `409`.
- **Estado:** só `IDEA`/`SCRIPTED`; `APPROVED` e demais → `409` com mensagem acionável.
- **Identidade de cena:** casa por conteúdo (narração + intenção visual) e depois por posição; reordenação preserva id e mídia; cena editada no lugar mantém id, limpa `asset_id` e marca `media_review_required`; cena removida não reaparece.

## 3. Verificação real (container, `scripts/test-container.sh`)

Imagens: `FACELESS_TEST_IMAGE=faceless-renderer:main`, `FACELESS_PYTEST_IMAGE=faceless-renderer-pytest:main`.

### Focados

```text
tests/test_longform_domain.py tests/test_longform_repo.py tests/test_editorial_repo.py tests/test_script_page.py tests/test_architecture.py -q
→ 66 passed, 1 warning in 12.06s
```

### Suíte completa (sem concorrência)

```text
scripts/test-container.sh tests -q -rfEs
→ 2 failed, 3186 passed, 6 skipped, 1 warning in 387.75s
```

- `hash renderer/app=bbe4cd8b8b8ff890`, `migrações=39`.
- **As 2 falhas são pré-existentes de isolamento de teste**, não regressão desta frente:
  - `tests/test_port_contracts.py::test_every_registered_provider_satisfies_its_port`
  - `tests/test_port_contracts.py::test_catalog_and_registry_have_no_drift`
  - Causa: `register(...)` em nível de módulo em `tests/test_editorial_api.py` e `tests/test_render_api.py` vaza no `_REGISTRY` global. O arquivo isolado dá **8 passed**. O subagente S8 já confirmou as mesmas 2 falhas no HEAD `a2e6a39` sem as mudanças (relatório S8, §2).
- Os 6 skips são `Node.js` ausente na imagem (filtro JS do painel e páginas de workflow).

### Correções de teste exigidas pela portagem

- `tests/test_db.py`: lista de migrações de `test_migrate_applies_once` e `test_failed_migration_rolls_back_and_is_not_kept` passou a incluir `0044_script_edit_requests`; `test_creates_tables` passou a incluir `script_edit_requests` e `approval_history`. Não é enfraquecimento: é a lista real de migrações/tabelas depois da adição.
- `tests/test_editorial_repo.py::test_script_edit_requests_migration_is_additive_and_cascades`: nome do arquivo atualizado para `0044`.

## 4. Nada pendente nesta frente

- Sem commit, sem push (bloqueado por restrição).
- `.env` e `requirements` não tocados; `.env.example` já estava modificado por outra frente antes desta portagem.
- Nenhum artefato de worktree foi apagado.
