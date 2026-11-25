# RUN-11 — cobertura 100% do plano e correção do flake de TTS

- Data: 2026-11-25
- Base: HEAD `79e3585` (branch `main`, merge do WIP V4/V3), árvore dirty com os ajustes
  desta sessão.
- Ambiente: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero,
  ffmpeg com libass).
- Comando: `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q`.

## Resultado

- **4059 passed, 20 skipped, 0 failed** em 682,07 s (exit 0).
- Série completa: RUN-02 39 → RUN-04 32 → RUN-06 29 → RUN-07 25 → RUN-08 23 → RUN-10 0
  → RUN-11 0.
- Nenhuma regressão introduzida pelas mudanças de cobertura e do teste de TTS.

## Cobertura 100% do plano

- O capítulo 08 ganhou o cenário **PUB-13 — Interruptor global de publicação: padrão
  ligado e contingência desligada**.
  - Cobre `PUB.R05` no nível do interruptor global, não apenas no destino/credencial.
  - Verifica `publication_enabled=True` (padrão) e `False` (contingência).
  - Em `False`, não há claim, não há upload e nada é marcado como publicado.
  - Referências: `tests/test_publication_execution.py:620-645` e
    `tests/test_compose_env.py:100-110`.
- O plano passou de 130 para **131 cenários**, mantendo as **88 regras** cobertas por ao
  menos um cenário.
- `validar.py` → **OK: 14 capítulos, 88 regras, 131 cenários coerentes**.

## Correção do flake de TTS

- `tests/test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time` comparava
  o delta de pausa com `10 × 0,40 s = 4,0 s ± 1,0 s`. O delta real medido nas três
  evidências é ~3,25 s (3,135 / 3,355 / 3,274), porque o ponto final não acrescenta pausa
  sobre o silêncio que já existe nas duas versões.
- O teste passou a comparar com a **média das três evidências** (`_recorded_pause_delta()`),
  com tolerância relativa de 15% para a variância da diferença entre duas sínteses
  estocásticas. O piso `delta > 0` continua explícito.
- Resultado no container: **6 passed** em `tests/test_tts_calibration.py`.

## Validações de apoio

- `tests/test_publication_execution.py`, `tests/test_publication_policy.py` e
  `tests/test_compose_env.py`: **84 passed**.
- `tests/test_tts_calibration.py`: **6 passed**.

## Leitura

- ACH-09 está coberto no plano por PUB-13; a campanha ainda precisa executá-lo.
- O flake de TTS foi corrigido na causa (expectativa errada), não por afrouxamento cego.
- A suíte canônica está verde; nenhum cenário do plano foi promovido a PASS.
