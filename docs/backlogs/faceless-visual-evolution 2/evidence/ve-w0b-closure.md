# W0B — Fechamento da onda funcional (22/11/2026, sessão 2)

**Base:** `a2e6a39` (branch `main`) · **Nada commitado** · **Testes:** só no container (`scripts/test-container.sh`).
**Como foi executado:** direto, com worktrees isolados por tarefa (`.worktrees/ve-w0b1-budget`, `ve-w0b2-publish`, `ve-w0b4-labels`); os arquivos finais foram portados para o checkout principal e a verificação integrada rodou lá. O runtime LangGraph do workspace CERC **não** foi usado (não existe neste repositório).
**Legenda:** **[F]** fato verificado (arquivo:linha, comando ou saída de teste) · **[D]** decisão minha, com custo se estiver errada.

| ID | Entrega | Arquivos | Testes novos |
|---|---|---|---|
| W0B.1 | Guard de orçamento encaminhado ao container + prova de bloqueio por canal (R1/P-07) | `docker-compose.yml`, `.env.example` | `tests/test_compose_env.py`, `tests/test_budget_guard_wiring.py`, +2 em `tests/test_composition.py` |
| W0B.2 | Publicação **falha fechada** sem destino (R8) | `domain/channel.py`, `application/publication_execution.py` | 3 novos + 2 reescritos (`tests/test_publication_execution.py`), 1 reescrito (`tests/test_channel_domain.py`) |
| W0B.3 | Perfil econômico declarado congelado no snapshot (R9, parte i) | `composition.py` | 3 em `tests/test_composition.py` |
| W0B.4 | Rótulos honestos para campos sem consumidor (R4) | `api/panel_channels.py` | 1 em `tests/test_channels_page.py` |

## W0B.1 — orçamento (R1/P-07)

**Fato.** `Settings.from_env` já lia `STUDIO_BUDGET_GUARD` e `STUDIO_PRODUCTION_MODE` (`composition.py:456-457`, `_production_mode` em `:133-137`), mas o bloco `renderer.environment` do Compose **não** encaminhava nenhuma das duas: no container o código nunca as via, o guard ficava desligado e os limites por canal não protegiam nada **[F]**. `ProductionMode` aceita exatamente `INTERACTIVE` e `BUDGET_GUARDED`; qualquer outro valor (ou vazio) cai em `INTERACTIVE` sem erro **[F]** `application/production.py:153-163`, `composition.py:133-137`, teste `test_settings_accept_the_budget_guard_and_the_production_mode`.

**Mudança.** Compose passa a encaminhar as duas variáveis, com default **ligado** (`STUDIO_BUDGET_GUARD: ${STUDIO_BUDGET_GUARD:-1}`, `STUDIO_PRODUCTION_MODE: ${STUDIO_PRODUCTION_MODE:-BUDGET_GUARDED}`), e o `.env.example` documenta os valores aceitos, o default e o pré-requisito dos tetos.

**Prova (D-C: "prova por teste, inclusive sob concorrência").** `tests/test_budget_guard_wiring.py`, contra Postgres descartável, com o repositório real de operação paga e `limits_for=channel_guard_limits(...)` como a composição monta:

1. `test_the_channel_ceiling_blocks_the_paid_call_before_the_external_effect` — estimativa 0,40 dentro do teto do canal executa **uma** vez; 0,60 (acima do teto por vídeo) e 4,80 (acima do teto mensal) → `BudgetDenied` com o contador de efeito externo **parado** e nenhuma operação paga registrada **[F]**.
2. `test_two_concurrent_reservations_for_the_same_channel_cannot_both_pass` — duas reservas de 0,60 em vídeos distintos do mesmo canal contra teto mensal 1,00, em `ThreadPoolExecutor` com `Barrier`: resultados `["DENIED", "EXECUTED"]`, **uma** chamada externa, **um** gasto confirmado no ledger, nenhuma reserva ativa **[F]**. O que serializa é o advisory lock único do adaptador (`adapters/postgres/budget_repo.py:15-35`, tomado antes de qualquer leitura de orçamento).
3. `test_without_a_channel_budget_the_settings_ceiling_applies` — sem limite de canal valem as settings; com teto por vídeo 0 a primeira chamada paga é recusada **[F]**. É a consequência documentada de ligar o guard sem definir teto.
4. `tests/test_composition.py::test_the_wired_budget_guard_resolves_the_channel_limits` — com `budget_guard=True` o guard do caminho pago recebe `channel_guard_limits` (limite do canal com fallback nas settings); com o guard desligado o caminho antigo permanece **[F]**. (Este teste passa desde a primeira execução: a fiação já existia; o teste o **fixa** contra regressão.)

**Comando/resultado:** `scripts/test-container.sh tests/test_budget_guard_wiring.py tests/test_compose_env.py tests/test_composition.py -q` → **39 passed**.

**[D] Default ligado.** O plano (W0B.1) e a decisão D-C mandam ligar o default **depois** da prova. Liguei no Compose e no `.env.example`; o guard passa a valer para quem sobe o stack sem definir a variável. Custo se estiver errado: uma instalação com teto em branco (`MAX_COST_USD_PER_VIDEO`/`MAX_COST_USD_PER_MONTH` vazios, ou `channel_budgets` com hard 0) passa a recusar **toda** chamada paga com HTTP 403 — fail-safe, mas bloqueante; desligar é uma linha no `.env` (`STUDIO_BUDGET_GUARD=0`). Mitigação aplicada: pré-requisito documentado no `.env.example`, no comentário do Compose e aqui. O `.env` do operador tem os dois tetos definidos e positivos **[F]** (valores não impressos).

## W0B.2 — publicação sem destino (R8)

**Fato (antes).** `verify_publication_authorization` devolvia `ALLOW` para canal sem destino; o gate da aplicação devolvia `None` (segue) também para canal inexistente e `project_id` inválido **[F]**.

**Mudança.** O domínio falha fechado: canal sem destino → `BLOCK` com motivo acionável. Com os repositórios injetados (o caminho do servidor sempre os injeta — `composition.py:734-737`), `InvalidId`, projeto sem perfil de canal e canal sem destino bloqueiam via `_blocked` (DLQ `PERMANENT`) **antes** de `uploads.upload`. Exceção documentada e deliberada: construção **sem** os repositórios segue o caminho antigo (é forma de teste/legado; sem os repositórios não há como consultar o canal).

**Testes.** 3 novos (projeto sem perfil de canal; `InvalidId`; construção legada) e 2 reescritos de propósito: `test_a_channel_without_a_target_is_blocked_before_any_upload` e `test_verification_blocks_when_the_channel_has_no_youtube_target` (mudança de comportamento pedida pelo operador, não enfraquecimento de asserção). O caso positivo (destino + autorização `CONNECTED` + token do mesmo canal → `UPLOADED`) continua verde.

**Achado verificado (fora do escopo desta tarefa, registrado e não corrigido).** `POST /publications/claim` **não** passa por este gate: `api/routes.py:1670-1675` → `ClaimPublication` (`application/publishing.py:109-145`), construído sem repositórios de canal/autorizações (`composition.py:741`); ele não faz upload, mas **entrega** arquivo + `youtube_body` para o chamador. Toda a publicação feita pelo servidor (`/publications/execute`, `/videos/{id}/publication/publish`) está coberta; o `claim` é caminho legado consumido pelo workflow n8n `workflows/03-publish-approved.json`, que está **inativo** (`"active": false`). Se for reativado, sobe ao YouTube fora do servidor, sem o gate.

## W0B.3 — snapshot de provider (R9)

**Fato (antes).** `_effective_config_for` não passava `provider_profile`, então `resolve_effective_config` congelava sempre `BALANCED` + proveniência `engine_default`, enquanto o roteamento real (`ProviderRouting.__call__`, `composition.py:295-302`) lia o perfil do canal (`channel_budgets.economic_profile`) **dinamicamente** — o snapshot dizia uma coisa e a execução usava outra **[F]**.

**Mudança (parte i).** `_economic_profile_for(budgets, project_id)` resolve o perfil declarado do canal e o resolvedor passa a congelá-lo. Sem orçamento de canal, o retrato legado (`BALANCED`/`engine_default`) é preservado.

**Testes (RED→GREEN observados).** `test_the_resolved_config_freezes_the_declared_economic_profile` e `test_a_created_run_keeps_the_frozen_profile_when_the_channel_budget_changes` falhavam com `BALANCED` antes da mudança (saída do vermelho registrada no ledger) e passam depois; `test_the_resolved_config_stays_on_the_engine_default_without_a_channel_budget` fixa o legado. O terceiro prova que o snapshot gravado por `create_run` **não muda** quando o orçamento do canal é alterado depois.

**Achado verificado — a *seleção* (provider/modelo por capacidade) continua NÃO congelada.** Isto é o que sobra da R9 e **não** foi implementado aqui:
- `provider_policy` é lido/escrito **apenas** em `domain/effective_config.py` (nenhum consumidor em `adapters/`, `application/` ou `api/`) **[F]** — `grep -rn "provider_policy" --include=*.py renderer tests` devolve só esse arquivo (e os testes de contrato).
- O contrato exige exatamente as chaves `profile` e `version`: `_exact_keys(policy, ("profile", "version"), "provider_policy")` (`effective_config.py:452-453`), fixado por `tests/test_effective_config.py:278-283` ("the provider policy is only a frozen reference").
- Quem decide a seleção é `ProviderRouting.__call__` em tempo de execução, lendo o perfil/limites vivos do canal **[F]**.

Congelar a seleção exige, então: (1) bump de `PROVIDER_POLICY_VERSION` e afrouxar o `_exact_keys`; (2) escolher a seleção **na criação do run** para cada capacidade; (3) fazer o consumidor de retry ler o snapshot em vez de re-rotear — e hoje o retry reexecuta handlers que chamam `ProviderRouting(kind, project_id)`, sem contexto de run/vídeo. É mudança média com ADR, não cabendo em W0B sem inventar um campo sem consumidor (o que violaria a regra "honestidade primeiro" do plano). Registrado para a onda 4 (W4.0/W4.3), onde o retry precisa de reprodutibilidade de qualquer forma.

## W0B.4 — rótulos honestos (R4)

- "Voz do narrador": "Voz usada nos vídeos novos deste canal" → "**Declarado, ainda não aplicado**: a voz dos vídeos novos ainda vem do estilo ou do padrão do estúdio." (`channel_profiles.voice` não é lida por nenhum estágio; a voz sai do estilo/projeto — `composition.py:218-260`) **[F]**. *(Regressão de vocabulário corrigida na integração da W1: a primeira redação dizia "do estilo ou do **projeto**", e o RF-01 proíbe "projeto" como texto visível — `tests/test_channel_vocabulary.py::test_channels_page_has_no_project_vocabulary` pegou isso na suíte completa; a redação passou a "do estilo ou do padrão do estúdio".)*
- "Identidade visual": "Aplicada a thumbnail, cartelas e legendas." → "**Declarado, ainda não aplicado**: hoje não altera thumbnail, cartelas nem legendas." **[F]**.
- Teste que fixa as duas frases e a ausência das antigas: `tests/test_channels_page.py::test_voice_and_visual_identity_are_declared_not_applied` (vermelho observado antes da mudança do texto).

## Verificação integrada (checkout principal)

```
scripts/test-container.sh tests/test_publication_execution.py tests/test_channel_domain.py tests/test_publication_api.py \
  tests/test_publish_api.py tests/test_composition.py tests/test_channels_page.py tests/test_channel_prefs_page.py \
  tests/test_channel_style_page.py tests/test_panel_page.py tests/test_qa_legacy_read.py tests/test_publication_policy.py \
  tests/test_channel_grant_token.py tests/test_budget_guard_wiring.py tests/test_compose_env.py tests/test_architecture.py -q
→ 276 passed
scripts/test-container.sh tests/test_composition.py tests/test_effective_config.py tests/test_production_run.py \
  tests/test_production_flow_db.py tests/test_production_api.py tests/test_budget_guard_wiring.py tests/test_compose_env.py \
  tests/test_channel_budget_service.py tests/test_paid_operations.py tests/test_render_rollout.py tests/test_architecture.py -q
→ 176 passed
```
Suíte completa: ver `evidence/ve-00-closure.md` (W0A) e o fechamento da sessão em `CONTINUITY.md`.

## Achados abertos desta onda (não corrigidos)

1. `POST /publications/claim` fora do gate de identidade (W0B.2) — só importa se o workflow n8n for reativado.
2. Recusa de orçamento chega ao operador como `403 "budget denied for paid operation <chave>"` (`api/routes.py:923`) sem dizer **qual** teto estourou — com o guard ligado por padrão, a mensagem passa a ser visível e vale melhorar (não é bug; não corrigido para não ampliar o escopo).
3. Seleção efetiva de provider não congelada (W0B.3, parte ii) — descrito acima.
4. `STUDIO_PROVIDER_PRODUCTION` e `STUDIO_SECRETS_ROOT` também **não** são encaminhados pelo Compose **[F]**; ficaram fora do escopo do W0B.1 (que nomeia só as duas do orçamento) e não mudam o comportamento atual (defaults do código coincidem com o uso no container).
