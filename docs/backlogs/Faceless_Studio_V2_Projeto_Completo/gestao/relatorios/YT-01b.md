# YT-01b — Repositórios Postgres da identidade de publicação do YouTube

**Data:** 2026-11-21
**Fatia:** YT-01b (repositórios da identidade: conta → autorizações → canais)
**Base:** `08aef55`
**Branch:** `feat/yt01b-identity-repos` (worktree isolado; sem push/merge)
**Entregue:** sim — código, portas e testes de integração verdes.

## Objetivo

Persistir as quatro entidades da identidade de publicação do YouTube criadas na fatia
YT-01 (migração `0035_youtube_identity.sql` + domínio `domain/youtube_identity.py`),
e expor as portas correspondentes em `application/ports.py`. Só metadados: **nenhum
token** é lido ou devolvido (tokens vivem no vault, escopo `oauth_grant:{id}`).

## Arquivos

| Arquivo | Estado | O que é |
|---|---|---|
| `renderer/app/studio/adapters/postgres/youtube_identity_repo.py` | **novo** | As quatro classes de repositório Postgres |
| `renderer/app/studio/application/ports.py` | alterado | As quatro portas (`Protocol`) + import do domínio |
| `tests/test_youtube_identity_repo.py` | **novo** | Testes de integração (banco descartável) |
| `docs/backlogs/Faceless_Studio_V2_Projeto_Completo/gestao/relatorios/YT-01b.md` | **novo** | Este relatório |

## O que foi feito

### Portas (`application/ports.py`)

Adicionadas ao lado da porta antiga `YouTubeChannelRepository` (modelo por projeto, que
**não** foi tocada), com nomes distintos para não colidir:

- `GoogleAccountRepository`: `upsert`, `get`, `get_by_email`, `list`.
- `OAuthGrantRepository`: `create`, `get`, `list_for_account`, `update_status`.
- `YouTubeChannelIdentityRepository`: `upsert`, `get`, `list`.
- `ChannelAuthorizationRepository`: `link`, `get`, `authorizations_for_channel`, `revoke`.

### Repositórios (`adapters/postgres/youtube_identity_repo.py`)

Seguem o padrão de `channel_repo.py`/`visual_style_repo.py` (`_Base` de `editorial_repo`,
`with _translated(), self._connect() as conn, conn.cursor(row_factory=dict_row) as cur`).
Classes: `PostgresGoogleAccountRepository`, `PostgresOAuthGrantRepository`,
`PostgresYouTubeChannelIdentityRepository`, `PostgresChannelAuthorizationRepository`.

Decisões relevantes:

- **Conta por e-mail sem distinguir caixa** — `INSERT ... ON CONFLICT ((lower(btrim(email))))`
  no índice único funcional `google_accounts_email_idx`: reconectar atualiza
  (`display_name`, `updated_at`) e devolve a **linha existente** (mesmo `id`, mesmo
  `created_at`); não duplica e não muda a PK (que é referenciada por `oauth_grants`).
- **Escopos como `Jsonb`** (`jsonb` + `CHECK (jsonb_typeof = 'array')` da migração) e
  normalizados pelo domínio (trim + dedupe, em `OAuthGrant.__post_init__`).
- **FKs violadas viram erro de domínio nomeado**: `create` de grant com conta inexistente →
  `OAuthGrantInvalid`; `link` com grant ou canal inexistente → `ChannelAuthorizationInvalid`
  (a mensagem diz **qual** dos dois, lendo `exc.diag.constraint_name`, para não mentir).
- **`update_status`** aceita status armazenável (`CONNECTED|EXPIRED|REVOKED|ERROR`) e
  **recusa `DISCONNECTED`** (é derivado, nunca persistido — respeita o `CHECK` da 0035).
  `token_expires_at` só é alterado quando informado (sentinela `_UNSET`): `None` limpa,
  omitir preserva.
- **`link` é upsert por `(grant_id, youtube_channel_id)`** e grava `validated_at`;
  `created_at` é preservado em revalidações. **`revoke`** só muda o status para `REVOKED`:
  mantém a linha e o `validated_at` da conferência.

Colisão evitada: a classe antiga `PostgresYouTubeChannelRepository`
(`youtube_channel_repo.py`) e a porta `YouTubeChannelRepository` permanecem intactas.

## Prova (comando real, container)

Suíte de integração com banco descartável (duas DSNs + prova de descarte), executada
no worktree:

```
docker run --rm --network integ-net -v "$REPO":/workspace -v "$T/proof":/budget-test-proof:ro \
  -e PYTHONPATH=/workspace/renderer -e STUDIO_TEST_DSN=postgresql://postgres:test@integ-pg:5432/postgres \
  -e STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@integ-pg:5432/postgres \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/budget-test-proof/proof -w /workspace \
  --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider \
  --tb=short tests/test_youtube_identity_repo.py tests/test_youtube_identity_domain.py \
  tests/test_db.py tests/test_architecture.py
```

**Resultado final: `41 passed`.**

- `tests/test_youtube_identity_repo.py` — **14 testes** (novos).
- `tests/test_youtube_identity_domain.py` — 6 (domínio YT-01, já existiam).
- `tests/test_db.py` — 15 (migração/schema; já existia, contempla 0035).
- `tests/test_architecture.py` — 6 (adapters fora do core; `application` só importa `domain`).

Cobertura dos 14 novos: upsert/get/list de conta; unicidade de e-mail sem caixa (mesmo
`id`, sem duplicar); `get_by_email` validando o endereço; criação/listagem de grant;
erro de conta inexistente; cascade da conta apaga os grants; `update_status` (preserva
vencimento ausente, limpa com `None`, recusa status derivado); upsert/list de canal;
validação de id de canal; `link` + `authorizations_for_channel`; erro de grant/canal
inexistente; `revoke` preservando `validated_at`; revalidação preservando `created_at`.

O módulo novo rodou 3/3 vezes isolado com 14/14 verdes.

## Limitações e observações honestas

- **`tests/test_db.py` é intermitente neste host por contenção externa**, não por esta
  fatia. O `integ-pg` é compartilhado por vários containers de teste de outros agentes
  rodando no mesmo host: em repetições observei erros de corrida de DDL entre sessões
  (`duplicate key ... pg_namespace_nspname_index` no `CREATE SCHEMA IF NOT EXISTS studio`,
  `relation "studio.projects" does not exist`, `schema "studio" does not exist`).
  Reproduzi a mesma falha rodando **só** `tests/test_db.py` (sem nenhum arquivo desta
  fatia), o que isola a causa. Todos os arquivos desta fatia são verdes de forma estável.
- Não alterei a migração `0035` nem `tests/test_db.py` (ambos já contemplam as tabelas).
- Não toquei no checkout principal, nem reiniciei app/bridge.
- Sem `git push`, merge ou `git add -A` (caminhos exatos no commit).
- Não há escrita em `knowledge/` nesta fatia (nenhum fato novo, não óbvio e durável além
  do que o desenho/spec já registram).
