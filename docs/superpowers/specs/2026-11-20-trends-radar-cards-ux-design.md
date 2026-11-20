# Especificação de Design: Radar de Tendências (Brasil & Mundo), Cards com Thumbnails, Tema YouTube e UX com Loading

**Data:** 2026-11-20  
**Status:** Aprovado  
**Contexto:** Faceless Studio (`youtube-faceless-starter`) — Módulo de Tendências e Painel Web (`/studio/panel`).

---

## 1. Intenção e "O Porquê"

O operador do canal *faceless* precisa de um **radar de oportunidades ágil, confiável e esteticamente familiar** para decidir quais vídeos produzir.
Hoje, os temas são exibidos apenas em texto corrido, sem thumbnails, sem links diretos para assistir ao vídeo no YouTube e sem distinção clara dos maiores virais do **Brasil** e do **Mundo**. Além disso, a falta de estados visuais de carregamento (*loading*) deixava a navegação sem feedback imediato.

Esta especificação define:
1. Inclusão dos virais oficiais de **Em Alta Brasil** e **Em Alta Mundo** (`chart=mostPopular` com `regionCode=BR` e `regionCode=US`).
2. Novo design de cards **Opção A** com **Tema YouTube Dark** (fundo `#0f0f0f`/`#1f1f1f`, pílulas arredondadas estilo YouTube, badge de duração, vermelho `#ff0000`, miniatura 16:9 em alta resolução e link direto `▶️ Assistir no YouTube`).
3. **UX Dinâmica com Loading:** spinner animado e estado desabilitado durante a busca de tendências, feedback visual imediato e atalho inteligente no botão `✨ Criar Vídeo deste Tema` (preenche o formulário e rola suavemente até ele).

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos
- **Dados Reais da YouTube Data API v3:**
  - Coletar Top 10 virais do Brasil (`regionCode=BR`) e Top 10 virais do Mundo (`regionCode=US`) via `videos.list?chart=mostPopular`.
  - Custo de cota estrito: apenas 1 unidade por chamada (2 unidades no total para todo o radar de virais).
- **Cards com Estética YouTube (Opção A):**
  - Miniatura oficial em alta definição (`https://i.ytimg.com/vi/{videoId}/hqdefault.jpg`) com cantos arredondados (`8px`), efeito hover suave e badge de duração no canto inferior direito (`08:42`).
  - Link externo clicável no título com ícone `↗` e botão dedicado `▶️ Assistir no YouTube` com abertura em nova aba segura (`target="_blank" rel="noopener noreferrer"`).
  - Metadados: nome do canal (`📺`), visualizações formatadas (`👁️ 1.250.000 views`) e data relativa/formatada de publicação.
  - Badges de origem estilizados:
    - `[ 🇧🇷 Em Alta Brasil ]` (vermelho/verde)
    - `[ 🌍 Em Alta Mundo ]` (azul YouTube)
    - `[ 🏷️ Nome do Pilar ]` (cinza escuro YouTube)
  - Botão de ação rápida `✨ Criar Vídeo deste Tema`.
- **Barra de Pílulas Estilo YouTube:**
  - Pílulas arredondadas com fundo `#272727` que se tornam brancas com texto preto quando ativas (padrão oficial do YouTube):
    `[ 🔥 Todas (N) ] [ 🇧🇷 Em Alta Brasil (N) ] [ 🌍 Em Alta Mundo (N) ] [ 🏷️ Pilares... ] [ + Novo Pilar ]`.
  - Filtragem instantânea via JavaScript sem recarregar a página.
- **UX de Loading e Ações:**
  - Botão `🔄 Buscar Agora`: exibe spinner animado SVG, texto `Consultando YouTube...` e fica desabilitado durante a requisição para evitar cliques duplicados.
  - Botão `✨ Criar Vídeo deste Tema`: ao clicar, preenche automaticamente o campo `#topic` da seção de criação de vídeo, adiciona destaque visual temporário e executa scroll suave até o formulário.
  - Mensagens de feedback de sucesso ou erro (com tratamento claro para chave ausente ou cota esgotada).

### Não-Objetivos
- Não gerar temas sintéticos com LLM. Apenas vídeos comprováveis da API oficial.
- Não carregar players embutidos pesados na listagem inicial (preservando alta performance e leveza da página).

### Anti-Objetivos
- **Zero XSS:** Não utilizar `innerHTML` em scripts. Toda interpolação deve usar `html.escape` no backend e `textContent` no frontend.
- **Zero Inline Script sem Nonce:** Todos os scripts e estilos da página usam o atributo `nonce="{nonce}"`.
- **Sem Estouro de Cota:** Preservar a cota gratuita do YouTube (máximo de 12 unidades por ciclo de refresh completo).

---

## 3. Arquitetura e Decisões Técnicas

### 3.1. Identificação e Persistência das Tendências de Região
- Na YouTube Data API (`adapters/youtube_trends.py`):
  - Função `fetch_popular_trends(yt_key: str, region_code: str, max_results: int = 10) -> list[TrendItem]`:
    - `source_name = "YouTube Brasil (Em Alta)"` para `regionCode="BR"`.
    - `source_name = "YouTube Global (Em Alta)"` para `regionCode="US"`.
    - `source_url = "https://www.youtube.com/feed/trending"`.
    - `evidence`: lista com o vídeo correspondente (título, URL com `videoId`, canal, views, published_at).
- Em `application/panel.py` (`BuildPanel`):
  - Classifica a origem da tendência:
    - Se `source_name == "YouTube Brasil (Em Alta)"` $\to$ `region_badge = "BR"` e associa à pílula `Em Alta Brasil`.
    - Se `source_name == "YouTube Global (Em Alta)"` $\to$ `region_badge = "GLOBAL"` e associa à pílula `Em Alta Mundo`.
    - Demais tópicos vinculados a categorias mantêm `category_id` e seu respectivo pilar.
  - Extrai `video_id` da URL da evidência (`https://youtube.com/watch?v={id}`), derivando `thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"`.

### 3.2. Tolerância a Falhas em `RefreshTrends`
- As chamadas de Brasil (`BR`), Global (`US`) e dos pilares do projeto são executadas com isolamento de erro: se uma consulta falhar por limite de rede temporário, as outras que tiveram sucesso são persistidas normalmente (`best-effort`), garantindo que o usuário nunca fique com o painel vazio.

### 3.3. Tema YouTube Dark e Estilos CSS (`api/panel.py`)
- Pílulas de filtro (`.cat-pill`):
  - Padrão YouTube: `background: #272727; color: #f1f1f1; border-radius: 18px; border: 1px solid transparent; font-weight: 500;`.
  - Ativa: `background: #f1f1f1; color: #0f0f0f; font-weight: 600;`.
- Cards de Tendência (`.trend-card-yt`):
  - `background: #181818; border: 1px solid #282828; border-radius: 12px; display: flex; gap: 1rem; align-items: flex-start; padding: 1rem;`.
  - Miniatura 16:9 (`width: 168px; height: 94px; border-radius: 8px; position: relative; overflow: hidden; background: #000; flex-shrink: 0;`).
  - Badge de duração na miniatura: `position: absolute; bottom: 4px; right: 4px; background: rgba(0,0,0,0.8); color: #fff; font-size: 0.68rem; font-weight: 600; padding: 1px 4px; border-radius: 4px;`.
  - Título do vídeo: `color: #f1f1f1; font-size: 0.95rem; font-weight: 600; text-decoration: none; line-height: 1.35;`. Hover com sublinhado ou cor clara.
  - Metadados: canal com `📺` e visualizações em destaque verde/azul.
  - Botão `▶️ Assistir no YouTube`: botão secundário estilizado com ícone do YouTube.
  - Botão `✨ Criar Vídeo deste Tema`: botão com destaque azul/vermelho.

### 3.4. Interatividade e UX de Loading
- Botão `🔄 Buscar Agora`:
  - Ao ser clicado:
    ```javascript
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-inline"></span> Consultando YouTube...';
    ```
  - Após resposta da API: feedback exibido, botão restaurado e reload automático em caso de sucesso.
- Botão `✨ Criar Vídeo deste Tema`:
  - Ao clicar:
    - Preenche `input#topic.value = topicName`.
    - Executa `input#topic.scrollIntoView({ behavior: 'smooth', block: 'center' })`.
    - Aplica efeito visual de destaque (*pulse/glow*) no campo de input.
