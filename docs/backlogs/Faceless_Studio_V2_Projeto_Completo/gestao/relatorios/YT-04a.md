# YT-04a — Serviço + API de Conexões (conta Google → autorizações → canais do YouTube)

**Data:** 2026-11-21
**Fatia:** YT-04a (serviço + API da identidade nova; **sem** painel)
**Base:** `759fe71` (`merge: biblioteca de Estilos (API + tela + menu) (VS-05a)`)
**Branch:** `feat/yt04-connections` (worktree isolado `/…/worktree/39a258/yt04-connections`; sem push/merge)
**Entregue:** sim — casos de uso, rotas JSON, _wiring_ só em `composition.py` e testes verdes.
**Fora desta fatia:** a página "Conexões" + item de menu é a **YT-04b** (outra fatia).

---

## Objetivo

Entregar o **serviço** e a **API** que faltam à identidade nova do desenho
(`docs/superpowers/specs/2026-11-21-youtube-account-grants-design.md`): conectar uma **conta
Google**, completar o consentimento (conta + autorização + **canal escolhido**), listar o que
está conectado, vincular um **canal do estúdio** a um canal do YouTube e **revogar** uma
autorização isoladamente. Nada de painel/HTML/menu; `api/panel.py` e `build_sidebar_nav`
intocados.

---

## Arquivos

| Arquivo | Estado | O que é |
|---|---|---|
| `renderer/app/studio/application/connections.py` | **novo** | Casos de uso: `BeginAccountConsent`, `CompleteAccountConsent`, `ListConnections`, `LinkStudioChannel`, `Unlink`, `RevokeAuthorization` (+ erros nomeados e escopos do cofre). Só portas. |
| `renderer/app/studio/domain/youtube_oauth.py` | alterado | `OAuthIdentity` ganha `email` opcional (identidade da **conta** quando o consentimento a expõe); aditivo, ignorado pelo fluxo antigo. |
| `renderer/app/studio/application/use_cases.py` | alterado | 6 campos novos no `UseCases` (`list_connections`, `begin_account_consent`, `complete_account_consent`, `revoke_authorization`, `link_studio_channel`, `unlink_studio_channel`) + `from_repo`. |
| `renderer/app/studio/api/routes.py` | alterado | Modelos pydantic + 4 rotas JSON de Conexões + mapeamento de erros (422/404). |
| `renderer/app/studio/composition.py` | alterado | Wiring: 4 repositórios da identidade nova + os 6 casos de uso ligados no `UseCases`. |
| `tests/test_connections_service.py` | **novo** | 11 testes do serviço com duplos das portas (sem rede, sem banco). |
| `tests/test_connections_api.py` | **novo** | 4 testes HTTP com Postgres descartável e `OAuthClient` duplo (nunca chama o Google). |

**Nada foi removido.** O fluxo antigo por projeto (`application/youtube_oauth.py` +
`/projects/{id}/youtube-oauth/...`, escopo `youtube:{project_id}`) continua de pé e verde.

---

## O que foi feito

### 1. Serviço — `application/connections.py` (novo)

- **`BeginAccountConsent`** — gera URL de autorização + `state` (PKCE S256), guardando
  `state`/`code_verifier`/validade no cofre, no escopo `oauth_consent:{state}` (um consentimento
  por `state`, o que permite várias contas em voo). Escopos: **os mesmos do fluxo antigo**
  (`DEFAULT_SCOPES`: `youtube.upload` + `youtube.readonly`) — nenhum escopo inventado.
- **`CompleteAccountConsent(code, state, *, email=None)`** — valida `state`/validade/verifier,
  troca o código, lê a **identidade** (`oauth.identity` → canal do YouTube escolhido no
  consentimento) e grava, em sequência: `upsert` da **conta** (por e-mail, sem caixa — reconectar
  o mesmo e-mail **não duplica**), `upsert` da **identidade do canal**, `create` da
  **autorização**, e `link` do **vínculo validado** com `validated_at` (existir a linha já afirma
  que houve conferência). Os tokens vão **só para o cofre**, por autorização
  (`oauth_grant:{grant_id}`); a resposta devolve conta + canal + status, **sem token**.
- **`ListConnections`** — o quadro **real**: conta → canais (lidos do **nosso banco**, **sem
  chamada ao vivo**) → status derivado do cofre + do vínculo → **qual canal do estúdio publica
  ali** (join com `channel_profiles.youtube_channel_id`). Status nunca é presumido: sem credencial
  → `DISCONNECTED`, vencido → `EXPIRED`, revogado → `REVOKED`.
- **`LinkStudioChannel(profile_id, youtube_channel_id)` / `Unlink(profile_id)`** — aponta/limpa o
  destino do canal do estúdio, recusando canal do YouTube nunca validado (`ChannelYouTubeTargetNotFound`).
- **`RevokeAuthorization(grant_id, youtube_channel_id)`** — marca **só aquele vínculo** como
  `REVOKED`. Só revoga no Google e apaga os tokens da autorização quando **nenhum outro** vínculo
  vivo a usa (o modelo absorve um grant com vários canais); as **outras** autorizações da conta
  ficam intactas. Idempotente.

### 2. API — `api/routes.py` (só JSON)

| Método | Rota | Notas |
|---|---|---|
| `GET` | `/studio/connections` | Conta → canais + status + canais do estúdio que publicam ali. |
| `POST` | `/studio/connections/oauth/start` | Devolve `authorization_url` + `state` (+ `expires_at`). |
| `POST` | `/studio/connections/oauth/callback` | Corpo `{code, state, email?}` → conta + canal + `grant_id` + status. |
| `POST` | `/studio/connections/authorizations/{grant_id}/{youtube_channel_id}/revoke` | Revoga aquele vínculo. |
| `PATCH` | `/studio/channels/{profile_id}` | **reusada** para o vínculo do canal (já aceitava `youtube_channel_id`) — nenhuma rota redundante criada. |

Erros: alvo inexistente (canal do estúdio, vínculo) → **404**; referência/estado inválidos
(`state` ruim/expirado, id malformado, e-mail sem cara de e-mail, destino não validado) → **422**.
Nenhuma resposta carrega token nem client secret; nada de stack trace.

### 3. Wiring — só em `composition.py`

Os **4 repositórios** da identidade nova (`PostgresGoogleAccountRepository`,
`PostgresOAuthGrantRepository`, `PostgresYouTubeChannelIdentityRepository`,
`PostgresChannelAuthorizationRepository`) são construídos na raiz de composição e injetados nos
casos de uso, que entram no `UseCases`. O mesmo repositório de vínculos é reusado pelo gate de
publicação (YT-03). Sem app OAuth configurado, `begin`/`complete` ficam `None` (a API responde
503) e a revogação local continua disponível (sem revogar no Google).

---

## Decisões e limites (honestos)

1. **Transação:** os repositórios da casa abrem **uma conexão/transação cada** (não há unidade de
   trabalho entre repositórios). O caso de uso grava na ordem conta → canal → autorização →
   vínculo (o **vínculo validado por último**) e só então escreve os **tokens no cofre**: uma falha
   deixa, no pior caso, metadados sem credencial — que o status deriva honestamente como
   `DISCONNECTED` — e **nunca** token órfão. Fazer uma transação de banco única exigiria alterar os
   adaptadores (fora do escopo desta fatia).
2. **E-mail da conta:** o desenho é **conta → autorizações → canais** e o e-mail é a identidade da
   conta. `OAuthIdentity` ganhou `email`, lido do consentimento. Com **só** os escopos antigos
   (`youtube.upload`/`youtube.readonly`), o Google **não** expõe o e-mail da conta (o endpoint
   userinfo exige `openid`/`userinfo.email`), então o adapter concreto ainda devolve `email=""`.
   Por isso o callback aceita um `email` **opcional** como reserva, mas a identidade do
   consentimento tem precedência. Sem nenhuma das duas, o serviço **recusa** (`AccountIdentityUnavailable`,
   422) em vez de inventar conta. Habilitar o e-mail real exige um escopo com e-mail (decisão fora
   desta fatia, coerente com o YT-05). Ver "o que ficou de fora".
3. **Preferência de grant:** cada consentimento cria uma **autorização nova** e o vínculo validado
   daquele canal; reconectar o mesmo canal acumula autorizações (o item aberto "preferência de
   grant" do quadro segue em aberto — o resolvedor devolve a primeira na ordem).
4. **`LinkStudioChannel`/`Unlink`** existem como serviço (e estão ligados no `UseCases`), mas o
   **caminho HTTP do vínculo é o `PATCH /channels/{profile_id}` existente** — não se criou rota
   redundante, conforme a orientação.

---

## Testes

**Antes:** suíte focada obrigatória (8 arquivos) = **103 passam**.
**Depois:** a mesma suíte + os dois arquivos novos = **118 passam** (+11 do serviço, +4 da API).
Verificação extra (rotas/UI afetadas pelo acréscimo, sem regressão): `test_channels_page`,
`test_styles_page`, `test_styles_api`, `test_publication_api`, `test_studio_api`,
`test_project_config_validation`, `test_team_admin_api`, `test_panel_api`, `test_category_api`
= **127 passam**; publicação/segredos (`test_publication_execution`, `test_workflow_publish`,
`test_publishing`, `test_channel_secrets`) = **78 passam, 30 pulados**. `test_architecture.py` verde
(`domain`/`application` puros; wiring só em `composition.py`).

Comando real (container, Postgres **dedicado** `integ-pg-b`, prova de banco descartável):

```
REPO=/Users/rodrigomendes/.local/share/opencode/worktree/39a258/yt04-connections
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg-b:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg-b:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_connections_service.py tests/test_connections_api.py \
  tests/test_youtube_identity_repo.py tests/test_youtube_identity_domain.py tests/test_youtube_oauth_service.py \
  tests/test_channel_api.py tests/test_channel_repo.py tests/test_architecture.py tests/test_composition.py tests/test_db.py
```

O `OAuthClient` é um **duplo** nos testes; o Google real **nunca** é chamado (mesmo nos testes de
API, por injeção do duplo no wiring).

### O que os testes provam

- **`CompleteAccountConsent`**: cria conta/autorização/canal/vínculo; `validated_at` gravado no
  vínculo; tokens no cofre por `grant_id` e **ausentes** da resposta; reconectar o mesmo e-mail
  (outra caixa) **não duplica** a conta e gera autorização independente; `state` errado/expirado/malformado
  recusado **antes** de chamar o provedor; consentimento sem e-mail **não inventa** conta.
- **`ListConnections`**: mostra conta → canais → `studio_channels` (quem publica ali) e deriva o
  status **do cofre** (sem credencial → `DISCONNECTED`; vencido → `EXPIRED`; revogado → `REVOKED`).
- **`RevokeAuthorization`**: revoga **só** aquele vínculo; o outro canal da mesma conta segue
  `CONNECTED`; tokens do grant revogado apagados e os do outro preservados; idempotente; 404 no
  vínculo inexistente.
- **API**: round-trip completo dos endpoints, `PATCH /channels` vinculando o canal do estúdio,
  token fora das respostas, **422** para estado/referência inválidos e **404** para alvo
  inexistente, e 401 sem autenticação.

---

## O que ficou de fora (registrado, não escondido)

- **A página "Conexões" e o item de menu — YT-04b.** Esta fatia entrega só serviço + API; nada de
  `api/panel.py`, HTML ou menu.
- **E-mail real da conta:** com os escopos atuais (`youtube.upload`/`youtube.readonly`) o Google
  não expõe o e-mail; a conclusão do consentimento em produção fica dependente de o app OAuth
  passar a conceder um escopo com e-mail e de o adapter (`GoogleOAuthClient.identity`) preenchê-lo
  (ou do callback informar `email`, já suportado). Sem isso, `CompleteAccountConsent` responde 422
  `AccountIdentityUnavailable`. É o único ponto que impede um fluxo ponta-a-ponta com o Google real.
- **Transação única de banco** entre os quatro repositórios (ver decisão 1).
- **Preferência de grant** quando há várias autorizações `CONECTADAS` para o mesmo canal (item
  aberto do quadro; segue para a YT-04b/YT-05).
- **`LinkStudioChannel`/`Unlink`** vinculam por `profile_id`; o caminho HTTP é o `PATCH` existente.
