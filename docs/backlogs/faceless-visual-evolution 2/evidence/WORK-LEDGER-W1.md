# Ledger — Onda 1 / UX (22/11/2026, sessão 2)

**Plano:** `phases/INTEGRATION-PLAN.md` §4 (Onda 1). **Base:** `a2e6a39` (branch `main`). **Nada commitado** em lugar algum.
**Modo:** execução direta com Superpowers (sem runtime LangGraph neste repo).

## Worktrees desta onda (todos com a infra de teste não rastreada copiada; base = árvore de trabalho do checkout principal, já com a W0B)

| Worktree | Branch | Tarefa | Dono |
|---|---|---|---|
| `.worktrees/ve-w1-listas` | `ve/w1-listas` | W1.1 + W1.3 + W1.6 | subagente |
| `.worktrees/ve-w1-workspace` | `ve/w1-workspace` | W1.4 + W1.7 | subagente |
| checkout principal | `main` | W1.2 (shell/canal), W1.5 (Configurações/Biblioteca), fiação de rota da W1.4, portes e docs | eu |

## Interfaces compartilhadas (pre-flight)

- `api/routes.py` e `api/shell_v3_css.py` foram **reservados a mim** (subagentes proibidos de tocar): evitou conflito entre W1.2/W1.4/W1.5.
- `api/panel_channels.py` tinha **duas fontes de mudança** concorrentes: meu refactor (extração de `_channels_page_js`) e os campos do W1.6 (subagente). O merge foi manual e o JS foi verificado byte a byte após o merge.
- Colisão real de infra: a tag única da imagem de teste fez o script abortar no meio da onda → parametrizei `FACELESS_TEST_IMAGE`/`FACELESS_PYTEST_IMAGE` e passei a usá-las em todas as rodadas concorrentes.

## Progresso

- W1.1 — ✅ implementado + testes (subagente); portado. `panel_videos.py`; `test_videos_v3.py`.
- W1.2 — ✅ implementado + testes (eu). `shell_v3.py`, `shell_v3_css.py`, `panel.py`, `preview.py`, `panel_production.py`, `routes.py`; `test_active_channel.py`, `test_panel_page.py`.
- W1.3 — ✅ implementado + testes (subagente); portado. `panel_trends.py`; `test_trends_v3.py`, 2 reescritos em `test_panel_page.py`.
- W1.4 — ✅ implementado + testes (subagente); rota e CSS fiados por mim. `panel_video_workspace.py` (novo), `routes.py`, `shell_v3_css.py`; `test_video_workspace.py`, `test_panel_page.py`.
- W1.5 — ✅ implementado + testes (eu). `shell_v3.py`, `routes.py`, `panel_settings.py` (novo), `panel_styles.py`; `test_settings_sections.py` + rótulos/redirects em 12 arquivos.
- W1.6 — ✅ implementado + testes (subagente); portado. `panel_channels.py`; `test_channels_page.py`.
- W1.7 — ✅ implementado + testes (subagente, dentro da W1.4). Honestidade das fontes visível.

## Extras encontrados ao integrar (fora dos subagentes)

- `tests/test_settings_area.py` e `tests/test_video_style_api.py` fixavam o comportamento **antigo** de Configurações (6 seções, `estrategia`/`producao` como âncoras 302, "Estilos" como seção). Atualizados: as seções com página própria agora são verificadas como não-redirect.
- `panel_styles.py` deixou de ser "Configurações / Estilos" e virou a página **Biblioteca** (item de topo do protótipo), com corpo próprio (`shell_v3.render_library_page_body`, sem a nav de Configurações).

## Pendências de hora

- Suíte completa pós-W1: **verde** — `full5-w1.log`: 0 failed, 3094 passed, 6 skipped (356 s), `hash renderer/app=b4839e8bcce19e10`; os 6 skips = Node.js ausente. Números em `CONTINUITY.md` §4.
- Rodada completa com W4.0 portado (`/tmp/ve-main-full.log`) foi **invalidada pelo ambiente** (Postgres descartável desapareceu; `ffmpeg` morto por OOM); as 8 falhas passam isoladas.
- Nada commitado; nada empurrado; nenhuma branch trocada.
