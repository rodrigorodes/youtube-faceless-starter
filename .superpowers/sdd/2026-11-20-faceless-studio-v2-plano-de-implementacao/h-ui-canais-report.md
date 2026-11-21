# Fatia H-UI — tela de Canais (F10) consumindo o backend da fatia H

**Worktree:** `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/h-ui-canais`
**Branch:** `feat/h-ui-canais` (base `e83af72`)
**Fonte de verdade visual:** `produto/tela-canais.html` (+ `tela-canais.png`), aprovada em 2026-11-20.
**Casca:** `render_sidebar(...)` de `renderer/app/studio/api/panel.py` (G1, `468b56a`).
Sem push e sem merge. Só caminhos exatos; nenhum `git add -A`.

**Commits desta fatia:**
- `a2b42a8` `feat(ui): tela de Canais consumindo providers, perfil, budget e OAuth da fatia H (F10)`
- `597536f` `test(ui): contrato de UX, honestidade de estado e casca da tela de Canais (F10)`
- `d4f9fbc` `fix(ui): texto do estado antes do ícone na tela de Canais (contrato R1)`
- `5fe6df2` `docs(h-ui): relatório da tela de Canais e divergências do mockup`
- `refactor(ui): Canais deixa de ser item indisponível e vira link na casca` (topo; revisa este relatório)

## O que foi entregue

Tela nova em `GET /studio/canais?project_id=…` (HTML, CSP+nonce, `no-store`), na casca aprovada
(`<nav class="nav" aria-label="Principal">`), com dado real do backend da H e estado vazio explícito:

- **Identidade/estratégia** — `GET/POST/PATCH` de `ChannelProfile`: nome, estratégia, idioma, público,
  pilares, identidade visual e voz. Cada save cria versão auditável (`channel_vN` real). O nicho do
  projeto é mostrado **somente leitura** (o backend não o expõe como campo do perfil).
- **Providers por tarefa** — `GET /providers` (uma porta por `ProviderKind`: Roteiro/Imagens/Voz/Render)
  com `capabilities`, custo (`Sem custo` / `Estimado US$ …` / `Desconhecido`), rate limit, disponibilidade
  e **motivo** quando `UNAVAILABLE`. `POST /providers/test` pelo botão “Testar conexão”, que só afirma o
  que a sonda mediu (`checked`, `available`, `reason`).
- **Roteamento econômico** — `POST /providers/route` por porta, derivado do `economic_profile` persistido
  do canal; porta sem candidato vira motivo explícito (`NoProviderAvailable`), nunca provider inventado.
- **Budget do canal** — `GET/PUT /budget`: limites **hard/soft mensal** e **por vídeo** (soft ≤ hard),
  resumo honesto (Real/Estimado/Sem custo/Desconhecido, jamais fundidos) e decisão mensal
  (WITHIN / SOFT_LIMIT / HARD_BLOCKED). Sem linha persistida, a tela diz que valem os tetos padrão do
  servidor e não inventa configuração do canal.
- **Canal do YouTube** — `GET /youtube-channel`: status OAuth (CONNECTED/EXPIRED/REVOKED/ERROR/
  DISCONNECTED), canal, escopos e expiração. **Nenhum** token, client secret ou máscara de segredo
  aparece — o backend não devolve o valor.
- **Config sanitizada** — `GET /config` (lista branca) dentro do `<details class="advanced">` fechado,
  junto de IDs/versão/expiração/uso não atribuído.
- **Casca** — “Canais” deixou de ser item indisponível e passou a **link real** em toda a casca
  (`render_sidebar(..., channels_href="/studio/canais")`, default); o item atual fica com
  `aria-current="page"`. “Analytics/Equipe/Configurações” seguem `<span aria-disabled tabindex="-1">`
  (não focáveis). Painel e telas de produção passaram a apontar para a tela de Canais.

Arquivos: `application/channels_page.py` (projeção pura sobre os casos de uso da H),
`api/panel_channels.py` (renderer), `api/routes.py` (rota), `application/use_cases.py` +
`composition.py` (fiação), `api/panel.py`/`api/panel_production.py` (link de nav),
`tests/test_channels_page.py` (+ ajustes em `tests/test_panel.py` e `tests/test_panel_page.py`).

Sem migração: a fatia é UI e usa as tabelas/rotas já existentes (nenhum `0025_` foi preciso).

## Regra crítica de UX

`assert_ux_contract(html, *, page=...)` de `tests/test_ux_contract.py` é aplicado à tela em dois estados
(vazio e com perfil/budget/YouTube/uso reais) e ao estado “sem canal cadastrado”:
`test_channels_empty_state_satisfies_the_ux_contract`,
`test_channels_page_with_real_data_satisfies_the_ux_contract` e
`test_channels_page_without_any_project_is_explicit` → **PASS**. Antes de existir a rota, os mesmos
testes eram `RED` (404). Cobre: estados sempre com texto, item indisponível não focável,
ausência de custo nunca `US$ 0,00`, sem stack trace, `<details>` avançado fechado, viewport + media query,
um único `<h1>`, sem barra de progresso e **nenhum texto ilustrativo do mockup**. Um teste extra
(`test_channels_state_badges_carry_real_text_not_only_an_icon`) exige o **texto do rótulo dentro do
badge**, não só o ícone.

Decisões de honestidade que o contrato não pega sozinho, mas os testes cobrem:
- “Testar conexão” de provider indisponível é `<span aria-disabled tabindex="-1">`, sem `<button>`;
- “Reordenar fallback” e “Reautorizar” são não focáveis, com motivo em texto — não há backend para eles;
- custo desconhecido e zero de limite são ditos por extenso (`US$ 0 (bloqueia operação paga)` /
  `US$ 0 (nenhum gasto projetado)`), nunca `US$ 0,00`.

## Divergências: mockup aprovado × o que o backend entrega

1. **Nicho** — o mockup tem `<input id="nicho">` editável; o backend guarda nicho no `Project` (só na
   criação) e não o expõe como campo do `ChannelProfile`. A tela mostra o nicho real **desabilitado**,
   com o motivo (“definido na criação do canal”).
2. **Custo por “1k tokens” (US$ 0,02)** — não existe preço por token no catálogo. O custo real vem de
   `CostEstimate`: `Sem custo` (local), `Estimado US$ …` (por imagem/segundo) ou `Desconhecido`.
3. **Providers nomeados** — o mockup lista “OpenAI gpt-5-mini”, “Stock local (Pexels)”, “Piper”. O
   catálogo é derivado de `Project.config` + implementações registradas (`demo`, `opencode`,
   `placeholder`, `stock`, `veo`, `piper`, `ffmpeg`) e marca UNAVAILABLE com motivo quando falta
   credencial/homologação — ex.: imagem `opencode` sem `OPENCODE_BRIDGE_TOKEN`.
4. **Limites de orçamento** — o mockup tem só soft/hard mensais; o backend tem hard/soft mensal **e por
   vídeo** mais `economic_profile`. A tela mostra os quatro limites reais.
5. **Consumo ilustrativo (0,07 / 0,05 / 3 / 1)** — o painel usa `usage_ledger` do mês; sem uso diz
   “Sem registro de uso”. Chamadas sem vínculo de vídeo aparecem à parte e **não** entram no gasto.
6. **Máscara de credencial (`•••• … 7f2a`) e “renovação automática / expira em 51 min”** — o backend
   não devolve valor nem prefixo de token; não há refresh. A tela mostra apenas estado, escopos e a
   expiração registrada, e diz explicitamente que nenhum valor de credencial volta ao browser.
7. **“Reautorizar” (diálogo de consentimento)** — o OAuth real (troca de código e refresh) **não** está
   implementado na H. O controle é um `span` desabilitado com o motivo; a associação é feita pela API.
8. **“Adicionar canal”** — implementado como `<details>` que cria um projeto (`POST /studio/projects`),
   pois canal = projeto no backend; nada de `.env`.
9. **Navegação** — o mockup tem uma lista própria de 9 itens; a casca aprovada (G1) tem grupos
   Operação/Indisponível. Mantivemos a casca e promovemos só “Canais” a link real.

## Validação

Postgres descartável próprio: container `hui-pg`, rede `hui-net`, `--tmpfs /var/lib/postgresql/data` e
`--tmpfs /budget-test-proof` com a prova de 64 hex lida por `pg_read_file('/budget-test-proof/proof')`.
`STUDIO_TEST_DSN`, `STUDIO_BUDGET_DISPOSABLE_DSN` e `STUDIO_BUDGET_TEST_PROOF_FILE` passados juntos
(sem as duas DSNs, ~100 testes de orçamento são pulados em silêncio).

Números da suíte no fim deste relatório (rodada serializada).

## Números reais (Postgres próprio `hui-pg`)

Rodada serializada em **4 partições de arquivos** (mesma imagem `faceless-v2-hygiene-test-local:latest`,
mesmo container/DSN), porque a rodada única de 1.985 testes foi morta por OOM do host (17 containers e
load ~35 de outras fatias) em 54%, **sem nenhuma falha até ali**:

| Partição | passed | skipped | failed |
|---|---|---|---|
| 1 (25 arquivos) | 412 | 0 | 0 |
| 2 (25 arquivos) | 625 | 0 | 1 |
| 3 (25 arquivos) | 550 | 1 | 2 |
| 4 (25 arquivos) | 358 | 34 | 2 |
| **Total** | **1945** | **35** | **5** |

- 35 pulados: **todos por Node.js ausente na imagem** (34 testes de workflow + 1 filtro JS do painel).
  **Nenhum teste de orçamento foi pulado** — `STUDIO_TEST_DSN` e `STUDIO_BUDGET_DISPOSABLE_DSN` foram
  passados juntos, e `test_budget_*`/`test_paid_operations`/produção rodaram de verdade.
- 5 falhas episódicas, **todas qualificadas**:
  - 3 passam isoladas nesta mesma configuração: `test_media_api::test_unknown_or_unconfigured_image_provider_is_422`
    e 2 de `test_publish_api` (estas são a flakiness conhecida sob carga) — 2 passed em 18 s ao rodar só elas.
  - 2 de `test_secrets_hygiene` (empacotamento) falham só na worktree: dentro do container o `.git` é um
    *gitfile* apontando para fora do mount e o script aborta com “could not complete safely”. Na rodada
    por partição `test_render_adapters` passou inteiro; numa repetição posterior sob OOM do host, o
    `ffmpeg` foi morto (`returncode -9`) — evidência de memória, não de código.
- Higiene: `python3 scripts/secret_hygiene.py scan` na worktree → **“Secret hygiene check passed.”**
  (rodado antes de cada commit, inclusive com os arquivos já staged).
