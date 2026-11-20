# F10 — fatia C: contrato e persistência de perfil de canal

Commit: `3afdbbd` (`feat: add channel profile contract, persistence and service (F10)`).
Escopo: primeiro corte de F10 — domínio, migração, repositório Postgres e serviço de aplicação.
Sem UI, sem endpoint HTTP e sem integração OAuth/YouTube.

## Entrega

- `renderer/app/studio/domain/channel.py`: `ChannelProfile` imutável (`@dataclass(frozen=True)`),
  com validação de todos os campos no `__post_init__`. Campos derivados do backlog F10:
  - F10-01: `name`, `strategy`, `language`, `audience`, `pillars`, `archived`.
  - F10-02: `narrative`, `target_duration_s`, `visual_identity`, `voice`, `audio`, `thumbnail`, `cta`.
  - Identidade/versionamento: `id`, `project_id`, `version`, `created_at`, `updated_at`.
- `renderer/app/studio/adapters/postgres/migrations/0016_channel_profiles.sql`:
  - `studio.channel_profiles` com `UNIQUE (project_id)`: um perfil por canal (o canal é o `project`).
  - `CHECK` de faixa/tamanho para nome, idioma, duração, specs de provedor e versão; espelha o domínio.
  - Índice parcial `channel_profiles_active_name_idx (name) WHERE archived = false` para a listagem
    de canais ativos, que ordena por nome.
  - `studio.channel_profile_revisions` (`profile_id`, `version`, `snapshot jsonb`), `PRIMARY KEY
    (profile_id, version)`: cada criação/atualização grava um snapshot, tornando a configuração
    versionada e auditável.
- `renderer/app/studio/adapters/postgres/channel_repo.py`: `PostgresChannelProfileRepository`
  - `create`, `get`, `get_by_project`, `list(include_archived)` e `update`.
  - Transacional, sem autocommit, usando `_Base`/`_translated` no padrão dos repositórios existentes.
  - `update` faz `SELECT ... FOR UPDATE`, exige `expected_version` (concorrência otimista) e grava
    a nova versão + snapshot na mesma transação.
  - Conflito de unicidade (`UniqueViolation` em `project_id`) vira `DuplicateChannelProfile`.
  - Versão divergente vira `ChannelVersionConflict`; perfil inexistente devolve `None`.
- `renderer/app/studio/application/ports.py`: porta `ChannelProfileRepository`.
- `renderer/app/studio/application/channels.py`: `CreateChannelProfile`, `GetChannelProfile`,
  `ListChannelProfiles`, `UpdateChannelProfile`. O `create`/`get` exigem projeto existente
  (`ProjectNotFound`) e validam o id (`InvalidId`); o `update` recusa campos desconhecidos.
- `renderer/app/studio/application/use_cases.py` + `composition.py`: wiring dos casos de uso.

## Migração: número final e evidência

Houve colisão com outro agente (F1/o guard de operação paga). No momento do meu commit:

```
$ git ls-files renderer/app/studio/adapters/postgres/migrations/ | tail -4
.../0013_budget_reservations.sql
.../0014_ledger_cost_evidence.sql
.../0015_ledger_cost_confirmation.sql
.../0016_channel_profiles.sql        # minha (commit 3afdbbd)
.../0017_paid_operations.sql         # do outro agente (commit 822334a)
```

Número final usado: **`0016_channel_profiles.sql`**. O outro agente ficou em `0017_paid_operations.sql`;
não há número duplicado. O `db.migrate` carrega o formato de quatro dígitos e aplica as duas em ordem.

## Testes (TDD)

RED observado antes da implementação (módulos ausentes):

```
ERROR tests/test_channel_domain.py   ModuleNotFoundError: No module named 'app.studio.domain.channel'
ERROR tests/test_channel_service.py  ModuleNotFoundError: No module named 'app.studio.application.channels'
ERROR tests/test_channel_repo.py     ModuleNotFoundError: No module named 'app.studio.adapters.postgres.channel_repo'
```

Cobertura (29 testes novos):

- Domínio: criação válida e defaults; nome vazio/espaços/longo/tipo inválido; ids hex-32;
  pilares normalizados/deduplicados/limitados; duração e versão inválidas; limites dos demais
  campos; imutabilidade; `dataclasses.replace` revalida.
- Serviço: projeto inexistente (`ProjectNotFound`), id inválido, conflito de unicidade propagado,
  leitura, listagem com `include_archived`, campos desconhecidos no update, conflito de versão.
- Repositório (Postgres descartável): criação/leitura por id e por projeto; unicidade conflitante;
  leitura inexistente; nomes iguais em canais distintos; nome inválido recusado antes de escrever;
  listagem filtrada/ordenada; update com incremento de versão e dois snapshots de revisão;
  versão defasada; update inexistente; validação de `changes`; FK de projeto inexistente.
- Arquitetura: coberta por `tests/test_architecture.py` (domínio puro; aplicação só importa domínio;
  adapters isolados), que passou.

Comandos reais (imagem local `faceless-v2-hygiene-test-local:latest`, Python 3.12.16,
postgres:16-alpine descartável em rede Docker isolada, prova de banco descartável preservada):

```
docker run --rm --network f10-net -v "$PWD":/w -w /w \
  -e STUDIO_TEST_DSN=postgresql://postgres:test@f10-pg:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/proof/proof -v "$PROOF_DIR":/proof:ro \
  faceless-v2-hygiene-test-local:latest \
  python -m pytest -q -p no:cacheprovider tests/test_channel_domain.py \
    tests/test_channel_service.py tests/test_channel_repo.py
# 29 passed
```

Suíte completa no HEAD commitado, executada numa cópia isolada (para não depender de arquivos
não rastreados de outros agentes no worktree compartilhado):

```
1119 passed, 86 skipped, 1 warning   (Starlette DeprecationWarning)
```

Antes do outro agente commitar o guard de orçamento, a mesma suíte sobre a minha fatia isolada
deu `1084 passed, 70 skipped`. O `skipped` caiu de 310 para 70–86 porque os testes de banco rodaram
com `STUDIO_TEST_DSN`; não houve falha.

## Limitações (F10 NÃO está concluída)

- Sem endpoints HTTP e sem UI; `api/panel.py` não foi tocado.
- Sem OAuth/associação de canal YouTube (F10-06) e sem tela/validação de providers (F10-03).
- O perfil é por projeto (um canal = um projeto). A associação canal↔vídeo/execução é implícita
  via `videos.project_id`; não há tabela de vínculo explícita nem vínculo a uma versão do perfil
  por vídeo/`ProductionRun`.
- O perfil ainda não é consumido pelo motor editorial/render: providers continuam resolvendo por
  `Project.config`/ambiente. Não há migração automática do `Project.config` para o perfil.
- Snapshots de revisão são gravados e testados, mas não existe API de leitura por versão.
- A concorrência cobre update do mesmo perfil (versão otimista + `FOR UPDATE`); não há teste de
  concorrência com múltiplas conexões disputando o mesmo perfil nesta fatia.
- O guard de unicidade usa a constraint do banco; a corrida de dois `create` simultâneos resulta em
  `DuplicateChannelProfile` para o perdedor, comportamento coberto indiretamente pela constraint.

## Convivência com outros agentes

- Arquivos de F1/F5/F3 não foram alterados.
- `renderer/app/studio/domain/production.py` e `tests/test_production_budget.py` não foram incluídos.
- Commit apenas dos meus 11 caminhos; sem `git add -A`/`git add .`, sem push/merge.
- Durante a fatia, outro agente editou os mesmos arquivos compartilhados (`ports.py`,
  `use_cases.py`, `composition.py`, `test_db.py`) e commitou o guard de orçamento. Meus hunks foram
  separados dos dele; o diff do commit `3afdbbd` não contém tokens do trabalho do outro agente.