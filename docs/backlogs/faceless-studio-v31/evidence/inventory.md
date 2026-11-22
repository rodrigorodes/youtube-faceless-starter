# Inventário revalidado (F00.T01)

Levantado em 21/11/2026 no checkout `/Users/rodrigomendes/youtube-faceless-starter`.
Símbolo e caminho são evidência de código; **não** são evidência de execução externa.

## Git

| Item | Valor |
|---|---|
| Branch | `main` (sem branch de trabalho criada) |
| HEAD | `e254b61` (Merge branch 'faceless-v2-impl') |
| Árvore de trabalho | limpa, exceto `docs/backlogs/` não rastreado (este pacote) |
| `bf2c6b1` | existe no histórico |
| Delta `bf2c6b1..HEAD` | 24 arquivos, +4030/−877 (confere com o documento-base) |
| `c0cd97c` (baseline do ZIP) | existe, **sem ancestral comum** com o HEAD (histórias não relacionadas) |
| `git diff c0cd97c HEAD` | vazio — a árvore é idêntica à do ZIP, apesar de o hash divergir |

Consequência prática: o baseline do ZIP está **confirmado por conteúdo**, não por hash.
Referências por hash ao ZIP devem citar `e254b61` no checkout ativo.

## Telas entregues na V3 (rotas confirmadas em `api/routes.py`)

| Tela | Rota | Módulo |
|---|---|---|
| Início | `/studio/panel` | `api/panel_home.py` |
| Novo vídeo | `/studio/panel/novo-video` | `api/panel_new_video.py` |
| Vídeos | `/studio/panel/videos` | `api/panel_videos.py` |
| Detalhe do vídeo | `/studio/panel/videos/{id}` | `api/panel.py` |
| Produção (run) | `/studio/panel/videos/{id}/production-runs/{run_id}` | `api/panel_production.py` |
| Roteiro | `/studio/videos/{id}/roteiro` | `api/preview.py` |
| Prévia | `/studio/videos/{id}/preview` | `api/preview.py` |
| Tendências | `/studio/panel/tendencias` | `api/panel_trends.py` |
| Desempenho | `/studio/panel/analytics` | `api/panel_analytics.py` |
| Configurações | `/studio/configuracoes` → redireciona | `api/routes.py` (`_SETTINGS_SECTIONS`) |
| Canais | `/studio/canais` | `api/panel_channels.py` |
| Estilos | `/studio/panel/estilos` | `api/panel_styles.py` |
| Conexões | `/studio/panel/conexoes` | `api/panel_connections.py` |
| Equipe | `/studio/panel/equipe` | `api/panel_team.py` |

Configurações tem **4** seções (`canais`, `estilos`, `conexoes`, `equipe`); o contrato de
Settings propõe **7** (faltam `estrategia`, `producao`, `avancado`). Ver G12/F02.T03.

## Símbolos citados em 01-current-state.md

Todos existem no HEAD, nos caminhos indicados: `shell_v3.py`/`shell_v3_css.py`,
`routes.py::_SETTINGS_SECTIONS`, `panel*.py`, `domain/channel.py::ChannelProfile`,
`application/editorial.py::GenerateScript`, `application/longform.py`,
`domain/visual_style.py::resolve_style`/`effective_style_id`, `application/video_style.py`,
`adapters/postgres/visual_style_repo.py::_clear_links`, `domain/production_run.py`,
`domain/render_plan.py::StyleSnapshot`, `application/production.py`, `application/render.py`,
`composition.py`, `application/connections.py`, `application/youtube_oauth.py`,
`application/publication_execution.py`, `application/publishing.py`,
`adapters/channel_analytics.py`, `application/budget.py`, `application/channel_budget.py`,
`application/providers.py`, `application/config.py::ProjectConfig`,
`adapters/postgres/budget_repo.py`, `channel_budget_repo.py`, `domain/saas.py`,
`application/saas.py`, `api/panel_team.py`.

## Arquivos de teste citados nas tarefas

Verificados 56 nomes em `tasks/F01..F07`. **Um não existe**: `tests/test_visual_style.py`
(citado em F02.T02 e F05.T01). Equivalentes reais: `tests/test_video_style.py` e
`tests/test_visual_style_domain.py`. Ajustar a tarefa antes de executá-la; não criar teste
com nome especulativo só para casar com o documento.

## Ambiente medido

| Item | Valor |
|---|---|
| Python | 3.11.9 (pyenv) |
| pytest | 8.2.0 |
| pydantic instalado | 2.5.0 |
| pydantic fixado em `renderer/requirements.txt` | 2.11.4 |
| Docker | disponível |
| `STUDIO_TEST_DSN` no shell | ausente (suítes de banco pulam sem ele) |

Divergência de dependência: a suíte de baseline passa com pydantic 2.5.0, mas o pin do
projeto é 2.11.4. Não é prova de compatibilidade com o pin; registrar como item a verificar
no ambiente de release (F07), sem alterar pin nesta fase.

## Preservação do shell V3

Todas as telas renderizam por `api/shell_v3.py::render_document` (Início, Novo vídeo, Vídeos,
detalhe, produção, roteiro, prévia, Tendências, Desempenho, Canais, Estilos, Conexões,
Equipe). `api/panel_oauth.py` não renderiza página (é passo do OAuth). Não há casca duplicada
a substituir: a regra "preservar shell V3" de F02 é sobre conteúdo/controles, não sobre
recriar a casca.

## Estado das telas (observação de código, não de navegador)

- Create mostra quatro opções fixas de estilo (`Padrão do canal`, `Cinemático`,
  `Documentário`, `Tech Clean`) em `api/panel_new_video.py` e envia ao `POST /studio/videos`
  apenas `project_id`, `topic` e `format` (G15 confirmado por leitura).
- O seletor de canal ativo grava `?project_id=` e recarrega a tela; links internos
  (`api/panel_home.py`, entre outros) não propagam o parâmetro (G11).
- Não houve navegação real em browser nesta fase: nenhuma alegação de UX validada em
  navegador está sendo feita.