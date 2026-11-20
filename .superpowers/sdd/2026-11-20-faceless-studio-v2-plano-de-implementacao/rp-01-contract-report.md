# RP-01 — Contrato canônico do Render Plan (fatia 2)

**Fatia:** 2 (RP-01) da fundação **Render Plan** — RP-005 a RP-009.
**Branch:** `faceless-v2-impl` · **Worktree:** `…/39a258/faceless-v2-implementation`.
**Base ao iniciar:** `d4db3cd`. Concorrência observada: o commit `ddfb754` (status F0–F11) entrou na
branch durante o trabalho; a fatia G1b segue com arquivos modificados não commitados, **não tocados**.
**Escopo:** só o **contrato** (modelos + schema + ADR + política + testes). Sem timeline, builder,
resolver, FFmpeg, persistência, API ou UI. Sem push/merge.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `89f45fc` | RP-006 — contrato canônico (modelos puros) + RP-009 (testes) | `renderer/app/studio/domain/render_plan.py` (+259), `tests/test_render_plan.py` (+290) |
| `c73f7fb` | RP-007 — schema gerado do código | `scripts/export_contracts.py`, `tests/test_contracts_snapshot.py`, `contracts/v1/renderplan.schema.json` (+534), `docs/10-arquitetura.md` (+1) |
| `3b3e123` | RP-005 + RP-008 — ADR e política de versionamento | `docs/adr/ADR-001-render-plan.md` (+85), `docs/contracts-versioning.md` (+84) |

## O que foi entregue

### RP-006 — modelos tipados puros (`domain/render_plan.py`)

`RenderPlan` é a raiz versionada (`schema_version` inteiro via `_Model`, `extra="forbid"`,
`frozen=True`). Nested usam `_PlanModel` (imutável/fechado, **sem** `schema_version` — só o
documento é versionado). Sem I/O e sem importar `application`/`adapters`/`api`
(`tests/test_architecture.py` cobre).

Modelos: `RenderPlan`, `Timeline`, `Scene`, `Shot`, `AssetReference`, `Output`, `StyleSnapshot`,
`Provenance`, `Composition`, `Effects`, `Transition` e **`GeneratedAudioSource`** (a fonte de áudio
gerada distinta de `AssetReference`, C2).

Decisões já tomadas refletidas no contrato:

- **Ticks inteiros + `ticks_per_second`** (`strict=True`, rejeita `float`/`bool`). Sem segundos no plano.
- **`content_sha256` próprio** em `AssetReference`, com padrão `^[0-9a-f]{64}$` (C1). Não reutiliza
  `assets.cache_key`.
- **Efeitos/disclosure/trilha no plano** (R3/C2): `Effects.motion` explícito por shot
  (`none|zoom_in|zoom_out|pan_left|pan_right`, sem `index % 4`); `Output.disclosure`;
  `GeneratedAudioSource` com `kind` (`voice|music`), `silent` e `params` (bpm/seed). `silent=True`
  representa o `music=False` do renderer (trilha silenciosa de mesmo comprimento) e não aceita `params`.
- **`style_snapshot` por chave + versão** (`source="channel"`, `style_id`, `version`), sem objeto (R4).
- **`paid_operation_key`** opcional em cena e shot (R5); o ledger da fatia A não muda.
- **Multi-shot hospedado** (R1/C4): `Scene.shots` exige ao menos 1 shot; cenas de 1 shot e multi-shot
  validam igual. O **produtor** de beats permanece fora (fatia separada).

### RP-007 — `contracts/v1/renderplan.schema.json` gerado

`RenderPlan` entrou em `MODELS` de `scripts/export_contracts.py` e `"renderplan"` na tupla de
`test_contracts_snapshot.py::test_every_entity_has_a_schema_and_diagram_lists_states`. O schema foi
**gerado** por `scripts/export_contracts.py` (rodado dentro do Docker de teste, pydantic 2.11.4) e o
`docs/10-arquitetura.md` regenerado (1 linha nova). Nada escrito à mão.

Schema: 534 linhas, `$defs` = `AssetReference`, `Composition`, `Effects`, `GeneratedAudioSource`,
`Output`, `Provenance`, `Scene`, `Shot`, `StyleSnapshot`, `Timeline`, `Transition`, `VideoFormat`.
`required` da raiz: `plan_id`, `revision`, `project_id`, `video_id`, `output`, `timeline`,
`style_snapshot`, `provenance`.

### RP-005 — ADR

`docs/adr/ADR-001-render-plan.md` (curto, no formato do ADR existente no repo: contexto/decisão/
consequências/regras verificáveis). **Nota de padrão:** o único ADR do repositório antes disso estava em
`docs/backlogs/Faceless_Studio_V2_DarkPlanner_Provider_Project/adr/` (subárvore de outro produto); não
havia pasta ADR de nível de repositório. Criei `docs/adr/`.

### RP-008 — política de versionamento e compatibilidade

`docs/contracts-versioning.md`, válida para a família `contracts/v1/` **e** para o plano. Cobre:
`schema_version` inteiro (forma) × `revision` (editorial) × `asset_version`/`style_snapshot.version`
(objeto externo); leitura fechada (`load_versioned` recusa versão desconhecida); `extra="forbid"`
(adicionar campo opcional **conta como mudança de forma** e incrementa a versão, porque um leitor
antigo recusaria o documento novo); regenerar-e-commitar com o snapshot; `v1/` só muda se a *forma do
arquivo* mudar; migração não destrutiva.

### RP-009 — testes

`tests/test_render_plan.py` — **23 testes** (TDD, RED antes do GREEN). Cobrem serialização,
validação e round-trip.

## Validações obrigatórias (todas com teste)

| Exigência | Teste |
|---|---|
| Schema inválido rejeitado | `test_unknown_fields_are_rejected`, `test_missing_required_fields_are_rejected`, `test_ticks_are_strict_integers_not_seconds`, `test_unknown_schema_version_is_rejected` |
| IDs únicos no escopo | `test_duplicate_scene_ids_are_rejected`, `test_duplicate_shot_ids_are_rejected_within_scene`, `test_duplicate_asset_ids_are_rejected`, `test_duplicate_generated_audio_ids_are_rejected` |
| Shot → asset inexistente rejeitado | `test_shot_referencing_missing_asset_is_rejected` |
| Duração respeita o formato de saída | `test_duration_must_respect_output_format_limit`, `test_resolution_must_match_output_format` |
| Round-trip sem perda | `test_plan_round_trips_through_json_without_loss` |
| Fonte de áudio gerada ≠ `AssetReference` (C2) | `test_generated_audio_is_distinct_from_asset_reference`, `test_generated_music_is_representable_with_and_without_silent_track`, `test_silent_track_carries_no_synthesis_params_and_only_music_may_be_silent` |
| Imutabilidade | `test_plan_is_immutable` |
| Efeito explícito por shot / disclosure / estilo (R3/R4) | `test_motion_is_explicit_per_shot_and_defaults_to_none`, `test_disclosure_lives_in_output`, `test_style_snapshot_references_channel_by_key_and_version_not_object`, `test_transition_duration_is_consistent_with_kind` |

## Evidências (comandos reais)

Python 3.12 no container `faceless-v2-hygiene-test-local:latest`, `--network none`, workspace `:ro`.

- **RED:** `… -m pytest -q -p no:cacheprovider tests/test_render_plan.py` →
  `ModuleNotFoundError: No module named 'app.studio.domain.render_plan'` (1 error na coleta).
- **GREEN (área):** `… tests/test_render_plan.py tests/test_contracts_snapshot.py tests/test_architecture.py tests/test_contracts.py`
  → **41 passed** (23 `render_plan` + 3 snapshot + 4 architecture + 11 contracts). Domínio segue sem imports proibidos.
- **Gerador sem drift:** `… scripts/export_contracts.py --check` → `exit=0`.
- **Nenhum outro schema mudou:** `git diff --stat contracts/` → vazio (após o commit, só
  `contracts/v1/renderplan.schema.json` foi adicionado). `docs/10-arquitetura.md` mudou só a linha nova.
- **Suíte completa:** `… -m pytest -q -p no:cacheprovider` (com o `.git` externo montado) →
  **1225 passed, 408 skipped, 1 warning**, sem falhas.

### Falhas ambientais de `test_secrets_hygiene` (qualificadas)

Sem montar o gitdir externo (`-v /Users/rodrigomendes/youtube-faceless-starter/.git:…:ro`), exatamente
**2** testes falham — e ambos por ambiente, não pelo contrato:

- `test_real_starter_archive_is_safe_and_keeps_scripts_executable`
- `test_extracted_starter_runs_contract_snapshot_and_backup_import`

Motivo: `scripts/package-starter.sh` → `scripts/secret_hygiene.py` usa `git ls-files`, e o `.git` do
worktree é um **arquivo** (`gitdir: …/youtube-faceless-starter/.git/worktrees/faceless-v2-implementation`)
que não existe dentro do container; o script termina com `Secret hygiene check could not complete
safely.` e `returncode=1`. **Com** o gitdir externo montado, os **32** testes de `test_secrets_hygiene`
passam. Um terceiro detalhe, já resolvido pelo commit: antes de commitar, o empacotamento excluía
`contracts/v1/renderplan.schema.json` (untracked) e `test_extracted_…` falhava; após o commit, passa.

## Onde o código real divergiu do design / do writing-block

1. **`schema_version` inteiro, não semver.** O §5 do `writing-block.md` ilustra `"1.0.0"` (string); o
   design (§7.3) manda usar inteiro como as outras entidades. Implementado inteiro (1). O ADR e a
   política registram a escolha.
2. **Sem `output.duration_ticks`.** O exemplo do §5 traz `duration_ticks` no output; omiti para não
   criar **duas verdades** (anti-objetivo §2). A duração é derivada: `Timeline.duration_ticks`
   (`max(start+duration)`), validada contra `MAX_SECONDS[format]`.
3. **`output.fps` inteiro em vez de `fps_num`/`fps_den`.** O timebase racional amplo (RP-010) é da
   fatia de timeline; aqui o plano tem `ticks_per_second` e o fps de entrega (default 25, decisão §5.2).
4. **`Composition`/`Transition` mínimos.** O `writing-block` lista os campos mas não as formas. Modelei
   só o que o renderer real faz: `Composition.fit` (`cover|contain`) e `Transition` (`none|fade`), com
   `fade` exigindo duração > 0 — derivado de `FADE_S=0.25` e do `index % 4` (`render_ffmpeg.py`).
5. **Nested sem `schema_version`.** O design diz "o plano usa `schema_version` inteiro como as outras
   entidades"; apliquei à **raiz** (documento). Nested não repetem o campo — evita ruído e mantém a
   versão no único lugar que identifica a forma do documento.
6. **Sobreposição por track e sincronização por tipo de mídia ficaram fora** (§9/RP-012/RP-013). O
   contrato só exige que cada shot caiba na sua cena; a régua de sobreposição é da fatia de timeline.
7. **Validei refs de narração/legenda** (resolvem no manifesto ∪ áudio gerado), além do exigido
   "shot → asset". É consistente com o anti-objetivo de referência órfã e foi além do §9 mínimo.

## Limitações desta entrega

- Não há **produtor** de plano nem persistência; nada foi plugado no `RunRender` (R2/§11 fica para as
  fatias 3–6). O `RenderSpec` e o renderer legado permanecem intactos.
- O contrato **não** verifica veracidade de proveniência/licença, disponibilidade, codec nem resolução
  de asset (RP-020/RP-022) — só exige os metadados.
- `GeneratedAudioSource.params` é `dict[str, str|int|float|bool]` sem validação semântica de bpm/seed
  (a síntese é do compilador, RP-023).
- Não toquei em `api/panel.py`, `tests/test_panel*.py`, `adapters/postgres/panel_repo.py`,
  `application/panel.py`, `0020_*.sql` nem `f1-guard-report.md` (G1b em andamento).

## Arquivos desta fatia

- `renderer/app/studio/domain/render_plan.py` (novo)
- `tests/test_render_plan.py` (novo)
- `scripts/export_contracts.py`, `tests/test_contracts_snapshot.py` (editados)
- `contracts/v1/renderplan.schema.json` (novo, gerado), `docs/10-arquitetura.md` (gerado)
- `docs/adr/ADR-001-render-plan.md`, `docs/contracts-versioning.md` (novos)
