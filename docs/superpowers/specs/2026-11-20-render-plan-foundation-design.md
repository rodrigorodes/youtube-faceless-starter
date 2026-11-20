# Render Plan Foundation — design e análise

**Fonte do pedido:** `docs/backlogs/writing-block.md` (F5-RP, status "Planejado", P0)
**Analisado contra:** o código real em `renderer/app/studio/`, as fatias em andamento (A, C, D, D2, G1) e o mockup aprovado (`produto/mockup-proposta.html`).
**Data:** 2026-11-20

---

## 1. Intenção

Hoje a renderização da Duplicata/V2 tem um contrato **implícito**: `RenderSpec` é um
saco de listas paralelas (`scenes`, `images`, `speech_wavs`, `scene_seconds`, `cues`)
que só funciona se todo mundo concordar com a ordem e com o fato de que o índice *i*
de uma lista casa com o índice *i* da outra. Não há versão, não há hash de asset, não
há timebase explícita, não há múltiplos shots por cena e não há registro de proveniência
no contrato.

O `writing-block.md` propõe trocar isso por um documento canônico, versionado e
independente de fornecedor — o **`RenderPlan`** — que o renderer executa sem conhecer o
roteiro editorial, o provider que gerou um asset ou as regras do canal.

Concordamos com a direção. Este documento aterrissa a proposta no código que existe,
aponta o que **já está pronto** (e portanto não precisa ser refeito) e o que colide.

## 2. Objetivo, não-objetivos e anti-objetivos

**Objetivo:** um `RenderPlan` v1 publicável, validado e versionado, com timeline
determinística (ticks inteiros), composição com vários shots por cena, manifesto de assets
com hash/versão/licença, e um adapter de render que executa **exclusivamente** o plano +
os assets resolvidos.

**Não-objetivos desta fundação:**
- SaaS, quota por organização, render distribuído (F11 — adiado).
- Editor visual interativo (timeline com arrasto). A fundação precisa *alimentar* esse
  editor depois, não implementá-lo agora.
- Integração DarkPlanner (sem contrato de API confirmado — bloqueado).
- Publicação real no YouTube.

**Anti-objetivos** (o que faria isso ser um fracasso mesmo funcionando):
- **Regressão funcional** nos vídeos do fluxo atual. O §11 do pedido exige preservar o
  renderer legado e comparar saídas; quebrar o `/videos` (modo *rich*) para ter plano
  bonito é fracasso.
- **Segundo lugar onde a verdade mora.** Um `RenderPlan` que divergir do `Scene`/`Asset`
  do banco cria duas verdades. A fundação tem de ser projeção fiel do que já existe.
- **Custo inventado.** O plano não pode reintroduzir a suposição, já rejeitada na fatia A
  de que "estimativa positiva = custo real".

## 3. Restrições reais (com evidência no repositório)

| Restrição | Evidência | Consequência para o plano do pedido |
|---|---|---|
| `domain` não importa `application`/`adapters`/`api`/I/O | `tests/test_architecture.py::test_domain_has_no_outward_or_io_imports` | `renderer/domain/audiovisual/` do §3 vira `app/studio/domain/…`, puro |
| `application` só importa `domain` | `test_application_only_imports_domain` | **não existe** `renderer/ports/`; as portas vivem em `application/ports.py` (§3 do pedido é inválido como está — o próprio doc manda "adaptar aos módulos existentes") |
| Schema não é escrito à mão | `scripts/export_contracts.py` + `tests/test_contracts_snapshot.py` | `contracts/render_plan/v1/schema.json` do §3 vira `contracts/v1/renderplan.schema.json`, **gerado** do modelo pydantic. Editar JSON à mão quebra o snapshot |
| Contratos são *snapshot* versionado | `tests/test_contracts_snapshot.py::test_committed_contracts_match_code` | todo modelo novo exige rodar `scripts/export_contracts.py` e commitar o JSON |
| Testes rodam offline | Docker `--network none`, `-p no:cacheprovider` | o **compilador** plano→comando tem de ser puro e testável sem FFmpeg instalado |
| Integração com Postgres é *opt-in* | `tests/conftest.py` (`STUDIO_TEST_DSN`) | persistência do plano testável só com banco descartável |
| Custo tem semântica dura | fatia A: `ESTIMATE`/`ACTUAL`/`FREE`, `ACTUAL` exige `ChargeEvidence` | campos de custo do plano têm de respeitar isso, não podem virar número solto |
| Ações bloqueadas pelo harness | `git push`, merge de PR, remoção via GitHub | rollout (§RP-032) fica em flag local; sem publicação remota |

## 4. Análise de lacuna — hoje vs. o que o pedido quer

| Capacidade pedida (RP) | O que já existe | Lacuna real |
|---|---|---|
| Timebase racional, ticks inteiros (RP-10) | `domain/render.py`: `FPS = 25`, `scene_length` arredonda para quadro inteiro em **float segundos** | falta `ticks_per_second` explícito e aritmética inteira |
| Cenas, shots, tracks (RP-11) | `VisualBeat` + `plan_scene_beats` (1 beat = 1 mídia, dentro da cena) | falta o conceito de **shot** com `track_id`; hoje "shot" ≈ beat |
| Sobreposição e intervalos (RP-12) | `plan_beat_windows`: janelas contíguas, sem sobreposição, cobertura validada, fuzz de ~34k casos | **pronto** — é o núcleo de RP-12 já fechado (fatia B) |
| Narração e legendas na timeline (RP-13) | `make_cues`, `Cue(start,end)`, `to_srt`, `NARRATION_FILE` | já existe, mas em segundos float, fora do plano |
| Contrato canônico + schema (RP-05..RP-08) | `contracts/v1/*.schema.json` (13 entidades) + `_Model` pydantic | falta `RenderPlan`/`Scene`/`Shot`/`AssetReference` **no plano**, não no banco |
| Builder do storyboard (RP-15/16) | `Scene` (banco) → `RenderSpec` (listas paralelas) em `application/render.py` | falta projeção explícita e `StyleSnapshot` do canal |
| Asset Resolver (RP-19..22) | `AssetRepository`, `AssetStore`, `Asset(cache_key, path, license, provider, model)` | falta porta `AssetResolver` com `content_sha256`, codec/resolução e validação de disponibilidade |
| FFmpeg adapter (RP-23..26) | `adapters/render_ffmpeg.py` (152 linhas, Ken Burns + legenda queimada via Pillow), `rich.py` | falta **compilador puro** + executor; hoje é um monólito com `subprocess` |
| Regeneração seletiva (RP-27..29) | `production_run.py` (DAG, lease, fencing, checkpoint) + outbox | falta o grafo de dependências **por cena/shot** e o cache de artefato |
| QA (RP-30) | `domain/render.evaluate_qa` + `adapters/qa_ffmpeg.py` | já existe; falta o `QualityEvaluator` como porta e o gate ligado à publicação (limitação já registrada) |

**Leitura:** cerca de **um terço do pedido já está implementado** — só que espalhado e sem
o contrato que amarra tudo. O trabalho novo concentra-se em RP-01 (modelo), RP-05 (builder),
RP-19 (resolver) e RP-23 (executor). RP-12 está fechado; RP-30 existe.

## 5. Decisões (defaults que eu escolho)

Cada linha é uma escolha minha, reversível, com o porquê. Se discordar, é só dizer.

1. **Ticks no plano, segundos na autoria.** O `RenderPlan` usa inteiros + `ticks_per_second`.
   O `VisualBeat` (segundos float) continua sendo a unidade **editorial** humana; o builder
   é a ponte e converte com testes de ida-e-volta. Motivo: não reescrever a fatia B, que já
   passou por fuzz e está fechada (§11 do pedido: nada destrutivo na primeira entrega).
2. **Timebase = 25 fps por padrão, não 30.** O exemplo do pedido usa 30, mas `render.py` já
   fixa `FPS = 25` e o QA (`expected_s`, tolerância de 1 s) foi calibrado nisso. Trocar o fps
   de saída é **decisão de produto** com recalibração de QA e comparação com vídeos legados —
   fica explícita, não acidental. O `ticks_per_second` do plano é parametrizável desde já.
3. **Schema sai do código, não do doc.** `RenderPlan`, `Scene`, `Shot`, `AssetReference` são
   modelos pydantic em `domain/`, e `contracts/v1/renderplan.schema.json` é gerado. Nada de
   `contracts/render_plan/v1/schema.json` escrito à mão (quebraria o snapshot de contratos).
4. **Compilador puro, executor em adapter.** `RenderPlan → lista de argumentos/graph FFmpeg`
   é função pura, no `application`/`domain`, testável sem FFmpeg. Só o `subprocess` mora em
   `adapters/`. Isso é o que torna "contratos testáveis sem FFmpeg" verdade, não slogan.
5. **Persistência: identidade lógica ≠ física** (§8 do pedido). Tabelas por plano/revisão/
   cena/shot (lógica) e por hash/codec/localização (física). Migração **aditiva**, nunca
   `DROP` do caminho legado.
6. **Rollout por flag local**, sem publicação remota (harness bloqueia push/merge). O
   caminho novo e o antigo rodam lado a lado; o antigo é o default até comparação registrada.
7. **Custo entra pelo guard existente.** O plano referencia operações pagas por chave; nada
   de campo de custo que burle `ESTIMATE`/`ACTUAL`/`FREE` da fatia A.

## 6. Fatiamento proposto

Ordem desenhada para **paralelizar** e para não depender do que ainda está aberto.
Cada fatia: TDD, commit local por caminho exato, revisão independente.

| # | Fatia | RP | Depende de | Paralelizável |
|---|---|---|---|---|
| 1 | Baseline: mapear `Storyboard→Assets→Render`, hashes e vídeos de regressão | RP-00 | — | sim |
| 2 | Contrato: modelos `RenderPlan/Scene/Shot/AssetReference` + schema gerado | RP-01 | 1 | sim |
| 3 | Timeline: `ticks_per_second`, tracks, sobreposição, ponte com `VisualBeat` | RP-02 | 2 | não (2) |
| 4 | Builder: `Scene` → plano + `StyleSnapshot` do canal | RP-03 | 2, **C** (identidade do canal) | sim |
| 5 | Asset Resolver: porta + manifesto com hash/versão/licença | RP-04 | 2 | sim (paralelo a 4) |
| 6 | FFmpeg: compilador puro + executor + publicação atômica | RP-05 | 3, 5 | não |
| 7 | Regeneração seletiva: grafo de dependências + cache | RP-06 | 6, **D/D2** | não |
| 8 | QA e rollout: `QualityEvaluator`, flag, comparação com o pipeline antigo | RP-07 | 6 | não |

**Caminho crítico:** 1 → 2 → 3 → 6 → 8. As fatias 4 e 5 correm em paralelo ao 3.
As fatias 1 e 2 podem começar **assim que as fatias atuais A/C/G1 fecharem** — não conflitam
com nenhum arquivo em edição (A toca `budget.py`/`budget_repo.py`; C toca `channel*` e
migração; G1 toca `api/panel.py`). A fatia 2 cria arquivos **novos**.

**Aviso de integração:** a fatia 2 deve ser a **primeira a commitar** o modelo de plano.
Se A, C ou D2 criarem qualquer coisa que o plano referencie (chave de operação paga, snapshot
de canal), o plano só referencia a **chave**, nunca o objeto — para não acoplar.

## 7. Conflitos e riscos (medidos, não supostos)

1. **Timebase 25 vs 30.** `render.py:8` fixa 25; o pedido exemplifica 30. Decisão explícita
   (item 2 acima). Silenciar isso é o risco de "melhoria de qualidade" virar quebra de QA.
2. **`VisualBeat` em segundos vs plano em ticks.** Resolvido pela ponte do item 1, mas exige
   teste de round-trip: `ticks → segundos → ticks` sem deriva. O `beat_plan` já acumula
   sequencialmente e rejeita span não representável — a conversão não pode reintroduzir
   deriva de arredondamento que a fatia B fechou.
3. **Família de contratos.** Hoje `contracts/v1/` mistura entidades com `schema_version`
   default 1. Um `RenderPlan` com sua própria versão de *schema do plano* (`1.0.0` no §5)
   convive com isso ou cria confusão? Default: o plano usa `schema_version` inteiro como as
   outras entidades, e a "política de versionamento" (RP-08) é escrita **uma vez** e vale para
   as duas famílias.
4. **Substituir `render_ffmpeg.py` é risco de regressão.** Ele e o `rich.py` produzem o vídeo
   atual. O compilador novo tem de reproduzir, no mínimo: Ken Burns, selo, aviso de imagem
   sintética, legenda queimada por trecho, ducking e `loudnorm` (`-16`). A comparação do
   §11 é obrigatória antes de a flag virar default.
5. **Legenda por modelo.** `make_cues` distribui tempo **proporcional ao tamanho do trecho**,
   não alinhado por TTS. O pedido quer "sincronização dentro da tolerância por tipo de mídia".
   A fundação pode representar o alinhamento; a **calibração** é limitação registrada e não
   está no escopo.
6. **`VisualBeat` não verifica licença/veracidade** (documentado no próprio módulo). RP-20
   pede licença no manifesto. A fundação **carrega** o metadado; **provar** o direito é F5-08
   e continua fora.
7. **Gate de QA não ligado à publicação** já é limitação conhecida. RP-30 é a oportunidade de
   ligá-lo; se não ligar, o rollout (RP-32) fica incompleto.

## 8. Superfície de produto (mockup + Dotti)

O mockup aprovado e as telas de `JORNADA-E-TELAS.md` **já pressupõem** esta fundação:

- O **stepper** (`Roteiro · Fontes · Fact-check · Cenas · Voz · Render · QA · Publicação`) é a
  projeção visual das etapas do plano. Só faz sentido com estado por etapa — que é o que o
  plano versionado fornece.
- A tela **Editor** ("Regenerar cena") é RP-06 com UI. Sem grafo de dependências, o botão
  "regenerar cena" ou refaz tudo (caro) ou mente.
- A tela **Preview** ("QA, render hash, alertas bloqueantes") é RP-30/32. O `render hash` do
  mockup é literalmente o `content_sha256` do manifesto de assets.
- **Custo rotulado** (Real / Estimado / Sem custo / Desconhecido) é a fatia A aparecendo na UI;
  o plano tem de transportar a atribuição por cena para a tela não inventar.

**Dotti como referência:** o Dotti vende "conecte suas APIs e produza no seu computador" com
planos por vídeos/dia. É a mesma promessa de **throughput e custo** — e é exatamente onde o
nosso número tem de ser **honesto**: as métricas do §10 do pedido (custo por minuto, tempo de
render, taxa de falhas, cache hit) são a versão verificável do que o Dotti mostra como plano.
O que se leva do Dotti é a **clareza** de expor custo e volume; **não** se copia número,
plano nem promessa de "quantos vídeos por dia" que a gente não mediu.

## 9. Métricas de sucesso

As do §10 do pedido, com uma correção de honestidade: as metas são **alvo a medir por
benchmark**, não promessa. Registrar custo por minuto, tempo de render, taxa de falhas,
cache hit e correções humanas **por plano**, com o rótulo Real/Estimado.

## 10. Em aberto (só você decide)

1. **fps de saída: manter 25 ou ir para 30?** Muda QA e comparação com vídeos antigos.
   Default que eu adotei: manter 25 até haver motivo medido para mudar.
2. **A fundação entra antes ou depois de D2/Publicação?** Ela melhora qualidade de vídeo, mas
   D2 destrava o fluxo ponta-a-ponta. Minha recomendação: fatias 1–2 em paralelo com D2, e
   3–6 depois.
3. **Trocar `render_ffmpeg.py` de uma vez ou manter os dois por flag?** §11 manda manter os
   dois. Confirme se aceita o custo de manter dois caminhos até a comparação.

---

**Decisão:** construir o `RenderPlan` como linguagem comum do audiovisual, **reusando** o
`beat_plan`/`evaluate_qa`/`production_run` já fechados, sem reescrever a fatia B e sem
derrubar o renderer legado. Implementação **depois** que A, C, D2 e G1 fecharem.
