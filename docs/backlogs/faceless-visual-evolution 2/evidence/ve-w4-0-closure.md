# W4.0 — IDs de cena estáveis (R2): fechamento

**Data:** 22/11/2026 · **Origem:** worktree `ve-w4-0-scene-ids` (branch `ve/w4-0-scene-ids`),
portado para o checkout principal. **Nada commitado.**

## O que mudou

| Arquivo | Mudança |
|---|---|
| `renderer/app/studio/adapters/postgres/migrations/0042_scene_stable_identity.sql` | **nova** migração aditiva: `media_review_required boolean NOT NULL DEFAULT false` em `studio.scenes` |
| `renderer/app/studio/adapters/postgres/editorial_repo.py` | `_write_script` não faz mais `DELETE`+`INSERT`; casa cenas em duas passadas (conteúdo exato, depois posição), preserva `id`/`asset_id` nas não afetadas, limpa `asset_id` e marca `media_review_required` quando a narração muda, desloca posições para não colidir com `UNIQUE (video_id, idx)` |
| `tests/test_editorial_repo.py` | +139 linhas: A06 (editar cena 3 preserva as outras), A08 (add/reorder/remove), migração com dados sintéticos |
| `tests/test_longform_repo.py` | ajuste de expectativa de escrita |
| `tests/test_db.py` | migração 0042 entra na lista esperada |
| `docs/schema/studio.sql`, `docs/22-modelo-de-dados.md` | regenerados por `scripts/export_schema.py --build` (artefatos gerados validados pela suíte) |

## Evidência real

- No worktree de origem: focados `tests/test_editorial_repo.py` + `tests/test_longform_repo.py`
  → **21 passed**.
- Suíte completa no worktree: **6 failed, 3037 passed, 6 skipped** (434 s); as 6 falhas são
  pré-existentes/dependentes de ordem (contrato gerado no HEAD, poluição de registry entre
  testes, `test_publish_api` pré-existente, scanner de segredos sem `.git` no worktree).
- **Portado para o checkout principal e revalidado:** `tests/test_editorial_repo.py`
  `tests/test_longform_repo.py` `tests/test_db.py` → **36 passed** (12 s), com
  `hash renderer/app=43489eedf465e75f` e `migrações=37`.

## Achados e limitações registrados

- `media_review_required` está persistida e testada no banco, mas **não** foi exposta no modelo
  `Scene` (`domain/contracts.py`); a rota W4.1 precisa expô-la.
- `SceneDraft` não carrega `id`: quando reordenar/editar/inserir/remover acontecem na mesma
  versão, o casamento por posição pode atribuir identidade de uma cena editada a outra. W4.1
  deve passar IDs explícitos.
- Duas cenas com narração e prompt idênticos são indistinguíveis; o casamento é determinístico
  pela primeira ocorrência.
- A suíte completa no worktree não pôde ser repetida por contenção de Postgres/memória; a
  execução válida é a registrada acima.
