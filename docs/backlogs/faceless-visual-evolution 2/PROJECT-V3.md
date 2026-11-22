# Projeto atualizado — preservar capacidade, melhorar usabilidade

## 1. Correção de escopo
O pedido é evoluir o aplicativo existente e incorporar a proposta Visual Evolution anterior. A revisão 2 reduziu o produto a poucas áreas, retirou configurações e tornou capacidades apenas mensagens demonstrativas. Esta revisão recupera a cobertura, sem reiniciar arquitetura ou descartar V3.1.

Bases: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` (visual e navegação), documento V3.1 (Settings e configuração efetiva), `evidence/v1-superseded/prototype/index.html` (etapas de produção VE-07), código Python e schema do ZIP. A inspeção é estática; a matriz não declara integração real de ponta a ponta.

## 2. Regra central
Simplificar é organizar campos, defaults e próximos passos. Não significa remover Fontes, Narração, Composição, QA, Providers, Orçamento, Conexões, Equipe, Analytics ou Avançado. Cada capacidade tem destino visível e contexto definido.

## 3. Navegação e hierarquia
Usuários participam de uma conta. Conta contém canais. Canal tem identidade e vídeos. Cada vídeo tem cenas, revisões, execuções e publicação. Preservar `projects`/`channel_profiles` 1:1; não adicionar um nível de projeto na UI.

Global: Início / Criar vídeo / Vídeos / Tendências e ideias / Desempenho / Biblioteca / Configurações. Canais são acessíveis no seletor persistente e em Configurações → Canais. Todos os canais pode ser agregação futura, mas criação exige destino editorial definido.

No vídeo: Visão geral / Fontes e roteiro / Narração / Cenas e mídias / Composição / Qualidade / Publicação / Produção. As abas são áreas de trabalho, não prova de etapa concluída. Produção é o mapa de status/retomada; nenhuma etapa interna vira um segundo fluxo.

## 4. Jornada principal completa
1. Canal ativo com padrão de voz, estilo, idioma, narrativa, mídia e custo.
2. Tema ou roteiro, formato e duração-alvo. Opções avançadas acessíveis, sem obrigatoriedade de preenchimento.
3. Fontes aproveitáveis e revisão do roteiro. Não prometer pesquisa automática: o caminho inspecionado exige fontes e documentação V3.1 registra lacuna de pesquisa autônoma.
4. Narração com seleção compatível, pré-escuta real quando disponível, duração medida e regeneração seletiva.
5. Storyboard por cena com texto, intenção visual, mídia, alternativas, licença e proveniência.
6. Composição multilayer, B-roll, títulos, legendas, voz e música; presets e timeline simples.
7. QA técnico bloqueante; semântico opcional explicitamente não verificado quando ausente. Correção leva à cena.
8. Aprovação do render/checksum exato; publicação em destino autorizado com metadados confirmados.
9. Produção retomável e publicação histórica preservada após edições locais.

Criação de registro, geração, montagem e publicação são operações distintas. A UI permite corrigir qualquer etapa sem perder o vídeo ou reconfigurar o canal.

## 5. Configurações completas
- **Canais:** perfis, seleção, nome/idioma, associação YouTube e status por canal.
- **Estratégia:** público, narrativa, estratégia, pilares, idioma, duração padrão e CTA.
- **Marca e estilo:** biblioteca de estilos, voz, fonte, legendas, posição/tamanho, música/volume, movimento/transição, cor e thumbnail.
- **Produção e orçamento:** econômico/equilibrado/maior qualidade, limites soft/hard mensais e por vídeo, saída, preferência de mídia, revisão e providers por tarefa, retry/fallback.
- **Conexões:** contas Google/canais/autorização, catálogo por capacidade, disponibilidade, configuração/modelo, teste, estado de credencial e BYOK. Não confundir registro, credencial e seleção.
- **Conta e equipe:** organização, membros, papéis, preferências e aparência. Auditoria/consumo somente quando suportados.
- **Avançado:** motor, RenderPlan, QA, saúde, configuração efetiva sanitizada, eventos/logs, API e n8n. Controle de run permanece no vídeo.

Campos efetivamente consumidos pelo core precisam ser distinguidos de campos apenas declarados. Todo formulário terá contrato, validação e teste do consumidor; persistência sozinha não comprova aplicação ao vídeo.

## 6. Reuso e arquitetura
Reutilizar shell_v3, panel_home/new_video/videos/trends/analytics, panel_channels/channel_style/styles/connections/team/advanced e panel_production. UI/ViewModel compõe casos de uso existentes. Domínio puro; adapters para providers, Postgres, filesystem, FFmpeg e YouTube. Um RenderPlan, um renderer, um coordenador. n8n aciona os mesmos casos de uso, sem duplicar gates.

Precedência de estilo conforme V3.1: override do vídeo > override do canal > estilo escolhido > default do motor. Confirmar grupos governados pelo effective_config; exceção de cena só para campos suportados e resolvida no plano. Snapshot da execução é imutável; retry/resume não re-resolvem defaults.

## 7. N providers
Catálogo de produção vem do registry, com capabilities, modelos, disponibilidade e políticas. Configuração da conexão pertence à conta; preferência por tarefa pertence ao canal, com override explícito por vídeo. Credencial é referência autorizada resolvida no backend. A UI não adiciona suporte a um SDK apenas por cadastrar um nome.

Falha não pode mudar voz, qualidade mínima ou custo autorizado silenciosamente. Toda operação paga respeita reserva/idempotência e resultados ambíguos exigem reconciliação. Verificar guards efetivos: o registro histórico V3.1 menciona budget_guard desligado e não equivale a proteção ativa.

## 8. Escopo do protótipo entregue
Cobertura navegável e formulários locais de todas as áreas da matriz. Geração/QA/publicação/testes de conexão são simulações identificadas. Conteúdo salvo é recuperável no navegador, sem backend. Analytics usa métricas fixas ilustrativas; não é medição real. Referência BYOK não coleta chave. Previews de áudio/vídeo reais, upload, pesquisa de stock, OAuth e isolamento exigem integração futura.

## 9. Implementação e aceite
Primeiro reconciliar matriz de capacidades com rotas/consumidores atuais. Evoluir navegação e Settings preservando recursos; implementar VE-01–06 e editores por dependências; ligar aprovação/publicação; validar jornadas completas e negativas de isolamento. Não declarar entrega concluída se configurações são salvas mas não consumidas, ou se um recurso anterior desaparece sem decisão explícita.

As referências ElevenLabs e FStudio orientam continuidade de criação/edição e cenas. V3/V3.1 do próprio projeto continuam sendo a base funcional e visual principal.
