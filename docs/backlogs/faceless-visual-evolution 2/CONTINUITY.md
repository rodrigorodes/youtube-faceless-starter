# CONTINUITY — retomada em outra sessão

**Atualizado:** 22/11/2026 · **Repo:** `/Users/rodrigomendes/youtube-faceless-starter` · **HEAD:** `c3585dc` (commit local desta sessão; o anterior é `c90d806`) · **`git push` negado por permissão — nada saiu da máquina**. Working tree limpo.
**Idioma:** pt-BR. **Testes:** só pelo container (`scripts/test-container.sh`); o host macOS não é ambiente de teste.
**Leia primeiro:** `phases/INTEGRATION-PLAN.md` (plano, §9 = decisões do operador) e `evidence/REPO-VALIDATION.md` (matriz e riscos R1–R11).

## 0. Sessão atual (resumo no topo)

**Objetivo:** fechar o backlog "faceless visual evolution 2" (W0–W5 ✅) + S3/S4/S5, achados abertos e
**alinhamento de UX ao protótipo** (`prototype/index.html`), com a regra do PO: *onde o atual for
melhor, manter; o resto adequar ao protótipo seguindo os docs de análise*.

**Feito nesta sessão (commit local `c3585dc`, 58 arquivos):**
- Achados 1, 3, 4, 11 resolvidos; bug B1 (porta da intenção) e B2 (ids duplicados no diálogo de
  canal) corrigidos — `evidence/VERIFIED-FINDINGS.md`.
- **S3/S4/S5 portados**: compilador FFmpeg em `adapters/render_plan_compiler.py`; `composition.py` →
  pacote `composition/`; `api/panel.py` → `panel_shell` + `panel_operacional` + `panel_video` +
  `panel_script` + agregador de 75 linhas.
- **UX/navegação**: `NAV_OPERACAO` com **7 itens** (Configurações como 7º, `NAV` do protótipo);
  um único `<nav aria-label="Principal">`; caption "Operação" e `<nav aria-label="Configuração">`
  removidos. Chips de Tendências no padrão do protótipo; Biblioteca com h1/lead do protótipo;
  Configurações com h1/eyebrow/lead do protótipo e perfil econômico em cartões; **matriz de papéis**
  em Conta e equipe (de `ROLE_PERMISSIONS`).
- Docs: `analysis/NAVEGACAO-COMPARACAO.md`, `analysis/CONFIG-UX-AVALIACAO.md`,
  `evidence/VERIFIED-FINDINGS.md`.

**Validação real (container):** focado 393 passed (S4/S5 + nav + team); suíte completa e validação
no ar no §4 (nav de 7 itens, zero ids duplicados, chips do protótipo, matriz de papéis, criação de
canal com o nome correto).

**Bloqueios:** `git push` negado por permissão (não contornado); W5.3 (E2E Chrome) bloqueada por
ambiente (imagem sem Node/Chrome).

**Achados abertos:** casca legada viva em `/studio/oauth/callback` (registrado); `application/config.py`
com `ffmpeg` nos defaults; `MediaSearch` sem 2ª fonte; QA semântico sem verificador;
`test_secrets_hygiene` só falha com a árvore suja; import morto de `render_new_video` em `routes.py`;
Início sem a faixa de benefícios e Biblioteca sem as 3 abas (ambos dependem de expor dado real).

**Próxima ação:** decidir com o PO (a) a remoção do canal de teste criado na validação no ar
(`Prova fix B2 (validacao no ar)`) e (b) a limpeza dos 3 canais "Musica" do banco dev — **nenhuma
remoção sem autorização**. O commit local já está feito (`c3585dc`); o `git push` continua bloqueado
por permissão.

## 1. Objetivo
Integrar a proposta (revisão 3) **seguindo a UX atual e acrescentando ao core e à UX existentes**. Sem SPA, sem segundo shell/coordenador/renderer. Autorizado até agora: **W0 e W1**. W2 em diante (render, mídia, edição por cena, publicação) **não** foi autorizado.

## 2. Decisões do operador (valem)
- **D-A** Seguir W0 e W1: fechar baseline → corrigir orçamento e destino de publicação → navegação W1 → (depois) render → edição versionada.
- **D-B / P-04** "Reabrir para edição" só para aprovado **não publicado**: volta a `SCRIPTED`, nova revisão, invalida aprovação, render/QA dependentes e intenção de envio pendente; **bloqueia/coordena se houver upload em andamento**. Publicado → duplicar. Precisa de ADR (W4.2).
- **D-C / P-07** Ligar `STUDIO_BUDGET_GUARD` + `STUDIO_PRODUCTION_MODE=BUDGET_GUARDED` **só depois** de teste provando que o limite por canal bloqueia a chamada paga **antes** do efeito externo, **inclusive sob concorrência**. `docker compose config` não comprova nada.
- **D-D / P-08** Pasta ativa = `faceless-visual-evolution 2/` (a original está em `~/.Trash`, não restaurar). ISO fora do MVP de um operador confiável; **dentro** se houver acesso com papéis diferentes.
- Ajustes de plano do operador já aplicados no INTEGRATION-PLAN: W0 dividida em **W0A** (sem mudar comportamento) e **W0B** (muda comportamento, teste próprio); IDs de cena **não** usam `idx`; `asset_id` preservado só em cenas não afetadas; histórico guarda texto+ordem+mídia por revisão; fail-open de publicação antecipado para W0B.2; snapshot deve congelar a seleção efetiva de provider/modelo; DSNs de teste mapeados.

## 3. Estado atual do código (alterações não commitadas)
| Arquivo | Mudança | Verificação |
|---|---|---|
| `contracts/v1/renderplan.schema.json` | regenerado em container por `scripts/export_contracts.py`; só **+40 linhas** (`ConfigSnapshot`) | `test_contracts_snapshot` (rodar de novo na suíte) |
| `tests/test_port_contracts.py` | fixture `registered_providers` esvazia `_REGISTRY` antes do `Studio` e o **restaura** no fim (remove a dependência de ordem; fakes de `test_render_api`/`test_editorial_api` vazavam) | `test_render_api + test_editorial_api + test_port_contracts`: **43 passed** |
| `tests/test_publish_api.py` | asserção da prévia dividida por marcador; texto esperado `"QA aprovado"` → `"QA Aprovado"` (causa: commit `9188d0f` mudou o rótulo da prévia e o teste ficou velho) | `test_publish_api.py`: **14 passed** |
| `scripts/test-container.sh` | exporta também `STUDIO_BUDGET_DISPOSABLE_DSN` (mesmo Postgres efêmero) + comentário | validado na suíte completa (ver §4) |
| `phases/INTEGRATION-PLAN.md`, `START-HERE.md`, este arquivo | docs | — |
Não rastreados de antes: `docker-compose.preview.yml`, `faceless-visual-evolution 2/` (e `.zip`), `scripts/render_golden.py`, `scripts/test-container.sh`, `tests/golden/`, `tests/golden_render.py`, `tests/test_render_golden.py`.
Obs.: o red→green da correção de `test_port_contracts` veio do baseline anterior (falhava com a suíte inteira); um `git stash` para reproduzir o vermelho foi negado pelas permissões e **não foi contornado**.

### Onda 1 (W1, UX) — concluída nesta sessão (detalhe em `evidence/ve-w1-closure.md`)

| Área | Arquivos | Estado |
|---|---|---|
| W1.1 Aprovado ≠ Publicado | `api/panel_videos.py` | ✅ |
| W1.2 Canal dono do vídeo na casca | `api/shell_v3.py`, `api/shell_v3_css.py`, `api/panel.py`, `api/preview.py`, `api/panel_production.py`, `api/routes.py` | ✅ |
| W1.3 Criar vídeo preserva canal | `api/panel_trends.py` | ✅ |
| W1.4 8 áreas do vídeo como rotas | **novo** `api/panel_video_workspace.py`, `api/routes.py`, `api/shell_v3_css.py` | ✅ |
| W1.5 Configurações (7) + Biblioteca | `api/shell_v3.py`, `api/routes.py`, **novo** `api/panel_settings.py`, `api/panel_styles.py` | ✅ |
| W1.6 narrativa/duração/CTA do canal | `api/panel_channels.py` | ✅ |
| W1.7 Fontes honestas | `api/panel_video_workspace.py` | ✅ |
| Infra de teste | `scripts/test-container.sh` agora honra `FACELESS_TEST_IMAGE`/`FACELESS_PYTEST_IMAGE` (worktrees paralelos não colidem na tag) | ✅ |
| Contrato de UX | `tests/test_ux_contract.py` (`MOCKUP_ONLY_TEXT` com os temas de demonstração do protótipo novo) | ✅ |

Worktrees da onda: `.worktrees/ve-w1-listas` (`ve/w1-listas`), `.worktrees/ve-w1-workspace` (`ve/w1-workspace`) — nada commitado; arquivos portados para o checkout principal. Rótulos de nav/seções deixaram de ser os antigos em 10 arquivos de teste (atualizados por serem expectativas velhas, não por enfraquecimento).

### Saneamento de arquitetura e fatias 3 (em curso nesta sessão)

| Frente | Onde | Estado |
|---|---|---|
| W4.0 IDs de cena estáveis | portado do worktree `ve-w4-0-scene-ids` | **portado e verde** (36 passed) — [evidence/ve-w4-0-closure.md](evidence/ve-w4-0-closure.md) |
| W3.1 porta `MediaSearch` + Pexels | portado do worktree `ve-w3-media` | **portado e verde** (115 passed) — [evidence/ve-w3-1-closure.md](evidence/ve-w3-1-closure.md) |
| S1/S2/S7 saneamento | portado do worktree `ve-arch-saneamento` | **portado e verde** (61 passed) — [evidence/ve-s1-s2-s7-closure.md](evidence/ve-s1-s2-s7-closure.md) |
| S8 congelar seleção de provider | portado do worktree `ve-s8-freeze` | **portado e verde** (150 passed) — [evidence/ve-s8-closure.md](evidence/ve-s8-closure.md) |
| W4.3 pré-escuta/duração real | checkout principal | **implementado e verde** (5 passed) — [evidence/ve-w4-3-closure.md](evidence/ve-w4-3-closure.md) |
| W5.2 retry/reconciliação | portado de `ve-w5-2-publish-reconcile` | **portado e verde** (136 passed, 1 skipped) — [evidence/ve-w5-2-closure.md](evidence/ve-w5-2-closure.md) |
| W2.3 aba Composição em leitura | portado de `ve-w2-3-composition` | **portado e verde** (72 passed) — [evidence/ve-w2-3-closure.md](evidence/ve-w2-3-closure.md) |
| W5.1 formulário de publicação + invalidação | portado de `ve-w5-1-publication` | **portado e verde** (126 passed) — [evidence/ve-w5-1-closure.md](evidence/ve-w5-1-closure.md) |
| W2.2 compositor FFmpeg do overlay | portado de `ve-w2-2-compositor` | **portado e verde** (236 passed agregado) — [evidence/ve-w2-2-closure.md](evidence/ve-w2-2-closure.md) |
| W3.2 presets/legenda/motion + `Shot.transition` | portado de `ve-w3-2-presets` | **portado e verde** — [evidence/ve-w3-2-closure.md](evidence/ve-w3-2-closure.md) |
| W3.3 QA técnico/semântico + S6 | portado de `ve-w3-3-qa` | **portado e verde** — [evidence/ve-w3-3-closure.md](evidence/ve-w3-3-closure.md) |
| W4.4 troca de mídia por cena | portado de `ve-w4-4-media` | **portado e verde** (161 passed) — [evidence/ve-w4-4-closure.md](evidence/ve-w4-4-closure.md) |
| W4.5 histórico recuperável | portado de `ve-w4-5-history` | **portado e verde** (64 passed) — [evidence/ve-w4-5-closure.md](evidence/ve-w4-5-closure.md) |
| W4.1 edição de cena com CAS | portado do worktree `ve-w4-1-edit` | **portado e verde** (66 passed) — [evidence/ve-w4-1-closure.md](evidence/ve-w4-1-closure.md) |
| W4.2 reabrir aprovado (ADR-002) | portado do worktree `ve-w4-2-reopen` | **portado e verde** (36 passed) — [evidence/ve-w4-2-closure.md](evidence/ve-w4-2-closure.md) |
| S6 portas `SemanticChecker`/`TenantContext` | — | adiado; `MediaSearch` já entrou com W3.1 |

## 4. Suíte completa — resultado
- **W0A baseline** (`ve00/full2.log`): 5 failed, 2888 passed, 158 skipped (351 s) — classificados em `evidence/ve-00-closure.md`.
- **W0A pós-correções** (`full1.log`): **0 failed, 3045 passed, 6 skipped** (399 s); `hash renderer/app=263674812e6c7007`; os 6 skips = Node.js ausente na imagem. Ver `evidence/ve-00-closure.md`.
- **W1 (UX) pós-integração** (`full5-w1.log`): **0 failed, 3094 passed, 6 skipped** (356 s); `hash renderer/app=b4839e8bcce19e10`; os 6 skips = Node.js ausente na imagem. Uma regressão própria (vocabulário "projeto" no rótulo da voz, da W0B.4) foi encontrada por `test_channel_vocabulary` e corrigida antes desta rodada; a rodada anterior (`full4-w1.log`) tinha 1 failed/3093 passed e serviu de RED.
- Rodadas focadas (todas verdes): 355 passed + 1 skipped (telas/painel/contrato), 219 passed + 1 skipped (rótulos/seções/Biblioteca) e 126 passed (vocabulário/seções/painel de configurações).
- **W4.0 portado para o checkout principal** (`editorial_repo.py`, migração `0042`, testes, docs gerados): `tests/test_editorial_repo.py tests/test_longform_repo.py tests/test_db.py` → **36 passed** (12 s), `hash renderer/app=43489eedf465e75f`, `migrações=37`. Detalhe em [evidence/ve-w4-0-closure.md](evidence/ve-w4-0-closure.md).
- **Rodada completa no checkout principal com W4.0 (`/tmp/ve-main-full.log`): inválida por ambiente** — 8 failed, 3057 passed, 6 skipped, **68 errors** em 1092 s. Os 68 errors são `psycopg.OperationalError [Errno 2] Name or service not known` (o Postgres descartável `faceless-pg-...` desapareceu no meio da rodada) e as 8 falhas são `ffmpeg` morto por `-9` (OOM) e 503 por banco ausente. **Prova de que são ambientais:** as 8 falhas passam isoladas (`18 passed`) e a suíte já era verde em `full5-w1.log`. Precisa de nova rodada limpa quando não houver subagentes concorrentes.
- **Rodada completa no checkout principal com W4.1 portado (`/tmp/w41-full-main2.log`): 2 failed, 3186 passed, 6 skipped** (388 s), `hash renderer/app=bbe4cd8b8b8ff890`, `migrações=39`. As 2 falhas são `test_port_contracts.py::test_every_registered_provider_satisfies_its_port` e `::test_catalog_and_registry_have_no_drift` — **pré-existentes por vazamento de registro entre testes** (`register(...)` em nível de módulo em `test_editorial_api.py`/`test_render_api.py`): o arquivo isolado dá **8 passed**. O S8 já confirmou as mesmas 2 falhas no HEAD `a2e6a39` sem as mudanças. Os 6 skips = Node.js ausente. Detalhe em [evidence/ve-w4-1-closure.md](evidence/ve-w4-1-closure.md).
- **Rodada completa no checkout principal após portar W2.2/W2.3/W3.2/W3.3/W4.3/W4.4/W4.5/W5.1/W5.2 (sessão 4): 2 failed, 3307 passed, 6 skipped** (451 s), `hash renderer/app=eac47af427ae6911`, `migrações=41`. As 2 falhas continuam sendo o **mesmo vazamento pré-existente de `_REGISTRY`** (`test_editorial_api` → `test_port_contracts`): reproduzido rodando só `test_editorial_api.py tests/test_port_contracts.py` → **2 failed, 29 passed**; e `test_schema_docs.py tests/test_port_contracts.py` → **15 passed**. Os 6 skips = Node.js ausente.
- **Rodada completa desta sessão (sessão 5), após S3/S4/S5 + UX/navegação: 3 failed, 3316 passed, 6 skipped** (434 s), `hash renderer/app=b8ab3099d5a1c228`, `migrações=41`. Nenhuma falha é regressão:
  - `test_port_contracts::test_catalog_and_registry_have_no_drift` — vazamento de `_REGISTRY` por `register("voice","tone-narr",...)` em nível de módulo em `test_scene_narration.py` (**achado 11b**). **Corrigido** (fixture autouse com `registered_providers`).
  - `test_secrets_hygiene` ×2 — artefato do trabalho não commitado: `package-starter.sh` faz `stat()` no caminho de cada arquivo do **índice**, e `composition.py` estava deletado no disco mas ainda no índice. **Resolvido** com `git add -A` (a deleção entrou no índice).
  - Verificação focada dos 3: `test_secrets_hygiene + test_port_contracts + test_scene_narration + test_editorial_api + test_render_api + test_tts_calibration` → **89 passed**.
- **Rodada completa final (`full2`, após as 2 correções): 0 failed, 3319 passed, 6 skipped** (446 s), `hash renderer/app=b8ab3099d5a1c228`, `migrações=41`. Commit local `c3585dc`; working tree limpo. Os 6 skips = Node.js ausente na imagem.
- **Validação no ar** (imagem `renderer` reconstruída, app em `http://localhost:8000`, `/health` 200):
  - Nav de **7 itens** sem caption "Operação" em `/studio/panel`, `/studio/canais`, `/studio/panel/tendencias`, `/studio/configuracoes/canais`, `/studio/panel/equipe`.
  - **Zero ids duplicados** em `/studio/canais`, `/studio/configuracoes/estrategia` e `/studio/configuracoes/producao`; o diálogo do shell usa `dlg-canal-*` e `canal-nome` aparece **1×** (o campo do perfil).
  - Chips de Tendências = `["Todas", "Flat Iron"]` (pilar), **sem contagem** e sem "Em Alta <região>"; `?filtro=regiao:BR|US|todas` seguem respondendo **200**.
  - Configurações: eyebrow `CONFIGURAÇÕES`, h1 "Seu estúdio, do seu jeito", lead do protótipo e perfil econômico em `fieldset.perfis-escolha`.
  - Conta e equipe: `table.papeis-matriz` com as colunas Papel / Editar·gerar / Aprovar / Publicar.
  - **Bug B2 corrigido end-to-end**: `POST /studio/projects` com nome distinto gravou `Prova fix B2 (validacao no ar)` / nicho `verificacao` (antes gravava "Musica" e `não informado`).


## 5. Próximas ações (ordem)
- **W0A/W0B/W1 estão implementadas e verdes** (detalhe em `evidence/ve-00-closure.md`, `evidence/ve-w0b-closure.md`, `evidence/ve-w1-closure.md` e nos ledgers `evidence/WORK-LEDGER-W0B.md` / `evidence/WORK-LEDGER-W1.md`).
- **W2+ autorizada** pelo operador na sessão 3 ("seguir até a última atividade"). **Implementadas e portadas nesta sessão (sessão 4):** W2.2 (compositor overlay), W2.3 (aba Composição em leitura), W3.2 (presets/`Shot.transition`), W3.3 (QA técnico/semântico + S6), W4.3 (pré-escuta/duração), W4.4 (troca de mídia por cena), W4.5 (histórico recuperável), W5.1 (formulário de publicação + invalidação) e W5.2 (retry/reconciliação). Todas com fechamento em `evidence/ve-*-closure.md`. Suíte completa: **2 failed (pré-existentes), 3307 passed, 6 skipped**.
- **Falta (não implementado nesta sessão):** W5.3 (bloqueada por ambiente — sem Node/Chrome) e a trilha ISO (ISO-01/02, fora do MVP solo).
- **Ação imediata:** nenhuma portagem pendente. A suíte completa já rodou sem concorrência (§4); as 2 falhas restantes são pré-existentes de isolamento de teste e estão registradas.
- Achados abertos: `/publications/claim` fora do gate de identidade; recusa de orçamento sem dizer qual teto estourou; Compose não encaminha `STUDIO_PROVIDER_PRODUCTION`/`STUDIO_SECRETS_ROOT`; `application/config.py` mantém nomes de fornecedor nos defaults (resíduo de S2, registrado); risco de ordem de locks em `reopen` vs `mark_uploaded` (W4.2); vazamento de `_REGISTRY` entre testes (falha de isolamento pré-existente em `test_port_contracts`).
- **Refatorações S3/S4/S5 (sem mudança de comportamento) — FEITAS nesta sessão:** S3 (compilador
  FFmpeg em `adapters/render_plan_compiler.py`), S4 (`composition.py` → pacote `composition/`) e S5
  (`api/panel.py` → `panel_shell`/`panel_operacional`/`panel_video`/`panel_script` + agregador).
  Detalhe e verificação em `evidence/VERIFIED-FINDINGS.md` ("Refatorações S3/S4/S5"). S6 entrou com W3.3.
- **Bloqueado por ambiente:** W5.3 (E2E Chrome headless 390/768/1280) — a imagem não tem Node/Chrome; só dá para cobrir o que é server-rendered com `TestClient` até o ambiente ganhar browser. Registrado, não contornado.

## 6. Backlog de achados fora de escopo (não corrigir agora)
- `/health` devolve `ffmpeg: True` fixo (`main.py:34-36`).
- Caminho vigente de publicação n8n × servidor sem confirmação (`preview.py:41` × `routes.py:1656`).
- Reuso de cache entre versões de roteiro provavelmente falha por `scene_id` instável (hipótese; W4.0).
- `EditScriptScene` sem rota; `set_video_style_patch` sem rota (P-05).
- `strategy`, `audio`, `thumbnail` do perfil persistidos e não consumidos; `transition` só declarada.
- Voz tem 1 provider (`piper`) e render tem 1 (`ffmpeg`); stock só Pexels.

## 7. Comandos úteis
```bash
cd /Users/rodrigomendes/youtube-faceless-starter
scripts/test-container.sh tests/test_x.py -q          # alvo
scripts/test-container.sh tests -q -rfEs               # suíte completa (~10 min agora)
docker build -q -t faceless-renderer:test renderer && docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD:/w" -w /w --entrypoint python faceless-renderer:test scripts/export_contracts.py   # regenerar contratos
```
macOS: `sed -i` exige `''`; não há `timeout`. Chrome headless não reduz a janela abaixo de 500 px (usar iframe para 390).

## 8. Estado do ambiente e limites
- Aplicação parada (compose parado); banco do Studio foi zerado antes e recriado (48 tabelas), `public` do n8n preservado. Containers de teste antigos (`pg-f05-ui`, `faceless-f00-pg`, `integ-pg*`, `yfs-p06-p07-isolated`) não foram tocados. `.env` tem segredos: nunca imprimir.
- A autorização histórica de limpeza do banco **não** vale para ações futuras.
- Sem commit, sem push, sem alterar dados/recursos externos sem autorização.
