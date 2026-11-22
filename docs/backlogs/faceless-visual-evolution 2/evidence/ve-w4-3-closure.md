# W4.3 (EDIT-02) — pré-escuta e regeneração da narração de uma cena

**Data:** 22/11/2026 · **Repo:** `/Users/rodrigomendes/youtube-faceless-starter` · **HEAD:** `a2e6a39` · **Nada commitado**.
**Testes:** só no container (`scripts/test-container.sh`). Imagem usada: `faceless-renderer:w43` / `faceless-renderer-pytest:w43`.

## 1. O que foi entregue

| Peça | Arquivo | Nota |
|---|---|---|
| Portas `SceneDurationStore` / `SceneNarrationStore` | `renderer/app/studio/application/ports.py` | `save_durations`/`durations`; `narration_path(project, video, scene)` |
| Casos de uso `SceneNarration` (pré-escuta) e `RegenerateSceneNarration` | `renderer/app/studio/application/scene_narration.py` | leitura nunca sintetiza; regeneração com estimativa + reserva antes do efeito |
| Repositório Postgres da duração real | `renderer/app/studio/adapters/postgres/scene_duration_repo.py` | grava `studio.scenes.duration_s` (coluna existia desde 0001; nada a gravava) |
| WAV durável por cena | `renderer/app/studio/adapters/storage.py` (`FileRenderStorage.narration_path`) | fora do `work/` descartável |
| Gravação no render | `renderer/app/studio/application/render.py` | `RunRender` opcional: grava a duração medida e copia o WAV |
| Fiação | `renderer/app/studio/composition.py` | `PostgresSceneDurationRepository`, `SceneNarration`, `RegenerateSceneNarration`; `Editorial.scene_narration` / `regenerate_narration` |
| Rotas | `renderer/app/studio/api/routes.py` | `GET /videos/{id}/scenes/{scene_id}/narration.wav`, `POST .../narration/regenerate`, `GET .../narration` (metadados) |

## 2. Decisões de implementação

- **Identidade por `id` estável** (W4.0), nunca por índice.
- **Pré-escuta nunca inventa áudio:** se não há WAV durável nem artefato físico íntegro no índice de cache, devolve `None` (404 na rota).
- **Regeneração só em `IDEA`/`SCRIPTED`:** vídeo aprovado/publicado exige reabrir (W4.2); a rota responde 409 com mensagem acionável.
- **Orçamento igual ao render:** estimativa antes, reserva antes do efeito, `settle` depois; `allow_free_replay=True` para voz gratuita comprovada. Sem `paid_guard`, a síntese roda direta (legado/teste).
- **Render passou a gravar a medida real** de cada cena e a manter o WAV para pré-escuta; sem os novos parâmetros, o render é exatamente o de antes (opcionais).

## 3. Evidência de teste (container)

| Comando | Resultado |
|---|---|
| `scripts/test_scene_narration.py` (com `w43`) | **5 passed** em 5.83 s |
| `tests/test_composition.py tests/test_editorial_api.py tests/test_render_api.py` | **66 passed** em 35.47 s |
| `tests/test_video_workspace.py` | 17 passed (W1, sem regressão) |
| W1 (rótulos/settings/estilos/canais) | 143 passed em 52 s |

Cobertura do novo teste: pré-escuta encontra o WAV; regeneração grava a duração real e serve o WAV; vídeo fora de `IDEA`/`SCRIPTED` → 409; cena de outro vídeo → 422; render grava `duration_s` para todas as cenas.

## 4. Lacunas / riscos registrados (não corrigidos)

- A pré-escuta usa o índice de cache do último render quando não há WAV durável; o índice é lido por `plan:{video_id}` — se o plano não estiver persistido, cai em 404 honesto.
- O WAV é copiado no render, mas o `final.srt`/legendas continuam sendo o artefato de legendas; a pré-escuta não gera legenda por cena.
- `SceneDurationStore` não é transacional com o render: se o `UPDATE` falhar, o render segue e a duração fica ausente (o `find` mede o WAV como fallback).
