# Status de execução — F0–F11 e Render Plan

**Data:** 2026-11-20
**Base:** `main` local com todas as fatias mescladas (`f909695`): F0, A, C, D, D2, F3-07, F4-duração,
F5-domínio, ContentBrief, F9-04, F7, F6, G1, G1b, RP-00..RP-02, RP-04, e as fatias **G** (wizard +
execução), **E** (long-form + roteiro), **H** (canais/providers/budget/segredos) e o protótipo UX.
**Método:** cada linha abaixo foi cruzada com commit e/ou revisão independente. Onde a evidência
é uma medição, o número está citado. **O `gestao/BACKLOG-MESTRE.md` marca "A fazer" em todos os 95
cards** — ele nunca foi atualizado; esta é a leitura real.

Legenda: **✅ feito** (com evidência) · **◐ parcial** (contrato/domínio feito, falta o resto) ·
**❌ pendente** · **🔒 bloqueado** (depende de terceiro ou de autorização) · **🚫 adiado** (decisão).

---

## F0 — Higiene, segurança, baseline e documentação (P0)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F0-01 rotacionar tokens expostos | ❓**não verificável por mim** | ação operacional sua; não há como eu provar rotação pelo repo |
| F0-02 `package-starter.sh` com allowlist | ✅ | commits `9a79e58`, `b8691b0`, `f8eefe6` |
| F0-03 secret scanning no CI + teste do ZIP | ◐ | scanner **heurístico** local + teste que inspeciona o ZIP; **CI remoto nunca executado** |
| F0-04 inventário de rotas/providers/capacidades | ◐ | `docs/superpowers/plans/2026-11-20-rp00-baseline-render-pipeline.md` cobre o fluxo de render; **não** é o inventário completo de rotas/providers |
| F0-05 reconciliar README/docs | ◐ | docs do Studio escritos; README raiz não auditado por mim |
| F0-06 baseline de testes/migrations/custo/cobertura | ◐ | baseline de testes existe e roda; **fixture de 8 min não existe** |
| F0-07 flags e rollout progressivo V2 | ❌ | — |

## F1 — Production Coordinator, checkpoints e recuperação (P0)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F1-01 `ProductionRun`/`StageExecution`/outbox + migrations | ✅ | slice D, `3a7bb8d` + `0018_production_runs.sql` |
| F1-02 DAG de estágios e contratos I/O | ✅ | slice D (validação topológica, testes de ciclo) |
| F1-03 `ProductionCoordinator` + executor port | ❌ | fatia **D2** (não iniciada) |
| F1-04 `POST production-runs` + status + eventos | ❌ | fatia D2 |
| F1-05 handlers de todas as etapas | ❌ | fatia D2 |
| F1-06 idempotency key, CAS, lease, heartbeat, fencing, checkpoint, replay | ✅ | slice D (verificado com 10 corridas; chave ASCII canônica com CHECK) |
| F1-07 pausa humana persistida | ◐ | `WAITING_HUMAN` sem lease existe e é testado; falta o fluxo ponta-a-ponta |
| F1-08 retry seletivo, cancelamento, DLQ, auditoria | ◐ | revogação de estágios em D; DLQ/cancelamento não |
| F1-09 testes de falha e concorrência entre 2 workers | ◐ | concorrência testada em D; falta o ensaio de falha ponta-a-ponta |
| — *guard de custo (F1-05/F1-03 orçamento)* | ✅ | fatia A: `ESTIMATE`/`ACTUAL`/`FREE`, `ACTUAL` exige evidência, 403/409/404/422 |

## F2 — UX do fluxo único, painel e acompanhamento (P0)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F2-01 mapa de navegação, wireframes, estados vazios | ✅ | `produto/mockup-proposta.html` **aprovado** + `JORNADA-E-TELAS.md` |
| F2-02 wizard `Novo vídeo` | ✅ | fatia **G** `a217365` (`api/panel_production.py`); Tema/Canal/Formato reais, resto desabilitado **com motivo em texto** |
| F2-03 botão `Produzir vídeo` → Coordinator | ✅ | fatia G — cria o vídeo e chama o coordinator D2 com `Idempotency-Key` |
| F2-04 página de execução (stepper, próxima ação, custo) | ✅ | fatia G `a217365` — stepper real por run, "etapa N de M" **sem barra/percentual**, custo rotulado |
| F2-05 ações pausar/continuar/cancelar/revisar | ✅ | fatia G — ações condicionadas ao estado (retry só em `FAILED`) |
| F2-06 lista `Vídeos` por estado + filtros | ◐ | G1 entregou lista; filtros `precisa de mim`/`em andamento` não completos |
| F2-07 mover IDs/traces/model usage para avançado | ✅ | G1 (`<details>` fechado) |
| F2-08 acessibilidade, responsividade, E2E com operador | ◐ | G1: responsivo + a11y estática; **sem validação em navegador/leitor de tela** |
| — *rótulos de custo real/estimado* | 🔄 | G1b em andamento (dado existe; `panel_repo.month_usage` não buscava a coluna) |

## F3 — Tendências → research → fontes verificáveis (P0)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F3-01 `ContentBrief` versionado | ✅ | `aad4391` |
| F3-02 transportar evidências para research | ❌ | — |
| F3-03 `ResearchPort` | ❌ | — |
| F3-04 canonicalizar URLs + `SourceSnapshot` | ◐ | contrato `SourceSnapshot` existe (`contracts/v1/sourcesnapshot.schema.json`); portas não |
| F3-05 avaliar fonte (data, reputação, claims) | ❌ | — |
| F3-06 UI de fontes | ❌ | — |
| F3-07 rotulagem de região (`US` → EUA) | ✅ | `165c708`, `93a0b6f`, `663f720` |
| F3-08 custos/cotas YouTube + throttle | ❌ | — |

## F4 — Motor editorial long-form e aprovação de roteiro (P0)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F4-01 expandir briefing | ✅ | ContentBrief + fatia F4-01 |
| F4-02 prompt short vs long (estrutura por blocos) | ✅ | fatia **E** `cc24b23`/`159a212` (`build_prompt_for_format`) |
| F4-03 estimativa palavras/minuto e duração por cena | ◐ | fatia E `estimate_text_durations`; **calibração TTS real continua pendente** |
| F4-04 roteiro em duas passagens | ✅ | fatia E `159a212` — plano de capítulos → cenas com citações |
| F4-05 validar continuidade/redundância/claims | ✅ | fatia E — reusa `facts.check_narration`; estrutura, continuidade, redundância e invenção |
| F4-06 versionar scripts + aprovação por hash | ✅ | fatia E `c7de848` — aprovação presa a `(versão, hash)`; editar cria versão nova e invalida |
| F4-07 tela de editar/regerar cenas | ✅ | fatia E `7d9e841` — tela de Roteiro aprovada; edição só em `IDEA`/`SCRIPTED` |
| F4-08 edição invalida só downstream | ✅ | fatia E — grafo de dependências no domínio + efeitos persistidos |
| F4-09 teste de roteiro ~480 s | ✅ | fatia E — 3 temas/estilos, determinístico/offline |

## F5 — Motor audiovisual, mídia e montagem dinâmica (P1)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F5-01 `VisualBeat` | ✅ | slice F5 domínio (`cce36a4`, `d6053aa`, `e816da6`); ~34k casos de fuzz |
| F5-02 1:N beats por cena e tipos de mídia | ◐ | contrato pronto; **sem produtor nem persistência** |
| F5-03 `MediaProviderPort` + capability registry | ❌ | — |
| F5-04 stock primeiro, IA quando agrega | ◐ | adapters de imagem existem; política não |
| F5-05 storyboard define duração/beat/safe area | ❌ | — |
| F5-06 render FFmpeg para beats múltiplos | ❌ | **RP-05** (fatia 6) |
| F5-07 regeração granular + cache por conteúdo | ❌ | **RP-06** (fatia 7) |
| F5-08 auditoria de licença/proveniência | ❌ | `VisualBeat` **não** verifica licença (documentado) |
| F5-09 perfis `economy`/`balanced`/`premium` | ❌ | — |
| — *RP-00 baseline* | ✅ | fatia 1, `17886db` |
| — *RP-01 contrato canônico* | 🔄 | fatia 2 em andamento |

## F6 — Editor visual, preview e QA (P1)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F6-01 player + timeline por cena | ❌ | — |
| F6-02 editor de narração/legenda por formulário | ❌ | — |
| F6-03 trocar asset/voz e regerar versão | ❌ | depende de RP-06 |
| F6-04 QA técnico (codec, áudio, duração, preto) | ◐ | `domain/render.evaluate_qa` existe; falta o `QualityEvaluator` como porta |
| F6-05 QA editorial (claims, pronúncia, ritmo) | ❌ | — |
| F6-06 severidade `blocking`/`warning`/`info` | ✅ | slice F6 (`aae03ad`, `4065888`, `9332f47`) |
| F6-07 aprovação exige `render_id`/checksum | ✅ | slice F6 |
| F6-08 regressão visual e de mídia | ❌ | — |
| — *gate de QA ligado à publicação* | ❌ | limitação registrada: o gate **não** está ligado ao fluxo de publicação |

## F7 — Thumbnails, títulos, SEO e experimentos (P1)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F7-01 `PackagingAgent` (contrato) | ✅ | `f3f800e`, `eb707a1`, `1ab364a` |
| F7-02 3 conceitos de thumbnail/títulos | ◐ | contrato sim; geração de imagem real não |
| F7-03 templates gráficos por canal | ❌ | — |
| F7-04 review UI de variantes | ❌ | — |
| F7-05 persistir versão escolhida | ◐ | `decisions`/`variant_id` no contrato; UI não |
| F7-06 validar dimensões/regras da API YouTube | ❌ | — |
| F7-07 testes de conteúdo enganoso/sem licença | ✅ | slice F7 (NFKC, `SafeText`, anti-clickbait com `title_claim`) |

## F8 — Publicação YouTube resiliente, OAuth e agenda (P0)

Todos **❌ pendente** (fatia **F**, não iniciada). F8-07 (`reabilitar workflow automático`) está
🔒 **bloqueado** até haver testes de falha/concorrência e autorização específica.

## F9 — Analytics e loop de aprendizado (P2)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F9-01 conectar dados às versões | ❌ | — |
| F9-02 coletar métricas autorizadas | ❌ | fatia **I** — **autorizada**; tela de Analytics aprovada |
| F9-03 dashboard por canal/vídeo/pilar | ❌ | fatia I — tela aprovada (`produto/tela-analytics.html`) |
| F9-04 insights com evidência e confiança | ✅ | `cbda7df`, `96edd7a` |
| F9-05 recomendar temas/formatos | ❌ | fatia I — recomendações **não** reconfiguram nada sozinhas |
| F9-06 histórico de experimentos | ❌ | — |

## F10 — Gerenciamento de canais, estratégias e providers (P1)

| Card | Status | Evidência / o que falta |
|---|---|---|
| F10-01 CRUD de canais/projetos, pilares | ◐ | fatia **H** `35c4947` completou o **HTTP**; **falta a UI** (fatia **H-UI**, aprovada) |
| F10-02 `ChannelProfile` versionado | ✅ | `6b9128c`, `c175a2a`, `bb0d108`, `78667e3` |
| F10-03 providers com capabilities | ✅ | fatia H — `GET/POST .../providers[/test]`; `AVAILABLE` só com implementação validada, senão `UNAVAILABLE` **com motivo** |
| F10-04 profiles econômicos e roteamento | ✅ | fatia H — `ECONOMY`/`BALANCED`/`PREMIUM` + `route_provider` com fallback controlado |
| F10-05 budget por canal, limites hard/soft | ✅ | fatia H — `BudgetLimits` com hard/soft **distintos**, ligados ao guard (`limits_for`) |
| F10-06 associar canal YouTube + status OAuth | ◐ | fatia H — associação e status derivado; **OAuth real (troca/refresh) não implementado** |
| F10-07 secrets em vault, não no `Project.config` | ✅ | fatia H — `FileSecretStore` (0700/0600) + `sanitize_project_config`; teste prova a ausência do segredo |

## F11 — Preparação SaaS, multiusuário e BYOK (P2)

**🔓 desadiada por decisão do usuário em 2026-11-20** — a fatia **F11** está autorizada (9 cards).

Escopo: membros, papéis (`owner`/`editor`/`reviewer`/`viewer`), tenants, chaves BYOK
(**máscara, nunca o valor**) e consumo. Tela de Equipe aprovada (`produto/tela-equipe.html`).

| Card | Status | Evidência / o que falta |
|---|---|---|
| F11-01…09 | ❌ | fatia **F11** autorizada; escopo acima |

---

## Render Plan (F5-RP, `docs/backlogs/writing-block.md`)

Este é o trabalho que o usuário pediu para iniciar **após** as fatias atuais. Ele **não** está no
`BACKLOG-MESTRE` (que lista só F0–F11) — é um backlog adicional de 32 itens (RP-001…RP-032) em 8
fases (RP-00…RP-07).

| Fase RP | Status | Evidência |
|---|---|---|
| RP-00 baseline e compatibilidade | ✅ | fatia 1, `17886db` (RP-001/002 + proposta RP-004) |
| RP-01 contrato canônico | ✅ | fatia 2 — `89f45fc`, `c73f7fb`, `3b3e123`, `c466d4a` |
| RP-02 timeline e sincronização | ✅ | fatia 3 — `eadb938`, `5e1e0ed`, `ad2f8b2` |
| RP-03 builder | ❌ | **fatia 4** — próxima; depende de C (✅) |
| RP-04 asset resolver | ✅ | `9e6387b` — porta `AssetResolver`, manifesto com `content_sha256` próprio (C1), validação multi-asset |
| RP-05 FFmpeg adapter | ❌ | fatia 6 — **a medição real de vídeo (ffprobe) fica aqui** |
| RP-06 regeneração seletiva | ❌ | fatia 7 (depende de D2, ✅) |
| RP-07 QA e rollout | ❌ | fatia 8 |

Design aprovado para seguir: `docs/superpowers/specs/2026-11-20-render-plan-foundation-design.md`
(com as decisões R1–R7 e as correções C1–C4 vindas da baseline).

---

## UX é gate, não preferência

As 7 regras canônicas de `produto/JORNADA-E-TELAS.md` estão consolidadas em
`tests/test_ux_contract.py` (`assert_ux_contract`), para toda fatia de UI de agora em diante:
três estados sempre com **texto** (glifo não conta), item indisponível **não focável**, ausência
de custo **nunca** `US$ 0,00`, sem stack trace para o operador, avançado **fechado por padrão**,
viewport + media query, um único `<h1>`, sem barra de progresso afirmando linearidade, e
**nenhum texto ilustrativo do mockup vazando** para o produto. Cada regra tem sonda própria que
prova que a checagem morde.

## Aprovações do usuário (fonte de verdade de design)

| Data | Artefato | Escopo da aprovação |
|---|---|---|
| 2026-11-20 | `produto/mockup-proposta.html` | linguagem visual do painel (slice G1) |
| 2026-11-20 | `produto/` (todos os mockups) | **toda a pasta**: 8 telas da jornada em `mockup-telas.html` + PNGs (`tela-*.png`, desktop e mobile) + `JORNADA-E-TELAS.md`. Passa a ser a referência visual de **todas** as fatias de UI (G, H e as telas seguintes) |
| 2026-11-20 | `produto/tela-canais.html` (+PNG) | **tela de Canais aprovada** — deixa de ser `em breve`; **destrava a UI da fatia H** |
| 2026-11-20 | `produto/tela-analytics.html` (+PNG) | **tela de Analytics aprovada** — libera a fatia **I** (F9-02/03/05) |
| 2026-11-20 | `produto/tela-equipe.html` (+PNG) | **tela de Equipe aprovada** — libera a fatia **F11** |
| 2026-11-20 | decisão de escopo | **F11 (SaaS/multiusuário/BYOK) desadiada** — o usuário reverteu o adiamento; os 9 cards estão autorizados |

**Consequência prática:** qualquer fatia de UI daqui para frente implementa o que está aprovado
em `produto/`. Onde o mockup mostra dado ilustrativo, o painel real renderiza **dado real** ou
**estado vazio explícito** — nunca o texto de exemplo.

## Resumo por fase

| Fase | Feito | Parcial | Pendente/Adiado |
|---|---|---|---|
| F0 | 1 | 4 | 2 |
| F1 | 6 | 3 | 0 |
| F2 | 6 | 2 | 0 |
| F3 | 2 | 1 | 5 |
| F4 | 8 | 1 | 0 |
| F5 | 1 (+RP-00/01/02/04) | 2 | 6 |
| F6 | 2 | 1 | 5 |
| F7 | 2 | 2 | 3 |
| F8 | 0 | 0 | 8 (1 bloqueado) |
| F9 | 1 | 0 | 5 |
| F10 | 5 | 2 | 0 |
| F11 | 0 | 0 | 9 (autorizados) |

**As três maiores lacunas, em ordem de impacto:**
1. **F8 — Publicação YouTube** (8 cards, P0): nenhum iniciado, e é P0. Sem ela não há loop real
   (publicar → medir → aprender) nem o analytics da fatia **I** tem dado de onde coletar.
2. **F3 — research e fontes verificáveis** (5 de 8 pendentes): o roteiro long-form já existe (fatia E),
   mas sem fonte verificável ele não cumpre o "sem invenção" do gate de fact-check.
3. **F5 / RP-05 — motor audiovisual real** (beats múltiplos, FFmpeg): RP-05 é onde a medição real de
   vídeo acontece; hoje o `AssetResolver` valida vídeo por metadado **declarado**, não medido.

**Baseline:** `main` local com 1924 passed, 35 skipped, 0 failed (o gate de higiene voltou a passar
após `7f248cd`, que corrigiu falsos positivos do scanner em código de canal/segredos).

**Nada aqui foi publicado.** `main` local tem tudo; o remoto não foi tocado (sem push).
