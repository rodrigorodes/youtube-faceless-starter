# Fatia H — backend/HTTP de canais e providers (F10-03..07)

**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/h-canais-backend`
**Branch:** `feat/h-canais-backend` (base `51734c7`, que já tem D2 e a fatia 3)
**Commits desta fatia:**
- `35c4947` `feat(channels): backend/HTTP de canais, providers, budget e segredos (F10-03..07)`
- `315e7f8` `test(channels): F10-03..07 (catálogo/roteamento, budget hard-soft, segredos, YouTube, HTTP)`

Sem push e sem merge. Só caminhos exatos; nenhum `git add -A`.

## Escopo entregue (só backend/HTTP; a tela de Canais NÃO foi feita e segue `em breve`)

### F10-03 — providers (capabilities, custo, rate limit, disponibilidade, teste de conexão)
- `domain/provider.py` (puro): `ProviderKind`, `Availability`, `CostEstimate` (FREE/ESTIMATE/UNKNOWN),
  `ProviderImplementation` (capabilities, custo, `rate_limit_per_min`, `quality`, `validated`),
  `ProviderCard`, `card_for`, `ConnectionTestResult`, `ProviderProbeResult`.
- Regra central: **só é `AVAILABLE` com implementação validada**; sem implementação ou não validada é
  `UNAVAILABLE` com motivo. `card_for("text", "openai:gpt-4o", [])` → `no implementation for 'text:openai'`.
- `application/providers.py`: `ProviderService.list/test_connection` monta o catálogo a partir do
  `Project.config`/ambiente e das implementações; o teste de conexão roda uma **sonda** (porta
  `ProviderProbe`) e, sem sonda, devolve `available=False, checked=False` — nunca finge sucesso.
- `adapters/provider_probes.py`: `LocalProviderProbe` (local) e `HttpReachableProbe` (bridge).
- Implementações registradas em `composition.py` a partir das settings: `demo`/`placeholder`/`piper`/
  `ffmpeg` validados; `opencode` validado só com `OPENCODE_BRIDGE_TOKEN`; `stock` só com Pexels;
  `veo` **não homologado** (`validated=False`).
- HTTP: `GET /studio/projects/{id}/providers`, `POST .../providers/test`.

### F10-04 — profiles econômicos e roteamento com fallback controlado
- `EconomicProfile` (`ECONOMY`/`BALANCED`/`PREMIUM`) e `route_provider(RouteRequest, cards)` puro:
  só candidatos `AVAILABLE`; teto de custo exclui estimativa acima do teto e **custo desconhecido**
  (desconhecido não é ilimitado); devolve `primary` + `fallbacks` ordenados; sem candidato →
  `NoProviderAvailable` (nunca inventa provider).
- Ordenação por perfil: ECONOMY por custo; PREMIUM por qualidade; BALANCED por qualidade entre
  opções que não custam mais de 10× a mais barata paga (`BALANCED_COST_FACTOR`).
- HTTP: `POST /studio/projects/{id}/providers/route`.

### F10-05 — budget por canal/produção com hard e soft distintos + painel honesto
- `domain/channel_budget.py` (puro): `BudgetLimits` (hard/soft mensal e por vídeo, `soft <= hard`),
  `evaluate_budget` (WITHIN / SOFT_LIMIT / HARD_BLOCKED), `CostSummary` (Real/Estimado/Sem custo/
  Desconhecido, nunca fundidos; ausência nunca é US$ 0,00).
- **O guard da fatia A não era hard limit**: os limites vinham do chamador. Aqui o canal define os
  limites e `application/budget.py` ganhou `limits_for` — o `PaidOperationGuard` passa a consultar o
  **hard** do canal no `reserve`. O **soft** vira o teto de pausa humana do coordenador
  (`_ChannelBudgetFloor` em `composition.py`). Sem linha de budget, valem as settings (comportamento
  anterior preservado).
- `adapters/postgres/channel_budget_repo.py`: `PostgresChannelBudgetRepository` (upsert/get) e
  `PostgresChannelUsageRepository.month_summary` (soma Real/Estimado/Sem custo/Desconhecido **só dos
  vídeos do canal**, por mês; não atribuídos contados à parte).
- HTTP: `GET`/`PUT /studio/projects/{id}/budget` (devolve limites, resumo honesto e decisões).

### F10-06 — associar canal YouTube + status OAuth sem expor secrets
- `domain/youtube_channel.py`: `YouTubeChannel` + `OAuthStatus`; status **derivado** na leitura —
  sem credenciais no vault é `DISCONNECTED`, token vencido é `EXPIRED`. `public()` só devolve metadados.
- `application/youtube_channels.py`: `Get`/`Associate`/`Disconnect`. Tokens vão para o `SecretStore`
  (escopo `youtube:<project_id>`); falha do cofre vira `ServiceUnavailable` (503), não 500.
- `adapters/postgres/youtube_channel_repo.py`: só metadados (canal, título, escopos, status, expiração).
- HTTP: `GET`/`PUT`/`DELETE /studio/projects/{id}/youtube-channel`. O teste prova que
  `access_token`/`refresh_token` não aparecem em nenhuma resposta (nem a segunda leitura).

### F10-07 — configs sensíveis em secret store, nunca no `Project.config` do browser
- `domain/secrets.py`: lista branca `PUBLIC_CONFIG_KEYS` + `sanitize_project_config` (descarta chaves
  desconhecidas e qualquer coisa com cara de segredo) + `redact`.
- `adapters/secret_store.py`: `FileSecretStore` — JSON por escopo, diretório `0700`, arquivo `0600`,
  escrita atômica, recusa path traversal (`../../etc`), só lista nomes (nunca valores).
- HTTP: `GET /studio/projects/{id}/config` devolve só a lista branca; `POST /studio/projects` passou a
  usar `response_model_exclude={"config"}`. Teste: com segredo gravado em `projects.config`, a resposta
  não contém o valor.

### Extras de conclusão da fase (necessários para os endpoints funcionarem)
- HTTP de CRUD do perfil de canal (F10-01/02) — a fatia C deixou só domínio/persistência/serviço:
  `POST /studio/projects/{id}/channels`, `GET /studio/projects/{id}/channels`, `GET /studio/channels`,
  `PATCH /studio/channels/{profile_id}`.
- Mapeamento das exceções de canal/provider/budget/YouTube em `api/routes.py` (o hand-off da fatia C
  avisava que, sem isso, viraria 500). `application/channels.py` passou a levantar `ChannelFieldInvalid`
  (subclasse de `ValueError`, então os testes da fatia C continuam válidos) em vez de `ValueError` cru.

## Migração

`0022_channel_management.sql` (número reservado a esta fatia): `studio.channel_budgets` (hard/soft
mensal e por vídeo, `CHECK soft <= hard`, `economic_profile`) e `studio.channel_youtube_channels`
(metadados + `oauth_status`; **sem segredos**). Adicionada às **duas** listas de `tests/test_db.py`
(`test_migrate_applies_once`, `test_failed_migration_rolls_back_and_is_not_recorded`) e a
`test_creates_all_tables`. Migrações existentes não foram renomeadas.

Segredos de OAuth ficam **fora do Postgres**, no cofre de arquivo (`STUDIO_SECRETS_ROOT`,
padrão `<STUDIO_STORAGE_ROOT>/secrets`). `.env.example` documenta a variável.

## Testes (TDD: RED → GREEN)

RED observado antes da implementação (6 arquivos, `ModuleNotFoundError` para
`app.studio.domain.provider`, `domain.channel_budget`, `domain.secrets`, `domain.youtube_channel`,
`adapters.secret_store`, `application.providers`, `application.channel_budget`).

Arquivos novos (~90 testes): `test_provider_catalog.py`, `test_provider_service.py`,
`test_channel_budget.py`, `test_channel_budget_service.py`, `test_channel_secrets.py`,
`test_youtube_channel.py`, `test_channel_backend_repo.py` (Postgres descartável),
`test_channel_api.py` (HTTP+Postgres) e 2 casos em `test_composition.py`.

Postgres próprio e descartável: container `h-pg`, rede `h-net`, `--tmpfs /var/lib/postgresql/data`,
prova em `/budget-test-proof/proof` montada em `h-pg` e no container de teste. Passadas **as duas**
variáveis (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) mais
`STUDIO_BUDGET_TEST_PROOF_FILE`, então os testes de orçamento **não** foram pulados.

Comando focado (fatia + arquitetura + composição + db):

```
docker run --rm --network h-net -v "$PWD":/w -w /w \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@h-pg:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@h-pg:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof \
  -v "$PROOF_DIR":/budget-test-proof:ro \
  faceless-v2-hygiene-test-local:latest \
  python -m pytest -q -p no:cacheprovider \
    tests/test_provider_catalog.py tests/test_provider_service.py \
    tests/test_channel_budget.py tests/test_channel_budget_service.py \
    tests/test_channel_secrets.py tests/test_youtube_channel.py \
    tests/test_channel_api.py tests/test_channel_backend_repo.py \
    tests/test_composition.py tests/test_db.py tests/test_architecture.py
# 112 passed
```

Suíte completa (mesmo runner, banco descartável), no estado commitado:

- **1801 passed, 35 skipped, 2 failed** — as 2 são `tests/test_secrets_hygiene.py` (ambientais, ver
  abaixo). Os 100+ testes de orçamento rodaram (as duas variáveis DSN estavam definidas).
- Numa passada anterior sob pressão de memória do host (vários containers de outras fatias ativos) os
  testes de render do ffmpeg foram **SIGKILL (9)** e 7 deles falharam; re-rodados isolados deram
  `45 passed` (`tests/test_render_adapters.py`, `tests/test_render_api.py`, `tests/test_publish_api.py`).
  São OOM do ambiente, não regressão desta fatia (não toquei em nada de render).

## Falhas ambientais (qualificadas, não consertadas)

`tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
`::test_extracted_starter_runs_contract_snapshot_and_backup_import`: o `.git` da worktree é um
**gitfile apontando para fora** do volume montado, então `scripts/check-secrets.sh` não consegue rodar
o `git cat-file`/`git ls-files` e `package-starter.sh` aborta com
`Secret hygiene check could not complete safely.` Não é vazamento de segredo nem regressão desta
fatia (não toquei em `scripts/`, `.git`, nem no empacotamento). **Não** foram alteradas as assertions.

## O que ficou indisponível / deferido (com justificativa)

- **UI da tela de Canais**: não aprovada (segue `em breve` no mockup). Só endpoints e regras.
- **Integração real do roteamento no `provider_for`**: o roteamento roda como serviço/endpoint
  decisório; não troquei a resolução de provider em runtime dos caminhos de produção para não
  regredir F1/D2 (o perfil de canal já guarda specs por porta; a troca por profile é evolução).
- **Probe de rede do `opencode`**: usa alcance do endpoint do bridge (`/health`); sem token, o
  provider nem chega a ser `AVAILABLE` e o teste de conexão curto-circuita. Sem sonda implementada,
  o teste devolve indisponível em vez de fingir.
- **`veo`**: marcado `validated=False` (experimental) por decisão de honestidade — aparece `UNAVAILABLE`.
- **OAuth real do YouTube**: não há troca de código/refresh; a associação recebe tokens e o status é
  derivado da presença/expiração no cofre. O fluxo OAuth em si é de outra fase.
- **`cost_summary` por canal**: soma por vídeos do canal; lançamentos sem `video_id` não entram no
  gasto (são contados como não atribuídos), preservando a honestidade do número.

## Onde o código real contradisse o plano

1. **O guard da fatia A já era bloqueante, mas com limites do chamador.** O texto do plano sugeria
   "não é hard limit"; o que faltava era a origem do limite. Resolvi no lugar certo: `limits_for` no
   `PaidOperationGuard` + limites por canal persistidos. Não reimplementei um segundo guard.
2. **`Project.config` já era devolvido** no `POST /studio/projects` (via `response_model=Project`).
   O plano tratava F10-07 como futuro; na prática era uma exposição atual. Removi `config` da resposta
   de criação e criei uma leitura sanitizada.
3. **`soft` não tinha onde morar.** O coordenador já tinha `BudgetProjection.ceiling` para decidir
   pausa humana — mapeei o soft do canal para esse teto (e o hard para o guard). Não criei um quarto
   mecanismo de orçamento.
4. **Fatia C sem HTTP e com erros não mapeados.** Sem os endpoints de canal e o `except` explícito em
   `routes.py`, o perfil de canal viraria 500 numa resposta real; completei o caminho HTTP.
5. **Capabilities/qualidade não existiam no registro de providers.** `application/config.py` só sabia
   `(kind, name) -> factory`; introduzi metadados explícitos em `composition.py`, com `validated`
   derivado da presença de credencial — sem tocar no `_REGISTRY` nem em `renderer/app/main.py`.

## Arquivos

Novos: `domain/{provider,channel_budget,secrets,youtube_channel}.py`;
`application/{providers,channel_budget,youtube_channels,secrets}.py`;
`adapters/{secret_store,provider_probes}.py`;
`adapters/postgres/{channel_budget_repo,youtube_channel_repo}.py`;
`adapters/postgres/migrations/0022_channel_management.sql`; 8 arquivos de teste.

Alterados: `application/{ports,use_cases,budget,channels}.py`, `composition.py`, `api/routes.py`,
`tests/test_db.py`, `tests/test_composition.py`, `.env.example`.

Não tocados (trilhas paralelas): `scripts/export_contracts.py`, `contracts/`, `domain/render_plan.py`,
`domain/ticks.py`, e nada em `renderer/` fora de `app/studio/`.
