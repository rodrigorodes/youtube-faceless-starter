# W3.2 (VE-04) — presets, legenda, motion e `Shot.transition`

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado em `ve-w3-2-presets` e **portado**.
**Testes:** container, tags `faceless-renderer:w43`.

## Entregue
- `application/render_compiler.py`: `_fade_filter(transition, ...)` — `Shot.transition` (`fade` de `n` ticks) define o fade-out do segmento; ausente/`none` mantém o fade legado byte a byte (paridade D4); fade maior que o shot é `CompileError` antes do FFmpeg.
- `domain/visual_style.py`: `APPLIED_GROUPS` (motion/music/caption/palette/voice) vs `LOADED_ONLY_GROUPS` (transition/extra); `PRESETS` (`documentario`, `noticia`, `curiosidades`) só com grupos aplicáveis; `preset_params` validado por `clean_params`.
- Testes: `test_visual_style_domain`, `test_render_compiler`, `test_render_cache`, `test_render_plan_executor`, `test_channel_style_page`.

## Evidência (checkout principal)
| Comando | Resultado |
|---|---|
| conjunto de render/style/QA acima | **236 passed** em 45.81 s |

## Lacunas
- A **transição de estilo** continua sem efeito (nada a converte em `Shot.transition`); por isso `transition` segue em `LOADED_ONLY_GROUPS` e a UI rotula "não aplicado".
- Presets sem seletor na Biblioteca de estilos (catálogo puro consumível, sem UI ainda).
