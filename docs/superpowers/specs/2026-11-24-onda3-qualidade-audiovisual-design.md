# Onda 3 — Qualidade Audiovisual: Pacing Engine, Audio Director & Captions ASS/Whisper

**Data:** 2026-11-24  
**Status:** Proposto para aprovação  
**Contexto:** Evolução do Faceless Studio para produção de vídeos com qualidade profissional (Onda 3 de 6).  

---

## 1. Intenção e Justificativa

Vídeos faceless para YouTube (Shorts e Long-form) dependem criticamente de três pilares de retenção de audiência:
1. **Ritmo de cortes (Pacing):** Manter o espectador engajado alternando planos visuais no compasso da narração (beats), evitando cenas estáticas prolongadas (> 4–5s em Shorts).
2. **Design Sonoro (Audio Director):** Trilha musical de fundo condizente com o tom, com ducking automático (volume reduzido quando o narrador fala, ganho restaurado nas pausas) e transições suaves (fade in/out).
3. **Legendas Dinâmicas (Captions ASS):** Texto perfeitamente sincronizado palavra por palavra com realce visual (estilo karaoke/highlight), fontes de alto contraste e posicionamento em áreas seguras (safe areas) que não conflitem com a interface de Shorts/Reels/TikTok.

Hoje, o Faceless Studio possui o contrato declarativo `RenderPlan v2` com `AudioMix` e suporte a múltiplos shots por cena (entregues na Onda 1 e 2), mas ainda sintetiza áudio de música rudimentar (`synth_music`) e não gera legendas dinâmicas no vídeo final. A Onda 3 conecta esses blocos, elevando o resultado a padrão profissional de estúdio.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos (Goals)
- **Pacing Engine (`domain/pacing.py`)**:
  - Módulo de domínio puro que recebe a duração da cena, a narração e o preset de ritmo (`dynamic`, `balanced`, `cinematic`).
  - Calcula a divisão da cena em beats temporais e distribui os assets visuais disponíveis (vídeos/imagens) de forma ritmada (shots entre 1.5s e 3.5s para Shorts; 3.0s a 6.0s para Longs).
- **Catálogo de Trilha Sonora Local & Audio Director (`domain/music.py`, `application/audio_director.py`)**:
  - Leitor e indexador do catálogo de músicas CC0 locais em `storage/music-candidates/manifest.json`.
  - Casamento semântico do tom/gênero da música com o `CreativeBrief` (`ambient`, `lofi`, `scifi`, `cinematic`).
  - Aplicação dos parâmetros de `AudioMix` (`music_gain`, `ducking_threshold`, `ducking_ratio`, `afade_in_s`, `afade_out_s`, `loudnorm_i`).
- **Captions Engine (`domain/captions.py`, `adapters/captions_ass.py`)**:
  - Gerador de legendas SubStation Alpha (`.ass` v4+):
    - Estilos tipográficos profissionais (Montserrat/Inter/Arial bold, contorno escuro para legibilidade sobre qualquer fundo).
    - Margens seguras (safe areas): zona inferior protegida em formato 9:16 (evitando sobreposição com botões laterais e título inferior do YouTube Shorts).
    - Realce de palavra ativa (word-by-word karaoke highlight) usando tags `\k` do ASS.
- **Serviço de Alinhamento Temporal (`adapters/alignment.py`)**:
  - Motor de alinhamento por palavra da narração:
    - Estimador determinístico por fonema/caractere (zero dependência externa).
    - Fallback/suporte a Whisper (`faster-whisper`) para timestamps exatos de milissegundos quando o áudio TTS estiver gerado.
- **Compilador e Executor de Renderização (`render_plan_compiler.py`, `render_plan_ffmpeg.py`)**:
  - Inclusão do filtro `subtitles='...':force_style='...'` no grafo de filtros de vídeo do FFmpeg.
  - Mixagem de áudio com ducking via filtro `sidechaincompress` ou `amix` do FFmpeg utilizando o arquivo MP3 da trilha escolhida.

### Não-Objetivos (Non-Goals)
- Não alterar a estrutura do `RenderPlan v1` legado (permanece congelado).
- Não consumir APIs de música externas ou não-licenciadas: apenas faixas locais com licença CC0 explícita no catálogo verificado.
- Não depender de GPU obrigatória para renderização ou legendas: toda a pipeline deve rodar eficientemente em CPU (Lenovo ThinkCentre local).

### Anti-Objetivos (Anti-Goals)
- Nunca cortar imagens ou vídeos no meio de palavras da narração sem alinhamento com a pontuação.
- Nunca sobrepor legendas em safe areas proibidas (como o topo de Shorts com logo ou rodapé com descrição).
- Nunca estourar picos de áudio (clipping / true-peak > -1.0 dBFS).

---

## 3. Arquitetura e Contratos de Domínio

### 3.1 Pacing Engine (`domain/pacing.py`)
```python
class PacingPreset(StrEnum):
    dynamic = "dynamic"      # Shorts: 1.5s - 3.0s por corte
    balanced = "balanced"    # Shorts/Long: 2.5s - 4.5s por corte
    cinematic = "cinematic"  # Long: 4.0s - 7.0s por corte

class PacingPlan(BaseModel):
    scene_id: str
    target_shot_durations_ticks: tuple[int, ...]
    transition_points_ticks: tuple[int, ...]
```

### 3.2 Catálogo Musical & Audio Director (`domain/music.py`)
```python
class MusicTrack(BaseModel):
    id: str
    title: str
    creator: str
    license: str
    license_url: str
    file_path: str
    duration_s: float
    sha256: str
    mood_tags: tuple[str, ...]

class AudioDirector:
    """Seleciona a melhor faixa musical para o tom do roteiro e configura o AudioMix."""
    def select_track(self, tone: str, format: VideoFormat, catalog: list[MusicTrack]) -> MusicTrack: ...
```

### 3.3 Captions Engine (`domain/captions.py`)
```python
class WordCue(BaseModel):
    word: str
    start_tick: int
    duration_ticks: int

class CaptionBlock(BaseModel):
    scene_id: str
    start_tick: int
    duration_ticks: int
    words: tuple[WordCue, ...]
    raw_text: str

class AssSubtitleRenderer:
    """Converte blocos de legendas com word cues em script ASS formatado com estilos e safe margins."""
    def render(self, blocks: list[CaptionBlock], format: VideoFormat) -> str: ...
```

---

## 4. Integração no Pipeline de Renderização & Decisões Arquiteturais

### 4.1 Resoluções do Builder Check (Decisões de Engenharia)
1. **Queima de Legendas ASS (Global pós-concat vs Per-shot):**
   - As legendas ASS são aplicadas de forma global durante a montagem/composição final do vídeo (`_assemble_video` / pós-xfade), tratando o arquivo `.ass` como artefato efêmero na pasta do job (`job/captions.ass`).
   - Isso evita o fatiamento complexo de legendas em fronteiras de corte e preserva o cache de shots visuais sem invalidar o grafo quando apenas o estilo da legenda for alterado.
2. **Pacing com Asset Único (Ken Burns Alternado):**
   - Quando uma cena possuir apenas um asset de imagem e sua duração exceder o limiar do preset (ex.: > 3.5s em preset `dynamic`), o `PacingEngine` subdivide o tempo em 2 shots mantendo o mesmo asset, porém alternando os movimentos de câmera declarativos de `Effects` (ex.: `zoom_in` -> `zoom_out` ou `pan_left` -> `pan_right`), mantendo dinamismo visual sem exigir múltiplos arquivos.
3. **Alinhamento Temporal (Híbrido Determinístico + Whisper Opcional):**
   - O alinhamento padrão roda de forma determinística em CPU sem dependências pesadas (`torch`/`ctranslate2`), alinhando os caracteres e pausas da narração aos timestamps exatos das pontuações do áudio gerado pelo TTS.
   - Caso `WHISPER_URL` esteja configurado no ambiente, o adaptador consome o serviço sidecar via HTTP, reconciliando os timestamps de áudio com o texto canônico do roteiro via algoritmo de alinhamento monótono (evitando alucinações de ASR).
4. **Compatibilidade de Legendas (RenderPlan v2 ASS vs v1 Pillow):**
   - O motor ASS é a primeira classe do `RenderPlan v2` (com `schema_version = 2`). O renderizador legado v1 preserva `Pillow` para compatibilidade total com testes golden existentes.
5. **Ducking & Fade-Out da Trilha Musical:**
   - A duração total da timeline é obtida deterministicamente de `timeline.duration_ticks / timebase.ticks_per_second`. O filtro `afade=t=out:st=...:d=...` recebe o timestamp de início exato `st = max(0, total_s - afade_out_s)`, garantindo um fade-out suave antes do término do vídeo, sem paradas abruptas.


---

## 5. Estratégia de Testes

- **Unitários de Pacing (`test_pacing_engine.py`)**: validação de subdivisão de tempos por preset, garantia de que a soma dos ticks dos shots é idêntica à duração total da cena.
- **Unitários de Música (`test_music_catalog.py`)**: parsing do `manifest.json`, seleção determinística por tom, verificação de hash SHA256 e licenças CC0.
- **Unitários de Legendas (`test_captions_ass.py`)**: geração de sintaxe ASS válida, safe margins por formato (vertical vs horizontal), tags `\k` corretas.
- **Alinhamento (`test_alignment.py`)**: teste do alinhador de palavras com áudios de teste e validação de tolerância temporal.
- **Integração FFmpeg (`test_render_quality_audiovisual.py`)**: renderização de vídeo curto com música de fundo, ducking audível e legendas gravadas no MP4 final.
- **Regressão**: suite completa de 566 testes passando no container.
