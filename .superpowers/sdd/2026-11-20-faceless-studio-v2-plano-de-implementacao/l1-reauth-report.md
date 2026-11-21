# L1 — Ligação do botão "Reautorizar" ao OAuth real (relatório)

Worktree `l1-reauth`, branch `feat/l1-reauth`, base `be07d53` (merge da F8), sem push e sem merge.
Postgres descartável próprio (`l1-pg`, rede `l1-net`, prova de 64 hex em `/budget-test-proof/proof`
montada com `-v`). Passadas **as duas** DSNs (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`)
mais `STUDIO_BUDGET_TEST_PROOF_FILE`; imagem `faceless-v2-hygiene-test-local:latest`,
`-p no:cacheprovider`. Nenhuma migração nova. Nenhum arquivo da fatia `ligacoes` nem do núcleo de
render foi tocado.

## O que estava falso

`renderer/app/studio/api/panel_channels.py:521-524` (no base) dizia, em produção, que o fluxo de
consentimento OAuth "não está implementado nesta versão" e o botão "Reautorizar" era um `<span>`
`is-disabled`/`aria-disabled`. Isso ficou **falso** na F8 (`be07d53`): as rotas
`POST .../youtube-oauth/{authorize,callback,refresh,revoke}` existem em `api/routes.py:1538-1556`.
A tela passou a negar uma capacidade real.

## O que foi feito (ligar de verdade, com honestidade)

### 1. A projeção expõe a disponibilidade real — `application/channels_page.py`

- `OAUTH_UNAVAILABLE_REASON` (`channels_page.py:33`): motivo real quando falta o app do Google.
- `ChannelsPageView` ganhou `oauth_available`, `oauth_unavailable_reason`, `oauth_authorize_path`,
  `oauth_revoke_path` (`channels_page.py:58-61`).
- `BuildChannelsPage.__init__` recebe `oauth_available` (`channels_page.py:74-85`) e `execute`
  monta os caminhos `/studio/projects/{id}/youtube-oauth/{authorize,revoke}` só quando disponível
  (`channels_page.py:113-131`); caso contrário devolve o motivo real.

**Como a tela descobre se o OAuth está disponível (arquivo:linha):**
`renderer/app/studio/composition.py:406` monta `oauth_client = build_google_oauth(s)` e
`composition.py:478` passa `oauth_available=oauth_client is not None` para o `BuildChannelsPage`.
É a **mesma** fonte de verdade que decide se `UseCases.begin_youtube_oauth` existe
(`composition.py:407-416`: `begin_oauth = BeginConsent(...)` só quando há `oauth_client`). Ou seja, o
flag do botão e o endpoint real concordam por construção — sem botão prometendo um 503.

### 2. Botão real chama o endpoint — `api/panel_channels.py`

- `_oauth_controls(view, status)` (`panel_channels.py:470-509`) renderiza:
  - disponível: `<button id="youtube-reauth" data-authorize-path="...">` (rótulo por estado) e, quando
    `CONNECTED`, `<button id="youtube-revoke" data-revoke-path="...">Revogar acesso</button>`;
  - indisponível: `<span class="btn ... is-disabled" aria-disabled="true" tabindex="-1">` **com o
    motivo real** (nunca "não está implementado").
- JS no `<script>` do painel (`panel_channels.py:875-930`), no mesmo estilo do form de orçamento:
  `POST` no `data-authorize-path`, lê `authorization_url` e faz `window.location.href = url`
  (redireciona o browser ao Google). O `revoke` faz `POST` e recarrega.
- Estados conforme `_OAUTH_STATE`: `DISCONNECTED` → "Conectar"; `EXPIRED`/`REVOKED`/`ERROR` →
  "Reautorizar"; `CONNECTED` → "Reconectar" + "Revogar acesso".
- O rail mostra "Fluxo de consentimento: disponível/indisponível no servidor" (`panel_channels.py:629`).

### 3. Callback — página implementada — `api/panel_oauth.py` + `api/routes.py`

Google redireciona para `redirect_uri` = `http://localhost:8000/studio/oauth/callback`
(`application/youtube_oauth.py:41`, `composition.py:245`). **Essa rota HTML não existia.** Foi
criada:

- `GET /studio/oauth/callback` em `api/routes.py:1056-1065` → `render_oauth_callback(...)`.
- `api/panel_oauth.py` (novo, 153 linhas) usa a casca aprovada (`render_sidebar`) e cobre:
  - sucesso: o browser lê `code`/`state` da própria URL e chama
    `POST /studio/projects/{id}/youtube-oauth/callback`; mostra o canal associado e volta para Canais;
  - `error=access_denied` (recusa do Google): renderizado **pelo servidor**, honesto mesmo sem JS;
  - `state` irreconhecível: explica que a conexão precisa ser refeita, com link para Canais.

**Decisão do callback — como a página sabe o projeto.** O `redirect_uri` não carrega o projeto e o
Google exige `redirect_uri` exatamente registrado (o adaptador valida igualdade em
`adapters/google_oauth.py:129-131`), então não dá para acrescentar `?project_id=`. A solução foi
embutir o id **no `state`**, que já é opaco e já é comparado pelo fluxo:
`state = f"{p_id}.{token_urlsafe(32)}"` (`application/youtube_oauth.py:135`) e o helper
`consent_project_id(state)` (`youtube_oauth.py:45-63`) extrai o projeto (32 hex) no callback. O nonce
aleatório continua intacto e o `compare_digest` do `CompleteConsent` não muda. Não é segredo: o id
do projeto já aparece na própria URL da tela.

### 4. Copy e segredos

- A copy do card deixou de negar o fluxo; a garantia "Nenhum valor de credencial (access token,
  refresh token, client secret ou máscara) volta para o browser" foi mantida (e testada).
- `_headers` mantém CSP com nonce e `connect-src 'self'`; a `authorization_url` (que contém o
  `client_id` público) **não** é renderizada no HTML — só é buscada no clique.

## Testes (TDD RED→GREEN)

- RED: o teste antigo `test_youtube_disconnected_state_and_unimplemented_oauth_are_explicit`
  afirmava `"não está implementado" in visible` — passou a **falhar** quando a copy foi corrigida.
  Foi substituído.
- Novos/reescritos em `tests/test_channels_page.py`:
  - sem OAuth no servidor: botão desabilitado, **sem** `id="youtube-reauth"`, **sem**
    `data-authorize-path`, com o motivo "não configurado no servidor" e **sem** "não está implementado";
  - com OAuth: botão ativo apontando para `.../youtube-oauth/authorize`; o endpoint devolve URL do
    Google (`access_type=offline`, `code_challenge_method=S256`) e `state` começando pelo projeto;
  - `CONNECTED` → "Reconectar" + "Revogar acesso" (com `data-revoke-path`);
  - `EXPIRED` → "Reautorizar";
  - callback: carrega o projeto, fecha o loop, **não** renderiza o `code`; estado desconhecido e
    `access_denied` sem beco sem saída;
  - vazamento: `your_client_secret`, `ya29.synthetic-access-value`, `1//refresh-secret`,
    `SYNTHETIC-code` e `••••` ausentes no HTML das duas páginas.
- `tests/test_youtube_oauth_service.py`: teste novo do `consent_project_id` e do formato do `state`.
- Também rodados: `test_ux_contract.py`, `test_architecture.py`, `test_panel.py`, `test_panel_page.py`,
  `test_publication_api.py`, `test_composition.py`, `test_db.py`, `test_channel_api.py`,
  `test_channel_backend_repo.py`, `test_youtube_channel.py`, `test_channel_secrets.py`,
  `test_publish_api.py`, `test_publishing.py`.

### Contagens reais (Postgres `l1-pg`, as duas DSNs, prova)

| Conjunto | Resultado |
|---|---|
| `tests/test_channels_page.py` | **32 passed** |
| `test_youtube_oauth_service.py` + `test_channels_page.py` | **43 passed** |
| ux/arch/panel/panel_page/youtube_oauth/composition/publication_api | **155 passed, 1 skipped** |
| db/channel/publish (focados, Postgres) | **105 passed** |
| **Suíte completa** (serializada, ambas DSNs + prova) | **2315 passed, 35 skipped, 3 failed** em 229 s |

Os 35 skips são os de ambiente (Node.js/ffmpeg), o mesmo número das fatias anteriores: os ~100 testes
de orçamento **não** foram pulados (as duas DSNs estavam definidas).

**As 3 falhas — qualificadas, nenhuma é regressão desta fatia:**

1. `test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
   `::test_extracted_starter_runs_contract_snapshot_and_backup_import` — ambientais: dentro do
   container o `.git` da worktree é *gitfile* e o `package-starter.sh` aborta com "Secret hygiene
   check could not complete safely". Mesmo par em todas as fatias anteriores. Fora do container,
   `python3 scripts/secret_hygiene.py scan` → **passed** (EXIT 0).
2. `test_tts_calibration.py::test_punctuation_adds_the_measured_pause_time` — **flakiness sob
   carga**: falhou na suíte cheia e passa **isolado** (`6 passed`). O arquivo está inalterado desde
   a base (`git diff --quiet be07d53 -- tests/test_tts_calibration.py`); não toquei em TTS.

A outra fatia rodando em partições não disputou memória nos testes focados; os módulos de render não
foram tocados.

## O que continua indisponível (e por quê)

- **Sem app OAuth no servidor** (`STUDIO_GOOGLE_CLIENT_SECRET_FILE` ausente/inválido) o botão fica
  desabilitado — correto: `begin_youtube_oauth` também seria `None` (503). O motivo agora é real
  ("falta o client secret do Google"), não uma negação do fluxo.
- **A rota de callback é fixa em `/studio/oauth/callback`.** Ela casa com o `redirect_uri` padrão e
  com o que a F8/documentação registram. Se um operador configurar outro
  `STUDIO_GOOGLE_OAUTH_REDIRECT_URI`, será preciso uma rota nesse caminho (não fiz rota dinâmica para
  não expor caminho arbitrário). Fica o registro.
- **Refresh automático** continua no backend (`EnsureAccessToken`), não é botão da tela; a tela só
  oferece reconectar/revogar, como o `_OAUTH_STATE` sugere.
- **Reordenar fallback** de providers continua não implementado (inalterado e honesto).

## Higiene e git

`python3 scripts/secret_hygiene.py scan` → **Secret hygiene check passed** (EXIT 0). Valores de teste
inequivocamente sintéticos, usando os placeholders que o próprio scanner isenta
(`your_client_secret`, `ya29.synthetic-access-value`, `1//refresh-secret`). `git add` por caminho
exato; sem `git add -A`, sem push, sem merge. Nenhum segredo impresso.

## Arquivos

```
 M renderer/app/studio/api/panel_channels.py
 M renderer/app/studio/api/routes.py
 M renderer/app/studio/application/channels_page.py
 M renderer/app/studio/application/youtube_oauth.py
 M renderer/app/studio/composition.py
 M tests/test_channels_page.py
 M tests/test_youtube_oauth_service.py
?? renderer/app/studio/api/panel_oauth.py
```

## Commits

- `feat(ligacoes): liga o botão Reautorizar ao OAuth real do YouTube (L1)` — código e testes.
- `docs(ligacoes): relatório do L1 (Reautorizar → OAuth real)` — este relatório (`git add -f`).
