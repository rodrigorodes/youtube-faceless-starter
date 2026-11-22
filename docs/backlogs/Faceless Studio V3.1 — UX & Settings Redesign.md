# Faceless Studio V3.1 — UX & Settings Redesign

> **Status:** planejamento; implementação não autorizada nesta etapa.
> **Atualização:** 21/11/2026.
> **Escopo desta revisão:** análise do documento contra o código atual, com lacunas, melhorias, evidências e prioridades na seção 22. Foram executados 89 testes selecionados; os limites dessa validação estão descritos na seção 22.6. As seções 17–21 preservam o registro da investigação inicial.

## 1. Contexto

O Faceless Studio está evoluindo para uma plataforma SaaS de criação automatizada de conteúdo audiovisual para o YouTube.

Atualmente, a experiência do Studio apresenta excesso de informações técnicas, complexidade de navegação, configurações dispersas e características visuais mais próximas de um painel administrativo do que de uma ferramenta criativa.

A referência principal é a [proposta V3 em português](ux/faceless-studio-v3-proposta-ptbr.html), cuja UX já está sendo implementada. O [mockup original](ux/faceless-studio-v3-mockup.html) permanece como referência complementar. A V3.1 deve evoluir essa base e conciliar as entregas em andamento antes de propor substituições.

O Render Core possui contratos, domínios, serviços, APIs e mecanismos de configuração que precisam ser preservados e reutilizados.

## 2. Objetivo

Evoluir o Faceless Studio para a versão V3.1, alinhando a experiência de usuário proposta no mockup às capacidades reais do Render Core.

A solução deve:

- Simplificar a experiência de criação de vídeos.
- Reorganizar Settings de acordo com os domínios existentes.
- Reutilizar funcionalidades, contratos e APIs do Core.
- Ocultar complexidades técnicas desnecessárias.
- Permitir personalização independente por canal.
- Preservar a extensibilidade arquitetural.
- Preparar o produto para evolução como SaaS.
- Priorizar qualidade audiovisual e facilidade de uso.

**Princípio central: a complexidade do Core não deve ser refletida na complexidade da UX.**

## 3. Princípios obrigatórios

### Product Design

- Configure once.
- Reuse everywhere.
- Override when needed.
- Create with simplicity.
- Progressive disclosure.
- Content-first experience.

### Software Design

- KISS.
- YAGNI.
- Separation of concerns.
- Single source of truth.
- Explicit contracts.
- Composition over coupling.
- Backward compatibility.
- Provider agnostic.
- Tenant isolation.

Não introduzir abstrações, frameworks, serviços ou mecanismos de persistência sem necessidade comprovada.

## 4. Etapa inicial — Discovery e Gap Analysis

Antes de realizar alterações, analisar integralmente:

- A proposta principal `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html` e, como referência complementar, `faceless-studio-v3-mockup.html`.
- As entregas da UX V3 já realizadas e em andamento, evitando duplicação de tarefas.
- A implementação atual do Studio.
- Domínios e contratos do Render Core.
- APIs existentes.
- Repositórios e mecanismos de persistência.
- Resolução de estilos.
- Configuração de providers.
- Perfis de canais.
- Gestão de orçamento.
- Integração com YouTube.
- Gestão de credenciais e BYOK.
- Workflows do n8n.
- Render Plan e pipeline de produção.
- Autenticação, autorização e isolamento entre tenants.

Considerar inicialmente os seguintes arquivos, validando sua existência e responsabilidade na versão atual do repositório:

```text
renderer/app/studio/
├── domain/
│   ├── channel.py
│   ├── visual_style.py
│   ├── render_plan.py
│   ├── provider.py
│   ├── channel_budget.py
│   └── saas.py
├── application/
│   ├── config.py
│   ├── providers.py
│   ├── editorial.py
│   ├── render_compiler.py
│   └── production.py
├── adapters/
├── api/
└── composition.py
```

Para cada funcionalidade encontrada no mockup, classificar:

- IMPLEMENTED: funcionalidade existente e efetivamente aplicada.
- PARTIAL: contrato existente, mas aplicação incompleta.
- MISSING: funcionalidade inexistente.
- UI_ONLY: comportamento exclusivamente visual ou demonstrativo.
- DEPRECATED: funcionalidade cuja remoção ou substituição foi explicitamente decidida, com justificativa, impacto e plano de compatibilidade; não classificar assim apenas porque ficou fora da nova navegação.

Não considerar uma funcionalidade implementada apenas porque existe um campo no domínio ou um endpoint.

Rastrear o fluxo completo:

```text
UI → API → Use Case → Domain → Persistence → Pipeline
```

Produzir uma matriz de rastreabilidade contendo:

| Feature | UI | API | Domain | Pipeline Consumer | Status | Gap | Recommended Action |
|---|---|---|---|---|---|---|---|

## 5. Nova arquitetura de navegação

A navegação principal deverá ser simplificada para:

```text
Faceless Studio
├── Home
├── Create
├── Library
├── Ideas
├── Analytics
└── Settings
```

O Video Workspace deverá ser acessível a partir dos projetos e vídeos.

Remover da navegação principal informações relacionadas a:

- Infraestrutura.
- Providers técnicos.
- Documentação de APIs.
- n8n.
- Diagnósticos.
- Fases de desenvolvimento.
- Configurações internas do renderer.

Essas informações devem permanecer disponíveis somente nas áreas apropriadas e para usuários autorizados.

## 6. Settings V3.1

Reorganizar Settings utilizando a seguinte estrutura:

```text
Settings
├── Channels
├── Content Strategy
├── Brand & Style
├── Production
├── Connections
├── Workspace
└── Advanced
```

### 6.1. Channels

Responsabilidade: gerenciar os canais e seus destinos de publicação.

Funcionalidades:

- Listar canais.
- Criar e editar perfis.
- Selecionar canal ativo.
- Associar uma identidade YouTube.
- Configurar destino de publicação.
- Exibir status da conexão.
- Gerenciar múltiplos canais de forma independente.

Reutilizar `ChannelProfile` e os mecanismos existentes de identidade e conexão com YouTube.

O canal ativo deve ser consistente entre Home, Create, Library, Ideas, Analytics e Settings.

Garantir que a publicação utilize a identidade autorizada do canal selecionado.

### 6.2. Content Strategy

Responsabilidade: definir a identidade editorial de cada canal.

Mapear os campos existentes de `ChannelProfile`, incluindo, quando disponíveis:

- Strategy.
- Target audience.
- Content pillars.
- Narrative style.
- Language.
- Default duration.
- Call to action.

O usuário deve configurar essas informações uma única vez e reutilizá-las durante a criação dos vídeos.

Validar quais configurações são efetivamente consumidas pelo pipeline de geração de roteiro, assets e publicação.

Preparar contratos para consumo futuro pelo Finder / Intelligence, sem implementar esse módulo como parte obrigatória deste redesign.

### 6.3. Brand & Style

Responsabilidade: controlar a identidade audiovisual dos vídeos.

Organizar a experiência em:

- Visual Style Library.
- Narrator Voice.
- Captions.
- Music & Audio.
- Motion & Transitions.
- Thumbnail Identity.
- Brand Colors.

Utilizar previews visuais sempre que possível.

Reutilizar o domínio `VisualStyle`, suas versões e os mecanismos existentes de resolução de estilos.

Não disponibilizar funcionalidades que o Render Core ainda não suporta como se estivessem operacionais.

Opções não implementadas devem ser omitidas ou explicitamente identificadas como indisponíveis.

### 6.4. Customização de estilos por canal

Investigar o comportamento atual de compartilhamento dos estilos entre canais.

Evitar que alterações realizadas em um canal modifiquem involuntariamente outros canais que utilizam o mesmo estilo.

Avaliar uma solução baseada em composição:

```text
Visual Style Defaults
        ↓
Channel Overrides
        ↓
Video Overrides
        ↓
Effective Visual Style
        ↓
Render Plan
```

A precedência proposta é:

```text
Video Override
    > Channel Override
    > Selected Visual Style
    > Engine Default
```

Validar essa proposta contra os contratos atuais antes da implementação.

A solução deve garantir:

- Estilos compartilhados reutilizáveis.
- Personalização independente por canal.
- Overrides específicos por vídeo.
- Resolução determinística.
- Validação de configurações.
- Versionamento.
- Compatibilidade com vídeos existentes.
- Imutabilidade da configuração efetiva de uma execução já iniciada.
- Reprodutibilidade da renderização.

Avaliar se o Effective Visual Style deve compor um snapshot do Render Plan existente, evitando mecanismos paralelos de persistência.

### 6.5. Production

Responsabilidade: controlar qualidade, custo e estratégia de produção.

Apresentar configurações simples para o usuário:

- Economy.
- Balanced.
- High Quality.

Esses perfis devem corresponder a estratégias reais de execução e seleção de providers.

Não criar perfis meramente visuais.

Reutilizar, quando aplicável:

- ProjectConfig.
- BudgetLimits.
- Provider Registry.
- Provider Routing.
- Cost Estimation.
- Usage Tracking.

Permitir configurar:

- Limite mensal.
- Limite por vídeo.
- Alertas de orçamento.
- Providers preferenciais.
- Estratégia de qualidade.

As configurações avançadas de modelos e roteamento devem utilizar progressive disclosure.

Não realizar fallback silencioso que viole orçamento ou requisitos mínimos de qualidade.

### 6.6. Connections

Responsabilidade: gerenciar conexões externas e disponibilidade dos providers.

Organizar integrações por capacidade:

```text
Publishing
└── YouTube

Content Generation
├── Text Providers
├── Image Providers
└── Video Providers

Audio
├── Voice Providers
└── Music Providers

Intelligence
└── Configured Intelligence Providers

Built-in Engine
├── FFmpeg
└── Piper
```

As opções apresentadas devem ser obtidas dos providers realmente registrados no sistema, evitando listas estáticas na interface.

Cada integração deverá apresentar, quando suportado:

- Nome.
- Capacidade.
- Disponibilidade.
- Status da conexão.
- Configuração.
- Teste de conexão.
- Consumo e custo associado.
- Gerenciamento seguro de credenciais.

Separar explicitamente:

- Disponibilidade do provider.
- Credenciais do provider.
- Seleção do provider.
- Estratégia de roteamento.
- Configuração por canal.

Preservar o modelo BYOK quando existente.

Nunca retornar API keys completas, tokens OAuth ou outros segredos ao frontend.

### 6.7. Workspace

Responsabilidade: configurações organizacionais e preferências pessoais.

Organizar:

- Organization.
- Team.
- Roles & Permissions.
- Usage.
- Personal Preferences.
- Appearance.

Garantir separação entre os seguintes escopos:

```text
Organization
    └── Workspace Settings

User
    └── Personal Preferences

Channel
    ├── Content Strategy
    ├── Brand & Style
    └── Production Preferences

Video
    └── Video Overrides

Execution
    └── Effective Configuration Snapshot
```

Reutilizar os mecanismos SaaS existentes.

Não duplicar entidades de usuários, organizações, membros ou credenciais.

### 6.8. Advanced

Responsabilidade: diagnóstico, automação e configurações técnicas.

Disponibilizar, conforme suporte real e permissões:

- Render Engine.
- Render Plan.
- Quality Assurance.
- Provider Health.
- Production Diagnostics.
- Automation.
- n8n.
- API Documentation.
- Logs e referências de execução.

As informações devem ser predominantemente diagnósticas.

Não expor configurações internas que possam comprometer a estabilidade, segurança ou integridade do Core.

Controles de execução como pause, resume, retry e cancel devem permanecer associados ao Video Workspace, quando suportados.

## 7. Design System

Evoluir o design visual com foco em um Creative Studio profissional.

### Direção visual

- Minimalista.
- Moderna.
- Profissional.
- Content-first.
- Baixa densidade visual.
- Hierarquia clara.
- Consistência entre páginas.
- Dark mode como experiência principal.
- Light mode opcional.

### Paleta proposta

```css
--background: #0D0E11;
--surface: #15171C;
--surface-hover: #1D2027;
--border: #272A31;
--text-primary: #F4F4F5;
--text-secondary: #A1A1AA;
--primary: #8B5CF6;
--success: #22C55E;
--danger: #EF4444;
```

Validar contraste e acessibilidade.

Evitar:

- Excesso de gradientes.
- Excesso de cores de destaque.
- Cards dentro de cards.
- Bordas desnecessárias.
- Badges em todos os elementos.
- Excesso de métricas.
- Informações técnicas na Home.
- Formulários extensos durante a criação.
- Aparência de dashboard administrativo.
- Campos desabilitados expondo limitações internas.

Criar componentes reutilizáveis dentro da stack atual do projeto.

Não introduzir um novo framework frontend apenas para realizar o redesign.

## 8. Simplificação da criação de vídeos

A experiência principal deve seguir:

```text
Idea
  ↓
Format
  ↓
Style
  ↓
Create
  ↓
Sources / Evidence
  ↓
Production
  ↓
Review
  ↓
Publish
```

**Restrição atual verificada:** criar o registro do vídeo não equivale a iniciar uma produção autônoma. O pipeline exige fontes aproveitáveis e não possui pesquisa automática operacional no caminho inspecionado. Preservar a etapa de fontes na página do vídeo e explicar o próximo passo; uma tendência pode sugerir o tema, mas não garante evidências suficientes.

Na criação inicial, solicitar somente informações essenciais:

- Tema ou ideia do vídeo.
- Formato: YouTube Video ou Short.
- Estilo visual, utilizando o padrão do canal por default.

As demais informações devem ser resolvidas automaticamente:

- Canal ativo.
- Idioma.
- Público-alvo.
- Narrativa.
- Voz.
- Legendas.
- Música.
- Providers.
- Orçamento.
- Estratégia editorial.

Permitir ajustes adicionais através de Advanced Options, sem comprometer o fluxo principal.

## 9. Settings API e integração com o Core

Reutilizar os endpoints e casos de uso existentes sempre que possível.

Avaliar a necessidade de View Models ou uma camada fina de composição para atender à UX.

```text
Studio UI
    ↓
Settings API / View Models
    ↓
Existing Application Use Cases
    ↓
Domain Contracts
    ↓
Repositories / Providers
    ↓
Production & Render Core
```

Caso seja necessária uma API agregadora:

- Não criar uma nova fonte de verdade.
- Não duplicar contratos de domínio.
- Não duplicar regras de negócio.
- Não acessar diretamente a persistência a partir da UI.
- Não implementar lógica de renderização na camada de apresentação.

Validar transações, concorrência, versionamento e consistência das alterações de configuração.

## 10. Compatibilidade com o pipeline

Preservar as fronteiras arquiteturais existentes.

```text
Faceless Studio
        ↓
Production Workflow
        ↓
Script → Assets → Voice
        ↓
Render Plan
        ↓
Render Compiler
        ↓
FFmpeg
        ↓
Quality Assurance
        ↓
Publish
```

O n8n deve continuar atuando como orquestrador, conforme seu papel atual.

A interface não deve se tornar responsável pela orquestração técnica do pipeline.

Validar que as configurações do canal sejam resolvidas corretamente durante execuções iniciadas pela UI, API ou n8n.

Preservar a independência do Render Core em relação a tecnologias de interface e orquestração.

## 11. Estratégia de implementação

Dividir a evolução em fases incrementais.

### F0 — Discovery

Conciliar primeiro a V3 em andamento com os requisitos V3.1. O marco de saída é o backlog reconciliado e a matriz de evidências.

- Inventário das funcionalidades.
- Gap Analysis.
- Mapeamento UI/Core.
- Identificação de riscos.
- Validação das fronteiras arquiteturais.

### F1 — UX Foundation

- Evolução do Design System existente, conforme gaps comprovados.
- Complementação do App Shell existente, preservando as entregas da V3.
- Navegação simplificada.
- Contexto do canal ativo.
- Componentes compartilhados.

### F2 — Settings Integration

- Channels.
- Content Strategy.
- Connections.
- Workspace.
- Integração com APIs existentes.

### F3 — Brand & Style

Depende das decisões de resolução de F4 para os controles de personalização. A biblioteca e os controles já suportados podem ser reaproveitados antes disso.

- Biblioteca visual de estilos.
- Configurações efetivamente suportadas.
- Previews.
- Seleção de identidade audiovisual.

### F4 — Configuration Resolution

Antecipar o desenho dos contratos e as decisões desta fase, antes dos formulários de overrides em F3. A numeração das fases não representa uma sequência estritamente linear.

- Channel Overrides.
- Video Overrides.
- Effective Visual Style.
- Integração com Render Plan.
- Reprodutibilidade das execuções.

### F5 — Production Preferences

Começar pelo mapeamento dos perfis, providers e limites existentes. Só oferecer Economy, Balanced e High Quality quando houver correspondência verificável com execução e orçamento.

- Perfis de qualidade.
- Configuração de providers.
- Controle de orçamento.
- Validação de roteamento.

### F6 — Creative Experience

Dividir em entregas menores. Priorizar criar → informar fontes → produzir → revisar → publicar; tratar Ideas e Analytics conforme dados e capacidades efetivamente disponíveis.

- Home simplificada.
- Create Video.
- Video Library.
- Video Workspace.
- Ideas.
- Analytics.

### F7 — Audiovisual Evolution

Planejar separadamente os gaps que exigem evolução real do Render Core, incluindo, quando aplicável:

- Dynamic Captions.
- Transições.
- Preview de voz.
- Motion presets.
- Thumbnail Identity.
- Visual Quality Evaluator.

Não implementar essas capacidades apenas para simular completude na interface.

## 12. Testes obrigatórios

Garantir cobertura para:

- Persistência das configurações.
- Resolução de estilos.
- Precedência de overrides.
- Isolamento entre canais.
- Isolamento entre organizações.
- Autorização.
- Proteção de credenciais.
- Compatibilidade das APIs.
- Seleção correta do destino YouTube.
- Limites de orçamento.
- Resolução de providers.
- Reprodutibilidade do Render Plan.
- Compatibilidade com vídeos existentes.
- Execução do pipeline pelo n8n.
- Navegação e fluxos principais da UI.
- Estados loading, empty, error e success.

Criar testes de regressão antes de alterar comportamentos existentes do Core.

## 13. Entregáveis

Entregas futuras previstas após o planejamento: criar a documentação do projeto dentro de:

```text
docs/projects/faceless-studio-v3.1/
├── README.md
├── 01-discovery.md
├── 02-gap-analysis.md
├── 03-ux-design.md
├── 04-settings-architecture.md
├── 05-domain-mapping.md
├── 06-api-contracts.md
├── 07-configuration-resolution.md
├── 08-implementation-plan.md
├── 09-test-strategy.md
├── 10-acceptance-criteria.md
├── adr/
│   ├── ADR-001-studio-core-boundaries.md
│   ├── ADR-002-settings-source-of-truth.md
│   └── ADR-003-style-resolution.md
└── mockups/
    └── faceless-studio-v3.1.html
```

O mockup HTML deverá:

- Possuir navegação funcional.
- Representar todas as páginas principais.
- Representar todas as seções de Settings.
- Utilizar os conceitos reais do domínio.
- Diferenciar dados demonstrativos de funcionalidades operacionais.
- Permitir simular configurações por canal.
- Demonstrar a precedência de configurações.
- Servir como especificação funcional para a implementação.

Organizar o roadmap em tarefas pequenas, independentes quando possível, contendo:

- Objetivo.
- Escopo.
- Arquivos impactados.
- Dependências.
- Critérios de aceite.
- Estratégia de testes.
- Riscos.
- Estratégia de rollback, quando necessária.

## 14. Restrições

- Não reescrever o Render Core.
- Não alterar funcionalidades existentes sem justificativa.
- Não introduzir outro orquestrador.
- Não duplicar configurações.
- Não persistir dados fictícios como configuração real.
- Não criar providers falsos.
- Não acoplar o Finder ao renderer.
- Não expor segredos ao frontend.
- Não adicionar complexidade apenas por antecipação de requisitos futuros.
- Não remover capacidades existentes apenas para simplificar a navegação.
- Não implementar alterações destrutivas sem análise de impacto e estratégia de migração.

## 15. Critérios de sucesso

O projeto será considerado bem-sucedido quando:

1. O usuário conseguir criar um vídeo sem conhecer a arquitetura interna.
2. Settings estiver alinhado aos contratos reais do Core.
3. Cada canal possuir sua identidade editorial e audiovisual independente.
4. Estilos compartilhados puderem ser reutilizados sem efeitos colaterais.
5. As configurações forem aplicadas de maneira determinística ao pipeline.
6. Providers e integrações continuarem extensíveis.
7. A criação permanecer simples mesmo com a evolução do motor.
8. Os fluxos existentes continuarem funcionando.
9. O Studio apresentar uma identidade visual profissional, consistente e orientada à criação.
10. Nenhuma nova fonte de verdade desnecessária for introduzida.

## 16. Instrução de execução inicial

**Escopo autorizado no momento:** planejamento e atualização deste documento. Não implementar código de produção nem criar o mockup V3.1 nesta rodada. A lista abaixo descreve o trabalho futuro de discovery e especificação; sua presença neste backlog não inicia sua execução.

Na futura etapa de discovery e especificação, realizar:

1. Discovery do repositório.
2. Análise do mockup existente.
3. Gap Analysis.
4. Proposta arquitetural.
5. Documentação do projeto.
6. Mockup HTML V3.1 navegável.
7. Roadmap de implementação.
8. Identificação de decisões arquiteturais pendentes.

Não iniciar alterações no código de produção nesta etapa.

Ao finalizar, apresentar o resultado da investigação, as evidências encontradas no código, os gaps identificados e as decisões que precisam ser validadas antes da implementação.

Priorizar evidências do repositório sobre as hipóteses apresentadas neste documento.

**O Faceless Studio deve ser simples na superfície, poderoso no Core e extensível em sua arquitetura.**

## 17. Evidências da investigação inicial

Leitura realizada em 21/11/2026. O histórico consultado tinha `bf2c6b1` como commit mais recente. Esta seção distingue evidência estática de capacidade validada de ponta a ponta. Comentários, contratos e nomes de testes são pistas; não comprovam isoladamente execução correta.

| Tema | Evidência encontrada | Implicação para o planejamento |
|---|---|---|
| UX V3 em andamento | Histórico: `383a603` (fundação), `16e38e1` (rotas de configurações), `bde27c6` (tema claro), `332d713` e `bf2c6b1` (simplificação visual e textual). | Conciliar o trabalho entregue; F1 não começa do zero. Validar o comportamento atual antes de marcar tarefas como concluídas. |
| Settings atual versus proposta | O HTML pt-BR apresenta Identidade do canal, Canais, Conexões, Estúdio e Avançado. | Mapear cinco áreas para as sete propostas sem perder capacidades ou quebrar acessos. |
| Perfil editorial | `renderer/app/studio/domain/channel.py`, `ChannelProfile`: estratégia, idioma, público, pilares, narrativa, duração e CTA, além de estilo e destino YouTube. | Rastrear consumo campo a campo; presença no contrato não prova aplicação no roteiro ou publicação. |
| Seleção de estilo | `application/video_style.py` implementa leitura da herança e gravação de `style_id`; `domain/visual_style.py` contém `effective_style_id` e `resolve_style`; `composition.py` liga a resolução ao vídeo. | A substituição do estilo inteiro por vídeo já tem caminhos existentes. Overrides parciais de parâmetros são uma decisão distinta. |
| Snapshot do plano | `domain/render_plan.py`, `StyleSnapshot`: referência por `style_id` e `version`. | Não presumir que já existe snapshot completo de toda configuração efetiva. Investigar revisões, consumo e congelamento na execução. |
| Capacidades audiovisuais | `ResolvedStyle` carrega motion, music, transition, caption, palette e voice; a documentação local distingue transições carregadas de transições aplicadas. | Confirmar cada consumidor no builder, compilador e executor antes de oferecer controles operacionais. |
| Fontes obrigatórias | `application/production.py`, `RESEARCH_REASON`, informa ausência de pesquisa automática; `application/editorial.py` rejeita geração sem fontes com claims verificáveis. | Preservar fontes no fluxo e distinguir criação do vídeo de produção. |
| Providers e orçamento | `application/providers.py` contém listagem, teste e roteamento; `application/channel_budget.py` contém leitura e gravação de limites. | Reaproveitar os serviços e verificar enforcement no pipeline antes de criar perfis de UX. |
| Conexões YouTube | `application/connections.py` contém consentimento, listagem, vínculo e revogação. | Reutilizar as entidades e validar identidade autorizada, escopo e destino efetivo da publicação. |
| SaaS e BYOK | `domain/saas.py` contém membros, permissões, erros de acesso entre tenants e contratos BYOK. | Auditar autorização e isolamento em endpoints e repositórios; não considerar segurança resolvida pela existência dos contratos. |

Caminhos abreviados nesta tabela são relativos a `renderer/app/studio/` quando começam em `domain/`, `application/` ou `composition.py`.

A especificação `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` também deve ser conciliada: ela documenta uma organização anterior de canais, estilos e conexões. Suas propostas não devem ser tratadas automaticamente como estado atual do produto.

## 18. Plano de atividades de planejamento

| ID | Atividade | Entrega e critério de conclusão | Dependências |
|---|---|---|---|
| P01 | Consolidar o trabalho atual | Inventário de entregas concluídas, em andamento e pendentes da V3, confrontando código, histórico e backlog; sem tarefas duplicadas. | Nenhuma. |
| P02 | Discovery por capacidade | Caminhos UI → API → caso de uso → domínio → persistência → consumidor, com arquivos e evidências; registrar caminhos não encontrados. | P01. |
| P03 | Matriz de gaps | Classificação por capacidade com justificativa, impacto e ação recomendada. Lacunas de investigação ficam explicitamente pendentes. | P02. |
| P04 | Navegação e Settings | Mapeamento das cinco áreas atuais para as sete propostas, preservando funções e acessos existentes; linguagem em português. | P01 e P03. |
| P05 | Escopos e resolução | Proposta para organização, usuário, projeto/canal, vídeo e execução; precedência, versionamento, concorrência, compatibilidade e congelamento. | P02 e P03. |
| P06 | Produção e integrações | Mapeamento de perfis, providers, orçamento, BYOK e identidade YouTube ao comportamento real e às permissões. | P02 e P03. |
| P07 | Fluxos criativos | Especificação de criação, fontes, produção, revisão e publicação, com loading, vazio, erro, sucesso e ações suportadas por estado. | P04, P05 e P06. |
| P08 | Roadmap e aceite | Tarefas pequenas com objetivo, escopo, arquivos impactados, dependências, aceite, testes, riscos e rollback quando aplicável. | P03 a P07. |

O primeiro marco é P01–P03: **backlog reconciliado com a UX atual e matriz de evidências**. Não fechar novos contratos ou controles dependentes de capacidades ainda não rastreadas.

## 19. Transição proposta de Settings

Este mapeamento é uma proposta para validação no discovery, não uma decisão de migração já implementada.

| Área atual do mockup pt-BR | Destino proposto na V3.1 | Cuidados |
|---|---|---|
| Identidade do canal | Estratégia de conteúdo + Marca e estilo | Separar identidade editorial da audiovisual; manter a biblioteca de estilos claramente compartilhada. |
| Canais | Canais | Preservar seleção de canal, perfil e destino de publicação. |
| Conexões | Conexões | Distinguir disponibilidade, credenciais, seleção e roteamento de providers. |
| Estúdio | Workspace / Estúdio | Separar preferências pessoais das organizacionais; revisar cada configuração atual antes de mover. |
| Avançado | Avançado | Preservar diagnósticos autorizados e manter ações de execução no contexto do vídeo. |
| Custos e providers dispersos | Produção | Mapear localização e comportamento atuais; não duplicar persistência. |

Manter a base visual existente, incluindo acessibilidade e tema claro já trabalhados. A paleta da seção 7 é referência de direção e deve ser conciliada com os tokens atuais, sem regressões ou substituição automática.

## 20. Decisões pendentes

| ID | Decisão | Orientação inicial e investigação necessária |
|---|---|---|
| D01 | Sete grupos de Settings e nomes em português | Recomenda-se a estrutura V3.1, validando a distribuição de funções da UX em andamento. |
| D02 | Editar estilo compartilhado versus personalizar canal | Ações distintas e explícitas; personalização do canal não deve alterar outros consumidores. Definir os contratos antes dos formulários. |
| D03 | Acompanhar novas versões ou fixar versão do estilo | Definir política para novos vídeos e alterações de canal; preservar referências históricas e reprodutibilidade. |
| D04 | Momento do congelamento da configuração | Investigar quando roteiro, assets, voz e render leem configurações. Definir retry, retomada e nova produção sem presumir que congelar só o Render Plan cobre todas as etapas. |
| D05 | Canal ativo versus projeto | Mapear a relação atual, persistência da seleção, filtragem, autorização e comportamento ao trocar de canal durante a edição. |
| D06 | Pilares editoriais versus pilares de tendências | Comparar os contratos e usos; decidir se compartilham dados, referências ou permanecem distintos sem duplicação inconsistente. |
| D07 | Fontes no fluxo de criação | Preservar etapa explícita até haver pesquisa automática operacional. Definir como a origem de uma tendência chega ao vídeo e como a suficiência da fonte é validada. |
| D08 | Perfis de produção | Relacionar nomes de UX a estratégias existentes, custos e qualidade; definir falhas e fallbacks permitidos. |
| D09 | Conteúdo do snapshot efetivo | Avaliar extensão compatível do Render Plan e referências versionadas existentes, evitando nova persistência paralela. |
| D10 | Overrides parciais | Definir ausência, null, limpeza, listas, campos desconhecidos e validação; reconciliar com `style_id` existente e valores padrão do projeto/motor. |

Nenhuma decisão desta tabela está automaticamente aprovada por constar no documento.

## 21. Verificação e limites da revisão inicial

Registro histórico da primeira leitura. A análise posterior e os testes executados estão na seção 22.

- Foi realizada leitura inicial do material, do mockup pt-BR, de contratos e serviços selecionados e do histórico recente.
- Não foi concluído o rastreamento integral de todas as capacidades, especialmente persistência, autorização, isolamento, enforcement de orçamento e execuções via n8n.
- Não foram executados testes de produto nesta revisão documental nem validados fluxos em navegador.
- Não foi criado mockup V3.1 e não houve alteração de código de produção.
- O discovery deve reutilizar e avaliar os testes existentes, incluindo estilos, Render Plan, orçamento, conexões, SaaS, produção e configurações. Novas regressões devem preceder mudanças de comportamento no Core.
- Estimativas de esforço e arquivos exatos de cada tarefa de implementação serão fechados após P01–P03, quando o escopo remanescente estiver comprovado.

## 22. Gap Analysis contra o código atual — 21/11/2026

### 22.1. Escopo e conclusão

Análise estática do checkout em `bf2c6b1`, cobrindo navegação, criação, perfis, estilos, composição, render, orçamento, providers, credenciais, publicação, analytics e workflows versionados. Foram executados testes selecionados de domínio e estrutura de workflows; não houve acesso ao banco operacional, chamadas a providers, publicação de vídeos ou alteração de produção.

**Conclusão:** existe uma base funcional reaproveitável, mas a V3.1 exige integração de configurações com execução, além da reorganização visual. Os principais bloqueios são identidade YouTube inconsistente entre caminhos, orçamento mensal com escopos diferentes, ausência de isolamento multi-tenant em runtime, configurações editoriais não consumidas e configuração de render lida durante a execução.

Esta seção amplia e, quando necessário, corrige as observações preliminares das seções 17–21. Os caminhos abaixo são relativos à raiz do repositório; números de linha referem-se ao checkout analisado.

Prioridades: **P1** = resolver antes de prometer a capacidade correspondente na V3.1; **P2** = integração e melhoria da experiência; **P3** = evolução audiovisual separada. P1 de tenancy é bloqueio para operação SaaS multi-tenant, não afirmação de que o produto mono-operador atual promete esse isolamento.

### 22.2. Lacunas prioritárias e melhorias

#### G01 — P1 — Orçamento mensal do canal usa gasto global na reserva

- **Requisito:** canais independentes e limites efetivos por canal/vídeo (§6.5).
- **Evidência:** `composition.py:158` resolve limites pelo projeto do vídeo; `application/budget.py:295` os passa à reserva. Porém, `adapters/postgres/budget_repo.py:55–65` soma gastos e reservas mensais sem filtro por projeto/organização. Já `adapters/postgres/channel_budget_repo.py:69` monta o resumo exibido filtrando por `v.project_id`.
- **Efeito:** o gasto de A pode impedir uma operação de B mesmo quando o resumo de B está abaixo do seu limite. Exemplo derivado da consulta: A gastou US$ 8; B tem limite mensal US$ 5 e gasto zero; a reserva de US$ 1 de B compara 8 + 1 com 5.
- **Lacuna adicional:** `Settings.budget_guard` é `False` por padrão (`composition.py:322`). A aplicação dos limites específicos via `PaidOperationGuard` depende dessa opção (`composition.py:499`). Isso não significa ausência de toda proteção: o `CostGuard` legado continua presente, com limites da composição.
- **Melhoria:** definir separadamente teto global/organizacional e teto de canal; atribuir operações e reservas ao escopo correto, incluindo chamadas sem vídeo; refletir na UI qual proteção está ativa. Preservar atomicidade e reconciliação.
- **Aceite/teste:** gastos de A não consomem o teto de B; teto global, quando existir, vale separadamente; reservas concorrentes respeitam ambos; UI e guard mostram/avaliam o mesmo escopo; testar guard ligado e desligado.

#### G02 — P1 — Conexões YouTube novas não alimentam o resolvedor de token do publicador

- **Requisito:** publicar pela identidade autorizada do canal selecionado (§6.1/6.6).
- **Evidência:** `application/connections.py:210` salva tokens em `grant_scope(grant.id)`. A composição do publicador (`composition.py:553`) usa `EnsureAccessToken` do repositório antigo por projeto, com fallback de ambiente. `application/youtube_oauth.py:217` resolve o cofre por projeto, não pelo grant escolhido. `adapters/channel_analytics.py:33` também usa associação/token antigos por projeto.
- **Efeito:** conectar e vincular um canal na nova área não basta, por si só, para fornecer a credencial ao publicador/analytics. O gate nativo pode bloquear divergências, mas não resolve a seleção da credencial correta.
- **Melhoria:** resolver credencial pela relação projeto → perfil → destino YouTube → autorização vigente; reutilizar a renovação e o SecretStore, sem copiar tokens entre modelos como solução permanente. Documentar migração do caminho legado.
- **Aceite/teste:** uma conexão feita apenas pelo fluxo novo publica e coleta métricas no canal vinculado; expiração renova o grant correto; revogação impede uso; canal A nunca usa credencial de B.

#### G03 — P1 — Publicação nativa e n8n não aplicam o mesmo gate de destino

- **Evidência:** `application/publication_execution.py:191` compara destino e identidade do token antes do upload, mas preserva o caminho legado quando não existe destino. `application/publishing.py:109`, `ClaimPublication`, prepara o upload sem receber repositórios de perfis/autorizações. `workflows/03-publish-approved.json` usa `/studio/publications/claim` e faz upload diretamente com credencial `youTubeOAuth2Api` do n8n.
- **Efeito:** a proteção do executor nativo não cobre o caminho do workflow. O workflow versionado está inativo; a análise não afirma que ele esteja em uso em produção.
- **Melhoria:** definir uma política comum para ambos os caminhos e para perfis sem destino. Preferir manter n8n como orquestrador chamando o executor protegido do Core, ou introduzir contrato equivalente que verifique o destino efetivo antes do upload externo. Não manter verificações divergentes.
- **Aceite/teste:** usar credencial de B numa publicação destinada a A bloqueia antes do envio em todos os caminhos; ausência de destino tem comportamento explícito e compatível com migração planejada.

#### G04 — P1 para SaaS — Tenancy existe no modelo, não no acesso operacional completo

- **Evidência:** `api/routes.py:117` autentica um operador Basic ou worker Bearer; `api/routes.py:829` aplica essas dependências ao router. O RBAC de equipe resolve o operador configurado (`api/routes.py:1310`). Listagens em `adapters/postgres/channel_repo.py:99` e `visual_style_repo.py:75` não filtram por tenant. A migração `0027_saas_multiuser_byok.sql` e `application/saas.py:47` declaram o runtime mono-usuário.
- **Efeito:** criar organizações e membros não fornece isolamento de vídeos, estilos, projetos e configurações para usuários distintos.
- **Melhoria:** separar explicitamente o marco de UX mono-operador do marco SaaS. Para SaaS, propagar identidade/organização autenticada até casos de uso, consultas, jobs e cofre, com autorização por recurso. Não duplicar entidades existentes.
- **Aceite/teste:** leituras e mutações cruzadas, IDs conhecidos de outra organização e execuções de worker são recusados; listagens e bibliotecas respeitam o escopo autorizado.

#### G05 — P1 — Estratégia editorial é persistida, mas não governa o roteiro

- **Evidência:** `domain/channel.py:179` e `adapters/postgres/channel_repo.py` armazenam estratégia, público, pilares, narrativa, idioma, duração e CTA. `application/editorial.py:150` fixa português do Brasil no prompt; `GenerateScript` recebe tema, claims e quantidade de cenas. `application/longform.py:127/141` também fixa pt-BR, com duração padrão de 480 s. O wiring editorial em `composition.py:503` não injeta o perfil do canal.
- **Efeito:** salvar idioma inglês, público ou CTA no perfil não altera esses geradores. O texto da UI não pode apresentar esses campos como preferências já aplicadas à criação.
- **Melhoria:** compor um contexto editorial tipado a partir das fontes existentes, com defaults legados explícitos. Usá-lo em short e long-form, preservando a restrição factual das fontes. Rastrear também prompts de imagem, metadados e thumbnail antes de prometer aplicação ampla.
- **Aceite/teste:** canais com idiomas, públicos e CTAs diferentes produzem entradas distintas para o modelo; ausência de perfil mantém o comportamento anterior; configurações editoriais não autorizam fatos inventados.

#### G06 — P1 — Configuração pode mudar entre voz e render da mesma execução

- **Evidência:** `composition.py:194` busca versões atuais dos estilos. `application/render.py:191` resolve voz; após sintetizar as cenas, `render.py:229` resolve o estilo novamente. `domain/production_run.py:384` não contém snapshot efetivo; `StyleSnapshot` em `domain/render_plan.py:435` contém ID/versão, não todo o contexto de produção.
- **Efeito:** uma alteração de estilo durante TTS pode fazer a voz usar uma versão e o render/snapshot outra. Retry e nova execução também dependem de leituras atuais. A existência de histórico de revisões não congela automaticamente as entradas.
- **Melhoria:** resolver uma configuração coerente antes do primeiro efeito de produção e definir como referenciá-la no run/Render Plan existente. Evitar um mecanismo paralelo de persistência; avaliar compatibilidade de schema e reuso das revisões.
- **Aceite/teste:** modificar canal/estilo entre duas etapas não muda a execução iniciada; retry segue a política definida; nova produção pode adotar configuração nova; rastrear versão de voz, editorial, providers e parâmetros de render.

#### G07 — P2 — Override atual troca o estilo inteiro; não personaliza parâmetros do canal

- **Evidência:** `application/video_style.py`, `domain/visual_style.py:301` e `composition.py:194` selecionam `Video.style_id > ChannelProfile.style_id > padrão`. `resolve_style` escolhe um objeto inteiro, sem mesclar um patch do canal/vídeo.
- **Efeito:** a precedência proposta no documento não está implementada. Editar um estilo compartilhado afeta futuras resoluções de todos os consumidores.
- **Melhoria:** manter seleção de estilo como capacidade existente; especificar overrides parciais como incremento distinto. Definir campos permitidos, ausência/null, limpeza, listas, defaults e versão. Separar na UI edição da biblioteca e personalização local.
- **Aceite/teste:** dois canais compartilham uma base e apenas um muda a voz; o outro permanece igual; vídeo pode sobrepor e voltar a herdar; configurações inválidas são recusadas.

#### G08 — P1 — Arquivar estilo limpa vínculos sem versionar o perfil afetado

- **Evidência:** `adapters/postgres/visual_style_repo.py:132`, `_clear_links`, atualiza `channel_profiles.style_id = NULL` e `videos.style_id = NULL`. A atualização dos perfis não incrementa `version` nem insere revisão, ao contrário de `channel_repo.update`. O comentário local declara essa escolha intencional; ela precisa ser reavaliada frente aos requisitos de auditoria e configuração imutável da V3.1.
- **Efeito:** o estado do perfil muda sem mudança da versão usada para concorrência e auditoria; futuros renders caem no padrão. A V3.1 precisa explicitar essa consequência, especialmente com execuções ativas.
- **Melhoria:** definir política de arquivamento compatível com histórico e runs congelados; se desvincular perfis, registrar revisões e conflitos na mesma transação. Considerar manter referências históricas sem permitir novas seleções.
- **Aceite/teste:** arquivamento preserva rastreabilidade, não altera um run iniciado e não permite que uma edição com versão antiga sobrescreva silenciosamente o novo estado.

#### G09 — P2 — Perfil econômico calcula recomendação, mas não escolhe o provider executado

- **Evidência:** `application/channels_page.py:119/154` usa `economic_profile` para montar decisões na tela; `application/providers.py:87` expõe roteamento. A execução em `composition.py:470` usa `ProjectConfig.resolve` e `_build_provider`, sem consumir essa decisão. Os enums existentes são `ECONOMY`, `BALANCED` e `PREMIUM`.
- **Efeito:** salvar Economy não garante execução pelo provider indicado no roteamento. Renomear Premium para High Quality não corrige a integração.
- **Melhoria:** definir política entre preferência explícita, perfil econômico, disponibilidade, custo conhecido e qualidade mínima; executar a decisão real e registrá-la. Catálogo inclui `demo` e `placeholder`: excluí-los de perfis de produção ou identificá-los explicitamente como demonstração.
- **Aceite/teste:** provider executado coincide com a decisão registrada; indisponibilidade ou custo desconhecido não provoca downgrade/fallback silencioso; limites de qualidade e orçamento são verificáveis.

#### G10 — P2 — BYOK tem gestão, mas não está ligado à construção dos providers

- **Evidência:** `application/saas.py` implementa registro, rotação, revogação e `RecordKeyUse`. A composição liga as mutações à API, mas não liga `RecordKeyUse` nem um resolvedor de chave organizacional ao `provider_for`. Providers continuam construídos a partir das configurações de deployment/projeto.
- **Efeito:** cadastrar uma chave no workspace não prova que ela seja usada ou que o consumo seja atribuído à organização correspondente.
- **Melhoria:** integrar resolução autorizada da chave no backend ao provider escolhido, reutilizando SecretStore e auditoria; invalidar caches pertinentes na rotação/revogação. Mostrar separadamente “chave cadastrada” e “credencial utilizada”.
- **Aceite/teste:** operação usa apenas a chave da organização autorizada, registra uso e falha após revogação; respostas e erros nunca devolvem segredos.

#### G11 — P2 — Canal ativo não é contexto consistente entre rotas

- **Evidência:** o seletor do painel navega com `project_id` (`api/panel.py:3006`), mas `build_sidebar_nav` monta URLs sem esse parâmetro (`panel.py:115`). `/panel/videos` redireciona para `/panel#videos` sem preservá-lo (`api/routes.py:1262`). `BuildChannelsPage.execute` escolhe o primeiro projeto quando o parâmetro não chega (`application/channels_page.py:97`).
- **Efeito:** a navegação pode perder a seleção e abrir outro canal ou um agregado. O seletor visual não constitui contexto global persistido.
- **Melhoria:** definir um contrato único para propagação e validação do canal ativo, incluindo deep links e troca durante formulários. Manter projeto como identidade técnica atual: a migração `0016_channel_profiles.sql` define no máximo um perfil por projeto.
- **Aceite/teste:** selecionar B e navegar por todas as áreas mantém B; vídeo existente usa sempre seu projeto proprietário; seleção inválida/sem autorização tem tratamento explícito.

#### G12 — P2 — Settings e criação ainda divergem da proposta

- **Evidência:** código possui quatro aliases de Settings (`api/routes.py:1271`): canais, estilos, conexões e equipe. A sidebar mantém os quatro destinos separados e ainda expõe API Docs e n8n Workflows (`api/panel.py:183`), em desacordo com a navegação técnica restrita proposta no §5. O mockup pt-BR tem cinco áreas e V3.1 prevê sete. Library é redirecionamento para o Início. O wizard (`api/panel_production.py:325–345`) expõe público, duração, estilo e idioma desabilitados; a mensagem de estilo afirma ausência de escolha por vídeo, embora `SetVideoStyle` já exista.
- **Melhoria:** mapear três estados distintos — código, mockup V3 e alvo V3.1. Consolidar Settings, preservar rotas compatíveis e contexto; reduzir Create a campos operacionais, com herança real e vínculo à página do vídeo para fontes. Reutilizar escolha de estilo existente e atualizar mensagens obsoletas.
- **Aceite/teste:** seis destinos principais, sete áreas quando sustentadas por capacidade real; nenhum campo demonstrativo salva dados; origem de cada valor herdado é clara; fontes continuam necessárias antes da geração.

#### G13 — P2 — Pilares editoriais e pilares de coleta são entidades distintas

- **Evidência:** `ChannelProfile.pillars` é uma lista textual em `channel_profiles`; `adapters/postgres/category_repo.py` persiste `project_categories` com nome e queries. Tendências usam os casos de uso de categorias em `application/categories.py`.
- **Efeito:** atualizar os pilares do perfil não atualiza automaticamente a coleta; duas telas podem apresentar identidades editoriais divergentes.
- **Melhoria:** definir vínculo explícito ou responsabilidades distintas, com nomes claros. Reutilizar categorias quando forem o mesmo conceito; não unir dados sem analisar queries e referências históricas.
- **Aceite/teste:** alterar estratégia de conteúdo tem efeito conhecido sobre tendências; exclusões/renomes preservam a integridade de vídeos e métricas associados.

#### G14 — P3 — Biblioteca audiovisual não equivale a todas as capacidades propostas

- **Evidência:** `adapters/render_plan_ffmpeg.py:84/101` aplica tamanho/posição de legenda e cores; motion e música são passados ao builder. A trilha usa síntese parametrizada, não um catálogo de music providers. `domain/visual_style.py` carrega transition, mas o builder/compilador inspecionados não a aplicam. A thumbnail é montada pelo `PillowThumbnail` ligado em `composition.py`, sem contexto de identidade visual do canal.
- **Melhoria:** apresentar a capacidade exata: movimento, parâmetros suportados de legendas, cores e voz. Planejar separadamente transições, legendas dinâmicas, preview real de voz/estilo, identidade de thumbnail e seleção de música. Não tratar QA técnico existente como avaliação estética de qualidade.
- **Aceite/teste:** cada controle altera resultado mensurável do pipeline; preview usa configuração efetiva; controles futuros não aparecem como operacionais.

### 22.3. Matriz de rastreabilidade consolidada

`IMPLEMENTED` abaixo significa caminho identificado no código, não certificação operacional. `PARTIAL` indica aplicação incompleta frente ao requisito V3.1. Não foi atribuída classificação `DEPRECATED`: nenhuma remoção foi decidida. Referências G01–G14 apontam para as evidências acima.

| Feature | UI | API / caso de uso | Domain / persistência | Pipeline consumer | Status | Gap / ação |
|---|---|---|---|---|---|---|
| Perfis de canal | `panel_channels` | rotas de canais → `Create/UpdateChannelProfile` | `ChannelProfile` → `channel_profiles` + revisões | estilo e gate YouTube; editorial incompleto | PARTIAL | G05/G11; preservar CRUD e concorrência existentes. |
| Estratégia editorial aplicada | formulário do canal | update do perfil | campos editoriais versionados | geradores não recebem perfil | PARTIAL | G05. |
| Biblioteca de estilos | `panel_styles` | rotas styles → casos de uso | `VisualStyle` → estilos/revisões | `_style_for_video` → render | IMPLEMENTED | Reaproveitar; corrigir ciclo de arquivamento G08. |
| Seleção de estilo por vídeo | página do vídeo | `SetVideoStyle` | `videos.style_id` | resolução vídeo > canal | IMPLEMENTED | Integrar ao wizard; não confundir com patch de parâmetros. |
| Overrides parciais por canal/vídeo | sem editor operacional correspondente | contrato de patch não encontrado | sem composição parcial correspondente | resolver escolhe estilo inteiro | MISSING | G07. |
| Configuração congelada por run | sem projeção completa | coordenador/render | run sem snapshot efetivo; plano tem referência de estilo | leituras separadas de voz e estilo | PARTIAL | G06. |
| Legendas, cores e motion existentes | biblioteca/edição de estilo | update style | params validados | adapter FFmpeg e builder | IMPLEMENTED | Expor apenas parâmetros efetivamente suportados. |
| Transições configuráveis | representáveis no domínio | estilo carrega valor | `transition` / `Shot.transition` | sem aplicação no caminho rastreado | PARTIAL | G14; evolução do motor. |
| Identidade de thumbnail por canal | campo no perfil | update perfil | texto persistido | gerador não consome identidade | PARTIAL | G14. |
| Perfis Economy/Balanced/High Quality | perfil econômico/decisão na tela | budget + route | `EconomicProfile` persistido | execução usa ProjectConfig | PARTIAL | G09; High Quality é mapeamento a decidir. |
| Budget mensal e por vídeo | tela de custos | Get/SetChannelBudget | limites + ledger + reservas | guard opcional; mensal global | PARTIAL | G01. |
| Catálogo e teste de providers | tela de canal | ProviderService | quatro kinds e catálogo da composição | build usa registry/config | PARTIAL | Falta agrupamento completo por capacidade e ligação ao routing; evitar segunda lista estática na UI. |
| Conexão e destino YouTube | canais/conexões | consentimento + vínculo | contas, grants e autorizações | token ainda vem do modelo por projeto | PARTIAL | G02/G03. |
| Equipe e gestão de BYOK | `panel_team` | mutações com RBAC do operador | memberships, keys, auditoria/cofre | chave organizacional sem ligação ao provider | PARTIAL | G04/G10. |
| Isolamento SaaS em runtime | operador único | Basic/worker global | tenancy modelada; filtros incompletos | sem contexto autenticado completo | PARTIAL | G04; bloqueio para marco multi-tenant. |
| Preferência de tema | alternador | estado local no navegador | sem preferência pessoal server-side | não aplicável | PARTIAL | Reaproveitar tema atual; decidir se sincronização por usuário é necessária. |
| Canal ativo transversal | seletor em algumas páginas | parâmetros independentes | projeto é base do canal | vídeo tem projeto próprio | PARTIAL | G11. |
| Create simplificado | dois caminhos de criação; wizard com placeholders | CreateVideo + fontes + production runs | Video, snapshots, ProductionRun | pipeline exige claims/fontes | PARTIAL | G12; consolidar fluxo sem prometer pesquisa automática. |
| Library dedicada | item Vídeos | redirect ao Início | leitura de vídeos existente | não aplicável | PARTIAL | Criar página sobre leitura existente; preservar filtro de canal. |
| Ideas / tendências | Tendências e pilares reais | ingest/refresh/categorias; scoring de ideias | trends e project_categories | tema pode iniciar criação | PARTIAL | Definir o que “Ideas” adiciona; G13; sem Finder novo obrigatório. |
| Analytics | página e consultas existentes | coleta/dashboard | métricas e learning repositories | adapter ainda usa OAuth legado | PARTIAL | G02; diferenciar indisponibilidade de dados e lacuna de credencial. |
| Controle de execução | página de execução | pause/resume/retry/cancel | estados e eventos do run | coordenador e worker existentes | IMPLEMENTED | Reaproveitar; manter ações no vídeo, não em Settings. |
| Mockup navegável | HTML pt-BR | interações locais demonstrativas | sem persistência operacional | nenhum | UI_ONLY | Usar como especificação; não contar simulações como integração. |

### 22.4. Ajustes arquiteturais recomendados

1. **Camada de apresentação:** reutilizar os view models existentes (`BuildChannelsPage`, `BuildStylesPage`, `BuildVideoStyleView`, dashboard). Uma API agregadora só se justifica para uma necessidade concreta de leitura; não introduzir outra base de configurações.
2. **Configuração efetiva:** resolução tipada e determinística na aplicação/domínio, consumida por UI, API e coordenador. Definir defaults legados e versionamento antes de implementar patches de estilo. Snapshot precisa cobrir também entradas anteriores ao render quando a reprodutibilidade exigir.
3. **Publicação e credenciais:** uma política de destino e autorização para publicador nativo, analytics e automação. A UI deve conseguir explicar “conectado”, “autorizado para publicar” e “pronto para executar” separadamente.
4. **Orçamento:** separar escopos de apuração, limites e reserva. Reusar os mecanismos de paid operations, sem trocar segurança transacional por checagem apenas na tela.
5. **SaaS:** tratar identidade autenticada e escopo por recurso como pré-requisito do runtime multi-tenant; aparência de Workspace e formulários de equipe não encerram esse trabalho.
6. **Escopo de UX:** reorganizar a navegação existente e expor somente capacidades reais; não recriar o shell nem adicionar framework frontend. Diagnósticos e erros devem informar ações possíveis sem expor segredos.

### 22.5. Roadmap derivado das lacunas

| Ordem | Pacote | Arquivos/áreas principais | Dependência | Critério de saída / rollback |
|---|---|---|---|---|
| 1 | Corrigir documento e contratos de comportamento | este backlog; ADRs de escopo, destino, resolução | análise atual | Decidir tenancy, limite mensal, destino obrigatório, versões e retry. Sem mudança de runtime. |
| 2 | Identidade YouTube comum | connections, youtube_oauth, publication_execution, channel_analytics, composição, workflow 03 | decisões de destino e migração | Casos cruzados bloqueados e novo fluxo funcional; manter migração explícita do legado, nunca fallback oculto. |
| 3 | Budget consistente | budget, channel_budget, repositórios e composição | decisão de escopos | Testes concorrentes em banco descartável e paridade UI/guard; migração aditiva e rollback que preserve ledger/reservas. |
| 4 | Configuração editorial e snapshot | editorial, longform, production, render, domínio, composição | decisões de precedência/congelamento | Contexto aplicado em short/long; execução imutável; compatibilidade com planos e vídeos legados. |
| 5 | Personalização e ciclo de estilos | visual_style, video_style, channel_repo, visual_style_repo | pacote 4 | Overrides isolados e arquivamento auditável; defaults mantidos para registros sem patches. |
| 6 | Routing e BYOK efetivos | providers, config, saas, secret_store, composição | orçamento e, para BYOK por tenant, identidade autenticada | Credencial e provider usados coincidem com decisão/auditoria; preservar config explícita legada mediante política definida. |
| 7 | Settings e fluxo criativo | panel, panel_channels, panel_styles, panel_connections, panel_team, panel_production, routes | contratos estabilizados; partes de navegação podem avançar antes | Canal preservado, criação sem placeholders, fluxo fontes → produção → revisão; manter redirects compatíveis. |
| Paralelo condicionado | Preparação SaaS operacional | auth, application ports/use cases, repositórios, workers | definição do marco multi-tenant | Isolamento efetivo antes de habilitar múltiplos tenants; não ativar por simples mudança de UI. |
| Posterior | Evolução audiovisual | render_plan_builder, render_compiler, adapter FFmpeg, thumbnail, previews | pacotes de configuração/estilo | Cada capacidade tem consumo real, preview verificável e testes audiovisuais; nenhuma simulação publicada como suporte. |

Cada pacote deve ser desdobrado em tarefas pequenas durante o planejamento de implementação. Esta análise não autoriza implementar nenhum deles.

### 22.6. Validação realizada e limites

Comando executado, sem gravação de bytecode/cache no repositório:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider \
  tests/test_channel_budget.py tests/test_provider_catalog.py \
  tests/test_saas_domain.py tests/test_workflow_publish.py \
  tests/test_workflow_analytics.py tests/test_workflow_trends.py -q
```

**Resultado: 89 testes passaram em 2,65 s.** Cobrem regras puras e estrutura/comportamento local dos workflows, não publicação real nem isolamento ponta a ponta.

O Python disponível não contém `pydantic`; não foi instalada dependência nem montado banco de testes para esta análise. Não foram executadas suítes HTTP/render/Postgres, inspeção visual de navegador, avaliação de contraste ou chamadas externas. Nenhum teste novo foi criado e nenhum código de produção foi alterado.

Próximas regressões necessárias: destino e credencial por canal em todos os caminhos, orçamento por escopo com concorrência, mudança de configuração durante TTS, aplicação do perfil editorial, arquivamento com revisão do perfil, routing realmente executado, BYOK efetivamente usado e navegação preservando canal. Usar PostgreSQL descartável com a prova exigida por `tests/conftest.py` antes de qualquer teste que recrie schema.
