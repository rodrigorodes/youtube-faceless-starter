# Continuidade — revisão do app e plano de testes Faceless

## Resumo atual

- Objetivo: revisar o app Faceless Studio e entregar o plano de testes no modelo GC.
- Fase: **plano completo e validado** (14 capítulos, 88 regras, 130 cenários; `validar.py` OK).
  Revisão do app concluída, suíte canônica executada e correções ACH-01/ACH-04..08 aplicadas
  e verificadas (ACH-09 mantido como intencional).
- Base: HEAD `f4a9244` (branch `main`), árvore **dirty** (49 entradas: WIP local de UX V4/V3,
  contratos gerados, testes ajustados e este plano). Referências de linha descrevem o estado lido.
- Ambiente canônico: `scripts/test-container.sh` (Docker, Python 3.12, Postgres 16 efêmero,
  ffmpeg com libass). O host macOS não é ambiente de teste válido.
- Última validação canônica (RUN-08, pós-correções ACH): `scripts/test-container.sh tests
  --ignore=tests/e2e_full --ignore=tests/e2e_ux -q` → **23 failed, 4035 passed, 20 skipped**
  (767 s, exit 1). Série completa: RUN-02 39 → RUN-04 32 → RUN-06 29 → RUN-07 25 → RUN-08 23.
  Resíduo: **23 falhas de A2** (texto/markup do WIP V4/V3); nenhuma regressão das correções.
  O flake de TTS passou na RUN-08.
- Triagem concluída (RUN-03): grupos B, C e D corrigidos como artefatos de teste
  desatualizados; grupo A (32 falhas) majoritariamente drift de teste do WIP V4/V3, não
  bug de produto confirmado. Subconjuntos verificados: B 39 passed, C+D 22 passed.
- Triagem refinada do grupo A (RUN-05): **32 failed, 165 passed** nos 9 arquivos do grupo.
  A1 (4) asserção em markup exato = defeito de teste; A2 (24) texto/markup do WIP V4/V3;
  A3 (5) mudança funcional com decisão de produto pendente (ACH-04..ACH-08); A4 (2)
  atraso de teste em relação a `auto_research`/`publication_enabled` **já commitados**.
  A1 e A4 corrigidos (só testes); reexecução dos 9 arquivos: **29 failed, 168 passed**
  (87,6 s) — naquele momento restavam 24 de A2 e 5 de A3. Depois da RUN-07, as 5 de A3
  saíram e restam 23 de A2 + 1 flake de medição de TTS.
- Execução completa pós-triagem (RUN-04): **32 failed, 4026 passed, 20 skipped**
  (691 s, exit 1). As 7 falhas removidas são os grupos B/C/D; as 32 restantes são todas
  do grupo A. O refinamento da RUN-05 mostra que A1 e A4 são corrigíveis sem tocar no
  produto; A2 e A3 dependem de decisão.
- Validação local no host: 19 failed, 3172 passed, 904 skipped; as 19 falhas são de
  render/subtitles por falta de libass no ffmpeg Homebrew e passam no container
  (74 passed, 1 skipped nos arquivos de render).
- Bloqueios: nenhum bloqueio de execução. A árvore dirty impede atribuir A2 ao produto; A2
  depende da aprovação do WIP V4/V3. ACH-01 e ACH-04..08 foram corrigidos e verificados;
  ACH-09 foi mantido como intencional.
- Próxima ação: a consistência dos capítulos e de `evidencias/` está fechada
  (`validar.py` OK após as edições). Falta a decisão do time: (a) aprovar o WIP V4/V3 e
  atualizar os 23 testes de A2; (b) acompanhar o flake de medição de TTS
  (`test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time`, que falhou na
  RUN-07 com 2,96 s e passou na RUN-08) na campanha; (c) cobrir `publication_enabled=False`
  em ACH-09.

## Decisões

- Modelo do plano: `.ai-analysis/GC_MVP/stg-teste/plano-de-testes-gc` (workspace CERC),
  adaptado ao domínio Faceless; sem HUs/cards inventados e sem presumir ambiente STG.
- Plano estritamente documental: cenários permanecem `A_PROJETAR`; a existência de um
  teste não promove cenário a PASS.
- Execução direta (sem LangGraph), conforme autorização do usuário; o runtime não foi usado.
- Evidências de execução em `evidencias/`; a suíte existente não é o plano.

## Mudanças feitas nesta sessão (além do plano)

- **Correções de produto ACH-01 e ACH-04..08** (decisão do usuário):
  - ACH-01: removidos os controles mortos de trilha/volume/ducking da Composição; o
    formulário mantém bpm/seed, que são o que o patch realmente envia.
  - ACH-04: removidos o diálogo modal de novo canal e o JS órfão; o caminho é o link
    `/studio/canais/novo` (ou o seletor global).
  - ACH-05: restaurados os filtros de vídeo/pilar e os chips de período em Análise; o
    seletor global de canal continua na casca e a rota aceita `project` e `project_id`.
  - ACH-06: a opção de herança de estilo no novo vídeo passou a dizer
    "Herdar do canal (nome)".
  - ACH-07: `/studio/configuracoes/canais` redireciona para `/studio/canais`; um único
    renderizador de lista de canais.
  - ACH-08: o novo vídeo voltou a mostrar o cartão "Predefinição do canal" com idioma,
    voz e estilo herdados.
  - ACH-09: mantido como intencional (publicação habilitada por padrão); o plano deve
    cobrir o caminho `publication_enabled=False`.
- `scripts/secret_hygiene.py`: trilhas CC0 de `storage/music-candidates/` deixam de ser
  bloqueadas por diretório; continuam sujeitas à varredura de conteúdo. Motivo: são
  amostras rastreadas e referenciadas pelo produto/testes.
- `tests/ve08/test_storyboard_functional.py`: o clique de mídia foi escopado à cena alvo
  (antes o `.first` global atingia a cena errada). O comportamento do app foi preservado.
- `tests/test_panel_production_render.py`: contagem de links da nav ajustada de 5 para 6,
  acompanhando as seis áreas canônicas.
- Contratos e DDL regenerados **dentro do container** (`scripts/export_contracts.py`,
  `scripts/export_schema.py --build` contra Postgres 16 efêmero). A geração anterior no
  host introduzia `minimum: 0.0` e a lista de 41 migrações; o container gera `0` e 48.
- `tests/test_db.py`: lista esperada de migrações atualizada para 48 (0047–0053).
- `tests/test_production_flow_db.py`: fixture passou a usar `auto_research=False`; a
  pipeline clássica é a que o teste descreve. A pipeline com pesquisa continua coberta
  em `tests/test_pesquisa_automatica.py`.
- `tests/test_panel_production_page.py`: mesma decisão da fixture anterior
  (`auto_research=False`), porque as asserções de stepper ("Etapa 1 de 8") e de etapa
  indisponível ("Fontes") descrevem a pipeline clássica. Verificado: 12 passed, 1 failed
  (a restante é a do bloco "Predefinição do canal", ACH-08).
- `tests/test_panel_page.py`, `tests/test_analytics_page.py`, `tests/test_script_page.py`:
  asserções de `<aside class="side">` afrouxadas para o prefixo do tag e
  `class="cartao-tendencia"` para `class="card cartao-tendencia"` (A1). Resultado: uma
  falha resolvida (`test_page_is_reached_through_the_approved_shell`); as outras três
  seguem falhando em asserções posteriores, que são A2 (cabeçalho "ESTÚDIO DO CANAL" e
  chip "Todas").
- Ambiente do host: `ffmpeg` 9.1 instalado via Homebrew (sem libass); a suíte canônica
  continua sendo o container. Isso mudou o resultado local de 2 para 19 falhas de render.

## Evidências

- `evidencias/RUN-2026-02-14-local/` — G0 e RUN-01 (unit/mock no host, antes dos ajustes).
- `evidencias/RUN-2026-11-25-container/RUN-02-container-suite.md` — suíte canônica,
  triagem inicial por categorias e reprodução no host.
- `evidencias/RUN-2026-11-25-container/RUN-03-triage.md` — triagem por grupo, correções
  em artefatos/testes e verificação dos subconjuntos.
- `evidencias/RUN-2026-11-25-container/RUN-04-container-suite-after-triage.md` — suíte
  completa pós-triagem: 32 failed / 4026 passed / 20 skipped, todas as falhas do grupo A.
- `evidencias/RUN-2026-11-25-container/RUN-05-group-a-refined.md` — triagem refinada das
  32 falhas do grupo A em A1/A2/A3/A4, com o detalhamento por teste e a correção de A4.
- `evidencias/RUN-2026-11-25-container/RUN-06-container-suite-after-group-a.md` — suíte
  completa após as correções de A1/A4: 29 failed / 4029 passed / 20 skipped.
- `evidencias/RUN-2026-11-25-container/RUN-07-ach-fixes.md` — correções de produto ACH-01 e
  ACH-04..08, testes atualizados e suíte completa pós-correção: RUN-07 25 failed / 4033
  passed e RUN-08 23 failed / 4035 passed (todas as 23 são A2).

## Restrições

Não ler segredos, não publicar vídeos, não chamar fornecedores pagos, não fazer push/merge.
Resultado parcial ou skip não é aprovação. As falhas do grupo A não são PASS nem FALHA de
produto até o WIP V4/V3 ser aprovado; a árvore dirty deve ser reconferida antes de
qualquer campanha.
