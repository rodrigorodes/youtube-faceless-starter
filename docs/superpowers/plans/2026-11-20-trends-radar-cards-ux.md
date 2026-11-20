# Trends Radar (Brasil & Global), YouTube Cards & UX Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o radar de tendências do YouTube (Brasil e Mundo), cards no formato Opção A com miniaturas 16:9, links diretos de reprodução, tema visual inspirado no YouTube Dark e UX com indicador de carregamento (*loading*).

**Architecture:** O adaptador `youtube_trends.py` ganha a função `fetch_popular_trends` chamando `chart=mostPopular` da YouTube Data API v3 (custo de 1 unidade por região). O caso de uso `RefreshTrends` unifica a coleta popular e de pilares com resiliência a falhas. O `BuildPanel` extrai `video_id`, thumbnail oficial e metadados das evidências e classifica badges de região (`BR`/`GLOBAL`). O painel web (`api/panel.py`) renderiza cards ricos no tema YouTube Dark com links diretos, pílulas de filtro arredondadas estilo YouTube e JavaScript protegido por CSP nonce com feedback animado de loading.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL / psycopg3, YouTube Data API v3, Vanilla JS / CSS (sem bibliotecas externas pesadas), CSP Nonce, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-trends-radar-cards-ux-design.md`

## Global Constraints
- Python 3.12 com tipagem estrita (`from __future__ import annotations`), sem dependências frontend extras.
- Sem temas sintéticos gerados por LLM: todas as tendências vêm da YouTube Data API v3 com URL e videoId oficiais.
- Cota da API: `chart=mostPopular` consome exatamente 1 unidade de cota por chamada (2 unidades no total para Brasil e Mundo).
- Segurança CSP: 100% de scripts e estilos utilizam `nonce="{nonce}"`. Zero inline scripts sem nonce.
- Zero XSS: Toda interpolação no backend usa `html.escape`. Toda manipulação no frontend usa `textContent` e atributos seguros. Zero `innerHTML` com dados externos.
- Nenhuma quebra de retrocompatibilidade em testes existentes (`tests/test_category_api.py`, `tests/test_panel_page.py`, `tests/test_architecture.py`).

## Review Focus
1. Falha de rede ou cota na chamada popular não deve derrubar o refresh dos pilares (isolamento best-effort com logging).
2. URLs de vídeo do YouTube em formatos variados (`https://youtube.com/watch?v=ID`, `https://youtu.be/ID`) devem extrair corretamente o `video_id` de 11 caracteres para compor a thumbnail.
3. Tratamento de vídeos sem thumbnail ou com miniatura indisponível deve exibir fallback SVG limpo sem quebrar o layout.
4. O botão "Criar Vídeo deste Tema" deve sanitizar o texto antes de preencher o input `#topic` e não disparar submissão acidental.
5. As pílulas de filtro `[ 🇧🇷 Em Alta Brasil ]` e `[ 🌍 Em Alta Mundo ]` devem filtrar instantaneamente via DOM sem recarregar a página e sem conflitar com as pílulas de categorias.

---

### Task 1: YouTube Trends Adapter (`fetch_popular_trends`)

**Files:**
- Modify: `renderer/app/studio/adapters/youtube_trends.py`
- Test: `tests/test_youtube_popular_trends.py`

**Interfaces:**
- Produces: `fetch_popular_trends(yt_key: str, region_code: str, max_results: int = 10) -> list[TrendItem]`
- Consumes: `TrendItem`, `Evidence` de `renderer/app/studio/domain/trends.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_popular_trends_brazil_returns_items(monkeypatch):
    from app.studio.adapters.youtube_trends import fetch_popular_trends
    from app.studio.domain.trends import TrendItem

    # mock urllib.request.urlopen returning sample popular videos payload
    items = fetch_popular_trends("fake-key", "BR", max_results=2)
    assert len(items) == 2
    assert all(isinstance(it, TrendItem) for it in items)
    assert items[0].source_name == "YouTube Brasil (Em Alta)"
    assert items[0].source_url == "https://www.youtube.com/feed/trending"
    assert len(items[0].evidence) == 1
    assert items[0].evidence[0].url.startswith("https://youtube.com/watch?v=")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_youtube_popular_trends.py`
Expected: FAIL with `cannot import name 'fetch_popular_trends'`

- [ ] **Step 3: Implement `fetch_popular_trends` in `renderer/app/studio/adapters/youtube_trends.py`**

Implementar chamada ao endpoint `https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode={region_code}&maxResults={max_results}&key={yt_key}`. Mapear cada item retornado para um `TrendItem` com `source_name = "YouTube Brasil (Em Alta)"` se `region_code == "BR"` ou `"YouTube Global (Em Alta)"` se `region_code == "US"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_youtube_popular_trends.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/youtube_trends.py tests/test_youtube_popular_trends.py
git commit -m "feat(trends): add fetch_popular_trends for Brasil and Global mostPopular charts"
```

---

### Task 2: Application Layer (`RefreshTrends` & `BuildPanel`)

**Files:**
- Modify: `renderer/app/studio/application/categories.py`
- Modify: `renderer/app/studio/application/panel.py`
- Modify: `renderer/app/studio/composition.py`
- Test: `tests/test_category_api.py`
- Test: `tests/test_panel.py`

**Interfaces:**
- Produces: `TrendItemView` com `video_id: str | None`, `thumbnail_url: str | None`, `video_url: str | None`, `channel_title: str | None`, `published_text: str | None`, `region: str | None`
- Consumes: `fetch_popular_trends` de `renderer/app/studio/adapters/youtube_trends.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_panel_extracts_video_metadata_and_region():
    # test BuildPanel populates thumbnail_url, video_url, channel_title, and region on TrendItemView
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel.py::test_build_panel_extracts_video_metadata_and_region`
Expected: FAIL

- [ ] **Step 3: Implement changes in `categories.py` and `panel.py`**

1. Em `categories.py`: Em `RefreshTrends.execute()`, se `custom_queries` for `None`, coletar virais populares do Brasil (`BR`) e Global (`US`) junto com os pilares usando tratamento de exceção resiliente (`try/except`). Se `custom_queries` for passado, manter apenas a busca das queries customizadas.
2. Em `panel.py`: Adicionar campos em `TrendItemView` (`video_id`, `thumbnail_url`, `video_url`, `channel_title`, `published_text`, `region`). Extrair `video_id` da URL da evidência primária e definir `thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"`. Definir `region = "BR"` para Brasil e `"GLOBAL"` para Global.
3. Em `composition.py`: Injetar `popular_fetcher=fetch_popular_trends` em `RefreshTrends`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel.py tests/test_category_api.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/application/categories.py renderer/app/studio/application/panel.py renderer/app/studio/composition.py tests/test_panel.py tests/test_category_api.py
git commit -m "feat(panel): enrich TrendItemView with thumbnail, video link, and region classification"
```

---

### Task 3: Web Panel YouTube Theme & Option A Cards

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: HTML e CSS do card de tendência no estilo YouTube Dark (`.trend-card-yt`), miniatura 16:9, link direto para o YouTube (`target="_blank"`), badges de região (`🇧🇷 Em Alta Brasil`, `🌍 Em Alta Mundo`)
- Consumes: `TrendItemView` com `thumbnail_url`, `video_url`, `channel_title`, `region`

- [ ] **Step 1: Write the failing test in `tests/test_panel_page.py`**

```python
def test_panel_renders_youtube_themed_cards_and_video_links():
    # asserts that trend items render thumbnail <img> or fallback, link to youtube with target="_blank", channel name and region badges
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_renders_youtube_themed_cards_and_video_links`
Expected: FAIL

- [ ] **Step 3: Implement YouTube theme and Option A markup in `renderer/app/studio/api/panel.py`**

1. Adicionar estilos CSS inspirados no YouTube Dark:
   - Fundo `#181818`, borda `#282828`, miniatura 16:9 (`width: 168px; height: 94px; border-radius: 8px`).
   - Badge de duração sobre a miniatura.
   - Pílulas arredondadas estilo YouTube: `.cat-pill { background: #272727; color: #f1f1f1; border-radius: 18px; }` e ativa branca `#f1f1f1` com texto preto.
2. Renderizar card Opção A:
   - Miniatura à esquerda com link para o YouTube.
   - Título clicável com link externo `↗`.
   - Badges coloridos de região (`🇧🇷 Em Alta Brasil`, `🌍 Em Alta Mundo`) ou pilar.
   - Botões: `▶️ Assistir no YouTube` e `✨ Criar Vídeo deste Tema`.
3. Sanitizar 100% das variáveis com `e(...)` (`html.escape`).

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): YouTube Dark theme cards with 16:9 thumbnails and watch links"
```

---

### Task 4: UI Interactivity, Pill Filters & UX Loading

**Files:**
- Modify: `renderer/app/studio/api/panel.py`
- Test: `tests/test_panel_page.py`

**Interfaces:**
- Produces: JS interativo com CSP nonce para loading animado, filtro de pílulas por região/categoria e preenchimento suave no botão "Criar Vídeo"
- Consumes: Endpoints `/studio/projects/{id}/trends/refresh`

- [ ] **Step 1: Write failing test in `tests/test_panel_page.py`**

```python
def test_panel_page_has_loading_spinner_and_region_filters():
    # asserts presence of region filter pills [Em Alta Brasil] and [Em Alta Mundo] and spinner markup/script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.yfs-test.sh tests/test_panel_page.py::test_panel_page_has_loading_spinner_and_region_filters`
Expected: FAIL

- [ ] **Step 3: Implement client JS in `renderer/app/studio/api/panel.py`**

1. Pílulas de filtro:
   - Renderizar `[ 🔥 Todas (N) ]`, `[ 🇧🇷 Em Alta Brasil (N) ]`, `[ 🌍 Em Alta Mundo (N) ]`, seguidas pelas pílulas dos pilares.
   - No script JS: filtrar elementos `.trend-item` por `data-region` ou `data-category-id` ao clicar nas pílulas, atualizando a classe `.active`.
2. Loading spinner no botão "Buscar Agora":
   - Ao clicar, desabilitar botão (`btn.disabled = true`), trocar texto para `<span class="spinner-inline"></span> Consultando YouTube...`.
   - Adicionar animação CSS `@keyframes spin` para o spinner.
   - Em caso de sucesso, exibir mensagem de sucesso e recarregar a página suavemente.
   - Em caso de erro, reabilitar o botão e exibir mensagem clara.
3. Atalho no botão "Criar Vídeo deste Tema":
   - Preencher `input#topic.value = topicName`.
   - Fazer scroll suave até o formulário (`scrollIntoView({ behavior: 'smooth' })`).
   - Aplicar classe temporária de destaque visual (pulso/brilho) no campo.

- [ ] **Step 4: Run test to verify it passes**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel.py tests/test_panel_page.py
git commit -m "feat(panel): loading spinner, YouTube-style pill filters and smooth create action"
```

---

### Task 5: Docker Rebuild, Visual Validation & Docs

**Files:**
- Modify: `docs/18-painel.md`
- Modify: `docs/19-tendencias.md`
- Create/Update: `docs/images/painel-dashboard.png`

**Interfaces:**
- Produces: Container `renderer` reconstruído, screenshots em alta resolução e documentação operacional completa

- [ ] **Step 1: Rebuild renderer container and verify health**

Run: `docker compose up -d --build renderer && sleep 3 && curl -s http://localhost:8000/health`
Expected: `{"status":"ok","ffmpeg":true,"studio_db":"ok"}`

- [ ] **Step 2: Seed / Refresh popular trends via API**

Run:
```bash
curl -s -X POST -u studio:studio-pass-2026 -H "Origin: http://localhost:8000" http://localhost:8000/studio/projects/359e326ae66e46de86d4c560c74779f1/trends/refresh
```
Expected: `{"stored": N}` com itens de Brasil, Mundo e Pilares.

- [ ] **Step 3: Capture updated screenshots with Chrome headless**

Capturar `docs/images/painel-dashboard.png` com o novo visual dos cards YouTube Dark, thumbnails e pílulas.

- [ ] **Step 4: Update documentation**

Atualizar `docs/18-painel.md` e `docs/19-tendencias.md` com detalhes do radar Brasil/Mundo, links para assistir no YouTube e loading.

- [ ] **Step 5: Run full test suite in test container**

Run: `export STUDIO_TEST_DSN=postgresql://postgres:test@host.docker.internal:55432/yfs_security_test && ~/.yfs-test.sh tests/test_panel_page.py tests/test_panel.py tests/test_category_api.py tests/test_youtube_popular_trends.py tests/test_category_repo.py tests/test_db.py tests/test_architecture.py`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add docs/18-painel.md docs/19-tendencias.md docs/images/
git commit -m "docs: document trends radar, YouTube cards, and updated dashboard screenshot"
```
