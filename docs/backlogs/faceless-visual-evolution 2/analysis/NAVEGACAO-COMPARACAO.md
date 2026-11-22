# Navegação — atual × protótipo (`prototype/index.html`)

Data: 2026-11-22 · Pedido do PO: "nossa configuração deveria seguir a mesma ideia do protótipo…
analisar… comparar a navegação atual com o protótipo" e "devemos alcançar o nível profissional do
protótipo".

## 1. Fontes

Protótipo (`docs/backlogs/faceless-visual-evolution 2/prototype/index.html`):

| O que | Onde | Conteúdo |
|---|---|---|
| Casca | linha 495 | `<aside class="sidebar">` → brand + **um** `<nav aria-label="Menu principal" id="globalnav">` + `<footer>` |
| Menu principal (final) | linha 583 | `NAV = [Início, Criar vídeo, Vídeos, Tendências e ideias, Desempenho, Biblioteca, **Configurações**]` — **7 itens numa lista só** |
| Render do menu | linha 604 | `NAV.map(...)` com `aria-current="page"` em `S.route===id` **ou** (`S.route==='video' && id==='videos'`) |
| Topbar | linha 496 | `<select id="channelSelect">` + tag "Conta pessoal" + "Rodrigo · proprietário · demo" |
| Faixa de demonstração | linha 496 | `<div class="demo">Protótipo navegável · alterações locais e dados de exemplo · geração e publicação simuladas</div>` |
| Rodapé da sidebar | linha 495 | "PROJETO · REVISÃO 3", "Fluxo completo…", botão "Reiniciar demo" |
| Seções de Configurações | linha 585 | `CFG = [Canais, Estratégia editorial, Marca e estilo, Produção e orçamento, Conexões e providers, Conta e equipe, Avançado e diagnóstico]` em `<nav class="cfgmenu">` (linha 622) |
| Abas do vídeo | linha 584 | `VIDEO_TABS = [Visão geral, Fontes e roteiro, Narração, Cenas e mídias, Composição, Qualidade, Publicação, Produção]` em `<nav class="vnav">` (linha 612) |
| Abas do canal | linha 524 | `.tabs`: Vídeos · Ideias · Identidade · Configurações |

Atual (`api/shell_v3.py`):

| O que | Onde | Conteúdo |
|---|---|---|
| Casca | `render_sidebar` | brand + `<nav aria-label="Principal">` (caption **"Operação"**, 6 itens) + `div.side-bottom` com `<nav aria-label="Configuração">` (**só** Configurações), nota de custo, bloco de conta e `mock-flag` |
| Menu de operação | `NAV_OPERACAO` | Início, Criar vídeo, Vídeos, Tendências e ideias, Desempenho, Biblioteca — **sem Configurações** |
| Item ativo | `_nav_item` + `_ALIASES` | `aria-current="page"`; `video → videos`, `estilos → biblioteca`, `canais → configuracoes`… |
| Topbar | `render_topbar` | `<select id="canal-ativo">` + botão "novo canal" + tema + link ⚙ Configurações; sem faixa de demonstração |
| Seções de Configurações | `render_settings_nav` | `<nav aria-label="Seções de configuração">` com **os mesmos 7 rótulos** do `CFG` |
| Abas do vídeo | `panel_video_nav.VIDEO_AREAS` | **os mesmos 8 rótulos** do `VIDEO_TABS` |

## 2. O que já está igual

- **Rótulos e ordem das 7 seções de Configurações** = `CFG` do protótipo.
- **Rótulos e ordem das 8 abas do vídeo** = `VIDEO_TABS` do protótipo.
- **Indicador de página ativa** por forma (fundo + barra + peso) e `aria-current="page"`.
- **Vídeo mantém "Vídeos" ativo** na navegação principal (nosso `_ALIASES`, igual ao
  `S.route==='video' && id==='videos'` do protótipo).
- Configurações como **área com menu próprio** (`cfgmenu` ≈ `nav[aria-label="Seções de configuração"]`).

## 3. Divergências reais (o que falta para o nível do protótipo)

### 3.1 Configurações não está no menu principal — **principal divergência** — **RESOLVIDO**
- Protótipo: **7 itens numa lista só**, com Configurações como o 7º.
- Atual: 6 itens em "Operação" **+** um segundo `<nav aria-label="Configuração">` no rodapé com um
  único item. Duas listas para a mesma navegação; o item de Configurações fica visualmente
  separado e "escondido" no rodapé.
- **Ação executada**: `NAV_OPERACAO` passou a ter 7 itens (Configurações como o 7º, `CONFIG_HREF`);
  o `<nav>` extra e a caption "Operação" foram removidos; `render_sidebar` tem **um** `<nav
  aria-label="Principal">` com a `<ul>` só. Testes atualizados em 8 arquivos + `test_panel.py`.

### 3.2 Caption "Operação" e rodapé — **RESOLVIDO**
- Protótipo: sem caption; rodapé com projeto/revisão e "Reiniciar demo" (é demo).
- Atual: caption "Operação" + rodapé com custo, bloco de conta e "Proposta V3 · pt-BR".
- **Ação executada**: caption removida. O rodapé fica com o que é real (custo + conta) — **não**
  copiar "Reiniciar demo" (é ação de demonstração).

### 3.3 Faixa de demonstração do protótipo
- Protótipo: `<div class="demo">Protótipo navegável · … · geração e publicação simuladas</div>`.
- Atual: não existe.
- **Ação**: não copiar — é a marcação de que o protótipo é simulado. O nosso app é real; já temos o
  `mock-flag` da proposta V3 no rodapé.

### 3.4 Topbar
- Protótipo: seletor de canal + tag "Conta pessoal" + "Rodrigo · proprietário · demo".
- Atual: seletor de canal + ações reais (novo canal, tema, Configurações).
- **Ação**: manter o nosso (as ações são reais). A tag/identidade de conta depende de
  autenticação real (a matriz de papéis do protótipo é proposta, não implementada).

### 3.4.1 Uma segunda casca (legado) ainda existe — achado
- `panel_shell.build_sidebar_nav` é a casca **pré-V3**: grupos "Operação" / "Configuração" /
  "Indisponível nesta versão", rótulos antigos ("Novo vídeo", "Tendências") e a marcação
  `nav.nav` + `app-layout`/`main-content` (diferente de `aside.side` + `main.main` do V3).
- **Quem ainda usa**: `panel_oauth.render_oauth_callback` (página de retorno do consentimento do
  Google, rota `/studio/oauth/callback`). `panel_production.render_new_video` também usa, mas está
  **morto** (importado por `routes.py` e nunca chamado — a rota `/studio/panel/novo-video` usa
  `panel_new_video.render_new_video_v3`).
- **Impacto**: quem volta do Google vê uma navegação diferente do resto do estúdio. É a única
  página viva com a casca antiga.
- **Recomendação**: migrar `render_oauth_callback` para `shell_v3.render_document` (casca única) e
  remover o import morto de `render_new_video`. **Não feito nesta rodada**: fora dos itens listados
  nos docs de análise; mexe em `tests/test_channels_page.py` (que fixa "Consentimento do YouTube" e
  o texto da página). Registrado para decisão.

### 3.5 Nível de tela (fora da navegação)
Lacunas visíveis para "nível profissional", em ordem de impacto:
1. **Início** — protótipo tem hero ("O que você vai criar hoje?" + campo de ideia + "Criar vídeo"),
   3 blocos de benefício (estilo/voz/orçamento, com atalhos) e "Ideias para o canal".
   **Estado atual**: o hero já existe (eyebrow, `h1`, prompt de tema, seletor de formato, "Criar
   vídeo"); o que falta é a **faixa de 3 benefícios** (estilo/voz/perfil do canal com atalhos) e
   "Ideias para o canal". O bloco "Tendências do canal" já cobre a intenção de "Ideias".
   Os 3 benefícios exigem estilo/voz/perfil do canal na `PanelView` — **não feito** (precisa
   expor esses campos na camada de aplicação; sem eles a faixa seria inventada).
2. **Biblioteca** — protótipo tem 3 abas (Estilos visuais · Mídias · Vozes); temos só estilos.
   **Estado atual**: não há fonte real para "Mídias" (assets privados não são listados por canal) nem
   para "Vozes" (não há catálogo de vozes exposto). Criar as abas com conteúdo vazio/inventado
   contraria a regra "dado real ou estado vazio explícito" — **não feito** até existir a fonte.
3. **Conta e equipe** — protótipo tem a matriz Papel × Editar/Aprovar/Publicar.
   **Resolvido**: `panel_team._permissions_matrix` gera a matriz de `ROLE_PERMISSIONS` (ver
   `CONFIG-UX-AVALIACAO.md` 3.3). Diverge de propósito do protótipo (Editor publica, no RBAC real).
4. **Prévia visual** (`feature-preview`) nos cartões de estilo/voz — decorativa no protótipo;
   **não copiada** sem frame real.

## 4. Executado nesta rodada

1. **Configurações no menu principal** (3.1 + 3.2) — `NAV_OPERACAO` com 7 itens, um único
   `<nav aria-label="Principal">`, sem caption "Operação"; testes de casca atualizados
   (`test_channels_page`, `test_connections_page`, `test_home_v3`, `test_styles_page`,
   `test_active_channel`, `test_advanced_page`, `test_panel`, `test_panel_page`,
   `test_settings_sections`).
2. **Matriz de papéis** (3.5.3 / CONFIG 3.3) — implementada.
3. Biblioteca com 3 abas (3.5.2) e Início com benefícios (3.5.1) — **não feitos** por falta de fonte
   real; registrados com o motivo.

## 5. Ordem de execução sugerida (atualizada)

1. ~~Configurações no menu principal (3.1 + 3.2)~~ — **feito**.
2. ~~Matriz de papéis (3.5.3)~~ — **feito**.
3. Início com benefícios (3.5.1) — depende de expor estilo/voz/perfil do canal na `PanelView`.
4. Biblioteca com as 3 abas (3.5.2) — depende de fonte real para Vozes/Mídias.
