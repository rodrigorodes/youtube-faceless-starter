# Prévia usando a casca compartilhada (fim da duplicação de UI)

Worktree `preview-shell`, branch **`feat/preview-shell`**, base **`f57dae2`** (HEAD do `main`
no momento da fatia — `git rev-parse HEAD` na worktree criada). Fatia `rich-boundary` rodou em
paralelo, em outra worktree; nada foi escrito fora desta aqui e `renderer/app/rich.py` não foi tocado.

## Commits

| commit | conteúdo |
|---|---|
| `48fed4a` | `fix(preview): prévia e roteiro usam a casca compartilhada` — `api/preview.py`, `api/panel.py`, `tests/test_panel_page.py`, `tests/test_publishing.py`, `tests/test_script_page.py` + arquivo verbatim em `archive/` |
| (este relatório) | `docs(preview-shell): relatório da fatia` |

Sem push, sem merge, sem rebuild do stack.

## Problema

A página de prévia (`renderer/app/studio/api/preview.py`) tinha uma **cópia velha da casca**:
um `<aside class="sidebar">` hardcoded com a navegação antiga (`FACELESS STUDIO` /
`Pipeline de Vídeos` / "Temas em Alta" / "+ Novo Vídeo") e ~150 linhas do design system
(`:root` com a paleta, `.sidebar`, `.nav-menu`, `.nav-item`, `.budget-*`, …). Enquanto isso,
todas as outras telas passam por `api.panel.render_sidebar(...)`.

## O que mudou

### `renderer/app/studio/api/preview.py`

- Passa a usar a casca compartilhada: `from . import panel as shell` +
  `shell.render_sidebar(active="videos", base_href="/studio/panel", side_card_html=side_card_html)`.
- **Removida** a constante `CSS` inteira (o `:root`, a paleta e toda a duplicação do design
  system). A página usa `<style nonce="{nonce}">{shell.CSS}</style>`.
- **Removido** o `<aside class="sidebar">` hardcoded.
- Conteúdo da página **intacto**: QA, roteiro narrado, fontes, créditos, decisão de aprovação,
  player/prévia, o formulário com o botão de decisão (`id="approve"` / `id="reject"`), o `output`
  de status e os **avisos de segurança** (CSP com `nonce`, `default-src 'none'`,
  `frame-ancestors 'none'`, `no-store`) e o escape de todo texto.
- `active="videos"`: a prévia é a página do vídeo (mesmo `active` do detalhe do vídeo,
  `panel.py:3099`); `base_href="/studio/panel"` porque a prévia não contém as seções do painel
  (as âncoras voltam ao painel em vez de apontar para âncora inexistente).
- `side_card_html`: um `.side-card` com fato verificável ("Sobre esta prévia" — revisar QA,
  roteiro e fontes; a publicação é do workflow do n8n). **Nenhum número inventado**: o `Preview`
  não traz orçamento do mês, então não existe `US$ 0,00` nem custo projetado.
- Estilo da página sem CSS próprio: `card-panel` → `card`, `layout` → `layout-detail`,
  botões → `btn btn-primary` / `btn btn-danger`. O que faltava no design system foi para a
  **casca** (ver abaixo), não para o arquivo da página.
- Bônus: o refactor eliminou o `f-string` com `\` na expressão (linha 331 antiga), então
  `preview.py` volta a **parsear em Python 3.11** — os testes de página não dependem mais
  exclusivamente do container 3.12 para importar a prévia.

### `renderer/app/studio/api/panel.py` (a casca, para todo mundo)

- Utilitários que faltavam no design system compartilhado, agora definidos uma vez:
  `.badge`, `.ok`, `.bad`, `.hint`, `.btn-danger` e o seletor de elemento `video` (player da prévia).
  Nenhum é específico de um arquivo de página — todos passam a valer para qualquer tela.
- `render_script` (tela de Roteiro) também tinha `<aside class="sidebar">` próprio: agora usa
  `render_sidebar(active="videos", base_href="/studio/panel", side_card_html=…)`.

## Linhas de CSS/HTML duplicado que saíram de `preview.py`

- `preview.py`: **453 → 136 linhas** (`git diff --numstat`: 26 inserções, **343 remoções**).
- Bloco **CSS** removido: linhas 10–287 do original → **278 linhas** (o `:root`/paleta + `.sidebar`,
  `.brand*`, `.nav-*`, `.budget-*`, `.app-layout`, `.main-content`, `.topbar`, `.content-body`,
  inputs/botões/tabelas genéricos e o CSS específico da página).
- Bloco `<aside>` hardcoded removido: linhas 373–423 do original → **51 linhas**.
- Total: **329 linhas de CSS/HTML duplicado** fora de `preview.py` (o resto da redução é
  simplificação do `render_preview`). Em `panel.py` entraram **40 linhas** de CSS/util para a casca.
- Conteúdo verbatim arquivado em
  `archive/preview-shell-removed.md` (via `git add -f`).

## Outras páginas com o mesmo defeito

Busca por `<aside class="sidebar">` hardcoded em `renderer/app/studio/api/*.py`:

| ocorrência | natureza | ação |
|---|---|---|
| `preview.py:374` | cópia antiga da casca (nav velha + CSS duplicado) | **corrigida** |
| `panel.py:3336` (tela de Roteiro, `render_script`) | `<aside>` próprio com marca V2 e nav **truncada** ("Início" + "Detalhe do vídeo"), sem a casca | **corrigida** |
| `panel.py:162` | definição legítima dentro de `render_sidebar` (a própria casca) | mantida |

Foram **duas** páginas corrigidas na mesma fatia. Nenhum link foi perdido: o "Detalhe do vídeo"
que a nav truncada do Roteiro oferecia continua no topo da página ("← Voltar ao vídeo") e a
casca já leva a "Vídeos"/"Início".

## Como provei que a prévia agora usa a casca nova

1. **Navegação extraída do HTML renderizado.** `tests/test_panel_page.py` →
   `test_preview_page_has_unified_sidebar_layout` extrai `<nav class="nav" aria-label="Principal">`
   via o helper `_nav_items` e afirma os itens atuais (Início, Produção, Tendências, Vídeos,
   Canais, Analytics, Equipe, Configurações), **um único** `aria-current="page"` em "Vídeos", e a
   **ausência** de `FACELESS STUDIO`, `Pipeline de Vídeos`, `Temas em Alta` e `+ Novo Vídeo`.
2. **Mesma prova sem banco** em `tests/test_publishing.py::test_preview_page_renders_sidebar_navigation`:
   chama `render_preview` direto, exige a marca `Faceless Studio V2`/`YouTube Automation`, a nav da
   casca e a paleta única (`--bg-canvas: #101827`), e recusa a paleta antiga
   (`--bg: #0f0f0f`, `--surface: #181818`) e as strings velhas.
3. **Regressão da paleta**: `test_panel_page.py::test_panel_uses_dark_mockup_palette_and_preview_stays_dark`
   passa a afirmar que `preview` **não tem** mais `CSS` próprio e que a página renderizada usa os
   tokens da casca.
4. **Segunda página**: `tests/test_script_page.py::test_roteiro_page_uses_the_shared_shell` faz o
   mesmo para o Roteiro.
5. Render direto (fora do pytest), inspeção do `<aside>`: marca `Faceless Studio V2` /
   `YouTube Automation`, nav `Início | Produção | Tendências | Vídeos | Analytics | Canais | Equipe | Configurações`,
   `aria-current="page"` = 1, strings velhas ausentes, paleta da casca presente, conteúdo
   (QA, Roteiro narrado, Fontes, Decisão de Aprovação, `id="approve"`/`id="reject"`) presente e
   CSP intacta. Conferi também que **prévia e Roteiro passam no `assert_ux_contract`** canônico.
6. Teste de casca existente **estendido** (não duplicado): reaproveitei `_nav_items` e
   `assert_ux_contract`.

## O que decidi manter por funcionalidade

- Todo o conteúdo e os fluxos da prévia (aprovar/rejeitar via JS, `override_reason` quando o QA
  reprova, agendamento, tags, rótulos e estados vazios explícitos) — nada foi removido.
- Os avisos de segurança: CSP com `nonce` e política restritiva, escape de todo texto (o teste
  `test_preview_page_is_escaped_locked_down_and_complete` continua passando).
- O player, agora estilizado pela casca (`video` na `panel.py`), e os botões de decisão, agora
  `btn btn-primary` (aprovar) e `btn btn-danger` (rejeitar).
- Nada de número ilustrativo: o card lateral e a QA continuam com dado real ou vazio explícito.

## Testes (focados, em container)

Runner: imagem `faceless-v2-hygiene-test-local:latest` (Python 3.12) com Postgres descartável
próprio (`pshell-pg`, `--tmpfs`, prova de 64 hex montada read-only em `/budget-test-proof/proof`
no banco e no runner, `STUDIO_TEST_DSN` + `STUDIO_BUDGET_TEST_PROOF_FILE`). Não usei o stack do
`localhost:8000` nem rebuildei nada.

```
tests/test_panel.py tests/test_panel_domain.py tests/test_panel_page.py tests/test_panel_api.py
tests/test_panel_repo.py tests/test_panel_production_page.py tests/test_panel_production_render.py
tests/test_script_page.py tests/test_publishing.py tests/test_architecture.py tests/test_ux_contract.py
→ 197 passed, 1 skipped (skip pré-existente: Node.js ausente no filtro JS de test_panel.py)

tests/test_qa_legacy_read.py tests/test_channels_page.py tests/test_analytics_page.py
tests/test_analytics_dashboard.py tests/test_publication_api.py
→ 87 passed

tests/test_publish_api.py
→ 14 passed
```

Não existe `tests/test_preview*.py` neste repo: os testes da prévia vivem em
`test_publishing.py` (unitário, sem banco) e `test_panel_page.py` (via `TestClient`) — ambos
rodados e atualizados. `test_publication_api.py` também é exercitado.

## Higiene

`python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (rc 0).
Nenhum segredo impresso; a prova do Postgres descartável é aleatória, só de teste, e é
descartada junto com o container.

## Limitações

- Sem navegador real: o layout (player + `layout-detail`, cards empilhados) foi validado por
  HTML/CSS, não por screenshot.
- A VM do Docker está apertada por causa das fatias em paralelo; rodei só as partições focadas
  acima, que cobrem prévia, todos os `test_panel*`, arquitetura, contrato de UX e as telas que
  compartilham a casca. A suíte completa não foi executada de uma vez.
