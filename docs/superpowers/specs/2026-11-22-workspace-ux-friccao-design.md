# Design Document: Workspace do Vídeo sem Fricção (Storyboard Integrado, Composição, QA, Publicação, Fontes e B-Roll)

**Data:** 2026-11-22  
**Status:** Proposta de Design (Aguardando Aprovação)  
**Autor:** OpenCode & Usuário  
**Alvo:** Faceless Studio (`renderer/app/studio/api/panel_video_workspace.py`, `panel_video_nav.py`)  

---

## 1. Contexto e Motivação

O Faceless Studio possui uma rica esteira de produção audiovisual (fontes, roteiro em cenas, narração TTS, geração/busca de imagens e vídeos, composição multilayer FFmpeg, QA técnico e publicação no YouTube). No entanto, a experiência no Workspace do vídeo sofria de alta fricção porque operava dividida em **8 rotas completamente isoladas no servidor** (`visao-geral`, `fontes`, `narracao`, `cenas`, `composicao`, `qualidade`, `publicacao`, `producao`).

Para ajustar uma única cena, o criador precisava navegar até a aba de roteiro, salvar, navegar até narração para gerar voz, navegar até cenas para ver a imagem e depois navegar até composição para ver o resultado. Essa fragmentação gerava a sensação de um "painel burocrático de TI" em vez de uma bancada criativa.

### Decisão do Usuário
- **Escopo Selecionado:** Integrar no Workspace:
  1. **Cenas & Storyboard** (com edição integrada de texto, áudio e mídia)
  2. **Composição & Legendas** (parâmetros de montagem FFmpeg e preview)
  3. **Qualidade (QA) & Aprovação** (gates e checklist determinístico)
  4. **Publicação YouTube** (metadados e upload OAuth2)
  5. **Fontes & Evidências** (URLs e notas de apoio)
  6. **B-roll** por cena
- **Dois Modos de Operação (Piloto Automático vs. Modo Diretor):**
  - **Piloto Automático (1 Clique):** Criação direta que aciona a esteira completa de ponta a ponta (roteiro -> voz -> mídia -> composição), entregando o vídeo pronto na aba de Prévia/Aprovação sem paradas manuais intermediárias.
  - **Modo Diretor (Manual):** Permite ao operador inspecionar e refinar cada cena no Storyboard, ouvir trechos de áudio individuais, trocar mídias e ajustar legendas antes da composição final.
- **Estilo Pré-definido da Biblioteca Vinculado ao Canal:**
  - O canal pode ter um Estilo Visual da biblioteca (`VisualStyle`) configurado como padrão (`channel_style`). Novos vídeos herdam esse tema visual automaticamente.
- **Preservação:** Manter o restante como está ("manter resto como está"), incluindo o tema visual nativo V3 (tons escuros `#0c0d10`, acentos roxo/violeta `#b9a3ff` / `#8f6ef7`, tokens CSS existentes) e os endpoints e regras de backend.

---

## 2. Metas, Não-Metas e Anti-Metas

### Metas (Goals)
1. **Storyboard Integrado (1 Cena = Texto + Voz + Mídia + B-Roll):** Na área de Cenas, cada cena é um cartão rico que reúne a edição inline do texto narrativo, o mini-player de áudio daquele trecho específico (`▶ Ouvir Narração`), a miniatura visual da arte gerada/stock com botão rápido de troca (`Trocar Mídia`) e controle de B-roll.
2. **Navegação Limpa entre Funcionalidades:** O Workspace passa a ter abas focadas:
   - `Cenas & Storyboard` (área principal de produção)
   - `Composição & Legendas` (camadas, música, volume, legendas, resolução/FPS)
   - `Qualidade (QA) & Aprovação` (checklist de severidades e decisão de aprovação)
   - `Publicação YouTube` (metadados, thumbnail, agendamento e upload)
   - `Fontes & Evidências` (pesquisa e fact-checking)
3. **Preservação Integral de Recursos:** Nenhuma funcionalidade ou gate técnico é removido. Todas as chamadas de API (`POST /script/scenes`, `POST /sources`, `/composition`, `/preview`, `/publish`) continuam funcionando com os mesmos payloads e validações.
4. **Zero Overflow e Acessibilidade:** Conformidade com WCAG, labels acessíveis, suporte a teclado (`:focus-visible`) e ausência de scroll horizontal em viewports de 390px, 768px e 1280px.

### Não-Metas (Non-Goals)
- Não alterar schemas de banco de dados PostgreSQL.
- Não alterar as rotas externas de API REST (`/studio/videos/*`).
- Não alterar a tela de Início, Tendências ou Configurações do canal além do que já foi alinhado.

### Anti-Metas (Anti-Goals)
- Não transformar o estúdio em uma "ferramenta de brinquedo": a seriedade dos gates determinísticos de QA, a honestidade de custos e a proveniência de dados devem ser 100% respeitadas.
- Não mascarar erros de pipeline com estados fictícios.

---

## 3. Especificação Detalhada da Experiência (UX)

### 3.1 Topbar do Vídeo (Visão Geral e Metadados)
Exibida no topo de todas as abas do Workspace:
- Link de retorno: `← Vídeos`
- Título do vídeo (editável inline ou exibido com destaque)
- Badges de contexto: Formato (`Short 9:16` ou `Vídeo 16:9`), Versão/Revisão (`v1`, `v2`), Status da produção (`Rascunho`, `Renderizado`, `Aprovado`).
- Custo medido de geração (exibição honesta, nunca "US$ 0,00" se não medido).
- Botão de ação rápida de renderização: `✦ Gerar/Atualizar Render`.

### 3.2 Área 1: Cenas & Storyboard (O Coração da Criação)
Layout em lista vertical ou grid responsivo de cartões de cena. Cada cartão de cena possui 3 zonas integradas:
1. **Zona Visual (Esquerda):**
   - Miniatura da arte da cena (16:9 ou 9:16 conforme formato).
   - Badge de origem (`Arte IA`, `Stock Pexels` ou `B-Roll`).
   - Timestamp e duração do trecho (ex.: `0:00 - 0:08`).
   - Botão `Trocar Mídia`: abre diálogo/gaveta para buscar nova imagem no stock ou inserir prompt de IA.
   - Toggle `B-Roll`: ativa/desativa uso de mídia complementar nesta cena.
2. **Zona de Narrativa (Centro):**
   - Cabeçalho: `CENA X · [TÍTULO/BLOCO]` com contagem de palavras e estimativa de tempo.
   - Textarea com o texto narrado da cena (editável; salvar atualiza via `POST /studio/videos/{id}/script/scenes/{idx}`).
   - Prompt visual associado exibido de forma discreta.
3. **Zona de Narração (Direita):**
   - Mini-player de áudio da cena com botão `▶ Ouvir`.
   - Velocidade da narração.
   - Botão `Regenerar Áudio` para regravar apenas aquele trecho se o texto foi modificado.

### 3.3 Área 2: Composição & Legendas
Reúne os controles reais de montagem FFmpeg:
- **Player de Prévia do Vídeo:** Exibição com controles de reprodução nativos.
- **Trilhas Multicamadas (Timeline Visual):**
  - Trilha 1: Imagem Base & B-roll.
  - Trilha 2: Narração TTS (com indicador de waveform).
  - Trilha 3: Legendas sincronizadas (VTT/SRT).
  - Trilha 4: Música de fundo com indicador de volume e ducking.
- **Painel de Parâmetros de Saída:**
  - Legendas: Checkbox de ativação, seleção de fonte (`Inter`, `Roboto`, `Serif`), tamanho e estilo (`Caixa discreta`, `Destaque por palavra`).
  - Trilha Sonora: Checkbox de ativação, clima musical (`Documental`, `Suspense`, `Leve`), volume (slider 0-100%).
  - Saída de Vídeo: Resolução (`1080p`, `720p`), FPS (`24`, `30`, `60`), transição (`Fade`, `Corte`) e movimento (`Suave`, `Estático`).

### 3.4 Área 3: Qualidade (QA) & Aprovação
- **Checklist Técnico Determinístico:**
  - Duração, resolução e FPS.
  - Presença e integridade da narração.
  - Cobertura de cenas e imagens.
  - Legendas na área segura (safe area para Shorts e YouTube).
  - Lista de findings com severidade (`blocking`, `warning`, `info`).
- **Painel de Decisão Atômica:**
  - Botão `Aprovar Versão` (vinculado ao `render_id` ativo).
  - Botão `Rejeitar Versão` com campo obrigatório de motivo.
  - Suporte a QA Override quando houver apenas avisos não-bloqueantes.

### 3.5 Área 4: Publicação YouTube
- **Destino Conectado:** Exibe o canal do YouTube conectado via OAuth2 com status.
- **Metadados:**
  - Título final do vídeo para o YouTube.
  - Descrição com hashtags automáticas.
  - Tags de busca.
  - Visibilidade (`Público`, `Não listado`, `Privado`).
  - Agendamento opcional (data e hora local).
  - Direção/Briefing da Thumbnail.
- **Ação:** Botão primário `Publicar no YouTube Agora`.

### 3.7 Dois Modos de Operação: Piloto Automático vs. Modo Diretor
1. **Piloto Automático (Auto-Pilot / 1 Clique):**
   - Disponível no painel de criação e na Home através do checkbox/toggle `[x] Produzir vídeo completo automaticamente`.
   - Quando acionado com um canal que já possui Estilo da Biblioteca e Voz configurados:
     1. Cria o rascunho do vídeo (`POST /studio/videos`).
     2. Se houver roteiro colado, persiste como fonte inicial; caso contrário, gera o roteiro com a contagem de cenas alvo.
     3. Dispara a esteira completa assíncrona (`POST /studio/production-runs` ou pipeline de ponta a ponta).
     4. Redireciona o usuário diretamente para o Workspace com status de render ativo e aba de Prévia & Estreia pronta para aprovação.
2. **Modo Diretor (Edição Fina de Etapas):**
   - Para quando o criador deseja lapidar a história: o vídeo abre na aba `Cenas & Storyboard`, permitindo editar cada parágrafo de cena, ouvir e regravar trechos de áudio individuais, trocar imagens de stock/IA e ajustar legendas antes de disparar o render final.

### 3.8 Vinculação de Estilo da Biblioteca ao Canal
- Na gestão do canal (`panel_channels.py`), o operador pode selecionar qualquer estilo ativo da biblioteca (`panel_styles.py`) e defini-lo como `channel_style`.
- A herança automática garante que novos vídeos criados naquele canal venham com o prompt de arte, proporção e atmosfera visual pré-configurados sem necessidade de seleção manual repetida.

---

## 4. Arquitetura Técnica e Módulos Afetados

### 4.1 Respostas às Decisões de Construção (Builder Clarifications)
1. **B-Roll & Políticas de Mídia:**
   - O B-roll no Faceless Studio opera como diretriz de estilo e composição (`mediaPolicy` / `broll: bool`), em conformidade com o protótipo canônico. O botão/toggle na cena associa o tipo de mídia complementar (vídeo stock vs imagem gerada) e persiste via metadados de cena/estilo existentes (`POST /studio/videos/{id}/script/scenes/{idx}`), sem alterar o schema do PostgreSQL.
2. **Parâmetros de Composição:**
   - A área de Composição exibe os parâmetros efetivos (resolução, FPS, fonte e estilo da legenda, trilha musical com volume) derivados do `VisualStyle` do vídeo e do canal. Edições nesses parâmetros atualizam o estilo efetivo do vídeo via `PATCH /studio/videos/{id}/style`, sem criar novas tabelas.
3. **Ciclo de Vida da Produção & Rota `/producao`:**
   - A rota `/studio/panel/videos/{id}/producao` **permanece ativa e suportada** no servidor para inspeção detalhada de logs e retries de pipeline, sendo acessível por link no cabeçalho e rodapé. As 5 abas principais do menu (`cenas`, `composicao`, `qualidade`, `publicacao`, `fontes`) mantêm o foco criativo do dia a dia.
   - O botão da topbar `✦ Gerar/Atualizar Render` aciona o endpoint padrão de disparo de produção (`POST /studio/production-runs` ou render correspondente).
4. **Exibição de Miniaturas de Cenas (Assets):**
   - Imagens de stock utilizam diretamente a URL remota segura persistida. Para assets locais gerados, disponibiliza-se a rota segura de leitura `GET /studio/videos/{id}/scenes/{scene_idx}/asset` (mesmo padrão já utilizado por `/file` e `/thumbnail`), garantindo que o navegador exiba as imagens com cache e CSP nonce sem quebrar restrições de escrita.
5. **Divisão entre QA (`qualidade`) e Publicação (`publicacao`):**
   - Na aba **Qualidade**, o operador valida o checklist de gates e registra a aprovação/rejeição da revisão (`POST /studio/videos/{id}/approve` ou `approval_form`).
   - Na aba **Publicação**, o operador revisa e edita os metadados finais do YouTube (título, descrição, tags, agendamento) e aciona o envio (`POST /publications/execute` ou fluxo final do canal conectado).
6. **Troca de Mídia na Cena:**
   - O modal "Trocar Mídia" oferece seleção de candidatos stock/banco de mídia (usando `POST /scenes/{id}/media`) e edição do prompt da imagem (`image_prompt` via `POST /script/scenes/{idx}`).

### 4.2 Módulos a Modificar
1. `renderer/app/studio/api/panel_video_nav.py`:
   - Atualizar a lista canônica de áreas do vídeo para:
     ```python
     VIDEO_AREAS = (
         ("cenas", "Cenas & Storyboard"),
         ("composicao", "Composição & Legendas"),
         ("qualidade", "Qualidade & QA"),
         ("publicacao", "Publicação"),
         ("fontes", "Fontes & Evidências"),
     )
     ```
   - Rota padrão do workspace: `"cenas"` (em vez de `"visao-geral"` isolada).
2. `renderer/app/studio/api/panel_video_workspace.py`:
   - Renderizar o cabeçalho consolidado com métricas de visão geral no topo de todas as abas.
   - Renderizar o novo template integrado de Storyboard na área `cenas`.
   - Renderizar Composição com a timeline visual e parâmetros FFmpeg na área `composicao`.
   - Renderizar QA com os gates e decisão de aprovação na área `qualidade`.
   - Renderizar Publicação na área `publicacao`.
   - Renderizar Fontes na área `fontes`.
   - Manter a renderização de diagnóstico para requisições em `producao`.
3. `renderer/app/studio/api/routes.py`:
   - Adicionar o endpoint de leitura de imagem da cena: `GET /studio/videos/{video_id}/scenes/{scene_idx}/asset`.

### 4.2 Testes e Validação
- **Testes Unitários:** Atualizar testes em `tests/test_ux_contract.py` e criar testes de contrato para o workspace integrado.
- **Testes E2E (Playwright):** Atualizar `tests/e2e_ux/pages/workspace_page.py` e `tests/e2e_ux/test_e2e_journey_workspace.py` para validar navegação pelas 5 áreas integradas e ausência de IDs duplicados / overflow.

---

## 5. O que fica a cargo do construtor (Builder's Discretion)
- Detalhes de espaçamento fino (padding/gap entre 12px e 20px).
- Animações CSS suaves de transição entre abas (respeitando `prefers-reduced-motion`).
- Ícones SVG semânticos inline para os botões de ação do storyboard.
