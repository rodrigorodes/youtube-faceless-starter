# W4.4 (EDIT-03/VE-06) — troca de mídia por cena com candidatos

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado em `ve-w4-4-media` e **portado**.
**Testes:** container, tags `faceless-renderer:w43`.

## Entregue
- `application/ports.py`: porta `MediaFetcher`; `AssetRepository.swap_scene_asset(...)` (CAS no vínculo lido).
- `application/media.py`: `ListSceneCandidates`/`SceneCandidates` e `SwapSceneMedia`/`SceneMediaResult` (aceita `candidate` ou `asset_id`; sem escolha = no-op; licença obrigatória; idempotente; CAS no vínculo + `expected_version` opcional); `SceneNotFound`, `SceneMediaRefused`.
- `adapters/media_pexels.py`: `PexelsMediaFetcher` (só host confiável `*.pexels.com`; licença/atribuição do candidato).
- `adapters/postgres/media_repo.py`: `swap_scene_asset` (`UPDATE ... WHERE video_id AND id AND asset_id IS NOT DISTINCT FROM expected`).
- `composition.py`: fiação; busca/fetcher Pexels só com `PEXELS_API_KEY`.
- `routes.py`: `GET /videos/{id}/scenes/{scene_id}/media/candidates` e `POST .../media`; 404/422.
- Testes: `test_media_swap.py` (novo, 15), `test_media_swap_api.py` (novo, 8), `test_media_api.py`, `test_media_search.py`, `test_render_cache.py`, `test_render_regeneration.py`.

## Evidência (checkout principal)
| Comando | Resultado |
|---|---|
| `test_media_search + test_media_swap + test_media_swap_api + test_media + test_media_api + test_render_cache + test_render_regeneration + test_render_reuse + test_composition` | **161 passed** em 12.57 s |

## Lacunas
- UI da aba Cenas não ligada (rota + testes entregues, como o enunciado permitia).
- Candidato aceito do corpo da requisição (licença validada não-vazia; download só de host Pexels). Multiusuário exigiria re-buscar por `media_id` no servidor (P-06: operador único confiável).
- Sem `PEXELS_API_KEY`, `list_candidates` responde 503; o vínculo por `asset_id` continua.
