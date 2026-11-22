# Matriz única de gaps

Status: **revalidado na F00 em 21/11/2026** (HEAD `e254b61`). G01–G14 provêm do documento original §22; G15 foi identificado na revisão V3. P0 = risco operacional ou financeiro; P1 = consistência; P2 = evolução. P0 SaaS não implica bloqueio da operação mono-operador. Evidência de código por gap em [decisions-needed](evidence/decisions-needed.md); símbolos em [inventory](evidence/inventory.md).

| ID | Lacuna | Prioridade | Fase | Saída | Revalidado na F00 |
|---|---|---|---|---|---|
| G01 | Orçamento global aplicado a limites de canal | P0 | F01 | Separar escopos e reservas atômicas | Confirmado: `_ChannelBudgetFloor` compara gasto global com teto soft do canal; painel soma por canal |
| G02 | Grant novo não consumido pelo publicador/analytics | P0 | F01 | Resolver identidade YouTube comum | Confirmado: token vem de `EnsureAccessToken(youtube_repo)` + `EnvRefreshTokenProvider`; grant só é consultado no gate |
| G03 | Gate divergente no n8n | P0 | F01 | Upload autorizado pelo Core | Confirmado: nó `Upload` usa credencial `youTubeOAuth2Api` própria |
| G04 | Tenancy operacional incompleta | P0 SaaS | Projeto C | Bloquear lançamento multi-tenant | Confirmado: modelo SaaS existe; produção usa `project_id` como canal, sem escopo por tenant |
| G05 | Editorial persistido não aplicado | P1 | F04 | Contexto congelado em short/long | Confirmado: `build_prompt` fixa pt-BR; perfil não é lido pelo gerador |
| G06 | Leituras de configuração durante execução | P1 | F03 | Snapshot antes de efeitos | Confirmado: `style_for`/`voice_for` resolvidos na execução; `ProductionRun` sem config congelada |
| G07 | Override parcial inexistente | P2 | F05 | Composição tipada | Confirmado: só seleção de estilo inteiro (`effective_style_id`) |
| G08 | Arquivamento limpa links sem revisão | P1 | F05 | Lifecycle auditável; mitigação até F05 | Confirmado: `_clear_links` zera `style_id` em canais e vídeos na mesma transação |
| G09 | Routing consultivo, não executado | P1 | F06 | Decisão efetiva e auditada | Confirmado: `route` só é chamado por API/página de Canais; execução lê `ProjectConfig` |
| G10 | BYOK cadastrado, não utilizado | P0 SaaS | Projeto C | Resolver chave autorizada; ocultar promessa atual | Confirmado: nenhum provider lê BYOK; só persistência/auditoria |
| G11 | Canal ativo inconsistente | P1 | F02 | Propagar e validar projeto | Confirmado: canal ativo é `?project_id=`; links internos não propagam |
| G12 | Controles e navegação divergentes | P1 | F02 | Preservar V3 e corrigir resíduo | Confirmado: 4 seções de Settings x 7 propostas; controles fictícios no Create |
| G13 | Pilares editoriais e categorias de coleta distintos | P2 | F04 | Responsabilidades explícitas; integração Finder separada | Confirmado: `pillars` no perfil; `domain/categories.py` são queries de tendências |
| G14 | Transições/dynamic captions/thumbnail/QA estética incompletos | P2 | Projeto B | Evolução audiovisual independente | Não detalhado nesta fase (Projeto B); sem mudança de escopo |
| G15 | Create apresenta estilo sem persistir escolha | P1 | F02 | Catálogo real e gravação validada | Confirmado: 4 estilos fixos no HTML; POST envia `project_id`/`topic`/`format` |

Achados adicionais da F00, sem novo ID (não alteram prioridade nem fase):

- `tests/test_visual_style.py`, citado em F02.T02 e F05.T01, não existe; ajustar a tarefa.
- Settings tem 4 seções reais contra 7 propostas (já coberto por G12).
- `pydantic` instalado 2.5.0 x pin 2.11.4 no `renderer/requirements.txt`.

Cada gap só fecha com teste do comportamento e evidência vinculada à tarefa. G04/G10/G14 permanecem fora do aceite A, com restrições explícitas de produto. G08 requer impedir arquivamento inseguro enquanto F05 não concluir, caso afete runs ativos.
