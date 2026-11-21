# Fatia F11 — Preparação SaaS, multiusuário e BYOK (P2)

**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/f11-saas`
**Branch:** `feat/f11-saas` (base `e83af72`)
**Situação:** fatia estava adiada; **liberada pelo usuário em 2026-11-20**.
**Sem push e sem merge.** Só caminhos exatos; nenhum `git add -A`.

## Commits desta fatia

- `86488ca` `feat(saas): tenancy, papéis, BYOK e tela de Equipe (F11-01..05)`
- `b028d6f` `test(saas): F11 — papéis, isolamento cross-tenant, BYOK sem vazamento e contrato de UX`

## O que foi entregue

### F11-01 — Organization/Workspace/User/Role/Membership (parcial)
- `domain/saas.py`: `Role` (owner/editor/reviewer/viewer), `MembershipStatus` (active/invited),
  `Membership`, invariante `ensure_owner_remains` (o último owner não é rebaixado nem removido).
- Migração `0027_saas_multiuser_byok.sql`: `organizations`, `workspaces`, `users`, `memberships`
  com `UNIQUE(organization_id, user_id)` e `CHECK role IN ('owner','editor','reviewer','viewer')`.
- `organization_id` **anulável** em `projects` e em `usage_ledger` (`member_id` também): é o
  **caminho modelado**. Nada foi atribuído em massa e **nada em runtime isola por tenant** —
  declarado na própria tela (`RUNTIME_NOTE`) e no `<details>` técnico.

### F11-02 — RBAC com owner/editor/reviewer/viewer (parcial)
- Matriz de permissões em `domain/saas.py` e regra de autorização aplicada nos casos de uso
  (`InviteMember`, `ChangeMemberRole`, `RemoveMember`, `RegisterByokKey`, `RotateByokKey`,
  `RevokeByokKey`, `RecordKeyUse`). `require()` falha sem citar papel/permissão (não é oráculo).
- **Sessão/OIDC e auditoria genérica NÃO foram implementados.** A autorização é testada com o
  papel do ator passado explicitamente; a rota é de leitura e as ações aparecem indisponíveis
  com motivo (`F11-02`). Auditoria existe só para as ações de BYOK (`byok_key_audit`).

### F11-03 — Isolamento por tenant (parcial)
- `PostgresSaasRepository` filtra **toda** consulta pela organização do ator; a fronteira é o
  `WHERE`, não a memória do chamador.
- Consumo: `usage_rows` filtra por `usage_ledger.organization_id` e só rotula membro se o vínculo
  for da **mesma** organização (join por `organization_id`).
- Testes de vazamento cross-tenant: membros, chaves e consumo A↔B; `repo.key(A, keyB) is None`.
- **Fora:** storage, jobs, filas e logs continuam compartilhados (`storage_root` único, fila de
  render não modelada por tenant). Declarado, não mascarado.

### F11-04 — BYOK (backend/serviço entregue; UI de escrita fora)
- `domain/saas.py`: `mask_secret` (no máximo os 4 últimos; valor ≤ 12 fica todo mascarado),
  `fingerprint` (sha256), `validate_byok_value`/`validate_provider` (nunca ecoam o valor),
  `ByokKey` (sem campo de valor), `secret_scope("byok:<org>")`/`secret_name`.
- `application/saas.py`: registrar, rotacionar (mesmo id, nome de segredo novo, remove o antigo),
  revogar (remove o segredo do cofre) e uso autorizado; **compensação** quando o metadado falha
  depois do `store.set` (o valor órfão é removido). Auditoria `created/rotated/revoked/used`.
- Reusa a porta `SecretStore` da fatia H (`FileSecretStore`, diretório `0700`, arquivo `0600`).
- Única chave ativa por `(organization_id, provider)`; revogada libera o provider.
- **Fora:** criptografia em repouso além da permissão de arquivo (não há KMS/envelope);
  botões de gerir chave na UI (F11-02).

### F11-05 — Consumo por membro/tenant (parcial)
- Visão real de consumo atribuído por membro e por tenant, com os quatro rótulos honestos
  (Real/Estimado/Sem custo/Desconhecido) reusando `cost_breakdown`/`cost_summary_text`;
  ausência vira "sem registro de uso atribuído", **nunca** `US$ 0,00`.
- **Fora:** quotas e modelo de cobrança plataforma vs API do cliente (sem tabela de preços).

### Tela de Equipe (entregável pedido)
- `api/panel_team.py` + `GET /studio/panel/equipe`, entrando pela casca aprovada
  (`render_sidebar`) — módulo próprio, `api/panel.py` tocado só o mínimo (ícone/rota/nav).
- Dado real ou estado vazio explícito; ações indisponíveis reais (`disabled`, não focáveis) com
  texto; sem barra de progresso; IDs/fingerprints no `<details>` fechado; passa
  `assert_ux_contract(html, page=...)`.

## Os 9 cards: o que ficou fora e por quê

| Card | Situação | Motivo |
|---|---|---|
| F11-01 | parcial | Modelo + schema + caminho anulável; isolamento de storage não aplicado |
| F11-02 | parcial | RBAC de domínio testado; **sessão/OIDC e auditoria genérica fora** (não há login no produto) |
| F11-03 | parcial | Registros/custos/segredos com teste de vazamento; storage/jobs/filas/logs fora |
| F11-04 | entregue (serviço) | Valor só no cofre 0600; UI de escrita depende de F11-02 |
| F11-05 | parcial | Consumo por membro/tenant honesto; quotas e cobrança fora |
| F11-06 | **fora** | Billing/créditos/webhooks exige provedor de pagamento (decisão de produto) |
| F11-07 | **fora** | Deploy API/worker, object storage, backups/retensão: infraestrutura, não código desta fatia |
| F11-08 | **fora** | Revisão de termos/licenças (n8n, modelos, stock) é trabalho jurídico/documental |
| F11-09 | **fora** | Escala de workers, rate limit por tenant/provider, antifraude, SLO e plano de incidentes |

## Onde o mockup aprovado divergiu do produto real

1. **"Adiada · F11 (P2)" / "Ainda não implementado" / "Modelo proposto":** o modelo de dados, o
   RBAC e o BYOK de serviço existem; o que segue pendente é a sessão/OIDC (F11-02). A tela diz
   "runtime mono-usuário" em vez de "adiada".
2. **Dados ilustrativos** ("Ana Ribeiro", `*@exemplo.com.br`, "Estúdio Exemplo Ltda",
   "US$ 3,10/0,84/3,94", `sk-…••••7f2a`, `1,2 mi views`, `run_7f31`): o painel renderiza **dado
   real** ou **estado vazio explícito**; teste garante que nada disso embarca.
3. **Ações:** o mockup usa `<button aria-disabled="true">` (ainda focável). O produto usa
   `disabled` de verdade (não entra na ordem de foco) **com o motivo em texto**.
4. **Item de nav "Equipe SaaS · adiada" desabilitado:** o produto tem link funcional para
   `/studio/panel/equipe` (ajuste dos contratos de nav em `test_panel.py`/`test_panel_page.py`).
5. **Status "Rotacionada" como estado:** o produto mostra `Ativa`/`Revogada` e a idade de rotação
   como texto ("rotacionada há N d").
6. **Diálogo "Revogar esta chave BYOK?" com botões ativos:** não é renderizado; sem sessão não há
   revogação pela UI.
7. **Card "Orçamento do mês — Real US$ 0,07 …":** o produto usa o custo real do mês
   (`BuildPanel.month_cost`) ou "Não disponível".
8. **"Consumo por tenant — US$ 3,94 (ilustrativo) · chaves ativas 2":** o produto mostra o consumo
   **atribuído** (Real/Estimado/Sem custo/Desconhecido) e a contagem real; ausência não é zero.
9. **"Papéis" e "Organização e isolamento":** o texto canônico de papéis foi mantido (papel é
   permissão, não plano), mas organização/workspace vêm do banco ou viram estado vazio.

## Contagens reais (com o meu Postgres)

Postgres descartável próprio: container **`f11-pg`**, rede **`f11-net`**, `--tmpfs
/var/lib/postgresql/data:rw,size=1g`, prova de 64 hex em `/budget-test-proof/proof`
(montada `:ro` e lida por `pg_read_file` dentro do container). Passadas **as duas** variáveis
(`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) **mais** `STUDIO_BUDGET_TEST_PROOF_FILE`
— por isso os ~100 testes de orçamento **não** foram pulados.

- Testes novos da F11: **44 passed** — domínio 15, aplicação 14, repositório 8, tela/HTTP 7.
- Foco F11 + db + arquitetura + composition: **70 passed**.
- Suíte completa em processo único (imagem `faceless-v2-hygiene-test-local:latest`,
  `-p no:cacheprovider`, `--tb=short`): **1952 passed, 35 skipped, 18 failed** em 533 s.
  - 35 skipped são todos `node missing`/`node not installed` (`test_workflow_*`) — nada de F11.
  - 18 failed: 7 `test_publish_api`, 4 `test_render_adapters`, 4 `test_render_api`,
    1 `test_script_page`, 2 `test_secrets_hygiene`.
  - **Nenhuma falha em arquivo da F11.**
- Batidas seriais por lote, com o host menos carregado: **g1 425**, **g2 367**, **g3 275**,
  **g4a 160** (+1 skip), **g4b 196**, **g5a 31**, **g5b 428** (+34 skipped), `test_qa_report` 86 —
  total **1968 passed / 35 skipped**. Nessa passada `test_publish_api`,
  `test_render_adapters` e `test_render_api` **passaram**; `test_script_page` também.
- Qualificação da flakiness (não mascarada): numa re-execução sob pressão de memória do host
  (11 processos `pytest` de outras fatias), o `ffmpeg` morreu com **SIGKILL(9)** e derrubou os
  testes de render/publicação em cascata; a mesma seleção já havia passado isolada. São **OOM do
  ambiente**, não regressão desta fatia (não toquei em render).
- `test_secrets_hygiene`: 2 falhas **ambientais** — `scripts/package-starter.sh` chama
  `scripts/secret_hygiene.py`, que no contexto do archive aborta ("could not complete safely").
- O primeiro container foi criado com tmpfs de 512 MB e encheu de WAL
  ("FATAL: could not write init file"); recriado com 1 GB e `max_wal_size=128MB`.

## Higiene de segredos

`python3 scripts/secret_hygiene.py scan` **passou** com os arquivos desta fatia **staged**
(o scanner usa `git ls-files --stage`, então viu os novos). Na worktree o `.git` é gitfile e o
aviso do handoff dizia que o scanner abortaria; aqui ele **concluiu** — o veredito final continua
sendo o do `main` com gitdir real. Nenhum valor de chave é impresso em teste, relatório ou log;
todos os valores usados são inequivocamente sintéticos.

## Limitações declaradas

- O produto segue **mono-usuário**: não há sessão, login, OIDC nem auditoria genérica.
- Storage, jobs, filas e logs **não** estão isolados por tenant.
- A UI de gestão (convidar/gerir/revogar/rotacionar) **não** executa: depende de F11-02.
- Criptografia at-rest das chaves é a permissão de arquivo do `FileSecretStore` (`0700/0600`);
  não há KMS/envelope.
- F11-06..F11-09 fora, conforme a tabela acima.
