# YT-04b — Página "Conexões" (conta Google → canais do YouTube)

- **Data:** 2026-11-21
- **Fatia:** YT-04b (a **página** do painel; serviço + API são a YT-04a)
- **Branch:** `feat/yt04b-connections-page` (worktree isolado `/…/worktree/39a258/yt04b-connections-page`; sem push/merge)
- **Base:** `6df1762` (`merge: seletor de estilo no canal + override no video (VS-05b)`)
- **Entrega:** sim — página `GET /panel/conexoes`, item de menu em **Gestão**, testes verdes.
- **Desenho:** `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` §4, §5.4, §6, §7;
  `docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md`.

---

## Objetivo

Entregar a **metade visual** do fluxo que a YT-04a deixou pronta como serviço + API: a tela que
mostra **conta → canais**, conecta uma conta (OAuth), **confirma o canal escolhido antes de
vincular**, vincula/desvincula o canal do estúdio e **revoga uma autorização isoladamente** — com o
critério do dono: **não pesada e fácil**, com vazio que ensina e nada inventado.

---

## Arquivos

| Arquivo | Estado | O que é |
|---|---|---|
| `renderer/app/studio/api/panel_connections.py` | **novo** | `render_connections(board, profiles) -> (html, headers)`, no molde de `panel_styles.py`: casca aprovada, estado vazio que ensina, hierarquia conta → canais, confirmação do canal antes do vínculo, `<dialog>` nativo para ações destrutivas e script que chama a API existente. |
| `renderer/app/studio/api/panel.py` | alterado | `_NAV_ICONS['conexoes']` (ícone de elo) + item **Conexões** em **Gestão**, entre Estilos e Equipe, `active="conexoes"`/`aria-current="page"`. Estilos/Equipe intactos; nenhum item morto recriado. |
| `renderer/app/studio/api/routes.py` | alterado | Import de `render_connections` + rota `GET /panel/conexoes` (`HTMLResponse`). Reusa os casos de uso já fiados (`list_connections`, `list_channel_profiles`) — **nenhum** caso de uso ou _wiring_ novo. |
| `tests/test_connections_page.py` | **novo** | 14 testes da página (contrato de UX, vazio, conta→canais, menu, confirmação antes do vínculo, destrutivas em `<dialog>`, retorno OAuth, XSS, CSP, auth). |
| `docs/backlogs/…/gestao/relatorios/YT-04b.md` | **novo** | Este relatório. |

**Nada foi removido.** O serviço/API da YT-04a e o fluxo antigo por projeto continuam intactos.

---

## O que foi feito

### 1. A página — `api/panel_connections.py` (novo)

- **Estado vazio que ensina** (§6): "Nenhuma conta conectada" + botão **Conectar conta Google** +
  o card **"O que será pedido"** com os escopos em linguagem clara (`youtube.upload` = subir os
  vídeos; `youtube.readonly` = ler o canal/vídeos para conferir o destino).
- **Conta → canais**: cada conta do Google agrupa seus canais; por canal, o **status** derivado
  (Conectado / Expirado / Revogado / Sem credencial / Erro), a **validade** ("expira em … UTC" ou
  "validade não informada") e **quem publica ali** ("Publica em: …" com o canal do estúdio), lidos
  do mesmo `ListConnections` do `GET /connections`.
- **Confirmação antes do vínculo** (§5.4): o bloco de vínculo mostra **nome + id** do canal do
  YouTube e o aviso "Confira o destino antes de vincular" **antes** do controle de vínculo; a
  escolha do canal do estúdio é um `<select>` rotulado, e o botão é **"Confirmar e vincular"**.
- **Vincular/desvincular** usam o `PATCH /studio/channels/{profile_id}` **já existente**
  (`link_studio_channel`/`unlink_studio_channel` não ganharam rota nova). O `expected_version` vem
  do perfil e o `409` de corrida é tratado com mensagem honesta.
- **Revogar** chama `POST /studio/connections/authorizations/{grant}/{yt}/revoke`, **isolado**.
- **Ações destrutivas** (revogar, desvincular) passam por um **`<dialog>` nativo** com o **efeito
  explícito** no texto, **Cancelar** com foco inicial (`autofocus`) e botão de confirmação — nenhuma
  ação destrutiva ocorre num clique acidental.
- **Retorno do OAuth pela query string**: ao carregar, a página lê `?code`/`?state` (e `?error`),
  conclui o consentimento via `POST /studio/connections/oauth/callback` e volta para
  `?conectado=<ytid>`, já com o bloco de confirmação aberto; `code`/`state` **nunca** são
  renderizados pelo servidor.

### 2. Acessibilidade / UX

- Um único `<h1>`; `<label for>` no seletor; `aria-describedby` nas dicas; resultados num único
  `role="status" aria-live="polite"`; foco visível (`:focus-visible` da casca); `<dialog>` modal faz
  o trabalho de inércia/foco/`Esc` sem focus-trap manual; SVGs decorativos com `aria-hidden`.
- Sem preview falso e sem percentual (§7.6); o que a API não traz vira "não disponível"/"não
  informado".

### 3. Menu — `api/panel.py`

Item **Conexões** promovido a destino real em **Gestão** (entre Estilos e Equipe), com ícone novo
em `_NAV_ICONS` e `active="conexoes"`. Nenhum item existente reordenado; o item morto
"Configurações" **não** foi recriado.

---

## Testes

Arquivo novo: **`tests/test_connections_page.py` (14)**.

Antes (suíte focada, sem o novo arquivo): **122 passam**.
Depois (a mesma suíte + o novo arquivo): **136 passam, 1 pulado**.

Cobertura do arquivo novo: contrato de UX no vazio e com dados; "Nenhuma conta conectada" + botão +
escopos; conta/canal/status/"Publica em:" com o canal do estúdio; "nenhum canal publica aqui ainda"
honesto; nada de preview/%/`progressbar`; XSS de dado real escapado; menu com **Conexões ativo** em
Gestão e sem "Configurações"/"em breve"; **confirmação do canal (nome+id) antes do vínculo**; ações
destrutivas em `<dialog>` com foco seguro; retorno OAuth pela query string e vínculo pelo
`PATCH /channels` existente; token fora do HTML; CSP + `no-store`; auth obrigatória.

### Comando

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/yt04b-connections-page
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-a:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_connections_page.py tests/test_connections_api.py tests/test_connections_service.py \
  tests/test_styles_page.py tests/test_panel.py tests/test_ux_contract.py tests/test_architecture.py \
  tests/test_composition.py tests/test_channels_page.py
```

Resultado: **136 passed, 1 skipped** — inclui `test_architecture.py` verde (domínio/aplicação puros;
API sem `psycopg`/adaptador) e `test_composition.py` verde.

---

## Arquitetura / wiring

- **Nenhum _wiring_ novo.** A rota da página reusa `uc.list_connections` (mesma fonte do
  `GET /connections`) e `uc.list_channel_profiles` (já fiado no `composition.py`). `composition.py`,
  `use_cases.py` e o serviço da YT-04a ficaram **intocados**.
- `panel_connections.py` importa `panel` como `shell` (api→api) e `..domain.channel` (api→domain),
  como `panel_channels.py`/`panel_styles.py`. Nenhum import de adaptador/`psycopg` na API.

## Modern Web Guidance (skill obrigatória de HTML/CSS/JS)

- **`dialog`**: as ações destrutivas usam o **`<dialog>` nativo** (`showModal()`), nomeado por
  `aria-labelledby`, com `<form method="dialog">` e **`autofocus` na ação segura** (Cancelar) e
  `overscroll-behavior: contain` em `dialog:modal`/`::backdrop`, sem `role="dialog"`/focus-trap
  manual ("DON'T add `role="dialog"`, `aria-modal`… to a native modal").
- **`accessibility`**: `<label for>`/`id`, dicas acima do controle via `aria-describedby`,
  `role="status" aria-live="polite"` para o resultado (live region `polite` = status, não
  `assertive`), um único `<h1>`, landmarks `aria-label` distintos, SVGs decorativos `aria-hidden`.

## Limitações / não feito (registrado, não escondido)

- **Retorno real do Google (redirect_uri):** a YT-04a usa o mesmo `google_oauth_redirect_uri`
  compartilhado (`http://localhost:8000/studio/oauth/callback`). Hoje, o Google devolve o
  navegador para a **página de callback existente** (do fluxo antigo F8-05), e não para
  `/studio/panel/conexoes`. A página **trata o retorno** pela query string (o que a fatia pediu) e
  funciona assim que o retorno apontar para ela (por exemplo, um `redirect_uri` de Conexões
  registrado no app OAuth igual a `/studio/panel/conexoes`). **Não** alterei a página de callback
  compartilhada: um teste existente fixa o comportamento dela para `state` desconhecido
  (`tests/test_channels_page.py::test_oauth_callback_page_refuses_an_unknown_state_without_dead_end`)
  e o `state` de Conexões é opaco — indistinguível de lixo por formato. Fechar esse ponto é uma
  decisão de configuração/integração (fora do escopo desta fatia de página).
- **Sem prova ponta-a-ponta com o Google real:** o `OAuthClient` segue como duplo nos testes; o
  Google nunca é chamado (mesmo padrão da YT-04a). O e-mail da conta continua dependente do escopo
  (limite herdado da YT-04a).
- **`token_expires_at`/`validated_at`**: exibidos só quando presentes; sem eles, a tela diz "não
  informado" em vez de inventar.
- Não rodei a suíte inteira (VM apertada); árvore limpa; sem `git add -A`; sem push/merge.
