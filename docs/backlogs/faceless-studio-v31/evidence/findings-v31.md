# Achados de comportamento real (não corrigidos)

Encontrados pela modernização dos testes de tela (F07.T01) e registrados em vez de "ajustar o
teste para passar". Os três foram corrigidos com teste de regressão (as marcas `xfail` foram
removidas e as assertions agora descrevem o contrato V3).

## FS31-A1 — Histórico de experimentos invisível no estado vazio

- **Arquivo:** `renderer/app/studio/api/panel_analytics.py` (renderização condicionada a
  `has_measurements`).
- **Sintoma:** `POST /studio/analytics/experiments` devolve `201`, mas a tela não mostra o
  experimento criado enquanto não há medições.
- **Impacto:** o operador cria uma variação e não a vê na tela; parece que nada foi salvo.
- **Teste:** `tests/test_analytics_page.py::test_experiment_registration_shows_history_and_refuses_platform_ab`.
- **Correção (feita):** o histórico é renderizado sempre que houver experimentos, mesmo sem
  medições; métricas/insights continuam dependendo de medição. Teste:
  `tests/test_analytics_page.py::test_experiment_registration_shows_history_and_refuses_platform_ab`.

## FS31-A2 — Seletor de canal é controle falso

- **Arquivo:** `renderer/app/studio/api/routes.py` (chama `render_analytics(view, month)` sem
  `projects`) e `panel_analytics.py` (`_filters_html` é código morto).
- **Sintoma:** o select de canal mostra 1 opção só; `?project=` funciona, mas não há UI.
- **Impacto:** viola o contrato de UX (controle sem função) e impede trocar de canal pela tela.
- **Teste:** `tests/test_analytics_page.py::test_channel_selector_lists_real_projects_and_switches`.
- **Correção (feita):** o render recebe os projetos reais e o seletor `#analytics-project`
  troca `?project=`; o vazio distingue "canal sem vídeo" de "sem medição no período". Teste:
  `tests/test_analytics_page.py::test_channel_selector_lists_real_projects_and_switches`.

## FS31-A3 — `/studio/panel/producao` ainda na casca V2

- **Sintoma:** `aside.sidebar`, “Faceless Studio V2”, links de API Docs/n8n.
- **Impacto:** quebra de consistência visual e de navegação; achado do stream G.
- **Correção (feita):** `render_production_page` desenha a tela na casca V3 (`id="pagina-producao"`),
  com vídeo real, situação e custo rotulado; a casca V2 não é mais emitida. Testes:
  `tests/test_panel_production_page.py::test_production_page_uses_the_v3_shell_and_real_data` e
  `::test_production_page_empty_state_is_explicit`.
