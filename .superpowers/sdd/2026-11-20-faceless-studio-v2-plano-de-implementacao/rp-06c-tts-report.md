# RP-06c — o TTS deixa de rodar para a cena intacta (última ponta do aceite da RP-06)

**Gap fechado:** a RP-06b provou o reúso do **vídeo** de uma cena intacta (contagem de FFmpeg),
mas o aceite literal da RP-029 ainda não valia para **narração**: *"alterar uma cena não exige
regenerar **narrações**, imagens ou vídeos de outras cenas."* O `RunRender` chamava
`voice.speak(scene.narration, wav)` para **toda** cena, mesmo quando o áudio era idêntico ao da
revisão anterior.

**Causa (medida):** o fingerprint do nó `narration:<scene>` (`domain/render_cache.py`) era
`(cue.source_ref, cue.duration_ticks)` + texto de legenda — e `duration_ticks` é **saída** do TTS.
Com a duração no hash, o acerto de cache só é decidível **depois** de sintetizar: o reúso era
possível na execução, nunca antes dela. Era a limitação declarada na RP-06b.

**Branch:** `feat/rp-06c-tts` · **Worktree:** `…/39a258/rp-06c-tts` · **Base:** `52b9f64`.
Nada escrito fora da worktree. Commits locais por caminho exato; **sem push e sem merge**.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `a57dc57` | RP-06c — narração decidida pela entrada; `RunRender` pula o TTS da cena intacta | `domain/render_cache.py`, `application/render.py`, `application/ports.py`, `domain/render_plan_builder.py`, `adapters/render_plan_ffmpeg.py`, `composition.py`, `tests/test_render_cache.py`, `tests/test_render_reuse.py` |
| este commit | relatório da fatia | `.superpowers/sdd/…/rp-06c-tts-report.md` |

## O que mudou (e onde)

| Camada | Arquivo | Mudança |
|---|---|---|
| `domain` | `domain/render_cache.py` | **Narração**: fingerprint passa a ser da **entrada** — texto (trechos de legenda) + voz (`source_ref`) + parâmetros de áudio — **sem** `duration_ticks`. Nova função pura `narration_fingerprint(texto, voz, params)`, usada pelo grafo **e** pelo `RunRender`. Fingerprint do **visual intacto**. |
| `application` | `application/render.py` | `RunRender` recebe `plans` (índice de cache) e consulta `plan:<video>` **antes** de sintetizar: fingerprint igual + WAV íntegro (hash conferido) ⇒ **reusa o WAV e pula o `speak`**. A duração da cena reusada é **medida do WAV** (`_wav_seconds`), nunca estimada. |
| `domain` | `domain/render_plan_builder.py` | `StoryboardScene.voice_id`; a fonte de voz do plano carrega `params={"voice": voice_id}` — a **identidade da voz** entra no fingerprint da narração. |
| `application` | `application/ports.py` | `RenderSpec.voice_id` (identidade da voz: nome+modelo) propagada ao executor. |
| `adapters` | `adapters/render_plan_ffmpeg.py` | `_build_plan` passa `voice_id=spec.voice_id` para o storyboard. |
| wiring | `composition.py` | injeta `PostgresRenderPlanRepository(connect)` no `RunRender` (mesmo índice da RP-06b). |

`api/panel*.py`, `application/channels_page.py`, `renderer/app/main.py`, `renderer/app/rich.py`,
`docs/` **intocados**. Nenhum arquivo fora dos caminhos acima foi escrito.

## Como o fingerprint da narração virou "da entrada"

`narration_fingerprint(texto, voz, params)` = `sha256(texto normalizado, ((voz, params_ordenados),))`.
A entrada são exatamente os fatores que mudam o áudio: **texto falado**, **voz** (nome+modelo, via
`source_ref`/`params`) e parâmetros. A **duração não entra** — é saída do TTS.

- No **grafo** (`plan_graph`), o texto vem dos trechos de legenda que o compilador queima e a voz
  vem do `source_ref` do cue + `params` da fonte de voz gerada (`GeneratedAudioSource`).
- No **`RunRender`** (sem plano), o texto vem de `split_chunks(scene.narration)` e a voz de
  `voice:{scene.id}` + `{"voice": voz}`. Como os trechos de legenda **são** `split_chunks` da
  narração (mesma função, mesmo `max_chars`), as duas decisões produzem o **mesmo hash** — provado
  por `tests/test_render_cache.py::test_plan_graph_uses_the_same_input_fingerprint_the_run_render_consults`.

Consequência: alongar a fala (só a duração muda) **não** invalida a narração; mudar o texto, a voz
ou um parâmetro de áudio invalida. É o que torna o reúso decidível **antes** de sintetizar.

## Como o `RunRender` reusa a narração sem regredir o plano

1. Por render, uma consulta `plans.entries("plan:<video>")` (não uma por cena).
2. Para cada cena, `_cached_narration`: compara `narration_fingerprint` da entrada com o
   fingerprint registrado no nó `narration:<scene>`; exige o arquivo existir e o `sha256` do WAV
   bater com `artifact_sha256`. Qualquer dúvida ⇒ sintetiza.
3. Acerto ⇒ `shutil.copyfile(cache_wav, work/speech_NNN.wav)` e **`speak` não é chamado**.
4. A duração da cena reusada é `_wav_seconds(wav)` — lida do **WAV reusado** (`wave.getnframes()/
   getframerate()`), nunca de `estimate_narration_durations` nem do retorno do TTS. `scene_length`
   é aplicado sobre ela, então o plano/timeline saem corretos.
5. O executor mantém o registro dos artefatos (RP-06b): WAV + `sha256` no `plan_artifacts` /
   `render_cache_entries`, agora sob o fingerprint de entrada. O `RunRender` só **lê** o índice.

## Prova obrigatória — arquivo:teste e o que conta

O `voice` é um stub que **conta cada `speak`**; o caminho de produção é `RunRender → PlanFfmpegRenderer`
(com `runner` FFmpeg stub, sem FFmpeg real).

| Teste (arquivo:teste) | O que conta / prova |
|---|---|
| `tests/test_render_reuse.py::test_changing_one_scene_does_not_speak_for_the_other_scene` | 1º render: `voice.calls == [A, B]`. Muda só a cena A ⇒ 2º render: `voice.calls == [A_reescrita]` — **`speak` NÃO é chamado para B** (WAV reusado) e **é** para A |
| `tests/test_render_reuse.py::test_a_corrupted_cached_narration_is_not_reused` | WAV de B do cache sobrescrito (hash divergente) ⇒ B **volta a sintetizar** (`TEXTS[1] in voice.calls`), além de A pela mudança de texto |
| `tests/test_render_reuse.py::test_a_reused_narration_takes_the_real_duration_from_the_reused_wav` | `voice` escreve um WAV de 1,7 s mas devolve 1,2 s. 1º render: `scene_seconds == [scene_length(1.2), …]`; 2º render reusa ⇒ `voice.calls == []` e `scene_seconds == [scene_length(1.7), …]` — a duração é a **real do WAV**, não o retorno do TTS |
| `tests/test_render_cache.py::test_narration_fingerprint_ignores_the_tts_duration_but_follows_the_text` | esticar a fala não muda o fingerprint da narração; reescrever o texto muda só o da cena editada |
| `tests/test_render_cache.py::test_changing_the_voice_invalidates_only_that_scene_narration` | trocar a voz invalida a narração da cena (identidade da voz no fingerprint) sem tocar na outra |
| `tests/test_render_cache.py::test_plan_graph_uses_the_same_input_fingerprint_the_run_render_consults` | o hash do grafo == o hash que o `RunRender` calcula da entrada (sem plano) |
| `tests/test_render_cache.py::test_narration_fingerprint_helper_follows_text_and_voice_over_whitespace` | normalização por espaço + sensibilidade a texto/voz/parâmetros |

**Como ficou provado que o TTS não roda para a cena intacta:** em
`test_changing_one_scene_does_not_speak_for_the_other_scene`, o `voice` stub registra os textos em
`voice.calls`; limpa-se a lista antes do 2º render e a asserção é `voice.calls == ["Primeira narração
totalmente reescrita."]` — ou seja, **só a cena A** foi sintetizada; B não aparece.

## Mutação (prova de que o reúso é load-bearing)

Duas mutações foram aplicadas e **revertidas** (arquivo voltou ao original):

1. `narration_reuse` default `True` → `False` (desliga o reúso): **2 falhas** — os testes
   `test_changing_one_scene_does_not_speak_for_the_other_scene` e
   `test_a_reused_narration_takes_the_real_duration_from_the_reused_wav`.
2. Remover a conferência `_sha256_file(path) != entry.artifact_sha256`: **1 falha** — o teste de
   corrupção (`test_a_corrupted_cached_narration_is_not_reused`).

Total: desligar o reúso (ou a integridade do WAV) derruba os testes correspondentes — as asserções
são load-bearing, não decorativas.

## O que continua fora (limites explícitos)

- **Imagens de outras cenas:** a etapa de mídia (`ProduceAssets`) já deduplica por `cache_key`; o
  caminho de render só as **consome**. Nada aqui muda isso — o aceite de *imagens* é da etapa de mídia.
- **Patch do MP4 final:** quando qualquer cena muda, `concat`/`final` são invalidados por dependência
  e a composição roda (o aceite admite). Só quando **nada** mudou o MP4 final vem do cache.
- **Cache em disco cresce por fingerprint** (`render-cache/<plan>/<kind>/<key>-<fp16>.wav`); sem GC
  (eviction é fatia futura, como na RP-06b).
- **Cenas silenciosas** (`speak` devolve 0): sem cue/legenda, o fingerprint não coincide com a
  entrada do `RunRender` ⇒ não reusa, apenas re-sintetiza (seguro, não otimizado).

## Validações reais (comandos)

Imagem `faceless-v2-hygiene-test-local:latest` (Python 3.12), `PYTHONPATH=/workspace/renderer`,
`-p no:cacheprovider`. **Postgres próprio:** container `rp6c-pg` na rede `rp6c-net`, `--tmpfs
/var/lib/postgresql/data`, prova de 64 hex montada em `-v <dir>:/budget-test-proof:ro` no banco e no
runner. As **duas** DSNs (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

```
docker run --rm --network rp6c-net \
  -v "$PWD":/workspace:ro -v "$PROOF_DIR":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@rp6c-pg:5432/postgres \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@rp6c-pg:5432/postgres \
  -w /workspace faceless-v2-hygiene-test-local:latest \
  python -m pytest -p no:cacheprovider <arquivos>
```

| Arquivo | Resultado |
|---|---|
| `tests/test_architecture.py` | 6 passed |
| `tests/test_render_cache.py` | 20 passed (**+4** novos) |
| `tests/test_render_regeneration.py` | 7 passed |
| `tests/test_render_reuse.py` | 5 passed (**+3** novos) |
| `tests/test_render_plan_repo.py` | 10 passed |
| `tests/test_render_plan_executor.py` | 17 passed |
| `tests/test_render.py` | 27 passed |
| `tests/test_render_api.py` | 15 passed |
| `tests/test_db.py` | 15 passed |
| `tests/test_composition.py` | 8 passed |
| `tests/test_narration_duration.py` | 19 passed |
| **Subtotal (lista exigida)** | **149 passed** |
| **Suíte completa (`tests/`)** | **2401 passed, 35 skipped** |
| `python scripts/export_contracts.py --check` | **EXIT 0** (nenhum contrato pydantic mudou; `RenderSpec`/`StoryboardScene` não são contratos versionados) |
| `python3 scripts/secret_hygiene.py scan` (com `.git` montado) | `Secret hygiene check passed.` (**EXIT 0**) |

**Testes novos: 7** (`test_render_reuse.py` **+3**, `test_render_cache.py` **+4**). Nenhuma asserção
existente foi afrouxada; nenhum teste existente precisou ser editado.

**Memória:** VM com 7,65 GB e outra fatia em paralelo (`rp6c-pg` isolado na `rp6c-net`). Clipes
curtos; nenhum `ffmpeg SIGKILL`/rc 137 observado.
