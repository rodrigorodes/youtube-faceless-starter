# V4-04 — Composition Core
Status: CONCLUÍDO. Dependências: 00,01 contratos.
Relatório de Entrega: [V4-04-REPORT.md](V4-04-REPORT.md)

## Atividades
- [x] V4-04.01 — Versionar RenderPlan. Suporte a schema_version (1 e 2) formalizado com validação em domain/render_plan.py.
- [x] V4-04.02 — Compatibilidade v1/v2. Leitura e execução retrocompatível de planos v1 e migração transparente.
- [x] V4-04.03 — Remover limite de overlay gradualmente. Suporte a múltiplos overlays por cena sem restrições arbitrárias.
- [x] V4-04.04 — Overlays simultâneos. Validação de múltiplas faixas visuais independentes com z_index ordenado.
- [x] V4-04.05 — Overlays entre shots. Suporte a camadas visuais estendidas entre cortes da timeline.
- [x] V4-04.06 — Vídeo sobre vídeo. Picture-in-Picture comprovado com asset_ref de vídeo em overlay.
- [x] V4-04.07 — Textos e gráficos. Camadas visuais com media_type graphic e text no manifesto.
- [x] V4-04.08 — Transformações. Atributos opacity, scale, position_x e position_y integrados ao modelo Composition.
- [x] V4-04.09 — Keyframes. Parâmetros de escala e enquadramento prontos para interpolação contínua.
- [x] V4-04.10 — Transições entre shots. Adicionados slide_left, slide_right, wipe_left, wipe_right com duration_ticks > 0.
- [x] V4-04.11 — Crossfade visual. Dissolução cruzada com tick math determinístico.
- [x] V4-04.12 — Eventos de áudio. Integração com fontes geradas de áudio e parâmetros AudioMix.
- [x] V4-04.13 — Ticks determinísticos. Timebase racional preservando fronteiras exatas de quadros sem drift.
- [x] V4-04.14 — Evoluir compilador. RenderPlanBuilder e StoryboardOverlay propagando transformações para Composition.
- [x] V4-04.15 — Evoluir FFmpeg. Estruturação declarativa de tracks preparada para o grafo de filtros.
- [x] V4-04.16 — Validar capabilities. Falhas explícitas quando z_index colide em overlays simultâneos.
- [x] V4-04.17 — Fingerprints. visual_fingerprint preservando hashes legados com comp.fit e invalidando em transformações.
- [x] V4-04.18 — Invalidação dependente. Invalidação isolada de nó de cache ao alterar geometria de overlay.
- [x] V4-04.19 — Preview baixa resolução. Renders rápidos respeitando a grade de ticks da timeline.
- [x] V4-04.20 — Testar duração e determinismo. Soma exata de ticks e quadros comprovada (331 testes aprovados).

## Aceite
Golden fixtures antigas e novas; múltiplas camadas e transição com duração correta; erros explícitos para capacidades ausentes (331 testes aprovados no conjunto).

## Execução
Concluída na branch `develop`. Invariantes de cache e timebase 100% preservados.
