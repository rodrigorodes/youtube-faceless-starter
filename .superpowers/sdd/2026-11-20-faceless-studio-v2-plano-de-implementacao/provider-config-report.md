# Relatório — superfície de configuração de providers + porta `voice` + `PUT …/config`

Fatia: alinhar a **superfície** (`.env.example`, `docker-compose.yml`, `scripts/doctor.py`, docs) ao
padrão novo de providers, corrigir a porta `voice` (o `model` do spec virou decorativo) e fechar a
lacuna do override por projeto.

- Worktree: `…/worktree/39a258/provider-config`, branch `feat/provider-config`, base `d4ec5e6`.
- **Mecanismo não tocado**: `application/config.py` (4 portas, spec `<provedor>:<modelo>`,
  precedência `Project.config` → env → default) e `composition.py` (o único `register` novo é o
  caso de uso, não um provider).
- Sem `git add -A`; sem push/merge. Higiene e segredos abaixo.

## Commits

| # | Assunto | Arquivos |
|---|---------|----------|
| 1 | `chore(config): alinha .env.example/compose/doctor/docs ao padrão de providers` | `.env.example`, `docker-compose.yml`, `scripts/doctor.py`, `tests/test_doctor.py`, `docs/04-variaveis-de-ambiente.md` |
| 2 | `fix(voice): PiperVoice honra o model do spec (PIPER_VOICE como override do caminho)` | `renderer/app/rich.py`, `renderer/app/studio/adapters/voice_piper.py`, `renderer/Dockerfile` |
| 3 | `feat(studio): PUT /studio/projects/{id}/config (override por projeto)` | `renderer/app/studio/application/secrets.py`, `…/application/ports.py`, `…/application/use_cases.py`, `…/adapters/postgres/repo.py`, `…/composition.py`, `…/api/routes.py`, `tests/test_channel_api.py` |
| 4 | `docs(status): relatório da fatia provider-config` | este arquivo (`git add -f`) |

## 1. Tabela variável → quem lê → ação

Evidência por `grep` em `renderer/ app`, `scripts/`, `tests/` (contagem e arquivos). "Antes" é o estado
em `d4ec5e6`.

| Variável | Lida por (antes) | Ação |
|----------|------------------|------|
| `AI_PROVIDER` | `scripts/doctor.py:86` (detecção do bridge) + `tests/test_doctor.py:84` | **removida** de `.env.example`; doctor reescrito para o padrão novo; teste atualizado para `STUDIO_TEXT` |
| `IMAGE_PROVIDER` | `scripts/doctor.py:86` | **removida** de `.env.example` |
| `GEMINI_MODEL` | ninguém (0 hits) | **removida** |
| `VERTEX_PROJECT`, `VERTEX_LOCATION`, `VERTEX_MODEL` | ninguém (0 hits) | **removidas** |
| `GCP_CREDENTIALS_FILE` | ninguém (0 hits) | **removida** |
| `GEMINI_API_KEY` | só `tests/test_secrets_hygiene.py:250` (`assert re.search(r"(?m)^GEMINI_API_KEY=$", env)`) | **MANTIDA vazia** (exigência do gate). Comentário no `.env.example` diz que não é lida pelo código. |
| `OPENCODE_BRIDGE_TOKEN` | `text_opencode`, `image_opencode`, `composition`, `doctor`, `opencode-bridge.py`, testes | vivo — mantido (obrigatório quando alguma porta usa `opencode`) |
| `OPENCODE_BRIDGE_URL` | `composition.py` (settings) | vivo — mantido |
| `OPENCODE_BRIDGE_PORT` | `scripts/opencode-bridge.py:151` | vivo, **do bridge** — mantido e documentado como tal |
| `OPENCODE_MODEL` | `opencode-bridge.py:141` (+ menções em adapters) | vivo, **do bridge** — mantido e documentado |
| `OPENCODE_IMAGE_MODEL` | `opencode-bridge.py:146` (+ menções) | vivo, **do bridge** — mantido e documentado |
| `STUDIO_TEXT/IMAGE/VOICE/RENDERER` | `application/config.py` (`_DEFAULTS`), doctor, testes | as 4 passam a ser documentadas no `.env.example` com os defaults reais |
| `PIPER_VOICE` | `voice_piper.py`, `rich.py`, `scripts/tts_calibration.py`, `tests/test_tts_calibration.py` | vivo — agora override explícito do caminho; passado pelo compose |
| `PEXELS_API_KEY`, `STUDIO_SECRETS_ROOT`, `YOUTUBE_API_KEY`, `STUDIO_BUDGET_GUARD`, … | vivos | mantidos |

Removidas do `docker-compose.yml` (renderer, ninguém no container as lia): `AI_PROVIDER`,
`GEMINI_API_KEY`, `GEMINI_MODEL`, `VERTEX_PROJECT`, `VERTEX_LOCATION`, `VERTEX_MODEL`, `IMAGE_PROVIDER`.
Adicionadas: `PIPER_VOICE: ${PIPER_VOICE:-}` e um volume comentado `./voices:/opt/voices:ro`.

### O que ficou e por quê (incluindo `GEMINI_API_KEY`)

- **`GEMINI_API_KEY=` continua no `.env.example`, vazia.** `tests/test_secrets_hygiene.py:250` exige
  exatamente a linha `^GEMINI_API_KEY=$` dentro do starter. Ainda que nenhum código a leia, removê-la
  quebra o gate — mantida e comentada como exigência do teste.
- No **compose** eu **removi** `GEMINI_API_KEY`: verifiquei que o container (`renderer`) não a lê
  (`grep` em `renderer/` = 0) e que **nenhum** teste lê `docker-compose.yml` (`grep` por
  `docker-compose`/`env.example` em `tests/` só acha `tests/test_doctor.py:91`, que lê `.env.example`,
  não o compose). Não é "dúvida": nada depende dela ali. Revertível trivialmente se o time preferir
  simetria com o `.env.example`.
- **`OPENCODE_MODEL` / `OPENCODE_IMAGE_MODEL` / `OPENCODE_BRIDGE_PORT`** têm nome "antigo" mas são
  **vivos**: `scripts/opencode-bridge.py` os lê para escolher o modelo (`:141`, `:146`, `:151`) e os
  adapters novos (`text_opencode`, `image_opencode`) delegam a ele. O `.env.example` agora diz, em
  comentário, que são **do bridge**, não do MVP antigo.

## 2. `scripts/doctor.py` (padrão novo)

Substituí a detecção morta (`AI_PROVIDER`/`IMAGE_PROVIDER`) por
`uses_opencode_bridge(values)`: o bridge é exigido quando alguma das 4 portas
(`STUDIO_TEXT/IMAGE/VOICE/RENDERER`) aponta para o provider `opencode`. Rodei o script
(`network=False`) em três cenários:

```
(A) .env padrão novo: STUDIO_TEXT=opencode + token do bridge
[OK  ] .env: presente
[aviso] .env permissões: mais aberta que 600 (rode chmod 600 .env)
[OK  ] POSTGRES_PASSWORD: definida
[OK  ] N8N_ENCRYPTION_KEY: definida
[OK  ] OPENCODE_BRIDGE_TOKEN: definida
Ambiente OK.                                          exit: 0

(B) .env copiado de .env.example (placeholders, STUDIO_* vazios)
[FALHA] POSTGRES_PASSWORD: placeholder do .env.example não trocado
[FALHA] N8N_ENCRYPTION_KEY: placeholder do .env.example não trocado
[aviso] OPENCODE_BRIDGE_TOKEN: em branco
2 falha(s) obrigatória(s).                            exit: 1

(C) nenhuma porta usa opencode (STUDIO_TEXT=demo, STUDIO_IMAGE=placeholder)
[OK  ] POSTGRES_PASSWORD: definida
[OK  ] N8N_ENCRYPTION_KEY: definida
[aviso] OPENCODE_BRIDGE_TOKEN: ausente
Ambiente OK.                                          exit: 0
```

## 3. Porta `voice` — o `model` agora troca a voz

**Defeito (medido).** `PiperVoice` guardava `self.model` e nunca o usava; `speak()` chamava
`rich.synthesize_speech`, que carregava a voz de `os.getenv("PIPER_VOICE", "/opt/voices/pt_BR-faber-medium.onnx")`
(`rich.py:31`). Resultado: `STUDIO_VOICE=piper:<qualquer>` e `Project.config.voice` **não trocavam a voz**.

**Correção.**

- `voice_piper.py`: `voice_path(model)` deriva `/opt/voices/<model>.onnx` do spec. `PiperVoice.speak`
  passa esse caminho pela porta nova `rich.use_voice(...)`.
- `rich.py`: `synthesize_speech` escolhe a voz por **`PIPER_VOICE` (caminho explícito) > voz do spec >
  `DEFAULT_VOICE`** (`/opt/voices/pt_BR-faber-medium.onnx`). Cache por caminho; **arquivo ausente →
  `FileNotFoundError` citando o caminho esperado** (nunca cai para outra voz em silêncio).
- `renderer/Dockerfile`: **removido `ENV PIPER_VOICE=/opt/voices/pt_BR-faber-medium.onnx`**. Com a
  precedência acima, manter esse `ENV` tornaria `STUDIO_VOICE` decorativo **no container** (o env
  sempre venceria). O default não muda: o spec default `piper:pt_BR-faber-medium` deriva exatamente o
  mesmo arquivo; `rich.DEFAULT_VOICE` cobre chamadores diretos.

**Por que `rich.use_voice` (e não um 3º parâmetro).** `tests/test_image_adapters.py` faz
`monkeypatch.setattr(rich, "synthesize_speech", fake)` com fakes de **2 argumentos** (`fake`, `silent`,
`slow`) — trava dada: não quebrar isso. Passar a voz como 3º argumento quebraria os fakes; a porta
`use_voice` (context manager que restaura o valor) mantém a chamada com 2 argumentos e o seam intacto.
`rich.synthesize_speech` continua 2-arg e é onde mora a checagem de arquivo ausente (nos testes ela é
pulada porque `synthesize_speech` é monkeypatched).

**Via limpa para outra voz (escolhida: volume + `PIPER_VOICE`, a que menos mexe na imagem).** Nada é
adicionado à imagem; nenhum `ARG` novo. Monte o `.onnx` (+ `.onnx.json`) em `/opt/voices` e aponte
`PIPER_VOICE`, **ou** use `STUDIO_VOICE=piper:<nome>` para uma voz já presente em `/opt/voices`.
Documentado em `.env.example`, `docs/04` e no volume comentado do compose.

**Vozes pt_BR existentes no repositório do Piper (verificadas na API do HF):** `faber`/`medium`
(atual), `cadu`/`medium`, `jeff`/`medium`, `edresson`/`low`.

**DECLARADO (obrigatório): trocar a voz invalida a calibração de duração.** `domain/narration_duration.py`
mediu `MEASURED_*` (172,0 wpm, pausa 0,40 s/marca, overhead 0,65 s) **só** para `pt_BR-faber-medium`;
com outra voz o erro volta (antes de calibrar era +15,6%). `tests/test_tts_calibration.py` **pula**
(compara hash da voz e versão do Piper) em vez de falhar — a perda do guarda é silenciosa. Caminho de
recalibração: `scripts/tts_calibration.py` (+ `scripts/tts_calibration_samples.json`). **Não recalibrei**
(depende da voz escolhida e de medição real). Está em `.env.example` e em `docs/04` (regra 6).

## 4. Lacuna real: `PUT /studio/projects/{id}/config` — **implementado**

A rota `GET …/config` existia; não havia como **escrever** o override por projeto (`ProjectIn` só tem
`name`/`niche`/`language`; sem `PUT`). Implementei o mínimo:

- `SetPublicProjectConfig` (`application/secrets.py`): valida por **`ProjectConfig`**
  (`extra="forbid"` ⇒ chave desconhecida é recusada), exige as 4 portas, valida cada valor com
  `parse_spec` (`<provedor>:<modelo>`; inválida ⇒ `ProviderSpecInvalid` ⇒ 422) e persiste.
- Correção de segurança: a rota recebe o corpo **cru (`dict`)**, não `ProjectConfig` como body do
  FastAPI. O handler 422 padrão do FastAPI serializa `exc.errors()`, que inclui `input` (o valor cru)
  — postar uma chave-semente como `OPENAI_API_KEY: "sk-…"` vazaria o valor. Validando em aplicação,
  o 422 só lista os **nomes** recusados. Teste cobre isso (`"LEAK" not in texto`).
- `VideoRepository.set_project_config` (porta) + `PostgresVideoRepository` (`UPDATE … RETURNING`,
  `Jsonb`). Coluna `config jsonb` já existia (`0001_init.sql`) — **sem migração**.
- Wiring em `UseCases`/`composition.py`. Resposta sempre `sanitize_project_config`.

Motivo de ter implementado: a decisão foi limpa e localizada, não exigiu mudança de produto — o
override passa a ser alcançável e validado, com o formato já definido pelo `ProjectConfig.resolve`.

## 5. Validações executadas

Imagem `yfs-test:latest` (py3.12.16, fastapi 0.115.12, pydantic 2.11.4 — casa com `renderer/requirements.txt`).
Postgres descartável próprio (`pcfg-pg`, `postgres:16-alpine`, tmpfs, prova de 64 hex em
`/budget-test-proof/proof` montada no banco e no runner; `STUDIO_TEST_DSN` e
`STUDIO_BUDGET_DISPOSABLE_DSN` juntos).

| Suíte | Resultado |
|-------|-----------|
| `test_ports.py`, `test_channel_secrets.py`, `test_doctor.py`, `test_rich.py`, `test_image_adapters.py`, `test_provider_catalog.py`, `test_provider_service.py` | **81 passed** |
| `test_composition.py`, `test_studio_api.py`, `test_studio_auth.py`, `test_studio_browser_security.py`, `test_render_adapters.py`, `test_text_adapters.py` | **42 passed, 22 skipped** |
| `test_db.py`, `test_repo.py`, `test_channel_api.py` (inclui o novo `PUT …/config`), `test_channel_secrets.py` (com DB) | **46 passed** |
| `test_composition.py`, `test_studio_api.py`, `test_panel_api.py`, `test_render_api.py`, `test_publish_api.py`, `test_publication_api.py`, `test_trends_api.py`, `test_team_admin_api.py` (com DB) | **93 passed** |
| `test_rich.py`, `test_render_plan_executor.py`, `test_render_plan_builder.py`, `test_render_plan.py`, `test_render_adapters.py`, `test_tts_calibration.py`, `test_render_cache.py`, `test_render_regeneration.py`, `test_render_quality_e2e.py` | **121 passed, 4 skipped** (os skips são o guarda de calibração da voz, já previstos) |
| `python3 scripts/secret_hygiene.py scan` | **Secret hygiene check passed** |
| `tests/test_secrets_hygiene.py` (host) | **31 passed, 1 failed** |

O único `failed` é `test_extracted_starter_runs_contract_snapshot_and_backup_import`, cujo teste interno
(`test_contracts_snapshot.py::test_committed_contracts_match_code`) diverge **por versão do pydantic**:
o host tem 2.5.0 e serializa `"minimum": 0.0`, o repo gera `"minimum": 0`. **Pré-existente e não
relacionado**: rodei o mesmo teste com as mudanças em `git stash` (base `d4ec5e6`) e ele falha
idêntico. O assert crítico do gate — `^GEMINI_API_KEY=$` no starter — **passa** (comprovando que a
linha obrigatória segue no `.env.example`).

`docker compose config`: `docker-compose.yml` e `docker-compose.test.yml` válidos (exit 0). O renderer
resolvido **não** tem mais `AI_PROVIDER`/`GEMINI_*`/`VERTEX_*`/`IMAGE_PROVIDER`; tem `PIPER_VOICE` e
`STUDIO_*`. Não subi o stack (VM apertada); validei só o arquivo.

## 6. Limitações / não feito

- Não recalibrei a voz (declarado, não escondido): trocar a voz reabre o erro de duração até rodar
  `scripts/tts_calibration.py`.
- `test_secrets_hygiene.py` só passa 100% na imagem pinada (pydantic 2.11.4); no host há 1 falha
  pré-existente de serialização de contrato (provada no base).
- `STUDIO_SECRETS_ROOT` não é passado pelo compose hoje (default = `<STUDIO_STORAGE_ROOT>/secrets`);
  não o adicionei para manter a mudança mínima — segue configurável por env.
- Não toquei em `docs/12,14,15,16,17,20`, `backups/`, `credentials/`, `workflows/`.
