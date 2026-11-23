# Radar de Tendências com Inspiração, Sinais Reais e Estratégia (Variação A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar na tela de Tendências do Faceless Studio a Variação A com cartões visuais (miniaturas, duração real, sinais de velocidade e excesso vs. nicho), score de prioridade explicável (5 parcelas ponderadas e diagnóstico de risco/repetição), ordenação/filtros server-side, diálogo modal de transparência ("Como calculamos") e pasta permanente de ideias guardadas ("☆ Guardar").

**Architecture:** Adicionar `contentDetails` à chamada existente `videos.list` da YouTube Data API v3 para obter duração sem custo adicional de cota. Implementar um módulo de domínio puro (`domain/trend_priority.py`) para calcular as 5 parcelas de priorização, classificação perene e detecção de riscos. Persistir ideias guardadas permanentemente na tabela `studio.saved_trends` associada ao canal (`project_id`). Atualizar a camada de visualização (`panel.py`) e a tela HTML (`panel_trends.py`) para renderizar os cartões da Variação A com ordenação estável e modal de transparência.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL / SQLite (testes), Pydantic v2, pytest, HTML5/CSS nativo V3 (sem frameworks de terceiros).

**Spec:** `/Users/rodrigomendes/youtube-faceless-starter/docs/superpowers/specs/2026-11-23-trends-radar-cards-inspiration-design.md`

## Global Constraints

- Tema visual 100% dark mode nativo V3 (`shell_v3_css.py`), tokens `--bg`, `--panel`, `--line`, `--accent` (#8f6ef7), `--text`, `--muted` e fonte Inter.
- Zero custo extra de cota da YouTube API: reaproveitar a chamada `videos.list` incluindo `contentDetails` (0 unidades extras).
- Zero templates sintéticos ou roteiros gerados por LLM nesta fase: apenas vídeos reais comprováveis da API do YouTube.
- Zero dependência externa não-oficial (sem scrapers de Google Trends e sem adivinhação de CPM).
- Zero XSS e zero inline script sem nonce: todo texto dinâmico escapado com `html.escape` e scripts com `nonce="{nonce}"`.
- Persistência permanente de ideias favoritadas por canal no banco local (`studio.saved_trends`).

## Review Focus

1. **Duração ISO 8601 malformada ou ausente:** Formatos como `PT0S`, lives gravadas com dias de duração ou campo ausente devem cair graciosamente para string vazia sem lançar exceção.
2. **Divisão por zero em velocidade e excesso:** Vídeos recém-publicados (menos de 1 minuto) ou lotes com mediana de visualizações zero devem usar limitador `max(1.0, horas)` e evitar `ZeroDivisionError`.
3. **Ideia guardada fora da janela de 7 dias:** Quando o filtro `Guardados` estiver ativo, o repositório deve retornar os itens da tabela `saved_trends` mesmo que os registros originais tenham expirado da janela de coleta.
4. **Resiliência a lote vazio ou unitário:** Em categorias com apenas 1 vídeo ou nenhuma tendência, o score de prioridade e os percentis não devem quebrar e devem apresentar valores neutros equilibrados.
5. **Alternância idempotente do botão Guardar:** Clicar repetidamente no botão "☆ Guardar" ou desfavoritar não deve criar duplicatas nem falhar caso o item já tenha sido removido.

---

### Task 1: Parser de Duração ISO 8601 e Enriquecimento do Adapter da YouTube API

**Files:**
- Modify: `renderer/app/studio/adapters/youtube_trends.py:1-160`
- Test: `tests/test_youtube_popular_trends.py`

**Interfaces:**
- Produces: `parse_iso8601_duration(duration_str: str | None) -> tuple[str, int]` (ex.: `"PT11M40S"` $\to$ `("11:40", 700)`).
- Produces: Campo `duration` (string formatada) e `duration_s` (int) dentro dos dicionários de `evidence` produzidos por `fetch_popular_trends` e `fetch_search_trends`.

- [ ] **Step 1: Escrever os testes de falha para o parser de duração ISO 8601**

```python
# Em tests/test_youtube_popular_trends.py
from app.studio.adapters.youtube_trends import parse_iso8601_duration


def test_parse_iso8601_duration_standard():
    text, sec = parse_iso8601_duration("PT11M40S")
    assert text == "11:40"
    assert sec == 700


def test_parse_iso8601_duration_with_hours():
    text, sec = parse_iso8601_duration("PT1H2M10S")
    assert text == "01:02:10"
    assert sec == 3730


def test_parse_iso8601_duration_seconds_only():
    text, sec = parse_iso8601_duration("PT45S")
    assert text == "00:45"
    assert sec == 45


def test_parse_iso8601_duration_invalid_or_none():
    assert parse_iso8601_duration(None) == ("", 0)
    assert parse_iso8601_duration("") == ("", 0)
    assert parse_iso8601_duration("INVALID") == ("", 0)
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_youtube_popular_trends.py -k "test_parse_iso8601_duration" -v`  
Expected: FAIL com `ImportError: cannot import name 'parse_iso8601_duration'`

- [ ] **Step 3: Implementar `parse_iso8601_duration` e adicionar `contentDetails` em `youtube_trends.py`**

Adicionar regex para parsing de ISO 8601 (`r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$"`) em `youtube_trends.py`.  
Atualizar as chamadas de `videos.list` (`fetch_popular_trends` e `fetch_search_trends`) para incluir `part="snippet,statistics,contentDetails"`, extraindo `duration` e `duration_s` para cada item de evidência.

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_youtube_popular_trends.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/youtube_trends.py tests/test_youtube_popular_trends.py
git commit -m "feat(trends): parse ISO 8601 duration and add contentDetails to youtube adapter"
```

---

### Task 2: Domínio de Sinais e Priorização Pura (`domain/trend_priority.py`)

**Files:**
- Create: `renderer/app/studio/domain/trend_priority.py`
- Test: `tests/test_trend_priority.py`

**Interfaces:**
- Produces: `dataclass PriorityBreakdown`: `velocity_score: int`, `niche_ratio_score: int`, `competition_score: int`, `adherence_score: int`, `variety_score: int`, `total_score: int`, `summary: str`, `risk_status: str`, `risk_level: str` (`"ok"`, `"warn"`, `"danger"`), `is_evergreen: bool`.
- Produces: `calculate_priority(views: int, published_at: datetime | None, niche_median_views: float, is_trending_chart: bool, has_category: bool, recent_channel_titles: list[str], title: str, now: datetime) -> PriorityBreakdown`.

- [ ] **Step 1: Escrever os testes de falha para priorização pura**

```python
# Em tests/test_trend_priority.py
from datetime import datetime, timedelta, timezone
from app.studio.domain.trend_priority import calculate_priority

T0 = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


def test_high_velocity_niche_aligned_gets_high_priority():
    published = T0 - timedelta(hours=24)
    # 240.000 views em 24h = 10.000 views/h; mediana do nicho = 50.000 (ratio = 4.8x)
    bd = calculate_priority(
        views=240_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=["Vídeo Antigo de Culinária"],
        title="O Segredo do Satélite Soviético",
        now=T0,
    )
    assert bd.total_score >= 80
    assert bd.risk_level == "ok"
    assert bd.is_evergreen is False


def test_repetitive_title_triggers_warning():
    published = T0 - timedelta(hours=48)
    recent = [
        "Satélite soviético misterioso",
        "Outro satélite da guerra fria",
        "Mais um mistério soviético",
    ]
    bd = calculate_priority(
        views=100_000,
        published_at=published,
        niche_median_views=50_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=recent,
        title="O que a NASA encontrou no satélite soviético",
        now=T0,
    )
    assert bd.variety_score <= 40
    assert "repetição" in bd.risk_status.lower() or bd.risk_level == "warn"


def test_evergreen_classification():
    published = T0 - timedelta(days=200)
    bd = calculate_priority(
        views=500_000,
        published_at=published,
        niche_median_views=100_000.0,
        is_trending_chart=False,
        has_category=True,
        recent_channel_titles=[],
        title="Buracos misteriosos na Amazônia",
        now=T0,
    )
    assert bd.is_evergreen is True
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_trend_priority.py -v`  
Expected: FAIL com `ModuleNotFoundError: No module named 'app.studio.domain.trend_priority'`

- [ ] **Step 3: Implementar `calculate_priority` em `renderer/app/studio/domain/trend_priority.py`**

Implementar cálculo determinístico com as 5 parcelas de 20%, detecção de palavras-chave sensíveis de desmonetização, cálculo de sobreposição de termos contra os últimos títulos do canal, e classificação de `is_evergreen` (`dias > 180 and views >= 100_000`).

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_trend_priority.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/trend_priority.py tests/test_trend_priority.py
git commit -m "feat(trends): implement pure domain priority score and risk diagnostics"
```

---

### Task 3: Banco de Dados e Repositório de Ideias Guardadas (`saved_trends`)

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0049_saved_trends.sql`
- Modify: `renderer/app/studio/application/ports.py`
- Modify: `renderer/app/studio/adapters/postgres/trend_repo.py`
- Test: `tests/test_trend_repo.py`

**Interfaces:**
- Produces: `TrendRepository.save_trend_snapshot(project_id: str, snapshot: SavedTrendSnapshot) -> None`
- Produces: `TrendRepository.unsave_trend(project_id: str, video_id: str) -> None`
- Produces: `TrendRepository.list_saved_trends(project_id: str) -> list[SavedTrendSnapshot]`
- Produces: `TrendRepository.is_trend_saved(project_id: str, video_id: str) -> bool`

- [ ] **Step 1: Escrever os testes de falha para persistência de ideias guardadas**

```python
# Em tests/test_trend_repo.py
from app.studio.domain.trend_priority import SavedTrendSnapshot


def test_saved_trends_lifecycle(repo):
    p_id = "project-123"
    snap = SavedTrendSnapshot(
        project_id=p_id,
        video_id="vid_test_99",
        title="Ideia Salva no Canal",
        channel_title="Canal X",
        thumbnail_url="https://i.ytimg.com/vi/vid_test_99/hqdefault.jpg",
        video_url="https://youtube.com/watch?v=vid_test_99",
        duration="11:40",
        views=1_400_000,
        category_name="Mistérios",
        score=86,
    )
    repo.save_trend_snapshot(p_id, snap)
    assert repo.is_trend_saved(p_id, "vid_test_99") is True
    saved = repo.list_saved_trends(p_id)
    assert len(saved) == 1
    assert saved[0].title == "Ideia Salva no Canal"

    repo.unsave_trend(p_id, "vid_test_99")
    assert repo.is_trend_saved(p_id, "vid_test_99") is False
    assert len(repo.list_saved_trends(p_id)) == 0
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_trend_repo.py -k "test_saved_trends_lifecycle" -v`  
Expected: FAIL com `AttributeError: 'PostgresTrendRepository' has no attribute 'save_trend_snapshot'`

- [ ] **Step 3: Criar migração SQL e implementar métodos em `trend_repo.py` e `ports.py`**

Criar `0049_saved_trends.sql` com schema `studio.saved_trends` (`project_id`, `video_id`, `title`, `channel_title`, `thumbnail_url`, `video_url`, `duration`, `views`, `category_name`, `score`, `created_at`).  
Implementar `save_trend_snapshot`, `unsave_trend`, `list_saved_trends` e `is_trend_saved` em `trend_repo.py` com suporte para PostgreSQL e SQLite in-memory de teste.

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_trend_repo.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/postgres/migrations/0049_saved_trends.sql renderer/app/studio/application/ports.py renderer/app/studio/adapters/postgres/trend_repo.py tests/test_trend_repo.py
git commit -m "feat(trends): implement permanent saved_trends schema and repository methods"
```

---

### Task 4: Enriquecimento do ViewModel de Tendências (`application/panel.py` e `domain/trend_cards.py`)

**Files:**
- Modify: `renderer/app/studio/domain/trend_cards.py`
- Modify: `renderer/app/studio/application/panel.py`
- Test: `tests/test_trend_cards.py`

**Interfaces:**
- Consumes: `calculate_priority(...)` de `domain/trend_priority.py`.
- Consumes: `list_saved_trends(...)` de `TrendRepository`.
- Produces: `TrendItemView` contendo campos:
  - `velocity_text: str` (ex.: `"29 mil/h"`)
  - `niche_ratio_text: str` (ex.: `"▲ 3,4×"`)
  - `duration_text: str` (ex.: `"11:40"`)
  - `priority_score: int` (0–100)
  - `priority_summary: str` (frase explicativa)
  - `priority_breakdown: PriorityBreakdown`
  - `risk_status: str`
  - `risk_level: str`
  - `is_saved: bool`
  - `is_evergreen: bool`
- Produces: Ordenação em `BuildPanel` de acordo com `sort` (`"prioridade"`, `"velocidade"`, `"recentes"`).
- Produces: Filtragem em `BuildPanel` de acordo com `tipo` (`"todos"`, `"perenes"`, `"sem_risco"`, `"guardados"`).

- [ ] **Step 1: Escrever os testes de falha para ordenação e campos enriquecidos no cartão**

```python
# Em tests/test_trend_cards.py
def test_trend_cards_contain_velocity_and_priority_score():
    records = [popular("v1", "Canal 1", 500_000, T0 - timedelta(hours=10))]
    cards = build_trend_cards(records, now=T0)
    assert hasattr(cards[0], "priority_score")
    assert hasattr(cards[0], "velocity_text")
    assert hasattr(cards[0], "duration_text")
    assert cards[0].priority_score > 0
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_trend_cards.py -k "test_trend_cards_contain_velocity" -v`  
Expected: FAIL com `AssertionError: assert hasattr(...)`

- [ ] **Step 3: Implementar cálculo de métricas em `trend_cards.py` e ordenação/filtros em `panel.py`**

Adicionar campos em `TrendItemCard` e `TrendItemView`.  
Conectar o cálculo de prioridade utilizando a mediana de views dos vídeos do mesmo lote de categoria.  
Ajustar `BuildPanel` para aceitar `sort: str = "prioridade"` e `tipo: str = "todos"`. Se `tipo == "guardados"`, carregar os registros permanentes de `saved_trends`.

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_trend_cards.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/trend_cards.py renderer/app/studio/application/panel.py tests/test_trend_cards.py
git commit -m "feat(trends): enrich trend cards with velocity, niche ratio, priority and sorting"
```

---

### Task 5: Endpoints REST para Guardar e Desfavoritar Ideias

**Files:**
- Modify: `renderer/app/studio/api/panel_trends.py`
- Modify: `renderer/app/studio/api/routes.py`
- Test: `tests/test_trends_api.py`

**Interfaces:**
- Produces: `POST /studio/projects/{id}/saved-trends` $\to$ HTTP 201 `{ "ok": true, "video_id": "..." }`.
- Produces: `DELETE /studio/projects/{id}/saved-trends/{video_id}` $\to$ HTTP 200 `{ "ok": true }`.

- [ ] **Step 1: Escrever os testes de falha para os endpoints REST de favoritos**

```python
# Em tests/test_trends_api.py
def test_post_and_delete_saved_trend(client, test_project_id):
    payload = {
        "video_id": "test_vid_123",
        "title": "Mistério na Antártida",
        "channel_title": "Canal Mistério",
        "thumbnail_url": "https://i.ytimg.com/vi/test_vid_123/hqdefault.jpg",
        "video_url": "https://youtube.com/watch?v=test_vid_123",
        "duration": "14:20",
        "views": 850000,
        "category_name": "Mistérios",
        "score": 82,
    }
    r = client.post(f"/studio/projects/{test_project_id}/saved-trends", json=payload)
    assert r.status_code == 201
    assert r.json().get("ok") is True

    r_del = client.delete(f"/studio/projects/{test_project_id}/saved-trends/test_vid_123")
    assert r_del.status_code == 200
    assert r_del.json().get("ok") is True
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_trends_api.py -k "test_post_and_delete_saved_trend" -v`  
Expected: FAIL com status 404 Not Found

- [ ] **Step 3: Implementar os endpoints em `panel_trends.py` e registrar em `routes.py`**

Adicionar rotas com Pydantic schema de entrada para snapshot seguro e validação de `project_id`. Chamar `repo.save_trend_snapshot` e `repo.unsave_trend`.

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_trends_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_trends.py renderer/app/studio/api/routes.py tests/test_trends_api.py
git commit -m "feat(trends): add REST endpoints to save and delete channel trend ideas"
```

---

### Task 6: Interface dos Cards Variação A, Barra de Filtros/Ordenação e Modal de Transparência

**Files:**
- Modify: `renderer/app/studio/api/panel_trends.py`
- Test: `tests/test_trends_v3.py`

**Interfaces:**
- Consumes: `TrendItemView` enriquecido (Task 4) e endpoints REST (Task 5).
- Produces: HTML da página de Tendências com:
  - Cards `.card.cartao-tendencia` contendo miniatura 16:9 (`.cardthumb`), duração, badges de proveniência (`.src.api`, `.src.calc`, `.src.own`), sinais, barra de score e `<details class="more">`.
  - Botão de alternância `☆ Guardar` / `★ Guardado` com chamada assíncrona com `fetch` e nonce.
  - Barra de controle abaixo dos pilares: `Ordenar por [ Prioridade | Velocidade | Mais recentes ]` e `Mostrar [ Todos | Perenes | Sem risco | Guardados ]`.
  - Modal `#dialog-como-calculamos` aberto pelo botão `ⓘ Como calculamos`.

- [ ] **Step 1: Escrever os testes de falha de renderização HTML**

```python
# Em tests/test_trends_v3.py
def test_render_trends_v3_contains_variation_a_elements(panel_view):
    html, _ = render_tendencias_v3(panel_view)
    assert 'class="cardthumb"' in html
    assert 'class="signals"' in html
    assert 'class="score"' in html
    assert "Por que esta nota" in html
    assert "Como calculamos" in html
    assert "btn-guardar" in html
```

- [ ] **Step 2: Executar o teste para verificar que falha**

Run: `python3 -m pytest tests/test_trends_v3.py -k "test_render_trends_v3_contains_variation_a" -v`  
Expected: FAIL com `AssertionError: assert 'class="cardthumb"' in html`

- [ ] **Step 3: Implementar a renderização dos cartões Variação A, barra de ordenação e diálogo em `panel_trends.py`**

Atualizar `_trend_card()` para produzir a estrutura da Variação A conforme a seção 5 da spec.  
Atualizar o cabeçalho para incluir a barra segmentada de ordenação e filtros rápidos com links estáveis.  
Adicionar o markup do diálogo `#dialog-como-calculamos`.  
Adicionar no `TRENDS_JS` o handler do clique do botão `.btn-guardar` para disparar `POST/DELETE` e alternar texto entre `☆ Guardar` e `★ Guardado`.

- [ ] **Step 4: Executar o teste para verificar que passa**

Run: `python3 -m pytest tests/test_trends_v3.py -v`  
Expected: PASS

- [ ] **Step 5: Executar a suíte completa de testes de tendências**

Run: `python3 -m pytest tests/test_trends*.py tests/test_trend*.py tests/test_youtube_popular_trends.py -v`  
Expected: Todos os testes PASS

- [ ] **Step 6: Commit**

```bash
git add renderer/app/studio/api/panel_trends.py tests/test_trends_v3.py
git commit -m "feat(trends): render Variation A cards with signals, priority breakdown, and transparency modal"
```
