# RUN-04 — suíte canônica após a triagem (container)

- Data: 2026-11-25
- HEAD: `f4a9244` (branch `main`), árvore dirty (WIP UX V4/V3, contratos/DDL regenerados,
  testes ajustados e este plano).
- Runner: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero,
  ffmpeg+libass).
- Comando:
  ```
  scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q --tb=line
  ```
- Resultado real (exit 1):
  - **32 failed**
  - **4026 passed**
  - **20 skipped**
  - 691.29 s
- Comparação com RUN-02: 39 failed → 32 failed. As 7 falhas removidas são os grupos B
  (3), C (2) e D (2), corrigidos como artefatos de teste desatualizados. O grupo A
  permanece com 32 falhas de drift de UI/casca.

## Falhas restantes (todas do grupo A)

As 32 falhas são de teste desatualizado em relação ao WIP V4/V3. Nenhuma foi confirmada
como regressão de produto nesta execução. A lista completa e o motivo por teste estão em
`RUN-03-triage.md` (mapa das falhas do grupo A).

Arquivos com falha: `test_analytics_page.py` (2), `test_channels_page.py` (3),
`test_connections_page.py` (1), `test_panel_page.py` (15),
`test_panel_production_page.py` (3), `test_script_page.py` (1),
`test_settings_sections.py` (3), `test_styles_page.py` (1),
`test_video_style_api.py` (3).

## O que este resultado prova

- Os grupos B, C e D foram resolvidos sem mudar o produto: contratos/DDL regenerados no
  container, lista de migrações atualizada e fixture de produção alinhada ao
  `auto_research`.
- O grupo A não foi alterado: continua sendo drift de teste do WIP V4/V3.

## O que este resultado não prova

- Não prova que o grupo A é bug de produto: a árvore está dirty e o WIP de UI pode estar
  incompleto.
- Não prova cobertura de fornecedores externos, publicação real ou avaliação humana.
- Nenhum cenário do plano foi promovido a PASS por esta execução.
