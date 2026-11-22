# Achados verificados

Registrados com evidência. A coluna **Estado** diz o que foi feito nesta rodada; o que não foi
resolvido fica com impacto e referência para avaliação futura — nada é apresentado como resolvido
sem teste.

| # | Achado | Evidência | Impacto | Estado |
|---|---|---|---|---|
| 1 | `/publications/claim` ficava **fora** do gate de identidade/versão da publicação | rota em `api/routes.py`; workflow n8n `workflows/03-publish-approved.json` inativo | um claim entregava arquivo + `youtube_body` sem passar pelo gate; risco de publicar canal/versão errados se o workflow fosse reativado | **resolvido**: `ClaimPublication` usa o mesmo gate (`application/publication_gate.py`), fail-closed, e falha a publicação em vez de entregar o arquivo. Testes: `tests/test_publishing.py::test_claim_refuses_without_a_valid_publication_intent`. |
| 2 | Seleção de provider congelada no snapshot do run (S8) | `domain/effective_config.py`, `application/production.py` | **resolvido** em rodada anterior (retry lê o snapshot) | — |
| 3 | Recusa de orçamento não era acionável | `api/routes.py` respondia `403 "budget denied for paid operation <key>"` | operador não sabia qual teto estourou nem os valores | **resolvido**: `BudgetDenial` (escopo, teto, comprometido, estimativa) viaja no `BudgetDenied.detail`; o 403 diz o escopo e os números. Testes: `tests/test_budget_guard_wiring.py::test_a_denied_reservation_says_which_ceiling_was_hit`, `tests/test_budget_http.py` (caso com detalhe). |
| 4 | Compose não encaminhava `STUDIO_PROVIDER_PRODUCTION` / `STUDIO_SECRETS_ROOT` | `docker-compose.yml` (W0B.1 só encaminhou o guard e o modo) | produção por provider e cofre de segredos não chegavam ao container | **resolvido**: as duas variáveis entram no serviço `renderer` com default seguro e estão documentadas no `.env.example`. Teste: `tests/test_compose_env.py::test_compose_forwards_the_provider_production_flag_and_the_secrets_root`. |
| 5 | `application/config.py` ainda cita `ffmpeg` nos `_DEFAULTS` | `renderer/app/studio/application/config.py` | resíduo de S2: nome de fornecedor na camada de aplicação | aberto (decisão de produto: mover o default para composição ou aceitar como dado de configuração) |
| 6 | ~~`render_compiler.py` emitia argumentos com `ffmpeg`~~ | `application/render_compiler.py` | S3 | **resolvido** na rodada anterior (compilador movido para `adapters/render_plan_compiler.py`; `grep -c ffmpeg` = 0 no neutro) |
| 7 | `MediaSearch` não tem adaptador de segunda fonte (Pixabay) | `adapters/media_pexels.py` é o único | se o Pexels cair ou não tiver o termo, não há fallback | aberto (segundo adaptador da mesma porta, sem tocar o domínio) |
| 8 | QA semântico não tem verificador | `domain/quality.py` marca `MULTIMODAL_EVALUATION` como `not_verified`; a aba Qualidade é honesta | não há selo falso; falta a porta do avaliador multimodal | aberto (`SemanticChecker` declarado; implementar por provedor de visão) |
| 9 | `panel_styles.py` `active_section` alinhado a `biblioteca` | `api/panel_styles.py` | — | resolvido na W1 |
| 10 | Testes de segredos não resolvem `.git` de worktree dentro do container | `tests/test_secrets_hygiene.py` | falso negativo em validação por worktree | aberto (montar o gitdir ou pular com motivo explícito no worktree) |
| 11 | `test_port_contracts` falhava na suíte completa por **vazamento de `_REGISTRY`** | `register(...)` em nível de módulo em `tests/test_editorial_api.py` e `tests/test_render_api.py` | 2 falhas falsas na suíte completa; o arquivo isolado passava | **resolvido**: fixture `registered_providers` (salva/restaura o `_REGISTRY`) e os fakes passaram a ser registrados dentro do teste. Verificado: os dois módulos + `test_port_contracts` juntos → 140 passed. |
| 11b | Mesmo vazamento, outra origem | `register("voice", "tone-narr", ToneVoice)` em **nível de módulo** em `tests/test_scene_narration.py` | `test_port_contracts::test_catalog_and_registry_have_no_drift` falhava na suíte completa com `('voice', 'tone-narr')` a mais no catálogo | **resolvido**: o registro foi para uma fixture autouse com `registered_providers`. Verificado: `test_secrets_hygiene + test_port_contracts + test_scene_narration + test_editorial_api + test_render_api + test_tts_calibration` → **89 passed**. |

## Bugs encontrados durante esta rodada (não estavam na lista original)

### B1. A porta da intenção de publicação recebia o repositório de aprovação — **resolvido**
- **Evidência (container, código real)**: `publish.approvals is publish.intents` → `True`;
  `type(publish.intents)` → `PostgresApprovalRepository`; `publish.intents.get` →
  `(video_id) -> Approval | None`; a porta `PublicationIntentRepository` exige
  `get -> PublicationIntentEvidence | None`; `PostgresApprovalRepository.intent()` existia e **não
  era chamado por ninguém**.
- **Impacto**: `RunPublication._prepare` lia um `Approval` (sem `render_id`) onde esperava a
  intenção, e `verify_publication_gate` estourava `AttributeError` → **500 em
  `POST /publications/execute`** (o caminho efetivo de upload) assim que houvesse vídeo aprovado
  com render. O gate de versão aprovada nunca rodava de verdade no caminho real.
- **Correção**: `adapters/postgres/publish_repo.PostgresPublicationIntentRepository` adapta
  `intent()` à porta `get()`; a composição passa `intents` distinto de `approvals`.
- **Testes**: `tests/test_publication_execution.py::test_the_intent_adapter_reads_the_intent_not_the_approval`
  e `...::test_composition_wires_the_intent_adapter_and_not_the_approval_repository`.

### B2. Ids duplicados na tela de Canais — "novo canal" nascia com o nome do perfil — **resolvido**
- **Evidência (HTML renderizado de `/studio/canais`)**: `canal-nome`, `canal-nicho`,
  `canal-idioma`, `btn-salvar-canal` e `btn-novo-canal` apareciam **duas vezes** — uma no cartão de
  perfil (que vem antes no documento) e outra no diálogo do shell (`#dlg-canal`). Como
  `document.getElementById` devolve o **primeiro** match, o diálogo "Novo canal" lia o nome do
  **perfil** (`value="Musica"`) e o nicho literal "não informado".
- **Impacto observado**: canais criados com o nome do perfil ativo em vez do nome digitado
  (`studio.projects`: 3 canais, todos `Musica`; os dois novos com `niche = 'não informado'`).
- **Correção**: os campos do diálogo passaram a ser namespaced (`dlg-canal-nome`,
  `dlg-canal-nicho`, `dlg-canal-idioma`, `dlg-btn-salvar-canal`) e o botão do cartão "Adicionar
  canal" virou `btn-criar-canal`.
- **Teste**: `tests/test_channels_page.py::test_settings_pages_never_repeat_an_element_id`
  (nenhum id repetido em `/studio/canais`, `/studio/configuracoes/estrategia` e `/producao`).

## Refatorações S3/S4/S5 (sem mudança de comportamento)

| Item | Antes | Depois | Verificação |
|---|---|---|---|
| S3 | `application/render_compiler.py` emitia `args` com `"ffmpeg"` | compilador específico em `adapters/render_plan_compiler.py`; `application/render_compiler.py` neutro (`grep -c ffmpeg` = 0) | conjunto de render verde (213 → 361) |
| S4 | `composition.py` (1025 linhas) | pacote `composition/{__init__,settings,providers,wiring}.py` (24+91+190+773) | fidelidade conferida linha a linha (só diferem docstring, reexport e as 3 linhas de `intents`); focado 393 passed |
| S5 | `api/panel.py` (4201 linhas) | `panel_shell.py` (1901) + `panel_operacional.py` (1403) + `panel_video.py` (739) + `panel_script.py` (204); `panel.py` = agregador de 75 linhas | slices byte-idênticos; subagente: suíte 3304 passed / 4 pré-existentes |

- **S4**: a única alteração não mecânica é `build_google_oauth` resolvido na raiz do pacote em tempo
  de chamada (`_composition.build_google_oauth`), preservando o `monkeypatch.setattr(composition,
  "build_google_oauth", ...)` de `test_connections_api.py`/`test_connections_page.py`.
- **S5**: reaplicada a injeção de `video_area_nav(v.id, DEFAULT_AREA)` em `panel_video.render_video`
  (a mudança era o "+3" de `panel.py` no checkout). `panel_video_workspace.py` continua importando a
  fonte única `panel_video_nav`.

## Achados de UX/navegação desta rodada

### C. Casca legada ainda viva na página de retorno do OAuth — **aberto**
- `panel_shell.build_sidebar_nav` (grupos "Operação"/"Configuração"/"Indisponível nesta versão") é
  usada só por `panel_oauth.render_oauth_callback` (`/studio/oauth/callback`);
  `panel_production.render_new_video` também a usa, mas está **morto** (import em `routes.py` sem uso).
- **Impacto**: a página de retorno do Google mostra navegação diferente do resto do estúdio.
- **Recomendação**: migrar para `shell_v3.render_document` e remover o import morto. Não feito
  (fora dos itens dos docs de análise; mexe em `tests/test_channels_page.py`).

### D. Menu principal sem "Operação"/"Configuração" — **resolvido**
- `NAV_OPERACAO` = 7 itens (`NAV` do protótipo, `prototype/index.html:583`), um único
  `<nav aria-label="Principal">`; caption "Operação" e o `<nav aria-label="Configuração">` do rodapé
  removidos. Ver `analysis/NAVEGACAO-COMPARACAO.md`.

### E. Matriz de papéis em Conta e equipe — **resolvido**
- `panel_team._permissions_matrix` gera Papel × (Editar/gerar · Aprovar · Publicar) de
  `ROLE_PERMISSIONS`. Diverge de propósito do protótipo (ilustrativo): no RBAC real o **Editor
  publica**. Ver `analysis/CONFIG-UX-AVALIACAO.md` 3.3.

## Ambiente de teste (não é código)

- Rodadas concorrentes de container derrubam o Postgres descartável e matam `ffmpeg` por OOM.
  Rodada completa com outras frentes ativas é **inválida**; refazer sozinha.
- `scripts/test-container.sh` honra `FACELESS_TEST_IMAGE`/`FACELESS_PYTEST_IMAGE`; cada frente usa
  uma tag própria para não colidir. O pytest roda com o checkout montado em `/w` (somente leitura)
  e `PYTHONPATH=/w/renderer` — o código testado é o do checkout, não o da imagem.
