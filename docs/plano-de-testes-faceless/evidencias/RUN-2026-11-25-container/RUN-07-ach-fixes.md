# RUN-07 — correções de produto ACH-01 e ACH-04..08

- Data: 2026-11-25
- Base: HEAD `f4a9244` (branch `main`), árvore dirty (WIP local de UX V4/V3 + este plano)
- Decisão do usuário: corrigir ACH-01 e ACH-04..08 no produto; manter ACH-09 como intencional.
- Ambiente: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero).

## Correções aplicadas

| Achado | Mudança | Arquivo |
|---|---|---|
| ACH-01 | Controles de trilha, volume e ducking removidos da Composição; BPM/seed permanecem e o texto explica que a trilha é sintetizada e a mixagem é aplicada pelo motor. | `renderer/app/studio/api/panel_video_workspace.py` |
| ACH-04 | Diálogo modal de novo canal e o JS morto removidos; o caminho é o item "＋ Novo canal…" do seletor (assistente em `/studio/canais/novo`). | `renderer/app/studio/api/shell_v3.py` |
| ACH-05 | Filtros de vídeo/pilar e chips de período voltaram a ser renderizados; a rota aceita `project_id` e `project`; o JS morto de `#analytics-project` foi removido. | `renderer/app/studio/api/panel_analytics.py`, `renderer/app/studio/api/routes.py` |
| ACH-06 | Opção de herança no novo vídeo passou a usar "Herdar do canal (nome do estilo)". | `renderer/app/studio/api/panel_new_video.py` |
| ACH-07 | `/studio/configuracoes/canais` redireciona (302) para `/studio/canais`; o renderizador duplicado foi removido. | `renderer/app/studio/api/routes.py`, `renderer/app/studio/api/panel_settings.py` |
| ACH-08 | Cartão "Predefinição do canal" restaurado com idioma, voz e estilo herdados; `_language_label` voltou a ser usado. | `renderer/app/studio/api/panel_new_video.py` |
| ACH-09 | Mantido como intencional (publicação habilitada por padrão); a campanha deve cobrir `publication_enabled=False`. | — |

## Testes atualizados (para o desenho corrigido)

- `tests/test_panel_page.py`: o teste do seletor de canal deixou de exigir o diálogo modal
  removido e passou a verificar o item "＋ Novo canal…" do seletor.
- `tests/test_video_style_api.py`: o teste de estilos passou a ler o bloco
  `aria-label="Estilo"`/`div.choice` e a esperar "Herdar do canal (nome)".
- `tests/test_panel_production_page.py`: o teste do wizard passou a esperar o cartão
  "Predefinição do canal" e o botão atual (`btn-criar-abrir`), sem exigir ausência de
  qualquer `disabled`.
- `tests/test_analytics_page.py`: o teste de troca de canal passou a verificar o seletor
  global `#canal-ativo` e a rota aceitando `project_id`; e foi adicionado
  `test_filters_form_lets_the_user_narrow_by_video_and_pillar`, que prova o formulário de
  filtros e a seleção por vídeo/pilar (15 passed no arquivo).
- `tests/test_video_download_and_audiovisual_summary.py`: o teste da Composição passou a
  verificar BPM/seed e a ausência dos controles removidos.

## Verificação por subconjunto

- `tests/test_new_video_v3.py tests/test_video_style_api.py tests/test_panel_production_page.py tests/test_analytics_page.py`:
  **72 passed** (24,5 s).
- `tests/test_panel_page.py tests/test_settings_sections.py tests/test_channels_page.py tests/test_styles_page.py tests/test_connections_page.py tests/test_video_download_and_audiovisual_summary.py`:
  **101 passed, 22 failed** — as 22 falhas são o drift A2 já documentado (nav com glifos,
  Configurações de 7 para 4 seções, vazios e rótulos do WIP V4/V3); nenhuma é regressão das
  correções.

## Execução completa (RUN-07/RUN-08)

- Primeira execução pós-correção (RUN-07, imagem anterior à última edição de teste):
  **25 failed, 4033 passed, 20 skipped** em 763 s (exit 1). Série: RUN-02 39 → RUN-04 32 →
  RUN-06 29 → RUN-07 25 falhas.
- Execução final (RUN-08, com todas as edições): **23 failed, 4035 passed, 20 skipped** em
  767 s (exit 1). **Todas as 23 falhas são A2** (drift de texto/markup do WIP V4/V3); nenhuma
  toca as correções de ACH. O flake de TTS passou nesta execução.
- As falhas removidas em relação à RUN-06 são os 5 testes de A3 (ACH-04..08). A falha de
  `test_settings_area.py::...[canais]` na RUN-07 era imagem antiga; passou na RUN-08.
- Triagem das 23 falhas de A2:
  - glifos na nav (`⌂ Início`), Configurações de 7 para 4 seções;
  - vazios e rótulos do painel (Tendências, "Todas", "Criar vídeo deste tema");
  - nota de custo, media query e eyebrow "ESTÚDIO DO CANAL";
  - `#appearance-form` em `/studio/configuracoes/marca` e link do painel de produção.
  Todas são mudanças de desenho do WIP V4/V3, pendentes de aprovação; não são bugs de
  produto nem regressões das correções.
- Nenhuma falha restante foi confirmada como regressão das correções ACH-01 e ACH-04..08.
