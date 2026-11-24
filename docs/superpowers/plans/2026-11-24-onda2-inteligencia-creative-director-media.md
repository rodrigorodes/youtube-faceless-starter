# Onda 2 — Inteligência (Creative Director & Media Intelligence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o módulo Creative Director baseado em LLM com contrato tipado `CreativeBrief` e o motor de Media Intelligence com seleção semântica, pontuação por relevância (`MediaRanker`), deduplicação entre cenas, suporte a vídeos no Pexels e novo adaptador Pixabay.

**Architecture:**
- Domínio Criativo (`domain/creative_director.py`): Contrato puro e congelado `CreativeBrief` com validações de regras de negócio (limites de custo, direção visual, ritmo, abertura, hook).
- Domínio de Mídia Inteligente (`domain/media_ranker.py`): Motor determinístico `MediaRanker` que pontua candidatos de mídia baseado em casamento semântico de termos, resolução, aspect ratio, duração mínima e penalidade severa para repetições no mesmo vídeo.
- Aplicação Editorial & Mídia (`application/creative_director.py`, `application/editorial.py`, `application/media.py`): Caso de uso para gerar o briefing criativo via porta `TextModel`, injeção das diretrizes visuais no roteiro gerando intenção visual (`visual_intent`) e consultas por cena, e seleção inteligente de mídia via ranking e deduplicação.
- Adaptadores de Mídia (`adapters/media_pexels.py`, `adapters/media_pixabay.py`): Extensão do Pexels para suportar vídeo stock e novo adaptador Pixabay completo (imagem e vídeo) consumindo `PIXABAY_API_KEY`.
- Composição (`composition/wiring.py`, `composition/providers.py`): Registro e fiação do Pixabay no catálogo de provedores.

**Tech Stack:** Python 3.11/3.12, Pydantic v2, HTTPX, FastAPI, Pytest.

**Spec:** `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` (Seção 6, Onda 2).

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub.
- Clean Architecture: `domain/` não importa `requests`, `httpx`, banco de dados nem I/O.
- Respeito a limites orçamentários: chamadas ao LLM utilizam `PaidOperationGuard` e cache por hash de entrada (`paid_key`).
- Nenhum asset é cadastrado sem licença e URL de origem válidas.
- Testes que dependem de rede externa usam mocks/fakes; testes de live network são explicitamente marcados com `@pytest.mark.live`.
- Testes rodam dentro do contêiner via `TMPDIR=/tmp scripts/test-container.sh`.

## Review Focus

1. **Validação estrita de `CreativeBrief`**: O briefing criativo deve rejeitar sugestões perigosas, valores em branco e parâmetros de budget que excedam os tetos configurados.
2. **Deduplicação de mídia entre cenas**: O `MediaRanker` deve penalizar (`-50 pts`) candidatos já utilizados em outras cenas do mesmo vídeo, impedindo repetição visual monótona.
3. **Pexels Vídeo & Pixabay Parsing Defensivo**: Respostas de API com payloads parciais, URLs malformadas ou sem atribuição devem ser graciosamente rejeitadas sem levantar `KeyError`.
4. **Alinhamento de aspect ratio e duração**: Vídeos de stock devem ser avaliados com base no formato do vídeo (`landscape` vs `portrait`) e possuir duração suficiente para a cena.
5. **Idempotência e guarda de custo no Creative Director**: A chamada de direção criativa não deve disparar múltiplas cobranças para o mesmo tema/canal se os parâmetros de entrada não mudaram.

---

### Task 1: Contrato de Domínio `CreativeBrief`

**Files:**
- Create: `renderer/app/studio/domain/creative_director.py`
- Create: `tests/test_creative_director_domain.py`

**Interfaces:**
- Produces:
  - `class CreativeBrief(_Model)`:
    - `schema_version: int = 1`
    - `topic: NonBlank`
    - `narrative_goal: NonBlank`
    - `hook: NonBlank`
    - `content_structure: tuple[NonBlank, ...]` (mínimo 2 seções)
    - `tone: NonBlank`
    - `pacing: NonBlank`
    - `visual_direction: NonBlank`
    - `recommended_media_types: tuple[Literal["image", "video", "graphic", "text"], ...]`
    - `caption_strategy: NonBlank`
    - `audio_guidance: NonBlank`
    - `max_budget_usd: float | None = None`
    - `quality_criteria: tuple[NonBlank, ...] = ()`
    - Validações: `content_structure` não vazia, `max_budget_usd >= 0` se presente.

- [x] **Step 1: Write failing test in `tests/test_creative_director_domain.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_domain.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `CreativeBrief` in `domain/creative_director.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_domain.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/creative_director.py tests/test_creative_director_domain.py
  git commit -m "feat(director): definir contrato de dominio CreativeBrief"
  ```

---

### Task 2: Caso de Uso Creative Director & Prompt Enriquecido

**Files:**
- Create: `renderer/app/studio/application/creative_director.py`
- Modify: `renderer/app/studio/application/editorial.py:280-350`
- Create: `tests/test_creative_director_use_case.py`

**Interfaces:**
- Consumes: `TextModel`, `PaidOperationGuard`, `CreativeBrief`
- Produces:
  - `class CreateCreativeBrief`:
    - `execute(topic: str, channel_context: dict, budget_cap: float | None = None) -> CreativeBrief`
    - Constrói prompt estruturado exigindo JSON estrito compatível com `CreativeBrief`.
    - Executa sob `paid_key("creative_direction", ...)`.
  - `editorial.py`:
    - Atualiza `build_prompt` para aceitar `brief: CreativeBrief | None = None`.
    - Quando o brief estiver presente, injeta suas diretrizes e instrui o modelo a devolver por cena:
      - `visual_intent`: intenção visual descritiva
      - `recommended_asset_kind`: `"image"` ou `"video"`
      - `search_queries`: lista de termos concisos para busca em bancos de stock

- [x] **Step 1: Write failing test in `tests/test_creative_director_use_case.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_use_case.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `CreateCreativeBrief` e extensão de `build_prompt`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_use_case.py tests/test_editorial.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/application/creative_director.py renderer/app/studio/application/editorial.py tests/test_creative_director_use_case.py
  git commit -m "feat(director): implementar caso de uso CreateCreativeBrief e injecao no roteiro"
  ```

---

### Task 3: Motor de Seleção Inteligente de Mídia (`MediaRanker` & Dedupe)

**Files:**
- Create: `renderer/app/studio/domain/media_ranker.py`
- Create: `tests/test_media_ranker.py`

**Interfaces:**
- Consumes: `MediaCandidate`
- Produces:
  - `class ScoredCandidate`:
    - `candidate: MediaCandidate`
    - `score: float`
    - `reasons: tuple[str, ...]`
  - `class MediaRanker`:
    - `rank(candidates: list[MediaCandidate], *, visual_intent: str, queries: list[str], target_format: str, min_duration_s: float | None = None, used_media_ids: set[str] = set()) -> list[ScoredCandidate]`
    - Algoritmo de pontuação:
      - Resolução ideal (1080p ou superior): +20 pts
      - Orientação compatível (`portrait` para short, `landscape` para long): +30 pts
      - Casamento semântico de termos entre as tags/descrição da URL e as `queries`/`visual_intent`: até +30 pts
      - Duração de vídeo adequada (`duration >= min_duration_s`): +20 pts
      - Penalidade por repetição (`candidate.media_id in used_media_ids`): -50 pts
    - Retorna lista ordenada decrescente por score.

- [x] **Step 1: Write failing test in `tests/test_media_ranker.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_ranker.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `MediaRanker` in `domain/media_ranker.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_ranker.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/media_ranker.py tests/test_media_ranker.py
  git commit -m "feat(media): implementar MediaRanker com pontuacao deterministica e deduplicacao"
  ```

---

### Task 4: Suporte a Vídeo Stock no Adaptador Pexels

**Files:**
- Modify: `renderer/app/studio/adapters/media_pexels.py:30-120`
- Modify: `renderer/app/studio/application/ports.py:80-110` (se `duration_s` precisar ser adicionado em `MediaCandidate`)
- Create: `tests/test_media_pexels_video.py`

**Interfaces:**
- Consumes: `PexelsMediaSearch`, `httpx`
- Produces:
  - `MediaCandidate.duration_s: float | None = None`
  - `PexelsMediaSearch.search(query, media_type="video", ...)`:
    - Consulta `https://api.pexels.com/videos/search?query=...&orientation=...&per_page=...`
    - Converte resultados em `MediaCandidate` com `media_type="video"`, `duration_s`, resolução e atribuição completa (`Vídeo de {photographer} no Pexels`).
    - Mantém busca de fotos com `media_type="image"`.

- [x] **Step 1: Write failing test in `tests/test_media_pexels_video.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_pexels_video.py -q`
  Expected: FAIL
- [x] **Step 3: Implement video search in `adapters/media_pexels.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_pexels_video.py tests/test_media_search.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/media_pexels.py renderer/app/studio/application/ports.py tests/test_media_pexels_video.py
  git commit -m "feat(pexels): suportar busca de video stock na API do Pexels"
  ```

---

### Task 5: Adaptador Pixabay para Imagens e Vídeos

**Files:**
- Create: `renderer/app/studio/adapters/media_pixabay.py`
- Create: `tests/test_media_pixabay.py`

**Interfaces:**
- Consumes: `MediaSearch`, `MediaCandidate`
- Produces:
  - `class PixabayMediaSearch(MediaSearch)`:
    - `name = "pixabay"`
    - Inicializa com `api_key: str`, `license_text: str = "Pixabay Content License"`
    - Imagens: consulta `https://pixabay.com/api/?key=...&q=...&image_type=photo&orientation=...`
    - Vídeos: consulta `https://pixabay.com/api/videos/?key=...&q=...&video_type=all&orientation=...`
    - Retorna `list[MediaCandidate]` normalizados com proveniência, tags e créditos (`user` e `pageURL`).

- [x] **Step 1: Write failing test in `tests/test_media_pixabay.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_pixabay.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `PixabayMediaSearch` in `adapters/media_pixabay.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_pixabay.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/media_pixabay.py tests/test_media_pixabay.py
  git commit -m "feat(pixabay): implementar adaptador MediaSearch para fotos e videos do Pixabay"
  ```

---

### Task 6: Orquestração e Integração no Pipeline de Mídia

**Files:**
- Modify: `renderer/app/studio/composition/providers.py`
- Modify: `renderer/app/studio/composition/wiring.py`
- Modify: `renderer/app/studio/application/media.py`
- Create: `tests/test_media_intelligence_pipeline.py`

**Interfaces:**
- Consumes: `MediaRanker`, `PexelsMediaSearch`, `PixabayMediaSearch`, `ProduceAssets`
- Produces:
  - `MultiProviderMediaSearch`: agrega buscas do Pexels e Pixabay de forma resiliente.
  - `ProduceAssets` e `SearchSceneMedia`:
    - Consultam candidatos utilizando as `search_queries` da cena.
    - Aplicam `MediaRanker` passando `visual_intent` e `used_media_ids` acumulados.
    - Selecionam o candidato de maior score, evitando repetições de imagens/vídeos já utilizados em cenas anteriores.

- [x] **Step 1: Write failing test in `tests/test_media_intelligence_pipeline.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_intelligence_pipeline.py -q`
  Expected: FAIL
- [x] **Step 3: Implement multi-provider integration and ranking in media application**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_media_intelligence_pipeline.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/composition/providers.py renderer/app/studio/composition/wiring.py renderer/app/studio/application/media.py tests/test_media_intelligence_pipeline.py
  git commit -m "feat(media): integrar ranking inteligente, deduplicacao e suporte multiprovedor"
  ```

---

### Task 7: Validação de Regressão e Fechamento da Onda 2

**Files:**
- Test: Suíte completa de testes de editorial, mídia, contratos e render

- [x] **Step 1: Run full regression test suite in container**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_*.py tests/test_media_*.py tests/test_render_*.py tests/test_contracts_snapshot.py -q`
  Expected: ALL PASS (0 failures)
- [x] **Step 2: Verify git status is clean and document progress**
  Atualizar `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` marcando Onda 2 como concluída.
- [x] **Step 3: Commit**
  ```bash
  git add docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md docs/superpowers/plans/2026-11-24-onda2-inteligencia-creative-director-media.md
  git commit -m "docs(onda2): registrar conclusao da Onda 2 - Creative Director e Media Intelligence"
  ```
