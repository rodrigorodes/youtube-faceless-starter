# RUN-03 — triagem das falhas da suíte canônica

- Data: 2026-11-25
- HEAD: f4a9244 (branch main)
- Árvore: dirty (WIP local de UX V4/V3, contratos gerados, testes ajustados e este plano)
- Base da triagem: RUN-02 (`RUN-02-container-suite.md`), 39 failed / 4019 passed / 20 skipped.
- Objetivo: separar artefato de teste de bug de produto, sem promover cenário a PASS.

## Resultado por grupo

| Grupo | Falhas | Classificação | Ação aplicada |
|---|---|---|---|
| A. Drift de UI/casca | 32 | Teste desatualizado (WIP V4/V3 não aprovado) | Nenhuma mudança de produto. Testes a atualizar quando o WIP for aprovado. |
| B. Artefatos gerados | 3 | Geração no host, não no container | Contratos regenerados no container; `docs/22` regenerado com `scripts/export_schema.py --build` contra Postgres 16 efêmero. |
| C. Lista de migrações | 2 | Teste desatualizado | Lista esperada em `tests/test_db.py` atualizada para 48 migrações (0047–0053). |
| D. Fluxo de produção | 2 | Teste desatualizado | Fixture de `tests/test_production_flow_db.py` passou a usar `auto_research=False`; a guarda de estágio indisponível continua válida. |

## Verificação após as correções (subconjuntos)

- `tests/test_contracts_snapshot.py tests/test_schema_docs.py tests/test_secrets_hygiene.py`:
  **39 passed**.
- `tests/test_db.py tests/test_production_flow_db.py`: **22 passed**.
- `tests/test_styles_page.py tests/test_connections_page.py`: 2 failed (mesmo drift de
  rótulos da nav; grupo A).
- `tests/test_panel_page.py`: 15 failed (grupo A).
- `tests/test_settings_sections.py tests/test_channels_page.py tests/test_video_style_api.py`:
  9 failed (grupo A).

## Mapa das falhas do grupo A (teste -> motivo)

| Arquivo | Teste | Motivo do descompasso |
|---|---|---|
| `tests/test_panel_page.py` | `test_panel_page_empty_state` | O vazio do Início virou "Primeiros passos"; o texto "Nenhum vídeo ainda" saiu. |
| `tests/test_panel_page.py` | `test_panel_page_renders_trending_topics_block` | O título da tela é "Tendências e ideias", não "Tendências</h1>". |
| `tests/test_panel_page.py` | `test_panel_page_renders_category_pills_and_management_modal` | O chip "Todas" virou "Todos"; o markup do chip mudou. |
| `tests/test_panel_page.py` | `test_panel_renders_youtube_themed_cards_and_video_links` | O CTA "Criar vídeo deste tema" virou "Criar com esta ideia". |
| `tests/test_panel_page.py` | `test_panel_page_has_loading_spinner_and_region_filters` | Filtro por região saiu da UI; chip "Todos". |
| `tests/test_panel_page.py` | `test_panel_uses_the_single_shell_palette_and_preview_stays_consistent` | A casca V4 não usa `color-scheme: light dark` nem `light-dark()`. |
| `tests/test_panel_page.py` | `test_panel_has_project_selector_and_create_project_modal` | O botão `#btn-novo-canal` não existe no HTML; o link de novo canal mudou. |
| `tests/test_panel_page.py` | `test_panel_renders_production_board_and_modern_video_cards` | O `aria-label` do cartão mudou. |
| `tests/test_panel_page.py` | `test_preview_page_has_unified_sidebar_layout` | A asserção exige `<aside class="side">` exato; o HTML tem `aria-label="Menu principal"`. |
| `tests/test_panel_page.py` | `test_panel_trends_lists_every_trend_with_an_honest_count` | A classe é `card cartao-tendencia`, não `class="cartao-tendencia"`. |
| `tests/test_panel_page.py` | `test_panel_empty_production_state_is_explicit_without_fake_progress` | O vazio do Início mudou de texto. |
| `tests/test_panel_page.py` | `test_panel_shell_preserves_sections_and_trend_filter_contract` | O chip usa `class="pill btnlike chip-filtro"` e o rótulo "Todos". |
| `tests/test_panel_page.py` | `test_panel_cost_note_labels_four_cost_categories` | A nota de custo saiu de `<p class="nota-custo">` para a casca; o seletor ficou órfão. |
| `tests/test_panel_page.py` | `test_panel_declares_viewport_and_responsive_media_query` | O breakpoint passou de 820 px para 1000 px. |
| `tests/test_panel_page.py` | `test_panel_ia01_producao_and_tendencias_are_isolated_from_the_home` | O Início não tem mais o link "Acompanhar produção". |
| `tests/test_settings_sections.py` | `test_the_global_menu_lists_the_prototype_items_and_the_library` | A nav ganhou glifos (`⌂ Início`). |
| `tests/test_settings_sections.py` | `test_the_settings_menu_has_the_seven_prototype_sections_with_the_active_channel` | Configurações passou de 7 para 4 seções. |
| `tests/test_settings_sections.py` | `test_every_settings_section_reaches_real_content` | A página de Canais não tem mais `id="painel-perfil"`. |
| `tests/test_channels_page.py` | `test_channels_page_uses_the_approved_shell` | A nav ganhou glifos. |
| `tests/test_channels_page.py` | `test_settings_menu_matches_the_prototype_and_keeps_the_active_channel` | 7 -> 4 seções. |
| `tests/test_channels_page.py` | `test_oauth_callback_page_refuses_an_unknown_state_without_dead_end` | O callback com `state` desconhecido agora redireciona para Conexões. |
| `tests/test_video_style_api.py` | `test_new_video_page_shows_the_real_styles_of_the_selected_channel` | O bloco de estilos mudou de `fieldset.pills` para `div.choice`. |
| `tests/test_video_style_api.py` | `test_settings_area_links_to_the_seven_groups` | 7 -> 4 seções; `canais` deixou de ser redirect. |
| `tests/test_video_style_api.py` | `test_new_video_preset_reads_the_channel_language_and_voice` | O preset não usa mais `aside.painel`; o idioma saiu do resumo. |
| `tests/test_styles_page.py` | `test_styles_page_marks_biblioteca_active_and_no_dead_configuracoes` | A nav ganhou glifos. |
| `tests/test_connections_page.py` | `test_connections_page_menu_has_conexoes_active_in_gestao` | A nav ganhou glifos. |
| `tests/test_analytics_page.py` | `test_page_is_reached_through_the_approved_shell` | A asserção exige `<aside class="side">` exato; o HTML tem `aria-label="Menu principal"`. |
| `tests/test_analytics_page.py` | `test_channel_selector_lists_real_projects_and_switches` | O id do seletor de projeto mudou. |
| `tests/test_panel_production_page.py` | `test_wizard_page_renders_real_channel_and_honest_fields` | O texto "Predefinição do canal" mudou. |
| `tests/test_panel_production_page.py` | `test_execution_page_renders_real_run_with_stepper_and_contract` | O stepper mudou de "Etapa 1 de 8". |
| `tests/test_panel_production_page.py` | `test_execution_page_lists_unavailable_stages_with_reason` | O texto "Indisponível nesta versão" mudou. |
| `tests/test_script_page.py` | `test_roteiro_page_uses_the_shared_shell` | A asserção exige `<aside class="side">` exato. |

## O que a triagem mudou no produto

Nada. As correções foram em artefatos gerados e testes. O produto não foi alterado para
fazer a suíte passar. As falhas do grupo A continuam como drift de teste; a decisão de
atualizar os testes depende da aprovação do WIP V4/V3.

## O que a triagem não prova

- Não prova que o grupo A é bug de produto; a árvore está dirty e o WIP de UI pode estar
  incompleto.
- Não prova cobertura de fornecedores externos, publicação real ou avaliação humana.
- Não substitui a execução de uma campanha com dados reais e critérios de aceite.
