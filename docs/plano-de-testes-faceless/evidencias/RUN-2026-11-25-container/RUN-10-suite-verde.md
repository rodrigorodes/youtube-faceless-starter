# RUN-10 — suíte canônica verde após o WIP V4/V3 e os ajustes A2

- Data: 2026-11-25
- Base: HEAD `79e3585` (branch `main`, merge do WIP V4/V3), árvore dirty com os ajustes
  desta sessão.
- Ambiente: `scripts/test-container.sh` (Docker, Postgres 16 efêmero, ffmpeg com libass).
- Comando: `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q`.

## Resultado

- **4059 passed, 20 skipped, 0 failed** em 748,70 s (exit 0).
- Série completa: RUN-02 39 → RUN-04 32 → RUN-06 29 → RUN-07 25 → RUN-08 23 → RUN-10 0.
- O flake de TTS (`test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time`)
  passou nesta execução.
- A higiene de segredos passou após remover do índice o artefato de debug
  `tests/_debug_trend.py` (arquivo criado durante a investigação e commitado por engano no
  merge; não faz parte do produto).

## Ajustes A2 aplicados

- `tests/test_panel_page.py`: título "Tendências e ideias", cartões por vídeo, chips com
  `pill btnlike`, prévia "Prévia da versão", link `novo-video`, ausência de "+ Novo pilar"
  (o caminho é o diálogo de pilares), e o cartão de tendência com `query`/origem honesta.
- `tests/test_settings_sections.py`: marcadores de Produção (`budget`/roteamento de
  providers) e Conexões.
- `renderer/app/studio/application/panel.py`: `TrendItemView` passou a carregar `query`.
- `renderer/app/studio/api/panel_trends.py`: cartão mostra "Busca" quando a coleta veio de
  termo; diz "Região não informada" quando não há região; JS morto de `#btn-novo-pilar`
  removido.
- `renderer/app/studio/api/routes.py`: import não usado de `render_tendencias` removido.

## Leitura

- Nenhuma falha restante foi confirmada como regressão de produto.
- ACH-09 permanece como decisão de campanha (cobrir `publication_enabled=False`).
- O host macOS não é ambiente válido; os números acima são do container.
