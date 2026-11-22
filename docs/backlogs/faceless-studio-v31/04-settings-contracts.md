# Settings: mapeamento funcional

Reutilizar shell, CSS e componentes V3 existentes. Rotas de destino abaixo são **propostas**, validar aliases/nomes no HEAD. `project_id` é identidade técnica atual do canal; derivar proprietário do vídeo pelo Core, nunca confiar cegamente no seletor.

| Grupo | Origem atual | Caso de uso / domínio | Escopo | Rota proposta | Gate |
|---|---|---|---|---|---|
| Canais | panel_channels | ChannelProfile, vínculo YouTube | projeto | /studio/configuracoes/canais | F01/F02 |
| Estratégia | panel_channels | UpdateChannelProfile, EditorialContext | projeto | /studio/configuracoes/estrategia | F04 |
| Marca e estilo | panel_styles, panel_channels | VisualStyle, SetVideoStyle, overrides | biblioteca/projeto/vídeo | /studio/configuracoes/estilos | F02/F05 |
| Produção | panel_channels | ProjectConfig, BudgetLimits, ProviderService | projeto | /studio/configuracoes/producao | F01/F06 |
| Conexões | panel_connections | grants, secret store, provider registry | instalação/workspace conforme runtime | /studio/configuracoes/conexoes | F01/F06 |
| Workspace | panel_team, tema local | SaaS existente, preferências pessoais | instalação/usuário | /studio/configuracoes/equipe | F02; tenancy fora |
| Avançado | panel_channels, diagnósticos | observabilidade, execução | operador autorizado | /studio/configuracoes/avancado | F02 |

## Regras de interação

- Identificar canal ativo no cabeçalho e manter query/contexto em links, redirects e formulário; seleção inválida não muda silenciosamente de canal; proteger mutações pela propriedade do recurso.
- Mostrar valor herdado, fonte e opção de reset apenas quando suportado. Separar editar biblioteca compartilhada de personalizar canal.
- Create: tema, formato, estilo real (ou herdar). Ao confirmar, persistir seleção real e levar à etapa de fontes. Criar registro não inicia produção automaticamente se faltarem fontes.
- Conexões: separar cadastrado, disponível, autorizado e utilizado. Não exibir token/chave. Workspace não promete tenants independentes.
- Manter tokens CSS existentes como fonte visual inicial; paleta do mockup é referência, não substituição automática. Verificar tema claro/escuro, foco, contraste e responsividade.
- Retirar controles fictícios; usar mensagens orientadas à ação em vez de detalhes de implementação. Erros operacionais explicam próximos passos sem segredos.
- APIs existentes são preferenciais; qualquer agregador de leitura precisa de justificativa. Sem regra de negócio no HTML.
