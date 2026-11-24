# Onda 3 — Qualidade Audiovisual: Pacing Engine, Audio Director & Captions ASS/Whisper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o Pacing Engine para cortes dinâmicos ritmados na narração, o Audio Director para mixagem de trilha sonora CC0 com ducking automático, e o Captions Engine para legendas dinâmicas em formato ASS com realce de palavra ativa.

**Architecture:**
- Domínio de Pacing (`domain/pacing.py`): Motor puro de cálculo de ritmo de cortes visuais por preset (`dynamic`, `balanced`, `cinematic`), subdividindo cenas em tomadas sincronizadas com a narração e alternando movimentos Ken Burns para assets únicos.
- Domínio e Aplicação Musical (`domain/music.py`, `application/audio_director.py`): Catálogo local de faixas CC0 (`storage/music-candidates/manifest.json`), seleção semântica por tom/humor e configuração declarativa de `AudioMix` (ducking, fade in/out e loudness).
- Domínio e Adaptador de Legendas (`domain/captions.py`, `adapters/captions_ass.py`): Motor de legendas dinâmicas gerando scripts SubStation Alpha (`.ass` v4+) com safe areas para formatos vertical (9:16) e horizontal (16:9), além de realce estilo karaoke por palavra (`\k`).
- Serviço de Alinhamento Temporal (`adapters/alignment.py`): Alinhador determinístico por caractere/pontuação nativo para CPU, com suporte modular a sidecar HTTP para Whisper (`WHISPER_URL`).
- Compilação e Renderização (`adapters/render_plan_compiler.py`, `adapters/render_plan_ffmpeg.py`): Integração de mixagem de áudio com ducking via FFmpeg e queima de legendas ASS no vídeo composto.

**Tech Stack:** Python 3.11/3.12, Pydantic v2, FFmpeg (libass, sidechaincompress/amix), HTTPX, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-onda3-qualidade-audiovisual-design.md`.

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção de arquivo via GitHub.
- Clean Architecture: `domain/` não importa `ffmpeg`, `requests`, `httpx`, banco de dados nem I/O.
- Todas as trilhas musicais devem vir do catálogo local licenciado CC0 (`storage/music-candidates/manifest.json`) com licença e hash verificados.
- Testes rodam dentro do contêiner via `TMPDIR=/tmp scripts/test-container.sh`.
- Preservação da retrocompatibilidade com RenderPlan v1 e suíte de regressão (566 testes passando).

## Review Focus

1. **Sincronia de Beats e Duração da Cena**: A soma das durações dos shots calculados pelo `PacingEngine` deve ser exatamente igual à duração total da cena em ticks, sem lacunas ou sobras.
2. **Safe Margins em Legendas ASS**: Legendas para o formato vertical (9:16) não devem ultrapassar a margem inferior de 280 pixels, evitando sobreposição com o título e controles de interface do YouTube Shorts.
3. **Fade-out e Ducking sem Estouro de Áudio**: O áudio mixado da trilha sonora com narração não deve ultrapassar o teto de true-peak (`-1.5 dBFS`) nem truncar bruscamente ao final do vídeo.
4. **Isolamento e Robustez do Alinhador**: Caso `WHISPER_URL` não esteja acessível ou demore para responder, o sistema deve recorrer transparentemente ao estimador acústico/determinístico local sem falhar a geração do vídeo.
5. **Dinamismo em Asset Único**: Cenas com apenas 1 asset de imagem e duração > 3.5s no preset dinâmico devem ser divididas em múltiplos shots com direções alternadas de movimento Ken Burns (`zoom_in` -> `zoom_out`).

---

### Task 1: Motor de Pacing (`domain/pacing.py`)

**Files:**
- Create: `renderer/app/studio/domain/pacing.py`
- Create: `tests/test_pacing_engine.py`

**Interfaces:**
- Produces:
  - `class PacingPreset(StrEnum)`: `dynamic`, `balanced`, `cinematic`
  - `class ShotTiming(BaseModel)`: `shot_index: int`, `start_tick: int`, `duration_ticks: int`, `motion: Motion`
  - `class PacingPlan(BaseModel)`: `scene_id: str`, `shots: tuple[ShotTiming, ...]`, `total_duration_ticks: int`
  - `class PacingEngine`:
    - `calculate(scene_id: str, total_duration_ticks: int, ticks_per_second: int, asset_count: int = 1, preset: PacingPreset = PacingPreset.dynamic, is_video_asset: bool = False) -> PacingPlan`
    - Regras:
      - `dynamic`: mira 2.0s a 3.0s por corte.
      - `balanced`: mira 3.0s a 4.5s por corte.
      - `cinematic`: mira 4.5s a 7.0s por corte.
      - Se `asset_count == 1` e `not is_video_asset` e duração > 3.5s: subdivide em múltiplos shots alternando `motion` (`zoom_in` -> `zoom_out`).
      - Soma das durações = `total_duration_ticks` exato.

- [x] **Step 1: Write failing test in `tests/test_pacing_engine.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_pacing_engine.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `PacingEngine` in `renderer/app/studio/domain/pacing.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_pacing_engine.py tests/test_architecture.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/pacing.py tests/test_pacing_engine.py
  git commit -m "feat(pacing): implementar PacingEngine de dominio puro para cortes ritmados"
  ```

---

### Task 2: Catálogo de Música CC0 & Audio Director (`domain/music.py`, `application/audio_director.py`)

**Files:**
- Create: `renderer/app/studio/domain/music.py`
- Create: `renderer/app/studio/application/audio_director.py`
- Create: `tests/test_music_catalog.py`
- Create: `tests/test_audio_director.py`

**Interfaces:**
- Produces:
  - `class MusicTrack(BaseModel)`: `id: str`, `title: str`, `creator: str`, `license: str`, `file_path: str`, `duration_s: float`, `sha256: str`, `mood_tags: tuple[str, ...]`
  - `class MusicCatalog`:
    - `load_from_manifest(manifest_path: Path, storage_root: Path) -> MusicCatalog`
    - `find_tracks(mood: str | None = None) -> list[MusicTrack]`
  - `class AudioDirector`:
    - `select_track(tone: str, catalog: MusicCatalog) -> MusicTrack | None`
    - `build_audio_mix(music_gain: float = 0.35, ducking_ratio: float = 12.0) -> AudioMix`

- [x] **Step 1: Write failing tests in `tests/test_music_catalog.py` and `tests/test_audio_director.py`**
- [x] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_music_catalog.py tests/test_audio_director.py -q`
  Expected: FAIL
- [x] **Step 3: Implement `MusicCatalog` in `domain/music.py` and `AudioDirector` in `application/audio_director.py`**
- [x] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_music_catalog.py tests/test_audio_director.py -q`
  Expected: PASS
- [x] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/music.py renderer/app/studio/application/audio_director.py tests/test_music_catalog.py tests/test_audio_director.py
  git commit -m "feat(audio): implementar MusicCatalog local CC0 e caso de uso AudioDirector"
  ```

---

### Task 3: Motor de Legendas Dinâmicas ASS (`domain/captions.py`, `adapters/captions_ass.py`)

**Files:**
- Create: `renderer/app/studio/domain/captions.py`
- Create: `renderer/app/studio/adapters/captions_ass.py`
- Create: `tests/test_captions_ass.py`

**Interfaces:**
- Produces:
  - `class WordTiming(BaseModel)`: `word: str`, `start_ms: int`, `duration_ms: int`
  - `class CaptionLine(BaseModel)`: `start_ms: int`, `end_ms: int`, `text: str`, `words: tuple[WordTiming, ...]`
  - `class AssSubtitleRenderer`:
    - `render(lines: list[CaptionLine], format: VideoFormat, style_kind: str = "highlight") -> str`
    - Formata cabeçalho `[Script Info]`, `[V4+ Styles]`, `[Events]`.
    - Margem inferior protegida em 9:16 (`MarginV = 280` para evitar botões de Shorts) e 16:9 (`MarginV = 60`).
    - Aplica tags `{\k<centisegundos>}` para efeito karaoke/highlight da palavra ativa.

- [ ] **Step 1: Write failing test in `tests/test_captions_ass.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_captions_ass.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement `AssSubtitleRenderer` in `adapters/captions_ass.py` and domain models in `domain/captions.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_captions_ass.py tests/test_architecture.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/captions.py renderer/app/studio/adapters/captions_ass.py tests/test_captions_ass.py
  git commit -m "feat(captions): implementar gerador de legendas dinamicas ASS com highlight e safe margins"
  ```

---

### Task 4: Serviço de Alinhamento Temporal de Palavras (`adapters/alignment.py`)

**Files:**
- Create: `renderer/app/studio/adapters/alignment.py`
- Create: `tests/test_word_alignment.py`

**Interfaces:**
- Produces:
  - `class WordAlignmentService`:
    - `align_words(text: str, audio_duration_ms: int, audio_path: Path | None = None) -> list[WordTiming]`
    - Modo nativo (CPU determinístico): calcula tempos relativos de cada palavra baseado no número de caracteres e pausas naturais de pontuação (`,`, `.`, `!`, `?`), normalizado pela duração real do áudio `audio_duration_ms`.
    - Modo Whisper (HTTP opcional se `WHISPER_URL` configurado): consulta sidecar com timeout estrito e fallback automático para o modo nativo em caso de erro ou divergência de texto.

- [ ] **Step 1: Write failing test in `tests/test_word_alignment.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_word_alignment.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement `WordAlignmentService` in `adapters/alignment.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_word_alignment.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/alignment.py tests/test_word_alignment.py
  git commit -m "feat(alignment): implementar servico de alinhamento de palavras hibrido deterministico e Whisper"
  ```

---

### Task 5: Integração no RenderPlanBuilder e Compilador v2 (`render_plan_builder.py`, `render_plan_compiler.py`)

**Files:**
- Modify: `renderer/app/studio/domain/render_plan_builder.py`
- Modify: `renderer/app/studio/adapters/render_plan_compiler.py`
- Create: `tests/test_render_plan_builder_audiovisual.py`

**Interfaces:**
- Consumes: `PacingEngine`, `MusicCatalog`, `AudioDirector`, `WordAlignmentService`, `AssSubtitleRenderer`
- Produces:
  - `RenderPlanBuilder.build(...)`:
    - Aplica `PacingEngine` para gerar shots ritmados por cena com transições e `Effects`.
    - Anexa a faixa de música selecionada em `asset_manifest` com `kind="music"` e configura `AudioMix`.
    - Preenche `timeline.subtitles` e escreve o arquivo `.ass` de legendas para o job.

- [ ] **Step 1: Write failing test in `tests/test_render_plan_builder_audiovisual.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_builder_audiovisual.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement integration in `render_plan_builder.py` and `render_plan_compiler.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_builder_audiovisual.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/domain/render_plan_builder.py renderer/app/studio/adapters/render_plan_compiler.py tests/test_render_plan_builder_audiovisual.py
  git commit -m "feat(renderplan): integrar pacing, musica local e legendas ASS no builder e compilador v2"
  ```

---

### Task 6: Renderização Audiovisual no FFmpeg (`render_plan_ffmpeg.py`)

**Files:**
- Modify: `renderer/app/studio/adapters/render_plan_ffmpeg.py`
- Create: `tests/test_render_plan_ffmpeg_audiovisual.py`

**Interfaces:**
- Produces:
  - `RenderPlanFFmpeg._assemble_video`:
    - Adiciona filtro de vídeo `subtitles='...':force_style='...'` quando `compiled.subtitles_ass_path` estiver presente.
    - Na mixagem de áudio, consome o arquivo real de música de `storage/music-candidates/`, aplica `aloop`, `volume={music_gain}`, e ducking com `sidechaincompress` contra a narração.
    - Aplica `afade=t=out:st={total_s - afade_out_s}:d={afade_out_s}` para encerramento musical suave.

- [ ] **Step 1: Write failing test in `tests/test_render_plan_ffmpeg_audiovisual.py`**
- [ ] **Step 2: Run test to verify it fails**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_ffmpeg_audiovisual.py -q`
  Expected: FAIL
- [ ] **Step 3: Implement audio ducking and ASS burning in `render_plan_ffmpeg.py`**
- [ ] **Step 4: Run test to verify it passes**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_render_plan_ffmpeg_audiovisual.py -q`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add renderer/app/studio/adapters/render_plan_ffmpeg.py tests/test_render_plan_ffmpeg_audiovisual.py
  git commit -m "feat(ffmpeg): implementar mixagem com ducking musical e queima de legendas ASS no FFmpeg"
  ```

---

### Task 7: Validação de Regressão e Fechamento da Onda 3

**Files:**
- Modify: `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md`
- Modify: `docs/superpowers/plans/2026-11-24-onda3-qualidade-audiovisual-pacing-audio-captions.md`

- [ ] **Step 1: Run full regression test suite in container**
  Run: `TMPDIR=/tmp scripts/test-container.sh tests/test_pacing_*.py tests/test_music_*.py tests/test_captions_*.py tests/test_word_alignment.py tests/test_render_plan_*.py tests/test_creative_director_*.py tests/test_media_*.py tests/test_contracts_snapshot.py -q`
  Expected: ALL PASS (0 failures)
- [ ] **Step 2: Verify git status is clean and document progress**
  Atualizar `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md` marcando Onda 3 como concluída.
- [ ] **Step 3: Commit**
  ```bash
  git add docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md docs/superpowers/plans/2026-11-24-onda3-qualidade-audiovisual-pacing-audio-captions.md
  git commit -m "docs(onda3): registrar conclusao da Onda 3 - Qualidade Audiovisual"
  ```
