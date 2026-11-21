# Limpeza do legado do MVP — relatório

**Data:** 2026-11-21
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/limpeza-legado`
**Branch:** `feat/limpeza-legado` · **Base:** `8f051f7`
**Escopo autorizado pelo usuário:** "tudo que for obsoleto pode ser removido; mantemos só a versão nova,
com o padrão novo" (Faceless Studio V2: camadas `domain`/`application`/`adapters`, wiring em
`composition.py`, API em `studio/api/`).

Fatia paralela **RP-05** intocada: `renderer/app/rich.py` e
`renderer/app/studio/adapters/render_ffmpeg.py` não foram alterados.

---

## 1. Commits

| # | Commit | Conteúdo |
|---|--------|----------|
| 1 | `refactor(renderer): remove codigo do MVP legado de main.py (so a fachada do Studio)` | `renderer/app/main.py` |
| 2 | `test(main): prova de boot e /videos 410; remove test_providers.py do MVP` | `tests/test_main_boot.py` (novo), `git rm tests/test_providers.py` |
| 3 | `docs(limpeza-legado): relatorio da remocao + arquivo verbatim do que saiu` | este relatório + `archive/` |

Base usada para tudo: `8f051f7` (registrado em `archive/BASE_COMMIT.txt`).

---

## 2. O que foi removido

### 2.1 `tests/test_providers.py` (arquivo inteiro) — 285 linhas, 30 testes

**Evidência de que era morto:** o único import do arquivo é `from app import main` (linha 13) e
todas as 30 coletas exercitam símbolos do MVP (`main.generate_script`, `main.vertex_*`,
`main.call_provider`, `main.parse_storyboard_text`, `main.fetch_image`, …). Com os símbolos
removidos, o arquivo testaria nada. Nenhum outro arquivo o importa (busca por
`test_providers` + `from app import main`).

**Paridade antes de apagar (confirmada, nada real ficou sem cobertura):**

| Comportamento coberto no legado | Cobertura no caminho novo |
|---|---|
| seleção de provider/`demo` | registry de provedores em `composition.py` + `tests/test_provider_catalog.py`, `tests/test_provider_service.py`, `tests/test_composition.py` |
| `opencode` via bridge (Bearer, erros, timeout, sem vazar token) | `app/studio/adapters/text_opencode.py` + `tests/test_text_adapters.py` (bearer, `ModelUnavailable`, token não vaza) |
| parsing de JSON (cercas ```json, clamping, rejeição) | `app/studio/application/editorial.py::parse_scene_drafts` (superset: tolera cercas, valida 5–400/10–500, clampa caption/label, exige `claim_ids`) + `tests/test_editorial.py` (7× `ScriptRejected`), `tests/test_longform_editorial.py`, `tests/test_text_adapters.py` |
| prompt de roteiro (`build_prompt`/`build_storyboard_prompt`) | `editorial.build_prompt` + `tests/test_text_adapters.py::test_demo_text_output_is_a_valid_script_built_from_the_claims` |
| imagem por bridge (retry, placeholder, falha 502, sem vazar token) | `app/studio/adapters/image_opencode.py` + `image_placeholder.py` + `tests/test_image_adapters.py` (retry 5xx, timeout, `ModelUnavailable`, placeholder determinístico) |
| validação de request/limites (`VideoRequest`, `Scene`) | `app/studio/domain/contracts.py` + `tests/test_contracts.py`, `tests/test_editorial.py` |
| `vertex`/`gemini` (`AI_PROVIDER`) | **provider legado removido por decisão do produto**; o caminho novo de texto é `opencode`/`demo`. Não há adapter novo a portar — a funcionalidade foi substituída, não perdida em silêncio. |

### 2.2 `renderer/app/main.py` — caiu de 387 para 30 linhas (diff `+1/−355`; o restante é contexto inalterado)

Símbolos removidos. A coluna "refs externas" é o resultado de `grep -rn '\bsimbolo\b'` no repo
(excl. `.git`/`__pycache__`) **e** da varredura de AST (imports/calls) — ambas concordam.

| Símbolo | refs fora de `main.py` | Observação |
|---|---|---|
| `resolve_provider` | 0 | chamado só por `generate_content`/`generate_storyboard` (também removidos) |
| `parse_slides` | 0 | **já era inalcançável** (nenhuma chamada, nem dentro de `main.py`) |
| `parse_slides_text` | 0 | **já era inalcançável** |
| `parse_content_text` | 0 | usado só pelo bloco removido |
| `generate_with_opencode` | 0 | usado só por `call_provider`/`generate_with_opencode` chain |
| `parse_content_meta` | 0 | usado só por `parse_storyboard_text` |
| `build_rich` | 0 | usado só por `create_rich_video` |
| `create_rich_video` | 0 | **já era inalcançável** |
| `make_slide` | 0 | **já era inalcançável** |
| `DEMO_SLIDES` | 0 | usado só por `generate_content` |
| `wrap` | 0 | usado só por `make_slide` |
| `build_prompt`, `call_provider`, `generate_script`, `generate_content`, `generate_storyboard` | 0 (só `test_providers.py`) | bloco de provider legado |
| `build_storyboard_prompt`, `parse_storyboard_text` | 0 (só `test_providers.py`) | parsing legado |
| `vertex_endpoint`, `vertex_access_token`, `_vertex_credentials` | 0 (só `test_providers.py`) | provider Vertex legado |
| `post_json` | 0 (só `test_providers.py`, via monkeypatch) | helper HTTP do bloco |
| `fetch_image` | 0 (só `test_providers.py`) | imagem via bridge legado |
| `VideoRequest`, `Scene` | 0 (só `test_providers.py`) | modelos Pydantic do MVP |
| `IMAGE_STYLE` | 0 | símbolo de `main.py` (o `IMAGE_STYLE` de `studio/domain/media.py` é outro, e fica) |
| `OUTPUT`, `JOBS`, `FONT` | 0 | paths/fonte do MVP; `OUTPUT.mkdir`/`JOBS.mkdir` eram efeito de boot sem leitor |

Imports que ficaram órfãos e foram retirados: `base64`, `json`, `os`, `re`, `subprocess`, `uuid`,
`from pathlib import Path`, `import httpx`, `from fastapi.responses import FileResponse`,
`from PIL import Image, ImageDraw, ImageFont`, `from pydantic import BaseModel, Field, HttpUrl`,
`from . import rich`.

**Mantido (a fachada do Studio) em `renderer/app/main.py`:** `app = FastAPI(...)`, `lifespan`,
`/health`, `legacy_videos_removed` (rotas `/videos` e `/videos/{path:path}` → 410) e
`app.include_router(make_router(...))`. `asyncio`, `os` e `Path` saíram junto com os símbolos que os
usavam; `asyncio` **permanece** (usado pelo `lifespan`).

Diff verbatim arquivado em `archive/main.py.diff`.

---

## 3. O que foi decidido manter (e por quê)

| Item | Decisão | Motivo / evidência |
|---|---|---|
| `renderer/app/studio/adapters/image_placeholder.py` (`PlaceholderImage`) | **Manter** | É **fallback real do caminho novo**: registrado em `composition.py:284` (`register("image", "placeholder", PlaceholderImage)`), listado como provider no catálogo e consumido por `tests/test_image_adapters.py`, `test_media_api.py`, `test_provider_service.py`, `test_provider_catalog.py`, `test_editorial.py`, `test_channel_api.py`/`test_channel_secrets.py`. Não há `renderer/app/adapters/image_placeholder.py` nem `studio/app/adapters/image_placeholder.py` (caminhos citados na tarefa não existem). |
| `renderer/app/rich.py` | **Manter (não tocar)** | Ficheiro da RP-05; consumido pelo caminho novo em `adapters/render_ffmpeg.py` e `adapters/voice_piper.py` e por `tests/test_rich.py`. |
| `scripts/test-create.sh`, `scripts/test-create.ps1` | **Manter** | Apesar de postarem no antigo `/videos`, têm uso documentado: `README.md` e 5 docs; o critério "sem importador **nem uso**" não se aplica. Fica registado para uma higienização de docs futura. |
| `examples/*.json` (`ade-2026-publish.json`, `ade-2026-rich-publish.json`, `rich-smoke.json`) | **Manter** | Referenciados em `scripts/secret_hygiene.py` (allowlist) e em `docs/`; payloads de exemplo, não módulos mortos. |
| imports/env legados em `docker-compose.yml` (`AI_PROVIDER`, `GEMINI_*`, `VERTEX_*`, `IMAGE_PROVIDER`) | **Manter** | Fora do escopo de código desta fatia; agora não são lidos por `main.py`. Não removidos para não mexer em deploy/compose em paralelo à RP-05. |
| `docs/06-vertex-ai.md`, `docs/09-modo-rich-imagens-voz-musica.md`, etc. | **Manter** | Documentação do MVP antigo; não é código. Registado como dívida de documentação. |

---

## 4. Prova de boot

O `renderer/Dockerfile:16` roda `uvicorn app.main:app`. Prova de que ainda sobe, com o app novo:

```
boot ok: Faceless Renderer MVP | /health 200 {'status': 'ok', 'ffmpeg': True, 'studio_db': 'unavailable'}
/videos GET 410 {'detail': 'legacy unauthenticated endpoint removed; use /studio/panel or /studio/videos'}
/videos POST 410 {'detail': 'legacy unauthenticated endpoint removed; use /studio/panel or /studio/videos'}
```

Novo teste `tests/test_main_boot.py` (2 testes):
- importa `app.main:app` e faz `TestClient(app).get("/health")` → 200 (`status=ok`, `ffmpeg=true`,
  `studio_db` em `{ok, unavailable}`);
- prova que `/videos` (GET/POST/HEAD) e `/videos/{path:path}` respondem **410** com a mensagem de
  `legacy_videos_removed`.

---

## 5. Suíte de testes — antes/depois

Rodada em **partições** (8 grupos) na imagem `faceless-v2-hygiene-test-local`, com Postgres próprio
`limp-pg`/`limp-net`, as duas DSNs (`STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN`) e
`STUDIO_BUDGET_TEST_PROOF_FILE` (prova de 64 hex montada com `-v`).

| | arquivos de teste | passed | failed | skipped |
|---|---|---|---|---|
| **Antes** (base `8f051f7`) | 123 | **2332** | 0 | 35 |
| **Depois** (`feat/limpeza-legado`) | 123 | **2304** | 0 | 35 |

**Diferença = −28 testes**, explicada exatamente por:
- **−30**: `tests/test_providers.py` removido (27 `def test_*` + 1 `parametrize` de 4 casos = 30 coletas);
- **+2**: `tests/test_main_boot.py` adicionado.

Nenhuma falha nova: os 8 grupos fecharam verdes nos dois lados. `tests/test_architecture.py`
(6 testes) passou isoladamente (8 passed junto com o boot test).

> Nota de método: numa primeira rodada dentro do container, 2 testes de
> `tests/test_secrets_hygiene.py` falharam por a `.git` da worktree apontar para um gitdir absoluto
> do host não montado (`git rev-parse --show-toplevel` → 128). O baseline foi refeito montando
> `$MAIN` e o gitdir no container; com isso, **0 falhas** antes e depois. Não é regressão.

---

## 6. Higiene de segredos

```
$ python3 scripts/secret_hygiene.py scan
Secret hygiene check passed.   (rc=0)
```

Além disso, `tests/test_secrets_hygiene.py` passou inteiro na partição 7 (185 passed), incluindo o
empacotamento real do starter.

---

## 7. Arquivo verbatim (nada foi removido sem cópia)

Em `.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/`:

| Arquivo | sha256 | Origem |
|---|---|---|
| `main.py.orig` | `9e241a6be3c36dca3bab753a0a63b1ec9d45e8d58fde0fa41719560cb16235ee` | `renderer/app/main.py` em `8f051f7` |
| `test_providers.py.orig` | `9667fcfd73af0f17bd1f0bfc21e7405c1822a60d8441a401473ddba0ddb2ec48` | `tests/test_providers.py` em `8f051f7` |
| `main.py.diff` | — | diff unificado de `renderer/app/main.py` |
| `BASE_COMMIT.txt` | — | `8f051f7` |

Os hashes dos `.orig` batem com os blobs de `HEAD` (`git show 8f051f7:... | shasum -a 256`).

---

## 8. Reprodução

```bash
# boot
docker run --rm --network limp-net -v "$MAIN":"$MAIN" \
  -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git \
  -e PYTHONPATH="$MAIN/renderer" -w "$MAIN" --entrypoint python \
  faceless-v2-hygiene-test-local:latest -m pytest -q tests/test_main_boot.py tests/test_architecture.py

# suíte em partições (script: /private/var/folders/.../T/opencode/limp-suite.sh)
GRUPOS=8 ./limp-suite.sh

# higiene
python3 scripts/secret_hygiene.py scan
```

(Verificações fora do escopo/código: nada foi enviado (`push`) nem integrado (`merge`).)
