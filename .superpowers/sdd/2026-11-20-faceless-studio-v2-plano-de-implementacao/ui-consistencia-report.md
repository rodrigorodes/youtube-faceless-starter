# UI — consistência da casca (detalhe do vídeo + "Vídeos" na sidebar)

Worktree `ui-consistencia`, branch `feat/ui-consistencia`, base `db8eebb`. Escopo autorizado:
`renderer/app/studio/api/panel.py`, `tests/test_panel.py`, `tests/test_ux_contract.py` e
`docs/backlogs/Faceless_Studio_V2_Projeto_Completo/produto/prototipo.html`. Nada de
`domain/render_plan.py`, `domain/ticks.py`, `contracts/`, `scripts/export_contracts.py`,
`api/panel_production.py` nem módulos de canais/analytics/saas/f8.

## Commits

| commit | conteúdo |
|---|---|
| `568bd44` | `fix(panel): detalhe do vídeo usa a casca aprovada` — `panel.py` + os dois arquivos de teste |
| `a2a32fa` | `docs(prototipo): restaura "Vídeos" na sidebar com destino real` — só `prototipo.html` |

Sem push, sem merge. Nenhuma migração: `tests/test_db.py` não foi tocado (o `0029_...` continua livre).

## Escopo 1 — detalhe do vídeo com a casca aprovada

`render_video(...)` agora renderiza `render_sidebar(active="videos", base_href="/studio/panel",
side_card_html=side_card_html)` no lugar da `<aside class="sidebar">` própria. Consequências:

- **`active` escolhido: `videos`.** A página é o detalhe de um vídeo aberto a partir da lista
  "Vídeos"; marcar "Início" faria o detalhe parecer a Home. Como o item "Vídeos" agora tem destino
  real (ver escopo 2), `aria-current="page"` nele descreve a seção correta. Um único
  `aria-current="page"` na nav principal (coberto por teste).
- `base_href="/studio/panel"` → as quatro âncoras da casca saem como
  `/studio/panel#inicio-section`, `#producao-section`, `#trending-section` e `#videos-section`.
  Todas essas âncoras existem na página do painel (teste novo verifica âncora existente).
- **Card lateral sem inventar dado:** a `VideoDetailView` não traz orçamento do mês, então o
  `side_card_html` da casca só repete o aviso que já existia no rodapé da sidebar antiga
  ("Diagnóstico — ID, erros brutos e uso de modelos ficam em Avançado"). Nenhum `US$ 0,00`,
  nenhum número ilustrativo.
- **A nav interna do vídeo continua existindo como navegação secundária**, agora no rail
  (`<aside class="rail" aria-label="Ações do vídeo">` → `<nav class="nav-menu"
  aria-label="Navegação do vídeo">` com "Roteiro" e "Ver Prévia"/"Prévia após render"). Isso usa
  a terceira coluna que a casca aprovada já reserva (sidebar + main + rail, como em
  `mockup-telas.html`), em vez de deixar um vão vazio de 300 px. Os itens que a casca já oferece
  ("Painel", "API Docs") deixaram de ser duplicados na nav secundária; nenhum link foi perdido.
- **Rótulos de `<nav>` distintos:** `Principal`, `Recursos externos` e `Navegação do vídeo`.
- **Um único `<h1>`**: a casca não tem `h1`; o `#detalhe-heading` continua sendo o único.
- Nada mais da página foi redesenhado (topbar, timeline, `<details>` avançado, script de retry
  e retry de publicação intactos).

### UX é gate

`tests/test_ux_contract.py::test_video_detail_satisfies_the_ux_contract` já aplicava
`assert_ux_contract` ao detalhe, mas passava de forma **vacuosa**: `_nav_items()` devolve `[]`
quando a página não tem `<nav class="nav" aria-label="Principal">`, e a regra R2 (item
indisponível não focável) nunca era exercitada. O teste agora exige `_nav_items(html)` não vazio,
então o contrato morde de verdade no detalhe: estados com texto, custo rotulado, sem stack trace
fora do avançado, `<details>` fechado, viewport + `@media`, um `<h1>`, sem `<progress>`, sem texto
do mockup, itens "em breve"/"SaaS" como `<span tabindex="-1">`.

## Escopo 2 — "Vídeos" com destino real

- **Casca (`build_sidebar_nav`)**: o item já existia na base (`468b56a`) apontando para
  `#videos-section`, e essa seção existe no painel (`<section ... id="videos-section">`). Ou seja,
  no produto o item nunca foi link morto — o que faltava era prova. Foi adicionado
  `test_render_panel_shell_nav_targets_exist_in_the_page`, que exige `id="videos-section"` na
  página e valida **toda** âncora interna da casca contra os `id` presentes (nenhuma âncora morta).
  Nenhum código de navegação precisou mudar.
- **`prototipo.html`** (artefato de design aprovado, que tinha removido o item): item
  `<a href="#videos" data-screen="videos">▷ Vídeos</a>` restaurado em "Operação" (mesma posição
  e ícone de `mockup-telas.html`). A lista virou âncora real: `<section class="block" id="videos">`
  com `<h2 id="h-videos" tabindex="-1">`, espelhando o `id="videos"` de `mockup-proposta.html`.
- **Roteamento do protótipo**: `#videos` não é tela própria, então entrou um mapa de alias
  (`ALIASES`): a rota abre a tela Início, marca **só** o item "Vídeos" com `aria-current="page"` e
  leva o foco para `#h-videos`. `render()`/`routeFocus()`/`show()` passaram a receber a rota
  (`{key, view, anchor}`) em vez do id da tela; o foco visível continua no CSS existente
  (`:focus-visible { outline: 2px solid var(--info) }`).
- **Prova do roteamento**: `node --check` no script extraído (rc 0) e execução do IIFE num DOM
  mínimo em Node:
  - deep link `#videos` → `aria-current` em `videos`;
  - clique em "Vídeos" → `aria-current` só em `videos`, `#h-videos` recebe `tabindex="-1"` e foco.

## Testes (TDD RED → GREEN)

1. **RED** (antes de tocar em `panel.py`), `pytest tests/test_ux_contract.py tests/test_panel.py`:
   **2 failed, 44 passed** — as duas falhas eram exatamente as novas:
   `test_video_detail_satisfies_the_ux_contract` (nav principal ausente) e
   `test_video_detail_uses_the_shell_and_videos_has_a_real_destination` ("Início" fora da casca).
2. **GREEN** (mesmos arquivos): **46 passed**.
3. **Docker** `faceless-v2-hygiene-test-local:latest`, `-p no:cacheprovider`, Postgres descartável
   próprio (`ui-pg`, rede `ui-net`, `--tmpfs /var/lib/postgresql/data`, prova de 64 hex montada
   read-only em `/budget-test-proof` tanto no banco quanto no runner, `STUDIO_TEST_DSN` +
   `STUDIO_BUDGET_DISPOSABLE_DSN` + `STUDIO_BUDGET_TEST_PROOF_FILE`):

```
tests/test_ux_contract.py tests/test_panel.py tests/test_panel_page.py
tests/test_panel_api.py tests/test_panel_production_render.py tests/test_panel_production_page.py
→ 126 passed, 1 skipped (tests/test_panel.py:513 — "Node.js necessário para exercitar o filtro
  JavaScript"; skip pré-existente, não relacionado)
```

## Flakiness / falhas do ambiente (verificadas contra a base)

`test_render_adapters.py` falha **9 failed / 7 passed** nesta imagem, e falha igual com o
`git stash` das minhas mudanças (base `db8eebb` limpa): **9 failed / 7 passed**. Causa: o `ffmpeg`
do container morre com SIGKILL — reproduzido fora do pytest, sem teste nenhum:

```
docker run --rm faceless-v2-hygiene-test-local:latest sh -c 'ffmpeg ... testsrc=... ok.mp4'
→ Killed, rc=137, arquivo de 48 bytes
```

`test_render_api.py` (15) e `test_publish_api.py` (19 failed / 10 passed) com DSN caem no mesmo
ponto (`PIL.UnidentifiedImageError`, fixture sem mídia porque o `ffmpeg` foi morto). Nenhum deles
importa `api/panel.py`; a falha é do ambiente local, não da fatia. Sem DSN esses arquivos fazem
skip, por isso não entram na contagem acima.

## Higiene

`python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (rc 0). Nada de segredo,
token ou DSN impresso neste relatório; o Postgres de teste é descartável (tmpfs) e a prova é
descartada junto com o container.

## Limitações

- A página responde em Python 3.12 (Docker); o host tem 3.11.9 e `api/preview.py` (de outra
  trilha, não tocado aqui) usa f-string com backslash — por isso `test_panel_page.py`/
  `test_panel_api.py` só rodam no container.
- Sem navegador real: layout do rail e foco foram validados por HTML/DOM, não por screenshot.