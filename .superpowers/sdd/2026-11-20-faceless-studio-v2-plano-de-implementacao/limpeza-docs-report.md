# Limpeza da camada legada de documentação, exemplos e scripts — relatório

**Data:** 2026-11-21
**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/limpeza-docs`
**Branch:** `feat/limpeza-docs` · **Base:** `81915ec`
**Escopo autorizado:** remover/arquivar a documentação, os exemplos e os scripts que descrevem
fluxos já removidos (o `POST /videos` legado, o `main.py` antigo e o provider Vertex), mantendo
apenas o padrão novo (Faceless Studio V2). **Regra de ouro:** só remover o que for provado
obsoleto (o comando, a rota ou a variável que o doc manda usar não existe mais no código).

Fatos que ancoram as decisões (verificados nesta worktree):

- `renderer/app/main.py` é só a fachada do Studio (30 linhas); `/videos` e `/videos/{path:path}`
  respondem **410 Gone** (`main.py:27-30`).
- `renderer/app/studio/composition.py` + `application/config.py` registram os providers do
  caminho novo: texto `opencode`/`demo`; imagem `opencode`/`placeholder`/`stock`/`veo`; voz
  `piper`; renderer `ffmpeg`. **Não existe provider `vertex`, `gemini` nem `luna`.**
- `grep` de `AI_PROVIDER`, `GEMINI_*`, `VERTEX_*`, `GCP_CREDENTIALS_FILE`, `IMAGE_PROVIDER` em
  `renderer/app/studio/**` e `scripts/opencode-bridge.py`: **nenhum leitor**. O único resquício de
  `luna` é o *modelo* `opencode:openai/gpt-6-luna` (spec de `STUDIO_TEXT`), que é vivo.
- Os workflows `workflows/01-create-short.json` e `workflows/02-create-and-publish.json` foram
  removidos em `d4fa4c1` (só restam `03`/`04`/`05`).

---

## 1. Commits

| # | Commit | Conteúdo |
|---|--------|----------|
| 1 | `chore(docs): remove camada legada (docs 01/05/06/09/11, scripts test-create, examples rich, compose.vertex)` | `git rm` dos 10 arquivos, cópia verbatim em `archive/docs/`, limpeza de `ALLOWED_FILES` |
| 2 | `docs: atualiza referencias apos remover o legado (README, 02, 03, 04, 07)` | links e contrato dos docs vivos |
| 3 | `docs(limpeza-docs): relatorio da limpeza` | este relatório |

---

## 2. Arquivo/doc → evidência de obsolescência → ação

| Arquivo / doc | Evidência de obsolescência (comando/rota/variável que não existe mais) | Ação |
|---|---|---|
| `docs/01-como-o-workflow-executa.md` | Manda `POST :8000/videos` (**410**), descreve o `main.py` antigo e importa `workflows/01-create-short.json` (ausente desde `d4fa4c1`). | **removido + arquivado** |
| `docs/06-vertex-ai.md` | `AI_PROVIDER=vertex`/`VERTEX_*` não existem no caminho novo (nenhum leitor); provider `vertex` não registrado; `docker-compose.vertex.yml` removido. | **removido + arquivado** |
| `docs/09-modo-rich-imagens-voz-musica.md` | Manda `mode:"rich"` no `POST /videos` (**410**); `IMAGE_PROVIDER` não é lido. (`rich.py` sobrevive como biblioteca do Studio — ver §3.) | **removido + arquivado** |
| `docs/05-validacao-realizada.md` | Registro histórico da validação do MVP (19/11/2026). Não é guia operacional. | **arquivado** (história) |
| `docs/11-validacao-lenovo.md` | Roteiro histórico **pendente**, cita `AI_PROVIDER`/`IMAGE_PROVIDER`, `scripts/test-create.ps1` e `examples/rich-smoke.json`. | **arquivado** (história) |
| `docker-compose.vertex.yml` | Único propósito é montar a ADC do Vertex — provider que não existe no caminho novo. | **removido + arquivado** |
| `scripts/test-create.sh` | `curl -X POST 'http://localhost:8000/videos'` → **410**. | **removido + arquivado** |
| `scripts/test-create.ps1` | `Invoke-RestMethod ... /videos` → **410**. | **removido + arquivado** |
| `examples/rich-smoke.json` | Payload `"mode":"rich"` do `POST /videos` legado. | **removido + arquivado** |
| `examples/ade-2026-rich-publish.json` | Payload `"mode":"rich"` + `scenes` do fluxo legado. | **removido + arquivado** |
| `README.md` | Links para docs removidos; contrato `POST /videos`; `scripts/test-create.*`. | **editado** |
| `docs/02-configuracao-macos.md` | Link p/ `01`; `bash scripts/test-create.sh`; importa `workflows/01-create-short.json`; webhook `faceless-create`; `GEMINI_API_KEY`. | **editado** |
| `docs/03-configuracao-windows.md` | Link p/ `01`; `.\scripts\test-create.ps1`; importa `workflows\01-create-short.json`; webhook; `GEMINI_API_KEY`. | **editado** |
| `docs/04-variaveis-de-ambiente.md` | Linhas de `AI_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `VERTEX_*`, `GCP_CREDENTIALS_FILE`, `IMAGE_PROVIDER` (variáveis mortas); link p/ `06`; `/videos segue normal`. | **editado** |
| `docs/07-openai-luna-oauth.md` | `AI_PROVIDER=opencode` (morto); links p/ `01` e `05`; `scripts/test-create.sh`; erro `500 AI_PROVIDER=opencode ...`. | **editado** (bridge é vivo) |
| `scripts/secret_hygiene.py` | `ALLOWED_FILES` citava 3 arquivos removidos. | **editado** |

Cada arquivo removido foi copiado **verbatim** para
`.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/docs/` (o `git`
detectou os 10 como *rename*, o que confirma byte a byte). sha256 dos arquivados:

| Arquivo arquivado | sha256 |
|---|---|
| `01-como-o-workflow-executa.md` | `5d5d5590c6329eb64fe745f3ed92655e3c3f4e985d772ee508bd8526687d394b` |
| `05-validacao-realizada.md` | `fe0228e08599302bdbbecdd9add0a300cd0583f4f01b92a38c1d53eb72a8b10c` |
| `06-vertex-ai.md` | `97b6dcaa007e80809b43dd03cc51f62bc1a2b863e113bb2f8c90ce3c57c24e41` |
| `09-modo-rich-imagens-voz-musica.md` | `5296d2a4253ad68a3d91921977fa4e129ba2e385b0f3ea294993548b9565d014` |
| `11-validacao-lenovo.md` | `bea0d03435a42893dffe2ec4431dca91ff1885274cd82353ef27f9efaa4de8a8` |
| `ade-2026-rich-publish.json` | `4efa3793e8563b368f2a279b6f996f3168e8a9eae5b69e0f9e486a90aae20679` |
| `docker-compose.vertex.yml` | `ae5a5bb0b4746093db00c21e8c5c9614ea1ac8be5d23418298cb0e271789cbbd` |
| `rich-smoke.json` | `8c60cb4fdb338799c4a1c5d400dcb86c00faa3d6d0976d24c3f4fd09118c0538` |
| `test-create.ps1` | `507985b929536b85dd407f0935b05736d034a0cdc267fe9f3bd7dd06f4b8ada1` |
| `test-create.sh` | `25cc308cb579eff32f9a214ab9e7f2114014a802f691526325702722ca173f6f` |

---

## 3. O que foi decidido manter (e por quê)

| Item | Decisão | Motivo / evidência |
|---|---|---|
| `examples/ade-2026-publish.json` | **Manter** | A pergunta era "ainda tem consumidor?". Sim: `docs/08-publicar-no-youtube.md` o usa (§5). Como o doc 08 **não** estava na lista autorizada de remoção, o exemplo fica junto. Se o 08 for arquivado depois, este vira órfão. |
| `docs/08-publicar-no-youtube.md` | **Manter, com ressalva** | **Não** estava na lista de mortos e traz um banner deliberado ("Fluxo legado removido → 15/18"). Porém o **corpo** é legado e prova-se obsoleto: importa `workflows/02-create-and-publish.json` (ausente desde `d4fa4c1`), chama `webhook/faceless-publish` (não existe; o 03 usa `faceless-publish-approved`) e baixa de `http://renderer:8000/videos/<id>/file` (**410**). Por "em dúvida, não remova e reporte", **mantive** — recomendo arquivá-lo numa próxima passada (e aí o `ade-2026-publish.json` junto). |
| `renderer/app/rich.py` | **Manter (intocado)** | É **vivo** no caminho novo: `studio/adapters/voice_piper.py` e `studio/adapters/render_plan_ffmpeg.py` o importam; `tests/test_rich.py` e `test_image_adapters.py` o exercitam. O que morreu foi o **payload** `mode:"rich"` do `/videos`, não a biblioteca. |
| `docker-compose.yml` (`AI_PROVIDER`, `GEMINI_*`, `VERTEX_*`, `IMAGE_PROVIDER`) e `.env.example` | **Manter** | Fora do escopo autorizado (é configuração, não doc/exemplo/script). São variáveis agora não lidas, mas removê-las mexe em deploy; e `.env.example` **precisa** manter `GEMINI_API_KEY=` — `tests/test_secrets_hygiene.py:250` exige essa linha no pacote do starter. Registrado como dívida. |
| `scripts/doctor.py` | **Manter** | Ainda é vivo e sua heurística usa `AI_PROVIDER`/`IMAGE_PROVIDER` (`doctor.py:86`); `tests/test_doctor.py:84` depende desse comportamento. Fora do escopo. |
| `workflows/03-publish-approved.json` | **Manter (intocado)** | Desativado por design (`workflows/README-publish-approval.md`). |
| `backups/`, `credentials/`, `storage/`, `contracts/`, `renderer/app/studio/**` | **Intocados** | Áreas proibidas pelo escopo. |
| `docs/10..20-*.md`, `16`, `adr/`, `contracts-versioning.md`, `p06-p07-offline.md` | **Intocados** | Vivos. |

---

## 4. Linhas ajustadas em `ALLOWED_FILES` (`scripts/secret_hygiene.py`)

Removi **3** entradas, todas apontando para arquivos que deixaram de existir (uma linha da lista
para cada):

| Linha | Motivo |
|---|---|
| `docker-compose.vertex.yml` | arquivo removido (override do Vertex; provider inexistente) |
| `examples/ade-2026-rich-publish.json` | arquivo removido (payload `mode:"rich"`) |
| `examples/rich-smoke.json` | arquivo removido (payload `mode:"rich"`) |

Mantive `examples/ade-2026-publish.json` na lista **porque o arquivo continua no repositório**
(consumido por `docs/08`). `docker-compose.yml`, `docker-compose.test.yml`, `workflows/03..05`,
`.env.example`, `README.md`, `renderer/*`, `scripts/backup.py`, `scripts/export_contracts.py`,
`tests/test_backup.py` ficaram intactos (todos existem e seguem entrando no pacote do starter).

---

## 5. Link-check dos docs vivos

Varredura de links relativos em `README.md`, `docs/*.md` (inclui `adr/`, `contracts-versioning.md`,
`p05-p07-continuation.md`, `p06-p07-offline.md`) e `workflows/README-publish-approval.md`, mais
`grep` pelos nomes removidos:

```
docs vivos verificados: 21
  nenhum link pendente em docs vivos / README / adr
```

Os únicos resquícios dos nomes removidos estão em **docs históricos de planejamento**, não em docs
vivos, e foram deixados de propósito (são registro do que foi planejado/feito):

- `docs/backlogs/Faceless_Studio_V2_Projeto_Completo/PLANO_MESTRE.md:38` — cita
  `docs/01-como-o-workflow-executa.md` como "referência histórica a reconciliar".
- `docs/superpowers/plans/2026-11-19-p00-p01-contracts-and-persistence.md` — plano que **criou**
  `scripts/test-create.sh`/`docs/11-validacao-lenovo.md`; é registro de execução, não documento vivo.

---

## 6. Higiene de segredos

```
$ python3 scripts/secret_hygiene.py scan
Secret hygiene check passed.   (rc=0)
```

---

## 7. Suíte de testes

Rodada em **partições** (8 grupos, sequenciais), imagem `faceless-v2-hygiene-test-local:latest`,
Postgres próprio **`limpd-pg`** na rede **`limpd-net`** (prova de 64 hex montada com `-v` no
**servidor**, exigida pelo guard `pg_read_file('/budget-test-proof/proof')`), com **as duas** DSNs
(`STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN`) e `STUDIO_BUDGET_TEST_PROOF_FILE`.

| | arquivos de teste | passed | failed | skipped | grupos verdes |
|---|---|---|---|---|---|
| **Antes** (base `81915ec`) | 131 | **2386** | 0 | 35 | 8/8 |
| **Depois** (`feat/limpeza-docs`) | 131 | **2386** | **0** | 35 | **8/8** |

Os números são **idênticos**: a limpeza não toca nenhum arquivo de teste, então a coleta não muda e
**nenhuma falha é nova**. O único arquivo de código tocado, `scripts/secret_hygiene.py`, continua
exercitado por `tests/test_secrets_hygiene.py` (verde, incluindo
`test_real_starter_archive_is_safe_and_keeps_scripts_executable`, que empacota o starter real com o
`.env.example`). O pacote do starter deixou de incluir `ade-2026-rich-publish.json`/`rich-smoke.json`
(saíram de `ALLOWED_FILES`), mas nenhum teste asserta a presença de `examples/`.

---

## 8. Reprodução

```bash
# higiene
python3 scripts/secret_hygiene.py scan

# suíte em partições (Postgres limpd-pg + rede limpd-net; prova montada no servidor)
docker network create limpd-net
docker run -d --name limpd-pg --network limpd-net \
  -v /private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ/proof:/budget-test-proof:ro \
  -e POSTGRES_PASSWORD=test postgres:16-alpine
GRUPOS=8 /private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/integ/suite_limpd.sh
```

Nada foi enviado (`push`) nem integrado (`merge`).
