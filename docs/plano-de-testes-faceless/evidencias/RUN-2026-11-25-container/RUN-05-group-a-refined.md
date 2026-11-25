# RUN-05 — triagem refinada do grupo A (32 falhas)

- Data: 2026-11-25 (execução local, host macOS com Docker).
- Base: HEAD `f4a9244` (branch `main`), árvore dirty (38 entradas no momento da execução).
- Ambiente: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero, ffmpeg com libass).
- Comando: `scripts/test-container.sh tests/test_panel_page.py tests/test_settings_sections.py
  tests/test_channels_page.py tests/test_video_style_api.py tests/test_analytics_page.py
  tests/test_panel_production_page.py tests/test_script_page.py tests/test_styles_page.py
  tests/test_connections_page.py -q --tb=short`.
- Resultado: **32 failed, 165 passed** (85,6 s, exit 1).
- Resultado após as correções de A1 e A4 (mesmo comando, mesmo conjunto de arquivos):
  **29 failed, 168 passed** (87,6 s, exit 1). Por arquivo: `test_panel_page.py` 15,
  `test_settings_sections.py` 3, `test_channels_page.py` 3, `test_video_style_api.py` 3,
  `test_analytics_page.py` 1, `test_panel_production_page.py` 1, `test_script_page.py` 1,
  `test_styles_page.py` 1, `test_connections_page.py` 1.

Este documento refina a classificação do grupo A da RUN-03/RUN-04. O grupo A não é
homogêneo: parte são defeitos de teste (asserção em markup exato), parte é texto/markup
que mudou com o WIP V4/V3, parte é mudança funcional que precisa de decisão de produto e
parte é atraso de teste em relação a comportamento **já commitado** (não é WIP).

## Resumo por subclasse

| Subclasse | Falhas | Natureza | Ação |
|---|---|---|---|
| A1. Asserção mais estrita que o HTML atual | 4 | Defeito de teste | **Corrigido**; 1 falha resolvida, 3 seguem em A2 |
| A2. Texto/markup da UI mudou (WIP V4/V3) | 24 | Teste desatualizado | Atualizar junto com a aprovação do WIP |
| A3. Mudança funcional com decisão de produto pendente | 5 | Achado de produto | Registrar como ACH-04..ACH-08 e decidir |
| A4. Comportamento já commitado que os testes não acompanharam | 2 | Teste desatualizado (não é WIP) | **Corrigido** na fixture |

Total após as correções de A1 e A4: **29 falhas** (24 de A2 + 5 de A3).

## A1 — asserção mais estrita que o HTML atual (4 falhas)

A casca V4 renderiza `<aside class="side" aria-label="Menu principal">`; a asserção antiga
procura o tag exato `<aside class="side">`. O cartão de tendência passou a
`<div class="card cartao-tendencia">`; a asserção procura `class="cartao-tendencia"`.

| Teste | Asserção | HTML atual |
|---|---|---|
| `tests/test_panel_page.py::test_preview_page_has_unified_sidebar_layout` | `<aside class="side">` | `<aside class="side" aria-label="Menu principal">` |
| `tests/test_panel_page.py::test_panel_trends_lists_every_trend_with_an_honest_count` | `class="cartao-tendencia"` | `class="card cartao-tendencia"` |
| `tests/test_analytics_page.py::test_page_is_reached_through_the_approved_shell` | `<aside class="side">` | `<aside class="side" aria-label="Menu principal">` |
| `tests/test_script_page.py::test_roteiro_page_uses_the_shared_shell` | `<aside class="side">` | `<aside class="side" aria-label="Menu principal">` |

Correção aplicada (só no teste): as cinco asserções foram afrouxadas — `<aside class="side">`
→ `<aside class="side"` e `class="cartao-tendencia"` → `class="card cartao-tendencia"`.
Nenhum código de produto foi tocado. Efeito: uma falha do grupo A1 ficou verde
(`test_page_is_reached_through_the_approved_shell`); as outras três continuam falhando
**em asserções posteriores**, que são A2 — o afrouxamento não bastava porque o teste tem
mais de uma expectativa desatualizada (ver A2 abaixo).

## A2 — texto/markup da UI mudou com o WIP V4/V3 (20 falhas)

| Teste | Esperado | Atual |
|---|---|---|
| `test_panel_page.py::test_panel_page_empty_state` | "Nenhum vídeo ainda" | "Primeiros passos do canal" (`panel_home.py:74`) |
| `test_panel_page.py::test_panel_empty_production_state_is_explicit_without_fake_progress` | "Nenhum vídeo ainda" | idem |
| `test_panel_page.py::test_panel_page_renders_trending_topics_block` | "Tendências</h1>" | "Tendências e ideias" |
| `test_panel_page.py::test_panel_page_renders_category_pills_and_management_modal` | ">Todas</a>" | chip "Todos" |
| `test_panel_page.py::test_panel_page_has_loading_spinner_and_region_filters` | ">Todas</a>" | chip "Todos" |
| `test_panel_page.py::test_panel_renders_youtube_themed_cards_and_video_links` | "Criar vídeo deste tema" | "Criar com esta ideia" |
| `test_panel_page.py::test_panel_uses_the_single_shell_palette_and_preview_stays_consistent` | `color-scheme: light dark` | a casca V4 fixa o esquema escuro |
| `test_panel_page.py::test_panel_renders_production_board_and_modern_video_cards` | `aria-label="Abrir o vídeo {título}"` | rótulo de ação do cartão mudou (`panel_home.py:62-65`) |
| `test_panel_page.py::test_panel_shell_preserves_sections_and_trend_filter_contract` | `<a class="chip-filtro" href="...?filtro=todas...">` | chip do filtro mudou de rótulo/URL |
| `test_panel_page.py::test_panel_declares_viewport_and_responsive_media_query` | `@media (max-width: 820px)` | breakpoint 1000 px |
| `test_panel_page.py::test_panel_ia01_producao_and_tendencias_are_isolated_from_the_home` | `href="/studio/panel/producao..."` | link da nav mudou |
| `test_panel_page.py::test_panel_cost_note_labels_four_cost_categories` | `<p class="nota-custo">` | nota virou `<span class="sub">` no rodapé da casca; as quatro categorias continuam no texto (`cost_summary_text`) |
| `test_settings_sections.py::test_the_global_menu_lists_the_prototype_items_and_the_library` | `['Início', ...]` | `['⌂Início', ...]` (glifo na nav) |
| `test_settings_sections.py::test_the_settings_menu_has_the_seven_prototype_sections_with_the_active_channel` | 7 seções | 4 seções (Canais, Marca & Editorial, Produção & Orçamento, Conexões & Equipe) |
| `test_channels_page.py::test_settings_menu_matches_the_prototype_and_keeps_the_active_channel` | idem | idem |
| `test_channels_page.py::test_channels_page_uses_the_approved_shell` | `['Início', ...]` | `['⌂ Início', ...]` |
| `test_styles_page.py::test_styles_page_marks_biblioteca_active_and_no_dead_configuracoes` | `['Início', ...]` | `['⌂ Início', ...]` |
| `test_connections_page.py::test_connections_page_menu_has_conexoes_active_in_gestao` | `['Início', ...]` | `['⌂ Início', ...]` |
| `test_video_style_api.py::test_settings_area_links_to_the_seven_groups` | `/configuracoes/canais` → 302 | `/configuracoes/canais` renderiza a lista de canais (200) |
| `test_analytics_page.py::test_channel_selector_lists_real_projects_and_switches` | `id="analytics-project"` | seletor global da casca (`#canal-ativo`) |
| `test_panel_production_page.py::test_wizard_page_renders_real_channel_and_honest_fields` | "Predefinição do canal" | bloco ausente na tela V3 (ACH-08) |
| `test_panel_page.py::test_preview_page_has_unified_sidebar_layout` | "Faceless Studio" + "ESTÚDIO DO CANAL" | a prévia não renderiza mais o eyebrow "ESTÚDIO DO CANAL" (o Início renderiza, em `panel_home.py:373`) |
| `test_script_page.py::test_roteiro_page_uses_the_shared_shell` | "Faceless Studio" + "ESTÚDIO DO CANAL" | mesma mudança de cabeçalho na página de Roteiro |
| `test_panel_page.py::test_panel_trends_lists_every_trend_with_an_honest_count` | ">Todas</a>" | chip "Todos" (a asserção de cartão já passou com o ajuste de A1) |

Observação: no caso da nota de custo, o produto preserva a intenção (quatro categorias
rotuladas, sem somar real com estimado); só o seletor mudou. Já o bloco "Predefinição do
canal" desapareceu de fato da tela de novo vídeo — está registrado como ACH-08.

## A3 — mudança funcional com decisão de produto pendente (6 falhas)

| Teste | O que mudou | Achado |
|---|---|---|
| `test_panel_page.py::test_panel_has_project_selector_and_create_project_modal` | `#btn-novo-canal` não existe mais; o JS ainda faz binding nele | ACH-04 |
| `test_settings_sections.py::test_every_settings_section_reaches_real_content` | `/configuracoes/canais` usa `panel_settings.render_channel_list`, sem `id="painel-perfil"` | ACH-07 |
| `test_channels_page.py::test_oauth_callback_page_refuses_an_unknown_state_without_dead_end` | retorno com `state` desconhecido redireciona (303) em vez de mostrar a mensagem | achado menor já registrado na RUN-03 |
| `test_video_style_api.py::test_new_video_page_shows_the_real_styles_of_the_selected_channel` | opções viraram `<div class="grid3">` com rótulo só do nome do estilo | ACH-06 |
| `test_video_style_api.py::test_new_video_preset_reads_the_channel_language_and_voice` | bloco de preset com idioma/voz ausente | ACH-08 |

## A4 — comportamento já commitado que os testes não acompanharam (2 falhas)

Não é WIP: `settings.py` não está modificado na árvore.

- `settings.auto_research = True` (commitado) coloca a etapa de pesquisa no DAG → 9 etapas.
  `test_execution_page_renders_real_run_with_stepper_and_contract` espera "Etapa 1 de 8".
- `settings.publication_enabled = True` (commitado) faz PUBLISH ser um handler disponível →
  `unavailable_stages` fica vazio e o cartão "Indisponível nesta versão" não renderiza.
  `test_execution_page_lists_unavailable_stages_with_reason` espera o cartão.

Correção aplicada (só no teste): a fixture `env` de `tests/test_panel_production_page.py`
passou a usar `Settings(..., auto_research=False)`, como já foi feito em
`tests/test_production_flow_db.py` (grupo D). Com isso o DAG volta a `COORDINATOR_DAG`
(8 etapas) e a etapa de pesquisa fica explicitamente indisponível — que é exatamente o
que as duas asserções exercitam. A pipeline com pesquisa continua coberta em
`tests/test_pesquisa_automatica.py`.

Verificação: `scripts/test-container.sh tests/test_panel_production_page.py -q --tb=line`
→ **1 failed, 12 passed** (8,3 s). As duas falhas de A4 passaram; a restante é
`test_wizard_page_renders_real_channel_and_honest_fields` (A2/ACH-08).

## O que este documento não prova

- Não prova que A2 ou A3 sejam regressões de produto: a árvore está dirty e o WIP V4/V3
  não foi aprovado.
- Não promove nenhum cenário do plano a PASS. A suíte existente não é o plano.
- A contagem de 32 falhas vale para este checkout; a árvore deve ser reconferida antes de
  qualquer campanha.
