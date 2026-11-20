# Painel do Studio — Fase A (operacional) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela `/studio/panel` com vídeos por tema e etapa, custos honestos (vídeo/tema/mês vs teto) e detalhe de progresso, sem n8n e sem IDs.

**Architecture:** Domínio puro (`domain/panel.py`: tema, etapa, custo) ← caso de uso `BuildPanel` (porta `PanelRepository`) ← adaptador Postgres de leitura agregada ← rotas e HTML em `api/panel.py`. Só `composition.py` conhece o adaptador. Sem migração.

**Tech Stack:** Python 3.12, FastAPI, psycopg, PostgreSQL, pytest (`~/.yfs-test.sh`); HTML/CSS/JS sem dependências, como `api/preview.py`.

**Spec:** `docs/superpowers/specs/2026-11-20-studio-panel-design.md`

## Global Constraints
- Pré-requisito: a frente "aprovação ↔ render" (migração `0010_approval_render`) integrada e a suíte verde (`702+` testes). Não editar `api/preview.py`.
- Clean Architecture: `domain` ← `application` ← `adapters`/`api`; `tests/test_architecture.py` deve continuar verde.
- Rotas dentro do `router` existente (`/studio`, com `_browser_guard` + `_authenticate`); sem rota nova fora dele.
- HTML: todo texto escapado (`html.escape`), CSP com nonce, sem script/estilo externo, sem `eval`.
- Nunca exibir `upload_uri`, tokens, caminhos internos; `error` truncado a 300 caracteres e escapado.
- Custo desconhecido nunca vira `US$ 0,00` (regra 5 do spec). Teto mensal = `Settings.max_cost_month`.
- Sem `git push`, sem merge, sem upload/rede externa nos testes. Testes de banco só com `STUDIO_TEST_DSN` de teste (a fixture apaga o schema `studio`).
- Commits locais, adicionando só os arquivos da tarefa (nunca `git add -A`).

## Review Focus
1. Tema com HTML/`<script>`/aspas (vindo de modelo ou fonte): aparece como texto, nunca executa (testado em A5).
2. Vídeo sem nenhuma linha de uso: "sem registro de uso", não US$ 0,00 (A1, A3).
3. Linha de uso com `cost_usd = 0` de provedor/modelo pago: conta como desconhecida (A1).
4. Vídeo com render `FAILED` ou publicação `FAILED`: etapa "Falhou", sem `upload_uri` na resposta (A2, A5).
5. Banco indisponível/lento: 503 claro, sem página quebrada; lista vazia: estado vazio explicado (A4, A5).

---

### Task A1: Domínio do painel

**Files:**
- Create: `renderer/app/studio/domain/panel.py`
- Test: `tests/test_panel_domain.py`

**Interfaces:**
- Produces:
  - `class Stage(str, Enum)`: `PENDING, IN_PRODUCTION, AWAITING_APPROVAL, APPROVED, COMPLETED, FAILED, REJECTED`
  - `topic_key(topic: str) -> str`
  - `classify(status: VideoStatus, *, job: JobStatus | None, step_running: bool, publication: PublicationStatus | None) -> Stage`
  - `is_known_cost(provider: str, model: str, cost_usd: float) -> bool`
  - `@dataclass(frozen=True) class CostSummary: known_usd: float; calls: int; unknown_calls: int` e `cost_text(c: CostSummary) -> str`

- [ ] **Step 1: Write the failing tests** em `tests/test_panel_domain.py`:
  - `topic_key("  ADE   Lineup! ") == topic_key("ade lineup")`; `topic_key("Ação") == topic_key("AÇÃO")`; chaves de temas diferentes diferem.
  - Tabela de `classify` (parametrizada): `REJECTED→REJECTED`; `PUBLISHED→COMPLETED`; `publication=FAILED→FAILED` mesmo com status `APPROVED`; `status=FAILED→FAILED`; `job=RUNNING` ou `QUEUED→IN_PRODUCTION`; `step_running=True→IN_PRODUCTION`; `publication=UPLOADING→IN_PRODUCTION`; `job=FAILED` com status `ASSETS_READY→FAILED`; `RENDERED`/`AWAITING_APPROVAL→AWAITING_APPROVAL`; `APPROVED→APPROVED`; `IDEA`…`ASSETS_READY` sem job ativo → `PENDING`.
  - `is_known_cost`: `("opencode","x/y:free",0.0)` verdadeiro; `("placeholder","p",0.0)` verdadeiro; `("opencode","paid-model",0.0)` falso; `("opencode","paid-model",0.02)` verdadeiro.
  - `cost_text`: `CostSummary(0,0,0)→"sem registro de uso"`; `(0.0,2,0)→"US$ 0,00 (gratuito)"`; `(0.12,3,0)→"US$ 0,12"`; `(0.0,2,1)→"US$ 0,00 + 1 chamada sem custo informado"`; `(0.5,4,2)→"US$ 0,50 + 2 chamadas sem custo informado"`.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel_domain.py` — Expected: FAIL (módulo inexistente).
- [ ] **Step 3: Implement** `domain/panel.py` só com stdlib + `contracts` (sem I/O). `topic_key`: NFKC, `casefold`, `\s+`→um espaço, `strip` de espaços e pontuação nas pontas. Precedência de `classify` na ordem dos testes acima. `cost_text` formata com vírgula decimal.
- [ ] **Step 4: Run** o mesmo comando — Expected: PASS.
- [ ] **Step 5: Commit** — `git add renderer/app/studio/domain/panel.py tests/test_panel_domain.py && git commit -m "feat(panel): domain rules for topic, stage and cost"`

### Task A2: Leitura agregada no Postgres

**Files:**
- Create: `renderer/app/studio/adapters/postgres/panel_repo.py`
- Modify: `renderer/app/studio/application/ports.py` (acrescentar `PanelRepository`)
- Test: `tests/test_panel_repo.py` (usa a fixture de banco de `tests/conftest.py`)

**Interfaces:**
- Consumes: A1 (`CostSummary` é montado no caso de uso; o repositório devolve dados crus).
- Produces:
  - `@dataclass(frozen=True) class VideoRow: id, project_id, topic, format, status: VideoStatus, title, updated_at: datetime, job_status: JobStatus | None, step_running: bool, publication_status: PublicationStatus | None, error: str | None, cost_rows: list[tuple[str, str, float]]` (provider, model, cost_usd — um por linha de uso)
  - `class PanelRepository(Protocol)`: `projects() -> list[tuple[str, str]]`; `videos(since: datetime | None, project_id: str | None, limit: int) -> list[VideoRow]`; `video_detail(video_id: str) -> VideoDetail | None`; `month_usage() -> tuple[float, int, int]` com `(known_usd, calls, unknown_calls)` mantendo a mesma definição de mês de `spent_month`; `unattributed_usage() -> list[tuple[str, str, float]]` (linhas sem `video_id`, mês corrente).
  - `VideoDetail`: `video: VideoRow`, `steps: list[StepInfo(step, attempt, status, error_class, error_message(≤300), started_at, finished_at)]`, `usage: list[UsageInfo(step, provider, model, cost_usd, created_at)]`, `render_error: str | None`, `publication: PubInfo(status, attempt, error(≤300)) | None` — **sem `upload_uri`**.

- [ ] **Step 1: Write the failing tests** (banco): semeia 1 projeto e vídeos em estados variados (job `RUNNING`, `step_runs` `RUNNING`, publicação `FAILED`, sem uso, uso `:free`, uso pago com custo 0) e afirma: `videos()` devolve `job_status`/`step_running`/`publication_status` corretos; filtro `since` e `project_id`; `limit` respeitado; um vídeo com 3 jobs usa o **último**; `video_detail` não contém o texto de um `upload_uri` semeado na publicação; `month_usage()` equivale a `spent_month()` somando só o conhecido e conta `unknown_calls`.
- [ ] **Step 2: Run** `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test; ~/.yfs-test.sh tests/test_panel_repo.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `PostgresPanelRepository(_Base)` herdando de `editorial_repo._Base` e usando `_translated()` como os demais repositórios. Uma consulta por método (agregação com `LATERAL` para o último job e `array_agg`/`jsonb_agg` para o uso), parâmetros sempre ligados (`%s`), `check_id` nos IDs. Truncar erros em SQL (`left(…, 300)`).
- [ ] **Step 4: Run** — Expected: PASS; rodar também `tests/test_architecture.py`.
- [ ] **Step 5: Commit** — `git add renderer/app/studio/adapters/postgres/panel_repo.py renderer/app/studio/application/ports.py tests/test_panel_repo.py && git commit -m "feat(panel): aggregated read model on Postgres"`

### Task A3: Caso de uso `BuildPanel`

**Files:**
- Create: `renderer/app/studio/application/panel.py`
- Test: `tests/test_panel.py` (repositório falso em memória)

**Interfaces:**
- Consumes: A1, A2.
- Produces:
  - `class BuildPanel: __init__(self, repo: PanelRepository, monthly_cap_usd: float, clock: Callable[[], datetime])`
  - `execute(days: int = 7, project_id: str | None = None) -> PanelView` com `days ∈ {7, 14, 30}` (senão `InvalidInput`).
  - `PanelView`: `generated_at`, `days`, `projects: list[tuple[str,str]]`, `totals: dict[Stage, int]`, `month: MonthCost(text, known_usd, cap_usd, unknown_calls, percent | None)`, `topics: list[TopicGroup(key, label, counts: dict[Stage,int], cost_text, videos: list[VideoItem])]`, `VideoItem(id, topic, title, stage, cost_text, updated_at, actions: list[str])`; ações: `preview` para `AWAITING_APPROVAL`/`APPROVED`/`COMPLETED`, `progress` para `IN_PRODUCTION`/`FAILED`/`PENDING`.
  - `detail(video_id: str) -> VideoDetailView` (usa `video_detail`; `VideoNotFound` se não existir).

- [ ] **Step 1: Write the failing tests:** agrupa "ADE Lineup" e "ade  lineup!" no mesmo grupo (`label` = texto do vídeo mais recente); `totals` conta por etapa; custo do tema soma só vídeos do tema; vídeo sem uso → `"sem registro de uso"`; mês `unknown_calls > 0` nunca produz texto igual a `"US$ 0,00 (gratuito)"`; `percent` é `None` se `cap == 0`; `days=5` → `InvalidInput`; ações corretas por etapa; ordem dos temas por atividade mais recente.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `BuildPanel` com `classify`, `topic_key`, `cost_text`; agrupar em Python sobre `VideoRow` (limite de 500 vídeos; se atingir o limite, `PanelView.truncated = True` e a tela avisa).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git add renderer/app/studio/application/panel.py tests/test_panel.py && git commit -m "feat(panel): BuildPanel use case"`

### Task A4: Composição e API JSON

**Files:**
- Modify: `renderer/app/studio/composition.py` (instanciar `PostgresPanelRepository` e `BuildPanel(…, settings.max_cost_month, …)`; expor em `UseCases` como `panel`)
- Modify: `renderer/app/studio/api/routes.py`
- Test: `tests/test_panel_api.py`

**Interfaces:**
- Consumes: A3. Produces: `GET /studio/panel/data?days=7&project_id=` → JSON de `PanelView`; `GET /studio/panel/videos/{video_id}/data` → JSON de `VideoDetailView`. Erros: 422 (`days` inválido/ID inválido), 404 (`VideoNotFound`), 503 (sem banco). Modelos de resposta ficam em `api/` (não em `contracts/v1`: modelo interno de UI).

- [ ] **Step 1: Write the failing tests** (cliente de teste como em `tests/test_studio_api.py`): 401 sem Basic; 403 com `Host` inválido; 200 com Basic; `days=3` → 422; ID malformado → 422; vídeo inexistente → 404; resposta de detalhe **não contém** a string de um `upload_uri` semeado; banco indisponível → 503.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel_api.py` — Expected: FAIL.
- [ ] **Step 3: Implement** as duas rotas dentro do `router` existente, usando `run(...)` para o mapeamento de erros; `composition.py` constrói o caso de uso junto dos demais.
- [ ] **Step 4: Run** `~/.yfs-test.sh tests/test_panel_api.py tests/test_studio_api.py tests/test_composition.py tests/test_architecture.py` — Expected: PASS.
- [ ] **Step 5: Commit** — arquivos modificados + `tests/test_panel_api.py`; `git commit -m "feat(panel): panel data endpoints"`

### Task A5: Páginas HTML (lista e detalhe)

**Files:**
- Create: `renderer/app/studio/api/panel.py` (`render_panel(view: PanelView) -> tuple[str, dict[str, str]]`, `render_video(view: VideoDetailView) -> tuple[str, dict[str, str]]`, mesma assinatura (corpo, cabeçalhos CSP) de `render_preview`)
- Modify: `renderer/app/studio/api/routes.py` (`GET /studio/panel` e `GET /studio/panel/videos/{video_id}`, `response_class=HTMLResponse`)
- Test: `tests/test_panel_page.py`, estender `tests/test_studio_browser_security.py`

**Interfaces:** Consumes A3/A4. Produces páginas com: resumo (contadores por etapa + mês), filtro de período (links `?days=7|14|30`, sem JS), tabela de temas expansíveis (`<details>`), tabela de vídeos, botões "Ver prévia" (`/studio/videos/{id}/preview`) e "Ver progresso" (`/studio/panel/videos/{id}`); detalhe com linha do tempo de passos, erros, publicação (status/tentativa) e custo por chamada. CSS próprio e mínimo (não importar nem alterar `preview.py`); tema claro/escuro, foco visível, alvos ≥ 44 px, `<table>` com `<th scope>`.

- [ ] **Step 1: Write the failing tests:** tema `"<script>alert(1)</script>"` aparece como `&lt;script&gt;` e a página não contém `<script>alert`; cabeçalho CSP com nonce e sem `unsafe-inline` para script; `Cache-Control: no-store`; estado vazio ("Nenhum vídeo no período") ; `truncated=True` mostra aviso; texto de custo desconhecido aparece literalmente ("sem custo informado") e nunca `US$ 0,00 (gratuito)` quando há desconhecidos; detalhe de vídeo `FAILED` mostra erro truncado e escapado; nenhum HTML contém `upload_uri`.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel_page.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `api/panel.py` com `e = html.escape(..., quote=True)`; JS opcional apenas para auto-atualizar a página a cada 30 s quando houver vídeos `IN_PRODUCTION` (`location.reload()`, com nonce). Rotas devolvem `HTMLResponse(page, headers=headers)`.
- [ ] **Step 4: Run** `~/.yfs-test.sh tests/test_panel_page.py tests/test_studio_browser_security.py` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(panel): panel and video detail pages"`

### Task A6: Criar vídeo pelo painel

**Files:**
- Modify: `renderer/app/studio/api/panel.py` (formulário "Novo vídeo": projeto, tema 3–300 caracteres, formato `short|long`; JS com `fetch` para `POST /studio/videos`)
- Test: `tests/test_panel_page.py`, `tests/test_panel_api.py`

**Interfaces:** Consumes `POST /studio/videos` (existente: `{project_id, topic, format}` → 201). Sem projeto cadastrado, a tela oferece criar o projeto (`POST /studio/projects`) antes.

- [ ] **Step 1: Write the failing tests:** a página contém o formulário com `maxlength="300"` e o `project_id` das opções; `POST /studio/videos` com Basic **sem** `Origin` → 403 (regra existente) e com `Origin` correto → 201; página sem projetos mostra o passo de criar projeto.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel_page.py tests/test_panel_api.py` — Expected: FAIL.
- [ ] **Step 3: Implement** o formulário e o JS (mensagem de erro com `textContent`, nunca `innerHTML`); após 201, recarregar a lista.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(panel): create video from the panel"`

### Task A7: Documentação e verificação final

**Files:**
- Create: `docs/18-painel.md` (como abrir `http://localhost:8000/studio/panel` no macOS e no Windows, credenciais `STUDIO_BROWSER_*`, leitura das etapas e do custo, limitações)
- Modify: `README.md` (link), `docs/17-studio-auth.md` (rotas novas)

- [ ] **Step 1:** Suíte completa: `export STUDIO_TEST_DSN=…yfs_security_test; ~/.yfs-test.sh tests` — Expected: tudo passa (≥ 702 + novos).
- [ ] **Step 2:** `python3 -m pytest -q tests/test_workflow_*.py`, `docker run --rm -v "$PWD":/w -w /w yfs-test python scripts/export_contracts.py --check`, `docker compose config --quiet`, `git diff --check` — Expected: todos ok.
- [ ] **Step 3:** Verificação manual: reconstruir o renderer (`docker compose up -d --build renderer`), abrir a tela com dados semeados de teste e conferir cada etapa e cada texto de custo; remover os dados semeados.
- [ ] **Step 4: Commit** — `git add docs/18-painel.md README.md docs/17-studio-auth.md && git commit -m "docs(panel): operator guide"`

## Self-review
- Cobertura do spec: resumo/etapas (A1–A3), custo vídeo/tema/mês e teto (A1–A3), detalhe/progresso (A2, A5), criar vídeo (A6), prévia (links), segurança (A4–A5), docs (A7). Temas em alta ficam na fase B.
- Nomes consistentes: `Stage`, `CostSummary`, `VideoRow`, `PanelView`, `VideoDetailView`, `BuildPanel` usados da mesma forma em todas as tarefas.
- Estimativa: ~1,5–3 h de agente; sem custo de API paga.
