# Especificação de Design: Tendências com Inspiração, Sinais Reais e Estratégia de Priorização (Variação A)

**Data:** 2026-11-23  
**Status:** Pronto para Aprovação  
**Contexto:** Faceless Studio (`youtube-faceless-starter`) — Módulo de Tendências e Ideias (`/studio/panel/tendencias`).

---

## 1. Intenção e "O Porquê"

Atualmente, a tela de **Tendências e Ideias** exibe cartões com texto simples contendo título, pilar, canal de origem e número bruto de visualizações. Falta apoio visual (miniatura da referência), contexto de tração (velocidade de views e comparação com o nicho) e uma avaliação objetiva de viabilidade para canais *faceless* com foco em monetização.

O operador precisa responder a três perguntas antes de investir tempo e cota de renderização em um tema:
1. **O que exatamente funcionou na referência?** (ver miniatura, formato, duração e dados reais da publicação).
2. **Este tema tem tração real e concorrência favorável?** (velocidade de visualizações e saturação recente de vídeos).
3. **Faz sentido produzir para o meu canal agora?** (aderência aos pilares do canal, diversidade temática para evitar penalidade do YouTube por "conteúdo repetitivo/inautêntico" e ausência de temas sensíveis à monetização).

Esta especificação define a evolução da tela de Tendências baseada na **Variação A** aprovada nos mockups visuais, respeitando estritamente o tema escuro nativo V3 da plataforma (`shell_v3_css.py`), utilizando **apenas dados e métricas disponíveis hoje** (sem dependência de APIs externas pagas ou geração sintética de temas por LLM), com suporte para favoritar ideias de forma **permanente** no canal ("☆ Guardar").

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos
- **Cartões de Tendência com Sinais Observáveis (Variação A):**
  - **Miniatura 16:9** oficial da referência do YouTube com cantos arredondados (`border-radius: 9px`), badge de região/origem (`Brasil · Em alta` ou `Mundo · Em alta`), duração formatada (ex.: `11:40`) e link seguro para assistir (`↗`).
  - **Sinais de Desempenho:**
    - Visualizações totais (`views`, vindo de `videos.list`).
    - Velocidade de crescimento (`views/hora`, calculada a partir de `published_at`).
    - Tração relativa ao nicho (`▲ X.X× vs. o nicho`, comparada à mediana das referências da mesma categoria na coleta).
  - **Prioridade Explicada (Score 0–100):**
    - Nota sintética calculada por regras determinísticas e transparentes.
    - Frase de diagnóstico resumida (ex.: *"Prioridade alta. Subindo rápido, concorrência baixa e combina com o pilar Mistérios"*).
    - Selo de status de risco (`[ Sem risco detectado ]` em verde ou `[ Atenção: repetição ]` / `[ Risco de monetização ]` em amarelo/vermelho).
    - Seção expansível `<details class="more">` com o detalhamento das 5 parcelas ponderadas (barras horizontais de progresso).
  - **Ações Rápidas por Cartão:**
    - `⚡ Criar com piloto` (leva tema e modo `piloto` para novo vídeo preservando o canal ativo).
    - `🎬 Modo Diretor` (leva tema e modo `diretor` para novo vídeo).
    - `☆ Guardar` / `★ Guardado` (alterna o estado da ideia no banco permanente de ideias do canal).
- **Pasta Permanente de Ideias Guardadas:**
  - As ideias favoritadas são salvas como snapshot permanente no banco do estúdio.
  - Mesmo que uma tendência expire da janela de coleta de 7 dias do YouTube, ela permanece acessível na lista e no filtro `Guardados` até que o operador a desfavorite ou produza o vídeo.
- **Barra de Controle, Ordenação e Filtros:**
  - **Ordenação via Servidor/URL:** `Prioridade` (padrão `sort=prioridade`), `Velocidade` (`sort=velocidade`) e `Mais recentes` (`sort=recentes`), garantindo ordenação correta sobre o catálogo completo.
  - **Filtros Rápidos:** `Todos`, `Perenes` (referências com mais de 180 dias com alta visualização contínua), `Sem risco` e `Guardados` (carrega as ideias salvas permanentemente no canal).
  - Preservação dos chips de pilares de conteúdo existentes (`Todos`, `Pilar A`, `Pilar B...`), do botão `↻ Buscar agora` e do diálogo `Gerenciar pilares`.
- **Transparência e Rastreabilidade ("Como calculamos"):**
  - Cada métrica exibe um selo de proveniência visual: `API YOUTUBE`, `CALCULADO` ou `SEU CANAL`.
  - Botão no cabeçalho `ⓘ Como calculamos` que abre um `<dialog>` modal com a tabela canônica das fontes de dados, regras de cálculo e custo de cota.

### Não-Objetivos
- **Sem Temas Sintéticos ou Roteiros por LLM nesta fase:** Toda tendência decorre exclusivamente de vídeos reais capturados da YouTube Data API v3.
- **Sem Google Trends não-oficial ou Scrapers:** Não utilizar bibliotecas não-oficiais de Google Trends (sem garantia de SLA ou estabilidade).
- **Sem Estimativas Ocultas de CPM ou Faturamento:** Não inferir receita em dólares ou CPM de vídeos de terceiros sem dados comprováveis.
- **Sem Prancheta Lateral Complexa ou Dashboards B:** Não implementar nesta fase o painel B (destaque heróico) nem a prancheta lateral C (foco em simplificar e enriquecer os cards existentes).

### Anti-Objetivos
- **Zero Estouro de Cota da YouTube API:** Manter o consumo restrito ao teto da spec de 20/11. A inclusão de `contentDetails` na chamada `videos.list` não consome cotas adicionais (já é coberta pelo mesmo custo de 1 unidade por lote de vídeos).
- **Zero XSS e Zero Nonce Ausente:** Todos os títulos, canais e metadados devem usar `html.escape` estrito no backend e `textContent` no frontend. Todos os scripts usam `nonce="{nonce}"`.
- **Zero Opacidade:** Nunca exibir uma nota como "86" sem permitir que o usuário abra o detalhamento e veja a fórmula exata das parcelas.

---

## 3. Fontes de Dados e Métricas Canônicas

| Métrica / Campo | Origem | Como é obtida / calculada | Custo de Cota |
| :--- | :--- | :--- | :--- |
| **Views, Canal, Data, Título, VideoId** | `API YOUTUBE` | `videos.list(part="snippet,statistics")` | 1 unidade por lote de até 50 vídeos (já existente) |
| **Duração do Vídeo** | `API YOUTUBE` | Adicionar `contentDetails` à chamada `videos.list` existente; converter formato ISO 8601 (`PT11M40S`) para `11:40` | 0 unidades extras (mesma chamada) |
| **Velocidade (views/h)** | `CALCULADO` | `views / max(1, horas_desde_publicacao)` | 0 unidades |
| **Tração vs. Nicho (▲ X.X×)** | `CALCULADO` | `views / mediana_views_lote_categoria` | 0 unidades |
| **Nível de Concorrência ($S_{\text{conc}}$)** | `CALCULADO` | Para pilares: densidade de vídeos sobre o mesmo termo na coleta recente. Para "Em Alta Geral": pontuação neutra de base (50) com rótulo "Geral (Ampla)". | 0 unidades |
| **Aderência ao Canal ($S_{\text{aderencia}}$)** | `SEU CANAL` | Correspondência entre o pilar da tendência e os pilares/histórico cadastrados no canal | 0 unidades |
| **Variedade Temática ($S_{\text{variedade}}$)** | `SEU CANAL` | Distância semântica/palavras-chave entre o título da tendência e os últimos 5 vídeos produzidos pelo canal | 0 unidades |
| **Classificação Perene vs. Pico** | `CALCULADO` | `Perene` se `data_publicacao > 180 dias` e `views > 100.000`; caso contrário, `Pico recente` | 0 unidades |
| **Risco de Monetização** | `CALCULADO` | Verificação contra lista determinística de temas de risco de desmonetização (sensíveis, YMYL em finanças/saúde/direito, violência) | 0 unidades |
| **Ideias Guardadas** | `SEU CANAL` | Tabela local `saved_trends` armazenando snapshot permanente da ideia associada ao `project_id` e `video_id` | 0 unidades |

---

## 4. Algoritmo do Score de Prioridade (0–100)

O Score de Prioridade é composto por 5 parcelas de peso equilibrado (20% cada), normalizadas de 0 a 100:

$$\text{Prioridade} = 0.20 \cdot S_{\text{vel}} + 0.20 \cdot S_{\text{nicho}} + 0.20 \cdot S_{\text{conc}} + 0.20 \cdot S_{\text{aderencia}} + 0.20 \cdot S_{\text{variedade}}$$

1. **$S_{\text{vel}}$ (Velocidade):** Percentil da velocidade de views/hora dentro da coleta atual (0 a 100).
2. **$S_{\text{nicho}}$ (Excesso sobre o nicho):** Razão `views / mediana_nicho`. Valor $\ge 3.0\times$ pontua 100; valor $= 1.0\times$ pontua 50; valor $< 0.5\times$ pontua 10.
3. **$S_{\text{conc}}$ (Oportunidade de Concorrência):** Poucos vídeos recentes no mesmo tema pontuam mais alto (concorrência baixa = 80–100; saturação alta = 20–40). Para vídeos virais de Em Alta Geral, adota-se valor neutro (50) para não distorcer o ranking.
4. **$S_{\text{aderencia}}$ (Aderência ao Canal):** Tendência originada diretamente de um pilar do canal pontua 90–100; originada de virais gerais (Em Alta Brasil/Mundo) pontua 65–75.
5. **$S_{\text{variedade}}$ (Ineditismo no Canal):** Reduz se o título compartilhar termos principais com 2 ou mais dos últimos 5 vídeos do canal, sinalizando risco de conteúdo repetitivo.

### Diagnósticos e Alertas
- Se termos de risco forem detectados: badge amarelo/vermelho `[ Risco de monetização ]` e penalidade de 30 pontos no score.
- Se variedade for $< 40$: badge amarelo `[ Atenção: repetição ]`.
- Se nenhum alerta disparar: badge verde `[ Sem risco detectado ]`.

---

## 5. Interface e Componentes Visuais (V3 Nativo)

### 5.1. Cartão de Tendência (`.card.cartao-tendencia`)
- Estrutura HTML:
  ```html
  <article class="card cartao-tendencia" data-prioridade="86" data-velocidade="29000" data-perene="false" data-guardado="false">
    <div class="cardthumb">
      <img src="{thumbnail_url}" alt="{topic}" loading="lazy">
      <span class="tag">{origem_rotulo}</span>
      <span class="time">{duracao}</span>
    </div>
    <div class="between" style="margin-top:12px">
      <span class="pill accent">{origem_pill}</span>
      <span class="sample">{pilar_nome}</span>
    </div>
    <h3 style="margin:8px 0 2px">{topic}</h3>
    <p class="sub">{canal} · {data_relativa} · <a href="{video_url}" target="_blank" rel="noopener noreferrer">Assistir referência ↗</a></p>
    
    <div class="signals">
      <span class="sig"><b>{views_fmt}</b> views <span class="src api">API</span></span>
      <span class="sig"><b class="up">{vel_fmt}/h</b> velocidade <span class="src calc">Calc.</span></span>
      <span class="sig"><b class="up">{ratio_fmt}</b> vs. nicho <span class="src calc">Calc.</span></span>
    </div>

    <div class="score">
      <div class="n">{score}</div>
      <div class="t"><b>{resumo_prioridade}.</b> {motivo_prioridade}</div>
      <span class="pill {status_classe}" style="margin-left:auto">{status_texto}</span>
    </div>

    <details class="more">
      <summary>Por que esta nota</summary>
      <div class="bd">
        <div class="r"><span>Velocidade</span><div class="meter ok"><b style="width:{p_vel}%"></b></div><b>{p_vel}</b><span class="src calc">Calc.</span></div>
        <div class="r"><span>Acima do nicho</span><div class="meter ok"><b style="width:{p_nicho}%"></b></div><b>{p_nicho}</b><span class="src calc">Calc.</span></div>
        <div class="r"><span>Concorrência ({rotulo_conc})</span><div class="meter {c_conc}"><b style="width:{p_conc}%"></b></div><b>{p_conc}</b><span class="src calc">Calc.</span></div>
        <div class="r"><span>Aderência ao canal</span><div class="meter"><b style="width:{p_ad}%"></b></div><b>{p_ad}</b><span class="src own">Canal</span></div>
        <div class="r"><span>Variedade vs. últimos 5</span><div class="meter {c_var}"><b style="width:{p_var}%"></b></div><b>{p_var}</b><span class="src own">Canal</span></div>
      </div>
    </details>

    <div class="row" style="margin-top:12px">
      <a class="btn primary small" href="{url_piloto}">⚡ Criar com piloto</a>
      <a class="btn small" href="{url_diretor}">🎬 Modo Diretor</a>
      <button class="btn ghost small btn-guardar" type="button" data-video-id="{video_id}" data-guardado="{is_saved}">
        {★ Guardado / ☆ Guardar}
      </button>
    </div>
  </article>
  ```

### 5.2. Barra de Controle, Ordenação e Filtros
- Barra de controle posicionada abaixo dos chips de pilares:
  - **Ordenar por:** `[ Prioridade | Velocidade | Mais recentes ]` via botões com links/parâmetros estáveis.
  - **Mostrar:** `[ Todos | Perenes | Sem risco | Guardados ]`.
  - Ao selecionar `Guardados`, carrega e exibe todas as ideias permanentemente salvas para o canal ativo.

### 5.3. Modal "Como calculamos" (`#dialog-como-calculamos`)
- Acionado pelo botão `ⓘ Como calculamos` na barra de ações.
- Tabela limpa explicando todas as métricas, suas origens e garantias.

---

## 6. Persistência e Integração Backend

1. **Extensão de `youtube_trends.py`:**
   - Adicionar `contentDetails` à chamada `videos.list`.
   - Parsear `contentDetails.duration` (ISO 8601 ex.: `PT1H2M10S` $\to$ string formatada `01:02:10` ou `PT11M40S` $\to$ `11:40`).
   - Persistir duração formatada e segundos na evidência.
2. **Pasta Permanente de Ideias Guardadas (`saved_trends`):**
   - Tabela SQL:
     ```sql
     CREATE TABLE IF NOT EXISTS studio.saved_trends (
       project_id TEXT NOT NULL,
       video_id TEXT NOT NULL,
       title TEXT NOT NULL,
       channel_title TEXT,
       thumbnail_url TEXT,
       video_url TEXT,
       duration TEXT,
       views BIGINT,
       category_name TEXT,
       score INT,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       PRIMARY KEY (project_id, video_id)
     );
     ```
   - Endpoints REST para favoritar/desfavoritar:
     - `POST /studio/projects/{id}/saved-trends`: recebe snapshot do cartão e persiste.
     - `DELETE /studio/projects/{id}/saved-trends/{video_id}`: remove da pasta de ideias do canal.
3. **Módulo de Priorização Pura (Domínio):**
   - Criação de `domain/trend_priority.py`: funções puras sem I/O para cálculo das 5 parcelas, normalização e diagnóstico de alertas.

---

## 7. O que Fica a Critério do Construtor (Builder)

- Implementação do parser de duração ISO 8601 (via regex ou biblioteca padrão).
- Mapeamento da migração `0049_saved_trends.sql` compatível com PostgreSQL e SQLite de testes.
- Tratamento de fallbacks visuais caso miniaturas do YouTube demorem a responder.
- Ajuste fino da interação JavaScript de clique rápido no botão de guardar (feedback visual otimista).
