# Matriz de cobertura — funcionalidades preservadas e propostas

Status desta entrega: todas as linhas abaixo são **UI_ONLY** no protótipo; interação local não prova integração real. “Base” indica origem observada estática, não certifica IMPLEMENTED. Antes de codificar: preencher UI → API → Use case → Domain → Persistence → Pipeline consumer e classificar IMPLEMENTED/PARTIAL/MISSING/UI_ONLY com evidência.

**Coluna “Status” (W0A.4, 22/11/2026):** vem de [evidence/REPO-VALIDATION.md](evidence/REPO-VALIDATION.md) §3, cruzada com o código real, com o ajuste do que a onda W0B mudou ([evidence/ve-w0b-closure.md](evidence/ve-w0b-closure.md)). Legenda: **IMPLEMENTADO** = UI → API → caso de uso → domínio → persistência com consumidor no pipeline · **PARCIAL** = existe ponta a ponta com lacuna declarada · **AUSENTE** = não existe no core · **UI_ONLY** = persistido/exibido sem consumidor. A evidência `arquivo:linha` é relativa a `renderer/app/studio/`.

| Funcionalidade | Base no projeto | Destino na revisão 3 | Comportamento da demo / lacuna real | Status | Evidência (REPO-VALIDATION §3) |
|---|---|---|---|---|---|
| Home e continuar vídeo | V3 / panel_home | Início | Canal, recentes e atalhos | IMPLEMENTADO | `api/panel_home.py`; cartão sem imagem de vídeo (`shell_v3_css.py:241-246`) |
| Tema, formato, duração, roteiro pronto | V3 / panel_new_video / VE-07 | Criar vídeo | Cria rascunho local, sem geração | IMPLEMENTADO | `panel_new_video.py`; sem campo de duração-alvo |
| Contexto de canal | active_channel / shell_v3 | Seletor + Canais | Listas separadas e snapshots | IMPLEMENTADO (W1.2) | `active_channel.py`; páginas de vídeo/prévia/roteiro/execução mostram o canal **dono** em leitura (`video_channel` na casca) |
| Listar/filtrar vídeos | panel_videos | Vídeos | Publicado separado de aprovado | IMPLEMENTADO (W1.1) | `panel_videos.py` agora só põe `COMPLETED` em "Publicados"; `APPROVED` vai para "Em criação" |
| Fontes e evidências | V3 / fluxo editorial | Fontes e roteiro | Texto/URL registrados; sem fetch/fact-check | IMPLEMENTADO | `panel.py:3343-3405`; allowlist de 1 domínio (`composition.py:112`); `Claim` por heurística e não persistido (`domain/claims.py:12-26`) |
| Roteiro por cena | VE-07 | Fontes e roteiro / editor | Edição salva; add/remove/reorder com IDs | PARCIAL (ver) / AUSENTE (editar, IDs) | ver: `panel.py:4012-4178`; editar: `EditScriptScene` sem rota (`application/longform.py:393`); ID estável ausente (`editorial_repo.py:77-81`) |
| Voz, provider, velocidade | Canal + VE-07 | Narração | Configuração, trechos e geração simulada | PARCIAL | 1 provider de voz (`piper`); `channel_profiles.voice` ignorada (`composition.py:247-260`, rótulo corrigido na W0B.4); sem campo de velocidade |
| Pré-escuta/duração real | VE-07 | Narração | Trecho exibido; sem áudio, duração não medida | AUSENTE | sem rota de áudio; `scenes.duration_s` nunca gravada (`render.py:52-57`) |
| Storyboard e intenção visual | VE-07 | Cenas e mídias | Texto/mídia por cena; intenção avançada a integrar | PARCIAL | `preview.py:81`; `image_prompt` existe por cena; sem UI de edição |
| Mídia híbrida, candidatos/licença | VE-03/06 | Trocar mídia | Origem fictícia; candidatos reais dependem de adapter | AUSENTE (troca/candidatos) / IMPLEMENTADO (licença) | `link_scene` só em STORYBOARDED e cena sem asset (`media.py:65,75`); stock só Pexels; `assets.license` obrigatória (`media.py:93-104`) |
| Camadas/B-roll | VE-01/02 | Composição | Tracks ilustrativas e toggle | AUSENTE | escopo VE-01/02 |
| Legendas, tipografia, música | V3.1 / VE-04 | Marca e estilo / Composição | Campos locais, sem render real | PARCIAL | consumidos: motion, bpm/seed, legenda, cor do selo, modelo de voz (`render_plan_ffmpeg.py:84-131,434,585`); sem volume de música (fixo 0,40), família de fonte (fixa) e thumbnail configurável |
| Resolução/FPS/transições/motion | Core + VE-04 | Composição / Produção | Overrides locais; validar allowlist real | PARCIAL | resolução e FPS fixos (`render.py:12`, 25 fps); **transição só declarada** (`visual_style.py:502-506`) |
| QA técnico / semântico | Core + VE-05 | Qualidade | Gate técnico simulado; semântico não verificado | IMPLEMENTADO (técnico) / AUSENTE (semântico) | `preview.py:69-80` bloqueante; semântico é VE-05 |
| Aprovar versão | production / VE-07 | Qualidade / Publicação | Exige QA e revisão atuais na simulação | IMPLEMENTADO | `publish_repo.py:41-63`: aprovação grava `render_id`, `media_checksum`, QA e `idempotency_key` na mesma transação |
| Título/descrição/privacidade | Fluxo publish | Publicação | Metadados locais; envio simulado | IMPLEMENTADO | `preview.py:91-108`; `public` exige confirmação separada (`publication_policy.py`) |
| Thumbnail/agendamento | Identidade/publication | Publicação | Briefing/data local; sem imagem/agenda real | PARCIAL (thumbnail) / IMPLEMENTADO (agendamento) | `adapters/thumbnail.py` (1ª cena), sem briefing nem upload; `pub.publish_at` com janela (`publication_policy.py`) |
| Histórico/revisões | Contratos + proposta UX | Histórico no vídeo | Restaurar cria revisão; publicação preservada | PARCIAL | versão do roteiro inteiro; sem versão por cena nem "restaurar" |
| Pause/resume/retry/cancel | production_run | Produção do vídeo | Controles locais; não há worker | IMPLEMENTADO | `routes.py:1780-1826`; `resume` com `expected_state` |
| Custos/limites | budget/provider | Produção e orçamento | Limites configuráveis; consumo real indisponível | PARCIAL (era risco R1; W0B.1 ligou o guard e provou o bloqueio por canal) | `budget_repo.py`, `composition.py:634-638`; tetos por canal em `channel_budgets`; falta mensagem de recusa acionável (`routes.py:923`) |
| Tendências/pilares | panel_trends | Tendências e ideias / Estratégia | Filtros e ideia → criar vídeo; dados fictícios | IMPLEMENTADO (dados reais; W1.3) | YouTube Data API; "Criar vídeo deste tema" virou `<a>` com `project_id` + `topic` (preserva o canal) |
| Analytics | panel_analytics | Desempenho | Período e gráfico ilustrativos; sem API | IMPLEMENTADO | `youtube_analytics.py`; nunca fabrica zero (`not_yet_available`) |
| Perfil/estratégia/público/CTA | ChannelProfile | Estratégia editorial | Campos persistidos localmente | IMPLEMENTADO (W1.6 expôs narrativa/duração/CTA) | consumidos no prompt (`editorial.py:99-153`); os três agora têm UI no perfil do canal |
| Estilos compartilhados / override | visual_style / effective_config | Biblioteca / Marca e estilo | Aplicar padrão preserva vídeos existentes | IMPLEMENTADO (estilos, canal, biblioteca como destino próprio na W1.5) / PARCIAL (override de vídeo; vozes/mídias) | `visual_styles`, `style_patch`, `panel_channel_style.py`; `set_video_style_patch` sem rota (`repo.py:203`); biblioteca só de estilos (`panel_styles.py`) |
| Providers por tarefa/perfil | provider.py / providers | Produção e orçamento | Escolha por capability em catálogo demo | PARCIAL | `PUT /projects/{id}/config` sem tela; botão "Reordenar fallback" desabilitado (`panel_channels.py:765`); **S8** congela a seleção por capacidade no snapshot e o retry usa a congelada (o exibido não pode mais diferir do executado) |
| N conexões/modelos/teste | V3.1 / connections | Conexões e providers | Adicionar/configurar/testar simulado | PARCIAL | texto 2, imagem 4, voz **1**, render **1** (`composition.py:367-398`) |
| Google/YouTube/vínculos | youtube identities / panel_connections | Conexões / Canais | Vínculo fictício; OAuth ausente | IMPLEMENTADO | `0035`; tokens só no cofre de arquivos; revogação (`connections.py:335-368`); gate de publicação fechado na W0B.2 |
| BYOK/revogação | saas / panel_team | Conexões e providers | Apenas alias fictício; sem segredo | PARCIAL | a UI avisa (`panel_channels.py:1074-1081`); providers usam env do servidor (fora da execução) |
| Usuários/papéis/equipe | memberships / panel_team | Conta e equipe | Membros locais, sem convite/autorização real | PARCIAL | papéis owner/editor/reviewer/viewer; `require()` só nas mutações de Equipe; `CREATE_VIDEO`, `EDIT_VIDEO`, `APPROVE_*`, `PUBLISH` declaradas e **não aplicadas** |
| Aparência e preferências | V3 / Settings | Conta e equipe | Tema claro/escuro local | IMPLEMENTADO | casca V3 (`shell_v3_css.py:17-30`, contraste documentado) |
| Saúde/config efetiva/diagnóstico | panel_advanced | Avançado / Produção | Config sanitizada local; sem logs reais | PARCIAL | sem logs/eventos nem diff de snapshot por run; `/health` devolve `ffmpeg: True` fixo (`main.py:34-36`) |
| n8n/API/RenderPlan | V3.1 / core | Avançado | Fronteiras explicadas; operação real a integrar | PARCIAL | a prévia diz que o n8n publica (`preview.py:41`) e `routes.py:1656` diz que o servidor publica: **caminho vigente não confirmado**; `POST /publications/claim` fora do gate de identidade (achado da W0B.2) |

## Linhas de §3 sem correspondência direta acima (não podem desaparecer)

| Funcionalidade | Status | Evidência |
|---|---|---|
| **ID de cena estável** | AUSENTE | `editorial_repo.py:77-81`: a cada versão `DELETE` + `INSERT` com `uuid4`; `asset_id` por cena se perde — quebra deep-link, mídia por cena e cache seletivo |
| **Editar após aprovar** | AUSENTE | `states.py:9`: `APPROVED` só vai a `PUBLISHED`; sem "reabrir" (D-B/P-04) |
| Snapshot congelado por run | IMPLEMENTADO (W0B.3 congelou o perfil econômico; **S8** congela a seleção por capacidade — `provider_policy.selection`, aditivo e compatível com runs antigos) | `0039`, `composition.py:212-232`; `provider_policy.selection` validado em `effective_config.py`; retry lê a seleção congelada |
| Retomada após fechar o navegador | IMPLEMENTADO (no processo) | worker em `ThreadPoolExecutor` dentro da API; `recover_in_flight` no boot |
| Gates de publicação no servidor | IMPLEMENTADO (fail-open fechado na W0B.2) | `publication_execution.py:226-260`; `verify_publication_gate`; sem destino → `BLOCK` acionável |
| Isolamento por organização | AUSENTE | `organization_id` não aparece em nenhum repo de vídeo/asset/render/produção; vem do corpo/query; um único usuário Basic |
| Avançado: config efetiva por run | PARCIAL | ver linha "Saúde/config efetiva/diagnóstico" |

## Atualizações desta coluna

- **22/11/2026 (W0A.4):** coluna criada a partir de `REPO-VALIDATION §3`, já com o efeito da onda W0B (orçamento provado, publicação fail-closed, perfil econômico congelado, rótulos honestos). Manter esta coluna sincronizada a cada onda.
- **22/11/2026 (W1):** efeitos da onda de UX — Vídeos distingue aprovado de publicado; páginas de vídeo mostram o canal dono; "Criar vídeo deste tema" preserva o canal; vídeo com 8 áreas como rotas (`panel_video_workspace.py`); Configurações em 7 seções e **Biblioteca** como destino próprio; narrativa/duração/CTA com UI; Fontes explicitam "registrada ≠ extraída ≠ verificada". Detalhe: [evidence/ve-w1-closure.md](evidence/ve-w1-closure.md).
