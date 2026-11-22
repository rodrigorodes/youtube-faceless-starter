# Estado atual e evidência

A referência histórica do documento original é `bf2c6b1`; a avaliação intermediária informou `9ba0d2d`; o ZIP mais recente contém `refs/heads/main` apontando para `c0cd97c`. O delta de 21 commits/24 arquivos (+4030/-877) é resultado informado na revisão anterior, a confirmar no Git local em F00.

A V3 já possui shell, CSS, Home, Create, Library, Trends, Analytics, detalhes, roteiro e preview. Não reconstruir páginas. Os gaps de execução não desaparecem porque as telas foram portadas. O ZIP confirma `api/panel_new_video.py` enviando project_id/topic/format sem style_id no POST; confirmar o contrato do endpoint e reproduzir pelo browser.

## Referências de código (relativas a renderer/app/studio)

| Área | Arquivos / símbolo a localizar |
|---|---|
| Shell e Settings | api/shell_v3.py, shell_v3_css.py, routes.py (`_SETTINGS_SECTIONS`), panel.py |
| Create e Library | api/panel_new_video.py, panel_videos.py, panel_home.py |
| Perfil editorial | domain/channel.py (`ChannelProfile`), application/editorial.py (`GenerateScript`), application/longform.py |
| Estilo | domain/visual_style.py (`resolve_style`, `effective_style_id`), application/video_style.py, adapters/postgres/visual_style_repo.py (`_clear_links`) |
| Run/render | domain/production_run.py, domain/render_plan.py (`StyleSnapshot`), application/production.py, application/render.py, composition.py |
| YouTube | application/connections.py, youtube_oauth.py, publication_execution.py, publishing.py, adapters/channel_analytics.py |
| Budget/providers | application/budget.py, channel_budget.py, providers.py, config.py, adapters/postgres/budget_repo.py, channel_budget_repo.py |
| SaaS | domain/saas.py, application/saas.py, api/panel_team.py |

Símbolos são referências mais estáveis que linhas. Confirmar existência/consumidor no HEAD real antes de editar. A evidência de código não prova execução externa. Ver [baseline](evidence/baseline.md).
