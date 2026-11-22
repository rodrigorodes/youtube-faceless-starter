# W2.3 — aba Composição em leitura (plano persistido)

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado no worktree `ve-w2-3-composition` e **portado** para o checkout principal.
**Testes:** container, tags `faceless-renderer:w43`.

## 1. O que foi entregue

| Arquivo | Mudança |
|---|---|
| `application/composition_view.py` **(novo)** | `BuildCompositionView` + `CompositionView`/`CompositionTrackView`/`CompositionShotView`; depende **só** da porta `RenderPlanRepository`; lê `latest_plan("plan:{video_id}")`. |
| `application/use_cases.py` | Campo `composition_view` no container `UseCases` e em `from_repo`. |
| `composition.py` | Fia `BuildCompositionView(PostgresRenderPlanRepository(connect))`. |
| `api/routes.py` | A rota `/panel/videos/{video_id}/{area}` só consulta o plano quando `area == "composicao"`. |
| `api/panel_video_workspace.py` | `_area_composicao` renderiza o plano em leitura: revisão, tracks (base/overlay/narração/legenda), shots com cena, papel, z-index, janela e ativo; sem plano, estado honesto; escape por `html.escape`. |
| `tests/test_video_workspace.py` | 4 testes novos (plano persistido, ausência, leitura sem controles, escape). |

## 2. Evidência (container)

| Comando | Resultado |
|---|---|
| `tests/test_video_workspace.py tests/test_architecture.py tests/test_panel_page.py` (checkout principal, portado) | **72 passed** em 34.66 s |

## 3. Lacunas / premissas

- "Ativo" foi interpretado como: track ativa = tem shots/cues; shot ativo = cabe inteiro na cena (sempre verdadeiro em plano válido). Não é um conceito de domínio — é derivado do plano, sem toggle inventado.
- O caminho "com plano" usa fake da porta com um `RenderPlan` real; o caminho "sem plano" foi exercitado contra o Postgres real na rota.
