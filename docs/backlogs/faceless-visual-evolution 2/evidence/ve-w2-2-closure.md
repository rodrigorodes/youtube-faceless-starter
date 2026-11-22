# W2.2 (VE-02) — compositor FFmpeg do overlay de imagem

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado em `ve-w2-2-compositor` e **portado**.
**Testes:** container, tags `faceless-renderer:w43`.

## Entregue
- `application/render_compiler.py`: grafo `base → overlays → selo → legendas → fade`; `_overlay_filter` com `enable` na janela semiaberta relativa ao segmento base; `cover`/`contain`; entradas de overlay depois das legendas.
- `adapters/render_plan_ffmpeg.py`: removida a recusa de overlay (I14 da VE-01); o executor só roda o comando compilado.
- `tests/test_render_plan_overlay.py` (novo, 9 testes) + `tests/test_render_plan_executor.py` atualizado.

## Evidência (checkout principal)
| Comando | Resultado |
|---|---|
| `test_render_plan_overlay + test_render_plan_executor + test_render_compiler + test_architecture + test_render_plan_builder + test_render_adapters + test_render_golden + test_visual_style_domain + test_channel_style_page + test_quality_overlay` | **236 passed** em 45.81 s |

## Lacunas
- `MAX_OVERLAYS_PER_SCENE = 1` mantido (limite de fase); ordem por `z_index` implementada mas multi-camada não exercitada ponta-a-ponta.
- `-loop 1` pressupõe overlay de imagem; overlay de vídeo futuro exigiria `trim`/`setpts`.
- Doc da VE-01 (I14) ficou desatualizada (recusa superada pela VE-02); não editada.
