# Changelog

- 21/11/2026: proposta de projeto consolidada, roadmap F00–F07, G15, ADRs propostos, prompts, diagramas e critérios de aceite. Sem alterações de runtime. Baseline e decisões aguardam F00.
- 21/11/2026 (F00, HEAD `e254b61`): baseline revalidado por conteúdo (`git diff c0cd97c HEAD`
  vazio; `c0cd97c` sem ancestral comum com o HEAD). Inventário de telas/símbolos em
  `evidence/inventory.md`; validação técnica dos 7 ADRs em `evidence/decisions-needed.md`;
  ADRs renomeados com prefixo `fs31-`; `README` corrigido para o caminho real do pacote;
  matriz de gaps com coluna de revalidação; receita do PostgreSQL descartável em
  `06-validation.md`; governança e documento-fonte registrados. Nenhum arquivo de runtime
  alterado; nenhum commit, push, deploy, publicação ou chamada paga.- 21/11/2026 (F02, sem commit): estilo real no Create (`VideoIn.style_id` opcional, validação
  no caso de uso, persistência na criação, arquivado recusado); canal ativo propagado por
  casca/corpo/redirects com validação no Core (`api/active_channel.py`); Configurações com sete
  áreas e nova tela read-only "Avançado" (saúde, providers reais, configuração efetiva);
  predefinição do canal com idioma/voz reais e sem linhas fictícias. Testes novos/atualizados
  em `test_active_channel.py`, `test_advanced_page.py`, `test_new_video_v3.py`,
  `test_video_style_api.py`, `test_ports.py`, `test_settings_area.py` e nos testes V3.
  Registro das 63 falhas pré-existentes em `evidence/pre-existing-failures.md`.
- 21/11/2026 (paralelização): worktrees `f01-identity`, `f01-budget` e `f06-providers` criadas
  a partir de `e254b61` com a F02 copiada; PostgreSQL descartável por stream (55436/55434/55435).
  Suíte principal da F02 fechou em 2679 passed / 63 failed / 58 skipped, com falhas idênticas ao
  baseline. Nenhum commit.
- 21/11/2026 (F05.T01, sem commit): patch tipado de estilo (`StylePatch`, allowlist por grupo,
  reset explícito, listas substituem, `extra` aberto) como entrada canônica de
  `resolve_effective_config`; sem regra duplicada. Testes: 139 passed no grupo. Limite: nenhum
  consumidor de produção chamava a resolução ainda.
- 21/11/2026 (F01.T02/T04, sem commit): o Core executa a publicação
  (`POST /studio/publications/execute`) e o n8n só orquestra — nenhum nó com credencial do
  YouTube, nenhum PUT em `googleapis`. Analytics usa o grant do canal de destino (escopos em
  `AccessToken`) e recusa sem `yt-analytics.readonly`. `STUDIO_PUBLICATION_ENABLED=0` bloqueia
  antes do claim (contingência explícita), sem alterar o padrão. Grupo F01 com DSN: 147 passed.
- 21/11/2026 (F04, sem commit): `EditorialContext` derivado de `EffectiveConfig`, idioma/duração/
  alvo fora do hardcode, prompts byte-idênticos quando não há perfil; matriz campo→consumidor em
  `evidence/f04-editorial-context.md`. Testes: 175 passed. Fiação `editorial_for` feita na
  composição na onda seguinte.
- 21/11/2026 (F03.T02, sem commit): snapshot da configuração efetiva persistido na mesma transação
  do run (migração `0039_production_run_config.sql`); replay com config divergente é conflito 409;
  run legado explícito e nunca re-resolvido. Testes integrados: 175 passed.
- 21/11/2026 (F05.T02, sem commit): patch de estilo persistido em canal e vídeo com revisão
  otimista e escrita dedicada (migração `0040_style_patches.sql`); `{}` recusado e allowlist
  aplicada antes do SQL. Grupo integrado: 261 passed. Fiação de patch na composição feita em
  seguida (junto com `editorial_for`): 146 passed nos testes de fiação.
- 21/11/2026 (**commit local `ea5782f`**, sem push): ondas 1–4 do backlog + scroll infinito em
  Tendências. Operador autorizou commit local, manteve o `budget_guard` desligado e não autorizou
  publicação real. 147 arquivos; `docs/`, `renderer/`, `tests/` e `workflows/`.
- 21/11/2026 (commits `832dc9f`, `a77f661`, `c77dbd5`, sem push): F06.T03 (preferências de
  produção na tela de Canais), F03.T04 (lifecycle com entradas congeladas + migração 0041),
  F05.T04 (personalizar canal separado da biblioteca, componente + rota de patch) e as rotas
  `style-patch`/`regenerate`. F03.T03 e F06.T02 já estavam nas ondas anteriores.
- 21/11/2026 (**gate de regressão**): `pytest tests` com banco → **2953 passed, 21 failed, 58
  skipped, 2 xfailed** (396 s); as 21 são as pré-existentes (17 FFmpeg/PIL, 2 pydantic, 2 ordem).
  Ver `evidence/test-results.md`.

- 22/11/2026 (paridade visual com a proposta, sem push): correções dos achados FS31-A1/A2/A3
  com testes de regressão, mais a rodada de paridade das telas.
  - Tokens/CSS: `.pills`/`.pill` voltaram à forma do protótipo (borda + `panel2`; checked =
    `accentfill`/`soft`/`accent`); `.hero` usa `var(--hero)` e `--muted` (claro no tema claro);
    `.btn-primario` usa `accentfill`/`onaccent` e o hover do protótipo; criados `--ok`, `--err`,
    `--success`, `--panel3`; removida a sombra fixa dos cards; `select` com opções legíveis no
    tema claro; `.muted` não encolhe mais o "Studio" da marca.
  - Novo vídeo: ícone 16:9/9:16 em cada formato e estilo em cartões `.cartao-estilo` com amostra
    do **nome real** da biblioteca (sem catálogo fictício).
  - Configurações: menu na ordem do protótipo (`Identidade do canal`, `Canais`, `Conexões`,
    `Estilos`, `Equipe`, `Avançado`), todos os links levando o canal ativo; h1 volta a ser
    "Configurações"; topbar de Estilos/Conexões/Equipe/Avançado passa a mostrar o canal real.
  - Identidade do canal: Voz e Idioma em linhas `item-config` pré-preenchidas pelo perfil;
    detalhes do perfil atrás de "Detalhes do perfil"; estilo padrão em galeria de cartões.
  - Canais: card fixo "Canal ativo" no topo com seletor, selo `ATIVO` e botão `Trocar` por canal.
  - Avançado: entra na casca de Configurações (menu lateral + h1 único), tabela com CSS.
  - Produção: `render_production_page` (casca V3) substitui `render_producao` (casca V2).
  - Testes: contratos antigos atualizados para o novo desenho (galeria, h1 de Configurações,
    links com `project_id`), com testes novos para o card de canal ativo e o menu completo.
