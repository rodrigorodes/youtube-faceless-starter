# RUN-02 — suíte no ambiente canônico (container)

- Data: 2026-11-25
- HEAD: f4a9244 (branch main)
- Árvore: dirty (WIP local de UX V4/V3, contratos gerados e este plano)
- Runner: `scripts/test-container.sh` (Docker; Python 3.12; Postgres 16 efêmero; ffmpeg com libass)
- Comando:
  ```
  scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q
  ```
- Resultado real (exit code 1):
  - 39 failed
  - 4019 passed
  - 20 skipped
  - 636.00 s
- Observação: a primeira execução do mesmo comando deu 40 failed / 4018 passed;
  uma falha não se repetiu na segunda execução (teste flaky ou dependente de ordem).
  O conjunto exato deve ser reconferido antes de qualquer conclusão por teste.

Nenhum cenário do plano foi promovido a PASS por este resultado: a suíte existente
não é o plano. Este registro é evidência de execução real da camada unit/mock/DB
no ambiente canônico.

## Categorias das falhas (triagem inicial)

| Categoria | Qtd. | Exemplos | Leitura inicial |
|---|---|---|---|
| A. Drift de UI/casca após o WIP V4/V3 | 32 | `test_panel_page.py`, `test_settings_sections.py`, `test_channels_page.py`, `test_video_style_api.py` | Asserções de texto/markup antigas (glifos na nav, `aside.side`, rótulos de Configurações, vazios) não batem com a casca atual. Decidir se o WIP está incompleto ou se os testes precisam acompanhar a mudança. |
| B. Artefatos gerados desatualizados | 3 | `test_contracts_snapshot.py`, `test_schema_docs.py`, `test_secrets_hygiene.py` | `project.schema.json` difere por `minimum: 0` vs `0.0` (provavelmente geração no host vs container); `docs/22-modelo-de-dados.md` e o snapshot extraído do starter dependem dos contratos. |
| C. Lista de migrações esperada desatualizada | 2 | `test_db.py::test_migrate_applies_once`, `test_failed_migration_rolls_back_and_is_not_recorded` | A árvore tem 7 migrações novas (0047–0053) além da lista esperada. |
| D. Fluxo de produção com banco | 2 | `test_production_flow_db.py` | Assertions de ações/eventos e de estágio indisponível. |

## Triagem

A triagem por grupo está em `RUN-03-triage.md`. Resumo: B, C e D eram artefatos de
teste desatualizados e foram corrigidos; A (32 falhas) é drift de teste do WIP V4/V3,
sem mudança de produto nesta sessão.

## O que este resultado não prova

- Não prova que as 39 falhas são bugs de produto: a árvore está dirty e o WIP de UI
  pode ter deixado testes e produto em estados diferentes.
- Não prova cobertura de fornecedores externos, publicação real ou avaliação humana.
- Não substitui a triagem por teste e a decisão de corrigir produto ou teste.

## Reprodução local (host)

O host macOS não é ambiente de teste válido (sem libass no ffmpeg Homebrew).
Com `python3 -m pytest tests --ignore=tests/e2e_full --ignore=tests/e2e_ux`:
- 19 failed, 3172 passed, 904 skipped.
- As 19 falhas são de render/subtitles por falta de libass; os mesmos arquivos
  passam no container: 74 passed, 1 skipped.
