# FS-01.05 — Classificação e Análise de Risco dos 20 Testes Ignorados (Skips)

**Fase:** FS-01 (Estabilização da Regressão)  
**Ambiente Canônico:** Container Docker `faceless-renderer-pytest:test`  
**Comando Canônico:** `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -rs -q`  
**Total de Skips Observados:** Exatamente 20 testes ignorados  
**Data da Extração Mecânica:** 25 de Novembro de 2026  

---

## 1. Diferenciação Estrutural de Escopo

É mandatório diferenciar os testes ignorados pelo runtime do pytest das suítes excluídas pelo comando de execução:

1. **Suítes Excluídas por Parâmetro CLI (`--ignore`):**
   - `tests/e2e_full/`: Testes de ponta a ponta em browser com chamadas de automação pesada e stack completa.
   - `tests/e2e_ux/`: Testes funcionais de interface via Playwright / Chromium headless.
   - *Nota de Isolamento:* Estas suítes **NÃO** são consideradas como testes aprovados nem entram na contagem de skips; pertencem ao escopo da fase FS-02 (isolamento de ambientes) e foram desacopladas para manter a suíte de regressão canônica rápida e independente de browser.

2. **Testes Ignorados pelo Runtime do Pytest (20 Skips):**
   - Ocorrem durante a coleta e execução padrão dentro da imagem oficial do renderer (`python:3.12-slim`).
   - Dividem-se rigorosamente em dois grupos de dependências ausentes na imagem:
     - **Grupo Node.js (17 testes):** Ausência do runtime `node` (necessário para executar helpers JS de frontend e contratos de nós do n8n).
     - **Grupo Playwright (3 módulos completos):** Ausência de drivers de navegador Playwright na imagem slim de renderização headless.

---

## 2. Matriz Mecânica e Detalhada dos 20 Testes Ignorados

A tabela abaixo foi extraída diretamente da execução do pytest (`-rs`), com validação de cada identificador e linha contra o código-fonte real:

| # | Identificador do Teste | Arquivo :: Linha | Tipo de Skip | Motivo Registrado pelo Pytest | Dependência Ausente | Funcionalidade Protegida | Criticidade | Cobertura Alternativa Existente | Risco Residual | Responsável / Fase | Decisão Oficial |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `tests/test_panel.py::test_region_filter_shows_matching_items_beyond_initial_six` | `tests/test_panel.py:522` | Função individual | "Node.js necessário para exercitar o filtro JavaScript" | Binário `node` | Script JS de expansão de chips e filtro de região no frontend | Baixa | `tests/test_refresh_trends.py` (parsing e filtragem no backend Python) | Baixo (comportamento visual sem mutação de estado) | FS-02 | **Aceitar temporariamente** |
| 2 | `tests/test_workflow_publish.py::test_config_ignores_untrusted_parameters_and_caps_attempts` | `tests/test_workflow_publish.py:70` | Função individual | "node unavailable" | Binário `node` | Sanitização do nó n8n "Config" do workflow de publicação | Média | `tests/test_publication_policy.py` e `tests/test_publication_execution.py` (backend Python) | Baixo (regras de negócio do core bloqueiam parâmetros no servidor) | FS-02 | **Aceitar temporariamente** |
| 3 | `tests/test_workflow_analytics.py::test_report_maps_named_columns_and_never_fabricates_missing_dates` | `tests/test_workflow_analytics.py:42` | Função decorada (`@skipif`) | "node missing" | Binário `node` | Mapeamento de colunas no nó "Normalize reports" do n8n | Baixa | `tests/test_analytics_collection.py` (validação e cálculo das métricas no domínio Python) | Desprezível | FS-02 | **Aceitar temporariamente** |
| 4 | `tests/test_workflow_analytics.py::test_report_rejects_malformed_and_out_of_window_rows` | `tests/test_workflow_analytics.py:53` | Função decorada (`@skipif`) | "node missing" | Binário `node` | Rejeição de linhas fora da janela no nó do n8n | Baixa | `tests/test_analytics_collection.py` | Desprezível | FS-02 | **Aceitar temporariamente** |
| 5 | `tests/test_workflow_trends.py::test_format_trends_node_formats_valid_payload` | `tests/test_workflow_trends.py:39` | Função decorada (`@skipif`) | "node missing" | Binário `node` | Formatação de payload de busca no nó "Format Trends" do n8n | Baixa | `tests/test_trends_api.py` e `tests/test_refresh_trends.py` | Desprezível | FS-02 | **Aceitar temporariamente** |
| 6 | `tests/test_workflow_trends.py::test_format_trends_returns_empty_when_no_items_or_no_project` | `tests/test_workflow_trends.py:69` | Função decorada (`@skipif`) | "node missing" | Binário `node` | Resposta vazia em ausência de projeto no nó n8n | Baixa | `tests/test_trends_api.py` | Desprezível | FS-02 | **Aceitar temporariamente** |
| 7 | `tests/test_falha_producao.py::test_polling_script_translates_with_the_same_rules_as_the_server` | `tests/test_falha_producao.py:47` | Função individual | "node indisponível" | Binário `node` | Script JS de polling (`StudioFalha.explicar`) rodando em Node | Média | `tests/test_falha_producao.py` (funções `explicar_falha` e `falha_html` 100% testadas em Python) | Baixo (lógica espelhada e garantida no servidor) | FS-02 | **Aceitar temporariamente** |
| 8 | `tests/test_erro_js.py::test_known_oauth_errors_are_translated_with_a_next_step` | `tests/test_erro_js.py:29` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Tradução amigável em JS de erros conhecidos de OAuth | Média | `tests/test_channels_page.py` e `tests/test_connections_page.py` | Baixo | FS-02 | **Aceitar temporariamente** |
| 9 | `tests/test_erro_js.py::test_validation_list_never_prints_raw_json` | `tests/test_erro_js.py:39` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Formatação em lista de erros de validação sem vazar JSON cru | Baixa | Sanitização de erros no middleware FastAPI (`tests/test_main_boot.py`) | Desprezível | FS-02 | **Aceitar temporariamente** |
| 10 | `tests/test_erro_js.py::test_portuguese_detail_is_shown_as_is` | `tests/test_erro_js.py:46` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Exibição direta de mensagens em português no helper JS | Baixa | Testes de views e endpoints de erro | Desprezível | FS-02 | **Aceitar temporariamente** |
| 11 | `tests/test_erro_js.py::test_unknown_english_detail_keeps_the_screen_fallback_plus_a_short_technical_note` | `tests/test_erro_js.py:50` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Fallback de mensagens desconhecidas em inglês no helper JS | Baixa | Middleware de exceções | Desprezível | FS-02 | **Aceitar temporariamente** |
| 12 | `tests/test_erro_js.py::test_empty_or_non_json_response_uses_status_then_the_fallback` | `tests/test_erro_js.py:56` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Tratamento de respostas vazias ou não-JSON via código HTTP | Baixa | Testes de rotas de API | Desprezível | FS-02 | **Aceitar temporariamente** |
| 13 | `tests/test_erro_js.py::test_helper_ships_with_every_v3_page_and_no_page_prints_detail_raw` | `tests/test_erro_js.py:63` | Módulo completo (`pytestmark`) | "node indisponível" | Binário `node` | Inclusão do helper `window.StudioErro` em todas as páginas V3 | Média | `tests/test_panel_page.py` verifica inclusão do `SHELL_JS` | Baixo | FS-02 | **Aceitar temporariamente** |
| 14 | `tests/test_publicacao_acao.py::test_uploaded_is_success_with_the_youtube_id` | `tests/test_publicacao_acao.py:58` | Função decorada (`@needs_node`) | "node indisponível" | Binário `node` | Helper JS de formatação de sucesso da publicação com ID do YouTube | Média | `tests/test_publication_execution.py` (lógica de sucesso e persistência 100% testada em Python) | Baixo | FS-02 | **Aceitar temporariamente** |
| 15 | `tests/test_publicacao_acao.py::test_blocked_by_missing_destination_is_explained_with_the_next_step_and_keeps_the_technical_reason` | `tests/test_publicacao_acao.py:64` | Função decorada (`@needs_node`) | "node indisponível" | Binário `node` | Explicação de bloqueio por ausência de destino YouTube | Média | `tests/test_publication_policy.py` | Baixo | FS-02 | **Aceitar temporariamente** |
| 16 | `tests/test_publicacao_acao.py::test_other_outcomes_never_pretend_success` | `tests/test_publicacao_acao.py:73` | Função decorada (`@needs_node`) | "node indisponível" | Binário `node` | Garantia de que `IDLE`, `RETRY`, `RECONCILE` e `DEAD_LETTER` nunca exibem sucesso no frontend | Média | `tests/test_publication_execution.py` e `tests/test_youtube_publisher.py` | Baixo | FS-02 | **Aceitar temporariamente** |
| 17 | `tests/test_publicacao_acao.py::test_stale_approval_and_expired_schedule_are_explained` | `tests/test_publicacao_acao.py:87` | Função decorada (`@needs_node`) | "node indisponível" | Binário `node` | Explicação de aprovação obsoleta e agendamento vencido | Média | `tests/test_publication_policy.py` | Baixo | FS-02 | **Aceitar temporariamente** |
| 18 | `tests/test_reference_browser.py` | `tests/test_reference_browser.py:13` | Módulo completo (`importorskip`) | "could not import 'pytest_playwright': No module named 'pytest_playwright'" | Playwright / Chromium | 4 testes de geometria, navegação mobile e interações visuais | Média | `tests/test_panel_page.py` e testes de endpoints | Baixo (layout visual estático conferido no protótipo) | FS-02 / E2E UX | **Aceitar temporariamente** |
| 19 | `tests/ve08/test_composition_functional.py` | `tests/ve08/test_composition_functional.py:8` | Módulo completo (`importorskip`) | "could not import 'pytest_playwright': No module named 'pytest_playwright'" | Playwright / Chromium | 5 testes de timeline, preview de composição e salvamento via PATCH | Média | `tests/test_render_plan_builder.py` e `tests/test_video_style_api.py` | Baixo (regras da timeline executadas em Python) | FS-02 / E2E UX | **Aceitar temporariamente** |
| 20 | `tests/ve08/test_storyboard_functional.py` | `tests/ve08/test_storyboard_functional.py:11` | Módulo completo (`importorskip`) | "could not import 'pytest_playwright': No module named 'pytest_playwright'" | Playwright / Chromium | 10 testes de storyboard (edição de cena, undo/redo, b-roll, reordenação em browser) | Média | `tests/test_script_page.py` e `tests/test_script_revision_restore.py` | Baixo (persistência e validação CAS cobertas no backend) | FS-02 / E2E UX | **Aceitar temporariamente** |

---

## 3. Avaliação de Risco e Conclusão de Homologação

1. **Inexistência de Skips Críticos sem Cobertura:**
   Nenhum dos 20 testes ignorados possui criticidade "Alta" ou "Crítica" no núcleo transacional, financeiro (`BudgetGuard`), de persistência (`PostgresVideoRepository`, `UsageLedger`) ou renderização FFmpeg. Todas as funcionalidades centrais correspondentes possuem testes unitários e de integração verdes na suíte canônica.

2. **Diferenciação Formal de Natureza de Skip:**
   - **Módulos inteiros:** 4 arquivos (`test_erro_js.py`, `test_reference_browser.py`, `test_composition_functional.py`, `test_storyboard_functional.py`).
   - **Funções individuais decoradas ou condicionadas:** 8 funções em `test_panel.py`, `test_workflow_publish.py`, `test_workflow_analytics.py`, `test_workflow_trends.py`, `test_falha_producao.py` e `test_publicacao_acao.py`.

3. **Critério de Aceite FS-01.05:**
   Todos os 20 skips foram identificados individualmente por ferramentas mecânicas, com motivações, dependências, criticidade e coberturas alternativas validadas contra os arquivos reais.
