# F5 — reconciliação do contrato VisualBeat e planejamento de beats por cena

Fatia B (domínio apenas). Base: `5b7eecf`; revisão corrigida sobre `cce36a4`.
Nenhum push/merge. Esta fatia **não** conclui F5: sem integração com renderer,
`Scene`, persistência, API/UI nem auditoria real de licença (F5-06/F5-07/F5-08
seguem pendentes).

## Escopo entregue

- `renderer/app/studio/domain/visual_beat.py`: contrato reconciliado; docstring
  canônica com a decisão/divergência; propriedade derivada `duration_s`.
- `renderer/app/studio/domain/beat_plan.py`: regra pura `plan_scene_beats` e o
  núcleo numérico `plan_beat_windows`, com `SceneBeatPlan`. Sem I/O.
- `tests/test_beat_plan.py`: 63 testes (TDD, RED antes de GREEN).
- `tests/test_visual_beat.py`: +1 teste da propriedade derivada (62 no total).
- Sem tocar em `render.py`, `panel.py`, `adapters/**`, `contracts.py`, `Scene`,
  `narration_duration.py`, `production.py` ou `test_production_budget.py`.

## 1. Reconciliação do contrato (decisão)

**Formato canônico:** `app.studio.domain.visual_beat.VisualBeat`, com os campos
do card F5-01 — `scene_id`, `start_s`, `end_s`, `asset_kind`, `reference`,
`transition`, `provenance`, `license` (versionado, imutável, `extra="forbid"`).
Nada disso mudou nesta rodada de correção.

Divergência com o esqueleto do plano (Task 6, ~linhas 397-406):

| Plano (rascunho) | Canônico | Tratamento |
|---|---|---|
| `from ...contracts import VisualBeat` | `domain.visual_beat` | O plano divergia do próprio card F5-01. Sem consumidor real (só `tests/test_visual_beat.py` importa `VisualBeat`). Um único módulo; sem duplicar em `contracts` (evita ciclo `contracts ↔ visual_beat`). |
| `duration` | `end_s - start_s` | Ponte aditiva `duration_s` (derivada, não persistida; verificado `"duration_s" not in model_dump()`). Sem renomear/quebrar campos. |
| `effect` (`zoom_in`…) | — | **Não** é `transition` (crossfade). Movimento de câmera é render (F5-06); sem campo especulativo. |
| `beat_id` | — | Não existe; identidade é (`scene_id`, ordem)/`reference`. Cache por beat é F5-07. |
| `Scene(scene_id=…, beats=[…])` | `Scene` usa `id`, `video_id`, `idx`, `narration`, `duration_s`; sem `beats` | Esqueleto erra a forma de `Scene`; integração/1:N fica para depois (restrição). `Scene` intocado. |

Sem renomeação de campo existente ⇒ sem migração. Testes existentes de
`tests/test_visual_beat.py` permanecem válidos (só ganharam 1 teste novo).

## 2. Planejamento de beats por cena (regra pura)

`plan_scene_beats(scene, beats, *, tolerance_s=1e-6) -> SceneBeatPlan`
(núcleo: `plan_beat_windows(scene_duration_s, beat_durations, *, tolerance_s)`).

- Cada beat de entrada traz a **duração desejada** (`end_s - start_s`); a
  posição é recalculada, contígua a partir de 0. Ordem estável; o último beat
  fecha a cena quando a soma não excede.
- `SceneBeatPlan(scene_id, duration_s, beats)` é `frozen`, com `coverage_s`.
- Retorna **novos** `VisualBeat` reconstruídos e **revalidados**
  (`VisualBeat.model_validate`), preservando os campos de mídia.

Validações que rejeitam com `ValueError`: cena sem duração finita positiva
(`None/0/neg/inf/nan/bool/str`); `beats`/`beat_durations` não iteráveis;
zero beats; beat de outra cena ou que não é `VisualBeat`; duração de beat não
finita/negativa/zero; **soma que excede a cena além do resíduo de ponto
flutuante**; soma que não cobre a cena além de `tolerance_s`; `tolerance_s`
inválido.

### Política de excedente (pós-revisão, achado 1)

`tolerance_s` admite apenas **sobra** (soma abaixo da cena), nunca overflow.
Beats que somam mais que a cena são **rejeitados**, exceto resíduo de soma em
ponto flutuante (poucos ulps da duração, `max(1e-9, ulp(duration)*8)`). As
janelas são cumulativas; o último beat só é fechado em `duration_s` se
`duration > last_start`, o que garante **por construção** `start < end` e
span > 0. Se `duration <= last_start` (overflow em resíduo), as janelas
cumulativas são mantidas sem encolher nenhum beat. Escolhi **rejeitar** o
excesso real porque um beat além da cena é inválido para o render; a folga
residual evita falsos negativos de `math.fsum`.

### Cobertura (pós-revisão, achado 2)

`coverage_s` é derivado das janelas contíguas: `beats[-1].end_s - beats[0].start_s`.
Quando a soma não excede a cena e o último beat fecha nela, é **bit-exato** igual
a `duration_s`; no resíduo raro de overflow, é a extensão cumulativa real
(≤ `duration_s` + resíduo). A afirmação anterior de exatidão universal era falsa
(divergência de ≤1 ulp entre `fsum` dos spans e a soma sequencial das posições)
e foi removida.

## 3. Proveniência e licença (limite explícito)

Mantida a exigência de `provenance`/`license` não vazias para mídia externa
(`stock`, `ai_image`, `ai_clip`, `diagram`, `screen_capture`), com
`text_animation` isenta. Explícito na docstring do contrato e aqui: **o contrato
NÃO verifica** veracidade da proveniência, validade real da licença, uso de
marca/pessoa nem recuperabilidade/existência do asset. Auditoria de direitos é
F5-08 e não foi implementada (não é verificável offline).

## 4. Correções da revisão independente

1. **CRÍTICO — `VisualBeat` inválido por tolerância.** Antes, forçar
   `windows[-1]` a terminar em `duration` sem checar o tempo restante produzia
   span 0 (`plan_beat_windows(5.0, [5.0, 1e-7])`) ou negativo
   (`[5.0000005, 1e-7]`). **Corrigido na raiz:** overflow real é rejeitado e o
   fechamento do último beat é condicionado a `duration > last_start`; nenhum
   span ≤ 0 ou `start >= end` é possível por construção. Removido `model_copy`;
   a reconstrução usa `VisualBeat.model_validate({**model_dump(), ...})` para
   **revalidar** (em pydantic v2, `model_copy` NÃO revalida).
2. **Cobertura não bit-exata.** `coverage_s` agora deriva das janelas contíguas;
   afirmação de exatidão universal corrigida (ver §2).
3. **Testes mortos por nome duplicado.** Renomeados para
   `test_windows_reject_beats_exceeding_scene` e
   `test_windows_reject_beats_not_covering_scene`; `--collect-only` confirma os
   4 nomes distintos (os do núcleo + os de cena).
4. **Lacunas de cobertura.** Adicionados testes de `tolerance_s`
   inf/-inf/nan/`None`/`True`/`"1"`/`-1` (núcleo e cena) e de beat que não é
   `VisualBeat`.
5. **Contrato de erro.** `beats`/`beat_durations` não iteráveis passam a ser
   `ValueError` (helper `_as_tuple`), não `TypeError`.
6. **Riscos não resolvidos** documentados em §6.

## 5. Evidências (comandos e resultados reais executados por mim)

Python 3.12 em `faceless-v2-hygiene-test-local:latest`, `--network none`,
workspace somente leitura.

- RED (funções ausentes): `… pytest -q -p no:cacheprovider tests/test_beat_plan.py`
  — `ModuleNotFoundError: app.studio.domain.beat_plan`; e
  `tests/test_visual_beat.py::test_duration_s_is_derived_from_the_interval`
  — `AttributeError: … 'duration_s'`.
- RED (correções da revisão, antes do fix): `… pytest -q -p no:cacheprovider
  tests/test_beat_plan.py` — **6 failed, 57 passed** (2 overflow, 1 span não
  positivo, 2 não-iterável, 1 overflow na regra por cena).
- GREEN (área + arquitetura): `… pytest -q -p no:cacheprovider
  tests/test_beat_plan.py tests/test_visual_beat.py tests/test_architecture.py`
  — **129 passed** (63 + 62 + 4). Domínio segue sem imports de
  `application`/`adapters`/`api`/I/O.
- `--collect-only tests/test_beat_plan.py` mostra os 4 nomes:
  `test_windows_reject_beats_exceeding_scene`,
  `test_windows_reject_beats_not_covering_scene`,
  `test_beats_exceeding_scene_are_rejected`,
  `test_beats_not_covering_scene_are_rejected`.

### Suíte completa (qualificada — ver §6 sobre confundidores)

Comando A (tudo, com montagem do `.git` externo exigida pelo empacotamento):
`docker run --rm --network none -v "$PWD:/workspace:ro" -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`
— **1 failed, 859 passed, 337 skipped, 1 warning**. A falha é
`tests/test_budget_guard.py::test_unreadable_provider_cost_stays_uncertain_and_never_rounds_to_zero`,
arquivo **não rastreado da fatia A** (orçamento), não desta fatia.

Comando B (excluindo os testes não rastreados de outras fatias A/C):
`… -m pytest -q -p no:cacheprovider --ignore=tests/test_budget_guard.py --ignore=tests/test_channel_domain.py --ignore=tests/test_channel_repo.py --ignore=tests/test_channel_service.py --ignore=tests/test_production_budget.py`
— **815 passed, 326 skipped, 1 warning** (sem falhas).

Separando medições: os testes da minha área passam em ambos. O número 797
citado no relatório anterior é do meu run prévio e **não** é baseline
comparável agora: o worktree é compartilhado e as fatias A/C alteraram arquivos
rastreados (`render.py`, `media.py`, `ports.py`, `use_cases.py`,
`composition.py`, migrações, etc.). Os testes de empacotamento do repo starter
externo podem falhar como "Secret hygiene check could not complete safely."
conforme o estado do repo montado (relatado pelo revisor); nos meus dois runs
eles passaram com o mount. Portanto não afirmo 797 sem essa qualificação.

## 6. Riscos que a revisão apontou e NÃO foram resolvidos (por escopo)

- **`tolerance_s` sem teto, controlável pelo chamador.** Um valor grande pode
  mascarar descasamento grosseiro: `plan_beat_windows(100.0, [1.0],
  tolerance_s=99.0)` aceita e estica um único beat de 1s para 100s. Não impus
  teto relativo à duração nesta fatia (mudaria a semântica da API); fica como
  decisão futura do integrador (F5-05/F5-06).
- **`SceneBeatPlan` é `dataclass` sem `schema_version` nem validação de
  persistência.** Se for persistido/serializado, precisará de versionamento e
  validação como os modelos `_Model` — não implementado aqui.
- **Ausência de revalidação em `model_copy` (pydantic v2)** motivou trocar por
  `VisualBeat.model_validate`; a invariante é garantida por construção e
  revalidada, mas isso reconstrói o modelo (custo desprezível neste volume).
- Auditoria de licença/proveniência (F5-08), port de mídia (F5-03), perfis de
  custo (F5-09), cache/regeneração por beat (F5-07) e render (F5-06) seguem
  fora desta fatia.
- Testes que exigem banco/serviços externos ficaram ignorados (326/337 conforme
  o run); não foram validados.
- A semântica "cada beat informa a duração desejada em `end_s - start_s`" é
  escolha desta fatia; se o storyboard (F5-05) usar tempos absolutos, a
  integração deve decidir entre reposicionar (esta regra) ou validar tempos
  fornecidos.
