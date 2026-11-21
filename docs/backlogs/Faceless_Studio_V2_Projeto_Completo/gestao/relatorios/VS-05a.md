# VS-05a — Estilos: a biblioteca compartilhada (API + tela + item de menu)

- **Branch:** `feat/vs05a-styles-library`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05a-styles-library`
- **Base:** `f848a57` (`merge: o canal referencia o destino do YouTube + resolvedor de autorizacao (YT-02)`)
- **Desenho:** `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` §4 (IA), §5.3
  (tela), §6 (vazio que ensina), §7 (checklist do "leve").
- **Escopo:** entregar a **superfície de Estilos** — (1) a API que faltava; (2) a página do painel
  ("lista + criar + editar + arquivar"); (3) o item de menu. **Não** entra: o seletor de estilo
  dentro do canal (VS-05b) nem a tela de Conexões (YT-04).

## Por que "Estilos" é destino próprio (e não um campo do canal)

O desenho §4/§5.3 diz: o estilo é **compartilhado entre canais**. Se ele morasse dentro do canal, o
usuário entenderia que é daquele canal só e voltaria a copiar à mão — o problema que a biblioteca
veio resolver. Por isso a tela é separada, "Gestão › Estilos", e a lista diz **quantos canais usam**
cada estilo (medição real). Nenhum campo obrigatório além do nome; nada de preview falso nem
percentual — o que não tem medição não aparece (§7.6).

## O que mudou (por arquivo)

### Domínio — `renderer/app/studio/domain/visual_style.py`
- Novo erro `VisualStyleFieldInvalid(VisualStyleError, ValueError)` para campo de edição desconhecido
  (fora de `UPDATABLE_FIELDS`), espelhando `ChannelFieldInvalid`. Os erros de params/nome/versão já
  existiam; nada mais mudou (domínio puro, sem I/O).

### Adaptador Postgres — `renderer/app/studio/adapters/postgres/visual_style_repo.py`
- `usage_counts() -> dict[str, int]`: `SELECT style_id, count(*) FROM studio.channel_profiles
  WHERE style_id IS NOT NULL GROUP BY style_id`. Só conta canal com estilo; canal sem estilo não
  aparece no mapa. **Contagem medida, nunca estimada.**
- `archive(style_id) -> VisualStyle | None`: **soft delete** — marca `archived = true`, grava uma
  revisão nova (bump de versão) e **não apaga linha nenhuma**. Idempotente (estilo já arquivado
  volta como está) e devolve `None` se o estilo não existe. Libera o nome ativo para reúso.

### Porta — `renderer/app/studio/application/ports.py`
- `VisualStyleRepository` ganha `archive(style_id)` e `usage_counts()`, com docstrings curtas. A
  porta segue só com o domínio.

### Aplicação (nova) — `renderer/app/studio/application/styles.py`
- Casos de uso `CreateVisualStyle`, `GetVisualStyle`, `ListVisualStyles`, `UpdateVisualStyle`,
  `ArchiveVisualStyle`, `VisualStyleUsage` (esta última lê `usage_counts`). Dependem só da porta
  `VisualStyleRepository`; a validação vive no domínio (`create`/`update` constroem `VisualStyle`,
  que roda `clean_params`).

### Aplicação (nova) — `renderer/app/studio/application/styles_page.py`
- `StyleListItem(style, channels_using)` e `StylesPageView(items, is_empty)`; `BuildStylesPage`
  monta a lista com `usage_counts()` (uma leitura só). Projeção pura, sem I/O.

### API — `renderer/app/studio/api/routes.py`
- Modelos `VisualStyleIn` (name + params), `VisualStyleUpdateIn` (expected_version + changes),
  `VisualStyleOut` (id, name, params, version, archived, created_at, updated_at, **channels_using**);
  helper `_style_out`.
- Endpoints (moldes dos endpoints de canal): `GET /styles`, `POST /styles` (201), `GET /styles/{id}`,
  `PATCH /styles/{id}`, `POST /styles/{id}/archive`, e a página `GET /panel/estilos` (`HTMLResponse`).
- Mapeamento de erro em `run()`: `VisualStyleNotFound`→**404**; `DuplicateVisualStyle`/
  `VisualStyleVersionConflict`→**409**; `VisualStyleNameInvalid`/`VisualStyleParamsInvalid`/
  `VisualStyleFieldInvalid`/`VisualStyleVersionInvalid`→**422** (usa a mensagem do domínio; não vaza
  stack trace). `organization_id` foi **omitido** de propósito (single-tenant; não confunde).

### Página (nova) — `renderer/app/studio/api/panel_styles.py`
- `render_styles(view) -> (html, headers)`, no molde das páginas existentes: mesma casca
  (`panel as shell`), mesmo `_headers(nonce)` (CSP + `no-store`), mesmo sidebar.
- **Lista**: cada linha = nome + **resumo curto** dos parâmetros (ex.: "zoom_in + pan_left · 122 bpm
  · legenda 58px") + **quantos canais usam** ("Nenhum canal usa" / "1 canal usa" / "N canais usam")
  + botão **Editar** (divulgação) + botão **Arquivar**.
- **Estado vazio que ensina** (§6): "Nenhum estilo ainda" + "Criar o primeiro estilo" (abre o
  formulário e foca o nome) e a nota "sem estilo, o canal segue o padrão do estúdio — e está ótimo".
- **Criar/editar** com **no máximo 2 níveis** de divulgação: o `<details>` que revela o formulário
  (nível 1) e o **Avançado** recolhido (nível 2). **Básico** = nome · ritmo de câmera (`motion`,
  checkboxes) · música (`music.bpm`). **Avançado** = `caption` (tamanho/rodapé), `palette` (3 cores),
  `voice` (modelo) e **`extra` (JSON)** para parâmetros sem campo próprio. Só o **nome** é obrigatório.
- **Sem invenção**: os parâmetros que não têm campo dedicado (ex.: `transition`) são **preservados**
  a partir do `data-params` do estilo atual no PATCH — nada é perdido sem querer nem inventado.
- **Acessibilidade**: `<label for>` em cada campo, `aria-describedby` nas dicas, `role="status"
  aria-live="polite"` no feedback, foco visível (`:focus-visible`), `aria-invalid` no nome quando
  vazio, teclado (nativo). Mantém o padrão do painel.

### Casca/menu — `renderer/app/studio/api/panel.py`
- Item **Estilos** promovido a destino real em **Gestão** (antes de "Equipe"), com
  `href="/studio/panel/estilos"` e `active="estilos"`/`aria-current="page"`; ícone novo na
  `_NAV_ICONS`.
- **Única remoção permitida:** a entrada morta "Configurações — em breve" saiu de `_NAV_UNAVAILABLE`
  (que passou a tupla vazia) e foi **substituída por uma tela real**. Com o slot vazio, a seção
  "Indisponível nesta versão" **deixa de ser renderizada** quando não há item indisponível (nada de
  grupo morto e vazio). Não havia "Conexões" morto para manter — e não foi criado.

### Fiação — `renderer/app/studio/composition.py` e `application/use_cases.py`
- `UseCases` ganha os sete campos novos (`create/get/list/update/archive_visual_style`,
  `visual_style_usage`, `styles_page`), **no fim** do dataclass, casando com a construção posicional
  de `from_repo`. `composition._wire` constrói os casos de uso sobre o `style_repo` já existente
  (o mesmo que alimenta `_style_for_project`) e o `BuildStylesPage`. **Wiring só em `composition.py`.**

## Testes

Arquivos tocados:

- **`tests/test_styles_api.py` (novo, 8)**: CRUD com round-trip dos params; arquivar é soft delete
  (some da lista, volta com `include_archived`, libera o nome); 404 em GET/PATCH/archive
  inexistente; POST com params inválidos → 422 com mensagem clara e sem stack trace; desconhecido em
  params → 422; nome duplicado e conflito de versão → 409; campo de update desconhecido → 422; auth
  obrigatória; **`channels_using` medido** (2 canais no mesmo estilo → 2; canal sem estilo não conta).
- **`tests/test_styles_page.py` (novo, 10)**: estado vazio ensina e passa no contrato de UX;
  página com dados passa no contrato; lista traz nome + resumo + uso medido; sem estilo não há linha
  de uso; nada de preview/percentual/`progressbar`; XSS de dado real é escapado; menu tem **Estilos
  ativo** e **não tem mais "Configurações"/"em breve"** (nem item indisponível, nem seção vazia);
  formulário com labels/dicas e Avançado recolhido; CSP + `no-store`; auth obrigatória.
- **`tests/test_visual_style_repo.py` (+3)**: `usage_counts` (2 no mesmo estilo; canal sem estilo
  fora); `archive` soft delete, idempotente, libera nome e grava revisão; `archive` de inexistente
  → `None`.
- **Testes de casca ajustados** (a única remoção permitida muda o esperado): `tests/test_panel.py`,
  `tests/test_panel_page.py` e `tests/test_publishing.py` passaram a esperar **"Estilos"** no lugar
  de "Configurações", e os testes de item indisponível viraram "não há item indisponível e Estilos
  é link real" / grupo "Gestão" no lugar de "Indisponível nesta versão".

Contagens (`--collect-only`):

| Arquivo | Antes | Depois |
| --- | --- | --- |
| `tests/test_styles_api.py` | — | 8 |
| `tests/test_styles_page.py` | — | 10 |
| `tests/test_visual_style_repo.py` | 8 | 11 |
| `tests/test_architecture.py` | 6 | 6 |
| **Total (arquivos novos/tocados acima)** | **14** | **35** |

Resultado:
- `tests/test_styles_api.py tests/test_styles_page.py tests/test_visual_style_repo.py` →
  **29 passed**.
- `tests/test_architecture.py tests/test_panel.py tests/test_panel_page.py tests/test_publishing.py
  tests/test_channels_page.py tests/test_channel_api.py tests/test_panel_production_page.py` →
  **176 passed, 1 skipped**.
- `tests/test_ux_contract.py tests/test_team_page.py tests/test_analytics_page.py
  tests/test_script_page.py tests/test_video_style.py` → **41 passed**.

### Comando

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05a-styles-library
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_styles_api.py tests/test_styles_page.py tests/test_visual_style_repo.py \
  tests/test_architecture.py tests/test_panel.py tests/test_panel_page.py tests/test_publishing.py \
  tests/test_channels_page.py tests/test_channel_api.py tests/test_panel_production_page.py
```

## Arquitetura

- `domain`/`application` continuam **puros**: os casos de uso dependem só da porta; a validação de
  params mora no domínio; `styles_page`/`BuildStylesPage` são projeção sem I/O. A API **não** constrói
  repositório concreto — fala só com os casos de uso via `_need`. `tests/test_architecture.py` verde.
- `panel_styles.py` importa `panel` como `shell` (api→api) e `..domain.visual_style` (api→domain),
  como `panel_channels.py`. Nenhum import de adaptador/`psycopg` na API.

## Modern Web Guidance (skill obrigatória de HTML/CSS/JS)

- **`forms`**: `<label for>` antes de cada campo e empilhado acima; `aria-describedby` para as dicas;
  `inputmode="numeric"`/`min`/`max` nos campos numéricos; validação no `submit` (não a cada tecla);
  `role="status" aria-live="polite"` para anunciar o resultado; `:focus-visible` preservado
  ("DO maintain a visible :focus-visible indicator on all controls"). Checkboxes para o multi-select
  de `motion` (2+ opções), conforme a matriz de controle de seleção do guia.
- **`accessibility`**: um único `<h1>`, `<label>` explícito, sem `aria-label` redundante; nada de
  heading dentro de `<summary>` ("Avoid placing headings inside the <summary> element"); landmarks
  `<main>`/`<aside>`/`<nav aria-label>` mantidos.
- **`content-first-noise-reduction`**: o avançado fica atrás de `<details>` ("Collapse secondary
  content with `details`") — divulgação progressiva em 2 níveis, sem modal bloqueante.

## Limitações / não feito (e o que ficou de fora)

- **VS-05b**: o **seletor de estilo dentro do canal** (aba "Aparência") não foi feito — fora do
  escopo desta fatia.
- **YT-04**: a página de **Conexões** não foi criada (e não havia item morto "Conexões": não
  inventei um).
- **`transition`/`music.seed` sem UI**: não têm campo dedicado nesta fatia; são **preservados** no
  PATCH via `extra`/`data-params`, mas não há controle visual para eles. `voice` é carregado pela
  tela mas **não** passa a ser aplicado no render (a ordem da voz segue como no VS-04).
- **Sem preview**: nada de preview falso nem percentual (§7.6) — a lista só mostra o que o render
  declara e a contagem medida.
- **Lista esconde arquivados** por padrão (sem alternância "mostrar arquivados" na tela); a API
  aceita `?include_archived=true`.
- Única remoção: a entrada **"Configurações — em breve"** (`_NAV_UNAVAILABLE`), substituída pela
  tela real de Estilos — registrada aqui. Nenhum outro item foi removido.
- Não rodei a suíte inteira (VM apertada); árvore limpa; sem `git add -A`, sem push/merge.
