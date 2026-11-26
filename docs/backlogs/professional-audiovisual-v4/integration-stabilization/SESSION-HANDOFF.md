# SESSION-HANDOFF — V4 Integration & Stabilization Recovery (`REC-00`..`REC-04`)

**Atualizado:** 2026-11-26 (2ª sessão, OpenCode) — substitui o handoff anterior (pausa por cota de 5h do Google).
**Branch:** `develop` (ONLY — NUNCA modificar nem fazer merge em `main`)
**HEAD commitado em `develop`:** `5097b98861458321e636abf0dd036b3b3077e6a3`
**`main` observada:** `42700cb331165a68455173a91c463d4733292cfd` (intocada)
**Status:** `PAUSED_QUOTA_CHECKPOINT` — cota mensal do Copilot esgotada; chave do Google inválida.
**Custo externo:** `$0.00` | **Kill switch de publicação:** `STUDIO_PUBLICATION_ENABLED=0` (`BLOCKED`).

---

## 1. Por que parou

- `github-copilot/*` (Neon e Flash testados) → `You have exceeded your monthly quota`.
- `google/*` → `API key not valid. Please pass a valid API key.`
- Modelos Claude/GPT/Grok existem no Copilot, mas **não foram usados**: a campanha é Google-only e o operador só autorizou o Copilot para os Gemini. Só usar outro modelo com autorização explícita.

## 2. Modelos reais (desvios da política, registrados)

- `gemini-4-carbon` e `gemini-4-hydrogen` **não existem** no catálogo. Neon High substitui Carbon (reviewer); Neon High/Flash 3.8 substituem Hydrogen (executor).
- Uso real: `github-copilot/gemini-4-neon#high` e `github-copilot/gemini-3.8-flash#high` (operador autorizou o Copilot em 2026-11-26).
- Executor e reviewer **sempre em sessões separadas** (subagent novo para cada review). O reviewer nunca é a sessão que implementou.
- Flash 3.8 teve 2 REJECTED seguidos no REC-03.03 e foi escalado para Neon. Após 2 tentativas por modelo, escalar.
- Antes de despachar, confirme um modelo com um teste trivial (`Responda OK`); se falhar, registre `BLOCKED_REVIEW` e pare.

## 3. Trabalho concluído e verificado (commitado em `develop`)

| Tarefa | Commit | Nota independente | Rounds |
|---|---|---|---|
| `REC-00.01–02` | `031811f` | 9.51 / 9.54 | 1 |
| `REC-01.01–03` (R01–R03) | `d9fd1cd` | 9.50 | 2 |
| `REC-02.05` (R09) | `4ece073` | 9.50 | 2 |
| `REC-02.01–02` (R04–R05) | `ef367fc` | 9.440 / 9.425 | 2 |
| `REC-02.03–04` (R06–R07) | `3ca1f85` | 9.425 / 9.440 | 2 |
| `REC-03.01–02` (R08) | `7ded0f5` | **9.290 / 9.355** | 3 (R1 6.85/6.55 e R2 7.475/7.75 REJECTED) |
| `REC-03.03` (R10) | `4fa225b` | **9.44** | 2 (R1 3.95 REJECTED; executor escalado) |
| `REC-04.01` (R11, slice 60–90s) | `5097b98` | **9.345** (técnico; audiovisual `AWAITING_HUMAN_REVIEW`) | 1 |

Slice de `REC-04.01`: 67,36 s, 1920x1080 H.264/AAC, `-16,1 LUFS`, `-1,4 dBTP`, Piper real, PNG+MP4 importados, overlay+PiP, regeneração seletiva (4/4 narrações e 10/10 shots reusados, −42,5%), QA com 10 checks e 0 bloqueios.
- MP4 (gitignored): `storage/output/runs/rec04_slice_20261126_213537_4fa225b/rec04_01_vertical_slice.mp4`
- Segundo run (reviewer): `storage/output/runs/rec04_slice_20261126_215800_4fa225b/`
- Manifesto: `evidence/rec-04/rec-04-01/manifest.json`
- Reproduzir: `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH" ./scripts/run-rec04-slice.sh`

Última regressão canônica (no reviewer de `REC-04.01`): `4502 passed, 26 skipped, 0 failed`, exit 0. Host Node/painel: `101 passed`.

## 4. Working tree NÃO commitado e NÃO revisado (`REC-04.02`, parcial)

O executor foi interrompido pela cota no meio dos pré-requisitos. **Nada foi testado nem revisado.** Arquivos:
- `renderer/app/studio/application/render.py` e `render_compiler.py` (correções em andamento de P2-1 e PRE-1).
- `tests/conftest.py`, `tests/test_rec_04_vertical_slice.py`, `tests/test_render.py`, `tests/test_render_plan_compiler_v2.py`.
- `tests/rec04_helpers.py` (novo).
- `EXECUTION-STATE.md` e `EXECUTION-LOG.md` (checkpoint de cota).

**Primeira ação ao retomar:** `git status` e `git diff`; rodar os testes focados (`tests/test_render.py`, `tests/test_render_plan_compiler_v2.py`, `tests/test_rec_04_vertical_slice.py`, `tests/test_architecture.py`) para saber o que já funciona. Não assumir que o parcial está correto. Se estiver confuso, `git stash` do parcial é aceitável (não destrutivo) e reimplementar tests-first.

## 5. Fila restante (ordem exata)

### Passo 1 — `REC-04.02` (R11): documentário real 5–8 min pareado com V4-00
- **Executor:** Neon High ou Flash 3.8 (via Copilot, se a cota voltar) | **Reviewer independente:** Neon High, sessão nova.
- **Pré-requisitos, tests-first (achados do review de `REC-04.01`):**
  1. **P2-1:** o PiP à esquerda (`position_x=0.06, position_y=0.14`, `render.py` ~353–354) sobrepõe o selo "FATO" e o disclosure "Ilustração gerada por IA" (zona y≈96..245 em 1080p). Reposicionar ou validar, com teste de geometria. Preservar hash e cache de vídeos sem PiP.
  2. **PRE-1 (bug preexistente, anotar como tal):** cena de vídeo base com shot único renderiza legenda Pillow (`caption_overlay`) e ASS (`-vf subtitles`) duplicadas (`render_compiler.py` ~216–219; `render_plan_compiler.py` ~240–294). Corrigir de forma mínima, com uma única fonte de legenda, sem quebrar golden e hashes não afetados. Declarar se o hash de cache mudar.
  3. **P2-4:** registrar no manifesto a versão do pacote `piper-tts`, não o texto de `usage:`.
- **Entrega:** MP4 de 300–480 s medidos por `ffprobe` (≥ 25 cenas), pelas rotas HTTP do Studio e `ProductionCoordinator`/`PlanFfmpegRenderer`. Perfil econômico real (`$0.00`); balanced local só se viável, senão `BLOCKED`/`DEFERRED` justificado; premium fora de escopo.
- **Conteúdo e métricas:** mesmo roteiro, formato e hardware do baseline V4-00 (localizar com `grep V4-00` em `docs/backlogs/professional-audiovisual-v4`; rebaseline controlado documentado se necessário). Incluir edição com regeneração seletiva, QA real, check `V2-F7` de thumbnail, e métricas pareadas (`ffprobe`, LUFS/dBTP, duração, fps, drift, frozen ratio, CPU/RAM com ressalva de kernel, tempos por estágio, economia de regeneração).
- **Artefatos:** `tests/test_rec_04_documentary.py` (marcador próprio), `scripts/run-rec04-documentary.sh`, `evidence/rec-04/rec-04-02/manifest.json` e `evidence/rec-04/rec-04-02-documentary-evidence.md`. MP4 e frames só em `storage/output/runs/<run_id>/` (gitignored, **nunca commitar**).
- **Reviewer:** deve recalcular SHA-256, `ffprobe` e `ebur128` no MP4, inspecionar frames, rodar mutações numa cópia fora do repo e a suíte canônica completa.
- **Antes do commit:** reconciliar `EXECUTION-STATE.md`, `EXECUTION-LOG.md` e `MODEL-USAGE.md`.

### Passo 2 — `REC-04.03` (R12): regressão canônica completa no SHA limpo
- **Executor:** Neon High | **Reviewer:** Neon High (sessão separada).
- Árvore limpa após a última mudança funcional. Rodar `./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q`, salvar JUnit e log sanitizados, SHA, hash da imagem, nº de migrações, exit 0 e contagens reconciliadas. Rodar também Node/painel no host e o Playwright isolado na porta 8100 (`down -v` depois).
- Qualquer falha: corrigir e **re-rodar a suíte inteira** no novo SHA (nunca combinar retestes parciais).

### Passo 3 — `REC-04.04` (R13): release gate final
- **Executor:** Neon High | **Reviewer:** Neon High (sessão separada) + operador humano.
- Reconciliar `TRACEABILITY-MATRIX.md` (227 IDs V4, GAI-01..09, INT-01..07, R01..R13, REC-00..04) e escrever `FINAL-REPORT.md`.
- Formalizar os `DEFERRED` com risco e owner: multitrack 3+ faixas e `xfade` fora das rotas HTTP do Studio (provados no renderer em REC-02), módulos legados `render_engine`/`asset_registry`/`studio_workbench` (0 chamadores em produção), e os P2 abertos (ver §6).
- Emitir **`TECHNICAL GO / AWAITING HUMAN REVIEW`**. Nunca aprovar audiovisual sozinho, nunca fazer merge em `main`, nunca publicar. Entregar ao operador os caminhos e comandos para assistir ao MP4 de 60–90 s e ao de 5–8 min.

## 6. P2 abertos e bug preexistente (não bloqueantes)

- **`ai-generated:`** em `asset_registry.py:63-65,85-91` usa denylist de 6 tokens e aceita strings como `ai-generated:cc-by-nc-nd-4.0`. Endurecer depois.
- **`scene_repair`** é `None` no wiring padrão (`production.py:466-486`, `wiring.py:748-752`), o que é coerente com `$0.00`.
- **P2 do round 3 de `REC-03.01–02`** (índices, transação de trim em 2 etapas, `except Exception: continue` em `GetSceneTiming`, entre outros): ver `evidence/rec-03/rec-03-01-02-independent-review-neon-high-round3.md`.
- **P2 de `REC-04.01`:** testes unitários de hash para overlays em `test_render.py`, timestamp `1.20s` vs `1.40s` no teste do slice, e a evidência chamando legenda duplicada de "lower-third".
- **`PRE-1`** é bug preexistente (legenda duplicada); registrar como preexistente, não como regressão.

## 7. Ambiente e segurança

- **PATH do host (macOS), sempre:** `PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"` (Docker 29.1.3, Node v26.0.0, pytest e Playwright Chromium 1255 no pyenv 3.11.9).
- **Testes canônicos:** `./scripts/test-container.sh <args>` (checkout RO, Postgres 16 descartável em tmpfs com proof guard, FFmpeg 7.1.5, Piper `pt_BR-faber-medium`). A suíte completa leva ~13 min.
- **Host Node/painel:** `python3 -m pytest tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py tests/test_falha_producao.py tests/test_publicacao_acao.py tests/test_workflow_analytics.py tests/test_workflow_publish.py tests/test_workflow_trends.py`
- **Browser E2E isolado:** `docker-compose.e2e.yml` na porta 8100 com `E2E_PROJECT_NAME` distinto por execução. Nunca tocar 8000 ou 5678. Sempre `docker compose -p <proj> -f docker-compose.e2e.yml down -v` depois.
- **Proibido:** API paga (`$0.00`), publicação no YouTube, qualquer mudança ou merge em `main`, `git push` (bloqueado pelo ambiente), `--force`, reset destrutivo, review ou aprovação humana simulados, relaxar asserts, MP4 no Git (`storage/output/*` está no `.gitignore`).
- Reviewers repetidamente reprovaram por testes tautológicos, asserts relaxados e requisitos provados só por função pura. Exigir consumidor real (rota/coordenador), Postgres e FFmpeg reais, e mutação fora do repo.

## 8. Prompt para colar na nova sessão

```text
Retome a campanha V4 Recovery exclusivamente na branch develop a partir de:
docs/backlogs/professional-audiovisual-v4/integration-stabilization/SESSION-HANDOFF.md

Leia SESSION-HANDOFF.md, EXECUTION-STATE.md, PROMPT-MASTER.md, MODEL-ROUTING.md, QUALITY-RUBRIC.md e QUALITY-GATES.md antes de agir.

Estado: REC-00..REC-03 e REC-04.01 (técnico) VERIFIED e commitados (HEAD 5097b98). REC-04.02 tem working tree parcial NÃO revisado (conferir git diff e rodar testes focados antes de reaproveitar).

Antes de despachar qualquer modelo, teste a disponibilidade com um prompt trivial. Se a cota do Copilot ou a chave do Google ainda estiverem bloqueadas, registre BLOCKED_REVIEW e pare, sem usar modelos fora da política sem minha autorização.

Execute em sequência, com executor e reviewer em sessões separadas e nota mínima >= 9,0/10 em todas as dimensões:
1. REC-04.02: pré-requisitos (PiP vs selo FATO/disclosure; legenda duplicada PRE-1; versão do piper) e documentário real 5-8min pareado com V4-00, com review independente e commit atômico;
2. REC-04.03: regressão canônica completa no SHA limpo + Node + browser isolado, com review independente;
3. REC-04.04: TRACEABILITY-MATRIX reconciliada, FINAL-REPORT.md e review final independente.

Mantenha custo externo $0.00, publicação bloqueada, main intocada, sem merge e sem push. Ao concluir os gates técnicos, emita TECHNICAL GO / AWAITING HUMAN REVIEW e disponibilize os MP4s (60-90s e 5-8min) para minha homologação audiovisual.
```
