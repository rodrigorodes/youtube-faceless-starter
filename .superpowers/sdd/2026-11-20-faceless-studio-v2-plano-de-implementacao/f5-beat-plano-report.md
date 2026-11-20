# F5 — reconciliação do contrato VisualBeat e planejamento de beats por cena

Fatia B (domínio apenas). Base: `5b7eecf`. Nenhum push/merge. Esta fatia **não
conclui F5**: não há integração com renderer, `Scene`, persistência, API/UI nem
auditoria real de licença (F5-06/F5-07/F5-08 seguem pendentes).

## Escopo entregue

- `renderer/app/studio/domain/visual_beat.py`: contrato reconciliado; docstring
  canônica com a decisão e a divergência; nova propriedade derivada `duration_s`.
- `renderer/app/studio/domain/beat_plan.py`: regra pura `plan_scene_beats` e o
  núcleo numérico `plan_beat_windows`, com `SceneBeatPlan`. Sem I/O.
- `tests/test_beat_plan.py`: 40 testes novos (TDD, RED antes de GREEN).
- `tests/test_visual_beat.py`: +1 teste da propriedade derivada.

Sem tocar em `render.py`, `panel.py`, `adapters/**`, `Scene`,
`narration_duration.py`, `production.py` ou `test_production_budget.py`.

## 1. Reconciliação do contrato (decisão)

**Formato canônico escolhido:** `app.studio.domain.visual_beat.VisualBeat`, com
os campos do card F5-01 — `scene_id`, `start_s`, `end_s`, `asset_kind`,
`reference`, `transition`, `provenance`, `license` (versionado, imutável,
`extra="forbid"`).

Divergência com o esqueleto do plano
(`docs/superpowers/plans/...md`, Task 6, ~linhas 397-406), que importava
`VisualBeat` de `contracts` e usava `beat_id`, `duration`, `effect`:

| Plano (rascunho) | Canônico | Tratamento |
|---|---|---|
| `from ...contracts import VisualBeat` | `domain.visual_beat` | O plano divergia do próprio card F5-01 (que fixa o módulo e os campos). O esqueleto é anterior ao card e não tem consumidor real: apenas `tests/test_visual_beat.py` importa `VisualBeat`. Mantido um único módulo, sem duplicar o contrato em `contracts`. |
| `duration` (float) | `end_s - start_s` | Ponte aditiva: propriedade derivada `duration_s`, somente leitura, **não** persistida (verificado no teste: `"duration_s" not in model_dump()`). Sem renomear ou quebrar campos existentes. |
| `effect` (`zoom_in`, `pan_right`) | — | **Não** mapeado para `transition`. `effect` é movimento de câmera; `transition` é crossfade entre beats (opcional e sem semântica de efeito suportado). Movimento pertence ao render (F5-06); inventar um campo `effect` sem consumidor seria contrato especulativo. Sem campo canônico. |
| `beat_id` | — | Não existe. Identidade do beat é (`scene_id`, ordem) ou `reference`. Granularidade/cache por beat é F5-07. |
| `Scene(scene_id=..., narration=..., beats=[...])` | `Scene` real usa `id`, `video_id`, `idx`, `narration`, `duration_s`… e **não** tem `beats` | Esqueleto do plano também erra a forma de `Scene`. Integração (campo `beats`/1:N) fica para etapa posterior, por restrição explícita; `Scene` não foi alterado. |

Não houve renomeação de campo existente, então não há migração a fazer; o que
existe é compatibilidade aditiva (`duration_s`) e documentação da quebra de
expectativa em relação ao rascunho. Não foi adicionado re-export em
`contracts`: criaria acoplamento circular (`contracts` ↔ `visual_beat`) e
legitimaria um caminho de módulo incorreto.

**Testes existentes:** `tests/test_visual_beat.py` permanece válido sem
alteração de comportamento — apenas ganhou um teste novo (contagem da suíte
não cai, nenhum teste removido ou relaxado).

## 2. Planejamento de beats por cena (regra pura)

`plan_scene_beats(scene, beats, *, tolerance_s=1e-6) -> SceneBeatPlan`

- Cada beat de entrada carrega a **duração desejada** em `end_s - start_s`; a
  posição absoluta é recalculada para que os beats fiquem contíguos a partir de
  0 e cubram `[0, scene.duration_s]`. A ordem de entrada é preservada (estável);
  o último beat fecha exatamente a cena.
- `SceneBeatPlan(scene_id, duration_s, beats)` é `frozen` e expõe `coverage_s`.
- Retorna **novos** `VisualBeat` (`model_copy`), preservando os campos de mídia;
  não muta a entrada.

Validações que rejeitam com `ValueError` (núcleo puro `plan_beat_windows`
separado do contrato de mídia para testar as fronteiras numéricas):

- cena sem `duration_s` (`None`), zero, negativa, não finita (`inf`/`nan`), ou
  de tipo inválido (`bool`/`str`, inclusive dado malformado injetado via
  `model_copy`);
- zero beats;
- beat que não pertence à cena (`beat.scene_id != scene.id`) ou que não é
  `VisualBeat`;
- duração de beat não finita, negativa ou zero;
- soma das durações que **excede** a cena ou **não a cobre** além de
  `tolerance_s` (default `1e-6`);
- `tolerance_s` inválido (negativo, não finito, tipo errado).

A distribuição é sequencial por construção, portanto **sem sobreposição**: cada
beat começa onde o anterior termina. Resíduo de ponto flutuante é absorvido no
último beat para fechar a cena (`coverage_s == duration_s`).

## 3. Proveniência e licença (limite explícito)

Mantida a exigência de `provenance` e `license` não vazias para mídia externa
(`stock`, `ai_image`, `ai_clip`, `diagram`, `screen_capture`), com
`text_animation` local isenta. Ficou explícito na docstring do contrato, na
docstring do módulo de planejamento e aqui: **o contrato NÃO verifica** a
veracidade da proveniência, a validade/à prova real da licença, o uso de
marca/pessoa nem a recuperabilidade/existência do asset. Apenas exige strings
não vazias. Auditoria de direitos é F5-08 e não foi implementada (não é
verificável offline).

## Evidências (comandos e resultados reais)

Python 3.12 na imagem `faceless-v2-hygiene-test-local:latest`, `--network none`,
workspace montado somente leitura.

1. RED — módulo de planejamento ausente:
   `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_beat_plan.py`
   — `ModuleNotFoundError: No module named 'app.studio.domain.beat_plan'` (erro de coleta).

2. RED — propriedade derivada ausente:
   `… pytest -q -p no:cacheprovider tests/test_visual_beat.py::test_duration_s_is_derived_from_the_interval`
   — `AttributeError: 'VisualBeat' object has no attribute 'duration_s'`.

3. GREEN — área + arquitetura:
   `… pytest -q -p no:cacheprovider tests/test_beat_plan.py tests/test_visual_beat.py tests/test_architecture.py`
   — **106 passed** (40 beat_plan + 62 visual_beat + 4 arquitetura). A camada de
   domínio continua sem imports de `application`/`adapters`/`api`/I/O.

4. Suíte completa (montagem extra somente leitura do Git externo, exigida pelos
   testes de empacotamento):
   `docker run --rm --network none -v "$PWD:/workspace:ro" -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`
   — **797 passed, 310 skipped, 1 warning** (depreciação Starlette/AnyIO). O
   baseline relatado era 756 passaram / 310 ignorados; a diferença de +41 é
   exatamente os 41 testes novos desta fatia (40 em `test_beat_plan.py` + 1 em
   `test_visual_beat.py`). Sem regressões.

## Limitações e o que não foi feito

- F5 **não** está concluída: sem render (F5-06), sem 1:N beats em `Scene`, sem
  port de mídia/provider registry (F5-03), sem perfis de custo (F5-09), sem
  auditoria de licença (F5-08) e sem regeração/cache por beat (F5-07).
- O esqueleto do plano de implementação continua inconsistente com o card
  F5-01; recomenda-se atualizar o documento `docs/superpowers/plans/...md` numa
  tarefa de documentação (fora desta fatia, para não colidir com outros agentes).
- Testes que exigem banco/serviços externos ficaram ignorados (310), como no
  baseline; não foram validados.
- Nenhuma verificação jurídica, de veracidade ou de recuperabilidade de asset é
  feita — apenas não-vazio.
- A semântica "cada beat informa a duração desejada em `end_s - start_s`" é uma
  escolha de modelagem desta fatia; se o storyboard (F5-05) definir beats com
  tempos absolutos, a integração deverá decidir explicitamente entre reposicionar
  (esta regra) ou validar tempos fornecidos.
