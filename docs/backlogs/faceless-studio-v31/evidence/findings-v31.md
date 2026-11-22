# Achados de comportamento real (não corrigidos)

Encontrados pela modernização dos testes de tela (F07.T01) e registrados em vez de "ajustar o
teste para passar". Cada um tem teste com `xfail(strict=True)`: quando o bug for corrigido, o
teste **falha** e obriga a remover a marca.

## FS31-A1 — Histórico de experimentos invisível no estado vazio

- **Arquivo:** `renderer/app/studio/api/panel_analytics.py` (renderização condicionada a
  `has_measurements`).
- **Sintoma:** `POST /studio/analytics/experiments` devolve `201`, mas a tela não mostra o
  experimento criado enquanto não há medições.
- **Impacto:** o operador cria uma variação e não a vê na tela; parece que nada foi salvo.
- **Teste:** `tests/test_analytics_page.py::test_experiment_registration_shows_history_and_refuses_platform_ab`.
- **Correção sugerida:** renderizar a seção de histórico sempre que houver experimentos,
  independentemente de medições.

## FS31-A2 — Seletor de canal é controle falso

- **Arquivo:** `renderer/app/studio/api/routes.py` (chama `render_analytics(view, month)` sem
  `projects`) e `panel_analytics.py` (`_filters_html` é código morto).
- **Sintoma:** o select de canal mostra 1 opção só; `?project=` funciona, mas não há UI.
- **Impacto:** viola o contrato de UX (controle sem função) e impede trocar de canal pela tela.
- **Teste:** `tests/test_analytics_page.py::test_channel_selector_lists_real_projects_and_switches`.
- **Correção sugerida:** passar os projetos reais para o render e ligar o parâmetro
  `project` do filtro ao `?project=` já suportado.

## FS31-A3 — `/studio/panel/producao` ainda na casca V2

- **Sintoma:** `aside.sidebar`, “Faceless Studio V2”, links de API Docs/n8n.
- **Impacto:** quebra de consistência visual e de navegação; achado do stream G.
- **Correção sugerida:** portar para `shell_v3.render_document`, como as demais telas.
