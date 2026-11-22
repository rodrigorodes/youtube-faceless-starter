# Onda paralela 1 — streams A, B, C (21/11/2026)

Três worktrees a partir de `e254b61`, cada uma com a entrega F02 copiada como baseline não
commitado (24 arquivos) e PostgreSQL 16 descartável próprio. Nenhum stream fez commit, push,
deploy ou chamada paga; nenhum rodou a suíte completa.

| Stream | Escopo | Worktree | Banco | Estado |
|---|---|---|---|---|
| A | F01.T01 identidade YouTube | `…worktrees/f01-identity` | 55436 | **integrado** |
| B | F01.T03 escopo/reserva de orçamento | `…worktrees/f01-budget` | 55434 | **integrado** |
| C | F06.T01 política e catálogo de providers | `…worktrees/f06-providers` | 55435 | **integrado** |

## Stream A — F01.T01 (identidade YouTube)

Arquivos integrados: `application/channel_grant.py` (novo), `application/publication_execution.py`,
`composition.py` (única fiação), `tests/test_channel_grant_token.py` (novo),
`tests/test_publication_execution.py`, `tests/test_composition.py`.

Comportamento:
- projeto → `channel_profiles.youtube_channel_id` → autorização `CONNECTED` → `oauth_grants` →
  cofre `oauth_grant:{grant_id}`; renovação usa o refresh **daquele** grant e grava só nele;
- vínculo escolhido é o **mais recente** entre os CONNECTED (reconexão usa o grant novo);
- falha fechada: sem vínculo/grant revogado/vencido sem refresh → `OAuthReconnectRequired`
  (a publicação vira `BLOCKED`); `invalid_grant` limpa o escopo e marca o grant;
- `TargetChannelTokenProvider`: canal com destino usa **somente** o grant; sem destino, o
  caminho legado (cofre por projeto → `token.env`) continua explícito e restrito — nunca como
  fallback de um canal com destino.

Testes: **135 passed** (`test_channel_grant_token`, `test_publication_execution`,
`test_composition`, `test_connections_service`, `test_youtube_oauth_service`,
`test_youtube_identity_repo`, `test_workflow_publish`).

Limites (declarados pelo stream e aceitos): n8n continua com credencial própria (F01.T02);
analytics usa token legado (F01.T02); botão "Reautorizar" de Canais ainda no consentimento
legado; revogar o grant mais novo pode deixar vínculo antigo utilizável (decisão de produto);
cofre e metadados do grant não compartilham transação; dois workers renovando o mesmo grant
podem disputar o refresh (mesmo padrão do `EnsureAccessToken`, sem lock).

## Stream C — F06.T01 (política e catálogo de providers)

Arquivos integrados: `domain/provider.py` (política pura), `application/providers.py` e os
testes `test_provider_catalog.py`, `test_provider_service.py`, `test_port_contracts.py`.

Regras: ranking por perfil (ECONOMY custo-primeiro; BALANCED *sweet spot*; PREMIUM qualidade-
-primeiro), pisos de qualidade 1/2/3, custo desconhecido recusado em ECONOMY/BALANCED e aceito
em PREMIUM só sem teto, capabilities por porta, e `ProviderStanding` (PRODUCTION/DEMO/PLACEHOLDER)
com `production=True` excluindo stand-ins.

Testes: **54 passed** nos quatro arquivos; **77 passed** nos consumidores com banco; as 5 falhas
de `test_channels_page` permanecem as pré-existentes.

Consequência importante para F06.T02: com `production=True`, texto em ECONOMY/BALANCED fica sem
candidato enquanto `opencode` tiver custo desconhecido — a falha nomeia `unknown cost`. Não
ligar o flag de produção em texto antes de declarar preço (ou passar `allow_unknown_cost`).

## Stream B — F01.T03 (escopo e reserva de orçamento)

Arquivos integrados: `application/budget.py`, `application/channel_budget.py`,
`adapters/postgres/budget_repo.py`, `adapters/postgres/channel_budget_repo.py`, migração
`0038_budget_scope_attribution.sql` (nova) e 4 arquivos de teste. Fiação de `composition.py`
feita à mão (import de `ChannelBudgetFloor`, remoção do `_ChannelBudgetFloor` local, uso de
`usage_repo`).

Comportamento:
- `PaidOperationGuard` envia **sempre** o teto global (settings) e o do canal; o SQL verifica
  três escopos: global mensal, canal mensal e vídeo vitalício (ledger + reservas ativas);
- operação sem vídeo = escopo **global explícito** (`project_id NULL`), não do canal;
- atribuição derivada do vídeo, nunca declarada pelo chamador; trigger `BEFORE INSERT` mantém a
  atribuição em qualquer caminho de escrita (inclusive o legado `record`);
- ordem de lock documentada: advisory xact `726002` → `paid_operations` → `budget_reservations`
  → `usage_ledger`; lock único, sem ordem inversa;
- `ChannelBudgetFloor` mede o gasto **do canal** (`month_summary(project_id)`) com teto
  `min(soft do canal, settings)`; sem vídeo mede o global.

Testes: **172 passed** nos arquivos da tarefa (com concorrência real em threads provando
`[CREATED, CREATED]` x `[CREATED, DENIED]` no teto global) e **201 passed** no grupo
budget/guarda/coordenador já com A e C integrados.

Limites declarados: o painel não mostra o teto global (fora do escopo); replay com orçamento de
canal editado ainda gera `IdempotencyConflict` (regra anterior, agora mais visível);
`ChannelUsageRepository` em `ports.py` ainda não declara `global_month_summary()`;
`CostGuard` do caminho não pago continua medindo gasto global; backfill da 0038 deve rodar fora
de pico em base grande.

## Integração

- C foi aplicado por `git apply` (sem conflito).
- A foi reaplicado por cópia dos 6 arquivos: o patch gerado no worktree trazia junto os trechos
  da F02 (baseline copiado), então a aplicação sobre a árvore principal conflitaria. O diff
  conferido contra a versão F02 local mostra apenas os hunks do stream A.
- B foi aplicado por `git apply` e a fiação de composição feita à mão (o stream não podia editar
  `composition.py`). O teste `test_channel_budget_floor_uses_soft_limit_and_falls_back` foi
  **reescrito** para a nova classe, mantendo as duas asserções originais, em vez de removido.
- Registro de decisões e custos em `.superpowers/sdd/05-roadmap/progress.md`. Sem commit.

## Falhas pré-existentes

Nenhuma falha nova até aqui; as 63 do baseline continuam sendo as únicas ([pre-existing-failures](pre-existing-failures.md)).
## Gate de integração (rodada única na árvore principal)

1ª rodada: **2730 passed, 67 failed, 58 skipped** (390 s). As 4 falhas novas eram da migração
`0038`: `test_db.py` fixa a lista exata de migrações (2) e `test_schema_docs.py` exige artefatos
regenerados (2). Correções: lista atualizada com `0038_budget_scope_attribution` e
`scripts/export_schema.py --build` regerando `docs/schema/studio.sql` e `docs/22-modelo-de-dados.md`
(DSN descartável). Reexecução dos 4 arquivos: **21 passed**. Saldo final: 63 falhas, todas
pré-existentes.
