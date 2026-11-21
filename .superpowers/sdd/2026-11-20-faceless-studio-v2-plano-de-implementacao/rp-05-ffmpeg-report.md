# RP-05 — Executor FFmpeg do Render Plan (fatia 6) — e remoção do renderer legado

**Fatia:** 6 (RP-05) da fundação **Render Plan** — RP-023 (já entregue na RP-03) consumido; RP-024/RP-025/RP-026
(composição/áudio/publicação atômica) implementados no executor; a flag de rollout **revogada por decisão do
usuário** e o **renderer legado removido** depois da paridade medida.
**Branch:** `feat/rp-05-ffmpeg` · **Worktree:** `…/39a258/rp-05-ffmpeg` · **Base ao iniciar:** `5da584a`.
**Restrições respeitadas:** nenhum arquivo fora da worktree; `domain/render_plan.py`, `domain/ticks.py`,
`application/render_compiler.py` **intactos**; `api/panel*.py`/`application/channels_page.py` intocados.
Commit local por caminho exato; **sem push e sem merge**.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `a60a78c` | RP-024..RP-026 — executor FFmpeg do plano + paridade | `renderer/app/studio/adapters/render_plan_ffmpeg.py` (novo), `tests/test_render_plan_executor.py` (novo), `tests/test_render_adapters.py` (migrado) |
| `0bde80c` | remoção do renderer legado (paridade já medida) | `renderer/app/studio/composition.py` (2 linhas), **delete** `renderer/app/studio/adapters/render_ffmpeg.py` |

Ordem escolhida de propósito: o executor e a migração dos testes **primeiro**; a remoção **depois** — a
árvore do commit `a60a78c` mantém o legado em disco (referência para medir a paridade) e o `0bde80c` só
apaga quando a medição já está registrada. Nada de `git add -A`.

## Como o caminho é escolhido (arquivo:linha) e por que não há flag

A decisão §5.6/§11-R2 ("legado default + novo atrás de flag") **foi revogada pelo usuário**: o caminho baseado
em plano passa a ser **o único**. Consequência no código:

- **Não existe flag** `STUDIO_RENDER_PLAN` nem `Settings.render_plan` — por isso o legado **não é default**: ele não existe mais.
- O `RunRender` **não muda** (`application/render.py:71-76`, `renderer_for`); nenhum dispatch dual foi escrito.
  Ele resolve o renderer como sempre: `renderer_for(video.project_id)` em `application/render.py:121`.
- A seleção concreta é a **composição**, em `renderer/app/studio/composition.py:288`:
  `register("renderer", "ffmpeg", PlanFfmpegRenderer)` (import na linha 46). O provider `ffmpeg:rich` do
  `ProjectConfig`/`STUDIO_RENDERER` continua o mesmo nome; só a implementação mudou.
- `PlanFfmpegRenderer.name = "ffmpeg"` (`adapters/render_plan_ffmpeg.py:158`), então a `cache_key` do asset de
  vídeo (`application/render.py:157`, `sha256("video|ffmpeg|…|job.id")`) **não muda**.

## O que o compilador puro (RP-023) já cobria vs. o que este executor acrescentou

**Já estava no compilador puro** (`application/render_compiler.py`, não tocado): grafo Ken Burns (`zoompan`)
com o modo **explícito** de `Effects.motion`; `scale` 1.5× lanczos + `format=yuv420p`; overlay de selo/disclosure
com índices de input corretos; legenda por trecho com `enable='gte(t,·)*lt(t,·)'` semiaberto; `fade` in/out por
segmento; `concat` `-c copy`; o `MIX_FILTER` com `sidechaincompress` (ducking) e `loudnorm=I=-16:TP=-1.5:LRA=11`;
os caminhos de `speech_NNN.wav`/`narration.wav`/`music.wav`; os parâmetros determinísticos da trilha (bpm 122,
seed 7) e o modo silencioso (C2); `digest()` determinístico; e as **recusas** (camada sobreposta, asset não
resolvido/indisponível, legenda que atravessa shot).

**Acrescentado no executor** (`adapters/render_plan_ffmpeg.py`):
1. **Materialização** dos overlays com Pillow: `static_overlay` (disclosure + selo `label`) e `caption_overlay`
   (legenda queimada) e `text_card` (asset de texto local, RP-021) — funções **movidas** do renderer antigo
   (mesmo código, comportamento idêntico).
2. **Áudio**: `rich.build_narration_track` sobre a fala de cada cena (ou silêncio do mesmo comprimento, para
   cena sem fala) e `rich.synth_music` (ou trilha muda de mesmo comprimento).
3. **Execução**: um `ffmpeg` por shot (`ShotExecution.args`), `concat` (`ConcatExecution.args`) e a mixagem
   (`AudioMix.args`), com timeout proporcional à duração.
4. **Publicação atômica** (`_publish`, linhas 325-335): o resultado é copiado para `<destino>.mp4.<uuid>.tmp` e
   movido com `os.replace` — nunca aparece um `.mp4` parcial no destino.
5. **Reconstrução do plano** a partir do `RenderSpec` (`_build_plan`/`_descriptors`): é o **único** ponto onde o
   `content_sha256` dos assets pode ser calculado (I/O de leitura), o que **mantém** `domain`/`application`
   puros. Desvio consciente do R2 ("`RunRender` constrói o plano"): fazê-lo no `RunRender` exigiria hash de
   arquivo na camada de aplicação. O plano é montado com o builder puro (RP-015/016) e o manifesto deduplica
   o **mesmo asset servindo várias cenas** (dois erros reais encontrados no E2E: `duplicate asset_id` e
   `SameFileError` quando a fala já estava no caminho esperado; ambos corrigidos e cobertos por teste).

## Tabela de paridade (medida ANTES de apagar o legado)

Medição real via `ffprobe`/`eBur128`/`blackdetect` + `evaluate_qa`, mesmo `RenderSpec` (2 cenas, 2.0 s + 1.5 s,
tom 220 Hz), na imagem `faceless-v2-hygiene-test-local:latest`:

| Recurso | Como foi medido | Legado (`FfmpegRenderer("rich")`) | Novo (plano) | Resultado |
|---|---|---|---|---|
| Resolução **short** | `ffprobe` `width×height` | 1080×1920 | 1080×1920 | idêntico |
| Resolução **long** | `ffprobe` `width×height` | 1920×1080 | 1920×1080 | idêntico |
| Duração (±1 s) | `ffprobe` `format.duration` | 5.12 s (short e long) | 5.16 s (short e long) | Δ 0.04 s ≤ 1 s |
| LUFS da mistura | `ebur128` (ffmpeg) | −15.3 | −15.3 | idêntico |
| LUFS da narração | `ebur128` na faixa de voz | −12.5 | −12.5 | idêntico |
| Razão de silêncio | `silencedetect` | 0.0 | 0.0 | idêntico |
| Razão de preto | `blackdetect` | 0.0 | 0.0 | idêntico |
| `evaluate_qa` (short/long) | `domain/render.evaluate_qa` | `passed=True` | `passed=True` | idêntico |
| **Ken Burns** (explícito por shot) | grafo `zoompan` do `CompiledRender` | `index % 4` (zoom_in/out/pan) | `Effects.motion` declarado; default reproduz o mesmo ciclo | mesma geometria |
| **Selo** (`label`) | PNG `static_NNN.png` materializado | presente | presente | idêntico (código movido) |
| **Disclosure** | PNG `static_NNN.png` materializado | presente | presente | idêntico (código movido) |
| **Legenda queimada por trecho** | frame extraído com/sem cue + `enable` semiaberto | presente | presente | `tests/test_render_adapters.py::test_subtitles_are_burned_into_the_frames` (migrado) |
| **Ducking** da música | `sidechaincompress` no `MIX_FILTER` | presente | presente | `test_audio_mix_reproduces_ducking_and_loudnorm_from_the_legacy_renderer` |
| **`loudnorm -16`** | `loudnorm=I=-16:TP=-1.5:LRA=11` | presente | presente | idem acima + LUFS medido |
| **Fades** in/out | `fade=t=in/out` no grafo | presente | presente | `test_still_image_compiles_to_ken_burns_with_legacy_geometry_and_encoding` |
| **Timebase 25 fps** | `-r 25` / `fps=25` no grafo | 25 | 25 | idêntico (`test_render_compiler` + `ffprobe`) |

**Nota de honestidade (quirk do FFmpeg, ex-paridade):** um clipe de **uma** cena com narração de amplitude
**exatamente zero** *e* `music=False` faz o encoder AAC falhar (`Error submitting audio frame … Invalid
argument`). Verifiquei que o **renderer legado falha identicamente** nessa mesma entrada (mesmo grafo de
mixagem, mesma geração de silêncio). Não é regressão e não alterei o grafo para "esconder" isso; o teste de
narração muda migrado usa 2 cenas (o caso real) e passa nos dois modos de música.

## Remoção do legado — lista exata

**Arquivos/trechos removidos:**
- **`renderer/app/studio/adapters/render_ffmpeg.py`** — arquivo inteiro (classe `FfmpegRenderer`, `static_overlay`,
  `caption_overlay`, `_LAYOUT`, `_wrap`, `_run`, `_scene_enable`, `_scene`, `_assemble`). O que era funcionalidade
  foi **movido** para `render_plan_ffmpeg.py` (overlays) ou já existia no compilador puro (grafo/mixagem);
  `_scene_enable` **deixou de existir** porque a janela semiaberta agora é gerada pelo compilador.
- **`renderer/app/studio/composition.py`** — troca de import/registro (2 linhas; ver acima).
- **`tests/test_render_adapters.py`** — migrado, não removido: `FfmpegRenderer("rich")` → `PlanFfmpegRenderer()`
  (5 usos), `asset_id` adicionado ao `spec_for` (o plano exige asset por cena), e o teste `_scene_enable`
  repontado para a janela semiaberta do `CompiledRender`. **Nenhuma asserção foi afrouxada ou apagada.**

**Decidi NÃO remover (com motivo):**
- **`renderer/app/rich.py` — intacto.** Apesar de o pedido sugerir remover "trechos duplicados do `rich.py`",
  **nada nele ficou morto**: `app/main.py` (rota `/videos`, modo *rich*) usa `synthesize_speech`,
  `build_narration_track`, `synth_music`, `make_overlay`, `render_scene`, `assemble`, `cover_image`,
  `placeholder_image`; `adapters/voice_piper.py` usa `synthesize_speech`/`wav_duration`; `test_rich.py` e
  `test_image_adapters.py` cobrem o módulo. O design **C3** declara a rota `/videos` (`rich.py`) **fora do
  escopo** da fundação. Remover qualquer função dele perderia funcionalidade do `/videos`. O
  `PlanFfmpegRenderer` **reusa** `rich.build_narration_track`/`synth_music`/`MUSIC_SR`/`FONT*`/`_wrap` — a
  duplicação real (o grafo de vídeo e a mixagem) foi eliminada reaproveitando o compilador.
- **`application/render_compiler.py` e `domain/render_plan_builder.py`** — não são legado; são o núcleo do
  caminho novo. Intactos.
- **Docstrings de `application/render_compiler.py` e `tests/test_render_compiler.py`** que citam
  `adapters/render_ffmpeg.py` como "a régua do §11" — referência **histórica**, sem import pendurado. Deixados
  para respeitar a restrição de não tocar o compilador (só correção mínima justificada).
- **`adapters/qa_ffmpeg.py`, `domain/render.evaluate_qa`** — é o QA técnico, não o renderer. Intactos.

## Validações reais (comandos)

Imagem `faceless-v2-hygiene-test-local:latest`, `PYTHONPATH=/workspace/renderer`, `-p no:cacheprovider`.
**Postgres próprio:** container `rp5-pg` na rede `rp5-net`, `--tmpfs /var/lib/postgresql/data`, prova de 64 hex
em `-v <dir>:/budget-test-proof:ro` (lida por `pg_read_file('/budget-test-proof/proof')` no container e conferida
localmente). As **duas** DSNs foram passadas (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

- **Paridade (script ad-hoc, não commitado):** JSON com os números da tabela acima → `passed=True` nos quatro
  casos (short/long × legado/plano). Script e work dir de depuração removidos.
- **Contagem nova:** `tests/test_render_plan_executor.py` = **13 testes** (10 sem FFmpeg por runner injetado + 3
  de paridade em clipe curto). `tests/test_render_adapters.py` segue com **16** (migrado). `tests/test_render_api.py`
  = **15** (passa pelo caminho novo agora — era o renderer legado).
- **Partição A (leve + banco):** `tests/test_architecture.py tests/test_contracts_snapshot.py tests/test_render_plan.py
  tests/test_render_plan_timeline.py tests/test_render_plan_builder.py tests/test_render_compiler.py tests/test_db.py
  tests/test_render.py` → **160 passed**.
- **Partição B (render com FFmpeg):** `tests/test_render_adapters.py tests/test_render_plan_executor.py
  tests/test_render_api.py` → **44 passed**. (`test_rich.py` + `test_render_repo.py` + `test_panel_production_render.py`
  → **41 passed**, conferindo o `rich.py` preservado e a composição.)
- **Gerador de contratos sem drift:** `scripts/export_contracts.py --check` → **exit 0** (dentro do container).
  Nenhum modelo do plano mudou → `contracts/` e `tests/test_contracts_snapshot.py` **intactos**.
- **Sem migração:** nenhuma tabela persistida nesta fatia → **`0032` NÃO foi criado** (sem tabela órfã) e
  `tests/test_db.py` ficou intacto.
- **Arquitetura:** `test_domain_has_no_outward_or_io_imports`, `test_application_only_imports_domain`,
  `test_render_core_has_no_media_or_provider_sdks` verdes — `subprocess`/PIL só no `adapters/`.
- **Higiene:** `python3 scripts/secret_hygiene.py scan` → `Secret hygiene check passed.` (exit 0).

**Memória:** clipes curtos (2 cenas, ≤ 3.7 s, 1080×1920), partições separadas, `rp5-pg` próprio. Nenhum
`ffmpeg … SIGKILL`/rc 137 observado nesta execução.

## O que ficou de fora / **o que NÃO está ligado**

- **fps 25 mantido** (decisão §5.2) — não mexi na timebase de saída nem recalibrei o QA.
- **Estilo estruturado adiado (RP-017/018, R4):** o plano construído aqui usa `style_snapshot` neutro
  (`style_id="studio-default"`, `version=1`), porque o `RenderSpec` do `RunRender` **não carrega** o perfil do
  canal. A ligação real com o `ChannelProfile` (RP-016) **não está ligada**.
- **Beats/multi-shot reais não estão ligados:** o plano do caminho de produção tem **um shot por cena** (R1/C4).
  O contrato e o compilador já hospedam multi-shot contíguo (testado), mas o **produtor de beats** é fatia
  posterior — o caminho E2E não produz multi-shot.
- **`plan_id`/`project_id` derivados de `video_id`:** o `RenderSpec` não tem `project_id`; o plano usa o
  `video_id` para os dois. Migração para os IDs reais vem junto com a construção do plano no `RunRender`.
- **Sem persistência do plano/manifesto** (RP-06) → **sem migração**, sem `plan_scene_costs`.
- **Agendamento de movimento:** o default materializa o ciclo `zoom_in/zoom_out/pan_right/pan_left` no plano
  (preserva o Ken Burns do legado de forma **explícita**, não `% 4` no compilador); um produtor de movimento
  por cena ainda não existe.
- **Retomada/idempotência fina:** o legado não tinha retomada (o `work/<job>` é descartável e limpo no fim);
  o novo caminho mantém isso. A "publicação atômica" evita `.mp4` parcial, mas não há render parcial/retomada
  no meio (RP-06).
