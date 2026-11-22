# S1/S2/S7 — saneamento de arquitetura do core: fechamento

**Data:** 22/11/2026. Implementado no worktree `ve-arch-saneamento` (branch `ve/arch-saneamento`)
e **portado para o checkout principal**. Nada commitado.

## S7 — guarda que falha primeiro (TDD)

`tests/test_architecture.py` ganhou uma guarda por **AST** (não regex cru) que proíbe nome de
fornecedor concreto no domínio, comparando **token exato** em minúsculas. Lista:
`opencode, piper, pexels, pixabay, elevenlabs, openai, anthropic, veo, capcut, fal, replicate,
stability, minimax, kling, runway`. Allowlist justificada: `youtube` e `google` (identidade do
produto em `domain/youtube_identity.py`). Docstrings são prosa e ficam de fora.

- **Falhou antes:** 3 ocorrências — `domain/panel.py:10` (`_KNOWN_FREE_PROVIDERS`) e
  `domain/narration_duration.py:40-41` (`MEASURED_VOICE`, `MEASURED_PIPER_VERSION`).
- **Passou depois:** sim, após S1 e após mover as constantes de calibração para
  `renderer/app/studio/tts_calibration.py` (ver "Correção de fronteira").
- **Load-bearing:** `test_supplier_name_guard_is_load_bearing` prova com `tmp_path` que string,
  constante e identificador são detectados e que "metadata"/"falcon" não geram falso positivo.

## S1 — domínio sem nome de fornecedor

`domain/panel.py` deixou de declarar `_KNOWN_FREE_PROVIDERS`. O conhecimento de "quem é
local/gratuito" passou para a raiz de composição (`composition.FREE_PROVIDERS =
{frozenset: placeholder, demo, piper, stock}`) e é **passado como parâmetro** a
`is_known_cost(provider, model, cost_usd, free_providers)` e a `cost_kind(...)`.

Comportamento observável preservado (conferido no container):
`placeholder/demo/piper/stock` com custo 0 → `True`; `opencode/openai/gpt-4o-mini` com 0 →
`False`; com 0.02 → `True`.

## S2 — aplicação sem nome de fornecedor

`application/render.py:354` gravava `model="ffmpeg"` fixo. Passou a usar `renderer.name` (o nome
declarado pelo renderer), sem literal de fornecedor na aplicação. O compilador de render plan
continua emitindo argumentos de linha de comando (S3, fora do escopo).

## Correção de fronteira (necessária para a guarda ficar verde)

`domain/narration_duration.py` tinha `MEASURED_VOICE = "piper:..."` e `MEASURED_PIPER_VERSION`
como constantes **sem uso no domínio** (só os testes de calibração as importavam). Foram movidas
para `renderer/app/studio/tts_calibration.py` (raiz do pacote, fora do domínio); o domínio
mantém só os números da regressão. `tests/test_tts_calibration.py` importa do novo módulo.
Nenhum comportamento mudou: os valores são os mesmos e nenhum código de produção os consome.

## Evidência real

- Focados no worktree de origem: **65 passed, 1 failed** — a única falha era a guarda S7 pelo
  vazamento de `narration_duration` (esperado, corrigido no port).
- Suíte completa no worktree: inválida por contenção (OOM/Postgres); contagens por blocos
  limpos: **7 failed, 3032 passed, 6 skipped** (as 7 são pré-existentes, incluindo a guarda nova).
- **Portado para o checkout principal:** `test_architecture.py test_panel_domain.py
  test_team_page.py test_quality.py` → **61 passed**; `test_tts_calibration.py -k punctuation`
  → **1 passed** (44 s).

## Achados registrados (não corrigidos)

1. **`application/config.py` ainda cita `ffmpeg`** nos `_DEFAULTS` de fornecedor — resíduo de S2
   (o default é dado de composição, mas está na camada de aplicação). Não foi alterado para não
   ampliar escopo; a guarda AST atual cobre só `domain/`.
2. **`application/render_compiler.py`** emite argumentos de linha de comando com `ffmpeg` (S3).
3. `test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time` falhou uma vez sob
   pressão de memória e passou isolado; flaky ambiental, não regressão.
