# Especificação de Design: Redesign do Painel & Prévia (Tema YouTube Dark Neutro, Gestão de Projetos, Menu Unificado, Esteira de Workflow e Amostras de Vídeos)

**Data:** 2026-11-20  
**Status:** Aprovado pelo Usuário  
**Contexto:** Faceless Studio (`youtube-faceless-starter`) — Painel Web do Operador (`/studio/panel`) e Tela de Prévia (`/studio/videos/{id}/preview`).

---

## 1. Intenção e "O Porquê"

O painel e a tela de prévia do Faceless Studio acumulavam inconsistências visuais e de navegação:
1. **Fundo Azulado e Poluição Visual:** O tom azul-marinho (`#0b111e`) e a lista infinita de mais de 40 cards de tendências engoliam a tela, escondendo o status da esteira de produção (workflow n8n / FFmpeg) e as amostras dos vídeos.
2. **Falta de Gestão de Projetos:** O formulário de "Novo Vídeo" carregava apenas o projeto padrão sem interface para cadastrar e alternar canais.
3. **Página de Prévia Isolada:** A tela de prévia do vídeo (`/studio/videos/{id}/preview`) era renderizada sem o menu lateral do Studio, quebrando a consistência de navegação e a experiência do usuário (UX).

Esta especificação define:
1. **Tema YouTube Dark Neutro Unificado:** substituição de todo o tom azul-marinho por preto carvão neutro (`#0f0f0f`), superfícies de cards em `#181818` / `#212121`, bordas finas em `#282828` e tipografia limpa em todas as telas (`/panel` e `/preview`).
2. **Menu Lateral Unificado na Página de Prévia:**
   - A tela de prévia (`/studio/videos/{id}/preview`) herda a mesma estrutura de layout do Studio: barra lateral com menu (`Painel`, `Temas em Alta`, `Vídeos`, `+ Novo Vídeo`, `API Docs`, `n8n`), topbar com breadcrumb e rodapé com teto financeiro.
3. **Gestão de Projetos / Canais no Painel:**
   - Seletor de canal ativo no topo do painel (`Canal: [ Projeto ▼ ]`).
   - Modal acessível in-page para cadastrar novos canais (`Nome`, `Nicho`, `Idioma`), que consome o endpoint existente `POST /studio/projects` e atualiza a seleção na hora.
4. **Métricas Visuais e Esteira do Workflow (Pipeline):**
   - Cards executivos com destaque visual para as fases da esteira:
     - 🔵 **Em Produção:** jobs de render / áudio ativos no n8n.
     - 🟡 **Aguardando Aprovação:** vídeos que exigem revisão humana.
     - 🟢 **Concluídos / Publicados:** vídeos finalizados no período.
     - 🟣 **Gasto no Mês vs Teto:** controle de orçamento com barra de progresso.
5. **Cards Ricos de Amostras de Vídeos:**
   - Grid moderno com as amostras dos vídeos do canal ativo: thumbnail, título, formato (Short / Long), duração, custo e botões diretos de ação (`👁️ Ver Prévia`, `✓ Aprovar`, `⚙️ Ver Progresso`).
6. **Radar de Tendências Despoluído:**
   - O radar de oportunidades é contido de forma elegante (com exibição inicial dos 6 virais mais fortes e botão expansor "Ver mais tendências (+N)"), mantendo o painel sempre ágil e despoluído.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos
- **Tema Visual YouTube Dark Oficial:** Fundo `#0f0f0f`, superfícies `#181818` / `#1f1f1f`, bordas `#282828`. Zero tons azul-marinho.
- **Menu e Layout Unificados na Prévia:**
  - A tela de prévia inclui a barra lateral do Studio com navegação completa e topbar consistente.
- **Cadastro e Alternância de Projetos:**
  - Dropdown no topbar para alternar o canal ativo (`?project_id=...`).
  - Modal in-page `+ Novo Projeto / Canal` chamando `POST /studio/projects` via fetch com feedback de sucesso/erro.
- **Esteira de Produção em Destaque:**
  - Cards executivos de status do pipeline com cores semânticas e visual limpo.
- **Grid de Amostras de Vídeos:**
  - Exibição dos vídeos mais recentes em formato de cards visuais com status, thumbnail/placeholder e botões de ação rápida.
- **Radar de Tendências Otimizado:**
  - Exibição inicial compacta com expansor interativo sem rolagem infinita.

### Não-Objetivos
- Não alterar as regras de transição de estado da prévia (`aprovar`, `rejeitar`, `override`).

### Anti-Objetivos
- **Zero XSS:** Proibido usar `innerHTML` com dados dinâmicos. Toda interpolação usa `e(...)` (`html.escape`) e DOM seguro (`textContent`).
- **Zero Scripts sem Nonce:** Todos os scripts e estilos da página usam `nonce="{nonce}"`.
- **Zero Quebra de Testes:** Manter total compatibilidade com `tests/test_panel_page.py`, `tests/test_publishing.py`, etc.
