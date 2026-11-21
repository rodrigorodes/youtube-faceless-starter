# PROD-04 — a criação carrega o vídeo base da tendência e não inicia produção fadada ao `SourceRefused`; um vídeo sempre pode iniciar produção nova

- **Branch:** `feat/prod04-creation-carries-source`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod04-creation-carries-source`
- **Base:** `main` @ `8de68c1`
- **Postgres dedicado:** `integ-pg-c` (sem contenção; o `integ-pg` compartilhado não foi usado)
- **Escopo:** os três achados da fatia (3, 4 e 5 do `ATIVIDADES.md`). Fundiu o antigo PROD-05.
  **Não** toquei `main.py`/produção (é da PROD-03, em paralelo), nem `docker-compose.yml`, allowlist,
  telas de Estilos/Conexões/Canais/Equipe.

## 1) Achado 3 — a criação a partir da tendência perde a URL do vídeo do YouTube

Relato do dono: *"ao criar video da trend nao carrega o link do video do youtube URL da fonte * vem vazio"*.
Diagnóstico confirmado no código (não re-derivado): o botão «✨ Criar Vídeo deste Tema» leva só o tema
(`api/panel.py`, `data-topic`/`href`), `studio.videos` não tem coluna de origem e o `#source-url` era
renderizado sempre vazio. O **vínculo já existia**: o cartão da tendência agrupa por `topic_key` e a
função de domínio `topic_key()` casa o tema do vídeo com o da tendência.

### O que mudou

- **Porta focada no domínio de tendências** (`application/ports.py`): `TrendRepository.find_by_topic_key(project_id, topic_key) -> TrendRecord | None`.
  A chave chega **já normalizada** (regra de domínio em Python); o casamento no banco é exato — **nada**
  de normalização em SQL.
- **Adapter Postgres** (`adapters/postgres/trend_repo.py`): implementa a porta; a construção do
  `TrendRecord` foi extraída para um `_record(row)` reaproveitado por `list` e pela nova busca (uma só
  montagem).
- **Extração única da URL do vídeo base** (`application/panel.py`): `evidence_video_url(evidence)`
  devolve `evidence[0]["url"]`. É a **mesma** extração que o cartão de tendência já usava
  (agora os dois leem daqui — sem duas verdades, o risco registrado no §5.2 do desenho).
- **Resolução na aplicação pura** (`BuildPanel.detail`): normaliza `topic_key(video.topic)` e busca a
  tendência do canal (`self.trends.find_by_topic_key(...)`). Sem correspondência → `None`.
- **`VideoDetailView`** ganhou `base_video_url: str | None` e `base_video_source_name: str | None`.
- **Página do vídeo** (`api/panel.py`, `_video_sources_card`): o `#source-url` sai com
  `value="{url}"` quando resolvido e um texto visível **"vídeo base: <a …>URL</a>"** (com a origem
  ao lado, quando existe). Sem correspondência, o campo volta vazio, como hoje.
- **NÃO** criei fonte automaticamente e **NÃO** gravei nada: com `text=None` o servidor tentaria buscar
  a URL e a allowlist de nicho (`STUDIO_SOURCE_ALLOWLIST`) recusa; fonte sem texto não é evidência. O
  ganho é o humano só precisar **colar o texto**.

### Antes → depois (página do vídeo, cartão Fontes)

```html
<!-- antes: sempre vazio -->
<input type="url" id="source-url" name="url" class="input" required …>

<!-- depois (tema casa com a tendência): preenchido + vídeo base visível -->
<p class="dim" …>vídeo base: <a href="https://youtube.com/watch?v=nTJ5Z9gZsZU" target="_blank"
  rel="noopener noreferrer">https://youtube.com/watch?v=nTJ5Z9gZsZU</a> · YouTube Brasil (Em Alta)</p>
<input type="url" id="source-url" name="url" class="input" required …
       value="https://youtube.com/watch?v=nTJ5Z9gZsZU">
```

## 2) Achado 4 — criar pelo Início inicia uma produção que já nasce falhando

O formulário do Início **criava e iniciava** (`POST /production-runs`), mas a 1ª etapa do DAG
(`script`) exige fontes, e a fonte só pode ser adicionada **depois** que o vídeo existe. Todo vídeo
novo nascia com um run `FAILED` e `SourceRefused: no sources with checkable claims: add sources first`.

### O que mudou

O formulário do Início passou a **criar o vídeo e abrir a página do vídeo**
(`/studio/panel/videos/{id}`), onde vivem **Fontes** e **Iniciar produção**. Nada de iniciar run no
ato de criar.

```js
// antes
const started = await fetch('/studio/videos/' + … + '/production-runs', { method:'POST', … });
if (started.ok && run.run_id) location.href = '…/production-runs/' + run.run_id;

// depois
feedback.textContent = 'Vídeo criado. Abrindo para você pesquisar as fontes...';
location.href = '/studio/panel/videos/' + encodeURIComponent(data.id);
```

O detalhe do motivo real do servidor em falha de criação e o link de saída («Ver meus vídeos») foram
preservados. O texto do formulário passou a declarar o fluxo novo: *"Ao criar, o vídeo abre para você
pesquisar as fontes; a produção só começa quando você clicar em «Iniciar produção»…"*.

**Isto reverte deliberadamente o auto-start do PROD-01.** O fluxo aprovado em `JORNADA-E-TELAS.md` é
**Produzir vídeo → Pesquisar fontes → Roteiro**; iniciar antes de existir fonte garantia um run
`FAILED` na cara do usuário. O resto do PROD-01 segue: cartão Fontes (URL+texto), «Iniciar
produção»/«Tentar novamente» e o motivo real do servidor.

## 3) Achado 5 — não havia como iniciar produção nova num vídeo que já tem run

A página só oferecia «Iniciar produção» quando `latest_run is None`; com qualquer run existente a
ação não existia — embora a API aceite (`create_run` não tem guarda de run ativo).

### O que mudou (cartão Produção, `api/panel.py`)

| Estado do run | Ações na tela |
| --- | --- |
| sem run | «Iniciar produção» (como hoje) |
| `FAILED` | «Tentar novamente» (retry da etapa) **+** «Iniciar nova produção» **+** «Abrir execução» |
| `CANCELLED` / `SUCCEEDED` | «Iniciar nova produção» (primário) **+** «Abrir execução» |
| `RUNNING` / `WAITING_HUMAN` | **só** «Abrir execução» (o «Continuar» do PROD-02 vive na tela de execução) |
| `CREATED` / `PAUSED` | sem produção nova: explica por quê (segue o caminho da execução) |

- «Iniciar nova produção» posta em `POST /studio/videos/{id}/production-runs` com **novo**
  `Idempotency-Key` a cada clique — é um **run novo**, não o retry da etapa. O mesmo handler JS serve
  os botões `#btn-start-production` e `#btn-new-production`.
- A tela deixa claro: *"«Iniciar nova produção» recomeça do zero: cria um novo run e reprograma as
  etapas. Não é o retry desta execução."*
- Sem botão inerte: com run vivo, a tela explica por que a produção nova não cabe.

## Testes

### Novos / corrigidos (`tests/`)

- `test_panel.py`:
  - `test_evidence_video_url_is_the_shared_trend_extraction` — a extração compartilhada (caso com
    URL, vazio, sem `url`, evidência vazia).
  - `test_detail_resolves_base_video_url_by_topic_key` — o caso do dono
    (`GTA VI: DIA 3 ZERANDO  🔴 CORINGA AO VIVO` → `topic_key` normalizado) resolve a URL
    do `evidence[0]`.
  - `test_detail_without_a_matching_trend_has_no_base_video_url` — sem correspondência → `None`.
  - `test_video_detail_sources_card_prefills_the_base_video_url` — o input sai com `value="…"` e o
    texto «vídeo base».
  - `test_video_detail_sources_card_stays_empty_without_a_matching_trend` — input sem `value=`.
  - `test_video_detail_terminal_run_offers_new_production` (parametrizado: `FAILED`/`CANCELLED`/`SUCCEEDED`)
    — «Iniciar nova produção» + «recomeça do zero».
  - `test_video_detail_live_run_does_not_offer_new_production` — `RUNNING`/`WAITING_HUMAN` **não**
    oferecem produção nova.
  - `test_home_create_form_opens_the_video_page_without_starting_production` — **substitui** o antigo
    `test_home_create_form_also_starts_the_production_run`.
  - `_detail_view` ganhou `base_video_url`/`base_video_source_name`; `FakeTrendRepo` ganhou
    `find_by_topic_key`.
- `test_panel_page.py` (Postgres):
  - `test_video_detail_page_prefills_the_base_video_url_from_the_matching_trend` — `trend_topics` de
    mesmo `topic_key` → página com a URL preenchida.
  - `test_video_detail_page_leaves_the_source_url_empty_without_a_matching_trend` — sem tendência →
    campo vazio.

### O assert corrigido, e por quê

- **`test_home_create_form_also_starts_the_production_run` → renomeado e invertido.** O teste antigo
  **fixava** o comportamento que o achado 4 aponta como defeito:
  ```python
  assert "/production-runs" in html          # inicia produção no ato de criar
  assert "Idempotency-Key" in html
  assert "A produção começa no modo assistido" in _visible_text(html)
  ```
  A expectativa nova é o oposto: o Início **não** posta `/production-runs` e **navega para a página
  do vídeo**. A mudança está documentada no próprio docstring do teste.

### Prova de que os novos asserts são load-bearing (falsificação)

Sabotei o código e conferi que os testes falham, então revertí:

- `evidence_video_url` → `None` e `detail` sem resolução:
  `2 failed` (`…shared_trend_extraction`, `…resolves_base_video_url_by_topic_key`) — os asserts
  apontaram exatamente os valores (`assert None == 'https://…'`).
- Prefill e ramo terminal do cartão sabotados:
  `4 failed` (`…prefills_the_base_video_url`, `…terminal_run_offers_new_production[FAILED/CANCELLED/SUCCEEDED]`).
- Revertido: os mesmos testes voltam a passar.

### Comando e resultado

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/prod04-creation-carries-source
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-c:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-c:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_panel.py tests/test_panel_page.py tests/test_panel_api.py tests/test_panel_domain.py \
  tests/test_panel_repo.py tests/test_ux_contract.py tests/test_publishing.py tests/test_architecture.py \
  tests/test_composition.py tests/test_panel_production_page.py tests/test_panel_production_render.py \
  tests/test_trend_repo.py
```

**235 passed, 1 skipped, 1 warning** (`integ-pg-c`).
O skip é o pré-existente `test_panel.py:522` ("Node.js necessário para exercitar o filtro JavaScript" —
o container não tem Node; o host tem e o teste passa local). Nenhuma falha nova.

`tests/test_architecture.py` verde: `domain`/`application` seguem **puros** (a porta `find_by_topic_key`
vive em `ports.py`; a resolução usa `topic_key()` do domínio, sem I/O); o wiring permanece **só** em
`composition.py` (o `BuildPanel` já recebia `trends=trend_repo`); nenhuma regra na view.

## O que mudou (por arquivo)

| Arquivo | Mudança |
| --- | --- |
| `renderer/app/studio/application/ports.py` | Porta `TrendRepository.find_by_topic_key(project_id, topic_key)` (chave já normalizada). |
| `renderer/app/studio/adapters/postgres/trend_repo.py` | Implementa a busca por `topic_key`; `_record(row)` compartilhado com `list`. |
| `renderer/app/studio/application/panel.py` | `evidence_video_url(evidence)` (extração única); `VideoDetailView.base_video_url`/`base_video_source_name`; resolução por `topic_key` em `BuildPanel.detail`. |
| `renderer/app/studio/api/panel.py` | `#source-url` pré-preenchido + «vídeo base»; formulário do Início cria e **abre o vídeo** (sem `/production-runs`); cartão Produção com «Iniciar nova produção» (terminal) e sem ele (vivo); JS do novo botão. |
| `tests/test_panel.py` | 8 testes novos, 1 substituído; `FakeTrendRepo.find_by_topic_key`; `_detail_view` estendido. |
| `tests/test_panel_page.py` | 2 testes de integração (Postgres) para o prefill. |

## O que **não** consegui / limitações reais

- **Tema editado ao criar:** se o dono **editar** o tema, o `topic_key` deixa de casar e a URL não se
  resolve (o campo volta vazio). Gravar a procedência (id da trend no vídeo) resolveria isso, mas
  **exige migração** — a fatia foi explícita em **não** migrar (o vínculo existente já basta). Registrado
  como opção, não incluído.
- **`CREATED`/`PAUSED`:** por não serem estados terminais nem “vivos” na acepção do pedido, a tela
  **não** oferece produção nova nesses casos (segue o caminho da execução). Se o dono quiser produção
  nova também neles, é uma linha a mudar — decisão de produto, não de bug.
- **Sem verificação ao vivo:** não reiniciei o app (8000) nem o bridge (8787) e não criei dados no
  ambiente do dono, conforme o pedido. A integração foi provada com Postgres dedicado (`integ-pg-c`),
  não contra a base real do estúdio.
- **Sem `git add -A`** (caminhos exatos), sem push/merge; suíte inteira **não** rodada (só os arquivos
  pedidos + `test_trend_repo.py`, já que o adapter mudou).
