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
  - `search.list` (pesquisa de vídeos em alta na janela): **100 unidades** por consulta.
  - `videos.list` (estatísticas de visualização): **1 unidade** por lote de até 50 vídeos.

### 2. Teto e Moderação de Uso
- O workflow diário de tendências limita-se a **no máximo 10 consultas curadas por dia** (≈ 1.010 unidades de cota).
- Isso preserva cerca de **9.000 unidades diárias**, garantindo margem para até 5 uploads diários sem esgotar a cota (`quotaExceeded`).

### 3. Parâmetros das Consultas
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
  - Payload opcional: `{"queries": ["termo customizado"]}`. Se omitido, utiliza as queries agregadas de todos os pilares do projeto.
  - Consulta a YouTube Data API v3, armazena os tópicos e evidências e retorna a contagem de registros persistidos.

---

## Status da Coleta e Exibição no Painel
- **Atualizado:** Consulta realizada dentro da janela do filtro selecionado.
- **Desatualizado (stale):** Se a última consulta bem-sucedida for mais antiga que o período selecionado (ex.: consulta de 10 dias atrás para um filtro de 7 dias), o painel exibe um aviso explícito de que os dados estão desatualizados.
- **Sem Coleta:** Se nunca houve ingestão ou se a cota foi atingida, o painel exibe `"Ainda não há coleta de tendências"` — nunca dados fictícios.
