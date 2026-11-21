# VS-05b — o canal herda, o vídeo pode sobrepor (seletor de Aparência + override de vídeo)

- **Branch:** `feat/vs05b-channel-style`
- **Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05b-channel-style`
- **Base:** `759fe71` (`merge: biblioteca de Estilos (API + tela + menu) (VS-05a)`)
- **Desenho:** `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` §5.2 (o canal
  em abas, com **Aparência** = seletor de estilo), §3/§7 (divulgação progressiva ≤ 2 níveis;
  "seleção em vez de formulário"; "o que não tem medição não aparece"), §6 (vazio que ensina).
- **Escopo:** fechar o "canal herda / vídeo sobrepõe" **na interface**: (1) seletor de estilo no
  canal (grava `channel_profiles.style_id`) + link "criar novo estilo"; (2) seletor de override no
  vídeo (grava o `style_id` do vídeo ou volta a herdar) + rota HTTP que faltava. **Não** entra: a
  página de Conexões, o menu de navegação (`build_sidebar_nav`) nem a reestruturação em abas do
  canal — outras fatias são donas disso.

## O que mudou (por arquivo)

### Domínio — `renderer/app/studio/domain/visual_style.py`
- Nova função pura `effective_style_id(channel_style_id, video_style_id) -> str | None`: o override
  do vídeo tem precedência sobre o do canal; sem override vale o do canal; sem nenhum, `None`
  (padrão do estúdio). É a mesma precedência do `resolve_style`, aqui sobre as **chaves** — o
  suficiente para a tela dizer de quem um vídeo herda sem carregar os parâmetros.

### Aplicação (nova) — `renderer/app/studio/application/video_style.py`
- `VideoStyleView`: `video_id`, `project_id`, `override_style_id` (None = herda),
  `channel_style_id`, `inherited_style_name` (nome do estilo do canal, ou None), `styles`
  (biblioteca ativa) e as propriedades `inherits_from_channel` / `effective_style_id`.
- `BuildVideoStyleView(videos, channels, styles)`: resolve `videos.get_video` → canal do projeto
  (`channels.get_by_project`) → nome do estilo do canal; devolve `None` se o vídeo não existe.
  Um estilo **fora da lista ativa** (ex.: arquivado depois) que esteja no canal ou no vídeo é
  **acrescentado** à lista para a opção atual nunca "virar" nenhum.
- `SetVideoStyle(videos)`: grava/limpa o override via `VideoRepository.set_video_style`
  (`None` do repo = vídeo inexistente; `VisualStyleNotFound` = estilo inexistente).
- Dependem **só** de portas e do domínio; sem I/O. Fiação vive em `composition.py`.

### Aplicação — `renderer/app/studio/application/channels_page.py`
- `ChannelsPageView.styles: tuple[VisualStyle, ...]` (biblioteca ativa real).
- `BuildChannelsPage` ganha `list_styles` (`ListVisualStyles`) e `get_style` (`GetVisualStyle`)
  **opcionais** (keyword-only). O seletor do canal lê a biblioteca pelo **caso de uso** — a tela
  nunca fala com o banco. Se o canal aponta para um estilo fora da lista ativa, ele é buscado e
  acrescentado.

### Aplicação — `renderer/app/studio/application/use_cases.py`
- `UseCases` ganha, **no fim** do dataclass (casando com a construção posicional de `from_repo`),
  `set_video_style` e `video_style_view`.

### Fiação — `renderer/app/studio/composition.py`
- `SetVideoStyle(repo)` e `BuildVideoStyleView(repo, channel_repo, style_repo)` injetados em
  `UseCases.from_repo`; `BuildChannelsPage` recebe `ListVisualStyles(style_repo)` e
  `GetVisualStyle(style_repo)`. **Wiring só aqui.**

### API — `renderer/app/studio/api/routes.py`
- Modelo `VideoStyleIn { style_id: str | None }`.
- `PATCH /videos/{video_id}/style` (`response_model=Video`): fixa / limpa o override. Vídeo
  inexistente → **404**; estilo inexistente → **422** com a mensagem do domínio (a rota captura
  `VisualStyleNotFound`, que o guard global mapearia a 404 na biblioteca); `null` → limpa.
- `GET /panel/videos/{video_id}` passou a montar a projeção (`uc.video_style_view.execute`) e
  entregá-la a `render_video(detail, style_view=...)`.

### Tela do canal — `renderer/app/studio/api/panel_channels.py`
- `_appearance_card(view)`: card **Aparência** entre "Estratégia e identidade" e "Providers".
  Um `<select id="canal-estilo" name="style_id">` com `<label for>` e `aria-describedby` na dica;
  a primeira opção é **"Segue o padrão do estúdio (nenhum estilo)"** (ausência de estilo **não é
  erro**, §6) e cada estilo da biblioteca vira uma opção. O estilo atual sai **selecionado**.
- Botão **Salvar aparência** (`PATCH /channels/{id}` com `expected_version` + `changes.style_id`)
  e link **"Criar novo estilo" → `/studio/panel/estilos`**. Feedback em
  `role="status" aria-live="polite"`; 409 = corrida vencida; erro do servidor aparece como
  mensagem, sem stack trace.
- Sem perfil ainda: o seletor aparece **desabilitado** com o motivo real ("Crie o perfil do canal
  para escolher um estilo") — o vazio ensina o próximo passo.
- **Nenhum campo inventado**: não há "Avançado" de canal nesta tela porque não existe ajuste raro
  de canal a esconder.

### Tela do vídeo — `renderer/app/studio/api/panel.py`
- `render_video(view, *, style_view=None)`: mudança compatível (o parâmetro é opcional; as páginas
  de teste que constroem `VideoDetailView` direto continuam funcionando).
- `_video_style_card(style_view)`: card **"Estilo deste vídeo"** com `<select id="video-estilo">`
  cuja opção padrão é **"Herdar do canal (<nome do estilo do canal>)"** (ou "(nenhum estilo)") e
  cada estilo da biblioteca. **Explicita de quem o vídeo herda hoje** ("Este vídeo herda o estilo
  do canal: X." / "…não usa estilo…" / "Este vídeo sobrepõe o canal com Y (o canal herda Z).").
- **Salvar estilo** envia `PATCH /videos/{id}/style` com `style_id` ou `null` (herdar). Feedback
  `role="status" aria-live="polite"`; 404 e 422 viram mensagem. Sem a projeção, a seção **não
  aparece** ("o que não tem medição não aparece").

### Testes
- **`tests/test_video_style_api.py` (novo, 11)**: `PATCH` fixa e limpa (round-trip incl. persistência
  no repo); estilo inexistente → 422 sem stack trace e nada gravado; vídeo inexistente → 404; auth
  obrigatória; a página do vídeo mostra "herda do canal (nome)" com o estilo do canal **certo**
  (projeto com dois canais), mostra o override selecionado quando definido, e "nenhum estilo" quando
  o canal não tem; contrato de UX do vídeo com a Aparência; projeção pura (`effective_style_id` e
  `BuildVideoStyleView`, incl. estilo arquivado representável).
- **`tests/test_channels_page.py` (+4)**: o `select` traz o estilo atual **selecionado** e o link
  para Estilos; sem estilo a opção "padrão do estúdio" fica selecionada; `<label for>` +
  `aria-describedby` + `role="status" aria-live="polite"` e nenhum `<details open>`; sem perfil, o
  vazio ensina o próximo passo. As duas primeiras também passam pelo `assert_ux_contract`.

## Testes — antes/depois e comando

| Arquivo | Antes | Depois |
| --- | --- | --- |
| `tests/test_video_style_api.py` | — | 11 |
| `tests/test_channels_page.py` | 32 | 36 |
| demais arquivos tocados | (inalterados) | (inalterados) |

Resultado da suíte focada: **196 passed, 1 skipped** (o skip é o teste de filtro JS de
`tests/test_panel.py:513`, que exige Node.js ausente no container — pré-existente).

### Comando

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/vs05b-channel-style
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_panel.py tests/test_panel_page.py tests/test_channels_page.py tests/test_channel_api.py \
  tests/test_styles_page.py tests/test_styles_api.py tests/test_video_style.py tests/test_video_style_api.py \
  tests/test_repo.py tests/test_architecture.py tests/test_composition.py tests/test_contracts_snapshot.py \
  tests/test_ux_contract.py
```

## Arquitetura

- `domain`/`application` seguem **puros**: a projeção e o caso de uso dependem só de portas; a
  precedência "vídeo sobrepõe canal" virou função pura no domínio. A API fala só com casos de uso
  (`_need`) e **não** constrói repositório. `tests/test_architecture.py` verde.
- `VideoOut`/contrato **não** mudou: `GET /videos/{id}` já devolve `Video` (que já tem `style_id`),
  e o novo `PATCH` usa o mesmo modelo — `tests/test_contracts_snapshot.py` verde sem regenerar.

## Modern Web Guidance (skill obrigatória de HTML/CSS/JS)

- **`forms`**: `<label for>` explícito empilhado acima de cada `<select>`; `aria-describedby` para a
  dica; `role="status" aria-live="polite"` no feedback; `:focus-visible` preservado; e a regra
  "DON'T auto-submit a form when a user changes `<select>`… without an explicit submit action" — o
  seletor sempre tem um botão de salvar, nada salva só por mudar de opção.
- **`select-menu-interaction`**: avaliado; **não aplicado**, porque o vazio ("nenhum estilo") é uma
  escolha **válida** neste caso (a ausência não é erro, §6) — nada de `required`/`:user-invalid` num
  seletor opcional. Os guias foram consultados no início da tarefa.

## Limitações / não feito (e o que ficou de fora)

- **Abas do canal (§5.2)**: entreguei a seção **Aparência** como um card, sem reescrever a tela do
  canal em abas (Identidade/Publicação/Custos) — por instrução, "acrescentar a seção sem reescrever
  o resto"; as abas são de outra fatia.
- **Página de Conexões e menu de navegação**: não tocados (outra fatia é dona); nenhum item de menu
  foi adicionado.
- **O render ainda usa só o estilo do canal**: `composition._style_for_project` chama
  `resolve_style(profile, style)` sem o `override` do vídeo. Esta fatia fecha o "pode sobrepor" **na
  interface** (API + telas); ligar o override no render é trabalho separado e não estava no escopo.
- **Observação real, não corrigida**: `PostgresVisualStyleRepository.archive` marca
  `visual_styles.archived` mas **não** limpa `channel_profiles.style_id` — o docstring do §5.3 diz que
  "os canais que usavam voltam ao padrão do estúdio", o que não acontece hoje no banco. Não corrigi
  (é território do VS-05a); a tela, porém, mantém a opção atual representável com o nome real.
- **Sem preview de estilo** e **sem percentual**: nada inventado (§7.6).
- Não rodei a suíte inteira (VM apertada); árvore limpa; sem `git add -A`, sem push/merge.
