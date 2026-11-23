# 19. Coleta de Tendências e Cota (Fase B)

Este documento registra a decisão de arquitetura, limites de cota e termos de uso para a exibição de **Temas em Alta** no painel do Faceless Studio.

## Regra Fundamental de Verificabilidade
**Nenhum tema aparece no painel como "tendência" sem uma fonte e data comprováveis.**
Modelos de linguagem (LLMs) são expressamente proibidos de inventar ou simular tópicos "em alta". Qualquer lote enviado para ingestão no Studio precisa conter:
- `source_name`: Nome da fonte (ex.: `"YouTube Data API"`).
- `source_url`: URL oficial HTTPS com host autorizado (ex.: `https://www.googleapis.com/youtube/v3/search`).
- `observed_at`: Data e hora da consulta com fuso horário (não no futuro).
- `window_start` e `window_end`: Janela de observação (máximo de 31 dias).
- Evidências concretas (título, canal, URL e contagem de visualizações).

Se qualquer item do lote violar esses critérios, o lote inteiro é recusado (`TrendRefused`, HTTP 422) e nada é persistido.

---

## Fonte Escolhida: YouTube Data API v3

### 1. Como Funciona a Cota
- A cota diária gratuita padrão da Google Cloud Console é de **10.000 unidades/dia** por projeto.
- Essa cota é **compartilhada** entre a coleta e a publicação de vídeos:
  - `videos.insert` (upload de vídeo): **1.600 unidades** por tentativa.
  - `search.list` (pesquisa de vídeos por palavra-chave na janela): **100 unidades** por consulta.
  - `videos.list` com `chart=mostPopular` (Em Alta Brasil e Em Alta Mundo): **apenas 1 unidade** por chamada de até 50 vídeos.
  - `videos.list` (estatísticas de visualização): **1 unidade** por lote de até 50 vídeos.

### 2. Radar de Tendências: Em Alta Brasil e Mundo (Alta Eficiência)
Para enriquecer a esteira sem consumir a cota de 100 unidades do `search.list`, o Studio incorpora a coleta de tendências gerais por região:
- **Em Alta Brasil:** `videos.list` com `chart=mostPopular` e `regionCode=BR`. Custo: **1 unidade de cota**.
- **Em Alta Mundo:** `videos.list` com `chart=mostPopular` e `regionCode=US` (global). Custo: **1 unidade de cota**.
- **Fonte Oficial e Hosts Autorizados:** Os itens coletados via `chart=mostPopular` utilizam `source_name = "YouTube Brasil (Em Alta)"` ou `"YouTube Global (Em Alta)"` e `source_url = "https://www.youtube.com/feed/trending"`. O host `www.youtube.com` faz parte dos hosts permitidos no domínio (`STUDIO_TREND_SOURCES`).
- O endpoint unificado `POST /studio/projects/{id}/trends/refresh` busca os termos do canal e o Em Alta (BR e US) **da categoria do pilar**, com resiliência a falhas parciais do Em Alta.

### 3. Teto e Moderação de Uso (o que o código impõe)
Cada **termo buscado custa 100 unidades**; cada chamada de Em Alta custa 1. Um "Buscar agora" completo gasta no máximo
**6 termos x 100 + 3 categorias x 2 regiões x 1 = 606 unidades**. Para não esgotar os 10.000/dia (divididos com o upload, 1.600 por tentativa):
- `MAX_SEARCH_TERMS_PER_REFRESH = 6`: os termos entram **intercalados entre os pilares** (1º termo de cada pilar antes do 2º de qualquer um).
- `SEARCH_COOLDOWN = 6 h`: termo buscado há menos de 6 horas **não é buscado de novo** (repetir o clique não repete a conta). Se todos
  estiverem dentro do intervalo, a coleta devolve `{"stored": 0}` sem gastar cota e a tela diz "Nada novo".
- O Em Alta cobre no máximo 3 categorias (`MAX_POPULAR_CATEGORIES`).
- Cada busca pede 10 vídeos (`SEARCH_RESULTS_PER_TERM`): o custo é por chamada, não por vídeo.

### 3.1 Termos do canal e Em Alta por categoria
- **Termos:** os do pilar. Sem pilar, o **nicho do canal** é o termo. Sem pilar e sem nicho, a coleta é recusada (`NoSearchTerms`, HTTP 422):
  não se inventa assunto (não há mais termos fixos de música eletrônica).
- **Em Alta por categoria:** `videos.list?chart=mostPopular` recebe `videoCategoryId` derivado do pilar (`domain/youtube_categories.py`,
  heurística por palavra-chave: Games 20, Música 10, Esportes 17, Pets 15, Ciência e tecnologia 28, Educação 27 etc.). Pilar sem categoria
  identificável **não gera Em Alta** (o Em Alta da plataforma inteira não é ideia do nicho). A categoria pode não existir como "mais populares" em
  alguma região (a API recusa): essa chamada falha sozinha e a coleta segue.
- O pilar de origem é gravado em `trend_topics.category_id` (termos e Em Alta) e é ele que liga o cartão ao pilar; a correspondência por texto
  só vale para coletas antigas sem pilar.

### 3.2 O que a tela mostra (`domain/trend_cards.py`)
- **Um cartão por vídeo.** A linha de busca por termo traz até 10 vídeos e vira um cartão para cada (o termo fica como contexto).
- **Sem repetição.** A coleta grava linhas novas a cada "Buscar agora"; o mesmo vídeo coletado várias vezes aparece uma vez, com a coleta mais recente.
- **Variedade.** No máximo **2 cartões por canal** (os mais vistos).
- Ordenação por visualizações do vídeo (não a soma do termo).

### 4. Parâmetros das Consultas de Pilares
- `q`: Termo de busca curado no projeto (ex.: `"ADE lineup"`, `"Amsterdam Dance Event"`).
- `type`: `video`
- `order`: `viewCount`
- `publishedAfter`: Início da janela (`now() - 7 days` em formato RFC 3339).
- `relevanceLanguage`: `pt`
- `regionCode`: `BR`

---

## Como Obter e Configurar a Credencial

A credencial de leitura do YouTube fica **exclusivamente no n8n** (nunca no `.env` do renderer e nunca no Git), da mesma forma que as credenciais do analytics.

1. Acesse o **Google Cloud Console** no mesmo projeto onde foi configurado o OAuth2 do YouTube.
2. Vá em **APIs e Serviços > Credenciais > Criar Credenciais > Chave de API**.
3. Em **Restrições de API**, restrinja a chave para operar apenas na **YouTube Data API v3**.
4. No n8n, crie uma credencial do tipo **Query Auth** ou **Header Auth** com a chave criada.
5. No workflow `05-trends-daily.json`, vincule a credencial nos nós de consulta da API.
6. O envio dos dados para o renderer utiliza a credencial existente `studio_worker` (`STUDIO_WORKER_TOKEN`) via `POST /studio/trends`.

---

## Pilares de Conteúdo e Categorias por Projeto

Para evitar que o canal dependa de buscas genéricas e sem foco editorial, o Studio organiza as tendências em **Pilares de Conteúdo** (categorias fixas por projeto).

### 1. Conceito Editorial
- Cada projeto/canal possui seus pilares estratégicos (exemplo para Música Eletrônica: `Festivais & Lineups`, `DJs & Bastidores`, `Rankings & Charts`).
- Cada pilar possui uma lista curada de termos de busca (`queries`), limitados a **no máximo 10 termos por categoria** para evitar consumo descontrolado da cota da YouTube Data API.
- Tópicos coletados são associados automaticamente ao pilar correspondente tanto pela chave quanto por correspondência léxica de termos de busca nos títulos de evidências.

### 2. Endpoints da API de Categorias e Tendências

As operações de categorias são autenticadas por `STUDIO_WORKER_TOKEN` (Bearer) ou autenticação do navegador (Basic Auth com CSRF):

- **Listar Categorias:**
  - `GET /studio/projects/{project_id}/categories`
  - Retorna a lista de pilares cadastrados, ordenados por nome.
- **Criar ou Atualizar Categoria:**
  - `POST /studio/projects/{project_id}/categories`
  - Payload:
    ```json
    {
      "id": "opcional (se omitido, gera novo id hex32)",
      "name": "Festivais & Lineups",
      "queries": ["ADE 2026", "Tomorrowland Brasil", "Ultra Brasil"]
    }
    ```
  - Validações: nome entre 1 e 100 caracteres; máximo de 10 queries; lista de queries deduplicada e sem termos em branco.
- **Excluir Categoria:**
  - `DELETE /studio/projects/{project_id}/categories/{category_id}`
  - Remove o pilar. No banco de dados, `studio.trend_topics.category_id` possui `ON DELETE SET NULL`, preservando as tendências já salvas.
- **Atualização sob Demanda de Tendências:**
  - `POST /studio/projects/{project_id}/trends/refresh`
  - Payload opcional: `{"queries": ["termo customizado"]}` (sem Em Alta e sem intervalo mínimo). Se omitido, usa os termos dos pilares (ou o nicho), respeitando o teto e o intervalo da seção 3. Sem termos: 422.
  - Consulta a YouTube Data API v3, armazena os tópicos e evidências e retorna a contagem de registros persistidos.

---

## Status da Coleta e Exibição no Painel
- **Atualizado:** Consulta realizada dentro da janela do filtro selecionado.
- **Desatualizado (stale):** Se a última consulta bem-sucedida for mais antiga que o período selecionado (ex.: consulta de 10 dias atrás para um filtro de 7 dias), o painel exibe um aviso explícito de que os dados estão desatualizados.
- **Sem Coleta:** Se nunca houve ingestão ou se a cota foi atingida, o painel exibe `"Ainda não há coleta de tendências"` — nunca dados fictícios.

---

## Experiência Visual do Radar (Padrão YouTube)

O painel adota os padrões de interface oficiais do YouTube para garantir usabilidade ágil e familiaridade ao operador:
- **Cards no Estilo YouTube Dark:** Cards em fundo escuro (`#0f0f0f` / `#1f1f1f`) com miniaturas 16:9 (`hqdefault.jpg`), badges informativas de região (`🇧🇷 Em Alta Brasil`, `🌍 Em Alta Mundo`), contadores formatados de views, e links diretos para assistir ao vídeo oficial no YouTube (`▶ Assistir no YouTube`).
- **Pílulas Arredondadas de Filtro:** Filtros rápidos no formato de pílulas oficiais do YouTube no topo da seção (`Todas`, `Em Alta Brasil`, `Em Alta Mundo` e pilares de conteúdo), permitindo alternar instantaneamente a visualização sem recarregar a página.
- **Feedback Interativo:** Durante a atualização sob demanda (`🔄 Buscar Agora`), o painel exibe um indicador animado de carregamento (*spinner* giratório), desabilitando o botão para prevenir disparos duplicados.
- **Criação Direta com Scroll Suave:** O botão `✨ Criar Vídeo deste Tema` preenche o tema selecionado no formulário de novo vídeo, abre a seção recolhida e realiza rolagem suave com foco imediato no campo.
