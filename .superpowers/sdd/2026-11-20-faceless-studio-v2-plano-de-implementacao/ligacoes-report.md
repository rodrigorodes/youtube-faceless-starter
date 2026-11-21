# Pendência de ligação L2 — Mutações da tela de Equipe (F11)

**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/ligacoes`
**Branch:** `feat/ligacoes` (base `4db8ae1`)
**Situação:** fechada — as mutações de Equipe estão expostas na rota, com o RBAC do domínio, o
ator autenticado do painel e auditoria de quem executou. Sem push e sem merge.
**L1 não foi tocado** (depende da F8). **L3 só confirmado** (sem alteração).

## Commits desta fatia

- `cadb251` `feat(equipe): expõe as mutações da Equipe (L2) com ator do painel e auditoria`
- `b3f6812` `test(equipe): RBAC 403/owner, auditoria do ator e BYOK sem vazamento`

## Como o ator foi obtido (o achado que destrava)

O painel já autentica o operador e já usa esse principal como ator em outro fluxo:

- **Basic auth** em `renderer/app/studio/api/routes.py:95` (`_authenticate`): lê
  `STUDIO_BROWSER_USER` / `STUDIO_BROWSER_PASSWORD` e valida o cabeçalho `Authorization: Basic`
  (o router inteiro depende de `_authenticate`).
- **Precedente do ator** em `renderer/app/studio/api/routes.py:856`: `approved_by =
  os.getenv("STUDIO_BROWSER_USER") or "painel"` — o mesmo principal humano já vira o autor da
  aprovação de roteiro.

O que faltava não era "um ator" (ele existe), e sim **derivar o papel** dele no domínio. A rota
passa a resolver o principal em **vínculo ativo na organização**:

- `ResolveActor` em `renderer/app/studio/application/saas.py:185` (método `execute` na linha 195):
  aceita o e-mail (`lower`) ou o id do usuário (32 hex), acha o vínculo da organização e devolve
  `Actor(user_id, email, role)`. Sem vínculo ativo ou vínculo de outra organização → nega
  (`AuthorizationDenied`). Nunca cria usuário nem vínculo: identificar não é cadastrar.
- Helper da rota em `renderer/app/studio/api/routes.py:1020` (`_team_actor`): pega
  `STUDIO_BROWSER_USER` do ambiente e chama `ResolveActor`.

Consequência operacional (honesta): o operador do painel precisa **ser** um membro da organização
(o `STUDIO_BROWSER_USER` igual ao e-mail do membro, ou ao id do usuário). Fora disso a mutação é
403. É o que torna o RBAC real sem OIDC — o papel não é um campo enviado pelo cliente nem um
"bootstrap" fixo.

## O que foi exposto (rotas JSON)

Padrão do projeto: rotas no router único (`api/routes.py`), renderização no módulo próprio
(`api/panel_team.py`). `api/panel.py` **não** foi tocado.

| Método | Rota | Serviço F11 |
|---|---|---|
| `POST` | `/studio/panel/equipe/members` | `InviteMember` (link 201) |
| `PATCH` | `/studio/panel/equipe/members/{membership_id}` | `ChangeMemberRole` |
| `DELETE` | `/studio/panel/equipe/members/{membership_id}?organization_id=` | `RemoveMember` |
| `POST` | `/studio/panel/equipe/keys` | `RegisterByokKey` (201) |
| `POST` | `/studio/panel/equipe/keys/{key_id}/rotate` | `RotateByokKey` |
| `DELETE` | `/studio/panel/equipe/keys/{key_id}?organization_id=` | `RevokeByokKey` |

`run()` ganhou o mapeamento de erro de domínio: 403 (`AuthorizationDenied`), 404
(`MembershipNotFound`/`KeyNotFound`), 409 (`DuplicateMembership`/`DuplicateProviderKey`/
`LastOwnerRequired`/`KeyRevoked`) e 422 (`MembershipInvalid`/`KeyInvalid`/`UnknownRole`/`SaasError`).

### Auditoria (quem fez)

`actor.user_id` é gravado por operação — o mesmo "registrar o autor" que `approved_by` já faz:

- BYOK: `byok_key_audit.actor_user_id` (coluna existente da F11-04).
- Vínculo: **nova** `studio.membership_audit` (migração `0031_membership_audit.sql`), com
  `actor_user_id`, `action` (`invited`/`role_changed`/`removed`) e `role`. `membership_id` sem FK
  de propósito — a auditoria sobrevive à remoção do vínculo.

## Resultado dos testes de autorização

`tests/test_team_admin_api.py` (8 testes, Postgres descartável real):

- `viewer` autenticado **não** registra chave → **403**; `owner` → **201**.
- `viewer` **não** convida membro → **403** e **nenhum** vínculo é criado (contagem inalterada);
  `owner` cria o vínculo (`reviewer`) → **201** e o audit guarda o ator (`owner`, `invited`).
- Alteração de papel pelo `owner` → audit `role_changed`.
- `owner` rotaciona e revoga; `byok_key_audit` = `created, rotated, revoked`.
- Principal **sem vínculo** na organização → **403**.
- Papel desconhecido (`admin`) → **422** sem tocar no repositório.

## Resultado dos testes de não-vazamento

- `test_key_value_never_reaches_the_response_or_the_log`: o valor sintético **não** aparece no
  corpo da resposta, **nem em base64**, e **não** aparece em `caplog` (nível DEBUG). O corpo do
  201 traz só `provider`, `mask`, `fingerprint`, `status`, `datas` e `id` — sem `value`,
  `secret_name` ou `secret_scope`. O valor só existe no cofre (JSON `0600` em pasta `0700`).
- `test_rotate_and_revoke_...`: rotação e revogação também não ecoam valor nenhum.
- Endpoints de `value` sem `min_length`/`max_length` no Pydantic, justamente para a validação ser
  a de domínio (`validate_byok_value`), que **nunca** ecoa o valor numa mensagem de erro — evita a
  chave reaparecer num corpo de 422.
- GET HTML da Equipe continua sem o valor (teste da F11 mantido).

## Honestidade da tela (`api/panel_team.py`)

- As constantes `RUNTIME_NOTE`/`ACTIONS_UNAVAILABLE_NOTE` e os textos da tela foram reescritos:
  a alegação antiga ("as ações exigem ator autenticado (F11-02)") era **falsa** e saiu.
- Com organização, os controles são executáveis (formulários + JS com `nonce`): adicionar/alterar
  membro, adicionar/rotacionar/revogar chave. Sem organização, continuam desabilitados com motivo
  (não há o que gerir).
- Continua **declarado como indisponível**, com motivo: login por **SSO/OIDC (F11-02)** como fonte
  de identidade, **envio do e-mail de convite**, **cobrança/créditos** e **isolamento de runtime por
  tenant**. Nada foi inventado.

## L3 — "Vídeos" com destino real (confirmação, não redesenho)

Resolvido em `80d7f4f`; segue válido e sem regressão:

- `renderer/app/studio/api/panel.py:95`: item de nav `("videos", "Vídeos",
  f"{base_href}#videos-section")`.
- `renderer/app/studio/api/panel.py:2421`: `<section ... id="videos-section">`.
- `tests/test_ux_contract.py::test_video_detail_uses_the_shell_and_videos_has_a_real_destination`
  **passa** (destino `href="/studio/panel#videos-section"` e `aria-current` correto).

## Contagens reais (Postgres próprio `lig-pg`)

Postgres descartável próprio: container **`lig-pg`**, rede **`lig-net`**, `--tmpfs
/var/lib/postgresql/data:rw,size=1g`, prova de 64 hex em `/budget-test-proof/proof` (montada `:ro`
e lida por `pg_read_file`). Passadas **as duas** variáveis (`STUDIO_TEST_DSN` **e**
`STUDIO_BUDGET_DISPOSABLE_DSN`) **mais** `STUDIO_BUDGET_TEST_PROOF_FILE` — os ~100 testes de
orçamento **não** foram pulados em silêncio.

- Foco F11 + arquitetura + UX + db (`test_saas_domain`, `test_saas_application`, `test_saas_repo`,
  `test_team_page`, `test_team_admin_api`, `test_db`, `test_architecture`, `test_ux_contract`):
  **87 passed**.
- Novos: `test_team_admin_api.py` **8**; `test_saas_application.py` +4 (ResolveActor ×3 e auditoria
  das mutações); `test_saas_repo.py` +1 (`audit_membership`); `test_team_page.py` +1 (tela honesta).
- Suíte completa em **4 partições sequenciais** (imagem `faceless-v2-hygiene-test-local:latest`,
  `-p no:cacheprovider`, `--tb=short`), por pressão de memória do host:

  | Partição | passed | skipped | failed |
  |---|---|---|---|
  | 1 | 439 | 0 | 0 |
  | 2 | 695 | 0 | 0 |
  | 3 | 564 | 1 | 0 |
  | 4 | 320 | 34 | 2 |
  | **Total** | **2018** | **35** | **2** |

- **35 skipped**: todos "Node.js necessário/ausente" (workflow e um teste de painel) — nada de F11.
- **2 failed**: `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable`
  e `::test_extracted_starter_runs_contract_snapshot_and_backup_import`, ambos por
  `Secret hygiene check could not complete safely`. **Falha ambiental de worktree**, não regressão:
  dentro do container o gitfile `.git` aponta para `.../worktrees/ligacoes` (caminho do host não
  montado), então `git rev-parse`/`git ls-files` do `package-starter.sh` abortam. Confirmado fora
  da suíte: `git rev-parse --show-toplevel` no container → `fatal: not a git repository: .../worktrees/ligacoes`.
  Nenhuma falha de render/publicação/OOM apareceu nesta rodada.
- `tests/test_architecture.py` e `tests/test_ux_contract.py`: **verdes** (nada de mídia/SDK no
  núcleo; contrato de UX íntegro).

## Higiene de segredos

- `python3 scripts/secret_hygiene.py scan` → **Secret hygiene check passed** (com os arquivos desta
  fatia staged; o scanner usa `git ls-files --stage`). Rodou inclusive na worktree.
- Todos os valores de teste são inequivocamente sintéticos (`synthetic-lig-...`), nenhum parece
  credencial. Nenhum valor de chave é impresso em teste, relatório ou log.
- O veredito do gate continua sendo o do `main` com gitdir real.

## Restrições cumpridas

- Só caminhos desta fatia; **sem** `git add -A`; **sem push** e **sem merge**.
- Não toquei em `domain/render_plan.py`, `domain/ticks.py`, `contracts/`,
  `scripts/export_contracts.py`, `api/panel_production.py`, `api/panel_channels.py`,
  `application/channels_page.py`, nem em `api/panel.py`.
- `domain/`/`application/` sem mídia/SDK (arquitetura verde). Migração `0031_...` (0024–0030
  intocados) adicionada às **duas** listas de `tests/test_db.py`.
- TDD (RED → GREEN): o novo arquivo de rota começou em 404 e fechou verde.

## O que da F11 continua indisponível (declarado, não fingido)

- **Login/SSO/OIDC (F11-02)** como fonte de identidade — o ator é o operador do painel, não uma
  sessão federada; sem MFA, sem sessão de usuário, sem troca de senha.
- **Envio do e-mail de convite** — o convite cria o vínculo `invited`, mas nenhum e-mail sai.
- **Cobrança/créditos/billing** (F11-06) e tabela de preços da plataforma (F11-05 parcial).
- **Isolamento de runtime por tenant** (storage, jobs, filas, logs) — registros/custos/segredos já
  têm fronteira por organização testada; o resto segue compartilhado (F11-03 parcial / F11-07 fora).
- **L1 — "Reautorizar" da tela de Canais:** intocado por depender da F8 (OAuth real).
