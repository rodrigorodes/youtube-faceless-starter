# Fatia I — Analytics e loop de aprendizado (F9-01, F9-02, F9-03, F9-05, F9-06)

Worktree: `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/i-analytics`
Branch: `feat/i-analytics` · base `e83af72`
F9-04 (`cbda7df`, `96edd7a`) foi reusado, não duplicado.

## O que foi entregue

| Card | Entrega real |
|---|---|
| F9-01 | `VersionAttribution` liga cada medição a roteiro (FK composta para `scripts(video_id, version)`), publicação e id remoto. Briefing e embalagem ainda não são persistidos: cada ausência vira `MissingVersionLink` com motivo explícito, nunca versão inventada. Id remoto sem publicação local é recusado. |
| F9-02 | Porta `AnalyticsCollectionPort` + `CollectMetrics` + `YoutubeAnalyticsAdapter` + `ChannelAnalyticsAdapter`. Escopo exigido: `yt-analytics.readonly`. Sem canal associado, escopo, token, publicação ou id remoto, a coleta **não chama a API** e devolve prontidão/motivo. Resposta é validada (uma linha, finita, não negativa, percentual 0..100). |
| F9-03 | `BuildAnalyticsDashboard` + tela `GET /studio/panel/analytics`: canal, vídeo, pilar e período (7/28/90 dias). Short e long-form nunca somados; métrica aditiva só com cobertura completa; taxa nunca vira média de médias; origem mista vira `origem desconhecida`. |
| F9-05 | Recomendação derivada de views medidas por pilar+formato, somente com **3+ vídeos comparáveis**, confiança declarada **baixa** e `requires_human_review=True`/`auto_applied=False`. `POST .../recommendations/{id}/decision` registra `accepted_for_review` ou `rejected`; nunca altera canal. |
| F9-06 | Histórico de experimentos de thumbnail/título em `analytics_experiments`/`analytics_experiment_variants`, com conclusão como hipótese não verificada. `platform_ab_supported` é travado em `false` no domínio e no banco: a API do YouTube Analytics não oferece A/B nesta integração; o registro é de rotação manual aprovada. |

## Peças

- Domínio puro: `renderer/app/studio/domain/analytics_learning.py`.
- Aplicação: `application/analytics_ports.py`, `analytics_collection.py`, `analytics_dashboard.py`, `analytics_learning.py`.
- Adaptadores: `adapters/youtube_analytics.py` (HTTP injetável), `adapters/channel_analytics.py` (escopo/token do vínculo + cofre), `adapters/postgres/analytics_learning_repo.py`.
- UI: `api/panel_analytics.py` (casca `render_sidebar`, tokens/CSS de `api/panel.py`).
- Migração aditiva: `0026_analytics_learning.sql` (reservada para esta fatia; 0024/0025/0027 não usados). `tests/test_db.py` atualizado nas **duas** listas e na lista de tabelas.
- Rotas: `GET /studio/panel/analytics`, `POST /studio/panel/analytics/recommendations/{id}/decision`, `POST /studio/analytics/collect`, `POST /studio/analytics/experiments`.
- Navegação: Analytics saiu de "em breve" e passou a link real na casca; `tests/test_panel.py` e `tests/test_panel_page.py` foram ajustados para a mudança (não é mascaramento: o item deixou de ser indisponível).

## Regras de honestidade provadas por teste

- Zero medido é `0.0`; ausência é `value=NULL` + `unavailable_reason` (domínio e CHECK do banco).
- `origem desconhecida` é o rótulo de origem não confiável; `origin_label("Global")` levanta erro e a tela nunca imprime "Global".
- Cobertura é explícita: `aggregate_metric` recebe o número de vídeos do recorte. Uma taxa de 1 vídeo entre 3 não vira "1 de 1" — o caso está coberto por teste.
- Soma aditiva recusada com cobertura parcial (ex.: 2 de 3 vídeos).
- Recomendação sem amostra mínima não é gerada; a tela mostra a regra e o vazio.
- Decisão de recomendação não toca `channel_profiles` (verificado por contagem antes/depois no Postgres).

## Contrato de UX

`assert_ux_contract` aplicado à página vazia, à página com medição e à página com experimento:

- estados sempre com texto (glifo não conta), item indisponível é `<span>` não focável;
- ausência de custo nunca `US$ 0,00`; sem barra de progresso; `<details>` fechado; um `<h1>`; viewport + media query; sem stack trace;
- nenhum texto ilustrativo do mockup ("1,2 mi views", "840 mil views", "run_7f31", "Finanças Descomplicadas") e nenhum "dados ilustrativos";
- tela acessível por `/studio/panel/analytics`, com `aria-current="page"` em Analytics e filtros reais.

## Dependência de F8 (indisponível de propósito)

F8 (publicação no YouTube) ainda não existe. Por isso, no produto real:

- não há `youtube_video_id` preenchido por publicação; a coleta retorna `collected=false` com motivo "nenhuma publicação autorizada/coletada";
- Views, CTR, retenção e tempo assistido aparecem como **Ainda não disponível**, com o motivo, em vez de número;
- "Última coleta" é **nunca**; "Escopo de leitura" reflete o vínculo real (hoje `não concedido` na ausência de OAuth);
- o fluxo OAuth de refresh continua fora desta fatia (F10 associa metadados/tokens, mas não troca código nem renova token). Mesmo com F8, token expirado deixa a prontidão em `não conectado`.

Também indisponível por falta de persistência anterior (não é F8):

- versão de briefing e de embalagem: contrato F3/F7 é domain-only, então a atribuição declara `brief`/`packaging` ausentes com motivo;
- vínculo persistente vídeo→pilar: `project_categories` existe, mas o vídeo não tem coluna de pilar. A observação carrega `pillar_id` apenas quando o coletor recebe um pilar válido do projeto; sem isso, a tela escreve "Pilar não registrado" (não deduz do tema).

A/B de thumbnail/título: a API do YouTube Analytics não expõe experimentos; o histórico é de rotação manual aprovada, com conclusão marcada como hipótese (`unverified`).

## Onde o mockup divergiu do produto

1. Chip "Canal: Finanças Descomplicadas" virou `<select>` com os canais/projetos reais.
2. Chips de vídeo/pilar viraram `<select>` com listas reais (o produto tem mais de uma opção).
3. "Atualizar agora" virou "Atualizar dados salvos": sem coleta pronta, um botão que finge coletar seria mentira; ele relê o banco.
4. O `<details>` de exemplo com números ilustrativos virou prosa sobre o layout; nenhum número de exemplo embarca.
5. Insights de exemplo viraram geração real (views por pilar+formato) apenas com 3+ vídeos comparáveis; sem amostra, vazio explícito.
6. "Aplicar (abre confirmação)" virou "Aceitar para revisão"/"Recusar": aplicar exige edição manual em Canais (tela ainda não disponível). A decisão é auditada e não reconfigura nada.
7. Foram acrescentados "Desempenho por vídeo", "Por pilar e formato" e "Histórico de experimentos" — exigidos por F9-01/03/06 e ausentes no mockup.
8. CTR/retenção por pilar nunca aparecem como média; aparecem por vídeo ou quando há um único vídeo comparável.
9. O rodapé "Tela 10 de 12 · dados ilustrativos" não existe na página real.

## Limitações assumidas

- Histórico de experimentos é append-only por registro: não há PATCH para mudar status de um experimento já gravado; um novo estado gera outro id determinístico (o id inclui status/janela/conclusão). Documentado, não mascarado.
- Decisão de recomendação é keyed pelo id determinístico; um id desconhecido é aceito como registro de revisão e não tem efeito na tela. O id é reprodutível a partir dos dados (não é conteúdo forjável que altere o canal).
- `analytics_recommendation_decisions.evidence` fica `[]`: a evidência é reconstruída pelo id determinístico + dados atuais, não é snapshot.
- Recomendações são descritivas (views por pilar+formato), não causais; confiança sempre baixa com base declarada. Não há recomendação automática de hook/pacing a partir de CTR/retenção porque não há amostra controlada.
- O adaptador HTTP real não foi exercitado contra o YouTube (sem credenciais); é testado com cliente injetado.
- A listagem de vídeos do dashboard carrega no máximo 500 por projeto.
- Janelas não são fatiadas: uma observação coletada para 28 dias não aparece no recorte de 7 dias. A página informa que existe coleta registrada, mas nenhuma observação cobre exatamente a janela; não derivamos um recorte menor de um agregado.
- Cada operação do repositório abre uma conexão (padrão dos adaptadores existentes); os testes de integração são lentos por isso.

## TDD e contagens reais

Arquivos novos de teste (94 casos): `test_analytics_learning.py` (26), `test_analytics_collection.py` (19), `test_analytics_dashboard.py` (19), `test_analytics_repo.py` (16), `test_analytics_page.py` (14).

Postgres próprio: container `i-pg`, rede `i-net`, `--tmpfs /var/lib/postgresql/data`, prova de 64 hex em `/budget-test-proof/proof` (lida por `pg_read_file` dentro do container e comparada pelo runner). Passadas **as duas** variáveis (`STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN`) + `STUDIO_BUDGET_TEST_PROOF_FILE`.

### Suíte completa (serializada, Postgres próprio, ambas as DSNs)

Comando na imagem `faceless-v2-hygiene-test-local:latest`, `-p no:cacheprovider`, no HEAD
`a9cf482`, com `STUDIO_TEST_DSN` **e** `STUDIO_BUDGET_DISPOSABLE_DSN` apontando para `i-pg`
(network `i-net`) e a prova montada read-only:

**2017 passed, 3 failed, 35 skipped** em ~4,5 min. Os 35 skips são Node.js/ambiente (o mesmo
número das fatias que rodaram com banco), ou seja, os ~100 testes de orçamento **não** foram
pulados.

Falhas (nenhuma em código desta fatia):

- `tests/test_publish_api.py::test_qa_failed_video_is_approved_only_with_a_recorded_override`
  — flakiness conhecida sob carga (render ffmpeg): passa isolado no mesmo tree (1 passed,
  2,5 s). Em execuções cheias anteriores a mesma família caiu e voltou.
- `tests/test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable`
  e `::test_extracted_starter_runs_contract_snapshot_and_backup_import` — dependem de gitdir
  real; dentro do container o `.git` da worktree é gitfile e o scanner aborta
  ("Secret hygiene check could not complete safely"). Fora do container,
  `python3 scripts/secret_hygiene.py scan` passou (EXIT=0). Não é regressão nem vazamento.

Para separar ambiente de regressão, o commit base `e83af72` foi extraído (`git archive`) para
um diretório temporário e o mesmo teste de render falhou com o **mesmo** `ffmpeg failed`;
`test_render_api.py` (15 passed) e `test_publish_api.py` (13 passed + 1 que passa sozinho)
passam isolados no tree desta fatia.

Também foram observados, sob load average ~45 com 4 outros containers de teste, o mesmo
padrão de falhas de render/publicação; re-rodados isolados, passaram.

### Comandos usados

```
# focado final (fatia + db + arquitetura + composição + painel)
tests/test_analytics_learning.py tests/test_analytics_collection.py
tests/test_analytics_dashboard.py tests/test_analytics_repo.py tests/test_analytics_page.py
tests/test_insight.py tests/test_architecture.py tests/test_db.py tests/test_composition.py
tests/test_panel.py tests/test_panel_page.py tests/test_panel_production_page.py
# 261 passed, 1 skipped (Node.js ausente)
```

## Commits

- `1bcece0` — `feat(analytics): medição ligada a versões e coleta autorizada (F9-01/02)`
- `a9cf482` — `feat(analytics): dashboard e tela aprovada com ausência explícita (F9-03/05/06)`
- relatório `i-analytics-report.md` commitado com `git add -f` (caminho em `.superpowers/sdd/...`).
- Sem `git add -A`, sem push e sem merge.

## Higiene e git

`python3 scripts/secret_hygiene.py scan` → **Secret hygiene check passed** (nesta worktree, o `.git` é gitfile; o resultado foi verificado aqui, mas o veredito canônico continua sendo no `main` com gitdir real).

Commits e caminhos exatos no fim deste relatório. Sem `git add -A`, sem push e sem merge.