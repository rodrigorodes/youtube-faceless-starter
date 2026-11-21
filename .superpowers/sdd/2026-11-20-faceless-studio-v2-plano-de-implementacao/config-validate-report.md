# config-validate — PUT /studio/projects/{id}/config não aceita mais config que mente

Worktree isolada: `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/config-validate`
Branch `feat/config-validate`, base `f57dae2`. Sem tocar em `api/preview.py`/`api/panel.py`
(fatia `preview-shell`).

## Commits

- `7b17525` `fix(studio): PUT /projects/{id}/config recusa provedor inexistente cedo`

## Defeito e correção

Repro (base): `PUT /studio/projects/{pid}/config` com `{"text":"nope","image":"x","voice":"y","renderer":"z"}`
→ `200` e persistia. `parse_spec("nope")` passa (`name="nope", model=""`) e nada checava se o
provedor existe: o projeto só quebrava no render, em `provider_for` (`composition.py`), com
`ProviderNotFound`. Além disso a mensagem de 422 prometia `'<provider>:<model>'` — formato que o
código nunca exigiu (`demo`, `demo:` e `piper` são válidos).

Correção, em 3 camadas (todas em `domain`/`application`, puras):

1. `ProjectConfig` continua exigindo as 4 portas (`extra="forbid"`).
2. `parse_spec` exige spec `<provedor>[:<modelo>]` não vazio — e **não ecoa mais** o spec cru.
3. `SetPublicProjectConfig` recebe o catálogo (`implementations`) do `composition` e recusa cedo
   um nome de provedor que não existe no registro.

## A regra final (o que é aceito/recusado e por quê)

- Aceito: as 4 portas `text`/`image`/`voice`/`renderer` presentes, cada valor string não vazia no
  formato `<provedor>` ou `<provedor>:<modelo>` (modelo **opcional**), com o **nome do provedor
  registrado no catálogo daquela porta**.
- Recusado (422):
  - chave desconhecida → só o **nome** da chave na mensagem;
  - porta faltando → mensagem lista as portas ausentes;
  - valor não-string ou vazio → só a mensagem genérica;
  - `:x` (nome vazio) → `"invalid provider spec: provider name is required"`;
  - provedor **não registrado** → `"unknown <porta> provider; registered providers are: ..."`
    (diz a porta e os provedores reais; **não** repete o valor ofensor).
- **Provedor registrado porém não validado (`validated=False`, ex.: `veo`) é ACEITO.** Decisão
  deliberada: (a) o catálogo (`GET .../providers`, `card_for`) já expõe `UNAVAILABLE` com o
  **motivo real** (`"provedor experimental, sem homologação"`), então a UI não mente; (b) recusar
  travaria configs legítimos quando uma credencial está ausente — `opencode` fica `validated=False`
  sem `OPENCODE_BRIDGE_TOKEN` — e impediria preparar a config antes de provisionar o segredo;
  (c) o mínimo seguro é "existe no registro": um provedor inexistente nunca funciona, um não
  validado pode. O `GET`/`GET providers` mostra o porquê.

Fonte de verdade escolhida: o catálogo `ProviderImplementation` (`_provider_implementations`,
`composition.py`) passado por parâmetro ao caso de uso. `application` não importa `adapters` nem
`composition` (fiação no `composition.py:514`); `tests/test_architecture.py` continua verde.
`registered_names()` é puro (domain), na ordem do catálogo e sem duplicatas.

## Como provei que o valor ofensor não vaza

Teste HTTP com Postgres real em container isolado (mesmo código, `uvicorn app.main:app`):

```
PUT {"text":"nope",...}            -> 422 {"detail":"unknown text provider; registered providers are: opencode, demo"}
PUT {... "text":123}               -> 422 "...specs like '<provider>' or '<provider>:<model>'"
PUT {... "OPENAI_API_KEY":"sk-..."}-> 422 {"detail":"unknown config keys: ['OPENAI_API_KEY']"}
PUT {... "text":":x-do-not-echo"}  -> 422 "invalid provider spec: provider name is required"
GET  depois dos recusos           -> {"config":{}}  (nada persistiu)
```

Nenhuma resposta contém `nope`, `123`, `LEAK`, `x-do-not-echo` nem o valor da chave desconhecida.
Coberto por teste: `test_provider_catalog.py::test_parse_spec_keeps_optional_model_and_never_echoes_the_raw_value`,
`tests/test_channel_api.py` (estendido) e `tests/test_project_config_validation.py`.

## Testes

Focados, no container Python 3.12 (`faceless-v2-hygiene-test-local`, traz pytest/psycopg/httpx) com
Postgres descartável isolado (`cfgval-pg`) e prova de DSN:

```
tests/test_channel_api.py tests/test_composition.py tests/test_db.py
tests/test_architecture.py tests/test_contracts_snapshot.py tests/test_provider_catalog.py
tests/test_provider_service.py tests/test_port_contracts.py tests/test_project_config_validation.py
=> 82 passed
```

Cobertura do pedido: (a) `nope` → 422; (b) registrado válido → 200; (c) 422 sem o valor ofensor;
(d) config ausente → 422 listando as portas; (e) `GET` após `PUT` válido devolve o salvo; (extra)
`veo` aceito e catálogo com o motivo.

Contagem antes/depois (coleta dos arquivos tocados):
`test_channel_api.py + test_provider_catalog.py` = **30** → **36** (+1 no PUT estendido, +2 puros
em `test_provider_catalog.py`, +3 no novo `test_project_config_validation.py`).

## Limitações / notas

- O stack de pé em `localhost:8000` roda a imagem de `main` (código **velho**: sem a correção).
  Não fiz o PUT inválido contra ele de propósito — persistiria a config quebrada do projeto de
  smoke. Em vez disso subi um container descartável com o **nosso** código + Postgres isolado para
  a prova HTTP real acima, e removi tudo depois. O projeto de smoke
  `c43f4b52718b41348c924fcb52d493c3` **permanece válido** (os 4 defaults documentados) e nenhum
  outro projeto foi tocado.
- Suíte completa não rodada (VM apertada com fatias paralelas — declarei o foco).
- `scripts/check-secrets.sh` (higiene `scan`) passa com os arquivos adicionados.
- No host (Python 3.11.9) `test_architecture.py` e `test_contracts_snapshot.py` falham por
  versão (f-string com backslash exige ≥3.12; JSON schema `0.0` vs `0`). Confirmei que já falham
  na base `f57dae2` e que **passam** na imagem 3.12 do projeto — não são regressão desta fatia.
