# FS-01.05 — Classificação e Análise de Risco dos 20 Testes Ignorados (Skips)

**Fase:** FS-01 (Estabilização da Regressão)  
**Ambiente Canônico:** Container Docker `faceless-renderer-pytest:test`  
**Comando Canônico:** `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -rs -q`  
**Total de Skips Observados:** 20 testes ignorados  
**Data:** 25 de Novembro de 2026  

---

## 1. Diferenciação Estrutural de Escopo

É mandatório diferenciar os testes ignorados pelo runtime do pytest das suítes excluídas pelo comando:

1. **Suítes Excluídas por Parâmetro CLI (`--ignore`):**
   - `tests/e2e_full/`: Testes de ponta a ponta em browser com chamadas de automação pesada e stack completa.
   - `tests/e2e_ux/`: Testes funcionais de interface via Playwright / Chromium headless.
   - *Nota:* Estas suítes **NÃO** são consideradas como testes aprovados nem entram na contagem de skips; pertencem ao escopo da fase FS-02 (isolamento de ambientes) e foram desacopladas para manter a suíte de regressão canônica rápida e independente de browser.

2. **Testes Ignorados dentro da Suíte Canônica (20 Skips):**
   - Ocorrem durante a coleta e execução padrão dentro da imagem oficial do renderer (`python:3.12-slim`).
   - Dividem-se em dois grupos bem delimitados de dependências ausentes no contêiner:
     - **Grupo 1 (7 testes):** Ausência do runtime `node` (scripts JS de nós do n8n / filtros de frontend).
     - **Grupo 2 (13 testes):** Ausência de drivers de navegador Playwright na imagem slim de renderização headless.

---

## 2. Matriz Granular dos 20 Testes Ignorados

| # | Identificador Completo | Arquivo | Motivo do Skip | Dependência Ausente | Funcionalidade Protegida | Criticidade | Cobertura Alternativa Existente | Risco Residual | Responsável / Fase | Decisão Oficial |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `tests/test_panel.py::test_javascript_filter_is_executable_by_node` | `tests/test_panel.py` | "Node.js necessário para exercitar o filtro JavaScript" | Binário `node` | Script JS embutido de filtro de tendências no painel | Baixa | Testes unitários do parser em Python (`test_refresh_trends.py`) e asserções de contrato HTML | Baixo: script estático simples sem mutação de estado | FS-02 / CI-local | **Aceitar temporariamente** (executar apenas em runner com Node) |
| 2 | `tests/test_workflow_publish.py::test_publish_workflow_contract` | `tests/test_workflow_publish.py` | "node unavailable" | Binário `node` | Execução simulada do nó de publicação do n8n | Média | `test_publication_policy.py` e `test_publication_execution.py` (cobrem exaustivamente claim, token, upload e falhas em Python) | Baixo: lógica central de negócio reside no renderer Python | FS-02 | **Aceitar temporariamente** |
| 3 | `tests/test_workflow_analytics.py::test_analytics_daily_node_scripts_execute` | `tests/test_workflow_analytics.py` | "node missing" | Binário `node` | Scripts JS internos do workflow diário de métricas do n8n | Baixa | `test_analytics_collection.py` (cobertura integral da coleta e agregações em Python) | Desprezível: regras analíticas implementadas no backend | FS-02 | **Aceitar temporariamente** |
| 4 | `tests/test_workflow_analytics.py::test_analytics_daily_workflow_contract` | `tests/test_workflow_analytics.py` | "node missing" | Binário `node` | Contrato JSON/IO do nó de workflow n8n | Baixa | `test_schema_docs.py` e `test_contracts_snapshot.py` | Baixo | FS-02 | **Aceitar temporariamente** |
| 5 | `tests/test_workflow_trends.py::test_trends_daily_node_scripts_execute` | `tests/test_workflow_trends.py` | "node missing" | Binário `node` | Script de normalização de termos de tendências no n8n | Baixa | `test_trends_api.py` e `test_refresh_trends.py` cobrem a normalização no domínio | Desprezível | FS-02 | **Aceitar temporariamente** |
| 6 | `tests/test_workflow_trends.py::test_trends_daily_workflow_contract` | `tests/test_workflow_trends.py` | "node missing" | Binário `node` | Validação de schema do fluxo de tendências diárias | Baixa | `contracts/v1/trend.schema.json` e testes de API | Desprezível | FS-02 | **Aceitar temporariamente** |
| 7 | `tests/test_falha_producao.py::test_n8n_failure_handler_contract` | `tests/test_falha_producao.py` | "node indisponível" | Binário `node` | Tratamento de webhook de erro no nó do n8n | Média | `test_lease_recovery_concurrency.py` e recuperação no `ProductionWorker` | Baixo: recuperação e fencing são garantidos no Postgres pelo renderer | FS-02 | **Aceitar temporariamente** |
| 8 | `tests/test_reference_browser.py::test_shell_matches_reference_geometry_and_navigation` | `tests/test_reference_browser.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Fidelidade geométrica de layout da casca contra referência V3 | Baixa | `tests/test_panel_page.py` valida DOM, estrutura de tags e classes CSS | Baixo: visual validado manualmente no protótipo aprovado | FS-02 / E2E UX | **Aceitar temporariamente** (mover para suíte UX) |
| 9 | `tests/test_reference_browser.py::test_mobile_navigation_wraps_like_reference` | `tests/test_reference_browser.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Responsividade mobile da barra de navegação | Baixa | `test_panel_declares_viewport_and_responsive_media_query` (valida breakpoints CSS) | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 10 | `tests/test_reference_browser.py::test_new_video_progressive_disclosure_preserves_script_and_updates_summary` | `tests/test_reference_browser.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Interatividade de disclosure progressivo na tela de novo vídeo | Média | `tests/test_panel_new_video_active.py` e `test_panel_production_page.py` | Baixo: estado persistido via API é verificado no backend | FS-02 / E2E UX | **Aceitar temporariamente** |
| 11 | `tests/test_reference_browser.py::test_channel_page_submits_full_transaction_and_keeps_draft_on_failure` | `tests/test_reference_browser.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Comportamento de retenção de rascunho em formulário do canal | Média | `tests/test_channel_creation_use_case.py` e `tests/test_channel_api.py` | Baixo: atomicidade garantida na camada de use case e banco | FS-02 / E2E UX | **Aceitar temporariamente** |
| 12 | `tests/ve08/test_composition_functional.py::test_composition_has_prototype_structure_and_real_timeline` | `tests/ve08/test_composition_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Renderização da timeline no storyboard com browser | Média | `tests/test_render_plan_builder.py` e testes de API de composição | Baixo: dados da timeline compilados pelo motor Pure Python | FS-02 / E2E UX | **Aceitar temporariamente** |
| 13 | `tests/ve08/test_composition_functional.py::test_composition_preview_follows_parameters_before_saving` | `tests/ve08/test_composition_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Prévia dinâmica de parâmetros no frontend | Baixa | `tests/test_preview.py` e testes de contratos RenderPlan V2 | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 14 | `tests/ve08/test_composition_functional.py::test_composition_saves_through_the_existing_style_patch_endpoint` | `tests/ve08/test_composition_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Salvamento de composição via PATCH em browser | Média | `tests/test_video_style_api.py` (valida endpoints e mutações completas) | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 15 | `tests/ve08/test_composition_functional.py::test_composition_without_scenes_is_honest` | `tests/ve08/test_composition_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Estado honesto da composição vazia no browser | Baixa | `tests/test_video_download_and_audiovisual_summary.py` | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 16 | `tests/ve08/test_composition_functional.py::test_composition_has_no_horizontal_overflow_on_small_screens` | `tests/ve08/test_composition_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Ausência de transbordamento horizontal em telas pequenas | Baixa | `test_panel_declares_viewport_and_responsive_media_query` | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 17 | `tests/ve08/test_storyboard_functional.py::test_all_scene_cards_are_on_the_bench_in_script_order` | `tests/ve08/test_storyboard_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Ordenação e visualização dos cards de cena em bancada | Média | `tests/test_panel_scene_multimedia.py` e `tests/test_script_page.py` | Baixo: ordem das cenas garantida pelo modelo de dados | FS-02 / E2E UX | **Aceitar temporariamente** |
| 18 | `tests/ve08/test_storyboard_functional.py::test_each_scene_edits_independently_and_persists` | `tests/ve08/test_storyboard_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Edição isolada de texto e mídia por cena | Média | `tests/test_script_page.py` (cobre adição, remoção, reordenação e persistência CAS) | Baixo: persistência e integridade cobertas no backend | FS-02 / E2E UX | **Aceitar temporariamente** |
| 19 | `tests/ve08/test_storyboard_functional.py::test_undo_redo_text_media_and_redo_is_invalidated_by_new_edit` | `tests/ve08/test_storyboard_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Mecanismo de Desfazer/Refazer na interface de storyboard | Média | `tests/test_script_revision_restore.py` (snapshots e revisões duráveis no Postgres) | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |
| 20 | `tests/ve08/test_storyboard_functional.py::test_broll_toggle_and_note_are_per_scene_and_persist` | `tests/ve08/test_storyboard_functional.py` | "could not import 'pytest_playwright'" | Playwright / Chromium | Toggle de B-Roll e notas por cena no frontend | Baixa | `tests/test_scene_assets_repo.py` e testes de DDL | Baixo | FS-02 / E2E UX | **Aceitar temporariamente** |

---

## 3. Avaliação de Risco e Conclusão de Homologação

1. **Inexistência de Skips Críticos sem Cobertura:**
   Nenhum dos 20 testes ignorados possui criticidade "Alta" ou "Crítica" no núcleo transacional, financeiro (`BudgetGuard`), de persistência (`PostgresVideoRepository`, `UsageLedger`) ou renderização FFmpeg. Todas as funcionalidades centrais correspondentes possuem testes unitários e de integração verdes na suíte canônica.

2. **Decisão por Categoria:**
   - **Node.js (7 testes):** Aceitar temporariamente. Os nós do n8n operam como orquestradores externos em ambiente operacional, cujos contratos JSON já estão validados por schemas.
   - **Playwright (13 testes):** Aceitar temporariamente na suíte canônica headless. Estes testes devem ser agrupados formalmente na suíte de E2E UX na fase FS-02, executados em ambiente dedicado com navegadores instalados.

3. **Critério de Aceite FS-01.05:**
   Todos os 20 skips foram identificados individualmente, com motivações, dependências, criticidade e coberturas alternativas explicitamente mapeadas. Não há risco residual que bloqueie a homologação da suíte canônica na FS-01.
