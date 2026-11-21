# `rich-boundary` — fronteira rich.py ↔ domínio (fonte única do tempo de cena)

**Data:** 2026-11-21
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/rich-boundary`
**Branch:** `feat/rich-boundary` · **Base:** `d4ec5e6` (`docs(status): veredito final do main`)
**Escopo autorizado:** corrigir **um** defeito de fronteira — o helper de mídia
`renderer/app/rich.py` **recopia** constantes canônicas do domínio puro. Direção do fix:
adapter→domínio (o domínio é a cópia canônica; nada foi movido para o domínio).
Fatia paralela `provider-config` (`voice_piper.py`/`.env.example`/`compose`/`docs`) **não
tocada**; `git diff` fecha em **3 arquivos**.

---

## 1. Commits

| # | Commit | Conteúdo |
|---|--------|----------|
| 1 | `4d030f3` `refactor(rich): tempo de cena e params da trilha vem do dominio (fonte unica)` | `renderer/app/rich.py`, `renderer/app/studio/adapters/render_plan_ffmpeg.py`, `tests/test_rich.py` |
| 2 | `docs(rich-boundary): relatorio + arquivo verbatim` | este relatório + `archive/rich-boundary/` (`git add -f`) |

Base registrada em `archive/rich-boundary/BASE_COMMIT.txt` (`d4ec5e690202b2ba9729a12013a290f2f259a091`).

---

## 2. O defeito, medido

Os valores de tempo do alinhamento áudio↔vídeo existiam em **dois lugares**, com corpo
**byte-idêntico**:

| | `renderer/app/rich.py` (base) | `renderer/app/studio/domain/render.py` |
|---|---|---|
| FPS | `:16` `FPS = 25` | `:8` `FPS = 25` |
| LEAD/TAIL | `:17` `LEAD, TAIL = 0.30, 0.50` | `:10` `LEAD, TAIL = 0.30, 0.50` |
| scene_length | `:42` `math.ceil((LEAD + speech_seconds + TAIL) * FPS) / FPS` | `:20` **mesma expressão e mesma docstring** |

Eram cópias, não wrappers. Hoje os valores coincidem — **não havia bug**; o risco era
divergência futura silenciosa (áudio e vídeo desalinham sem erro). O consumidor de
produção real do `scene_length` é o do domínio (`application/render.py:205`,
`domain/render_plan_builder.py:196`); no `rich` ele só era alcançado internamente por
`build_narration_track`.

---

## 3. Tabela símbolo → onde era definido → consumidores → ação

| Símbolo | Onde era definido (base) | Consumidores (medidos) | Ação |
|---|---|---|---|
| `FPS` | **rich.py:16** e **domain/render.py:8** | domain: `render_plan_builder.py:64` (`DEFAULT_TICKS_PER_SECOND = FPS*1000`), `render_plan.py:95` (`fps_num`), `scene_length`; rich: indireto via `scene_length`; teste `test_rich` | **definição removida do rich**; importado de `app.studio.domain.render` (reexportado) |
| `LEAD`, `TAIL` | **rich.py:17** e **domain/render.py:10** | rich: `build_narration_track`; domain: `render_plan_builder.py:251`, `render_compiler.py:519`, `render_plan_ffmpeg.py:44`; testes | **definição removida do rich**; importados do domínio |
| `scene_length` | **rich.py:42** e **domain/render.py:20** | produção: `rich.build_narration_track` (interno); domain: `application/render.py:205`, `render_plan_builder.py:196`; testes | **def removida do rich**; importada do domínio (reexportada). Sem wrapper morto. Teste passou a exercitar a **canônica** |
| `synth_music(bpm=122)` | **rich.py:69** (default) + **adapter fallback `122`** (`render_plan_ffmpeg.py:518`) | produção: `render_plan_ffmpeg.py:518` | default vira `DEFAULT_MUSIC_PARAMS["bpm"]`; fallback do adapter vira `DEFAULT_MUSIC_PARAMS["bpm"]` |
| `synth_music` seed (**`default_rng(7)` hardcoded**) | **rich.py:74** | produção: corpo do `synth_music`; o plano **documentava** `seed 7` em `DEFAULT_MUSIC_PARAMS` | vira **parâmetro `seed`**, default `DEFAULT_MUSIC_PARAMS["seed"]`; adapter passa o seed do plano |
| `MUSIC_SR` | **rich.py:20** (único) | rich: `synth_music`; adapter: `_write_silence(rate=rich.MUSIC_SR)` | **sem mudança** — já era fonte única (adapter deriva) |
| `FONT`/`FONT_BOLD`/`_wrap` | rich.py (único) | `render_plan_ffmpeg.py:49`/`:69` (derivam) | **sem mudança** — já fonte única |
| `synthesize_speech`/`wav_duration`/`_voice` | rich.py (único) | `voice_piper.py:23`/`:28`; testes | **intocados** (item 5) |

`rich.py`: **140 → 145 linhas** (+5: docstring explica a fonte canônica, imports e o
parâmetro `seed`). Nada de `synth_music`/`build_narration_track`/`synthesize_speech`/
`wav_duration`/`_voice`/`FONT`/`FONT_BOLD`/`_wrap`/`MUSIC_SR` foi removido.

---

## 4. Prova de fonte única

Um único ponto de definição (grep `verbo` em `archive/rich-boundary/single-source-grep.txt`):

```
$ grep -rnE '^\s*(FPS|LEAD|TAIL)\s*(,|:|=)' --include=*.py . | grep -v .superpowers
./renderer/app/studio/domain/render.py:8:FPS = 25
./renderer/app/studio/domain/render.py:10:LEAD, TAIL = 0.30, 0.50  # silêncio antes/depois de cada fala (s)

$ grep -rnE '^\s*def scene_length' --include=*.py . | grep -v .superpowers
./renderer/app/studio/domain/render.py:20:def scene_length(speech_seconds: float) -> float:
```

No nível de objeto, `rich` reexporta **o mesmo objeto** do domínio (não uma cópia):
`rich.scene_length is domain_render.scene_length -> True`. Isso está travado por um teste
novo (`tests/test_rich.py::test_rich_reexports_the_canonical_timing_and_music_constants`):
se alguém reintroduzir `FPS`/`LEAD`/`TAIL`/`scene_length` no `rich`, a identidade falha;
e os defaults do `synth_music` têm de continuar iguais a `DEFAULT_MUSIC_PARAMS`.

---

## 5. Mutação (prova de que é a mesma fonte)

Numa **cópia descartável** (`cp -R renderer`), mutando **só o domínio** e deixando o
`rich.py` intocado (raw em `archive/rich-boundary/mutation-proof.txt`):

| Estado (só no domínio) | `rich.FPS` | `rich.LEAD` | `rich.scene_length(1.23)` |
|---|---|---|---|
| base (`FPS=25`, `LEAD=0.30`) | 25 | 0.3 | 2.04 |
| `FPS = 30` | **30** | 0.3 | **2.0333…** |
| e `LEAD, TAIL = 0.10, 0.50` | 30 | **0.1** | **1.8333…** |

O valor usado pelo `rich` **muda junto** com o domínio → é a mesma fonte. Cópia removida;
a árvore real nunca foi tocada.

---

## 6. Outras duplicações no mesmo espírito (item 4) e decisão

- **`MUSIC_SR`** — **fonte única já existente**: definido só em `rich.py:20`; o adapter
  **deriva** (`render_plan_ffmpeg.py:158`, `rate: int = rich.MUSIC_SR`). Nenhuma ação.
- **Parâmetros da trilha (bpm/seed)** — **não era "só comentário"**: além do comentário em
  `render_plan_builder.py:67`, a linha 68 é dado real (`DEFAULT_MUSIC_PARAMS = {"bpm":122,
  "seed":7}`) que **entra no plano** (`GeneratedAudioSource.params`) e alimenta o
  fingerprint de cache (RP-06). Havia acoplamento e **divergência latente**:
  `rich.synth_music` **ignorava** o `seed` (usava `default_rng(7)` fixo) e o adapter
  **recopiava** o fallback `122`. **Alinhei**: (a) `synth_music` recebe e honra `seed`;
  (b) o adapter passa `bpm`/`seed` do plano com fallback em `DEFAULT_MUSIC_PARAMS`. Assim o
  que o plano documenta **é** o que a síntese executa, e o fingerprint não dessincroniza do
  áudio. Determinismo preservado (o builder usa `seed 7`, o pipeline passa 7 → bytes
  idênticos aos de antes).

---

## 7. Testes — antes/depois

Infra: imagem `faceless-v2-hygiene-test-local:latest`, Postgres próprio **`rb-pg`** na rede
**`rb-net`**, com **as duas** DSNs (`STUDIO_TEST_DSN` e `STUDIO_BUDGET_DISPOSABLE_DSN`) e
`STUDIO_BUDGET_TEST_PROOF_FILE` (prova de 64 hex montada com `-v` — também no servidor,
onde o `conftest` faz `pg_read_file('/budget-test-proof/proof')`). `-p no:cacheprovider`.
FFmpeg e Piper são reais.

### 7.1 Lista exigida (7 arquivos)

`tests/test_rich.py`, `test_render_plan_executor.py`, `test_render_adapters.py`,
`test_render.py`, `test_tts_calibration.py`, `test_narration_duration.py`,
`test_architecture.py`:

| | passed | failed |
|---|---|---|
| antes (`d4ec5e6`) | **96** | 0 |
| depois (`4d030f3`) | **97** | 0 |

(Δ = **+1**, o teste de fonte única novo. Logs: `focused-before.txt`, `focused-after.txt`.)

**Falha qualificada (não é regressão):** numa primeira rodada do "depois" o teste
**limítrofe** `test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time`
falhou (`delta = 2.81` contra `4.0 ± 1.0`; raw em `focused-after-run-flake.txt`). É a
mesma flutuação já documentada no `rich-sweep-report.md` (faixa medida 2.88–3.24). O teste
**não importa `rich`**: carrega `piper.PiperVoice.load` e sintetiza direto. Passou na
re-rodada (97 passed) e a suíte completa fechou 0 failed nos dois lados.

### 7.2 Suíte completa em 8 partições

| rodada | passed | failed | skipped | grupos verdes |
|---|---|---|---|---|
| **Antes** `d4ec5e6` | **2403** | 0 | 35 | 8/8 |
| **Depois** `4d030f3` | **2404** | 0 | 35 | 8/8 |

Diferença = **+1 passed** (`test_rich.py`, grupo 7: 210→211). **0 falhas novas.**
Por grupo antes/depois: 370·199·382·418·386·269·**210→211**·169. Logs:
`rb-before-suite.log`, `rb-after-suite.log`.

### 7.3 Boot e `/health`

`python -c "import app.main"` → **OK** (prova de ausência de ciclo: `domain` não alcança
`app.rich`). `tests/test_main_boot.py` → **2 passed**, incluindo `GET /health`
(`status=ok`, `ffmpeg=true`, `studio_db ∈ {ok, unavailable}`). Raw em
`archive/rich-boundary/boot-import.txt`.

Não há import circular por construção: `app.studio.domain.render` só importa `.contracts`
(puro, sem I/O) e `domain` é proibido de importar mídia/IO pelo `test_architecture.py`;
`rich` é folha em relação ao domínio.

### 7.4 Higiene de segredos

```
$ python3 scripts/secret_hygiene.py scan
Secret hygiene check passed.   (rc=0)
```

(re-executado após o commit, sobre os arquivos já rastreados — `secret-hygiene.txt`.)

---

## 8. Arquivo verbatim (nada saiu sem cópia)

Em `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/rich-boundary/`
(`git add -f`):

| Arquivo | sha256 | Origem |
|---|---|---|
| `rich.py.orig` | `d33e3cdf…62` | `renderer/app/rich.py` em `d4ec5e6` |
| `render_plan_ffmpeg.py.orig` | `880e8311…4f` | `renderer/app/studio/adapters/render_plan_ffmpeg.py` em `d4ec5e6` |
| `test_rich.py.orig` | `f55b0538…0f` | `tests/test_rich.py` em `d4ec5e6` |
| `rich-boundary.diff` | `271094b0…d6` | diff unificado dos 3 arquivos |
| `single-source-grep.txt` | — | grep de definição (`FPS`/`LEAD`/`TAIL`/`scene_length`) |
| `mutation-proof.txt` | — | mutação no domínio (cópia descartável) |
| `boot-import.txt` | — | `import app.main`, identidade de objeto, `test_main_boot.py` |
| `focused-before.txt` / `focused-after.txt` | — | lista exigida (7 arquivos) |
| `focused-after-run-flake.txt` | — | a rodada com o teste limítrofe flutuante |
| `rb-before-suite.log` / `rb-after-suite.log` | — | suíte completa em 8 partições |
| `secret-hygiene.txt` | — | `scripts/secret_hygiene.py scan` |
| `BASE_COMMIT.txt` | — | `d4ec5e6` |

Os `.orig` batem byte-a-byte com os blobs de `HEAD` (`git show d4ec5e6:<path> | shasum -a 256`).

---

## 9. Reprodução

```bash
MAIN=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/rich-boundary
PROOFDIR=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rb-proof   # prova de 64 hex
GITDIR=/Users/rodrigomendes/youtube-faceless-starter/.git

docker network create rb-net
docker run -d --name rb-pg --network rb-net -v "$PROOFDIR":/budget-test-proof:ro \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=postgres postgres:16-alpine

# prova de fonte única + boot
cd "$MAIN"
grep -rnE '^\s*(FPS|LEAD|TAIL)\s*(,|:|=)' --include=*.py . | grep -v .superpowers
docker run --rm --network rb-net -v "$MAIN":"$MAIN" -v "$GITDIR":"$GITDIR" \
  -v "$PROOFDIR":/budget-test-proof:ro -e PYTHONPATH="$MAIN/renderer" -w "$MAIN" \
  --entrypoint python faceless-v2-hygiene-test-local:latest -c "import app.main; print('OK')"

# lista exigida
docker run --rm --network rb-net -v "$MAIN":"$MAIN" -v "$GITDIR":"$GITDIR" \
  -v "$PROOFDIR":/budget-test-proof:ro -e PYTHONPATH="$MAIN/renderer" \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@rb-pg:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@rb-pg:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w "$MAIN" \
  --entrypoint python faceless-v2-hygiene-test-local:latest \
  -m pytest -q -p no:cacheprovider tests/test_rich.py tests/test_render_plan_executor.py \
  tests/test_render_adapters.py tests/test_render.py tests/test_tts_calibration.py \
  tests/test_narration_duration.py tests/test_architecture.py

# suíte completa em partições
GRUPOS=8 bash /private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/rb-suite.sh

# higiene
python3 scripts/secret_hygiene.py scan
```

---

## 10. Limitações e notas

- O `rb-pg` foi criado uma vez e reutilizado nas duas rodadas (o `conftest` dropa o schema
  `studio` a cada teste de banco, e o container é descartável/sem volume). A rodada
  "antes" e a "depois" correram na mesma janela de relógio; a fatia paralela
  `provider-config` também rodava (memória da VM apertada — as partições esperam folga).
- A mudança é **comportamento-preservador** por medição: `FPS`/`LEAD`/`TAIL`/`scene_length`
  passam a apontar para os mesmos valores do domínio, e o `seed` executado continua 7
  (o builder não mudou). Nenhum número da suíte caiu; o único movimento foi `+1` teste.
- Nada foi enviado (`push`) nem integrado (`merge`). Nenhum segredo foi impresso.
