# Registro de testes

Resultados informados na revisão anterior (V3): 89 testes Core/workflows e 43 UX V3 passaram;
não constituem certificação operacional. Ambiente: Python 3.11.9, pytest 8.2.0, pydantic 2.5.0
(pin do projeto: 2.11.4), sem FFmpeg no host, Docker disponível.

## Baseline da F00 (HEAD `e254b61`, sem mudanças de runtime)

| Fase/tarefa | HEAD | Ambiente | Comando | Pass/fail/skip | Artefato |
|---|---|---|---|---|---|
| F00.T03 | `e254b61` | host, sem banco | `pytest tests/test_channel_budget.py tests/test_provider_catalog.py tests/test_saas_domain.py tests/test_workflow_publish.py tests/test_workflow_analytics.py tests/test_workflow_trends.py -q` | **89 passed** (2,66 s) | — |
| F00.T03 | `e254b61` | host, sem banco | `pytest tests/test_home_v3.py tests/test_new_video_v3.py tests/test_videos_v3.py tests/test_trends_v3.py tests/test_analytics_v3.py tests/test_ux_contract.py -q` | **43 passed** (0,29 s) | — |
| F00.T03 | `e254b61` | PostgreSQL 16 descartável (prova privada) | `pytest tests/test_budget_reservations.py -q` | **35 passed** (18,4 s) | guard do conftest exercitado |
| F00.T03 | `e254b61` | PostgreSQL descartável | `pytest tests -q` | **2625 passed, 63 failed, 58 skipped** (400 s) | falhas classificadas em [pre-existing-failures](pre-existing-failures.md) |
| F00.T04 | `e254b61` | host | `python3 scripts/secret_hygiene.py scan` | **passe** | sem segredo no repositório/pacote |

As 63 falhas **não** são regressões desta fase: 42 são testes de tela desatualizados após o
port V3, 17 dependem de FFmpeg ausente no host, 2 são o contrato gerado com outra versão de
pydantic e 2 são sensíveis à ordem (passam isolados). Detalhe e reprodução no documento citado.

## F02 — Fundação de Settings (HEAD `e254b61` + mudanças não commitadas)

| Tarefa | Arquivos de teste | Resultado |
|---|---|---|
| F02.T02 estilo real no Create | `tests/test_new_video_v3.py`, `tests/test_video_style_api.py`, `tests/test_ports.py` | 13 + 24 + 7 **pass** |
| F02.T01 canal ativo | `tests/test_active_channel.py`, `tests/test_settings_area.py`, V3 (`home/new_video/videos/trends/analytics`) | 25 + 10 + V3 **pass** |
| F02.T03 sete grupos + tela Avançado | `tests/test_advanced_page.py`, `tests/test_settings_area.py`, rotas em `test_video_style_api.py` | 5 + 10 + rotas **pass** |
| F02.T04 predefinição do canal | `tests/test_new_video_v3.py`, `tests/test_video_style_api.py` | 13 + 24 **pass** |

Regressão ampla: ver a seção "Suíte completa após F02" abaixo (comparação com o baseline de 63
falhas). Antes de qualquer release, repetir com a versão pinada de pydantic e com FFmpeg (F07).

## Suíte completa após F02

Ver [test-results-f02](test-results-f02.md) — mesmo comando e mesmo banco do baseline.