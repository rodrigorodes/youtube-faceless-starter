# F10 — fatia C: contrato e persistência de perfil de canal

Commits: `3afdbbd` (entrega inicial) e `6b9128c` (correção da revisão independente).
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

Cobertura (38 testes novos):

- Domínio: criação válida e defaults; nome vazio/espaços/longo/tipo inválido; ids hex-32;
  pilares normalizados/deduplicados/limitados; duração e versão inválidas; limites dos demais
  campos; imutabilidade; `dataclasses.replace` revalida. Regressão de imutabilidade profunda:
  `pillars` é `tuple`, mutar a lista do chamador não afeta o agregado e `hash(profile)` funciona.
- Serviço: projeto inexistente (`ProjectNotFound`), id inválido, conflito de unicidade propagado,
  leitura, listagem com `include_archived`, `include_archived` não-booleano recusado, opção
  desconhecida no create recusada antes do repositório, campos desconhecidos no update,
  conflito de versão.
- Repositório (Postgres descartável): criação/leitura por id e por projeto; unicidade conflitante;
  leitura inexistente; nomes iguais em canais distintos; nome inválido recusado antes de escrever;
  listagem filtrada/ordenada; update com incremento de versão e dois snapshots de revisão;
  versão defasada; update inexistente; validação de `changes`; opção desconhecida no create;
  `include_archived` não-booleano; FK de projeto inexistente traduzida; banco recusando >20 pilares;
  `lock_timeout` traduzido; concorrência real com duas conexões (create e update, 1 vencedor,
  revisões contíguas `[1, 2]`).
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
# 38 passed
```

Suíte completa no estado commitado, executada numa cópia isolada (HEAD + apenas as minhas
edições, para não depender de arquivos não rastreados de outros agentes no worktree compartilhado):

```
1284 passed, 86 skipped, 1 warning   (Starlette DeprecationWarning)
```

No worktree compartilhado, com os arquivos em andamento dos outros agentes:

```
1351 passed, 116 skipped, 2 failed
```

As 2 falhas são `tests/test_db.py::test_migrate_applies_once` e
`::test_failed_migration_rolls_back_and_is_not_recorded`, causadas por migrações `0018/0019`
não rastreadas de outra fatia e pela lista hardcoded desatualizada no `tests/test_db.py` do outro
agente — não pelo meu código. No tree isolado, `test_db.py` passa com `0016` + `0017`. As falhas
ambientais de `test_secrets_hygiene` exigem o `.git` externo montado; com ele, passaram.

Antes do outro agente commitar o guard de orçamento, a mesma suíte sobre a minha fatia isolada
deu `1084 passed, 70 skipped`. O `skipped` caiu de 310 para 70–86 porque os testes de banco rodaram
com `STUDIO_TEST_DSN`; não houve falha minha.

## Limitações (F10 NÃO está concluída)

- Sem endpoints HTTP e sem UI; `api/panel.py` não foi tocado.
- Sem OAuth/associação de canal YouTube (F10-06) e sem tela/validação de providers (F10-03).
- O perfil é por projeto (um canal = um projeto). A associação canal↔vídeo/execução é implícita
  via `videos.project_id`; não há tabela de vínculo explícita nem vínculo a uma versão do perfil
  por vídeo/`ProductionRun`.
- O perfil ainda não é consumido pelo motor editorial/render: providers continuam resolvendo por
  `Project.config`/ambiente. Não há migração automática do `Project.config` para o perfil.
- Snapshots de revisão são gravados e testados, mas não existe API de leitura por versão.
- `pillars` é `tuple[str, ...]` (imutabilidade profunda, hashable); a lista de entrada do chamador
  não é compartilhada. O banco também recusa `cardinality(pillars) > 20`, espelhando o domínio.
- Concorrência coberta com duas conexões reais: `create` disputado tem 1 vencedor (o outro recebe
  `DuplicateChannelProfile`) e `update` disputado tem 1 vencedor (o outro recebe
  `ChannelVersionConflict`), com revisões contíguas `[1, 2]`. Sob contenção além do `lock_timeout`,
  o repositório traduz `LockNotAvailable` em `ChannelLockTimeout`.
- FK de projeto inexistente é traduzida em `ChannelProjectNotFound` (não vaza erro cru do driver).

## Convivência com outros agentes

- Arquivos de F1/F5/F3 não foram alterados.
- `renderer/app/studio/domain/production.py` e `tests/test_production_budget.py` não foram incluídos.
- Commit apenas dos meus 11 caminhos; sem `git add -A`/`git add .`, sem push/merge.
- Durante a fatia, outro agente editou os mesmos arquivos compartilhados (`ports.py`,
  `use_cases.py`, `composition.py`, `test_db.py`) e commitou o guard de orçamento. Meus hunks foram
  separados dos dele; o diff dos meus commits não contém tokens do trabalho do outro agente.
- Nesta rodada de correção, `composition.py` estava modificado e não commitado por outro agente.
  Conforme instruído, **não foi tocado** (a correção não precisava de wiring novo). `ports.py`,
  `test_db.py`, `budget.py`, `api/routes.py`, `domain/insight.py`, `domain/packaging.py`,
  `domain/production_run.py` e `adapters/postgres/production_repo.py` também não foram tocados.

## Rodada de correção (revisão independente)

Commit: `6b9128c`. TDD: os testes de regressão rodaram em RED antes da implementação (falhas
medidas: `pillars == []`, `hash(profile)` `TypeError: unhashable type: 'list'`,
`clean_pillars` devolvendo `list`, `include_archived` não validado, opção desconhecida chegando ao
repositório) e depois em GREEN.

### Bloqueador 1 — imutabilidade falsa

- `ChannelProfile.pillars` passou de `list[str]` para `tuple[str, ...]`; `clean_pillars` devolve
  tupla; o repositório reconstrói com `tuple(...)`; a escrita no banco passa `list(tuple)` apenas
  na borda.
- Regressão (`test_pillars_are_deeply_immutable_and_hashable`): `p.pillars.append(...)` falha,
  mutar a lista do chamador não altera o agregado e `hash(profile)` é estável. Não há outro campo
  de coleção no agregado (`claims` não faz parte de `ChannelProfile`).

### Bloqueador 2 — `pillars` sem espelho no banco

- `0016_channel_profiles.sql` (editada no lugar, sem migração nova) agora tem
  `CHECK (cardinality(pillars) <= 20)`.
- Regressão (`test_db_rejects_more_pillars_than_domain_limit`): 20 pilares são aceitos; 21 são
  recusados pelo banco com `CheckViolation`, sem truncamento silencioso no round-trip.

### Melhorias exigidas

3. `ForeignKeyViolation` → `ChannelProjectNotFound` (domínio). O teste que consagrava o vazamento
   foi atualizado para exigir a tradução.
4. `LockNotAvailable` → `ChannelLockTimeout` (domínio), em `create`/`update`, documentado. Teste
   segura a linha com uma conexão e usa `lock_timeout=200` na conexão do repositório.
5. Coberto: opção desconhecida no `create` (serviço e repositório), `include_archived` não-booleano
   (serviço e repositório) e limite de pilares no domínio e no banco.
6. Concorrência real com duas conexões: `test_concurrent_update_has_single_winner` e
   `test_concurrent_create_has_single_winner` provam 1 vencedor por corrida e revisões `[1, 2]`.

### Registrado para o controlador (não corrigido nesta rodada)

- Identidade duplicada: `projects.name/language/niche` e `channel_profiles.name/language` são
  duas fontes de verdade sem sincronização; o painel usa `projects.name`. Decisão de modelagem.
- `created_at/updated_at` vão como ISO-string no `snapshot` jsonb (menos consultável).
- Hand-off para a fatia H: as exceções de canal herdam de `ValueError`, mas `api/routes.py` só
  traduz as que enumera. É preciso `except` explícito antes de expor endpoint, senão vira 500.