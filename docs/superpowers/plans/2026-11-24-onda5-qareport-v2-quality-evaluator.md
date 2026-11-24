# Onda 5 — Avaliação Audiovisual: QaReport v2 & Quality Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o sistema de QA do Faceless Studio para o QaReport v2, incorporando novas verificações determinísticas de áudio (True-Peak e clipping em dBTP), codecs de mídia (H.264 / AAC), repetição de assets em cenas adjacentes, congelamento prolongado de quadros, associação de achados a cenas (`scene_id`) com flags de auto-fix e intervenção humana, e interface aprimorada na aba de Qualidade.

**Architecture:**
- Domínio de QA (`domain/qa_report.py`, `domain/quality.py`): Enriquecimento de `QaFinding` com `scene_id`, `shot_id`, `auto_fixable` e `needs_human`. Novos checks determinísticos: `CHECK_TRUE_PEAK`, `CHECK_CODEC`, `CHECK_REPEATED_ASSETS`, `CHECK_FROZEN_FRAMES`.
- Adaptador FFmpeg (`adapters/qa_ffmpeg.py`, `adapters/quality_ffmpeg.py`): Extração de True Peak via filtro `ebur128=peak=true`, inspeção de codecs de vídeo e áudio via streams do `ffprobe`, e detecção de freeze.
- Verificador Semântico (`adapters/quality_semantic.py`, `application/quality.py`): Verificação de coerência textual roteiro-tema e declaração explícita de cobertura visual/multimodal graciosa sem provedor.
- Interface Web (`api/panel_video_workspace.py`): Exibição dos achados com badge por cena, severidade e link direto para o storyboard.

**Tech Stack:** Python 3.11+, Pydantic v2, FFmpeg 7+ / ffprobe, Starlette / FastAPI, Pytest.

**Spec:** `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` (Onda 5 — Avaliação).

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub.
- Clean Architecture: `domain/` sem I/O, adapters isolados, decisões no domínio.
- Falsos positivos e falha fechada: Nota alta de LLM nunca libera sozinha; cobertura `not_verified` requer justificativa; severidade desconhecida é contada como `blocking`.
- Testes exclusivamente no contêiner Docker: `TMPDIR=/tmp scripts/test-container.sh <testes> -q`.
- Preservar integridade dos 482+ testes existentes.

## Review Focus

1. **Retrocompatibilidade de `QaFinding`**: Campos novos (`scene_id`, `shot_id`, `auto_fixable`, `needs_human`) devem ter defaults (`None` e `False`), preservando imutabilidade `frozen=True` e `extra="forbid"`.
2. **True-Peak e Clipping de Áudio**: `true_peak > 0.0 dBTP` é `blocking` (distorção perceptível/estouro digital); `true_peak > -1.0 dBTP` é `warning` (limiar de recomendação para plataformas de streaming como YouTube e Spotify).
3. **Repetição de Mídia em Cenas Adjacentes**: Se cenas consecutivas utilizam o mesmo `asset_id` (ou `asset_ref`), o check `render.repeated_assets` deve gerar um `warning` apontando a `scene_id` afetada e sugerindo variação de tomada ou troca de mídia.
4. **Validação de Codecs**: O formato padrão do YouTube requer vídeo H.264 (`avc1`/`h264`) e áudio AAC (`aac`). Codecs incompatíveis geram `blocking`.
5. **Apresentação Visual na UX**: A aba de Qualidade deve renderizar os achados agrupados ou identificados por cena, permitindo ao operador navegar até a bancada da cena.

---

### Task 1: Contrato QaFinding v2 e QaReport Enriquecido (Domínio)

**Files:**
- Modify: `renderer/app/studio/domain/qa_report.py:213-233`
- Create: `tests/test_qa_report_v2_contract.py`

**Interfaces:**
- Produces:
  - `domain/qa_report.py::QaFinding`: novos campos:
    - `scene_id: str | None = None`
    - `shot_id: str | None = None`
    - `auto_fixable: bool = False`
    - `needs_human: bool = False`
  - Métodos e validadores atualizados garantindo consistência com `extra="forbid"`.

- [ ] **Step 1: Write failing test in `tests/test_qa_report_v2_contract.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_qa_report_v2_contract.py -q`
  Expected: FAIL
- [ ] **Step 3: Update `QaFinding` model in `renderer/app/studio/domain/qa_report.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_qa_report_v2_contract.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/qa_report.py tests/test_qa_report_v2_contract.py
  git commit -m "feat(qa): evoluir contrato QaFinding com scene_id, shot_id, auto_fixable e needs_human"
  ```

---

### Task 2: Novos Checks Determinísticos no Domínio de Qualidade (`domain/quality.py`)

**Files:**
- Modify: `renderer/app/studio/domain/quality.py`
- Modify: `renderer/app/studio/domain/render.py:131-162`
- Create: `tests/test_quality_v2_domain.py`

**Interfaces:**
- Produces:
  - Constantes de checks em `domain/quality.py`:
    - `CHECK_TRUE_PEAK = "render.true_peak"`
    - `CHECK_CODEC = "render.codec"`
    - `CHECK_REPEATED_ASSETS = "render.repeated_assets"`
    - `CHECK_FROZEN_FRAMES = "render.frozen_frames"`
  - Regras em `evaluate_qa` e `_collect_media_checks`:
    - True-peak check: `true_peak_dbtp` medido. Se `> 0.0` gera `blocking`; se `> -1.0` gera `warning`.
    - Codec check: `video_codec` e `audio_codec`. Se não for `h264`/`avc1` e `aac`, gera `blocking`.
    - Repeated assets check: inspeciona shots de cenas vizinhas no `RenderPlan`. Se `shot.asset_ref` for idêntico em cenas adjacentes, gera achado com `scene_id` da segunda cena e `auto_fixable=True`.
    - Frozen frames check: se `frozen_ratio > 0.15` (ou duração contínua congelada > 3s), gera `warning`.

- [ ] **Step 1: Write failing test in `tests/test_quality_v2_domain.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_v2_domain.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement new quality checks and rules in `domain/quality.py` and `domain/render.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_v2_domain.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/quality.py renderer/app/studio/domain/render.py tests/test_quality_v2_domain.py
  git commit -m "feat(qa): implementar checks de true-peak, codec, assets repetidos e frames congelados"
  ```

---

### Task 3: Adaptador FFmpeg QA com Métricas Avançadas (`adapters/qa_ffmpeg.py`)

**Files:**
- Modify: `renderer/app/studio/adapters/qa_ffmpeg.py`
- Modify: `renderer/app/studio/adapters/quality_ffmpeg.py`
- Create: `tests/test_quality_ffmpeg_v2.py`

**Interfaces:**
- Produces:
  - `FfmpegQa.analyze`:
    - Extração de `True peak:` no log do `ebur128=peak=true` -> métrica `true_peak_dbtp: float | None`.
    - Leitura de `video_codec` e `audio_codec` das streams do `ffprobe`.
    - Execução do filtro `freezedetect` -> métrica `frozen_ratio: float`.
  - `FfmpegQualityProbe`: repassa as novas métricas para `QualityEvidence.media`.

- [ ] **Step 1: Write failing test in `tests/test_quality_ffmpeg_v2.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_ffmpeg_v2.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement extraction in `adapters/qa_ffmpeg.py` and `adapters/quality_ffmpeg.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_ffmpeg_v2.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/qa_ffmpeg.py renderer/app/studio/adapters/quality_ffmpeg.py tests/test_quality_ffmpeg_v2.py
  git commit -m "feat(qa): extrator ffmpeg para true-peak, codecs e deteccao de frames congelados"
  ```

---

### Task 4: Avaliação Semântica Aprimorada e Coerência (`adapters/quality_semantic.py`)

**Files:**
- Modify: `renderer/app/studio/adapters/quality_semantic.py`
- Modify: `renderer/app/studio/application/quality.py`
- Create: `tests/test_quality_semantic_v2.py`

**Interfaces:**
- Produces:
  - `SemanticChecker`: suporte à verificação de coerência entre briefing criativo / visual intent e o roteiro gerado.
  - Degradação declarada quando não houver LLM de visão: `not_verified` com motivo auditável explícito.
  - Testes cobrindo reprovação semântica (`verdict="failed"` -> `blocking`) e aprovação textual.

- [ ] **Step 1: Write failing test in `tests/test_quality_semantic_v2.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_semantic_v2.py -q`
  Expected: FAIL
- [ ] **Step 3: Update `adapters/quality_semantic.py` and `application/quality.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_quality_semantic_v2.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/quality_semantic.py renderer/app/studio/application/quality.py tests/test_quality_semantic_v2.py
  git commit -m "feat(qa): aprimorar verificador semantico com auditoria de coerencia e degradacao graciosa"
  ```

---

### Task 5: Apresentação de Achados por Cena na UX de Qualidade (`panel_video_workspace.py`)

**Files:**
- Modify: `renderer/app/studio/api/panel_video_workspace.py:1170-1250`
- Create: `tests/test_panel_quality_v2.py`

**Interfaces:**
- Consumes: `QaReport` v2 com `scene_id`, `auto_fixable` e `needs_human`.
- Produces:
  - Cartão de Verificações Técnicas e lista de Achados:
    - Exibe badge de identificação de cena `Cena N` quando `finding.scene_id` estiver presente, com link para a bancada da cena.
    - Badges informativos: `⚡ Auto-correção disponível` ou `👤 Requer operador`.
    - Exibição de métricas técnicas no detalhe: True-Peak (dBTP), LUFS integrado, Codec e ratio de congelamento.

- [ ] **Step 1: Write failing test in `tests/test_panel_quality_v2.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_quality_v2.py -q`
  Expected: FAIL
- [ ] **Step 3: Update `_area_qualidade` in `panel_video_workspace.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_panel_quality_v2.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/api/panel_video_workspace.py tests/test_panel_quality_v2.py
  git commit -m "feat(ux): apresentar achados de QA vinculados a cena e badges operacionais"
  ```

---

### Task 6: Snapshot de Contratos e Validação Ampla

**Files:**
- Update: `contracts/v1/qareport.schema.json`
- Test: Todas as suítes no contêiner Docker.

- [ ] **Step 1: Gerar e verificar schemas de contratos atualizados**
  Run: `docker run --rm -v "$(pwd):/w" -w /w faceless-renderer-pytest:test python3 scripts/export_contracts.py`
  Verify: `git diff contracts/`
- [ ] **Step 2: Executar testes de QA e regressão completa**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_qa_report_v2_contract.py tests/test_quality_v2_domain.py tests/test_quality_ffmpeg_v2.py tests/test_quality_semantic_v2.py tests/test_panel_quality_v2.py tests/test_contracts_snapshot.py -q`
  Expected: ALL PASS
- [ ] **Step 3: Executar regressão de todas as ondas**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py tests/test_panel_new_video_active.py tests/test_panel_direction_tab.py tests/test_panel_scene_multimedia.py tests/test_video_download_and_audiovisual_summary.py tests/test_pacing_*.py tests/test_music_*.py tests/test_captions_*.py tests/test_word_alignment.py tests/test_render_plan_*.py tests/test_creative_director_*.py tests/test_media_*.py tests/test_audio_director.py -q`
  Expected: ALL PASS
- [ ] **Step 4: Atualizar CONTINUITY com a conclusão da Onda 5**
