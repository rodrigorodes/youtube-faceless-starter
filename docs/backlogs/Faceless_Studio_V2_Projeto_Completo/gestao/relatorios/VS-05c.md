# VS-05c — o override chega ao render e `archive` limpa os vínculos

- **Branch:** `feat/vs05c-override-and-archive`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05c-override-and-archive`
- **Base:** `6df1762` (`merge: seletor de estilo no canal + override no video (VS-05b)`)
- **Escopo:** fechar **duas promessas que o código não cumpria**, ambas achadas na VS-05b e
  verificadas no código da base: (1) o override de estilo do vídeo existia na tela, mas **não**
  chegava ao render; (2) `archive` **não** limpava os vínculos e a docstring **mentia**. Correção
  cirúrgica, sem refatoração. **Não** entra: painel/HTML (outra fatia é dona), preview de estilo.

## Defeito 1 — o override existe na tela, mas não chega ao render

**Evidência na base `6df1762`:**

- `renderer/app/studio/composition.py:483`
  `style_for=lambda project_id: _style_for_project(project_id, channel_repo, style_repo)` — o
  resolvedor recebe **só o `project_id`**.
- `renderer/app/studio/application/render.py:220`
  `style = self.style_for(video.project_id) if self.style_for is not None else None` — o
  `RunRender` passa o `project_id`, nunca o `Video`.
- `renderer/app/studio/composition.py:178` `_style_for_project(project_id, channels, styles)`
  resolve **só** o estilo do canal: `profile = channels.get_by_project(project_id)` →
  `style = styles.get(profile.style_id)` → `resolve_style(profile, style)` (linha 196). O
  `videos.style_id` **nunca é lido**.
- `renderer/app/studio/domain/visual_style.py:294` `resolve_style(profile, style, override=None)`
  já aceitava `override`, e a linha 309 (`chosen = override if override is not None else style`)
  demonstra que o parâmetro existia **sem ser alimentado** por ninguém.

Ou seja: `Video.style_id` (VS-02b, `migrations/0036_video_style.sql`), o seletor de override
(VS-05b) e o parâmetro `override` de `resolve_style` existiam — mas o render ignorava o override.
"O vídeo pode sobrepor" era falso na prática.

### O que passou a valer

- **`RunRender` recebe o `Video`**, não o `project_id`:
  `style_for: Callable[[Video], ResolvedStyle | None] | None` (`application/render.py`) e a chamada
  virou `self.style_for(video)` (`application/render.py:220`). O resto da assinatura intacto.
- **`_style_for_video(video, channels, styles)`** (renomeado de `_style_for_project`) resolve:
  canal do projeto → `channel_profiles.style_id` **e** `videos.style_id` (override) →
  `resolve_style(profile, canal_style, override=video_style)`.
- **Precedência documentada no código: vídeo > canal > neutro.** Sem canal e sem estilo de vídeo,
  `resolve_style` devolve `None` → bundle neutro, como hoje.
- **Tolerância**: `InvalidId` no canal (catch igual ao `channel_guard_limits`) e id/estilo
  inexistente **não** derrubam o render — caem no comportamento seguro (sem estilo, ou estilo do
  canal). Um override quebrado cai no estilo do canal.
- Fiação só em `composition.py`:
  `style_for=lambda video: _style_for_video(video, channel_repo, style_repo)`.

## Defeito 2 — `archive` não limpa os vínculos, e a docstring mentia

**Evidência na base `6df1762`:**

- `renderer/app/studio/adapters/postgres/visual_style_repo.py:98` `archive` só executava
  `UPDATE studio.visual_styles SET archived = true, version = version + 1` + revisão. **Não** tocava
  em `channel_profiles.style_id` nem em `videos.style_id`.
- A docstring dele (linhas 99-103) dizia: *"os canais que apontavam para ele passam a resolver o
  padrão do estúdio"* — **falso**.
- `get(style_id)` (linha 67) **não** filtra `archived`, e `_style_for_project` usava
  `styles.get(profile.style_id)`: um canal apontando para um estilo **arquivado continuava
  resolvendo aquele estilo**.
- Do outro lado, a FK de `videos.style_id` é `ON DELETE SET NULL`
  (`migrations/0036_video_style.sql:10`), que **só age em `DELETE`** — e `archive` não deleta.
  Logo, o vídeo também seguia apontando para o estilo arquivado.

### O que passou a valer

- **Arquivar limpa os vínculos na mesma transação** (`visual_style_repo.py::archive`): após marcar
  `archived`, roda `UPDATE studio.channel_profiles SET style_id = NULL WHERE style_id = %s` e
  `UPDATE studio.videos SET style_id = NULL WHERE style_id = %s` — o canal volta ao padrão do
  estúdio; o vídeo volta a herdar do canal. Tudo dentro do mesmo `self._connect()`/transação do
  arquivamento (atômico).
- **Contagem medida exposta**: novo tipo puro `VisualStyleArchive(style, cleared_links)`
  (`domain/visual_style.py`), devolvido pelo repositório (`archive`) e pelo caso de uso
  (`ArchiveVisualStyle`). `cleared_links` é o **rowcount real** dos UPDATE (canal + vídeo), nunca
  estimado. A rota `POST /styles/{style_id}/archive` passa a devolver o campo `links_cleared`.
- **Idempotência preservada**: arquivar duas vezes não bumpa a versão de novo (devolve o estilo como
  está); a limpeza roda de novo (barata) para um vínculo reinserido à mão não escapar.
- **Defesa em profundidade na resolução** — estilo arquivado nunca dirige render:
  - `composition._active_style(styles, style_id)` trata `archived` como **ausente** (id estranho
    também): um override arquivado cai no estilo do canal; um estilo de canal arquivado cai no
    neutro.
  - `domain.resolve_style` também: `chosen = override if (override is not None and not
    override.archived) else style` e `if chosen is None or chosen.archived: return None`.
  - Assim, mesmo que um vínculo escape da limpeza, o render não usa estilo arquivado.
- **Docstring corrigida** em `archive` (adaptador), na porta (`ports.VisualStyleRepository`) e no
  caso de uso, descrevendo o comportamento real (limpa os vínculos + devolve a contagem).

## O que mudou (por arquivo)

| Arquivo | Mudança |
| --- | --- |
| `renderer/app/studio/domain/visual_style.py` | `resolve_style` passa a tratar estilo arquivado como ausente; novo `VisualStyleArchive(style, cleared_links)`. |
| `renderer/app/studio/application/render.py` | `style_for` recebe `Video`; chama `self.style_for(video)`. |
| `renderer/app/studio/application/ports.py` | Porta `archive` devolve `VisualStyleArchive | None` e documenta a limpeza atômica. |
| `renderer/app/studio/application/styles.py` | `ArchiveVisualStyle.execute` devolve `VisualStyleArchive | None`. |
| `renderer/app/studio/adapters/postgres/visual_style_repo.py` | `archive` limpa canal+vídeo na mesma transação, conta os vínculos (`_clear_links`) e devolve o resultado; docstring corrigida. |
| `renderer/app/studio/composition.py` | `_style_for_project` → `_style_for_video(video, …)` com precedência vídeo > canal > neutro; `_active_style` (defesa contra arquivado); lambda da fiação recebe o vídeo. |
| `renderer/app/studio/api/routes.py` | Rota de archive devolve `links_cleared`; campo aditivo em `VisualStyleOut`. |

Nada de `domain`/`application` tocando banco: a resolução é pura; a limpeza vive no adaptador
Postgres (dono da transação). **Wiring só em `composition.py`.**

## Testes

- **`tests/test_composition.py` (+4, 13 no total)** — reescrito para o novo resolvedor:
  (a) canal com estilo + vídeo sem override → estilo do canal; (b) vídeo com override → estilo do
  **vídeo** (snapshot + params do vídeo); (c) sem canal e sem estilo de vídeo → `None`; (d) vínculo
  quebrado (`InvalidId` / id inexistente) não derruba; (e) estilo arquivado conta como ausente
  (canal arquivado → `None`; override arquivado → canal).
- **`tests/test_render.py` (30)** — o teste do `style_for` agora prova que o **vídeo** (com o
  `style_id` do override) chega ao resolvedor; o fake `Videos` ganhou `style_id`.
- **`tests/test_visual_style_repo.py` (+2, 13 no total)** — (1) arquivar um estilo usado por
  **1 canal + 1 vídeo** → os dois `style_id` viram `NULL`, o outro estilo não é tocado, contagem
  devolvida `== 3`, e arquivar de novo devolve `cleared_links == 0` sem bumpar a versão;
  (2) estilo arquivado **não** resolve no `_style_for_video` mesmo com os vínculos reinseridos à
  mão (defesa em profundidade). O teste de idempotência/nome liberado foi adaptado ao novo retorno.
- **`tests/test_visual_style_domain.py` (+1, 19 no total)** — `resolve_style` trata arquivado como
  ausente (override arquivado cai no canal; canal arquivado e ambos arquivados → `None`).
- **`tests/test_styles_api.py` (+1, 9 no total)** — arquivar via HTTP devolve `links_cleared == 1` e
  o canal do projeto perde o `style_id`.

### Comando e resultado

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05c-override-and-archive
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-b:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-b:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_composition.py tests/test_visual_style_repo.py tests/test_visual_style_domain.py \
  tests/test_video_style.py tests/test_render.py tests/test_render_plan_executor.py \
  tests/test_styles_api.py tests/test_architecture.py tests/test_repo.py tests/test_channel_repo.py tests/test_db.py
```

**167 passed** (Postgres dedicado `integ-pg-b`). Extra (sem mudança de escopo, para não deixar
buraco): `tests/test_video_style_api.py tests/test_styles_page.py tests/test_channel_api.py
tests/test_render_cache.py tests/test_render_plan_repo.py` → **70 passed**. Sem contenção
(`schema "studio" does not exist` / `duplicate key … (nspname)`).

## Arquitetura

- `domain`/`application` seguem **puros**: a precedência e o "arquivado = ausente" viraram regra
  pura (`resolve_style`, `effective_style_id`) e a limpeza de vínculos vive no adaptador Postgres,
  dono da transação. Nenhum repo é construído em `application`/`api`. `tests/test_architecture.py`
  verde.
- A API fala só com casos de uso (`_need`) e o campo novo (`links_cleared`) é **aditivo** em
  `VisualStyleOut` (default `0`); nenhum contrato existente quebra.
- **Wiring só em `composition.py`.**

## Limitações / não feito

- **Painel/HTML não tocado** (outra fatia é dona). O `links_cleared` já é devolvido pela API para
  essa tela consumir quando quiser; a fatia do painel decide como exibir.
- **Não bumpa a versão do canal** ao limpar o `style_id`: quem limpou foi a biblioteca, não uma
  edição do canal; a otimização de versão do perfil continua sendo do operador. Uma atualização
  concorrente do canal com a versão antiga ainda pode reintroduzir o `style_id` — e aí a defesa em
  profundidade da resolução entra em ação (estilo arquivado não dirige render).
- **Arquivar não deleta linhas** (continua soft delete): a FK `ON DELETE SET NULL` só valeria numa
  limpeza dura; aqui a limpeza é feita por UPDATE explícito, na mesma transação.
- Não rodei a suíte inteira (VM apertada). Árvore limpa; **sem `git add -A`**, sem push/merge.
