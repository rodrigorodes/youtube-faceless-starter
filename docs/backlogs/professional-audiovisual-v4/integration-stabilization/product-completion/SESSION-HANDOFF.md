# SESSION-HANDOFF — V4 Product Completion (`PC-00`..`PC-09`)

**Created (UTC):** `2026-11-27T01:45Z` (`22:45` local)  
**Branch:** `develop` (ONLY — NEVER modify or merge into `main`)  
**Base HEAD:** `8484b72` (`docs(v4): plan product completion with strict 9-point gates and detailed model-routed prompts`, descendant of REC closure `2e8b153` & clean functional SHA `6a55f1f`)  
**Observed `main` SHA:** `42700cb331165a68455173a91c463d4733292cfd` (strictly untouched)  
**Reason for Clean Pause:** Observed Google quota was **`16%`** remaining at campaign start (safety reserve `15%` weekly / `10%` 5h window; resets at **`2026-11-27T03:47:25Z` / `00:47:25` local**). Starting `PC-00` (`Neon High` + `Carbon High`) with `16%` remaining would exhaust the pool mid-audit. Starting fresh at `100%` in a new session preserves full context and quota runway.

---

## 1. Current State
- **Tasks Completed in PC Campaign:** `0 / 27` (`PC-00.01`..`PC-09.02` all `PENDING`).
- **Uncommitted Initialization Docs Only:** `EXECUTION-STATE.md`, `EXECUTION-LOG.md`, `MODEL-USAGE.md`, `SESSION-HANDOFF.md` inside `docs/backlogs/professional-audiovisual-v4/integration-stabilization/product-completion/` (ZERO changes to `renderer/`, `tests/`, `scripts/`, or `contracts/`).
- **Verified Environment (macOS host + Docker):**
  - Always prefix host commands with `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"`.
  - Canonical container: `./scripts/test-container.sh <args>` (Docker `29.1.3`, Python `3.12.16`, FFmpeg `7.1.5`, `piper-tts==1.8.0` `pt_BR-faber-medium`, 49 Postgres migrations, `hash renderer/app=b677160103d832a3`).
  - Host Node `v26.0.0` + pyenv `pytest` + Playwright Chromium `1255` available; isolated browser E2E MUST use `docker-compose.e2e.yml` on port `8100` (`down -v` after), NEVER touching DEV ports `8000`/`5678`.
  - Gemini-only native `swarm` models confirmed: `gemini-3.8-flash-high`, `gemini-4-hydrogen-medium`, `gemini-4-carbon-high`, `gemini-4-neon-high` (set `monitor` to `gemini-3.8-flash-low`).

---

## 2. Copy-Paste Prompt to Start Cleanly After Quota Reset (`00:48` Local)

```text
/goal

Inicie a campanha V4 Product Completion (PC-00 até PC-09) exclusivamente na branch develop a partir do checkpoint de preflight em:
docs/backlogs/professional-audiovisual-v4/integration-stabilization/product-completion/SESSION-HANDOFF.md

Leia MASTER-PROMPT.md, README.md, BACKLOG.md, SCOPE-MATRIX.md, ACCEPTANCE.md, MODEL-ROUTING.md, EXECUTION-STATE.md e prompts/PC-00-audit.md antes de agir.

Use Gemini somente via swarm nativo com sessões separadas para executor e reviewer independente conforme MODEL-ROUTING.md (Carbon High orquestrador, Neon High para PC-00 e revisões críticas, Hydrogen Medium para implementações complexas, Flash 3.8 para UX/testes/tarefas simples; monitor em gemini-3.8-flash-low; encerrar workers concluídos para economizar cota).

Regras obrigatórias:
- Nota >= 9,0/10 em TODAS as dimensões aplicáveis e média ponderada sem arredondamento; zero P0/P1 obrigatório aberto;
- Commits atômicos na develop somente após review independente aprovado;
- Custo externo $0.00, publicação bloqueada (STUDIO_PUBLICATION_ENABLED=0), main intocada (sem merge/push), nunca tocar portas 8000/5678;
- Pausar com checkpoint seguro se a cota se aproximar da reserva (15% semanal / 10% janela 5h).

Comece pela PC-00 (sem alterar código de produto na auditoria) e avance automaticamente pelas dependências até PC-09, entregando os pilotos reais (60–90s e 5–8min) para minha homologação audiovisual.
```
