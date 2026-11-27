# Evidência de Regressão Final no SHA Limpo: `REC-04.03` (`R12` / Gate `G6`)

- **Data (UTC):** `2026-11-27T00:48Z`
- **Agente Executor:** `rec04-release` (`Gemini 4 Carbon High`)
- **Branch:** `develop`
- **Último Commit Funcional de Produção (`renderer/`):** `a1e3640b96330da2f981983117ccf1ab66735e2a` (`hash renderer/app = b677160103d832a3`, `49` migrações SQL)
- **SHA Limpo Final Verificado (`HEAD`):** `6a55f1f296d1d34bad64d2adcaad3bc0eafce011` (`git status -s` completamente vazio antes, durante e após todas as 4 campanhas; `alterações_em_renderer/tests=não`; `hash renderer/app: checkout=b677160103d832a3 == imagem=b677160103d832a3`; `migrações: checkout=49 == imagem=49`)
- **Branch Protegida `main`:** `42700cb331165a68455173a91c463d4733292cfd` (estritamente intocada)
- **Status:** `IMPLEMENTED` — Aguardando auditoria independente de `Gemini 4 Neon (High)` (`rec04-release-rev`; executor nunca se autoaprova como `VERIFIED`)
- **Governança, Orçamento & Isolamento:**
  - Custo externo em APIs pagas: **`$0.00` USD** (`STUDIO_PUBLICATION_ENABLED=0` → `BLOCKED`, `STUDIO_AUTO_RESEARCH=0`, zero credenciais externas)
  - Portas DEV (`8000` e `5678`): **100% intocadas**
  - Containers E2E (`faceless-e2e-rec0403final` na porta `8100`): **100% destruídos via `docker compose ... down -v`** (`0` containers remanescentes, `PORT_8100_CLOSED`)

---

## 1. Histórico Transparente: Parada Imediata em `a1e3640` → Alinhamento em `6a55f1f` → Reexecução Integral Limpa

Em cumprimento estrito à Regra Obrigatória #1 (`QUALITY-GATES.md:G6` / `prompts/REC-04-pilot-release.md`):
1. **Rodada Inicial no SHA Limpo `a1e3640` (`git status -s == ""`):**
   - **Campanha 1 (Container Canônico):** `4510 passed, 26 skipped, 0 failed` em `1104.27s` (`exit 0`).
   - **Campanha 2 (Host Node/Painel):** `101 passed, 0 skipped, 0 failed` em `8.56s` (`exit 0`).
   - **Campanha 3 (`tests/e2e_ux` + `tests/e2e_full` completos na porta `8100`) & Diagnóstico dos 3 Módulos Playwright Pulados no Container (`test_reference_browser.py` + `tests/ve08/`):** pela primeira vez em toda a campanha V4, todos os `27` testes E2E de navegador e os `20` testes funcionais Playwright de contrato foram executados ponta a ponta, revelando **3 descompassos pré-V4 de expectativa/seletor de teste** (**zero defeitos de produto; `renderer/` permaneceu 100% intocado**):
     - `tests/e2e_ux/test_e2e_journey_workspace.py:16-22,46`: esperava as 5 abas V3 pré-`9f300cf`, faltando `("Direção criativa", "/direcao")` já canônica em `panel_video_nav.VIDEO_AREAS` (`tests/test_panel_direction_tab.py:19-22`).
     - `tests/e2e_full/test_journey_piloto.py:107`: assertiva pré-V4 `render["qa_report"]["findings"] == []` rejeitava achados não-bloqueantes (`severity="warning"` de `render.frozen_frames` em imagens estáticas `placeholder:v4` de Short e `severity="info"` de `semantic-not-verified` introduzidos em V4-09 `b60a1f1`/`e05ece2`), embora `qa_report` tivesse **`0` achados bloqueantes** (`coverage.status == "verified"`, aprovação concluída normalmente em `test_journey_diretor.py`).
     - `tests/ve08/test_storyboard_functional.py:33,44,125`: seletor genérico `.scene textarea` colidia com o segundo `<textarea data-f="assisted-prompt">` (modo assistido `GAI-02`, dentro de `<details>` fechado) adicionado em `REC-03.01` (`7ded0f5`).
2. **Parada Imediata & Commit Atômico de Teste (`6a55f1f`):**
   - A execução de `REC-04.03` foi interrompida imediatamente sem iniciar `REC-04.04` e sem combinar retestes parciais.
   - Aplicados exclusivamente os 3 ajustes cirúrgicos em `tests/` (`3 files changed, 9 insertions(+), 5 deletions(-)`; `0` alterações em `renderer/`), preservando e fortalecendo as garantias fail-closed (`qa["coverage"]["status"] == "verified"`, `len(qa["checks_run"]) > 0`, `[f for f in qa["findings"] if f.get("severity") not in ("warning", "info")] == []`, navegação completa das 6 abas incluindo `/direcao`, e seletor exato `.scene textarea[data-a="text"]`), commitados em `develop` como **`6a55f1f296d1d34bad64d2adcaad3bc0eafce011`**.
3. **Reexecução Completa do Zero no Novo SHA Limpo `6a55f1f`:**
   - As **4 campanhas completas** foram reexecutadas integralmente do zero sobre `HEAD=6a55f1f296d1d34bad64d2adcaad3bc0eafce011` com `git status -s` vazio do início ao fim.

---

## 2. Tabela Consolidada das 4 Campanhas em `6a55f1f` (Separadas — Sem Soma de Campanhas Sobrepostas)

| # | Campanha | Ambiente Isolado | Escopo Executado | Coletados | Passaram | Pulados (`Skipped`) | Falhas / Erros | Tempo | Exit Code |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| **1** | **Suíte Canônica Completa (Container)** | Docker `faceless-renderer-pytest:test` (`Python 3.12.16`, `pytest 8.3.5`, `FFmpeg 7.1.5`, `piper-tts 1.8.0`) + `postgres:16-alpine` efêmero (`tmpfs` + proof guard) | `./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q --junitxml=/test-reports/rec04-03-canonical-final-junit.xml` | **4.536** | **4.510** | **26** | **0 / 0** | `1063.12s` (`17m43s`) | **`0`** |
| **2** | **Suíte Host Node.js / Painel / Workflows** | Host macOS (`Python 3.11.9`, `pytest 8.2.0`, `Node v26.0.0`) | `8` arquivos (`test_erro_js.py`, `test_storyboard_js.py`, `test_panel.py`, `test_falha_producao.py`, `test_publicacao_acao.py`, `test_workflow_analytics.py`, `test_workflow_publish.py`, `test_workflow_trends.py`) | **101** | **101** | **0** | **0 / 0** | `8.21s` | **`0`** |
| **3** | **Suíte Browser E2E Isolada (Playwright)** | `docker-compose.e2e.yml` (`faceless-e2e-rec0403final`, `127.0.0.1:8100`, Postgres+storage `tmpfs`, `down -v`) + `Chromium 1255` | `tests/e2e_ux` (`23` testes, incl. `test_rec_03_studio_browser.py` Desktop+Mobile) + `tests/e2e_full` (`4` jornadas completas) | **27** | **27** | **0** | **0 / 0** | `64.26s` (`1m04s`) | **`0`** |
| **4** | **Suíte Host Módulos Playwright de Contrato** | Host macOS (`PYTHONPATH=renderer`, `Chromium 1255`, harness local sem tocar portas) | `tests/test_reference_browser.py` (`4`), `tests/ve08/test_composition_functional.py` (`6`), `tests/ve08/test_storyboard_functional.py` (`10`) | **20** | **20** | **0** | **0 / 0** | `7.48s` | **`0`** |

> **Nota Metodológica (`QUALITY-GATES.md:G6`):** As contagens das 4 campanhas **não são somadas em um único número global** porque a Campanha 2 reexecuta no host os módulos mistos Python+Node (`101` testes totais, dos quais `78` testes Python já rodam na Campanha 1 e `23` testes Node são pulados na Campanha 1). Reportá-las separadamente garante 100% de transparência sem dupla contagem.

---

## 3. Reconciliação Aritmética Exata de Coleta, Evolução, Skips e Exclusões

### 3.1 Alinhamento Checkout × Imagem Docker (Campanha 1)
```text
HEAD=6a55f1f alterações_em_renderer/tests=não
hash renderer/app: checkout=b677160103d832a3 imagem=b677160103d832a3
migrações: checkout=49 imagem=49
4510 passed, 26 skipped, 1 warning in 1063.12s (0:17:43)
== pytest saiu com código 0
```
- **Equação exata do JUnit XML (`canonical-pytest-junit.xml`):** `tests="4536" = 4510 passed + 26 skipped + 0 failures + 0 errors`.
- **Reconciliação histórica de crescimento da suíte canônica:**
  - Baseline `REC-00` (`5800f46`): `4.416` coletados (`48` migrações).
  - Pós-`REC-01`..`REC-03.02` (`7ded0f5`): `4.517` coletados (`4.491 passed + 26 skipped`, `49` migrações).
  - Pós-`REC-03.03` (`4fa225b`): `4.527` coletados (`4.501 passed + 26 skipped`, `+10` testes em `test_rec_03_pipeline_integration.py`).
  - Pós-`REC-04.01` (`5097b98`): `4.528` coletados (`4.502 passed + 26 skipped`, `+1` slice real `test_rec_04_vertical_slice.py`).
  - Final `REC-04.02` / `REC-04.03` (`a1e3640` / `6a55f1f`): **`4.536` coletados (`4.510 passed + 26 skipped`)**, refletindo `+8` novos testes de `REC-04.02` (`test_rec_04_documentary.py`, geometria `P2-1` em `test_render.py`, `PRE-1` em `test_render_plan_compiler_v2.py`, e `'zero'` em `test_facts.py`).

### 3.2 Reconciliação 100% dos `26` Skips da Campanha 1 (Zero Skips Sem Cobertura!)

A imagem Docker de produção/teste (`python:3.12-slim`) propositalmente não embarca Node.js nem navegadores Chromium. Todos os **26 skips** da Campanha 1 são estruturais e foram **100% executados e aprovados** no host nas Campanhas 2 e 4:

| Categoria de Skip na Campanha 1 | Qtd Skips no Container | Arquivos / Linhas Exatas | Motivo Estrutural no Container | Onde Executou e Passou em `6a55f1f` |
|---|---:|---|---|---|
| **Testes JS / Node.js** | **23** | `test_erro_js.py` (`6`: `:29,:39,:46,:50,:56,:63`), `test_storyboard_js.py` (`6`: `:331,:338,:376,:416,:453,:515`), `test_publicacao_acao.py` (`4`: `:58,:64,:73,:87`), `test_workflow_analytics.py` (`2`: `:42,:53`), `test_workflow_trends.py` (`2`: `:39,:69`), `test_falha_producao.py` (`1`: `:47`), `test_panel.py` (`1`: `:522`), `test_workflow_publish.py` (`1`: `:70`) | `node` ausente na imagem slim `python:3.12-slim` | **Campanha 2 (Host Node):** `101 passed, 0 skipped` (`exit 0`) |
| **Módulos Playwright (`importorskip`)** | **3** *(skips de módulo = 20 testes)* | `tests/test_reference_browser.py:13` (`4` testes), `tests/ve08/test_composition_functional.py:8` (`6` testes), `tests/ve08/test_storyboard_functional.py:11` (`10` testes) | `pytest_playwright` ausente na imagem slim | **Campanha 4 (Host Playwright Modules):** `20 passed, 0 skipped` (`exit 0`) |
| **Total de Skips na Campanha 1** | **26** | `23 + 3 = 26` | `100%` justificados | **`100%` executados e verdes no host** |

### 3.3 Reconciliação 100% dos Caminhos Excluídos (`--ignore`) na Campanha 1

| Diretório Excluído na Campanha 1 | Motivo da Exclusão no Container | Onde Executou e Passou em `6a55f1f` |
|---|---|---|
| `--ignore=tests/e2e_ux` (`23` testes Chromium Desktop/Tablet/Mobile, incl. `test_rec_03_studio_browser.py`) | Exige stack HTTP viva isolada (`docker-compose.e2e.yml` porta `8100`) e Playwright Chromium | **Campanha 3 (Browser E2E Isolado):** `23/23 passed` (`exit 0`) |
| `--ignore=tests/e2e_full` (`4` jornadas ponta a ponta com Piper + FFmpeg reais na stack `8100`) | Exige `STUDIO_E2E_ISOLATED=1` contra `docker-compose.e2e.yml` (`tmpfs`) | **Campanha 3 (Browser E2E Isolado):** `4/4 passed` (`exit 0`) |

> **Nota sobre marcadores `rec04_slice` e `rec04_documentary`:** Nenhum teste foi desmarcado (`-m` não utilizado). Tanto `tests/test_rec_04_vertical_slice.py` quanto `tests/test_rec_04_documentary.py` rodaram integralmente **dentro** dos `4.510 passed` da Campanha 1!

---

## 4. Artefatos Sanitizados e Hashes SHA-256

Todos os logs e relatórios JUnit XML foram sanitizados (remoção de sequências ANSI/spinners e verificação estrita de ausência de DSNs, senhas efêmeras `POSTGRES_PASSWORD`/`e2e-*` ou tokens) e arquivados em `docs/backlogs/professional-audiovisual-v4/integration-stabilization/evidence/rec-04/rec-04-03/`:

| Artefato Sanitizado | Tamanho (Bytes) | JUnit Resumo | SHA-256 |
|---|---:|---|---|
| [canonical-pytest.log](rec-04-03/canonical-pytest.log) | `8,031` | `4510 passed, 26 skipped` (`exit 0`) | `c3a9ad06987f484d94b466d9dbc07cc5633685bd56c2b8b45105cebfad2aa432` |
| [canonical-pytest-junit.xml](rec-04-03/canonical-pytest-junit.xml) | `785,570` | `tests=4536, failures=0, errors=0, skipped=26, time=1062.913` | `c741b915ad90a8276502556f0f44bfabaab5ddb7d4c463acf9dfb40c9b7396d8` |
| [host-node.log](rec-04-03/host-node.log) | `1,934` | `101 passed, 0 skipped` (`exit 0`) | `f14aee61c96d85e3c67a17739b28fdf6ccbc9069e90a1a2e8715cc276dd5c147` |
| [host-node-junit.xml](rec-04-03/host-node-junit.xml) | `12,806` | `tests=101, failures=0, errors=0, skipped=0, time=8.211` | `04dc5c75cb272baf9a97ffe81e271983d736580b8d4ae873c0010072f153809a` |
| [browser-e2e.log](rec-04-03/browser-e2e.log) | `4,433` | `27 passed, 0 skipped` (`exit 0`, `down -v`) | `72780daf522449ce2e8e765e902c3f1e737536f8c78c7dc7c549529852e642be` |
| [browser-e2e-junit.xml](rec-04-03/browser-e2e-junit.xml) | `4,089` | `tests=27, failures=0, errors=0, skipped=0, time=64.264` | `744b0322a1a74a5d93e2489975ef5157c8ae6a99de491b78647fcf9dd9744138` |
| [host-playwright-modules.log](rec-04-03/host-playwright-modules.log) | `3,729` | `20 passed, 0 skipped` (`exit 0`) | `bc490e5d8a949f17394b5f19e9d682f48411d093d86105878d0c816830a337e7` |
| [host-playwright-modules-junit.xml](rec-04-03/host-playwright-modules-junit.xml) | `3,199` | `tests=20, failures=0, errors=0, skipped=0, time=7.481` | `9510481e1e09ec91d1c801ff669049dda84f9e93fafacccb5d30035313a3c3c1` |

---

## 5. Comandos Exatos para Reprodução Independente

```bash
export PATH="/Users/rodrigomendes/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:$PATH"

# 1. Suíte Canônica Completa no Container Descartável
./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q

# 2. Suíte Host Node.js / Painel / Workflows
python3 -m pytest \
  tests/test_erro_js.py tests/test_storyboard_js.py tests/test_panel.py \
  tests/test_falha_producao.py tests/test_publicacao_acao.py \
  tests/test_workflow_analytics.py tests/test_workflow_publish.py tests/test_workflow_trends.py -ra

# 3. Suíte Browser E2E Isolada (Porta 8100, tmpfs, Teardown Automático)
(
  set -euo pipefail
  export E2E_PORT=8100 E2E_PROJECT_NAME="faceless-e2e-verify-$$"
  trap 'docker compose -p "$E2E_PROJECT_NAME" -f docker-compose.e2e.yml down -v >/dev/null 2>&1 || true' EXIT
  docker compose -p "$E2E_PROJECT_NAME" -f docker-compose.e2e.yml up -d --build --wait
  STUDIO_E2E_ISOLATED=1 STUDIO_BASE_URL="http://127.0.0.1:8100" STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
  STUDIO_BROWSER_USER="e2e" STUDIO_BROWSER_PASSWORD="e2e-senha-descartavel" \
  STUDIO_E2E_USER="e2e" STUDIO_E2E_PASSWORD="e2e-senha-descartavel" STUDIO_PUBLICATION_ENABLED=0 \
    python3 -m pytest tests/e2e_ux tests/e2e_full -v -ra -p no:cacheprovider
)

# 4. Módulos Playwright de Contrato no Host
PYTHONPATH=renderer python3 -m pytest \
  tests/test_reference_browser.py \
  tests/ve08/test_composition_functional.py \
  tests/ve08/test_storyboard_functional.py -v -ra -p no:cacheprovider
```
