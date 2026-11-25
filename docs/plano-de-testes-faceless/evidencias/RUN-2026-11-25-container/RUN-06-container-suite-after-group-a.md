# RUN-06 — suíte canônica completa após as correções de A1/A4

- Data: 2026-11-25 (execução local, host com Docker).
- Base: HEAD `f4a9244` (branch `main`), árvore dirty (42 entradas no momento da execução).
- Ambiente: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero, ffmpeg com libass).
- Comando: `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q`.
- Resultado: **29 failed, 4029 passed, 20 skipped** (629 s, exit 1).

## Comparação com as execuções anteriores

| Execução | Falhas | Passados | Observação |
|---|---|---|---|
| RUN-02 | 39 | 4019 | antes da triagem de B/C/D |
| RUN-04 | 32 | 4026 | após B/C/D; todas as falhas restantes do grupo A |
| RUN-06 | **29** | **4029** | após as correções de A1 e A4 (só testes) |

A diferença de 3 falhas é exatamente o que A1 e A4 explicavam: 2 do grupo A4
(`test_panel_production_page.py`, fixture com `auto_research=False`) e 1 do grupo A1
(`test_analytics_page.py::test_page_is_reached_through_the_approved_shell`).

## Falhas restantes (29), por arquivo

| Arquivo | Falhas | Subclasse |
|---|---|---|
| `tests/test_panel_page.py` | 15 | A1 (3, agora em asserção posterior) + A2 (12) |
| `tests/test_settings_sections.py` | 3 | A2 |
| `tests/test_channels_page.py` | 3 | A2 (2) + A3 (1, OAuth) |
| `tests/test_video_style_api.py` | 3 | A2 (1) + A3 (2) |
| `tests/test_analytics_page.py` | 1 | A2 |
| `tests/test_panel_production_page.py` | 1 | A2 (bloco "Predefinição do canal", ACH-08) |
| `tests/test_script_page.py` | 1 | A2 |
| `tests/test_styles_page.py` | 1 | A2 |
| `tests/test_connections_page.py` | 1 | A2 |

Nenhuma falha restante foi confirmada como regressão de produto. A2 depende da aprovação
do WIP V4/V3; A3 depende de decisão de produto (ACH-04 a ACH-08).

## O que esta execução não prova

- Não promove nenhum cenário do plano a PASS. A suíte existente não é o plano.
- Não separa produto de WIP: a árvore está dirty e o WIP de UI pode ter deixado testes e
  produto em estados diferentes.
- Não cobre `tests/e2e_full` nem `tests/e2e_ux` (excluídos por padrão neste comando).
