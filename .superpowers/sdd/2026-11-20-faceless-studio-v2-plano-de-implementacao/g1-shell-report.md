# G1 — shell do painel com navegação e seções

Worktree `faceless-v2-implementation`. Escopo autorizado: `renderer/app/studio/api/panel.py`,
`tests/test_panel.py`, `tests/test_panel_page.py`. Nada de `api/routes.py`, `composition.py`,
`tests/test_db.py`, `adapters/`, `application/`, `domain/`.

## Objetivo entregue

O painel deixou de ser uma página única sem hierarquia e passou a ser um **shell** com:

- sidebar em grupos (Operação / Indisponível nesta versão), navegação por âncoras na mesma página;
- hero com eyebrow, `h1` com palavra-acento e abas de origem;
- faixa de estados (Concluído / Em execução / Ação necessária) sempre visível, com texto + ícone;
- seções Produção, Precisa de você, Tendências e Vídeos;
- rail lateral (Custo do mês, Última falha, Estado das fases);
- `<details>` "Avançado — diagnóstico" fechado por padrão.

Somente dados reais do `PanelView`/`VideoDetailView`. Nada de conteúdo ilustrativo do mockup.

## Alinhamento ao mockup aprovado (`mockup-proposta.html`)

Design tokens copiados do mockup, em `:root`, dark-only (`color-scheme: dark`, sem
`prefers-color-scheme`): `--bg-app #0a0f19`, `--bg-canvas #101827`, `--surface #131b2d`,
`--surface-raised #1b263e`, `--border #2a3350`, `--border-soft #1f2942`, `--text #e6e9f5`,
`--text-muted #aab3c8`, `--text-dim #7f8aa6`, `--accent #7c3aed`, `--accent-strong #5b08f6`,
`--accent-soft #331e7e`, `--accent-contrast #ffffff`, `--success #74d6a6`,
`--success-surface #12322a`, `--success-contrast #06130d`, `--info #0abcff`,
`--warn #e3b341`, `--danger #ff5a6e`, `--radius 18px`, `--gap 20px`. Os aliases antigos
(`--primary`, `--ok`, `--bad`, `--warn` etc.) derivam dos tokens; nenhuma regra pinta texto
branco sobre `--success-surface` (teste cobre). `accent-color` e `scrollbar-color` no `:root`,
`scrollbar-color` sem animação, `:focus-visible { outline: 2px solid var(--info) }`.

Escolha **dark-only** justificada: o produto/mockup são escuros; tokens fixos evitam
tema claro quebrado e mantêm controles nativos coerentes (não há `light-dark()`).

Já existia uma troca de paleta intermediária (`--success #61ed9f`, `--warn #f7c948`) pedida
antes do mockup ser aprovado; ela foi substituída pela paleta medida do mockup, que passa a ser
a fonte de verdade.

## Honestidade da interface

- Itens sem backend (Canais, Analytics, Equipe, Configurações) são `<span>` com
  `aria-disabled="true"` e `tabindex="-1"`, tag visível `em breve`/`SaaS`; **não** são links.
- Nenhum percentual de progresso, barra falsa, "Implementado", "Plano Pro", créditos ou nomes
  fictícios. Sem execução, o estado é "Nenhuma execução registrada" com chips de etapas sem
  estado e sem percentual.
- Custo sempre com origem: `sem registro de uso` (ausência, nunca `US$ 0,00`),
  `Custo: US$ 0,00 (gratuito)` (free), `Custo desconhecido: N chamada(s) sem custo informado`,
  `Custo registrado: US$ x` (conhecido). Nenhum número sem rótulo.
- Ações contextuais: "Abrir Prévia" só onde há artefato (AWAITING/APPROVED/COMPLETED),
  "Ver correção"/"Ver Progresso" no restante; "Aprovar" nunca aparece sem artefato
  (detalhe do vídeo só oferece aprovação em AWAITING_APPROVAL).
- Falhas: resumo humano com "Passo de correção" + botão de nova tentativa **só quando válido**
  (`ASSETS_READY` → `/resume`; publicação `FAILED` → `/publication/retry`). Erro bruto/`Traceback`
  vai para "Avançado — diagnóstico", nunca na área principal.
- `Registro de Uso de Modelos`, ID do vídeo e erros brutos ficam no `<details>` fechado.

## Acessibilidade

Consultado `modern-web-guidance` (`search "navigation sidebar landmarks"`,
`retrieve navbar`): aplicado `aria-current="page"` no ativo (um só), `<nav>` com rótulo,
links em `<ul>`, `[aria-current]` como gancho visual, foco visível, estado por texto+ícone
(nunca só cor), alvos ≥ 40 px (nav) / 44 px (botões), `lang="pt-BR"`, um único `h1`,
skip-link, responsivo (1180 px e 820 px; nav ativa em faixa horizontal, indisponíveis em
duas colunas, itens empilhados, botões de largura total).

## TDD (RED → GREEN)

RED inicial (`tests/test_panel.py`): 12 falhas (`aria-current` só no ativo, itens desabilitados,
sections ausentes, estado vazio sem progresso, três estados, custo rotulado, avançado fechado,
tokens, detalhe sem "Aprovar", traceback fora da área principal, avançado com uso, retry válido).

GREEN após a implementação. Testes de página extras cobrem: sidebar/grupos e indisponíveis,
ausência de conteúdo ilustrativo do mockup, estado vazio, filtros de tendências com `aria-pressed`
e "Ver Mais (+2)", escaping de tópico/fonte com `<script>`, custo rotulado e ausência ≠ zero,
avançado fechado, viewport/media query 820 px, hero/abas/rail, detalhe sem "Aprovar" inválido.

## Comandos e resultados reais

Imagem `faceless-v2-hygiene-test-local:latest` (Python 3.12.16, pytest 8.3.5), `-p no:cacheprovider`.

- Focado, `--network none`:
  `… -m pytest -q -p no:cacheprovider tests/test_panel.py tests/test_panel_page.py tests/test_architecture.py`
  → **69 passed, 1 skipped** (com Postgres descartável; sem DSN os de página são ignorados).
- Suíte completa, `--network none`, `.git` montado somente leitura a partir de **snapshot estático**:
  → **1199 passed, 406 skipped, 0 failed**.
- Suíte completa com PostgreSQL 16 descartável (rede isolada `g1-net`, prova em
  `/budget-test-proof`, tmpfs) e snapshot de `.git`:
  → **1570 passed, 35 skipped, 0 failed**.
- JavaScript do filtro de tendências exercitado via Node no teste `test_region_filter_...`
  dentro da suíte do container.

### Falhas de outras fatias / ambiente

- `tests/test_db.py` chegou a falhar nas listas de migração (`0020`/`0021`); na última execução
  já estava corrigido por outro agente e passou. Não toquei no arquivo.
- `tests/test_secrets_hygiene.py` (2 testes) falhou de forma intermitente com a montagem do
  `.git` **vivo** (`Permission denied` ao abrir loose objects recém-escritos enquanto outros
  agentes commitavam). Com um **snapshot estático** do `.git` os 32 testes passam; é ambiente
  de montagem, não regressão desta fatia. Nada em `scripts/` foi alterado.

## Limitações assumidas (não mascarei)

- **Real vs estimado**: **FECHADA em fatia de continuação da G1** (ver seção
  “Fechamento da limitação — rótulos de custo”, abaixo). A G1 rotulava o conhecido como
  "Custo registrado (real ou estimado)"; agora `PanelView`/`VideoDetailView` expõem
  `cost_confirmation_kind` e a UI separa **Real** (ACTUAL), **Estimado** (ESTIMATE),
  **Sem custo** (FREE) e **Desconhecido** (sem confirmação e sem custo conhecido).
- **Runs reais**: não há acesso a `production_runs`/`stage_executions` no `PanelView`; a seção
  Produção mostra o vazio real quando não há vídeos e a contagem por etapa quando há.
- **"Última falha"**: o painel não carrega o erro por vídeo, então mostra o vídeo falho mais
  recente e um ponteiro para o detalhe (onde existe o retry válido), em vez de um botão
  "Tentar novamente" que poderia ser inválido.
- **Estado das fases**: rótulos estáticos do plano de implementação, marcados como tal no HTML.

## Fora do escopo desta fatia

Editor de cenas, revisão de roteiro, configuração de canal/OAuth, equipe/permissões, analytics,
publicação assistida e demais telas dos 11 fluxos — não implementados. A navegação os marca como
indisponíveis. `api/preview.py` continua com o tema anterior (não faz parte da fatia).

## Fechamento da limitação — rótulos de custo (continuação da G1)

A regra de UX aprovada (`JORNADA-E-TELAS.md`: "Mostrar custos reais vs estimados com rótulos
explícitos") e o mockup (quatro rótulos) deixaram de ser contrariados. O dado já existia na
coluna `studio.usage_ledger.cost_confirmation_kind` (`ACTUAL`/`ESTIMATE`/`FREE`/`NULL`, migração
`0019_ledger_estimate_and_attribution.sql`, fatia A); o gargalo era a leitura do painel não
trazer a coluna.

O que mudou:

- `adapters/postgres/panel_repo.py`: `videos()`, `video_detail()` e `month_usage()` passam a
  selecionar `cost_confirmation_kind`; `cost_rows` e a lista de uso do detalhe carregam o tipo
  (`month_usage` devolve os lançamentos crus do mês, agora com o tipo).
- `application/panel.py`: `cost_kind()` classifica cada lançamento em **Real** (ACTUAL),
  **Estimado** (ESTIMATE ou valor positivo ainda sem confirmação), **Sem custo** (FREE ou
  gratuidade reconhecida pelo provedor/modelo) e **Desconhecido** (sem confirmação e sem custo
  conhecido). `cost_summary_text()`/`CostBreakdown` somam por categoria e nunca fundem real e
  estimado num único número. `MonthCost` passa a expor o `breakdown`.
- `api/panel.py`: o rail "Custo do mês" mostra as quatro linhas (Real, Estimado, Sem custo,
  Desconhecido); o "Gasto no Mês vs Teto" e o detalhe do vídeo (por chamada) usam os mesmos
  rótulos. `Sem custo` nunca vira `US$ 0,00`; ausência segue "sem registro de uso"; desconhecido
  permanece distinto de zero.

Escolha de classificação documentada: sem confirmação, um positivo é **Estimado** — alinha com
`application/budget.py::provider_settlement` (positivo sem evidência de cobrança é ESTIMATE) e
mantém o teto consumido coerente com `spent_month`; o zero de provedor/modelo reconhecidamente
gratuito é **Sem custo**; o resto é **Desconhecido**. Não houve split inventado.

TDD (RED → GREEN). Arquivos: `renderer/app/studio/application/panel.py`,
`application/ports.py`, `adapters/postgres/panel_repo.py`, `api/panel.py`, `tests/test_panel.py`,
`tests/test_panel_page.py`, `tests/test_panel_repo.py`. `domain/`, `application/budget.py`,
`adapters/postgres/budget_repo.py`, migrações e `tests/test_db.py` não foram tocados.

Comandos e resultados reais (imagem `faceless-v2-hygiene-test-local:latest`, `-p no:cacheprovider`):

- Focado, `--network none` com PostgreSQL descartável (rede isolada `g1b-net`, prova em
  `/budget-test-proof`, tmpfs):
  `… tests/test_panel.py tests/test_panel_page.py tests/test_panel_repo.py tests/test_architecture.py`
  → **79 passed, 1 skipped**.
- Suíte completa com PostgreSQL 16 descartável (`STUDIO_TEST_DSN` e
  `STUDIO_BUDGET_DISPOSABLE_DSN`) → **1573 passed, 35 skipped, 2 failed**; as 2 falhas são as
  de `tests/test_secrets_hygiene.py` (ambiente de montagem, ver abaixo), não regressão desta
  continuação. Suíte sem banco: mesma coisa exceto os de banco, que aparecem como `skipped`.
- Falhas de `test_secrets_hygiene.py`: `.git` do worktree é um **gitfile** apontando para
  `/Users/rodrigomendes/youtube-faceless-starter/.git/worktrees/faceless-v2-implementation`, que
  não existe dentro do contêiner; `git rev-parse --show-toplevel` retorna 128 e o scanner responde
  "Secret hygiene check could not complete safely." Com o *gitdir* montado no caminho esperado, o
  scanner passa. A segunda falha
  (`test_extracted_starter_runs_contract_snapshot_and_backup_import`) decorre de
  `render_plan.py` estar **untracked** (trabalho em andamento de outra fatia na mesma árvore), o
  que faz o pacote carecer do módulo. Nenhum `scripts/` foi alterado.

## Git

Continuação: commit apenas de `renderer/app/studio/application/panel.py`,
`renderer/app/studio/application/ports.py`,
`renderer/app/studio/adapters/postgres/panel_repo.py`, `renderer/app/studio/api/panel.py`,
`tests/test_panel.py`, `tests/test_panel_page.py`, `tests/test_panel_repo.py` e deste relatório.
Caminhos exatos, sem `git add -A`, sem push/merge. Arquivos de outras fatias em andamento na
mesma árvore (`render_plan.py`, `scripts/export_contracts.py`, `tests/test_contracts_snapshot.py`,
`docs/10-arquitetura.md`, `docs/adr/`, `docs/contracts-versioning.md`,
`contracts/v1/renderplan.schema.json`, `tests/test_render_plan.py`) foram deixados intactos.

A fatia original (G1) commitou apenas `renderer/app/studio/api/panel.py`, `tests/test_panel.py`,
`tests/test_panel_page.py` e este relatório.
