# Painel do Studio — Fase B (temas em alta) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seção "Temas em alta" no painel com filtro de 7/14/30 dias, fonte e data da consulta, vídeos por tema e criação de vídeo a partir do tema.

**Architecture:** Um workflow n8n agendado (inativo por padrão) consulta a fonte oficial e envia lotes a `POST /studio/trends` com o token do worker. O renderer valida, recusa itens sem fonte verificável e persiste em `studio.trend_topics`; `BuildPanel` (fase A) junta tendências e vídeos pela mesma `topic_key`.

**Tech Stack:** Python 3.12, FastAPI, psycopg, PostgreSQL, n8n (workflow JSON), YouTube Data API v3 (`search.list` + `videos.list`), pytest e Node para testes de workflow.

**Spec:** `docs/superpowers/specs/2026-11-20-studio-panel-design.md`

## Global Constraints
- Pré-requisito: Fase A concluída e verde. Migração nova: `0011_trends.sql` (a anterior é `0010_approval_render`); atualizar a lista esperada em `tests/test_db.py`.
- Tendência só vale com `source_name`, `source_url` (https, host em `STUDIO_TREND_SOURCES`), `observed_at` e `window_start/window_end`; sem isso o item é recusado e nunca aparece.
- Nenhum LLM gera tendências. Nenhuma credencial no renderer: a chave/OAuth de leitura fica no n8n, como no analytics (`workflows/04-analytics-daily.json`).
- Workflow entregue **inativo**; ativação e credencial são ação do usuário.
- Sem chamadas reais ao Google nos testes; a validação real é uma etapa explícita (B6) que só roda com a credencial do usuário.
- Cota: ≤ 10 consultas curadas por execução diária (≈ 1.000 unidades de 10.000/dia, compartilhadas com o upload a 1.600/upload).
- Sem `git push`/merge; commits locais só dos arquivos da tarefa.

## Review Focus
1. Item sem fonte, com URL `http://`, host fora da lista ou sem data: recusado inteiro, nada gravado (B2).
2. Reenvio do mesmo lote (retry do n8n): sem duplicidade, a consulta mais nova substitui a anterior (B2).
3. Tendência antiga (consulta mais velha que o filtro): marcada "desatualizada", nunca como "em alta agora" (B4).
4. Título/canal de vídeo vindo do YouTube com HTML ou texto enorme: escapado e truncado (B4).
5. Fonte fora do ar / cota esgotada (403 `quotaExceeded`): painel mostra "sem coleta recente" com a data da última consulta bem-sucedida, nunca lista vazia silenciosa (B3, B4).

---

### Task B1: Spike de fonte e cota (decisão documentada)

**Files:**
- Create: `docs/19-tendencias.md` (decisão, limites, termos de uso, como obter a credencial)

- [ ] **Step 1:** Ler a documentação oficial atual (Context7: YouTube Data API) e registrar em `docs/19-tendencias.md`: custo de `search.list` (100) e `videos.list` (1), parâmetros usados (`publishedAfter`, `order=viewCount`, `type=video`, `regionCode`, `relevanceLanguage=pt`), campos devolvidos, e que a cota é compartilhada com o upload.
- [ ] **Step 2:** Documentar a credencial pedida ao usuário: chave de API (dados públicos) criada no mesmo projeto Google, restrita à YouTube Data API v3, guardada como credencial **Query Auth** no n8n (nunca no `.env`/git). Documentar a alternativa (OAuth `youtube.readonly`).
- [ ] **Step 3 (opcional, só se o usuário pedir):** verificar se o site oficial do ADE tem feed/páginas de notícias estáveis dentro da allowlist; registrar o resultado (viável/inviável) sem implementar.
- [ ] **Step 4: Commit** — `git add docs/19-tendencias.md && git commit -m "docs(trends): source decision and quota"`

### Task B2: Domínio, migração e repositório de tendências

**Files:**
- Create: `renderer/app/studio/domain/trends.py`, `renderer/app/studio/adapters/postgres/trend_repo.py`, `renderer/app/studio/adapters/postgres/migrations/0011_trends.sql`
- Modify: `renderer/app/studio/application/ports.py` (`TrendRepository`), `tests/test_db.py` (lista de migrações e tabela)
- Test: `tests/test_trends_domain.py`, `tests/test_trend_repo.py`

**Interfaces:**
- Consumes: `topic_key` (A1).
- Produces:
  - `class TrendItem(BaseModel, extra="forbid")`: `topic: str (3–300)`, `source_name: str (1–80)`, `source_url: HttpUrl (https)`, `observed_at: datetime (com fuso, não futuro)`, `window_start/window_end: datetime`, `metric_name: str | None`, `metric_value: float | None (≥ 0, finito)`, `evidence: list[Evidence] (≤ 5)`; `Evidence`: `title (≤ 200)`, `url`, `channel (≤ 100)`, `views: int | None`, `published_at: datetime | None`.
  - `validate_trends(items: list[TrendItem], allowed_hosts: tuple[str, ...]) -> None` (levanta `TrendRefused` se **qualquer** item violar; janela ≤ 31 dias e `window_end ≥ window_start`).
  - Tabela `studio.trend_topics(id text pk, project_id → projects, topic, topic_key, source_name, source_url, observed_at, window_start, window_end, metric_name, metric_value, evidence jsonb, UNIQUE (project_id, topic_key, source_name, window_end))`.
  - `class TrendRepository(Protocol)`: `upsert(project_id: str, items: list[TrendItem]) -> int` (transacional: tudo ou nada); `list(project_id: str | None, since: datetime) -> list[TrendRecord]`; `last_collected_at(project_id: str | None) -> datetime | None`.

- [ ] **Step 1: Write the failing tests:** domínio — item sem `source_url`, `http://`, host fora da lista, `observed_at` sem fuso ou no futuro, `metric_value` NaN/negativo, janela invertida ou > 31 dias, mais de 5 evidências → `TrendRefused`; um item inválido num lote de 3 recusa o lote. Repositório (banco) — `upsert` do mesmo lote duas vezes mantém 1 linha por chave e atualiza `observed_at`/métrica; lote com item que viola constraint não grava nenhum; `list(since)` filtra por `window_end`; `last_collected_at` devolve o maior `observed_at`.
- [ ] **Step 2: Run** `export STUDIO_TEST_DSN=…yfs_security_test; ~/.yfs-test.sh tests/test_trends_domain.py tests/test_trend_repo.py tests/test_db.py` — Expected: FAIL.
- [ ] **Step 3: Implement** domínio (pydantic, sem I/O), migração (checks de tamanho, `metric_value >= 0`, `source_url ~ '^https://'`) e repositório (`INSERT … ON CONFLICT … DO UPDATE` numa transação; `check_id` no projeto).
- [ ] **Step 4: Run** os mesmos testes + `tests/test_architecture.py` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(trends): validated trend topics store"`

### Task B3: Endpoint de ingestão e configuração

**Files:**
- Modify: `renderer/app/studio/api/routes.py`, `renderer/app/studio/composition.py` (`Settings.trend_hosts` lida de `STUDIO_TREND_SOURCES`, padrão `("www.googleapis.com",)`; use case `IngestTrends`)
- Create: `renderer/app/studio/application/trends.py` (`IngestTrends.execute(project_id: str, items: list[TrendItem]) -> int`)
- Test: `tests/test_trends_api.py`

**Interfaces:** Produces `POST /studio/trends` body `{project_id, items: [TrendItem]}` (1–50 itens) → `202 {"stored": n}`. Aceita **só o worker** (Bearer, sem `Origin`); Basic do navegador → 403. 422 para lote recusado, 404 projeto inexistente, 503 sem banco.

- [ ] **Step 1: Write the failing tests:** worker válido → 202 e itens persistidos; Basic de navegador → 403; sem credencial → 401; item sem fonte → 422 e nada gravado; 51 itens → 422; projeto inexistente → 404; corpo > 256 KB → 413/422 (seguir o padrão atual de `/analytics/metrics`).
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_trends_api.py` — Expected: FAIL.
- [ ] **Step 3: Implement** a rota exigindo worker (reutilizar o mesmo mecanismo de `/analytics/metrics`) e o caso de uso `IngestTrends` chamando `validate_trends` antes do repositório.
- [ ] **Step 4: Run** `~/.yfs-test.sh tests/test_trends_api.py tests/test_studio_auth.py tests/test_composition.py` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(trends): worker-only ingestion endpoint"`

### Task B4: Tendências no painel

**Files:**
- Modify: `renderer/app/studio/application/panel.py` (`PanelView.trends: list[TrendItemView]`, `PanelView.trends_status`), `renderer/app/studio/api/panel.py`, `renderer/app/studio/api/routes.py` (injeta `TrendRepository` em `BuildPanel`)
- Test: `tests/test_panel.py`, `tests/test_panel_page.py`

**Interfaces:**
- Consumes: B2 (`TrendRepository.list/last_collected_at`), A3.
- Produces: `TrendItemView(topic, key, source_name, source_url, observed_at, stale: bool, metric_text: str | None, evidence: list[...], counts: dict[Stage,int], cost_text, create_action: bool)`; `trends_status ∈ {"ok","never_collected","stale"}`; `stale = observed_at < now − days`; ordenação por `metric_value` decrescente, itens sem métrica por último; `counts`/`cost_text` vêm dos vídeos com a mesma `topic_key`.

- [ ] **Step 1: Write the failing tests:** tendência com vídeos do mesmo `topic_key` mostra contagens e custo desses vídeos; sem vídeos → "Nenhum vídeo ainda"; `observed_at` mais velho que o filtro → `stale=True` e rótulo "desatualizado"; nunca coletado → mensagem "Ainda não há coleta de tendências", sem lista fabricada; HTML de título/canal escapado e título truncado a 200; link da fonte com `rel="noopener noreferrer"` e só `https`; filtro 14/30 dias troca a janela; botão "Criar vídeo" existe só com `create_action=True`.
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel.py tests/test_panel_page.py` — Expected: FAIL.
- [ ] **Step 3: Implement** a junção em memória por `topic_key` e a seção "Temas em alta" (fonte, data da consulta, métrica com unidade "visualizações na janela").
- [ ] **Step 4: Run** — Expected: PASS (testes da fase A continuam verdes).
- [ ] **Step 5: Commit** — `git commit -m "feat(panel): trending topics section"`

### Task B5: Criar vídeo a partir do tema

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:** Consumes `POST /studio/videos` (existente). O botão envia `topic` **verbatim** da tendência (≤ 300), `format=short`, `project_id` do projeto atual.

- [ ] **Step 1: Write the failing tests:** o botão carrega `data-topic` escapado e o JS usa `JSON.stringify`; tema > 300 caracteres não oferece o botão; após criar, o vídeo agrupa sob o mesmo tema (`topic_key` igual — teste de caso de uso).
- [ ] **Step 2: Run** `~/.yfs-test.sh tests/test_panel_page.py tests/test_panel.py` — Expected: FAIL.
- [ ] **Step 3: Implement** o botão e o handler reutilizando o `fetch` de A6.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(panel): create video from trending topic"`

### Task B6: Workflow n8n de coleta (inativo) e validação real

**Files:**
- Create: `workflows/05-trends-daily.json`, `tests/test_workflow_trends.py`
- Modify: `docs/19-tendencias.md` (passo a passo de ativação)

**Interfaces:** Workflow: gatilho agendado diário → lê as consultas curadas do projeto (lista no próprio workflow, ≤ 10, vazia por padrão) → `search.list` (credencial Query Auth `youtube_data_readonly`) → `videos.list` (estatísticas) → Code node monta `TrendItem` (`source_name="YouTube Data API"`, `source_url="https://www.googleapis.com/youtube/v3/search"`, `observed_at` = horário da consulta, janela = últimos N dias) → `POST /studio/trends` com credencial `studio_worker`. Erro `quotaExceeded`/5xx: falha visível na execução, sem enviar lote parcial vazio.

- [ ] **Step 1: Write the failing tests** (Node, como `tests/test_workflow_analytics.py`): JSON válido e `active=false`; lista de consultas vazia por padrão; nenhum segredo no JSON; o Code node produz itens que passam no esquema de `TrendItem` (incluindo `observed_at` com fuso); resposta sem itens não gera POST; `quotaExceeded` interrompe o fluxo; nenhuma URL fora de `googleapis.com` e `STUDIO_RENDERER_URL`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_workflow_trends.py` — Expected: FAIL.
- [ ] **Step 3: Implement** o workflow seguindo `workflows/04-analytics-daily.json` (mesmo padrão de credencial do worker, sem token no JSON).
- [ ] **Step 4: Run** `python3 -m pytest -q tests/test_workflow_*.py` — Expected: PASS.
- [ ] **Step 5: Validação real (só com a chave do usuário):** importar o workflow, definir 1–2 consultas, rodar **manualmente uma vez**, conferir no painel fonte, data e métrica contra a resposta crua da API e registrar o resultado e a cota gasta em `docs/19-tendencias.md`. Sem a credencial, registrar "não validado contra o Google" — não declarar a coleta pronta.
- [ ] **Step 6: Commit** — `git add workflows/05-trends-daily.json tests/test_workflow_trends.py docs/19-tendencias.md && git commit -m "feat(trends): inactive daily collection workflow"`

### Task B7: Verificação final e documentação

**Files:**
- Modify: `docs/18-painel.md`, `README.md`, `docs/17-studio-auth.md` (rota `/studio/trends`, só worker)

- [ ] **Step 1:** Suíte completa `export STUDIO_TEST_DSN=…yfs_security_test; ~/.yfs-test.sh tests` — Expected: tudo passa.
- [ ] **Step 2:** `python3 -m pytest -q tests/test_workflow_*.py`; `docker run --rm -v "$PWD":/w -w /w yfs-test python scripts/export_contracts.py --check`; `docker compose config --quiet`; `git diff --check` — Expected: ok.
- [ ] **Step 3:** Revisão independente (subagente `code-review`) focada nos 5 itens de Review Focus; corrigir achados Critical/Important.
- [ ] **Step 4: Commit** — `git commit -m "docs(trends): operator documentation"`

## Self-review
- Cobertura do spec: fonte verificável e data (B2–B4), filtro de período (B4), vídeos/custos por tema (B4 via fase A), criar vídeo (B5), coleta fora do renderer (B6), cota e credenciais (B1, B6).
- Nomes consistentes: `TrendItem`, `TrendRepository`, `IngestTrends`, `TrendItemView`, `topic_key` (A1) usados igualmente.
- Limitação assumida: "tema" é a consulta curada do projeto, não detecção automática; a métrica mede interesse no YouTube, não popularidade geral.
- Estimativa: ~1,5–2 h de agente, mais a validação real que depende da credencial do usuário.
