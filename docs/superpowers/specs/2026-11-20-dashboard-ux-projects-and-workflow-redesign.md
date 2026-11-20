# Especificação de Design: Redesign do Painel (Tema YouTube Dark Neutro, Gestão de Projetos, Esteira de Workflow e Amostras de Vídeos)

**Data:** 2026-11-20  
**Status:** Aprovado pelo Usuário  
**Contexto:** Faceless Studio (`youtube-faceless-starter`) — Painel Web do Operador (`/studio/panel`).

---

## 1. Intenção e "O Porquê"

O painel do Faceless Studio acumulou elementos com fundo azul-marinho (`#0b111e`) e uma rolagem infinita de mais de 40 cards de tendências que engoliam a tela, deixando o dashboard sobrecarregado ("poluído") e escondendo o que é essencial para o operador: **as métricas da esteira de produção (workflow n8n / FFmpeg) e as amostras dos vídeos sendo gerados**. Além disso, o formulário de "Novo Vídeo" carregava apenas o projeto padrão do banco sem qualquer interface para cadastrar e alternar novos canais/projetos.

Esta especificação define:
1. **Tema YouTube Dark Neutro:** substituição de todo o tom azul-marinho por preto carvão neutro (`#0f0f0f`), superfícies de cards em `#181818` / `#212121`, bordas finas em `#282828` e tipografia limpa.
2. **Gestão de Projetos / Canais no Painel:**
   - Seletor de canal ativo no topo do painel (`Canal: [ Projeto ▼ ]`).
   - Modal acessível in-page para cadastrar novos canais (`Nome`, `Nicho`, `Idioma`), que consome o endpoint existente `POST /studio/projects` e atualiza a seleção na hora.
   - Sincronização automática com o formulário de "+ Novo Vídeo".
3. **Métricas Visuais e Esteira do Workflow (Pipeline):**
   - Cards executivos com destaque visual para as fases da esteira:
     - 🔵 **Em Produção:** jobs de render / áudio ativos no n8n.
     - 🟡 **Aguardando Aprovação:** vídeos que exigem revisão humana.
     - 🟢 **Concluídos / Publicados:** vídeos finalizados no período.
     - 🟣 **Gasto no Mês vs Teto:** controle de orçamento com barra de progresso.
4. **Cards Ricos de Amostras de Vídeos:**
   - Grid moderno com as amostras dos vídeos do canal ativo: thumbnail, título, formato (Short / Long), duração, custo e botões diretos de ação (`👁️ Ver Prévia`, `✓ Aprovar`, `⚙️ Ver Progresso`).
5. **Radar de Tendências Despoluído:**
   - O radar de oportunidades é contido de forma elegante (com paginação ou limite inicial compacto de 6 cards e botão de expansão "Ver mais tendências (+N)"), evitando que a lista infinita empurre o resto do dashboard para baixo.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos
- **Tema Visual YouTube Dark Oficial:** Fundo `#0f0f0f`, superfícies `#181818` / `#1f1f1f`, bordas `#282828`. Zero tons azul-marinho.
- **Cadastro e Alternância de Projetos:**
  - Dropdown no topbar para alternar o canal ativo (`?project_id=...`).
  - Modal in-page `+ Novo Projeto / Canal` chamando `POST /studio/projects` via fetch com feedback de sucesso/erro.
- **Esteira de Produção em Destaque:**
  - Cards executivos de status do pipeline com cores semânticas e visual limpo.
- **Grid de Amostras de Vídeos:**
  - Exibição dos vídeos mais recentes em formato de cards visuais com status, thumbnail/placeholder e botões de ação rápida.
- **Radar de Tendências Otimizado:**
  - Exibição inicial dos virais com expansor "Ver mais tendências" sem esticar a página indefinidamente.

### Não-Objetivos
- Não alterar a lógica de banco de dados do schema de projetos (`studio.projects` já possui a estrutura completa necessária).
- Não criar dependências de frameworks frontend pesados (React, Vue, Tailwind); manter o painel ultrarrápido em Vanilla CSS/JS com CSP Nonce.

### Anti-Objetivos
- **Zero XSS:** Proibido usar `innerHTML` com dados dinâmicos. Toda interpolação de strings usa `e(...)` (`html.escape`) e DOM seguro (`textContent`).
- **Zero Scripts sem Nonce:** Todos os scripts e estilos da página usam `nonce="{nonce}"`.
- **Zero Quebra de Testes:** Manter total compatibilidade com a suíte de testes de integração e páginas (`tests/test_panel_page.py`, `tests/test_panel.py`, etc.).

---

## 3. Arquitetura e Detalhes de Implementação

### 3.1. API de Projetos (`renderer/app/studio/api/routes.py` & `panel.py`)
- O endpoint `POST /studio/projects` já existe e aceita `{ name: str, niche?: str, language?: str }`.
- O modal de criação de projetos no painel enviará JSON para `/studio/projects` com autenticação Basic/Worker.
- Após o cadastro com sucesso, o novo projeto é selecionado e a página é recarregada para o novo canal ativo (`/studio/panel?project_id={new_id}`).

### 3.2. Seletor Global de Canais
- No topo da página (`.topbar`), adiciona-se o seletor `<select id="global-project-select">` listando `view.projects`.
- Ao alterar o select, o navegador navega para `/studio/panel?project_id={id}&days={days}`.
- O formulário de criação de vídeo já inicializa com o projeto ativo selecionado.

### 3.3. Estilização YouTube Studio Dark (`renderer/app/studio/api/panel.py`)
- `:root`:
  - `--bg: #0f0f0f;` (fundo principal neutro)
  - `--surface: #181818;` (cards principais)
  - `--surface-alt: #212121;` (inputs, selects, barras secundárias)
  - `--border: #282828;` (bordas sutis)
  - `--text: #f1f1f1;` (texto principal em alto contraste)
  - `--text-muted: #aaaaaa;` (texto secundário)
  - `--accent-red: #cc0000;` (vermelho característico do YouTube)

### 3.4. Amostras de Vídeos em Cards Ricos
- Cada vídeo do canal é apresentado com status claro, badge de formato (`Short` / `Long`), miniatura ou placeholder 16:9, e botões contextuais:
  - Se `preview` em ações: botão `👁️ Ver Prévia` (leva a `/studio/videos/{id}/preview`).
  - Se `progress` em ações: botão `⚙️ Ver Progresso` (leva a `/studio/panel/videos/{id}`).
