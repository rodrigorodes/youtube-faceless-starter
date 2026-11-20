# Content Pillars & Categories Design Specification

**Date:** 2026-11-20  
**Status:** Approved  
**Author:** Faceless Studio Team  

## 1. Intent & Context
O Faceless Studio opera canais no YouTube no formato *faceless* (sem rosto). A melhor prática da indústria em 2026 é estruturar o canal em **Pilares de Conteúdo** (Content Pillars / Topic Clusters fixos), em vez de buscar temas genéricos.

Esta especificação define:
1. O cadastro e gerenciamento de categorias fixas por projeto (canal) com seus respectivos termos de busca no YouTube.
2. A exibição de pílulas (chips) de filtro na seção de "Temas em Alta" do painel web.
3. A possibilidade de disparar a coleta ao vivo de tendências da YouTube Data API diretamente do painel ("Buscar Agora").
4. A vinculação de cada tendência coletada ao seu respectivo pilar de conteúdo.

---

## 2. Requirements

### 2.1 Banco de Dados & Domínio
- Nova tabela `studio.project_categories`:
  - `id text PRIMARY KEY` (UUID hex 32 chars)
  - `project_id text NOT NULL REFERENCES studio.projects(id) ON DELETE CASCADE`
  - `name text NOT NULL CHECK (length(name) >= 1 AND length(name) <= 100)`
  - `queries text[] NOT NULL DEFAULT '{}'` (termos de pesquisa associados, ex.: `['ADE 2026', 'Tomorrowland']`)
  - `created_at timestamptz NOT NULL`
  - `updated_at timestamptz NOT NULL`
  - `UNIQUE (project_id, name)`
- Na tabela `studio.trend_topics`:
  - Coluna opcional `category_id text REFERENCES studio.project_categories(id) ON DELETE SET NULL`.
- Migração `0012_categories.sql` com teste em `tests/test_db.py`.

### 2.2 Endpoints REST
- `GET /studio/projects/{project_id}/categories`: Lista os pilares do projeto (autenticado por Basic ou Worker).
- `POST /studio/projects/{project_id}/categories`: Cadastra ou atualiza um pilar (valida nome de 1 a 100 caracteres e termos de busca).
- `DELETE /studio/projects/{project_id}/categories/{category_id}`: Remove o pilar.
- `POST /studio/projects/{project_id}/trends/refresh`: Executa a busca ao vivo na YouTube Data API usando as categorias do projeto e a chave local `credentials/token.env`, persistindo os resultados via `IngestTrends`.

### 2.3 Interface do Usuário (Painel Web)
- Barra de pílulas (chips) no topo de "Temas em Alta":
  - `[ Todas (N) ]`
  - `[ <Nome da Categoria> (N) ]`
  - `[ + Novo Pilar ]`
- Botão `⚙️ Gerenciar Categorias (N)` que abre um modal limpo sobre o painel:
  - Lista das categorias com termos associados e botões de excluir/editar.
  - Formulário para adicionar nova categoria com termos separados por vírgula.
  - Botão de salvar com feedback em tempo real.
- Botão `🔄 Buscar Agora` que dispara o refresh na YouTube Data API e recarrega o painel.
- Protegido por CSP nonce e sanitização HTML em todas as saídas.

---

## 3. Non-Goals
- Não alterar provedores de IA ou pipeline de renderização.
- Não expor chaves de API nem tokens ao navegador.
- Não criar páginas externas de configurações; manter a edição no próprio contexto das tendências.
