# V3 - Plano 2: Motor de Composição Visual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as capacidades do motor de composição visual descritas no roadmap V3: suporte a posição da legenda (topo/meio/base), fonte e estilo da legenda (caixa/simples), ativação da transição fade no RenderPlan, metadados de B-roll em cenas e ativação dos controles vigentes na UI de composição.

**Architecture:**
- Domínio de Estilo (`domain/visual_style.py`): Expandir `_clean_caption` para validar `position`, `font_family`, `style_kind`. Promover `transition` para `APPLIED_GROUPS`.
- Renderização de Legendas (`adapters/render_plan_ffmpeg.py`): `caption_layout` calcula geometria para topo/meio/base; `caption_overlay` suporta estilo de caixa vs simples e seleção tipográfica.
- Construtor do RenderPlan (`domain/render_plan_builder.py`): Preencher `Shot.transition = Transition(kind="fade", duration_ticks=...)` quando o estilo declarar transição fade.
- Metadados de B-Roll (`adapters/postgres/migrations/0048_scene_broll.sql`, `domain/contracts.py`, `repo.py`): Armazenar `broll_enabled` e `broll_note` nas cenas do vídeo.
- UI do Workspace (`api/panel_video_workspace.py`): Habilitar os controles recém-suportados na aba `composicao` e no storyboard de `cenas`, enviando patches reais via `PATCH /studio/videos/{id}/style-patch`.

**Tech Stack:** Python 3.11, Pillow (PIL Image/ImageDraw/ImageFont), FFmpeg, PostgreSQL (psycopg 3), FastAPI, Pydantic v2, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-22-v3-decisoes-e-escopo.md` (Seção Plano 2).

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção via GitHub.
- Paridade de render e estabilidade de golden tests: vídeos sem o novo parâmetro mantêm exatamente a mesma geometria, cores e comandos de sempre.
- Honestidade do produto: parâmetros aplicados devem estar em `APPLIED_GROUPS`; parâmetros sem efeito real permanecem em `LOADED_ONLY_GROUPS`.
- Transição de vídeo não pode exceder a duração do shot correspondente.
- Todos os testes devem rodar limpos e sem quebrar esquemas de banco de dados existentes.

## Review Focus

1. **Paridade byte-a-byte de legendas legadas**: layouts sem `position` ou com `position="bottom"` devem manter idêntico `caption_bottom` e coordenadas originais. (Task 1)
2. **Fallback resiliente de fontes**: se uma família de fonte configurada (ex.: `"inter"`, `"roboto"`, `"georgia"`) não estiver fisicamente instalada no ambiente, o motor deve degradar graciosamente para `rich.FONT_BOLD` sem lançar `OSError`. (Task 2)
3. **Transição de saída em múltiplos shots**: a transição `fade` só pode ser aplicada a shots com próximo vizinho e com duração estritamente menor que o shot; o último shot da timeline não pode quebrar o render por tentar aplicar transição para o vazio. (Task 3)
4. **Idempotência de B-roll e migração**: `broll_enabled` deve ter default `false` e `broll_note` nulo; carregamento de cenas legadas sem B-roll deve instanciar valores seguros sem falhas de deserialização. (Task 4)
5. **Sincronização com o endpoint `/style-patch`**: formulário de composição deve enviar os novos campos (`caption.position`, `caption.font_family`, `caption.style_kind`, `transition`) para `/studio/videos/{id}/style-patch` respeitando `expected_revision`. (Task 5)

---

### Task 1: Posição da Legenda no Layout e Domínio de Estilo (Topo / Meio / Base)

**Files:**
- Modify: `renderer/app/studio/domain/visual_style.py:210-222`
- Modify: `renderer/app/studio/adapters/render_plan_ffmpeg.py:89-105`
- Create: `tests/test_caption_position_v3.py`

**Interfaces:**
- Consumes: `VideoFormat`, `ResolvedStyle`, `_LAYOUT`, `SIZE`
- Produces:
  - `_clean_caption`: valida chave opcional `position` pertencente a `("top", "middle", "bottom", "topo", "meio", "base")`. Normaliza internamente para `"top"`, `"middle"`, `"bottom"`.
  - `caption_layout(fmt, style)`: calcula `caption_bottom` e retorna chave adicional `"position"`:
    - `"bottom"`: usa `_LAYOUT[fmt]["caption_bottom"]` (1560 para short, 960 para long).
    - `"top"`: posiciona o bloco de legenda no terço superior (respeitando margem superior segura, ex.: 380px para short, 240px para long).
    - `"middle"`: centraliza o bloco verticalmente no quadro (`h // 2 + (len(lines) * line_h + 64) // 2`).
  - Sem `position`: preserva exatamente o `caption_bottom` e layout default.

- [x] **Step 1: Write failing test in `tests/test_caption_position_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement caption position support in `visual_style.py` and `render_plan_ffmpeg.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/visual_style.py renderer/app/studio/adapters/render_plan_ffmpeg.py tests/test_caption_position_v3.py
git commit -m "feat(studio): suportar posicao da legenda topo/meio/base no layout e estilo"
```

---

### Task 2: Fonte e Estilo Visual da Legenda (Caixa / Simples / Destaque)

**Files:**
- Modify: `renderer/app/studio/domain/visual_style.py:210-222`
- Modify: `renderer/app/studio/adapters/render_plan_ffmpeg.py:141-160`
- Modify: `tests/test_caption_position_v3.py`

**Interfaces:**
- Consumes: `caption.font_family`, `caption.style_kind`, `FONT`, `FONT_BOLD`
- Produces:
  - `_clean_caption`: aceita `font_family` em `("dejavu", "roboto", "georgia", "inter")` e `style_kind` em `("box", "simple", "word_highlight", "caixa", "simples", "destaque")`.
  - `resolve_caption_font(family, size)`: carrega a fonte solicitada ou faz fallback para `FONT_BOLD` se o arquivo de fonte TTF não existir.
  - `caption_overlay(fmt, text, dst, style)`:
    - Se `style_kind == "box"` (ou default): desenha a caixa arredondada de fundo (`rounded_rectangle`).
    - Se `style_kind == "simple"`: omite a caixa de fundo e desenha o texto com contorno reforçado/sombra escura para manter legibilidade sobre o vídeo.

- [x] **Step 1: Write failing test in `tests/test_caption_position_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement font family and style kind in `visual_style.py` and `render_plan_ffmpeg.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/visual_style.py renderer/app/studio/adapters/render_plan_ffmpeg.py tests/test_caption_position_v3.py
git commit -m "feat(studio): suportar familia de fontes e estilo de legenda caixa vs simples"
```

---

### Task 3: Transição Fade no Compilador de Planos e Promoção para `APPLIED_GROUPS`

**Files:**
- Modify: `renderer/app/studio/domain/visual_style.py:82-84`
- Modify: `renderer/app/studio/domain/render_plan_builder.py:240-270`
- Create: `tests/test_transition_applied_v3.py`

**Interfaces:**
- Consumes: `style.transition`, `Transition`
- Produces:
  - `APPLIED_GROUPS`: inclui `"transition"` (`frozenset({"motion", "music", "caption", "palette", "voice", "transition"})`).
  - `LOADED_ONLY_GROUPS`: atualizado como complemento exato.
  - `build_render_plan`: quando `style.transition` estiver ativo (`kind == "fade"` e `duration_ticks > 0`), aplica `Transition(kind="fade", duration_ticks=duration_ticks)` em todos os shots visuais base, exceto quando a duração do fade exceder a do shot.

- [x] **Step 1: Write failing test in `tests/test_transition_applied_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update `visual_style.py` and `render_plan_builder.py`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/visual_style.py renderer/app/studio/domain/render_plan_builder.py tests/test_transition_applied_v3.py
git commit -m "feat(studio): promover transicao fade para APPLIED_GROUPS e aplicar nos shots"
```

---

### Task 4: Metadados de B-Roll em Cenas (Migração 0048, Repositório e Storyboard)

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0048_scene_broll.sql`
- Modify: `renderer/app/studio/domain/contracts.py` (ou `SceneDetailView` / dataclass correspondente)
- Modify: `renderer/app/studio/adapters/postgres/repo.py`
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Create: `tests/test_scene_broll_v3.py`

**Interfaces:**
- Consumes: Cenas do vídeo, tabela `studio.scenes`
- Produces:
  - Migração 0048: `ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS broll_enabled boolean NOT NULL DEFAULT false; ALTER TABLE studio.scenes ADD COLUMN IF NOT EXISTS broll_note text NULL;`
  - Campos `broll_enabled: bool` e `broll_note: str | None` no modelo de cena e métodos de leitura/escrita do repositório.
  - Aba `cenas` do workspace: exibe checkbox `B-roll ativo` e campo de nota textual `Nota de B-roll` na cena em foco.

- [x] **Step 1: Write failing test in `tests/test_scene_broll_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Create migration 0048 and update schema, models and workspace**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/postgres/migrations/0048_scene_broll.sql renderer/app/studio/adapters/postgres/repo.py renderer/app/studio/domain/contracts.py renderer/app/studio/api/panel_video_workspace.py tests/test_scene_broll_v3.py
git commit -m "feat(studio): adicionar metadados de b-roll em cenas e controles no storyboard"
```

---

### Task 5: Ativação dos Controles Vigentes na UI de Composição e Conexão ao Style-Patch

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py`
- Modify: `tests/test_video_composition_v3.py`

**Interfaces:**
- Consumes: `_area_composicao`, `PAGE_JS`, `PATCH /studio/videos/{id}/style-patch`
- Produces:
  - Habilita na aba `composicao`:
    - Posição da legenda: Topo / Meio / Base (radios sem disabled, sem badge "Em breve").
    - Fonte da legenda: Inter / Roboto / Georgia / DejaVu (select habilitado).
    - Estilo da legenda: Caixa / Simples (radios habilitados).
    - Transição entre cenas: Fade / Corte seco (radios habilitados).
  - `#form-composicao` coleta e empacota `caption.position`, `caption.font_family`, `caption.style_kind` e `transition` no payload enviado via `PATCH /studio/videos/{id}/style-patch`.

- [x] **Step 1: Write failing test in `tests/test_video_composition_v3.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Update `panel_video_workspace.py` composition controls and JS**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_video_workspace.py tests/test_video_composition_v3.py
git commit -m "feat(studio): ativar controles de posicao, fonte e transicao na composicao V3"
```

---

### Task 6: Verificação de Regressão, Golden Tests e Integração em Container

**Files:**
- Test: `tests/test_caption_position_v3.py`, `tests/test_transition_applied_v3.py`, `tests/test_scene_broll_v3.py`, `tests/test_video_composition_v3.py`, `tests/test_render_plan_*.py`

- [x] **Step 1: Run all composition, layout and render plan test suites**
- [x] **Step 2: Run containerized test suite with PostgreSQL**
- [x] **Step 3: Commit final integration milestone**

```bash
git commit --allow-empty -m "chore: marco do plano 2 - motor de composicao visual concluido"
```

---
