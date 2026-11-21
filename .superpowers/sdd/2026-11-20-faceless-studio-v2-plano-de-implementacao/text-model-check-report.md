# text-model-check — `OpenCodeText` deixa de mentir: o `model` do spec é conferido no bridge

Fecha a **assimetria dentro da família `opencode`**: o `OpenCodeImage` já conferia o modelo que o
bridge declara; o `OpenCodeText` aceitava qualquer coisa e rotulava o ledger com o modelo do spec.
Mesmo padrão "config que mente" do `PiperVoice` (spec ignorado) e do `PUT /config` (provedor
inexistente aceito) — aqui é o `bridge` que escolhe o modelo real e o spec só apontava.

- Worktree: `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/text-model-check`
- Branch `feat/text-model-check`, base `main` = `0c04ad3`
  (`docs(status): analise com o app real — upgrade 0013..0032, E2E aprovado e 6 bugs achados rodando`)
- Sem `git add -A`; sem push/merge; bridge **não** foi reiniciado; `api/preview.py`/`api/panel.py`/
  `rich.py`/`voice_piper.py`/`.env.example`/`docker-compose.yml`/`docs/04` **não** tocados.

## Commit

| # | Assunto | Arquivos |
|---|---------|----------|
| `18ba578` | `fix(studio): OpenCodeText confere o modelo de texto declarado no bridge` | `renderer/app/studio/adapters/text_opencode.py`, `tests/test_text_adapters.py` |

`2 files changed, 89 insertions(+), 3 deletions(-)`.

## Defeito medido (antes)

`OpenCodeText.complete` fazia **só** `POST /generate` e devolvia
`UsageEntry(model=self.model)` — o `model` vindo do spec (`STUDIO_TEXT=opencode:<modelo>`). Quem
escolhe o modelo de verdade é o bridge, por `OPENCODE_MODEL`. Nada comparava os dois. Reprodução
sob `MockTransport` (bridge declara `openai/gpt-6-luna`; spec diz `openai/outro-modelo`):

```
HEAD (antes)  -> SUCESSO SILENCIOSO; ledger.model = openai/outro-modelo | texto = "roteiro gerado pelo modelo REAL"
novo (depois) -> PreEffectFailure: bridge text model (openai/gpt-6-luna) differs from the configured openai/outro-modelo; ...
```

Antes: roda no modelo real do bridge e **rotula o spec** — ledger/analytics errados, sem aviso.

## Via escolhida: conferir o **`/health`** (não mexer no `/generate`)

Havia duas vias; escolhi **validar contra o `/health`** e **não** adicionar `model` ao corpo do
`/generate`. Motivos:

1. **O campo já existe**: o `/health` do bridge declara `{"status":"ok","model":<ref>,"image_model":<img>}`
   desde o **primeiro commit** do bridge (`ecf4400 feat: provider opencode (OpenAI Luna via OAuth)…`).
   Verifiquei no git (`git log -S '"status": "ok", "model"' -- scripts/opencode-bridge.py` → `ecf4400`)
   e no bridge **em execução** do host:
   `curl http://127.0.0.1:8787/health` →
   `{"status":"ok","model":"openai/gpt-6-luna","image_model":"openrouter/recraft/recraft-v4.1-flash-v2:free"}`.
   Logo, **não há cliente antigo a quebrar** e não é preciso mexer no bridge nem reiniciá-lo.
2. **Consistência máxima**: o texto passa a usar **exatamente o mesmo mecanismo** do `OpenCodeImage`
   (`_check_bridge(client)` → compara o campo declarado com `self.model`), não só a mesma decisão.
3. **Efeito imediato**: a correção vale **agora**, contra o bridge que já está rodando. Pela via do
   `/generate`, o bridge só mudaria de comportamento depois de reiniciado (proibido nesta tarefa) —
   a falha silenciosa seguiria aberta até lá.
4. Sem mudança de contrato de rede, sem tocar `scripts/opencode-bridge.py` nem `tests/test_bridge.py`.

Escolhi **uma** via e documentei — não fiz as duas. `scripts/opencode-bridge.py` **não foi alterado**
(o `/generate` segue devolvendo só `{"text": ...}`, linha 125).

### Estrutura nova (`_check_bridge`, espelhando `image_opencode.py`)

- `GET /health` → `declared = response.json().get("model")`.
- `declared != self.model` → **`PreEffectFailure`** nomeando os dois modelos, **antes** do
  `POST /generate` (nenhum efeito externo aconteceu). Mesma exceção do `OpenCodeImage`
  (`PreEffectFailure` é subclasse de `ModelUnavailable` — `application/budget.py:100`).
- `_verified` por instância (como no `OpenCodeImage`) evita reconsultar o `/health` em chamadas
  repetidas do mesmo adaptador.
- Conexão nunca estabelecida / resposta ilegível: não verifica agora e **deixa a geração decidir o
  erro** (o `POST` falha e vira `PreEffectFailure`/`ModelUnavailable` como antes) — preserva o
  comportamento dos testes de alerta do P06 e não emite aviso falso de "não declarado".

## Comportamento com bridge antigo (sem o campo)

Se o `/health` responder **200 sem `model`** (bridge antigo), o adaptador **aceita** a chamada para
não quebrar o rollout, mas **nunca em silêncio**: emite
`logging.getLogger("studio.alerts").warning('{"event":"bridge_text_model_undeclared"}')`
— mesmo canal/estilo do `bridge_unreachable` do `BridgeAlerts`. O evento **não** ecoa modelo nem
prompt (testado). Divergência **declarada** jamais passa; ausência de declaração passa com aviso.

*Nota de consistência (deliberada e declarada):* o `OpenCodeImage` **recusa** um `/health` sem
`image_model`. No texto eu **aceito com aviso** o campo ausente, porque (a) a tarefa pede
explicitamente "não quebre" com bridge antigo e (b) manter o aviso garante que a ausência de
verificação não é silenciosa. A regra que importa — "declarado e diferente ⇒ `PreEffectFailure`" —
é idêntica nos dois adapters.

## Segunda inconsistência do mesmo tipo — encontrada, **reportada e não corrigida**

`PiperVoice` (porta `voice`) + `PIPER_VOICE`. O `model` do spec de voz
(`STUDIO_VOICE=piper:<nome>` / `Project.config.voice`) é passado via `rich.use_voice(self.voice_path)`,
mas `renderer/app/rich.py:55` faz

```python
wanted = os.getenv("PIPER_VOICE") or _requested_voice or DEFAULT_VOICE
```

ou seja, **`PIPER_VOICE` (caminho explícito) sobrepõe a voz do spec**, enquanto
`application/render.py:55` grava no ledger `model=getattr(voice, "model", "")` = **modelo do spec**.
Com `PIPER_VOICE=/opt/voices/jeff.onnx` e `STUDIO_VOICE=piper:faber`, o ledger diz `faber` e quem
fala é `jeff` — a mesma classe ("config que mente"), sem verificação nem aviso. Não corrigi:
a precedência é intencional (override explícito do operador, da fatia `provider-config`) e a correção
exigiria tocar `renderer/app/rich.py`, **fora do escopo autorizado**. Fica reportado.

### Rótulos decorativos que **não** são a mesma classe (sem divergência real a conferir)

`PexelsImage` (`stock`), `PlaceholderImage`, `VeoImage`, `DemoText` e o `renderer` guardam o `model`
do spec apenas como rótulo do ledger; não há um "modelo real" alternativo escolhido por outro
componente para divergir. `PexelsImage` aceitaria um rótulo arbitrário (`stock:<qualquer>`), mas não
seleciona modelo algum — anotado por completude, fora do escopo.

## Testes

Suíte focada em `yfs-test:latest` (py3.12, pydantic **2.11.4** — casa com `renderer/requirements.txt`),
mount do worktree:

```
docker run --rm --memory=1g -v $PWD:/work -w /work yfs-test:latest \
  python3 -m pytest tests/test_text_adapters.py tests/test_alerts_p06.py tests/test_image_adapters.py \
     tests/test_architecture.py tests/test_provider_catalog.py tests/test_provider_service.py \
     tests/test_token_env_provider.py tests/test_composition.py tests/test_contracts_snapshot.py -q
```

| Foco pedido | Resultado |
|-------------|-----------|
| `test_text_adapters.py` | passa (inclui os 3 novos) |
| `test_providers*` (`test_provider_catalog.py`, `test_provider_service.py`, `test_token_env_provider.py`) | passa |
| `test_architecture.py` | passa (adapters/net continuam fora de `domain`/`application`) |
| `test_alerts_p06.py` | passa |
| `test_composition.py` | passa (2 skips = testes que exigem DB) |
| `test_contracts_snapshot.py` | passa na imagem |

**Antes/depois (mesmas 9 suítes):** antes **96 passed, 2 skipped** → depois **99 passed, 2 skipped**
(+3 testes). Não rodei a suíte completa em partições (VM apertada) — declarado.

Matriz exigida em `tests/test_text_adapters.py`:

| Caso | Teste | Esperado |
|------|-------|----------|
| (a) declarado **igual** | `test_opencode_accepts_a_bridge_that_declares_the_same_text_model` | passa; ledger com o modelo do spec; só `/generate` é chamado |
| (b) declarado **diferente** | `test_opencode_refuses_a_bridge_that_declares_another_text_model_before_generating` | **`PreEffectFailure`** (não `ModelUnavailable` genérico); cita os 2 modelos; `calls == []` (nada gerado) |
| (c) **sem o campo** | `test_opencode_accepts_a_bridge_without_the_declared_text_model_but_warns` | aceita, gera, emite `bridge_text_model_undeclared` sem vazar modelo |
| (d) **`OpenCodeImage` regressão** | `tests/test_image_adapters.py` (inalterado) | passa sem mudanças |

`test_alerts_p06.py` **não precisou mudar** (o `PreEffectFailure` já é `ModelUnavailable`; o
`observe(False)` continua acontecendo) — sinal de que a via espelha bem o `OpenCodeImage`.

### Prova real contra o bridge do host (somente leitura)

`OpenCodeText._check_bridge`/`complete` contra `http://127.0.0.1:8787` — **apenas `GET /health`**,
nenhum `/generate` disparado (a divergência para antes do POST):

```
spec == declarado  -> verified = True
spec != declarado  -> PreEffectFailure: bridge text model (openai/gpt-6-luna) differs from the configured openai/gpt-5-inexistente; ...
```

O bridge em execução **não foi morto nem reiniciado**; e como a via não altera
`scripts/opencode-bridge.py`, ele segue válido sem reinício.

## Higiene

- `python3 scripts/secret_hygiene.py scan` → **Secret hygiene check passed.**
- Nenhum teste/arquivo imprime segredo; o aviso de "não declarado" carrega só o evento.

## Evidência arquivada (verbatim, `git add -f`)

`.superpowers/sdd/2026-11-20-faceless-studio-v2-plano-de-implementacao/archive/`:

- `text-model-check-tests-host.txt` — `pytest` no host (1 falha ambiental por `numpy` ausente).
- `text-model-check-tests-docker.txt` — os 9 arquivos focados na imagem (99 passed, 2 skipped).
- `text-model-check-live-probe.txt` — probe no bridge real + antes/depois sob `MockTransport`.
- `text-model-check-secret-hygiene.txt`, `text-model-check.diff`, `text_opencode.py.before`.

## Contagem antes/depois

| Métrica | Antes | Depois |
|---------|-------|--------|
| Adapters da família `opencode` que **conferem** o modelo declarado | 1/2 (`image` sim, `text` não) | **2/2** |
| Superfícies "config que mente" abertas (conhecidas) | 2 (`OpenCodeText`; `PiperVoice`/`PIPER_VOICE`) | **1** (`PiperVoice` — reportada) |
| Suítes focadas (9 arquivos) | 96 passed, 2 skipped | 99 passed, 2 skipped |

## Limitações / não feito

- Não alterei `scripts/opencode-bridge.py` (via escolhida); o `/generate` continua `{"text": ...}`.
- Não usei a via do `/generate` (seria a outra alternativa) — escolhi uma só, documentado acima.
- `PiperVoice`/`PIPER_VOICE` reportado, não corrigido (tocaria `rich.py`, fora do escopo).
- Não rodei a suíte completa (VM apertada). No host, `test_alerts_p06::test_each_studio…` falha por
  `numpy` ausente e `test_contracts_snapshot` falha pelo drift de pydantic (`0.0` vs `0`) — ambos
  ambientais/pré-existentes (o último já documentado em `provider-config-report.md` §5) e verdes na imagem.
