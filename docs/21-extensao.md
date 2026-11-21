# Estender o stúdio: providers e portas

O estúdio é organizado em três camadas com fronteiras reais:

- **`domain/`** — regras puras (contratos, política, roteamento econômico). Não faz I/O.
- **`application/`** — casos de uso e as **portas** (`ports.py`). Fala com o mundo só por
  Protocol; nunca importa um adaptador.
- **`adapters/`** — implementações concretas (rede, disco, FFmpeg, SDK de provedor).

A composição (`composition.py`) é o **único** lugar que liga caso de uso ↔ adaptador. Trocar
ou acrescentar um provedor é editar um adaptador e uma linha de registro — não o núcleo.

## As fronteiras (o que o núcleo não pode importar)

Quem impõe isso por CI é `tests/test_architecture.py`. O núcleo (`domain/` e `application/`)
não pode importar:

| Lista | Conteúdo | Referência |
| --- | --- | --- |
| `IO` | `fastapi`, `psycopg`, `httpx`, `subprocess`, `requests`, `os`, `socket`, `urllib.request`, `http.client`, `sqlalchemy` | `tests/test_architecture.py:5` |
| `MEDIA` | `PIL`, `numpy`, `cv2`, `ffmpeg`, `moviepy`, `av` | `tests/test_architecture.py:9` |
| `PROVIDER_SDKS` | `openai`, `anthropic`, `elevenlabs`, `fal_client`, `boto3`, `google` | `tests/test_architecture.py:10` |

Essas três listas formam `CORE_FORBIDDEN` (`tests/test_architecture.py:11`) e são checadas
por `test_render_core_has_no_media_or_provider_sdks`. É o que sustenta o compilador puro do
Render Plan e permite um provedor de voz/imagem de nuvem **sem** contaminar o núcleo.

As portas que o núcleo usa para falar com os provedores são Protocols em
`renderer/app/studio/application/ports.py`:

| Porta | `kind` | Membros | Linha |
| --- | --- | --- | --- |
| `TextModel` | `text` | `name`, `cost_estimate`, `complete` | `ports.py:88` |
| `ImageModel` | `image` | `name`, `model`, `cost_estimate`, `generate` | `ports.py:95` |
| `Voice` | `voice` | `name`, `speak` | `ports.py:103` |
| `Renderer` | `renderer` | `name`, `render`, `qa_inputs` | `ports.py:109` |

Os quatro são `@runtime_checkable` (`ports.py:87,94,102,108`) só para que
`tests/test_port_contracts.py` possa checar `isinstance(impl, Porta)`. É aditivo e não muda
comportamento: `runtime_checkable` só relaxa o `isinstance`; sem ele, o Python recusa a checagem.

---

## Parte A — adicionar um provedor novo a uma porta existente

Use quando a porta já existe (ex.: uma nova `Voice`) e só falta uma implementação.

1. **Adaptador.** Crie `renderer/app/studio/adapters/<nome>.py` com uma classe que implemente
   a porta (tabela acima). Ex.: para voz, defina `name` e
   `speak(self, text: str, out_path: Path) -> float` (`ports.py:103`). O `name` **precisa**
   bater com o nome que você vai registrar e anunciar.
2. **Registro.** Em `composition.py`, dentro de `Studio.__init__`, acrescente
   `register("<kind>", "<nome>", <factory>)` junto dos outros (`composition.py:289-306`).
   A `factory` recebe o `model` (a parte depois dos dois-pontos da spec) e devolve a instância
   — é o mesmo `register` de `application/config.py:39`. Se o provedor depender de credencial,
   capture o valor de `Settings` na closure, como `stock` faz (`composition.py:293`).
3. **Catálogo.** Adicione uma `ProviderImplementation` em `_provider_implementations`
   (`composition.py:182-213`) com `capabilities`, `cost`, `quality`, `validated` e `reason`.
   Regras que o domínio cobra (`domain/provider.py:121-152`):
   - `validated=False` **exige** `reason` (senão `ProviderImplementation` levanta) — o painel
     mostra UNAVAILABLE com o motivo em vez de prometer o que não há.
   - `CostEstimate` é honesto: `CostEstimate.free(...)`, `CostEstimate.estimate(valor, note=...)`
     ou `CostEstimate.unknown(note=...)`. Ausência de preço **nunca** vira US$ 0,00
     (`domain/provider.py:67-118`).
4. **Credencial (se houver).** Leia a variável no `Settings`/`Settings.from_env`
   (`composition.py:230-271`). Não leia ambiente no núcleo: `Settings` é montado na composição
   e o valor chega ao adaptador pela closure do passo 2.
5. **Sonda (opcional).** Para o teste de conexão do painel, registre um probe em
   `_provider_probes` (`composition.py:216-227`) — `HttpReachableProbe` para HTTP,
   `LocalProviderProbe` para os locais.
6. **Baseline e guia.** Atualize `EXPECTED_CATALOG` em `tests/test_port_contracts.py` (o teste
   de drift falha de propósito quando o catálogo muda). Registre o provedor neste guia.
7. **Testes.** Rode `tests/test_port_contracts.py` — o provedor novo é incluído
   automaticamente (o teste itera o registro real). Some os testes de comportamento do
   adaptador (o contrato estrutural não checa assinatura nem semântica; veja o fim deste guia).

Nenhum passo toca `domain/` nem `application/`.

---

## Parte B — adicionar uma porta nova

Use quando um novo tipo de dependência externa precisa entrar (ex.: uma porta de "música" ou
de "analytics de canal"). Um provedor configurável a mais por projeto implica os dez passos.

1. **Contrato.** Declare o `Protocol` em `ports.py`, perto dos outros (`ports.py:88-114`).
   Adicione `@runtime_checkable` **somente** se você for checá-lo com `isinstance` no teste de
   contratos; a checagem estrutural exige o decorador.
2. **Tipos de resultado.** Se a porta devolve dados, defina dataclasses em `ports.py`
   (como `TextResult`/`ImageResult`/`RenderSpec`, `ports.py:32-59`) — o núcleo depende de tipos
   puros, não de estruturas do adaptador.
3. **Consumidor no núcleo.** Injete a porta por `Callable[[str], Porta]` num caso de uso de
   `application/` (o padrão do render é `voice_for`/`renderer_for` em
   `application/render.py:100`). O caso de uso chama só os membros da porta
   (ex.: `voice.speak`, `application/render.py:193`).
4. **`kind` de configuração (se for por projeto).** Acrescente o `kind` em `KINDS` e o default
   em `_DEFAULTS` (`application/config.py:6-12`). `ProjectConfig.resolve` cobre o resto
   (`application/config.py:28`).
5. **Implementações.** Escreva os adaptadores e registre cada um com
   `register("<kind>", "<nome>", ...)` (`composition.py:289-306`).
6. **Fiação.** Monte o consumidor em `Studio._wire` passando
   `lambda project_id: provider_for("<kind>", project_id)` (o render monta assim,
   `composition.py:436-438`).
7. **Catálogo.** Anuncie cada implementação em `_provider_implementations`
   (`composition.py:182-213`), como na Parte A.
8. **Contrato de teste.** Acrescente a porta ao mapa `PORTS` e o `kind` a `EXPECTED_CATALOG`
   em `tests/test_port_contracts.py`.
9. **Fronteira.** Confirme que `domain/`/`application/` continuam sem importar mídia nem SDK
   (`tests/test_architecture.py`). Se a dependência nova for de mídia ou SDK, ela pertence ao
   adaptador, nunca ao núcleo.
10. **Documentação.** Descreva a porta e seu `kind` neste guia e no índice do `README.md`.

---

## Exemplo concreto: voz de nuvem `elevenlabs` (não implementado)

Caso de uso da Parte A. O objetivo é permitir que um projeto escolha
`STUDIO_VOICE=elevenlabs:<voz>` no lugar de `piper:<voz>` — trocando só configuração.

- **Adaptador.** `renderer/app/studio/adapters/voice_elevenlabs.py`, classe
  `ElevenLabsVoice` com `name = "elevenlabs"` e `speak(...) -> float` (`ports.py:103`).
  A classe **deve honrar `self.model`**: é a identidade que o `RunRender` deriva em
  `_voice_identity` (`application/render.py:28`, `name:model`) e que entra no fingerprint da
  narração (`RP-06c`, `application/render.py:163`). Ignorar o modelo (o defeito que o
  `PiperVoice` tinha) faria o cache de narração reusar áudio da voz errada.
- **Import do SDK.** `import elevenlabs` **só** em `adapters/` — `elevenlabs` está em
  `PROVIDER_SDKS` (`tests/test_architecture.py:10`) e importá-lo no núcleo reprova o CI.
- **Registro.** `register("voice", "elevenlabs", lambda model: ElevenLabsVoice(model, settings.elevenlabs_key))`
  em `composition.py` (junto de `composition.py:295`).
- **Credencial.** `elevenlabs_key` em `Settings`/`Settings.from_env` (`composition.py:230-271`).
- **Catálogo.** `ProviderImplementation(ProviderKind.VOICE, "elevenlabs", capabilities=("voice.speak",),
  cost=CostEstimate.estimate(<taxa por caractere>, note="por caractere"), quality=5,
  validated=bool(settings.elevenlabs_key), reason=None if key else "ELEVENLABS_API_KEY ausente")`
  em `_provider_implementations` (`composition.py:209`).
- **Núcleo.** Zero mudanças: `RunRender` já consome a porta por `voice_for`
  (`application/render.py:100,177,193`).

---

## Limite honesto da checagem estrutural

`tests/test_port_contracts.py` prova duas coisas fortes e uma fraca:

- **Forte:** todo `register(...)` produz um objeto que **tem** os membros da porta
  (`isinstance` com `@runtime_checkable`) e o catálogo e o registro não divergem.
- **Fraca (por design do Python):** `@runtime_checkable` checa **presença** de membros, não
  assinatura nem semântica. Uma classe com `speak(self)` (aridade errada) passa no
  `isinstance` — é o que o teste `test_runtime_checkable_proves_member_presence_not_signatures`
  documenta. Por isso cada adaptador novo precisa também de testes de comportamento, e a
  prova de que o fluxo real usa a porta é `test_a_new_provider_enters_through_the_same_seams_without_touching_the_core`
  (que roda o `RunRender` de verdade contra um provider registrado em tempo de teste).
