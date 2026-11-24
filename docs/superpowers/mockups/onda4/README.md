# Onda 4 — mockups fiéis (evidência para validação)

- `index.html`: visão geral com as 5 telas (abra no navegador).
- `telas/*.html`: cada tela isolada, página completa.
- `gerador/`: scripts que renderizam as telas REAIS (`render_new_video_v3`, `render_video_workspace`)
  com dados de exemplo e injetam só os elementos novos.
  Regerar: `python3 gerador/build.py index.html` (requer `renderer/` no PYTHONPATH; ajustar caminhos em `base.py`).

Legenda: contorno laranja tracejado = NOVO; contorno azul tracejado = muda algo que já existe.
Os dados (canal, cenas, tomadas, trilha) são de exemplo.
