# VE-01 — Contrato e compilador de overlay (especificação executável)

**Status:** pronta para implementar. **Não iniciada**: depende de autorização do operador.
**Base:** [PLAN.md](PLAN.md) (D1–D7) e [evidence/ve-00-closure.md](evidence/ve-00-closure.md) (baseline).
**Comando de validação (único):** `scripts/test-container.sh <testes>`; o host não é ambiente de teste (D7).

## 1. Escopo

**Entrega:** um plano pode declarar, por cena, **uma base + um overlay de imagem** com janela temporal. O contrato valida, o builder gera o plano, o compilador descreve o overlay de forma determinística e o cache o enxerga.

**Fora do escopo (não antecipar):**

| Item | Fase |
|---|---|
| Desenhar o overlay no vídeo (filter graph, entradas FFmpeg) | VE-02 |
| Overlay de vídeo ou de texto; sondagem de vídeo por ffprobe | VE-02 |
| Posição/tamanho do overlay (só tela cheia com `fit`) | não planejado |
| Providers de mídia, candidatos, licença verificada | VE-03 |
| Consumir `Shot.transition`; presets; tipografia | VE-04 |
| QA visual do overlay | VE-05 |
| UI | VE-06 |
| Qualquer produtor de `layers` em produção (`application/render.py:338` continua sem passar `layers`) | VE-03+ |

**Invariante de segurança de fase:** o executor FFmpeg **recusa** plano compilado com overlay enquanto a VE-02 não existir. Sem isso o vídeo sairia sem o overlay e sem erro (o "vídeo errado" que o compilador já evita hoje, `render_compiler.py:332`).

## 2. Decisões herdadas, aplicadas

| Decisão | Efeito na VE-01 |
|---|---|
| D1 | `Shot` ganha `role` e `z_index`. Não há tipo `Layer` no domínio. |
| D2 | Campos aditivos com default: planos sem overlay continuam válidos. Não há bump de `SCHEMA_VERSION` (nenhuma mudança incompatível é necessária). O snapshot `contracts/v1/renderplan.schema.json` é regenerado. |
| D3 | O overlay vive **dentro** de um segmento base; `concat -c copy` continua com um segmento por shot **base**. |
| D4 | Digest pode mudar (campo `overlays` entra no digest). Exige-se determinismo na mesma versão e paridade audiovisual sem overlay (golden). |
| D5 | `RenderSpec.layers` (default `()`). `_build_plan` repassa ao `build_render_plan`. |
| D6 | Sem flag. |

## 3. Contratos

### 3.1 Entrada: `RenderSpec.layers`

Tipo novo e mínimo em `application/ports.py` (junto de `RenderSpec`); é DTO de entrada, **não** um modelo de domínio:

```python
@dataclass(frozen=True)
class OverlayLayer:
    scene_id: str          # RenderSpec.scenes[i].id
    asset_id: str          # id do asset do overlay (imagem)
    image: Path            # arquivo PNG/JPEG do overlay
    license: str           # obrigatória, não vazia (como ImageResult.license)
    start_s: float         # início RELATIVO à cena, em segundos (>= 0)
    duration_s: float      # > 0
    z_index: int = 1       # >= 1
    fit: Literal["cover", "contain"] = "contain"
```

`RenderSpec.layers: tuple[OverlayLayer, ...] = ()`. Entrada para o builder (sem caminho de arquivo), em `domain/render_plan_builder.py`, ao lado de `StoryboardScene`:

```python
@dataclass(frozen=True)
class StoryboardOverlay:
    scene_id: str; asset_id: str; start_s: float; duration_s: float
    z_index: int = 1; fit: Literal["cover", "contain"] = "contain"
```

`build_render_plan(..., overlays: Sequence[StoryboardOverlay] = ())`.

### 3.2 Plano (domínio): `Shot`

| Campo | Tipo | Default | Regra |
|---|---|---|---|
| `role` | `Literal["base","overlay"]` | `"base"` | — |
| `z_index` | `int`, estrito, `>= 0` | `0` | `base` ⇒ `0`; `overlay` ⇒ `>= 1` |
| `transition` | já existe | `None` | `overlay` ⇒ **deve** ser `None` (a transição é do segmento base) |

### 3.3 Saída do compilador

```python
@dataclass(frozen=True)
class LayerExecution:        # em application/render_compiler.py
    shot_id: str
    asset_id: str
    media_type: str          # "image" | "graphic" na VE-01
    source: str              # descriptor.location or descriptor.uri
    z_index: int
    start_ticks: int         # RELATIVO ao início do segmento base hospedeiro
    duration_ticks: int
    fit: str
```

`ShotExecution.overlays: tuple[LayerExecution, ...] = ()`. Entra em `_shot_dict` (e, portanto, no digest). **Não** gera filtro nem argumento FFmpeg (VE-02).

### 3.4 Identidade e ordenação

- `shot_id` do overlay gerado pelo builder: `overlay:{scene_id}:{k}`, com `k` = posição após ordenar a entrada por `(z_index, start_s, asset_id)`.
- Track do overlay: `visual-overlay` (`kind="visual"`), declarada **somente** se houver overlay; sem overlay a lista de tracks é idêntica à de hoje.
- Ordem dos overlays em `ShotExecution.overlays` e no fingerprint: `(z_index, start_tick, shot_id)`.
- Segmentos base: ordem atual `(start_tick, scene_id, shot_id)`, só com `role="base"`.

## 4. Invariantes e onde são impostas

| # | Invariante | Camada | Erro | Observação |
|---|---|---|---|---|
| I1 | `base` tem `z_index == 0`; `overlay` tem `z_index >= 1` | `Shot` (validador) | `ValidationError` | — |
| I2 | `overlay` não tem `transition` | `Shot` (validador) | `ValidationError` | — |
| I3 | A cobertura contínua da cena é feita **só por shots `base`**; overlay nunca fecha lacuna | `Timeline._every_scene_is_fully_covered` | `ValidationError` ("gap…"/"not fully covered") | altera o validador existente: filtra `role == "base"` |
| I4 | Overlay dentro da cena | `Scene._shots_fit_inside_scene` | `ValidationError` | já existe; só ganha teste |
| I5 | Overlay não ocupa a track de um shot base | `Timeline._shots_live_on_declared_visual_tracks` | `ValidationError` ("overlap on track") | **já garantido**: a base cobre a cena inteira, logo um overlay na mesma track a sobreporia. Sem código novo; só teste |
| I6 | Dois overlays da mesma cena que se sobrepõem no tempo têm `z_index` distintos | `Timeline` (validador novo) | `ValidationError` | — |
| I7 | `asset_ref` do overlay existe no manifesto | `RenderPlan._references_and_output` | `ValidationError` | já existe; só ganha teste |
| I8 | Trajetória base contínua, sem lacuna e sem sobreposição, cobrindo `0..total_ticks` | compilador (`_require_base_trajectory`) | `CompileError` | substitui `_require_single_layer`, agora só sobre `base`. Sobreposição de dois `base` mantém a mensagem com `layer`/`overlap`/`track` |
| I9 | Overlay cabe inteiro em **um** segmento base (não atravessa fronteira de base) | compilador | `CompileError` | evita dividir um overlay entre segmentos (D3) |
| I10 | No máximo **1** overlay por cena (`MAX_OVERLAYS_PER_SCENE = 1`) | compilador | `CompileError` | o domínio aceita N; o limite é de fase, sobe na VE-02 se medido |
| I11 | Mídia do overlay é `image`/`graphic` | compilador | `CompileError` | `video` e `text` entram na VE-02/VE-04 |
| I12 | Asset do overlay resolvido, disponível e com hash/tipo iguais ao manifesto | compilador (`_check_descriptor`) | `CompileError` | mesma checagem da base |
| I13 | Cena sem overlay compila **igual** ao de hoje, salvo o campo `overlays: []` | compilador | — | provado pelo golden (paridade) e por teste de unidade |
| I14 | Plano compilado com overlay não é renderizado | `PlanFfmpegRenderer.execute` | `RuntimeError` com mensagem citando VE-02 | falha fechada; nada é escrito |
| I15 | Janela do overlay no builder: `start_s >= 0`, `duration_s > 0`, dentro da cena, cena e asset existentes | builder | `PlanBuildError` | — |
| I16 | Camada com `license` vazia é recusada | `_build_plan` | `RuntimeError` (padrão do arquivo) | — |
| I17 | O compilador continua puro | `tests/test_architecture.py` | — | sem `PIL`, `subprocess`, SDK |

## 5. Cache (`domain/render_cache.py`)

| Mudança | Motivo |
|---|---|
| `plan_graph` cria nó `visual:<shot_id>` **só para shots `base`** | sem isso nasceria um nó sem segmento físico (`render_plan_ffmpeg.py:381` mapeia nó → saída por `shot_id`) |
| O fingerprint do nó `visual` do base passa a incluir os overlays hospedados: `(asset_ref, content_sha256, media_type, z_index, início relativo ao base, duração, fit)` ordenados | adicionar, remover ou trocar um overlay deve invalidar só aquela cena |
| `_ordered_shots` (usado no fingerprint do `concat`) considera só `base` | o concat é de segmentos base |

## 6. Matriz de testes

Todos rodam no container. "U" = unidade sem ffmpeg; "G" = precisa de ffmpeg (golden).

| ID | Invariante | Arquivo | Caso | Tipo |
|---|---|---|---|---|
| T01 | I1 | `test_render_plan_timeline.py` | `base` com `z_index=1` recusado; `overlay` com `z_index=0` recusado | U |
| T02 | I2 | idem | overlay com `transition=Transition(kind="fade", duration_ticks=3)` recusado | U |
| T03 | I3 | idem | cena só com overlay (sem base) recusada; base com lacuna + overlay "tapando" a lacuna recusada | U |
| T04 | I4 | idem | overlay que termina depois da cena recusado | U |
| T05 | I5 | idem | overlay na mesma track do base recusado | U |
| T06 | I6 | idem | dois overlays sobrepostos com o mesmo `z_index` recusados; com `z_index` distintos aceitos; não sobrepostos com o mesmo `z_index` aceitos | U |
| T07 | I7 | `test_render_plan.py` | `asset_ref` do overlay fora do manifesto recusado | U |
| T08 | compat | `test_render_plan.py`, `test_render_plan_repo.py` | JSON de plano sem `role`/`z_index` carrega com `base`/`0`; round-trip JSON → modelo → JSON do plano com overlay é estável | U (+ banco) |
| T09 | I8 | `test_render_compiler.py` | **o teste existente `test_compiler_refuses_layered_visual_tracks_instead_of_producing_a_wrong_video` continua verde sem edição** (dois `base` sobrepostos). Falha de lacuna na base continua recusada | U |
| T10 | I9 | idem | overlay que atravessa a fronteira de dois shots base recusado | U |
| T11 | I10 | idem | dois overlays na mesma cena recusados | U |
| T12 | I11 | idem | overlay `video` e `text` recusados com mensagem citando a fase | U |
| T13 | I12 | idem | overlay sem descriptor, indisponível ou com hash diferente recusado | U |
| T14 | núcleo | idem | base + 1 overlay: `shots` tem **1** entrada (só base), `overlays` tem 1 com janela relativa correta, e o `concat.manifest` lista só o segmento base | U |
| T15 | determinismo | idem | compilar 2× o mesmo plano ⇒ mesmo `digest()`; embaralhar a ordem dos `shots` do plano de entrada ⇒ mesmo digest | U |
| T16 | I13 | idem | plano sem overlay: `overlays == ()` e `filter_complex`/`args` iguais aos de uma cópia do plano com `role` default | U |
| T17 | builder | `test_render_plan_builder.py` | 1 base + 1 overlay: shot `overlay:<cena>:0`, track `visual-overlay`, `z_index` e `Composition(fit)`; sem overlay o plano é **igual** ao atual (tracks e shots idênticos) | U |
| T18 | I15 | idem | cena inexistente, asset fora do manifesto, `start_s<0`, `duration_s<=0`, overlay fora da cena ⇒ `PlanBuildError` | U |
| T19 | cache | `test_render_cache.py` | sem nó `visual` para overlay; fingerprint do base muda ao adicionar, remover, trocar asset, mudar janela ou `z_index` do overlay; não muda ao reordenar a entrada | U |
| T20 | cache | `test_render_reuse.py` / `test_render_regeneration.py` | adicionar overlay a uma cena invalida **só** o nó dela e `concat`/`final`; as outras cenas continuam reusáveis | U |
| T21 | I14 | `test_render_plan_executor.py` | `execute` com `CompiledRender` que tem overlay levanta `RuntimeError` (VE-02) e **não escreve** nada em `final_output` | U |
| T22 | D5/I16 | `test_render_adapters.py` | `_build_plan` com `RenderSpec.layers`: manifesto inclui o asset do overlay (hash do arquivo, `media_type="image"`); layer sem `license` recusada; `layers=()` ⇒ plano igual ao atual | U |
| T23 | assets | `test_asset_resolver.py` | overlay `contain` com asset menor que a saída resolve; `cover` menor recusa (`check_fit` já cobre; só teste) | U |
| T24 | QA | `test_quality.py` | asset usado só como overlay **não** aparece em `plan-orphan-assets` | U |
| T25 | I17 | `test_architecture.py` | continua verde | U |
| T26 | contrato | `test_contracts_snapshot.py` | `contracts/v1/renderplan.schema.json` regenerado contém `role` e `z_index` | U |
| T27 | paridade | `test_render_golden.py` | os 3 casos continuam dentro do envelope (D4) e determinísticos | G |
| T28 | regressão | suíte completa | só as falhas já classificadas em `ve-00-closure.md`; **nenhuma nova** | G |

## 7. Atividades (ordem de execução, cada uma verificável)

Regra de processo: um teste falhando escrito antes do código (`test-driven-development`); sem commit; só arquivos listados.

| # | Atividade | Arquivos | Verificação (comando) | Aceite |
|---|---|---|---|---|
| A0 | **Regenerar o snapshot defasado**, num passo separado, antes de mexer no contrato: `python scripts/export_contracts.py` dentro do container, copiando só `contracts/v1/renderplan.schema.json`. O diff esperado é **só `ConfigSnapshot`** (drift de ea5782f, ver closure §4) | `contracts/v1/renderplan.schema.json` | `scripts/test-container.sh tests/test_contracts_snapshot.py tests/test_secrets_hygiene.py` | 0 falhas; diff contém só `ConfigSnapshot` |
| A1 | Escrever T01–T08 (falham) | `tests/test_render_plan_timeline.py`, `tests/test_render_plan.py` | rodar: falham pelo motivo certo | falham por falta de `role`/`z_index` |
| A2 | `Shot.role`, `Shot.z_index`, validador I1/I2; `Timeline._every_scene_is_fully_covered` só base (I3); validador I6; propriedades `Scene.base_shots`/`Scene.overlay_shots` e helper de hospedagem (base que contém o overlay) em `domain/render_plan.py` | `domain/render_plan.py` | T01–T08 + `tests/test_render_plan*.py` | verdes; planos antigos carregam |
| A3 | Escrever T09–T16 | `tests/test_render_compiler.py` | falham | — |
| A4 | `LayerExecution`, `ShotExecution.overlays`, `_require_base_trajectory`, I9–I12, `MAX_OVERLAYS_PER_SCENE`, `_shot_dict` com `overlays`; índice dos arquivos `scene_NNN` só entre bases | `application/render_compiler.py` | `tests/test_render_compiler.py` | T09–T16 verdes; T09 sem edição |
| A5 | Escrever T17–T18; `StoryboardOverlay`, `overlays=` no builder, track `visual-overlay` condicional, I15 | `tests/test_render_plan_builder.py`, `domain/render_plan_builder.py` | idem | verdes; plano sem overlay idêntico |
| A6 | Escrever T19–T20; nó `visual` só base, overlays no fingerprint, `_ordered_shots` só base | `tests/test_render_cache.py`, `tests/test_render_reuse.py`, `tests/test_render_regeneration.py`, `domain/render_cache.py` | idem | verdes |
| A7 | Escrever T21–T22; `OverlayLayer`, `RenderSpec.layers`, `_build_plan`/`_descriptors` com `layers`, recusa no início de `execute`, antes do atalho de reuse do MP4 final (I14, I16) | `application/ports.py`, `adapters/render_plan_ffmpeg.py`, testes | idem | verdes |
| A8 | T23–T24 (só teste, sem código; se algum falhar, é achado novo: parar e registrar) | `tests/test_asset_resolver.py`, `tests/test_quality.py` | idem | verdes sem alterar produção |
| A9 | Regenerar o snapshot do contrato novo (T26) | `contracts/v1/renderplan.schema.json` | `tests/test_contracts_snapshot.py` | verde; diff contém só `role`/`z_index` |
| A10 | Gate: `tests/test_architecture.py`, `tests/test_render_golden.py` (T27) e **suíte completa** (T28) | — | `scripts/test-container.sh tests -q -rfEs` | sem falha nova; golden dentro do envelope |
| A11 | Evidência: `evidence/ve-01-closure.md` (comandos, contagens antes/depois, diff dos arquivos), `PLAN.md` atualizado | `docs/backlogs/faceless-visual-evolution/` | — | tudo rastreável |

Se uma atividade exigir arquivo fora da lista (por exemplo `render_plan_ffmpeg.py` além de A7), parar e registrar como achado: não ampliar o escopo.

## 8. Critérios de aceite da fase (objetivos)

1. T01–T28 passam no container (`scripts/test-container.sh`), com a suíte completa sem falha nova em relação ao baseline.
2. Base + 1 overlay compila: `len(compiled.shots) == nº de bases`, `overlays` preenchido, 2 compilações ⇒ mesmo digest.
3. Plano sem overlay: golden dentro do envelope e `overlays == ()`.
4. Cada intervalo inválido (T03, T04, T10, T18) é recusado **antes** de qualquer chamada ao FFmpeg.
5. `PlanFfmpegRenderer.execute` recusa overlay (T21): nenhum vídeo sem overlay é produzido silenciosamente.
6. Diff restrito aos arquivos do §7; nenhum provider, dependência ou variável de ambiente novos (`git diff --stat` e `requirements*.txt` sem mudança).

## 9. Riscos da VE-01

| Risco | Mitigação |
|---|---|
| Nó de cache para overlay sem segmento | T19/T20; §5 |
| Overlay mudar a numeração dos arquivos `scene_NNN` dos bases | A4 indexa só entre bases; T14 |
| Quem preenche `layers` no futuro passar janela fora de quadro | VE-02 decide arredondamento (`enable` em segundos); VE-01 só exige `ticks` válidos e dentro da cena |
| `test_render_compiler.py` ter outros testes que fixam "uma camada" | A3 roda o arquivo inteiro antes; qualquer outro teste a mudar é registrado, não afrouxado |
| Snapshot de contrato com drift anterior misturar-se ao diff novo | A0 separa os dois |
