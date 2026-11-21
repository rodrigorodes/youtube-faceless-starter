# `renderer/app/rich.py` — varredura final do que morreu com o renderer legado

**Data:** 2026-11-21
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/rich-sweep`
**Branch:** `feat/rich-sweep` · **Base:** `7fdb607`
**Escopo autorizado pelo usuário:** remover o obsoleto do `rich.py` e manter só o padrão novo
(o caminho baseado em Render Plan). Fatia paralela de **QA** (`application/render.py`,
`adapters/postgres/repo.py`, `publish_repo.py`) **não tocada**: `git diff --stat` fecha com
**3 arquivos** (`renderer/app/rich.py`, `tests/test_rich.py`, `tests/test_render_plan_executor.py`).
`adapters/render_plan_ffmpeg.py` e `adapters/voice_piper.py` (consumidores) foram **só lidos**.

---

## 1. Commits

| # | Commit | Conteúdo |
|---|--------|----------|
| 1 | `refactor(rich): remove o renderer legado (imagem/vídeo) — fica o áudio e o _wrap` | `renderer/app/rich.py` |
| 2 | `test(rich): tira os testes do comportamento extinto e porta o overlay para o executor` | `tests/test_rich.py`, `tests/test_render_plan_executor.py` |
| 3 | `docs(rich-sweep): relatorio da varredura + arquivo verbatim do que saiu` | este relatório + `archive/` |

Base registrada em `archive/BASE_COMMIT_rich-sweep.txt` (`7fdb607`).

---

## 2. Método da decisão (não removi no escuro)

Para **cada** símbolo de `rich.py` cruzei três fontes:

1. `grep -rn '\brich\.<nome>\b'` no repo inteiro (excl. `.git`/`__pycache__`/`.superpowers`);
2. varredura de **AST** (script próprio): `rich.<nome>` em qualquer `.py` **e** `from … import rich`;
3. `calls` **internas** dentro do próprio `rich.py` (um símbolo pode ser usado por outro que fica).

As três concordaram. A varredura de AST é a base da tabela abaixo.
**Descoberta que corrigiu o levantamento recebido:** `scene_length` **não** é órfão — é
chamado internamente por `build_narration_track` (que fica), então é **vivo** (idem `FPS`, que só
existe por causa de `scene_length`).

---

## 3. Tabela símbolo → consumidores encontrados → ação

| Símbolo | Consumidor(es) encontrado(s) | Ação |
|---|---|---|
| `W`, `H` | só `cover_image`/`placeholder_image`/`make_overlay`/`render_scene` (todos removidos) e os testes desses | **removido** |
| `FPS` | interno: `scene_length` (fica); teste `test_rich` | **mantido** |
| `LEAD`, `TAIL` | interno: `scene_length`, `build_narration_track`; teste `test_rich` | **mantido** |
| `FADE` | interno: só `render_scene` (removido) | **removido** |
| `FONT` | `render_plan_ffmpeg.py:49` (`FONT = rich.FONT`) | **mantido** |
| `FONT_BOLD` | `render_plan_ffmpeg.py:49` | **mantido** |
| `MUSIC_SR` | interno: `synth_music`; `render_plan_ffmpeg.py:158`; teste `test_rich` | **mantido** |
| `_voice` | interno: `synthesize_speech` (cache global do Piper; citado no comentário de `voice_piper`) | **mantido** |
| `synthesize_speech` | `voice_piper.py:23`; `test_image_adapters.py` (monkeypatch) | **mantido** |
| `wav_duration` | interno: `synthesize_speech`; `voice_piper.py:28`; teste `test_rich` | **mantido** |
| `scene_length` | interno: `build_narration_track`; teste `test_rich` | **mantido** |
| `build_narration_track` | `render_plan_ffmpeg.py:439`; teste `test_rich` | **mantido** |
| `synth_music` | `render_plan_ffmpeg.py:508`; `render_plan_builder.py:67` (comentário do contrato da trilha); teste `test_rich` | **mantido** |
| `_wrap` | `render_plan_ffmpeg.py:69` (`rich._wrap`) | **mantido** (byte-idêntico; só mudou de seção) |
| `cover_image` | só `test_rich.py:61` (comportamento extinto: o *fit* agora é `scale=…:flags=lanczos` no FFmpeg) | **removido** (+ teste removido) |
| `placeholder_image` | **nenhum** (nem teste) | **removido** |
| `make_overlay` | só `test_rich.py:48` (substituído por `static_overlay`/`caption_overlay`) | **removido** (+ teste **portado**) |
| `_run` | interno: `render_scene`, `assemble` (removidos) | **removido** |
| `render_scene` | nenhum | **removido** |
| `assemble` | nenhum | **removido** |

**Imports órfãos** retirados junto: `io`, `subprocess`, `from pathlib import Path` e todo o
`from PIL import Image, ImageDraw, ImageFont, ImageOps` (nada de PIL sobrou em `rich.py`).
Restaram `math`, `os`, `wave`, `numpy` — usados por `scene_length`, `synthesize_speech`,
`build_narration_track` e `synth_music`.

`rich.py`: **225 → 140 linhas** (diff `+7 −92`; os símbolos que ficaram não mudaram de conteúdo,
`_wrap` continua byte-idêntico ao base).

---

## 4. O que decidi manter e por quê

- **Voz do produto (Piper `pt_BR-faber-medium`):** `synthesize_speech`, `wav_duration`, `_voice`.
  Consumidos por `voice_piper.py` (import **tardio**, dentro de `speak()`) e por
  `test_image_adapters.py` (via monkeypatch de `rich.synthesize_speech`). O erro de removê-los só
  apareceria em runtime de voz — por isso cheguei nos consumidores de comentário/import indireto.
- **Áudio do plano:** `synth_music`, `build_narration_track`, `MUSIC_SR` — consumidos por
  `adapters/render_plan_ffmpeg.py` (`_write_music`/`_narration_inputs`/`_write_silence`).
- **Fontes e quebra de texto:** `FONT`, `FONT_BOLD`, `_wrap` — o executor do plano monta os
  overlays com Pillow e usa `rich.FONT`/`rich.FONT_BOLD` (linha 49) e `rich._wrap` (linha 69).
  A legenda/disclosure não morreram: mudaram de casa (de `rich.make_overlay` para
  `static_overlay`/`caption_overlay` em `render_plan_ffmpeg.py`).
- **Tempo de cena:** `scene_length`, `FPS`, `LEAD`, `TAIL` — `scene_length` é reusado por
  `build_narration_track` para casar áudio e vídeo em quadros inteiros (e segue exercitado por
  `test_rich.py`). O `scene_length`/`FPS` de `domain/render.py` é outro módulo e não foi tocado.

### Porte de teste (comportamento que ainda vale)

`test_overlay_has_transparency_and_text` cobria a **transparência** do PNG de overlay e a
**área inferior livre da UI dos Shorts** — invariantes que continuam valendo em
`static_overlay`/`caption_overlay`, mas não tinham cobertura no caminho novo (só a existência dos
PNGs e a legenda queimada eram testadas). Em vez de apagar, **portei** para o consumidor novo em
`tests/test_render_plan_executor.py::test_materialized_overlays_are_transparent_and_keep_the_shorts_ui_area_free`.
Já `test_cover_image_fills_frame` cobria `cover_image`, cujo comportamento virou filtro FFmpeg e
**já é coberto** ponta-a-ponta por
`test_render_adapters.py::test_renders_mp4_with_audio_video_and_the_format_size` (resolução do MP4
== `SIZE[fmt]`); não havia o que portar sem duplicar.

---

## 5. Testes exigidos

Rodados na imagem `faceless-v2-hygiene-test-local:latest`, Postgres próprio `rich-pg`/`rich-net`,
com as **duas** DSNs (`STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN`) e
`STUDIO_BUDGET_TEST_PROOF_FILE` (prova de 64 hex **montada no próprio servidor** —
`pg_read_file('/budget-test-proof/proof')` — e no runner). `-p no:cacheprovider`.
Ffmpeg e Piper/Piper-voice são **reais** (sem stub que mascare): a lista abaixo passa pelos testes
de paridade de `test_render_adapters.py`/`test_render_plan_executor.py` e pela calibração de voz.

```
tests/test_rich.py tests/test_render_plan_executor.py tests/test_render_adapters.py
tests/test_render.py tests/test_tts_calibration.py tests/test_narration_duration.py
tests/test_architecture.py tests/test_db.py
```

| | passed | failed |
|---|---|---|
| antes (base `7fdb607`) | **111** | 0 |
| depois (`feat/rich-sweep`) | **110** | 0 |

(−2 removidos + 1 portado = −1.)

---

## 6. Suíte completa em 8 partições — antes/depois

Duas rodadas na **mesma janela de relógio** (para comparar de forma honesta), cada uma com
`rich-pg` recriado do zero.

| rodada | passed | failed | skipped | grupos verdes |
|---|---|---|---|---|
| **Antes** — base `7fdb607` @ 12:09Z | **2400** | 1 | 35 | 7/8 |
| **Depois** — `feat/rich-sweep` @ 12:16Z | **2399** | 1 | 35 | 7/8 |

A **única** falha é **a mesma nos dois lados**:
`tests/test_channel_api.py::test_youtube_association_never_returns_tokens` — **0 falhas novas**.

**Diferença = −1 passed**, explicada exatamente por:
- **−2**: removidos `test_rich.py::test_overlay_has_transparency_and_text` e
  `test_rich.py::test_cover_image_fills_frame` (funções que deixaram de existir);
- **+1**: `test_render_plan_executor.py::test_materialized_overlays_are_transparent_and_keep_the_shorts_ui_area_free`.

Por grupo (determinístico): 370·199·382·418·384·**267→268**·**212→210**·169.

### Falsas falhas qualificadas (nenhuma é regressão)

1. **`test_youtube_association_never_returns_tokens` (bomba-relógio):** o payload fixa
   `token_expires_at = "2026-11-21T12:00:00+00:00"`. Meu relógio já passou disso, então o `GET`
   deriva `oauth_status=EXPIRED`/`connected=False`. Reproduzi a causa com um probe
   (`PUT` → linha `CONNECTED` no banco; `GET` → `EXPIRED` porque `now > expires_at`); o mesmo teste
   **falha igual na base** e numa base com banco recém-criado. Não tem relação com `rich.py`.
   De manhã, com o relógio antes de 12:00Z, a suíte fechou **2401 passed / 0 failed / 35 skipped**.
2. **`test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time` (limítrofe):** mede a
   diferença real de duração entre prosa pontuada e sem pontuação e exige
   `delta ≈ 4.0 ± 1.0`. A síntese do Piper varia e o `delta` fica em ~2.88–3.24 — na borda de 3.0.
   Provei com um probe de 6 repetições na **mesma árvore** e na **base** (faixas sobrepostas; a
   base sorteou 3.05–3.17, o `feat/rich-sweep` sorteou 2.88–3.24). O teste **não** depende de
   `rich.py` (sintetiza com `piper.PiperVoice.load` direto). Não falhou na rodada final "depois".

Nada foi enviado (`push`) nem integrado (`merge`).

---

## 7. Higiene de segredos

```
$ python3 scripts/secret_hygiene.py scan
Secret hygiene check passed.   (rc=0)
```

---

## 8. Arquivo verbatim (nada saiu sem cópia)

Em `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/`
(`git add -f`):

| Arquivo | sha256 | Origem |
|---|---|---|
| `rich.py.orig` | `258c282a178fa4f8af149bb047075f8cdad626435a7f2bc16ad6177c9883bdb7` | `renderer/app/rich.py` em `7fdb607` |
| `test_rich.py.orig` | `daaf202572ecf0be2c662fd70fe7ca25209867e764080772d9ffd7af5ffe3f99` | `tests/test_rich.py` em `7fdb607` |
| `test_render_plan_executor.py.orig` | `1940e4d3586cec5b7a5747bac0c915a52111b79660188c949a91947d5fbb2f62` | `tests/test_render_plan_executor.py` em `7fdb607` |
| `rich.py.diff` | — | diff unificado do `rich.py` |
| `tests_rich_and_executor.diff` | — | diff dos dois arquivos de teste |
| `BASE_COMMIT_rich-sweep.txt` | — | `7fdb607` |

Os `.orig` batem byte-a-byte com os blobs de `HEAD` (`git show 7fdb607:<path> | shasum -a 256`).

---

## 9. Reprodução

```bash
MAIN=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/rich-sweep
PROOF=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rich-proof   # prova de 64 hex
GITDIR=/Users/rodrigomendes/youtube-faceless-starter/.git

# Postgres próprio com a prova também NO SERVIDOR (pg_read_file)
docker network create rich-net
docker run -d --name rich-pg --network rich-net -v "$PROOF":/budget-test-proof:ro \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=postgres postgres:16-alpine

# testes exigidos
docker run --rm --network rich-net -v "$MAIN":"$MAIN" -v "$GITDIR":"$GITDIR" \
  -v "$PROOF":/budget-test-proof:ro -e PYTHONPATH="$MAIN/renderer" \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@rich-pg:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@rich-pg:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w "$MAIN" \
  --entrypoint python faceless-v2-hygiene-test-local:latest \
  -m pytest -q -p no:cacheprovider tests/test_rich.py tests/test_render_plan_executor.py \
  tests/test_render_adapters.py tests/test_render.py tests/test_tts_calibration.py \
  tests/test_narration_duration.py tests/test_architecture.py tests/test_db.py

# suíte em partições (script: /private/var/folders/.../T/opencode/rich-suite.sh)
GRUPOS=8 bash /private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rich-suite.sh

# higiene
python3 scripts/secret_hygiene.py scan
```
