# PROD-01 — fechar o ciclo de produção pela interface: criar→iniciar, informar fontes e retomar

- **Branch:** `feat/prod01-production-loop`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod01-production-loop`
- **Base:** `e7a5182` (`merge: voz com precedencia unica - estilo > projeto > default (VS-06)`)
- **Escopo:** fechar, na interface, o ciclo **criar → iniciar → informar fontes → retomar**.
  Sem inventar dado: toda mensagem de erro vem do servidor.

## Os três gaps (diagnóstico confirmado no código)

### Gap 1 — dois fluxos de criação e um deles não inicia a produção

- `renderer/app/studio/api/panel.py` (página **Início**, `#create-video-form`, ~2359–2383): o form
  fazia `POST /studio/videos` e, no sucesso, só escrevia "Vídeo criado com sucesso! Atualizando..."
  + `location.reload()`. **Nunca** chamava a produção — enquanto o próprio texto da tela promete
  "A produção começa no modo assistido; a aprovação do roteiro e do preview acontece no vídeo."
- `renderer/app/studio/api/panel_production.py` (assistente, `GET /panel/novo-video`): o
  `#btn-produzir-video` faz `POST /studio/videos` e **depois** `POST /studio/videos/{id}/production-runs`
  com header `Idempotency-Key` e navega para `/studio/panel/videos/{id}/production-runs/{run_id}`.
  **É o fluxo correto** e foi o espelho usado aqui.

### Gap 2 — a produção falha sem fontes (o run fica preso/`FAILED`)

- `renderer/app/studio/application/production.py:445` — `COORDINATOR_DAG` começa em `SCRIPT`
  (`SCRIPT → FACTCHECK → STORYBOARD → ASSETS → RENDER → QA → APPROVAL → PUBLISH`).
- O stage `SCRIPT` exige claims de fontes: `renderer/app/studio/application/editorial.py:226`
  `raise SourceRefused("no sources with checkable claims: add sources first")`. Sem fonte, o run
  falha com exatamente essa mensagem.

### Gap 3 — a UI não tinha como adicionar nem ver fontes

- O endpoint de criação já existia (`POST /videos/{id}/sources`, `routes.py`), mas **não havia
  `GET /videos/{id}/sources`** e a página do vídeo não tinha nenhum controle de fontes — a tela
  "Pesquisa" do desenho aprovado não foi implementada.

## O que cada mudança fecha

### 1. Início — criar **e** iniciar (`renderer/app/studio/api/panel.py`)

O sucesso do `#create-video-form` passou a: `POST /studio/videos` → `POST /studio/videos/{id}/
production-runs` com `Idempotency-Key` gerado no browser (`crypto.randomUUID()`, fallback
`Date.now()`), igual ao assistente → navegação para a execução. Em qualquer falha:

- falha ao criar → mensagem com o **motivo real** do servidor + link de saída para `#videos-section`;
- vídeo criado mas produção não iniciou → motivo real do servidor + **link para o vídeo**
  (`/studio/panel/videos/{id}`) para tentar de novo.

Sem `innerHTML` (o painel proíbe): os nós são montados com `textContent` + `Element.append`, então o
texto do servidor nunca é interpretado como HTML. Comentário curto marca que o fluxo duplicado será
unificado na fatia de IA das telas (`// TODO(fatia IA das telas): …`).

### 2. Página do vídeo — cartão **Fontes** (`_video_sources_card`)

- Lista as fontes já registradas (**URL + quantidade de caracteres**), lidas do servidor.
- Formulário com **URL obrigatória** + **`<textarea>` de texto opcional** → `POST /studio/videos/{id}/sources`.
- Texto de ajuda com a regra real: *com texto*, o texto colado é a fonte e a URL é referência;
  *sem texto*, o servidor busca a URL e ela precisa estar em `STUDIO_SOURCE_ALLOWLIST` — e quando a
  busca é recusada a **mensagem do servidor** (`SourceRefused` → 422) aparece no feedback.
- `GET /videos/{id}/sources` foi **criado** (`response_model=list[SourceOut]`), servido pela
  composição via o caso de uso `ListSources`.

### 3. Página do vídeo — iniciar / retomar (`_video_run_card`)

A página passou a receber a execução mais recente **pela projeção da aplicação** (não consulta o
banco na view):

- sem run → botão **"Iniciar produção"** → `POST /production-runs` + navegação para a execução;
- run `FAILED` → mostra **a etapa** e **o motivo real** do stage (ex.: "add sources first") e o botão
  **"Tentar novamente"** → `POST /production-runs/{run_id}/retry` + navegação;
- qualquer outro estado → **sem botão inerte**: explica que a nova tentativa só vale em falha e
  oferece "Abrir execução".

Projeção estendida (camada de aplicação, pura):

- `application/ports.py`: novos `SourceInfo` e `LatestRun`; `VideoDetail` ganhou `sources` e
  `latest_run` (defaults, sem quebrar chamadas existentes).
- `application/panel.py`: `VideoDetailView` ganhou os mesmos campos; `BuildPanel.detail` só copia.
- `adapters/postgres/panel_repo.py`: a leitura agregada (`video_detail`) passou a trazer as fontes
  (`length(text)`, sem o texto) e o run mais recente + a etapa que falhou (`stage_executions.error`,
  truncado a 500). **Nenhum** acesso a banco na view.
- `composition.py`: único lugar de fiação — `list_sources=ListSources(snaps, repo)`.
- `application/editorial.py`: novo caso de uso `ListSources` (valida o vídeo → 404; lista as fontes).
- `api/routes.py`: `GET /videos/{video_id}/sources`.

## O que mudou (por arquivo)

| Arquivo | Mudança |
| --- | --- |
| `renderer/app/studio/api/panel.py` | Form da Início inicia a produção (idempotência + link de saída); cartões Fontes e Produção na página do vídeo; CSS de erro (`:user-invalid` + `.error-msg`) e ponte `aria-invalid`; JS de fontes/iniciar/retomar. |
| `renderer/app/studio/api/routes.py` | `GET /videos/{video_id}/sources` (`list[SourceOut]`), via `editorial(uc).list_sources`. |
| `renderer/app/studio/application/editorial.py` | `ListSources` (lista fontes; vídeo inexistente → `VideoNotFound`); campo `list_sources` em `Editorial`. |
| `renderer/app/studio/application/ports.py` | `SourceInfo`, `LatestRun`; `VideoDetail.sources` / `.latest_run`. |
| `renderer/app/studio/application/panel.py` | `VideoDetailView.sources` / `.latest_run`; `detail()` copia da projeção. |
| `renderer/app/studio/adapters/postgres/panel_repo.py` | `video_detail` lê fontes (tamanho) e run mais recente + etapa/erro que falhou. |
| `renderer/app/studio/composition.py` | Fiação de `ListSources`. |
| `tests/test_panel.py` | +6: Início chama `production-runs`; cartão Fontes (URL+chars, URL+textarea); iniciar/sem-run; falha com motivo real + retry; estado não-falha explica sem botão inerte. |
| `tests/test_panel_page.py` | +3 (Postgres): cartão Fontes + controle de iniciar; motivo real + retry com run `FAILED`; lista de fontes registradas. |
| `tests/test_editorial_api.py` | +3: round-trip de `GET /sources` (sem o texto); regra **texto dispensa allowlist × busca recusada (422)**; vídeo inexistente → 404. |
| `tests/test_editorial.py` | +1: com fonte aproveitável o `SourceRefused` do roteiro deixa de acontecer. |

Wiring **só** em `composition.py`; `domain`/`application` seguem puros (`tests/test_architecture.py`
verde). Nenhum repo é construído em `application`/`api`.

## Testes — comando e resultado

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod01-production-loop
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-c:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-c:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_panel.py tests/test_panel_page.py tests/test_panel_production_page.py tests/test_production_api.py \
  tests/test_editorial_repo.py tests/test_editorial_api.py tests/test_editorial.py tests/test_architecture.py \
  tests/test_composition.py tests/test_publishing.py
```

**258 passed, 1 skipped** (Postgres dedicado `integ-pg-c`). Sem contenção
(`schema "studio" does not exist` / `duplicate key … (nspname)`).

Extra (contrato de UX + vizinhança do painel):

```
… tests/test_ux_contract.py tests/test_panel_api.py tests/test_panel_repo.py tests/test_panel_domain.py
```

**38 passed.** O contrato de UX roda sobre a página do vídeo alterada (`test_video_detail_satisfies_the_ux_contract`).

## UI/acessibilidade (modern-web-guidance)

Consultei a skill antes de escrever HTML/JS. Aplicado:

- `<label>` para a URL e para o `<textarea>`; URL `required` com `*` em `aria-hidden` (o `required` já
  anuncia "obrigatório").
- A regra "mostrar o erro só depois da interação": erro visual e `aria-invalid` acompanham
  `:user-invalid` (Baseline desde 2023) via ponte JS, e o campo só referencia a mensagem em
  `aria-describedby` enquanto está inválido — a mensagem não é lida escondida no load.
- Feedback com `role="status" aria-live="polite"` (o padrão do painel); foco nativo no primeiro campo
  inválido ao enviar.

## Limitações / não feito

- **Não dividi** as páginas Início/Produção/Tendências (é a fatia de IA) e não toquei em
  Estilos/Conexões/Canais.
- **Não** alterei a allowlist default (`amsterdam-dance-event.nl`) nem o `docker-compose.yml`.
- A produção real ainda depende de fontes: a UI agora **mostra o motivo real** do servidor e dá a
  saída (adicionar texto/URL), mas não inventa fonte nem dado.
- Não rodei a suíte inteira (VM apertada). Árvore limpa; **sem `git add -A`**, sem push/merge.
