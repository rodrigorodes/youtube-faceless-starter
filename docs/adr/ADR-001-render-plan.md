# ADR-001 — Render Plan como contrato canônico do audiovisual

**Status:** Aceito (fatia RP-01 da fundação Render Plan).
**Data:** 2026-11-20.
**Fonte:** `docs/superpowers/specs/2026-11-20-render-plan-foundation-design.md` (§5, §11) e
`docs/backlogs/writing-block.md` §4–§9.

## Contexto

A renderização da Duplicata/V2 tem hoje um contrato **implícito**: `RenderSpec`
(`renderer/app/studio/application/ports.py:36-46`) é um saco de listas paralelas
(`scenes`, `images`, `speech_wavs`, `scene_seconds`, `cues`) que só funciona se todo
mundo concordar com a ordem. Não há versão, hash de conteúdo, timebase explícita,
multi-shot nem proveniência no contrato.

O `writing-block.md` propõe um documento canônico, versionado e independente de
fornecedor — o `RenderPlan`. Três restrições reais do repositório moldam a decisão:

1. `tests/test_architecture.py::test_domain_has_no_outward_or_io_imports` proíbe I/O e
   imports de `application`/`adapters`/`api` no domínio.
2. Os contratos são **gerados do código** (`scripts/export_contracts.py`) e *snapshot*
   (`tests/test_contracts_snapshot.py`); JSON escrito à mão quebra o snapshot.
3. O renderer legado (`adapters/render_ffmpeg.py`, `rich.py`) produz o vídeo atual;
   substituí-lo de uma vez é risco de regressão (§11 do pedido).

A fatia RP-00 (`docs/superpowers/plans/2026-11-20-rp00-baseline-render-pipeline.md`)
corrigiu o design com quatro fatos medidos (C1–C4), todos refletidos aqui.

## Decisão

Adotar o **`RenderPlan` v1** como contrato canônico, como modelos pydantic **puros** em
`renderer/app/studio/domain/render_plan.py`:

- **Ticks inteiros + `ticks_per_second` explícito** (R1). Segundos float continuam
  sendo a unidade de autoria (`VisualBeat`); a ponte é do builder. `scene_length` e o
  QA ficam calibrados em 25 fps por default (design §5.2).
- **`content_sha256` próprio em `AssetReference`** (C1). O `assets.cache_key` é hash de
  *entrada* e o do vídeo inclui `job.id` (`application/render.py:157`), portanto não é
  content-addressable; o único precedente no domínio é `SourceSnapshot.content_sha256`.
- **Fonte de áudio gerada** (`GeneratedAudioSource`) distinta de `AssetReference` (C2):
  a música é sintetizada em processo com RNG semeado e `music=False` grava trilha
  silenciosa de mesmo comprimento — o contrato representa os dois modos.
- **Efeitos, disclosure e movimento no plano** (R3): modo de movimento explícito por
  shot (`Effects.motion`), sem o `index % 4` do renderer; `disclosure` no `Output`.
- **`style_snapshot` referencia o canal por chave + versão** (R4), sem carregar objeto.
- **Custo por cena/shot por chave** (`paid_operation_key`, R5): não muda a semântica do
  ledger `ESTIMATE`/`ACTUAL`/`FREE` da fatia A; a tabela lateral de custo é outra fatia.
- **Schema gerado do código**: `contracts/v1/renderplan.schema.json` sai de
  `scripts/export_contracts.py` (`MODELS`), nunca escrito à mão (R7 do §5).
- **Multi-shot hospedado, produtor depois** (R1/C4): o contrato aceita cenas de um shot
  e múltiplos shots com mídias distintas; o produtor de beats é fatia separada.
- **Renderer legado preservado** (R2/§11): o caminho novo é uma segunda implementação de
  `Renderer`, atrás de flag; `RenderSpec` continua sendo a entrada do legado.
- **Persistência aditiva**, sem `DROP` do caminho legado (design §5.5). API/painel ficam
  fora da fundação (R7).

## Consequências

**Prós:** uma única verdade audiovisual, versionada e validável offline; contratos
testáveis sem FFmpeg nem banco; paridade verificável com o renderer atual; base para o
editor visual (regeneração seletiva) e para o custo rotulado do mockup.

**Trade-offs:** dois caminhos (legado e plano) convivem até a comparação do §11; a
conversão ticks↔segundos exige teste de round-trip para não reintroduzir deriva que a
fatia B fechou; `Scene` do plano **não** é a `Scene` editorial do banco — o schema do
plano é `renderplan.schema.json` (a cena do banco é `scene.schema.json`), sem colisão de
nomes. A régua de sobreposição por *track* (RP-012/RP-014) e a sincronização por tipo de
mídia (RP-013) não fazem parte deste contrato; a régua de duração já existe
(`evaluate_qa`, `domain/render.py`).

## Regras verificáveis

1. `domain/render_plan.py` não importa `application`/`adapters`/`api`/I/O
   (`tests/test_architecture.py`).
2. `contracts/v1/renderplan.schema.json` é gerado e commitado; o snapshot
   (`tests/test_contracts_snapshot.py`) compara o JSON gerado ao código.
3. `RenderPlan` recusa `schema_version` desconhecido (`load_versioned`) e campos extras
   (`extra="forbid"`); é imutável (`frozen=True`).
4. Nenhum shot referencia asset inexistente; ids de cena/shot/asset são únicos no escopo;
   a duração e a resolução respeitam o formato de saída; o round-trip JSON é sem perda
   (`tests/test_render_plan.py`).
5. Segundos float não entram no plano: os ticks são inteiros estritos.
6. O JSON Schema não é editado à mão (regenerar via `scripts/export_contracts.py`).
7. A política de versionamento vale para `contracts/v1/` e para o plano:
   `docs/contracts-versioning.md`.
