# G — F2 wizard `Novo vídeo` + página de execução (relatório)

Worktree `faceless-v2-implementation`, branch `faceless-v2-impl`. Sem push/merge. Dependência
usada, não refeita: **D2** (`ProductionCoordinator`, `POST /studio/videos/{id}/production-runs`,
`GET .../production-runs/{run_id}`, pause/resume/cancel/retry, eventos) em `9d5ab2c`..`51734c7`.

Fonte de verdade visual: `produto/mockup-telas.html` §§2 (`#novo`) e 3 (`#producao`) e os PNGs
`tela-novo-video.png` / `tela-producao.png`, agora cobertos pelo contrato `tests/test_ux_contract.py`.

## Commits

| Commit | Conteúdo |
|---|---|
| `468b56a` | `refactor(panel)`: extrai a casca (`build_sidebar_nav`/`render_sidebar`), o card de orçamento (`budget_side_card`) e as linhas de custo (`cost_breakdown_rows`); `BuildPanel.month_cost()` reutiliza o mesmo cálculo do rail do painel |
| `a217365` | `feat(api)`: novo módulo `api/panel_production.py` (wizard + execução) e as rotas HTML |
| `fd08ad2` | `test(panel)`: contrato de UX + ações por estado (render puro e rotas com Postgres) |
| (este relatório + linha no `progress.md`) | `docs(g)` |

**Decisão de arquitetura:** a tela nova foi para `renderer/app/studio/api/panel_production.py` em
vez de inflar `api/panel.py` (3.177 linhas). A casca/tokens vêm de `panel.py` por import
(`render_sidebar`, `budget_side_card`, `cost_breakdown_rows`, `CSS`, `_headers`); nenhuma rota
existente mudou de comportamento (os 70 testes de painel/detalhe seguem verdes). O `render_video`
(detalhe do vídeo) **não** foi tocado — ver pendência.

## O que foi entregue (F2-02..F2-05)

**Wizard `Novo vídeo`** (`GET /studio/panel/novo-video`) — hero, grid de campos, chips de origem
com `aria-pressed`, rail "O que acontece ao produzir", card "Modo de execução". Controles com
capacidade real: **Tema**, **Canal** (projetos reais do Studio), **Formato**. Controles sem
backend ficam **desabilitados com motivo em texto** (`role="note"`, "Motivo: …"): Público, Duração
alvo (480 s padrão), Estilo, Idioma e Teto de custo. Botão primário **`Produzir vídeo`**
(`#btn-produzir-video`) cria o vídeo (`POST /studio/videos`) e chama o coordinator D2 com
`Idempotency-Key` (`POST /studio/videos/{id}/production-runs`), redirecionando para a execução.

**Página de execução** (`GET /studio/panel/videos/{video_id}/production-runs/{run_id}`) — stepper
com **estado por etapa** (concluído / em execução / ação necessária, sempre texto + ícone),
etapa atual (`aria-current="step"`), **próxima ação**, tempo decorrido, custo com rótulo de origem
e eventos. **Sem barra de progresso e sem percentual**: mostra "Etapa N de M" e diz por quê
("o trabalho não é linear e etapas podem ser refeitas"). Card de **ação necessária** com
"O que fazer" + retry **só quando o estado é `FAILED`**. Rail de custo com os quatro rótulos
(`Real`/`Estimado`/`Sem custo`/`Desconhecido`, de `cost_kind`/`CostBreakdown` da G1b). Rail de
ações **condicionadas ao estado**; "Revisar" só com artefato (`next_action == "approve"`).
`<details>` "Avançado — diagnóstico" **fechado por padrão**, com IDs, eventos e uso de modelos.

## Provas e contagens reais

Docker `faceless-v2-hygiene-test-local:latest` (Python 3.12, pytest 8.3.5), `-p no:cacheprovider`,
rede `g1-net`, Postgres descartável `g1-pg` com prova montada em `/budget-test-proof`, **as duas**
variáveis `STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN` + `STUDIO_BUDGET_TEST_PROOF_FILE`.

- Novos: `tests/test_panel_production_render.py` (27) + `tests/test_panel_production_page.py` (12)
  → **39 passed**; +1 em `tests/test_panel.py` (`month_cost`) → **40 novos**.
- Focado (arch+contrato+painel+produção+novos): **196 passed, 1 skipped**; subconjunto dos arquivos
  novos: **123 passed, 1 skipped**.
- **Suíte completa: 1759 passed, 35 skipped, 2 failed** em 195 s. As 2 falhas são
  `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
  `::test_extracted_starter_runs_contract_snapshot_and_backup_import` — **ambientais**: o `.git` do
  worktree é um *gitfile* apontando para fora do mount, e o `render_plan.py` está *untracked* na
  mesma árvore. Não é regressão desta fatia (mesmo par em D2/G1).
- `tests/test_architecture.py` verde (módulo novo fica em `api/`; `domain/`/`application/` sem
  import de PIL/numpy/cv2/ffmpeg/SDK).

**TDD / load-bearing.** `assert_ux_contract` (R1–R6 + sem `<progress>` + sem texto do mockup) é
aplicado às duas telas nos dois arquivos de teste. As regras de ação por estado foram verificadas
por mutação: forçando `pause` em qualquer estado, os testes de ações ficam vermelhos
(`7 failed, 1 passed`); revertido em seguida. Nada do mockup ilustrativo vaza
(`"Como a OpenAI ganha dinheiro?"`, `"1,2 mi views"`, `"run_7f31"`, `"Finanças Descomplicadas"`,
`"US$ 0,42"`, `"US$ 1,50"` são proibidos por teste).

## Onde o código real contradisse o mockup aprovado

1. **IDs/`run_id` no topo** — o mockup mostra `Execução run_7f31 · iniciada há 6 min`; a regra diz
   que IDs ficam só no avançado. A página mostra "Execução iniciada há … · modo …" e o `run_id` só
   no `<details>` (testado).
2. **`Estimado de hoje para este perfil: US$ 0,42`** — não existe projeção de custo pré-produção.
   Trocado por "Registrado no mês: …" (real) + "o Studio não projeta o custo antes de produzir".
3. **Stepper de 8 passos** — o pipeline real do coordenador é `script..approval` (7). `research`
   (Fontes) e `publish` (Publicação) são **indisponíveis** e aparecem no rail "Indisponível nesta
   versão" com o motivo real, não no stepper (para "Etapa N de M" ser real).
4. **Passo "Voz"** — o estágio `assets` cobre imagens **e** voz; rotulado "Voz e imagens".
5. **"Custo desta execução"** — `usage_ledger` não tem `run_id`; não há atribuição por execução.
   O rail mostra o custo **registrado do vídeo** e diz explicitamente que não há atribuição por
   execução. `Real`/`Estimado`/`Sem custo`/`Desconhecido` continuam separados.
6. **"Canal"** — o mockup sugere canal com voz/identidade/orçamento (perfil de canal, F10). O
   `create_video` exige um **projeto** e o `channel_id` do run é opcional/independente; então
   "Canal" lista os **projetos** reais do painel.
7. **`Produzir vídeo` em dois passos** — o endpoint D2 exige `video_id`; o botão cria o vídeo e
   então inicia o run (idempotência pela chave aleatória no navegador).

## Explicitamente indisponível (nunca finge funcionar)

- Etapas **Fontes/pesquisa (F3)** e **Publicação (F8)**: recusadas pelo coordenador; wizard e
  execução as listam com o motivo.
- Origem **Série/Playlist**: chip `aria-disabled` (sem backend).
- Por vídeo: **Público, Duração alvo, Estilo de edição, Idioma, Teto de custo** — o
  `create_video`/run não os persistem; ficam desabilitados com motivo. O teto por vídeo é
  configuração do servidor (`MAX_COST_USD_PER_VIDEO`), não editável por vídeo.

## Pendência registrada (fora do escopo da G)

A **página de detalhe do vídeo** (`render_video` em `api/panel.py`) **não usa a casca aprovada**:
seu único `<nav>` é `<nav class="nav-menu" aria-label="Navegação do vídeo">` (linha ~3080) e não
existe `<nav class="nav" aria-label="Principal">`. O mockup tem a sidebar em todas as telas. Isso é
anterior à fatia G (não é regressão) e a unificação exigiria mexer em `render_video` (muitos testes
de detalhe). Não ampliei a fatia; fica para uma fatia de UI dedicada (H ou continuação de G),
usando `render_sidebar(...)`.

## Limitações

- Sem validação em navegador/leitor de tela (não há UI instrumentada no ambiente); o contrato de UX
  é a garantia automatizada. O JavaScript (criação do vídeo + ações do run) não é exercitado por
  teste de navegador — só o HTML/contrato.
- A página de execução usa o custo do **vídeo** (ver item 5), por ausência de atribuição por run.
