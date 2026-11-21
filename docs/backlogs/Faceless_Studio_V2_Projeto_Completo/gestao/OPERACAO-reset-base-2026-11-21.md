# Operação — reset da base de dados do app (2026-11-21)

**Objetivo do dono:** deixar a base limpa para começar a **configurar** (canal, estilo,
conexão do YouTube) e **criar conteúdo** de verdade.

## O que é a base do app

- Container: `youtube-faceless-starter-postgres-1`
- Banco: `n8n` · usuário: `n8n` — o app aponta para `postgres:5432/n8n`
  (`STUDIO_DATABASE_URL` do container `youtube-faceless-starter-renderer-1`).
- **Dois schemas** no mesmo banco: `public` (do **n8n**, 52 tabelas) e `studio` (o nosso).
- **Nenhuma FK cruza os schemas** (verificado em `pg_constraint`), então limpar o `studio`
  **não** vaza para o n8n.

## Achado importante: o banco vivo estava 5 migrações atrás

O banco tinha **27** migrações (até `0032_render_plan_cache`) e **não tinha**
`studio.visual_styles`. Ou seja: as tabelas de **Estilos** (`0033`, `0034`), **Identidade
YouTube** (`0035`), **override de vídeo** (`0036`) e **destino no YouTube** (`0037`) não
existiam ali.

Causa: o container do app roda uma **imagem antiga** — o diretório de migrações *dentro dele*
só tinha 27 arquivos. Por isso `migrate()` devolvia `[]`.

**Ação:** apliquei as 5 pendentes usando o **próprio `migrate()` do app** (copiei os arquivos
novos para o diretório de migrações do container e rodei a função de lá — sem manipular
segredo nenhum). Resultado: `schema_migrations` = **32**, idempotente na segunda execução.

## Backup (antes de qualquer remoção)

- Arquivo: `backups/studio-20261121-130237.sql` (schema `studio`, estrutura + dados)
- 232 KB · 42 `CREATE TABLE` · 42 blocos `COPY`
- **Verificado linha a linha contra o banco vivo** (contagem por tabela, 0 divergências).
- `backups/*` está no `.gitignore` — **não** entra no git.

Para restaurar, se precisar:

```bash
docker exec -i youtube-faceless-starter-postgres-1 \
  psql -U n8n -d n8n -v ON_ERROR_STOP=1 < backups/studio-20261121-130237.sql
```

## Limpeza

`TRUNCATE` de **47 tabelas** do schema `studio` (`RESTART IDENTITY CASCADE`),
**preservando `studio.schema_migrations`** (32 linhas). Depois:

| Verificação | Resultado |
| --- | --- |
| Linhas restantes no `studio` | só `schema_migrations` = 32 |
| `schema_migrations` | 32 (intacto — não re-aplicar migração) |
| Tabelas em `public` (n8n) | 52 (intactas) |
| `/health` do app | HTTP 200 |

## O que **não** foi limpo (e por quê)

- `storage/` no host: **377 MB** de artefatos de render (`render-cache` 24 MB,
  `jobs` 272 MB, `output` 63 MB). Não é banco — deixei como está e reporto para você decidir.
- Schema `public` (n8n): intocado.

## Para usar as telas novas (Estilos / Conexões)

As migrações já estão aplicadas, mas o **container do app roda uma imagem anterior** às telas
novas: o painel em `http://localhost:8000/studio/panel` **ainda não tem** "Estilos" nem
"Conexões". Para vê-las é preciso **reconstruir e reiniciar** o serviço `renderer` com o
código atual do `main` — decisão do dono (a orientação anterior era manter o app no ar).
