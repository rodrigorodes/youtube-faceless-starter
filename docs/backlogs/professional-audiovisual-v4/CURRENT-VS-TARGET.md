# AS-IS vs TO-BE
Base da auditoria anterior: 352dfd7. Revalidar na V4-00.
| Evidência anterior (renderer/app/studio/) | Evolução |
|---|---|
| domain/provider.py: TEXT IMAGE VOICE RENDERER SEARCH | Expandir capacidades existentes |
| composition/providers.py: Piper, FFmpeg, Pexels, Pixabay, OpenCode | Adapters homologados incrementalmente |
| application/ports.py | Reutilizar portas |
| domain/render_plan.py: Timebase, Track, Scene, Shot, AudioMix, Transition | Versionar contrato existente |
| application/render_compiler.py: MAX_OVERLAYS_PER_SCENE=1 | Multilayer com validação |
| adapters/render_plan_compiler.py | Evoluir execução FFmpeg e crossfade |
| application/audio_director.py | Música contextual e eventos multitrack |
| domain/music.py | Não presumir CC0; licença comprovada |
| docs/reviews/2026-11-24-architecture-review.md | Revalidar riscos operacionais |
Relatórios anteriores não equivalem a testes executados nesta entrega. Não afirmar que um componente está ausente sem reconciliação.
