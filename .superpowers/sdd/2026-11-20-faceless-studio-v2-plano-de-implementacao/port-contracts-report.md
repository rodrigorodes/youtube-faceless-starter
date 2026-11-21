# Fatia `port-contracts` — contratos de porta e trava catálogo↔registro

**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/port-contracts`
**Branch:** `feat/port-contracts` (base `d4ec5e6`)
**Objetivo:** dar ao núcleo de render o outro lado da fronteira — provar que as
implementações **satisfazem** as portas e **travar a divergência catálogo↔registro** (a
classe de bug "config/painel mentindo"), mantendo o núcleo extensível sem tocar
`domain/`/`application/`.

## Commits

| Commit | Escopo |
| --- | --- |
| `ad4b12a` | `test(ports): contratos de porta e trava catálogo<->registro` — `renderer/app/studio/application/ports.py`, `tests/test_port_contracts.py` |
| `331143d` | `docs(ports): guia de extensão (provider novo e porta nova)` — `docs/21-extensao.md`, `README.md` |

Nenhum arquivo das outras fatias foi tocado (`rich.py`, `voice_piper.py`, `api/routes.py`,
`.env.example`, `docker-compose.yml`, `scripts/doctor.py`, `render_plan_ffmpeg.py`, `domain/`).
`composition.py` **não foi alterado** (só lido): o teste introspecta os `register(...)` reais
executando o `Studio`, sem duplicar a lista.

Mudança de produção: **exatamente** `@runtime_checkable` em 4 Protocols de `ports.py` (aditivo;
justificado abaixo). O resto é teste e doc.

## Invariantes novos (o que cada um prova)

Arquivo: `tests/test_port_contracts.py` (6 testes + 1 fixture). Resultado:
**18 passed, 2 skipped** ao rodar junto de `tests/test_architecture.py` e
`tests/test_composition.py` (os 2 skips são os testes de banco de `test_composition.py`, sem
`STUDIO_TEST_DSN` — não subi Postgres).

1. **`test_every_registered_provider_satisfies_its_port`** — *Registro ⇒ porta*.
   Constrói **cada** `(kind, name)` de `_REGISTRY` com um modelo dummy (`build(kind,
   "name:dummy")`) e afirma `isinstance(impl, Porta)` para `TextModel`/`ImageModel`/`Voice`/
   `Renderer`, mais `impl.name == name`. Prova: todo `register` produz um objeto com os membros
   da sua porta — um `register` apontando para uma classe incompleta reprova no CI em vez de
   estourar no meio de um render.

2. **`test_catalog_and_registry_have_no_drift`** — *Registro ⇔ catálogo*.
   Compara `{(impl.kind.value, impl.name)}` de `_provider_implementations(Settings())` (o
   catálogo que o painel usa, `F10-03`) com `set(_REGISTRY)`, **nos dois sentidos**
   (anunciado-sem-implementação e implementado-sem-anúncio) e contra a baseline
   `EXPECTED_CATALOG` (text=opencode,demo; image=opencode,placeholder,stock,veo; voice=piper;
   renderer=ffmpeg). Prova: nenhum provider anunciado como AVAILABLE deixa de ter registro, e
   nenhum registro fica invisível na configuração; mexer no catálogo passa a exigir atualização
   deliberada do teste e do guia.

3. **`test_the_drift_check_catches_both_directions`** — *prova de que o invariante 2 é
   load-bearing*. Alimenta `_drift()` com um drift fabricado e confirma que ele é detectado nas
   duas direções (mesmo espírito de `test_media_and_provider_guard_catches_violations` em
   `test_architecture.py`). Sem isto, a comparação poderia passar por vacuidade.

4. **`test_architecture_guard_still_bars_provider_sdks_from_the_core`** — a fronteira continua
   barrando SDK no núcleo. Importa `PROVIDER_SDKS`/`imports_of`/`violates` de
   `test_architecture`, cita **`elevenlabs` em `PROVIDER_SDKS`** e confirma
   `domain`/`application` limpos. Prova que dá para acrescentar um provider de nuvem (o
   exemplo do guia) sem importar o SDK no núcleo puro do Render Plan.

5. **`test_a_new_provider_enters_through_the_same_seams_without_touching_the_core`** —
   *extensibilidade sem tocar o núcleo*. Registra `_FakeVoice` pelo **mesmo** `register("voice",
   "fake", ...)` de produção, resolve por
   `ProjectConfig.resolve(overrides={"voice": "fake:pt_BR-x"}, env={})` + `build("voice",
   spec)` e **executa o `RunRender` real** (`application/render.py`) com fakes mínimos das
   outras portas. Afirma que a voz fake foi de fato usada (`voice.spoken`), que o job completou
   e que `renderer.spec.voice_id == "fake:pt_BR-x"`. **Nenhuma** alteração em
   `domain/`/`application/` foi necessária. A identidade `name:model` chegando ao render é
   exatamente o elo que o `PiperVoice` não honrava.

6. **`test_runtime_checkable_proves_member_presence_not_signatures`** — o limite honesto.
   Documenta que `@runtime_checkable` checa presença de membros, não assinatura: uma classe com
   `speak(self)` (aridade errada) ainda passa no `isinstance`. Por isso o invariante 5 (fluxo
   real) e os testes de comportamento de cada adaptador continuam necessários.

### `@runtime_checkable` (mudança aditiva em `ports.py`)

Adicionado em `TextModel` (`ports.py:88`), `ImageModel` (`ports.py:95`), `Voice`
(`ports.py:103`) e `Renderer` (`ports.py:109`) — só nos quatro onde a checagem estrutural faz
sentido (são os quatro `kind` de provider configuráveis por projeto). Sem o decorador o Python
recusa `isinstance` (`TypeError: Instance and class checks can only be used with
@runtime_checkable protocols`, confirmado em execução). É aditivo: nenhuma linha de
comportamento mudou; `ports.py` segue sem I/O e sem SDK.

## O que **não** dá para checar estruturalmente (e por quê)

- **Assinatura dos métodos.** `runtime_checkable` usa `hasattr` por membro; não valida aridade
  nem tipos. O teste 6 prova isso. Consequência: o contrato estrutural pega "faltou
  implementar", não "implementou errado".
- **Semântica do `model`.** O defeito real do `PiperVoice` (`self.model` decorativo; corrigido
  em `b067d4a` — "synthesize_speech carregava a voz de PIPER_VOICE e STUDIO_VOICE não trocava
  nada") **não** é pego por `isinstance` nem só por catálogo↔registro: piper estava registrado
  **e** no catálogo. Por isso o invariante 5 afirma que a identidade `name:model` da porta
  chega ao render — é o que cobre a parte semântica da mesma classe de bug.
- **Corpo default em Protocol.** `Renderer.qa_inputs` (`ports.py:108`) tem corpo com docstring.
  Não impediu o `isinstance` (vira membro comum), então não houve nada a "não forçar" aqui:
  todos os membros dos quatro Protocols são checáveis.
- **Painel ↔ roteamento econômico.** O catálogo é checado quanto à *existência* do registro;
  o `validated`/`reason`/`CostEstimate` do painel não são reexecutados (o `ProviderImplementation`
  já os valida em `domain/provider.py:134-152`, coberto no nível do domínio).

## Checklist do guia `docs/21-extensao.md`

**Parte A — provider novo numa porta existente: 7 passos.** Arquivos citados com linha real:
`adapters/<nome>.py` (implementa a porta — `ports.py:88/95/103/109`);
`composition.py:289-306` (`register(...)`); `composition.py:182-213`
(`ProviderImplementation` no catálogo, com regras de `validated`/`reason` em
`domain/provider.py:121-152` e `CostEstimate` em `domain/provider.py:67-118`);
`composition.py:230-271` (credencial via `Settings`/`Settings.from_env`);
`composition.py:216-227` (sonda opcional); `EXPECTED_CATALOG` em
`tests/test_port_contracts.py`; e o próprio guia.

**Parte B — porta nova: 10 passos.** `ports.py` (Protocol + tipos de resultado,
`ports.py:88-114`); `application/config.py:6-12`/`:28` (`KINDS`/`_DEFAULTS`/`resolve`);
consumidor no núcleo por `Callable[[str], Porta]` (padrão `voice_for`/
`renderer_for` em `application/render.py:100`); `register` + fiação em `Studio._wire`
(`composition.py:436-438`); catálogo (`composition.py:182-213`); `PORTS` e
`EXPECTED_CATALOG` no teste; fronteira (`tests/test_architecture.py`); doc + `README.md`.

**Regra das fronteiras:** documentada com as três listas por linha —
`IO` (`tests/test_architecture.py:5`), `MEDIA` (`:9`), `PROVIDER_SDKS` (`:10`) e
`CORE_FORBIDDEN` (`:11`), mais a tabela de portas (membros e linha).

**Exemplo concreto (não implementado): voz de nuvem `elevenlabs`.** Adaptador em
`adapters/voice_elevenlabs.py` honrando `self.model` (a identidade que entra no fingerprint da
narração, `application/render.py:28`/`:163`); `import elevenlabs` só em `adapters/`;
`register` junto de `composition.py:295`; `validated=bool(key)`/`reason`; `CostEstimate`
honesto; núcleo inalterado (`application/render.py:100,177,193`).

## Verificação executada

- `docker run --rm ... faceless-v2-hygiene-test-local:latest python -m pytest -q -p
  no:cacheprovider --tb=short tests/test_port_contracts.py tests/test_architecture.py
  tests/test_composition.py` → **18 passed, 2 skipped**. Os 2 skips são testes de banco de
  `test_composition.py` (`dsn`/`conn`) sem `STUDIO_TEST_DSN`.
- `python3 scripts/secret_hygiene.py scan` → **Secret hygiene check passed** (exit 0).

**Limitações declaradas:**
- **Não** rodei a suíte completa (memória/VM apertada com 2 fatias em paralelo) nem em
  partições.
- **Não** subi container de Postgres; meus testes não usam banco. Para executar o pytest usei a
  **imagem de teste já existente** `faceless-v2-hygiene-test-local:latest` em execução one-shot
  (`--rm`, sem serviço) — é o único runtime com as dependências do renderer
  (`numpy`/`PIL`/`piper`). Não havia venv local com as deps.
- Sem push/merge; sem `git add -A`.

## Fatos vs. hipóteses

- *Fato (medido):* `_REGISTRY` e catálogo já coincidiam em `d4ec5e6`; o teste trava isso e a
  baseline.
- *Fato (código):* `b067d4a` é o fix histórico do `PiperVoice` (`self.model` decorativo). O
  invariante catálogo↔registro **não** teria pego esse caso específico (registro e catálogo
  existiam); ele pega a forma estrutural da classe "painel mentindo". A forma semântica
  (`model` ignorado) passou a ser coberta pela asserção de identidade `voice_id` no fluxo real
  (invariante 5) — reportado assim, sem inflar o alcance do teste de drift.
