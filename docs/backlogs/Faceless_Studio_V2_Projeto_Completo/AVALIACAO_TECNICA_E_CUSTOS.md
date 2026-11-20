# Design e Avaliação Técnica: Faceless Studio V2 (F0–F11, Custos e Clean Architecture)

**Data:** 2026-11-20  
**Status:** Proposta de Design Técnico / Avaliação de Arquitetura  
**Alvo:** Repositório `youtube-faceless-starter`  

> **Ressalva de execução (20/11/2026):** os preços e resultados de qualidade abaixo não foram verificados e não são base para orçamento ou escolha de fornecedor. O custo do DarkPlanner é desconhecido. O contrato de API, autenticação, cobrança, licenças e idempotência exigem discovery antes de integrar; manter o Piper selecionável. O plano de implementação também requer correções de testes, orçamento concorrente e recuperação antes de ser seguido literalmente.

---

## 1. Visão do Produto e Princípio Norteador

> **North Star:**  
> *"Transformar uma ideia em um vídeo de qualidade, publicado no YouTube, por meio de uma experiência simples, automatizada, controlável e financeiramente eficiente."*

### 1.1 Premissas Inegociáveis
1. **Clean Architecture e Fronteiras Limpas:** O core (`domain/` e `application/ports.py`) deve permanecer 100% puro e desacoplado de infraestrutura, bancos de dados, FFmpeg, orquestradores (como n8n) e APIs de provedores específicos (OpenAI, Gemini, ElevenLabs, fal.ai, YouTube). Tudo que é externo é implementado como adaptadores em `adapters/` e montado exclusivamente em `composition.py`.
2. **Qualidade sem Desperdício:** A busca por economia e simplicidade **nunca deve degradar a qualidade do vídeo**. A qualidade percebida (gancho de atenção, ritmo do roteiro, clareza sonora da voz, dinamismo visual e pertinência de imagens) é mantida usando ferramentas com a melhor relação custo/impacto (ex.: modelos de linguagem rápidos e acessíveis, composição com efeitos dinâmicos no FFmpeg e voz de alta fidelidade).
3. **Controle Financeiro e Modos de Execução:** Nenhuma etapa cara dispara sem conferência de custo projetado. O sistema suporta dois modos de operação:
   - **Modo Interativo (Manual):** Pausa obrigatória para revisão humana após a geração do roteiro e antes da publicação no YouTube.
   - **Modo Automático com Teto Orçamentário (Budget-Guarded):** O pipeline auto-aprova etapas intermediárias (voz, mídia, render) desde que a projeção de custo não ultrapasse o teto pré-configurado do canal (`budget_cap`). A publicação no YouTube permanece como rascunho/privado ou requer confirmação explícita de segurança.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### 2.1 Objetivos (Goals)
- **Avaliação fase a fase (F0–F11):** Confrontar cada fase contra a estrutura real de `renderer/app/studio/` e `workflows/`, distinguindo o que está pronto, o que precisa de refatoração e o que é excesso de engenharia.
- **Modelagem de Custos Operacionais:** Definir o custo unitário por vídeo longo (~8 minutos, ~1200–1400 palavras, 12–16 cenas) e os custos de infraestrutura em três cenários (Econômico, Híbrido de Alta Qualidade e Generativo Total).
- **Simplificação e KISS (Keep It Simple, Stupid):** Cortar dependências externas pesadas; internalizar a orquestração do ciclo de vida em Python nativo (`ProductionCoordinator`) utilizando PostgreSQL com padrão Outbox/CAS.
- **Plano de Execução por Marcos de Valor:** Agrupar as 12 fases em 4 marcos objetivos focados em colocar vídeos monetizáveis no ar.

### 2.2 Não-Objetivos (Non-Goals)
- **SaaS Multiusuário e Faturamento Completo (F11) no MVP:** Suporte a multi-inquilinos com cobrança Stripe, contas corporativas e cotas por usuário final ficam postergados até que o canal e o fluxo principal atinjam escala.
- **Geração de Vídeo Generativo Integral:** Gerar clipes de vídeo por IA (Runway/Kling/Veo) para 100% das cenas não é meta, pois multiplicaria o custo por 30x sem ganho proporcional de retenção.

### 2.3 Anti-Objetivos (Anti-Goals)
- **Qualidade Amadora:** Produzir vídeos estáticos, monótonos ou com vozes robóticas sob o pretexto de "economia máxima".
- **Acoplamento do Core:** Deixar contratos ou regras de negócio do `domain` dependerem de formatos do n8n, parâmetros brutos do FFmpeg ou bibliotecas de terceiros.
- **Publicação Fantasma ou Acidental:** Permitir que vídeos não aprovados ou uploads concorrentes ocorram no canal do YouTube.

---

## 3. Avaliação Técnica Detalhada: Fases F0 a F11

O repositório já possui uma base sólida de Clean Architecture em `renderer/app/studio`:
- `domain/`: Entidades bem definidas (`contracts.py`, `states.py`, `render.py`, `trends.py`, `claims.py`).
- `application/ports.py`: Portas explícitas (`TextModel`, `ImageModel`, `VoiceModel`, `Renderer`, `VideoRepository`, etc.).
- `adapters/`: Adaptadores locais já funcionais (`voice_piper.py`, `render_ffmpeg.py`, `qa_ffmpeg.py`, `thumbnail.py`, `postgres/`).
- `composition.py`: Raiz de composição onde tudo é montado.

Abaixo está o cruzamento minucioso de cada fase do backlog mestre com o código existente, indicando o status real, os gaps e a recomendação de simplificação:

| Fase | Título Original | Status no Código Atual | O que Realmente Falta | Simplificação & Economia Recomendada |
|---|---|---|---|---|
| **F0** | Higiene, Segurança, Baseline e Docs | Parcial: estrutura limpa, mas `.env` com segredos na raiz e sem secret scanning. | Script de empacotamento seguro, rotação de chaves expostas, testes de regressão de baseline. | **Manter simples:** Script shell único de checagem (`scripts/check-secrets.sh`) e `.env.example` sanitizado. Sem adicionar ferramentas pesadas de compliance corporativo. |
| **F1** | Production Coordinator, Checkpoints e Recuperação | Ausente: existem use cases isolados (`GenerateScript`, `ProduceAssets`, `StartRender`), mas sem coordenador único de fluxo. | Entidades `ProductionRun` e `StageExecution`, transições de estado atômicas (CAS), retomada de falha. | **Core enxuto:** Implementar `ProductionCoordinator` como use case em Python puro com tabela simples no PostgreSQL (`production_runs`). Não usar orquestradores pesados externos; rodar workers assíncronos leves via ThreadPool ou fila simples no Postgres. |
| **F2** | UX de Fluxo Único, Painel e Acompanhamento | Parcial: endpoints em `api/panel.py` e `api/preview.py`, mas a jornada ponta a ponta não é guiada. | Visualização das etapas da corrida de produção, custo realizado, botão de aprovação e retry. | **UI direta:** Painel web minimalista (servido pelo FastAPI ou SPA leve) focado na linha do tempo do vídeo: Ideia → Roteiro → Mídia → Aprovação → Publicação. Sem dashboards analíticos inflados antes do tempo. |
| **F3** | Tendências, Research e Fontes Verificáveis | Parcial: `youtube_trends.py` e ingestão de categorias existem; falta conectar com research de fontes. | `ResearchPort` para buscar fatos e fontes comprovadas; snapshot de referências para checagem. | **Custo mínimo:** Adaptador com DuckDuckGo Search / Tavily API / HttpxFetcher. Não pagar por provedores caros de dados; usar LLM leve para sumarizar fontes gratuitas antes de redigir o roteiro. |
| **F4** | Motor Editorial Long-form & Aprovação de Roteiro | Parcial: `editorial.py` gera roteiros curtos (Shorts); falta pipeline de roteiro longo (~8 min). | Geração em 2 passos (Outline/Capítulos → Cenas com ganchos e retenção), estimativa de timing por cena, versão aprovada. | **Alta qualidade e baixo custo:** Usar **Gemini 1.5/2.0 Flash** ou **GPT-4o-mini** via porta `TextModel`. Roteiro longo de 8 minutos custa menos de $0.02. Gate de aprovação humana de roteiro antes de sintetizar voz ou mídia. |
| **F5** | Motor Audiovisual, Mídia e Montagem Dinâmica | Parcial: suporta 1 imagem por cena; usa `PexelsImage`, `VeoImage` (mock/experimental). Porta `Voice` já existente com `PiperVoice`. | Suporte a múltiplos `VisualBeat` por cena, fallback inteligente de mídia; integração plugável do **DarkPlanner Voice Provider** (`voice: darkplanner:<voice-id>`). | **Otimização Chave & Plugabilidade:** Evitar vídeo generativo em lote ($$$). Usar imagens IA em alta definição (FLUX via fal.ai) e stock grátis (Pexels), animadas via FFmpeg. Conectar **DarkPlanner** como adapter anti-corrupção implementando a porta `Voice`, produzindo WAV local validado por cena, com guardas de custo e idempotência, sem acoplar o core. |
| **F6** | Editor Visual, Preview e QA | Avançado no backend: `render_ffmpeg.py` e `qa_ffmpeg.py` já fazem render e verificação técnica de áudio/vídeo. | Regeneração granular (reprocessar apenas a cena editada sem renderizar todo o projeto do zero). | **Economia de processamento:** Cache de render por cena (`storage/renders/scenes/{scene_id}_{hash}.ts`). Concatenar com FFmpeg em segundos. |
| **F7** | Thumbnails, Títulos, SEO e Experimentos | Parcial: `PillowThumbnail` gera thumbnails básicas com PIL. | Variações de títulos de alto CTR geradas por LLM, templates gráficos atrativos para a thumb. | **Simplicidade:** Gerar 3 opções de título + descrição + tags via LLM. Para thumbnail: composição Pillow/FFmpeg sobre imagem gerada por IA com texto tipográfico em destaque. |
| **F8** | Publicação YouTube Resiliente, OAuth e Agenda | Parcial: workflow n8n `03-publish-approved.json` e rotas em `api/routes.py`. | Upload direto em Python com sessão resumable, bloqueio de concorrência (lease), publicação privada/agendada. | **Desacoplamento:** Implementar adapter nativo `GoogleYouTubePublisher` em Python puro via API v3, removendo a dependência estrita do n8n para publicar. |
| **F9** | Analytics e Loop de Aprendizado | Parcial: repositório de analytics e workflow n8n diário existem. | Transformar métricas (retenção, CTR) em sugestões de novos temas para o canal. | **Manter simples:** Ingestão de métricas pelo YouTube Analytics API diária em tabela local e exibição simples das melhores ideias comprovadas. |
| **F10** | Gerenciamento de Canais, Estratégias e Providers | Parcial: entidade `Project` existe no banco. | Configurar múltiplos canais (ex.: História, Curiosidades, Negócios) com seus respectivos estilos de voz, prompts e orçamentos. | **Clean Arch:** Configuração de perfil por canal no banco (`channel_profiles`), permitindo alternar estratégia de voz e visual sem alterar uma linha de código. |
| **F11** | Preparação SaaS, Multiusuário e BYOK | Não iniciado: desenhado como SaaS corporativo com tenants e billing. | Contas individuais, chaves de API próprias do cliente (BYOK). | **PODA RECOMENDADA (MVP):** Manter como Single-Tenant / Multi-Canal. BYOK via arquivo de configuração ou tela de settings local. Adiar cobrança multi-usuário e billing até que o produto gere receita consistente. |

---

## 4. Análise e Planejamento de Custos Operacionais

Para manter o compromisso de **qualidade com máxima eficiência financeira**, analisamos o custo de produção de um **vídeo longo típico de 8 minutos** (~1.200 a 1.400 palavras narradas, 12 a 16 cenas, 2 a 3 minutos de b-roll e transições visuais):

### 4.1 Composição de Custos por Etapa (Vídeo de 8 Minutos)

| Etapa | Tecnologia / Serviço Econômico | Alternativa Premium | Custo Econômico | Custo Híbrido (Recomendado) |
|---|---|---|---|---|
| **Pesquisa & Briefing** | DuckDuckGo / Tavily Search + Gemini Flash | Perplexity Sonar Pro / GPT-4o | $0,005 | $0,01 |
| **Roteiro & Fact-Check** | Gemini 1.5/2.0 Flash (~15k tokens I/O) | Claude 3.5 Sonnet / GPT-4o | $0,015 | $0,03 |
| **Narração / Voz (TTS)** | Piper TTS (Local / Zero Custo) ou Edge-TTS | DarkPlanner Voice / ElevenLabs Flash / OpenAI TTS HD (~8.000 chars) | $0,000 | $0,50 – $1,20 |
| **Imagens de Cena** | Pexels (Grátis) + FLUX.1 Schnell via fal.ai (~12 imagens) | Midjourney API / FLUX Pro | $0,030 | $0,15 – $0,25 |
| **Animação & Efeitos** | FFmpeg local (Ken Burns, Pan/Zoom, Partículas) | Clipes de Vídeo IA (Kling/Runway) | $0,000 | $0,000 (FFmpeg dinâmico) |
| **Render Final & QA** | FFmpeg nativo na máquina local / VPS | Cloud Render Farm (AWS/Replicate) | $0,000 | $0,000 |
| **Thumbnail & SEO** | Pillow local + 1 imagem FLUX + Gemini Flash | Designer / APIs caras | $0,003 | $0,02 |
| **Total por Vídeo de 8 min** | | | **~$0,05** | **~$0,90 – $1,50** |

### 4.2 Comparação dos Três Modelos de Operação

1. **Cenário A: "Custo Quase Zero" (Open Source e Local)**
   - *Stack:* Gemini Flash (Roteiro) + Piper TTS local (Voz pt-BR) + Pexels/FLUX Schnell + FFmpeg local.
   - *Custo por vídeo:* **R$ 0,30 a R$ 0,50** (~$0,05 a $0,10).
   - *Qualidade:* Narrativa muito boa, visual consistente, porém voz sintética com tom mais formal e menos emocional.
2. **Cenário B: "Híbrido de Alta Retenção" (O Melhor ROI - RECOMENDADO)**
   - *Stack:* Gemini Flash ou GPT-4o-mini (Roteiro estruturado para retenção) + OpenAI TTS HD ou ElevenLabs Turbo v2 (Voz humana envolvente) + FLUX.1 (Imagens de impacto customizadas) + Animação de câmera e legendas cinéticas com FFmpeg.
   - *Custo por vídeo:* **R$ 5,00 a R$ 9,00** (~$0,90 a $1,50).
   - *Qualidade:* Padrão de canal de milhões de inscritos, retenção altíssima de público, excelente CTR na thumbnail, custo que permite produzir 20 a 30 vídeos por mês por menos de R$ 250 de verba operacional total.
3. **Cenário C: "Vídeo 100% Gerado por IA" (Anti-Padrão Financeiro)**
   - *Stack:* Gerar cada tomada de 5 segundos com Kling / Runway Gen-3 / Sora.
   - *Custo por vídeo:* **R$ 150,00 a R$ 250,00** ($25 a $45 por vídeo).
   - *Diagnóstico:* Totalmente inviável e desnecessário para canais faceless em crescimento.

### 4.3 Custos Fixos de Infraestrutura
- **Ambiente de Desenvolvimento / Produção Local:** R$ 0/mês (execução no Mac/PC do operador via Docker Compose com PostgreSQL local e FFmpeg nativo).
- **Ambiente em Nuvem (se desejado no futuro):** 1 VPS Hetzner ou DigitalOcean (4 vCPUs, 8 GB RAM) por aproximadamente $15–$25/mês, suficiente para renderizar e publicar dezenas de vídeos com agendamento contínuo.

---

## 5. Diretrizes de Arquitetura Limpa (Clean Architecture)

Para garantir que o core nunca seja poluído:

```
renderer/app/studio/
├── domain/                    <-- Regras puras e contratos de negócio
│   ├── contracts.py           <-- Entidades (Video, Scene, Script, Asset, Publication)
│   ├── production.py          <-- NOVO: ProductionRun, StageExecution, StageKind, StageStatus
│   └── states.py              <-- Máquina de estados de vídeo e publicação
├── application/               <-- Casos de uso e portas de entrada/saída
│   ├── ports.py               <-- Interfaces puras (TextModel, VoiceModel, ImageModel, Renderer, Outbox)
│   ├── coordinator.py         <-- NOVO: ProductionCoordinator (orquestrador do pipeline)
│   ├── editorial.py           <-- Roteirização e fact-checking
│   ├── media.py               <-- Preparação de assets e storyboard
│   └── publishing.py          <-- Publicação segura e agendamento
├── adapters/                  <-- Adaptadores concretos (infraestrutura)
│   ├── postgres/              <-- Repositórios e controle de transação/outbox
│   ├── llm/                   <-- Adaptadores OpenAI, Gemini, Claude (implementam TextModel)
│   ├── voice/                 <-- Adaptadores Piper, EdgeTTS, DarkPlanner, ElevenLabs (implementam VoiceModel)
│   ├── image/                 <-- Adaptadores Pexels, FalAi, Midjourney (implementam ImageModel)
│   ├── render_ffmpeg.py       <-- Renderização com legendas e animação
│   └── youtube/               <-- Adaptador YouTube Data API v3 (implementa PublisherPort)
└── composition.py             <-- ÚNICO local onde os adaptadores são injetados nas portas
```

**Regras de Dependência:**
1. Arquivos em `domain/` **não importam** nada fora de `domain/` ou da biblioteca padrão do Python.
2. Arquivos em `application/` **só importam** de `domain/` e definem `ports.py`.
3. Arquivos em `adapters/` implementam as classes abstratas / `Protocol` de `application/ports.py`. Adaptadores de fornecedores específicos (como DarkPlanner, fal.ai, ElevenLabs) atuam como Anti-Corruption Layers (ACL), convertendo contratos externos para os tipos do core e validando saídas (ex.: WAV sem silêncio e medição exata de segundos).
4. Nenhum controller ou rota FastAPI em `api/` executa lógica de negócio diretamente; eles apenas chamam use cases expostos por `composition.py`.

---

## 6. Roteiro de Implementação Otimizado (4 Marcos Práticos)

Em vez de se perder na complexidade de 95 cards dispersos, consolidamos as fases em 4 Marcos com entregas de valor tangível:

### Marco 1: Saneamento, Baseline e Orquestrador Central (F0 + F1)
- Sanitizar credenciais, criar script de empacotamento seguro e isolar `.env`.
- Criar `ProductionRun` e `ProductionCoordinator` no core com transições atômicas no PostgreSQL.
- Permitir executar o pipeline em lote de ponta a ponta via comando/API, com persistência de progresso e capacidade de pausar/retomar.

### Marco 2: Motor Long-Form de 8 Minutos e Mídia Dinâmica Econômica (F3 + F4 + F5 + DarkPlanner)
- Suporte a briefing com tendências/fatos e geração de roteiros de ~8 min estruturados em capítulos com gancho, desenvolvimento e CTA.
- Gate de aprovação humana de roteiro antes de disparar mídia (com bypass automático seguro se o modo for budget-guarded).
- Suporte a múltiplos `VisualBeat` por cena usando imagens com movimentação virtual no FFmpeg (estética cinematográfica com baixo custo de API).
- Integração de modelos de alto rendimento: Gemini Flash para texto; **DarkPlanner Voice Provider** (`voice: darkplanner:<voice-id>`) / ElevenLabs / Edge-TTS / Piper para narração; fal.ai FLUX / Pexels para imagens.
- Anti-Corruption Adapter do DarkPlanner: sintetiza áudio por cena, gera WAV local compatível, valida silêncio, mede duração e registra consumo financeiro sem acoplar o core.

### Marco 3: QA Granular, Thumbnails e Publicação Segura (F6 + F7 + F8)
- Render modular com cache por cena (regeneração localizada rápida).
- Geração de 3 variantes de título/descrição e thumbnail com imagem IA + tipografia PIL/FFmpeg.
- Adaptador nativo Python de publicação no YouTube (OAuth2, resumable upload, trava de idempotência contra duplicatas).
- Agendamento de postagem e publicação como rascunho/não-listado/privado para revisão final.

### Marco 4: Painel Unificado e Gestão de Canais (F2 + F9 + F10)
- Interface de usuário simplificada guiando o criador: Ideia → Roteiro → Aprovação → Mídia → Publicação.
- Configuração de perfis por canal (estilo, voz, prompts e teto de orçamento).
- Coleta básica de analytics para retroalimentar o radar de tendências.

*(A fase F11 de SaaS multiusuário corporativo fica catalogada para quando houver validação comercial de múltiplos clientes externos).*

---

## 7. Decisões do Builder vs Decisões do Parceiro Humano

- **Decisões do Parceiro Humano (fechadas nesta conversa):**
  - North Star oficial aprovada: *"Transformar uma ideia em um vídeo de qualidade, publicado no YouTube, por meio de uma experiência simples, automatizada, controlável e financeiramente eficiente."*
  - Princípio de Clean Architecture estrita preservado (core agnóstico, portas em `application/ports.py`).
  - Simplicidade e economia guiando as escolhas sem degradar a qualidade do vídeo.
  - Foco em formato longo (~8 minutos) com controle orçamentário por vídeo.
  - **Modo Automático Autorizado:** O sistema deve oferecer a opção de modo automático com teto de orçamento (auto-aprovação de mídia se o custo projetado estiver abaixo do limite configurado), além do modo manual passo a passo.
  - **Coexistência e Seleção de Provedores de Voz:** Manter a ferramenta de voz local atual do Piper TTS (`piper:pt_BR-faber-medium`) plenamente ativa e funcional, permitindo ao criador/canal escolher via configuração se quer sintetizar a narração com Piper (grátis/local) ou DarkPlanner (ou outros providers plugáveis).

- **Decisões Técnicas do Builder (incorporadas ao design):**
  - **Orquestrador Nativo:** Eliminar orquestradores externos pesados para o fluxo principal, adotando o `ProductionCoordinator` nativo em Python puro + PostgreSQL com outbox e estados atômicos.
  - **Composição Visual de 8 Minutos:** 1 imagem principal gerada por IA por cena (~12 a 16 imagens por vídeo) combinada com b-roll de stock gratuito (Pexels) e animação de câmera (Ken Burns, cortes, legendas cinéticas) no FFmpeg, mantendo o custo de mídia abaixo de $0.30 por vídeo sem gerar telas monótonas.
  - **Ambiente de Testes Local-First (Custo Zero):** A suíte de testes ponta a ponta e o baseline de desenvolvimento rodam 100% offline utilizando Piper TTS, Pexels e mocks locais, tratando provedores em nuvem (ElevenLabs, fal.ai) como adaptadores plugáveis.
  - **Pesquisa como Enriquecimento Opcional:** O motor de pesquisa (F3) enriquece temas e tendências quando solicitado, mas não bloqueia a criação de vídeos quando o usuário já fornece um briefing, outline ou roteiro pronto.
  - **OAuth do YouTube por Canal no Banco:** O armazenamento seguro e o refresh de tokens do YouTube API v3 nascerão associados ao ID do projeto/canal no PostgreSQL desde o Marco 3, eliminando retrabalho no Marco 4.
  - **Poda do SaaS Multiusuário (F11):** Postergar F11 (SaaS multi-tenant e billing externo) para focar na entrega de valor e eficiência operacional direta do canal.
