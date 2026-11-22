# ADR-003 — Isolamento por organização (ISO) com escopo single-tenant preparado

**Status:** Proposto. Decisão do operador: **agora só um operador**; deixar preparado para
papéis depois, sem complexidade desnecessária (D-E em `DECISIONS.md`).
**Data:** 22/11/2026.

## Contexto

O produto nasceu como estúdio de um operador. A autenticação é **Basic auth** com um único
usuário (`STUDIO_BROWSER_USER`); não há sessão, usuário de produto nem papel aplicado.

O banco já tem `studio.organizations`, `studio.users`, `studio.memberships` e
`studio.workspaces`, e `organization_id` aparece em `visual_styles` e nas tabelas de SaaS
(`byok_keys`, `memberships`). Mas **não** aparece em `videos`, `scenes`, `assets`,
`render_jobs`, `render_plans`, `publications`, `production_runs`, `budget_reservations`,
`usage_ledger` — as tabelas do trabalho real. Quando um `organization_id` chega hoje, vem
de corpo ou query string, não de identidade verificada. Isso é vazamento por construção se
houver mais de um cliente.

`CREATE_VIDEO`, `EDIT_VIDEO`, `APPROVE_*`, `PUBLISH` existem como permissões declaradas e
**não são aplicadas** nas rotas.

## Decisão

### Fase 1 — escopo de dados (agora, sem sessão)

1. **Um tenant fixo.** O `organization_id` do operador único é resolvido por uma porta
   `TenantContext` (em `application/ports.py`), com implementação single-tenant que devolve
   o tenant configurado. Nenhum `organization_id` vem de query string em rota de escrita.
2. **Coluna aditiva.** Migração aditiva adiciona `organization_id` (FK para
   `studio.organizations`, `NOT NULL`) nas tabelas de trabalho, com **default** = tenant
   único existente. Nada é apagado; dados existentes ficam no tenant default.
3. **Filtro em repositório.** Toda consulta de vídeo/asset/render/produção/publicação passa
   a filtrar pelo tenant do contexto. O repositório recebe o escopo, não o descobre.
4. **Sem mudança de comportamento visível.** Com um tenant só, o produto se comporta igual.
   O ganho é que a fronteira existe e é testável.

### Fase 2 — autorização por papel (quando houver mais de um usuário)

1. **Sessão** substitui Basic auth; `TenantContext` passa a vir da sessão verificada.
2. **RBAC** aplicado na borda: `CREATE_VIDEO`, `EDIT_VIDEO`, `APPROVE_*`, `PUBLISH` viram
   guardas de rota, com o papel vindo de `memberships`.
3. **Auditoria** de mudança de papel em `membership_audit` (já existe).

## O que **não** se faz nesta fase

- Não se cria sessão, login, cookie ou JWT.
- Não se aplica RBAC nas rotas (só a porta e o escopo de dados).
- Não se migra dados entre tenants.
- Não se cria administração de organizações.

## Consequências

**Prós:** a fronteira de dados nasce correta e barata; a fase 2 não precisa reescrever
repositórios, só trocar a origem do contexto e ligar as guardas. Testes com dois tenants
sintéticos passam a ser possíveis.

**Trade-offs:** colunas `NOT NULL` com default exigem migração cuidadosa; toda consulta
nova precisa lembrar do filtro (mitigado por teste de arquitetura/consulta).

**Riscos e mitigação:**

| Risco | Mitigação |
|---|---|
| Consulta sem filtro de tenant | teste que varre repositórios e exige filtro; revisão de PR |
| `organization_id` vindo de query string | proibido em rota de escrita; teste de contrato |
| Migração quebrar dados existentes | aditiva com default; ensaio em banco efêmero |

## Regras verificáveis

1. Nenhuma rota de escrita aceita `organization_id` do cliente.
2. Todo repositório de trabalho filtra pelo tenant do contexto.
3. Com um tenant, o comportamento observável é idêntico ao atual (suíte verde).
4. A fase 2 não exige mudança em repositório, só em `TenantContext` e guardas de rota.

## Implementação (quando entrar)

- `application/ports.py`: `TenantContext`.
- `composition.py`: implementação single-tenant a partir de `Settings`.
- Migração aditiva: `organization_id` nas tabelas de trabalho + índice por tenant.
- `adapters/postgres/*`: filtro de escopo em vídeo/asset/render/produção/publicação.
- Testes: dois tenants sintéticos não se enxergam; rota de escrita recusa `organization_id`
  do cliente.
