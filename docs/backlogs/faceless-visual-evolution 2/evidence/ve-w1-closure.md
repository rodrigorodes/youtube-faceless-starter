# W1 — Fechamento da onda de UX (22/11/2026, sessão 2)

**Base:** `a2e6a39` (branch `main`) · **Nada commitado** · **Testes:** só no container (`scripts/test-container.sh`).
**Como foi executado:** execução direta com Superpowers (o runtime LangGraph do workspace CERC não existe neste repositório). W1.1/W1.3/W1.6 e W1.4/W1.7 rodaram em **worktrees isolados** por subagentes; W1.2 e W1.5 no checkout principal; os arquivos finais foram portados para o checkout principal e a verificação integrada rodou lá.
**Referência de UX:** `prototype/index.html` (estrutura, rótulos, estados e honestidade), **com o tema/estilo/efeitos existentes** (casca V3: `shell_v3_css.py`, tokens, `StudioLoading`, `form-feedback`). Nada de CSS do protótipo foi copiado.
**Legenda:** **[F]** fato verificado (arquivo:linha, comando ou saída de teste) · **[D]** decisão minha, com o custo se estiver errada.

## Placar por item

| ID | Entrega | Arquivos principais | Testes |
|---|---|---|---|
| W1.1 | "Aprovado" ≠ "Publicado" (R5) | `api/panel_videos.py` | `tests/test_videos_v3.py` (3 novos) |
| W1.2 | Canal **dono do vídeo** na casca (R6) | `api/shell_v3.py`, `api/shell_v3_css.py`, `api/panel.py`, `api/preview.py`, `api/panel_production.py`, `api/routes.py` | `tests/test_active_channel.py` (2), `tests/test_panel_page.py` (1) |
| W1.3 | "Criar vídeo deste tema" preserva o canal (KEEP-01) | `api/panel_trends.py` | `tests/test_trends_v3.py` (1), `tests/test_panel_page.py` (2 reescritos) |
| W1.4 | 8 áreas do vídeo como **rotas** (UX-03) | **novo** `api/panel_video_workspace.py`, `api/routes.py`, `api/shell_v3_css.py` | `tests/test_video_workspace.py` (17), `tests/test_panel_page.py` (rota + antigas) |
| W1.5 | Configurações em 7 seções + item **Biblioteca** (SET) | `api/shell_v3.py`, `api/routes.py`, **novo** `api/panel_settings.py`, `api/panel_styles.py` | `tests/test_settings_sections.py` (6) + rótulos atualizados em 8 arquivos |
| W1.6 | Narrativa, duração padrão e CTA do canal (SET-01) | `api/panel_channels.py` | `tests/test_channels_page.py` (2) |
| W1.7 | Fontes: registrada ≠ extraída ≠ verificada (FLOW-01) | `api/panel_video_workspace.py` | `tests/test_video_workspace.py` (2) |

## W1.1 — "Aprovado" ≠ "Publicado"

**Fato (antes).** `panel_videos.py::_situacao_key` mapeava `Stage.APPROVED` **e** `Stage.COMPLETED` para `"publicados"` **[F]**, então um vídeo aprovado sem upload aparecia como publicado. `domain/panel.py::classify` já devolvia `COMPLETED` só para `VideoStatus.PUBLISHED` ou publicação `UPLOADED` **[F]** — o defeito era só no rótulo da tela de Vídeos.

**Mudança.** `_situacao_key` devolve `"publicados"` **somente** para `Stage.COMPLETED`; `Stage.APPROVED` cai em `"producao"` ("Em criação"), que é a semântica do protótipo (`working = !published`). O item de filtro passou de "Em produção" → **"Em criação"** (valor `producao` mantido).

**Testes.** `test_approved_video_shows_as_approved_and_stays_out_of_published`, `test_only_effectively_published_videos_are_in_the_published_filter`, `test_videos_filters_follow_the_prototype_labels`. Vermelho observado: o cartão de um vídeo `APPROVED` trazia `data-situacao="publicados"`. `domain/panel.py` **não** foi alterado (o `classify` já estava correto e coberto por teste paramétrico).

## W1.2 — canal dono do vídeo na casca

**Fato (antes).** As páginas de vídeo/prévia/roteiro/execução chamavam `render_document(..., projects=[], project_id="")` **[F]** (`panel.py:3985,4173`, `preview.py:158`, `panel_production.py:757`), então a topbar mostrava "Nenhum canal cadastrado" — embora trocar de canal ativo não mova o vídeo (`active_channel.py`).

**Mudança.** `render_document`/`render_topbar` ganharam `video_channel: str = ""`; quando informado, a topbar mostra o canal **em leitura** (`<span class="canal-video" id="canal-do-video">`, CSS `.canal-video`) em vez do seletor. As rotas preenchem o nome por `_channel_name(uc, project_id)` (a partir da lista real de canais) e `_video_channel_name(uc, video_id)` (a partir do vídeo). Sem canal → comportamento anterior preservado (`""`).

**Testes.** `tests/test_active_channel.py::test_the_video_page_shell_shows_the_owner_channel_and_not_the_empty_state` e `::test_without_a_video_channel_the_shell_keeps_the_previous_behavior`; `tests/test_panel_page.py::test_video_pages_show_the_owner_channel` (verifica as 3 rotas com banco real). Vermelho observado: "Nenhum canal cadastrado" na página do vídeo.

## W1.3 — "Criar vídeo deste tema" preserva o canal

**Fato (antes).** `panel_trends.py:164-170` navegava para `/studio/panel?...topic=` **sem** `project_id` (via handler JS), trocando o canal ativo em silêncio **[F]**.

**Mudança.** O controle virou um `<a href="/studio/panel?project_id=…&topic=…">` (funciona sem JS) e o handler JS antigo foi removido. Dois testes de `test_panel_page.py` foram **reescritos de propósito** (fixavam o botão + JS + href sem `project_id`) — mudança pedida, não enfraquecimento.

**Testes.** `tests/test_trends_v3.py::test_create_video_link_keeps_the_active_channel_and_topic` (vermelho: "link de criar vídeo ausente").

## W1.4 — 8 áreas do vídeo como rotas

**Mudança.** Novo `api/panel_video_workspace.py`: `render_video_workspace(view, area, *, style_view=None, script_view=None, projects=(), project_id="", channel_name="")`. Navegação por `<nav class="abas-video">` com **links** (`<a class="aba" href=… aria-current="page">` exato na ativa) — sem `role=tab`, sem JS de abas. Rota `GET /studio/panel/videos/{video_id}/{area}` adicionada em `routes.py`. Áreas: `visao-geral`, `fontes`, `narracao`, `cenas`, `composicao`, `qualidade`, `publicacao`, `producao`. As áreas somente leitura (Narração, Cenas) não têm controle falso (sem player, sem botão de gerar). Reusa `panel._video_sources_card`/`_video_run_card`; a aprovação continua na prévia e a produção nas rotas de execução (não reimplementa gate).

**Testes.** `tests/test_video_workspace.py` (17, sem banco) + `tests/test_panel_page.py::test_video_area_routes_are_real_and_old_routes_still_work` (as 8 áreas retornam 200 com a nav e link ativo; `/panel/videos/{id}`, `/roteiro`, `/preview` seguem 200; área desconhecida não quebra).

**[D] Área desconhecida → Visão geral (não 404).** O protótipo faz igual (`panels[S.videoTab] || overviewPanel`) e um segmento estranho não é erro do operador. Custo se errado: um link quebrado em vez de um link quebrado — irrelevante.

## W1.5 — Configurações em 7 seções + Biblioteca

**Mudança.** Em `shell_v3.py`: `NAV_OPERACAO` passou a `Início · Criar vídeo · Vídeos · Tendências e ideias · Desempenho · Biblioteca` (+ Configurações no rodapé); `SETTINGS_SECTIONS` passou a 7 itens (`Canais · Estratégia editorial · Marca e estilo · Produção e orçamento · Conexões e providers · Conta e equipe · Avançado e diagnóstico`). Novo `api/panel_settings.py` renderiza páginas próprias (`/studio/configuracoes/{estrategia|marca|producao}`) que **reusam** os cartões, o formulário, o endpoint e o JS da tela de Canais (`_channels_page_js(project_id)`, extraída mecanicamente e verificada byte a byte contra a versão anterior). Apelidos legados `/studio/configuracoes/estilos` e `/studio/configuracoes/identidade` continuam respondendo 302 (não viram 404).

**[D] A biblioteca de estilos é a página própria "Biblioteca", não uma seção de Configurações.** `panel_styles.py` passou a renderizar `active="biblioteca"`, `crumb="Biblioteca"` e um corpo próprio (`shell_v3.render_library_page_body`, sem a navegação de Configurações). Antes ela se chamava "Configurações / Estilos". O protótipo trata `library` como destino de topo (fora de `CFG`) — manter a página dentro do layout de Configurações com a nav marcando "Biblioteca" seria contraditório. Custo se errado: uma tela sai do guarda-chuva "Configurações"; reverter é uma linha.

**Testes.** Novo `tests/test_settings_sections.py` (menu com Biblioteca, 7 seções navegáveis com conteúdo real, reúso do JS, apelidos legados, 404 para seção inexistente). Contratos de rótulo/redirecionamento atualizados em 12 arquivos de teste (`test_channels_page`, `test_connections_page`, `test_home_v3`, `test_panel_page`, `test_panel_production_page`, `test_script_page`, `test_styles_page`, `test_ux_contract`, `test_panel`, `test_publishing`, `test_settings_area`, `test_video_style_api`) — expectativas **velhas** (menu de 5 itens, 6 seções, `estrategia`/`producao` como âncoras, "Estilos" como seção), não enfraquecimento de asserção. Em `test_settings_area.py` e `test_video_style_api.py`, as seções com página própria passaram a ser verificadas como **não-redirect** (o `302` antigo virou `200`/`!= 302`), que era exatamente o comportamento antigo fixado.

## W1.6 — narrativa, duração padrão e CTA do canal

**Fato.** `channel_profiles.narrative`, `target_duration_s` e `cta` **já são consumidos** pelo prompt (`application/editorial.py:99-153`) e só existiam via `PATCH /channels/{id}` **[F]**.

**Mudança.** Os três campos entraram no formulário do perfil em `panel_channels.py` (mesmo padrão label/hint, limites do domínio: `narrative` ≤4000, `target_duration_s` 1–36000, `cta` ≤500) e no `changes` do JS (duração só entra quando preenchida; vazio ≠ 0). Nenhuma rota nova — o formulário já posta no perfil.

**Testes.** `test_profile_form_exposes_narrative_duration_and_cta_with_real_values` e `test_profile_form_sends_the_editorial_fields_to_the_same_profile_route`. O consumidor real já é coberto por `tests/test_editorial.py::test_channel_editorial_fields_reach_the_short_prompt` (**registrado, não duplicado**).

## W1.7 — Fontes: registrada ≠ extraída ≠ verificada

Frase visível (fora de `sr-only`) na área Fontes do workspace: `<p class="aviso" id="fontes-honestidade">` diz que URL registrada não é fonte extraída nem verificada. Teste `test_fontes_honesty_is_visible_not_sr_only`.

## Verificação integrada (checkout principal)

```
FACELESS_TEST_IMAGE=faceless-renderer:main FACELESS_PYTEST_IMAGE=faceless-renderer-pytest:main \
  scripts/test-container.sh tests/test_active_channel.py ... tests/test_video_workspace.py tests/test_panel.py -q
→ 355 passed, 1 skipped   (telas/painel/contrato de UX)
FACELESS_TEST_IMAGE=... scripts/test-container.sh \
  tests/test_panel.py tests/test_publishing.py tests/test_connections_page.py tests/test_styles_page.py \
  tests/test_ux_contract.py tests/test_settings_sections.py tests/test_video_workspace.py \
  tests/test_channels_page.py tests/test_active_channel.py -q
→ 219 passed, 1 skipped
```
Suíte completa: `full5-w1.log` → **0 failed, 3094 passed, 6 skipped** (356 s), `hash renderer/app=b4839e8bcce19e10`.

## Decisões desta onda

1. **[D] `scripts/test-container.sh` parametrizável.** `BASE_IMAGE`/`PYTEST_IMAGE` passaram a honrar `FACELESS_TEST_IMAGE`/`FACELESS_PYTEST_IMAGE` (default inalterado). Sem isso, worktrees em paralelo colidiam na tag única e o script abortava com "a imagem não corresponde ao checkout" **[F]**. Custo se errado: nenhum (default preservado).
2. **[D] Biblioteca como página própria** (acima).
3. **[D] Área de vídeo desconhecida → Visão geral** (acima).
4. **[D] `MOCKUP_ONLY_TEXT` estendido** com os temas de demonstração do protótipo novo ("O que quase ninguém sabe sobre este lugar", "Três perguntas para entender o futuro", "Uma descoberta que mudou nossa história", "Além do planeta", "Histórias em 5 minutos"), para o contrato de UX barrar vazamento nas telas novas.

## Regressão própria encontrada e corrigida

A suíte completa pegou uma **regressão de vocabulário** introduzida na W0B.4: o rótulo honesto da
"Voz do narrador" dizia "…vem do estilo ou do **projeto**", e o RF-01 proíbe "projeto" como texto
visível (`tests/test_channel_vocabulary.py::test_channels_page_has_no_project_vocabulary`). A
redação passou a "…do estilo ou do padrão do estúdio" (o campo `channel_profiles.voice` continua
não aplicado; quem decide é o estilo ou o fallback do estúdio), e a asserção equivalente em
`tests/test_channels_page.py` foi ajustada. Nada de asserção enfraquecida: o contrato de vocabulário
segue valendo. Foi a única falha da suíte completa.

## Achados abertos (não corrigidos)

1. `POST /publications/claim` fora do gate de identidade (W0B.2) — só importa se o workflow n8n for reativado.
2. Seleção efetiva de provider/modelo por capacidade **não** congelada no snapshot (W0B.3, parte ii) — `provider_policy` só tem `profile`/`version` e nenhum consumidor o lê.
3. Recusa de orçamento chega como `403 "budget denied for paid operation <chave>"` sem dizer qual teto estourou.
4. `STUDIO_PROVIDER_PRODUCTION` e `STUDIO_SECRETS_ROOT` não são encaminhados pelo Compose.
5. `__pycache__` obsoleto (compilado em `/workspace`) explica caminhos `../workspace/tests/...` nos resumos do pytest; não afeta o resultado.
