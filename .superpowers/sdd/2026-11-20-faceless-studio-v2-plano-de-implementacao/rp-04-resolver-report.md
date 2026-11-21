# RP-04 — Asset Resolver e multi-asset (fatia 5)

**Fatia:** 5 (RP-04) da fundação **Render Plan** — RP-019 a RP-022.
**Branch:** `feat/rp-04-resolver` · **Worktree:** `…/39a258/rp-04-resolver`.
**Base ao iniciar:** `51734c7`. Concorrência: nenhuma alteração inesperada observada; os arquivos proibidos
da fatia G (`api/panel.py`, `application/panel.py`, `adapters/postgres/panel_repo.py`) e de outras fatias
**não foram tocados**. Commits locais por caminho exato; **sem push e sem merge**.

**Escopo entregue:** porta `AssetResolver`, manifesto indexado, `AssetDescriptor` por tipo de mídia,
validação de disponibilidade/hash/licença/codec/resolução/duração e o caso de uso `ResolvePlanAssets`.
**Sem render, sem FFmpeg, sem subprocess.** O executor é o RP-05.

## Commits

| Commit | Tema | Arquivos |
|---|---|---|
| `9e6387b` | RP-019..RP-022 — resolver, manifesto e validação multi-asset | `renderer/app/studio/domain/asset_resolver.py` (+212), `renderer/app/studio/application/assets.py` (+64), `renderer/app/studio/application/ports.py` (+15), `renderer/app/studio/adapters/asset_resolver.py` (+134), `tests/test_asset_resolver.py` (+436) |

Um único commit: o arquivo de teste exercita domínio, aplicação e adapter juntos, então um commit
torna a árvore verde de ponta a ponta. `git show --stat` = **5 arquivos, 861 inserções**.

## O que foi entregue

### RP-019 — porta `AssetResolver`

`AssetResolver(Protocol)` em `application/ports.py` (a arquitetura real **não** tem `renderer/ports/`; o
design §3 manda usar `application/ports.py`): `resolve(reference: AssetReference) -> AssetDescriptor`.
O resolver concreto é injetado em `ResolvePlanAssets`; o núcleo de render não depende de implementação.

### RP-020 — manifesto com URI, versão, `content_sha256` e licença (C1)

`AssetManifest` (`domain/asset_resolver.py`) indexa `RenderPlan.asset_manifest` por `asset_id`
(`of(plan)` — não é segunda verdade, só a leitura da mesma lista) e recusa duplicados.
`verify_descriptor` exige que o descriptor confira com a entrada do manifesto em **versão, URI,
`content_sha256` e tipo**, com **licença registrada** para mídia externa e **arquivo disponível**.
O `content_sha256` é do **conteúdo** (C1): o `LocalAssetResolver` recomputa `sha256` dos bytes e recusa
um manifesto que não bata — nunca reusa `assets.cache_key` (hash de entrada; o do vídeo inclui `job.id`).

### RP-021 — imagem, vídeo, gráfico e texto

`AssetDescriptor` com regras por tipo, validadas na **construção** (não dá para forjar um descriptor
incompleto):

- `image`/`graphic`: `codec` na lista de raster, `width`/`height` obrigatórios, **sem** duração;
- `video`: `codec` na lista de vídeo, `width`/`height` **e** `duration_ticks` obrigatórios;
- `text`: animação **local** (`text_animation`), isenta de mídia externa — proíbe `codec`, `width`,
  `height`, `duration_ticks` e `location`.

### RP-022 — disponibilidade, codec, resolução e duração

- **Disponibilidade**: o adapter reporta `available=False` (arquivo ausente) e `verify_descriptor`
  recusa com o URI; nada é inventado.
- **Codec**: validado no descriptor (lista fechada por tipo); o adapter traduz metadado inválido em
  `AssetResolutionError`.
- **Resolução** (`check_fit`): composição `cover` exige resolução ≥ saída (sem upscale); `contain`
  aceita qualquer resolução positiva.
- **Duração**: o vídeo tem de durar ≥ o shot que o consome (cada shot é checado).

`ResolvePlanAssets` percorre o manifesto (resolve + verifica identidade/licença/disponibilidade) e **cada
shot** (`composition.fit` + `duration_ticks`), e devolve `ResolvedAssets` indexado por `asset_id`.

### Adapter `LocalAssetResolver` (toca disco)

- **imagem/gráfico**: sonda o arquivo com **Pillow** (formato→codec e dimensões reais) e confere o hash;
- **vídeo**: **sem ffprobe** nesta fatia — codec/resolução/duração vêm declarados no `metadata` do
  `AssetReference` e são validados; faltando, falha claro;
- **texto**: local, sem arquivo;
- confere existência e hash do conteúdo em todos os casos externos; recusa `uri` que escapa da raiz.

## Aceite de RP-04 (design R1/C4)

“Cada cena suporta múltiplos shots com mídias distintas” é provado no nível do **contrato + resolver**
(como o design manda: o produtor de beats é fatia separada). O teste
`test_resolve_plan_accepts_a_multi_shot_scene_with_distinct_media` monta uma cena de **4 shots contíguos**
(imagem, vídeo, gráfico e texto) e resolve/valida os 4; o teste de integração
`test_adapter_and_use_case_resolve_a_multi_media_scene_from_disk` faz o mesmo **a partir de arquivos reais
no disco** (PNGs + “vídeo” com metadado declarado + texto local).

## Validações obrigatórias (todas com teste)

| Exigência | Teste |
|---|---|
| Porta `AssetResolver` devolve `AssetDescriptor` | uso via `ResolvePlanAssets` em todos os testes de aplicação |
| Manifesto com URI/versão/hash/licença (C1) | `test_manifest_indexes_references_and_rejects_duplicates`, `test_verify_descriptor_rejects_identity_drift` (versão/URI/hash/tipo), `test_adapter_rejects_a_content_hash_mismatch` |
| Licença obrigatória para mídia externa | `test_descriptor_requires_a_license_for_external_media`, `test_verify_descriptor_rejects_a_license_mismatch`, `test_adapter_rejects_external_media_without_a_registered_license` |
| Quatro tipos de mídia / texto isento | `test_descriptor_requires_codec_and_resolution_for_raster_media`, `test_local_text_asset_is_exempt_from_external_media`, `test_adapter_resolves_a_local_text_asset_without_external_media` |
| Codec desconhecido recusado | `test_descriptor_video_rejects_an_unknown_codec`, `test_adapter_rejects_an_unknown_declared_video_codec` |
| Disponibilidade | `test_verify_descriptor_rejects_an_unavailable_asset`, `test_adapter_reports_an_unavailable_asset_without_inventing_metadata`, `test_resolve_plan_fails_when_an_asset_is_unavailable` |
| Resolução (cover/contain) | `test_check_fit_rejects_upscaling_under_cover`, `test_check_fit_allows_a_smaller_asset_under_contain`, `test_resolve_plan_honours_contain_on_a_small_image` |
| Duração do vídeo vs. shot | `test_check_fit_rejects_a_video_shorter_than_its_shot`, `test_resolve_plan_fails_when_the_video_is_shorter_than_its_shot` |
| Sem inventar metadado | `test_adapter_rejects_a_video_without_declared_metadata`, `test_adapter_rejects_a_file_that_is_not_a_readable_image` |
| Multi-asset (aceite) | `test_resolve_plan_accepts_a_multi_shot_scene_with_distinct_media`, `test_adapter_and_use_case_resolve_a_multi_media_scene_from_disk` |
| Arquitetura (domínio/aplicação sem mídia) | `tests/test_architecture.py::test_render_core_has_no_media_or_provider_sdks` (verde; `PIL` só no adapter) |

## Evidências (comandos reais)

Python 3.12.16 / pytest 8.3.5 na imagem `faceless-v2-hygiene-test-local:latest`, `--network none`,
workspace `:ro`, `-p no:cacheprovider`, `PYTHONPATH=/workspace/renderer`.

- **RED:** com os três módulos novos ausentes,
  `… -m pytest -q -p no:cacheprovider tests/test_asset_resolver.py` →
  `ModuleNotFoundError: No module named 'app.studio.adapters.asset_resolver'` (1 error na coleta).
- **GREEN (área):**
  `… tests/test_asset_resolver.py tests/test_architecture.py tests/test_contracts_snapshot.py tests/test_render_plan.py tests/test_render_plan_timeline.py`
  → **107 passed** (40 do resolver + 6 architecture + 3 snapshot + 23 render_plan + 35 timeline).
- **Contagem nova:** `tests/test_asset_resolver.py` = **40 testes**.
- **Gerador sem drift:** `… scripts/export_contracts.py --check` → `exit=0`; `git diff --stat contracts/ docs/10-arquitetura.md` → **vazio**
  (não há modelo novo no documento do plano — `AssetDescriptor` não é contrato versionado).
- **Suíte completa (com o `.git` externo montado):**
  `… -v /Users/rodrigomendes/youtube-faceless-starter/.git:…:ro … -m pytest -q` →
  **1367 passed, 423 skipped, 1 warning**, sem falhas.
- **Suíte completa (sem o gitdir):** **2 failed, 1365 passed, 423 skipped** — as **mesmas 2 falhas
  ambientais** qualificadas no RP-01/RP-02
  (`test_real_starter_archive_is_safe_and_keeps_scripts_executable`,
  `test_extracted_starter_runs_contract_snapshot_and_backup_import`): `scripts/secret_hygiene.py` usa
  `git ls-files` e o `.git` do worktree é um **gitfile** ausente no container. **Com** o gitdir montado,
  passam — não é regressão desta fatia.
- **Sem Docker/FFmpeg no resolver:** o adapter importa apenas `hashlib`, `pathlib` e `PIL`; não há
  `subprocess` nem `ffmpeg` no caminho de resolução (grep no arquivo).
- **Sem migração:** 0024 **não** foi usado e `tests/test_db.py` ficou intacto (ver abaixo).

## Onde o código real contradisse o design / o writing-block

1. **Vídeo não pode ser sondado nesta fatia.** O design (tabela de lacunas) e RP-022 pedem “validar
   codec/resolução”; a sondagem real de vídeo é `ffprobe` (**subprocess**), proibido aqui por escopo. O
   que se fez: imagem/gráfico são **sondados de verdade** (Pillow: formato e dimensões reais) e o vídeo é
   **declarado** no manifesto e **validado** (codec fechado, resolução, duração) — nunca medido. A medição
   de vídeo fica no executor (RP-05). É a contradição mais relevante entre o pedido literal e a restrição
   explícita da fatia.
2. **Metadado técnico de vídeo vive no manifesto.** Para não inventar, o adapter precisa de codec/dims/
   duração do vídeo; usei `AssetReference.metadata: dict[str,str]` (`codec`, `width`, `height`,
   `duration_ticks`). O writing-block §4 diz que “detalhes específicos do fornecedor permanecem fora do
   contrato obrigatório”; codec/resolução não é exatamente detalhe de fornecedor, e `metadata` é o ponto
   de extensão do contrato — registrado como escolha pragmática. Um resolver apoiado em proveniência pode
   substituir isso sem mudar a porta.
3. **`duration_ticks` declarada na timebase do plano.** Como o resolver só recebe o `AssetReference`,
   a duração declarada do vídeo é em ticks **da timebase do plano** (o manifesto é do plano). Se a
   timebase mudar, o manifesto tem de ser reconstruído — consequência não prevista no design.
4. **`AssetDescriptor` não é contrato versionado.** O writing-block §7 lista a porta e seu DTO, mas o
   `AssetDescriptor` é DTO de resolução (efêmero), **não** parte do documento `RenderPlan`; por isso não
   entrou em `export_contracts.py` e o snapshot de contratos não mudou. O “manifesto” de RP-020 continua
   sendo `RenderPlan.asset_manifest`.
5. **“Validar resolução” precisou de predicado.** O design não define o que é resolução válida. Adotei:
   `cover` ⇒ asset ≥ saída (sem upscale); `contain` ⇒ qualquer resolução positiva. É política escolhida
   aqui (como o RP-02 teve de definir “zero lacunas” com um predicado).
6. **Licença é política do resolver, não do contrato.** `AssetReference.license` é opcional (`_Model` do
   RP-01); RP-020 quer licença no manifesto. Mantive o contrato permissivo e tornei a licença
   **obrigatória no resolver** para mídia externa — um plano representa asset ainda sem licença, mas não
   se resolve.
7. **Texto local ainda exige `content_sha256`.** `AssetReference.content_sha256` é `Hex64` obrigatório
   para **todos** os tipos. Como o texto é local (sem bytes externos), seu hash é do conteúdo local e o
   adapter **não** o confere contra arquivo. Pequena assimetria do contrato do RP-01 preservada.
8. **Sem migração `0024`.** O design §5.5 fala de tabelas “por hash/codec/localização (física)”, mas
   persistir identidade física/plano é de outra fatia; RP-04 resolve contra o storage e o manifesto. Não
   adicionei coluna nem toquei `tests/test_db.py`. `0024` segue livre.
9. **ADR-001 segue desatualizado** (já apontado no RP-02): o docstring de `domain/render_plan.py` ainda
   diz que disponibilidade/codec/licença são “fatias posteriores”. Continua verdadeiro **para o
   contrato**; a resolução passou a validá-los fora dele. Não editei o ADR por não estar na lista de
   arquivos desta fatia.

## Limitações desta entrega

- **Sem produtor nem fiação**: nada foi plugado no `RunRender`/`composition.py` (o executor é RP-05); a
  persistência e o painel do plano continuam de outras fatias (R7).
- **Vídeo declarado, não medido** (itens 1–3 acima).
- **Tolerância de duração do vídeo** é `≥` shot: um clipe mais longo é cortado; um mais curto falha.
- **Listas de codec fechadas** (`IMAGE_CODECS`/`VIDEO_CODECS`) são de política e terão de crescer com os
  provedores reais; hoje cobrem o que o pipeline usa (PNG/JPEG e H.264 etc.).
- **`AssetDescriptor` não guarda proveniência** (`provider`/`model`): o contrato não os expõe e a
  proveniência fica fora, como o writing-block pede.

## Arquivos desta fatia

- `renderer/app/studio/domain/asset_resolver.py` (novo) — `AssetDescriptor`, `AssetManifest`,
  `AssetResolutionError`, `verify_descriptor`, `check_fit`, codecs.
- `renderer/app/studio/application/ports.py` (editado) — porta `AssetResolver`.
- `renderer/app/studio/application/assets.py` (novo) — `ResolvedAssets`, `ResolvePlanAssets`.
- `renderer/app/studio/adapters/asset_resolver.py` (novo) — `LocalAssetResolver`.
- `tests/test_asset_resolver.py` (novo, 40 testes).
