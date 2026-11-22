# Persistência: o que o mockup v4 guarda vs o que a plataforma já salva

Data: 2026-11-22 · Escopo: `docs/backlogs/faceless-visual-evolution 2/prototype-v4/index.html` contra o código real em `renderer/app/studio` (migrações `0001`–`0046`, domínio, rotas em `api/routes.py`).

**Método.** Li o objeto de estado `S` do mockup (canais, vídeos, cenas, providers, wizard, UI) e conferi cada campo em: migrações SQL, modelos de domínio (`contracts.py`, `channel.py`, `visual_style.py`, `effective_config.py`, `provider.py`, `channel_budget.py`, `saas.py`), e a lista de rotas. Tudo marcado abaixo como fato cita o arquivo. O que é inferência está marcado como **[assunção]**.

Legenda: ✅ já persistido · 🔶 persistido com outra forma/limite (ajustar) · ❌ lacuna (não existe) · ⚙ derivável (não salvar) · 🖥 só interface · 🔒 nunca no navegador

---

## 1. Resumo

- **Muito do mockup já tem onde morar.** Canal, perfil editorial, orçamento, estilo, cenas, revisões, aprovação, publicação, fontes, métricas, equipe e chaves BYOK existem no Postgres.
- **Há 3 grupos de lacuna real**, e o mais sério é o segundo:
  1. **Preferências de produção do canal sem coluna**: modo padrão (Piloto/Diretor), formato padrão, política de mídia, comportamento em falha, B-roll padrão, tentativas.
  2. **Controles do mockup que o motor não aplica hoje** (risco de prometer o que não acontece): fonte e estilo da legenda, posição topo/meio/base, trilha e volume de música, "abaixar música sob a voz", transição, resolução e FPS.
  3. **Bibliotecas sem tabela**: vozes, músicas, modelos de roteiro, e "arte" do estilo (prompt de arte, descrição, miniatura).
- **"+ Adicionar provider" não tem backend.** O catálogo de providers vem de código/ambiente, não de tabela. O que existe é cadastrar uma **chave BYOK** para um provider já suportado.
- **Criar canal não é uma gravação, são ~5.** Projeto, perfil, orçamento, configuração, vínculo de estilo e YouTube são chamadas separadas. Falha no meio deixa canal pela metade.
- **B-roll por cena não tem campo.** O design decidiu "sem mudar schema", mas falta definir onde o flag vive.

---

## 2. Matriz por entidade

### 2.1 Canal e identidade

Fato de modelo: **projeto ↔ perfil de canal é 1:1** (`channel_profiles.project_id ... UNIQUE`, migração 0016). Um "canal" do mockup = `projects` + `channel_profiles` (+ `channel_budgets` + `channel_youtube_channels`).

| Campo no mockup | Estado | Onde / observação |
|---|---|---|
| `name` | ✅ | `channel_profiles.name`; também `projects.name` (duplicado, manter em sincronia) |
| `niche` | ✅ | `projects.niche` |
| `lang` ("Português (BR)") | 🔶 | `channel_profiles.language` e `projects.language` guardam código (`pt-BR`); a interface mapeia rótulo ↔ código |
| `audience`, `strategy`, `pillars`, `cta` | ✅ | colunas homônimas; `pillars` tem limite (`MAX_PILLARS`) e normalização (`clean_pillars`) |
| `tone` ("estilo narrativo") | ✅ | `channel_profiles.narrative` |
| `dur` (duração padrão) | ✅ | `channel_profiles.target_duration_s` |
| `style` (estilo da biblioteca) | ✅ | `channel_profiles.style_id` (FK, `ON DELETE SET NULL`) |
| `subFont`, `subMode` do canal | 🔶 | só via `style_patch` do canal (`PATCH /channels/{id}/style-patch`), e o patch de legenda aceita apenas `font_size` e `bottom` (ver 2.5) |
| `voice` (padrão do canal) | 🔶 | `channel_profiles.voice` é um texto livre de provider/spec, **não** um id de uma biblioteca de vozes |
| `brand` (cor da marca) | 🔶 | não há campo no canal. Cores moram em `style.params.palette` (`caption_text`, `caption_box`, `accent`). `visual_identity` é texto |
| `format` (padrão do canal) | ❌ | formato é por vídeo (`videos.format`); canal não tem padrão |
| `mode` (Piloto/Diretor padrão) | ❌ | não existe em lugar nenhum |
| `ytOn`, `handle` | ✅ | `channel_youtube_channels` (`oauth_status`, `title`, `scopes`, `token_expires_at`) e `channel_profiles.youtube_channel_id`; conexões em `google_accounts`/`oauth_grants`/`channel_authorizations` |
| canal ativo | 🖥 | hoje é `?project_id=` na URL (`active_channel.py`). Não é salvo no servidor |

### 2.2 Produção, orçamento e providers do canal

| Campo no mockup | Estado | Onde / observação |
|---|---|---|
| `profile` econômico/equilibrado/premium | 🔶 | `channel_budgets.economic_profile` = `ECONOMY`/`BALANCED`/`PREMIUM`. Mapear nomes |
| `cap` (teto mensal) e `capVideo` (por vídeo) | 🔶 | o banco tem **quatro** limites: `hard_monthly`, `soft_monthly`, `hard_video`, `soft_video`. O mockup mostra um por escopo. Decidir: mostrar os dois (alerta e teto) ou derivar o alerta |
| gasto do mês | ⚙ | calculado de `usage_ledger`; **custo ausente nunca vira zero** (`cost_zero_evidence`, `unknown_ledger_cost`) |
| `mediaPolicy` | ❌ | sem coluna nem chave |
| `fallback` (se provider falhar) | ❌ | sem coluna nem chave |
| `retries` (máx. tentativas) | ❌ | tentativas existem por etapa (`stage_executions.attempt`), mas não como preferência do canal |
| `broll` (padrão do canal) | ❌ | sem campo |
| `res`, `fps` | ❌ | resolução é fixa por formato (`domain/render.py`: 1080×1920 e 1920×1080) e FPS é a constante **25** (`render.FPS`). O `Timebase` do plano aceita `fps_num`, mas nada o configura. O padrão **30** do mockup não bate com o motor |
| `routing` (provider fixado por tarefa) | 🔶 | `projects.config` aceita só `text`, `image`, `voice`, `renderer` (`PUBLIC_CONFIG_KEYS`); **`search` (stock) não é aceito**. A seleção efetiva também é congelada por execução (`EffectiveConfig.provider_selection`) |
| rota escolhida e fallbacks | ⚙ | `POST /projects/{id}/providers/route` recalcula a cada leitura. Não persistir |

### 2.3 Catálogo de providers e credenciais

| Item | Estado | Onde / observação |
|---|---|---|
| lista, capability, custo, rate limit, qualidade, disponibilidade, motivo | ⚙ | `GET /projects/{id}/providers` (`ProviderCardOut`), derivada de código/ambiente |
| "Testar conexão" | ✅ | `POST /projects/{id}/providers/test`. O resultado não é persistido (correto) |
| **"+ Adicionar provider" (nome, modelo, custo)** | ❌ | **não existe.** Adapters são código. Não há tabela de catálogo |
| credencial (referência) | ✅ | `byok_keys` (`provider`, `mask`, `fingerprint`, `secret_scope`, `secret_name`, `rotated_at`, `revoked_at`) e `byok_key_audit`; rotas `POST/DELETE /panel/equipe/keys` |
| valor da chave ou token | 🔒 | nunca vai ao navegador. Já é assim no backend; o mockup só pede um apelido |

### 2.4 Vídeo e cenas

| Campo no mockup | Estado | Onde / observação |
|---|---|---|
| `title` | 🔶 | `videos.topic` (3–300) e `videos.title` (título de publicação) são coisas diferentes. O mockup usa um só |
| `format`, `style` (override do vídeo) | ✅ | `videos.format`; `videos.style_id` e `videos.style_patch` (`PATCH /videos/{id}/style`) |
| `mode` (piloto/diretor) | ❌ | origem do vídeo não é registrada. **[assunção]** dá para inferir "piloto" por existir `production_run` completo, mas não é confiável |
| `state` | 🔶 | mapa abaixo |
| `rev`, `dirty` | ⚙ | `scene_revisions` (versão por cena), `render_plans.revision`, `render_jobs`. "Edições pendentes" = versão das cenas > versão renderizada |
| `target` (duração alvo do vídeo) | 🔶 | só existe no canal (`target_duration_s`) e é congelado no run (`production_runs` config, migração 0039). Alvo por vídeo antes do run não é salvo |
| `cost` | ⚙ | soma de `usage_ledger`; `null` quando desconhecido |
| `steps` (etapas) | ✅ | `stage_executions` (`state`, `attempt`, `error`), `production_runs`, `production_outbox` |
| `voice` (por vídeo) | 🔶 | só via `style_patch.voice.model` |

Mapa de estado (mockup → plataforma):

| Mockup | Plataforma |
|---|---|
| Rascunho (Diretor) | `SCRIPTED` / `STORYBOARDED` / `ASSETS_READY` |
| Gerando | `production_runs.state` em andamento (não é `VideoStatus`) |
| Aguardando aprovação | `AWAITING_APPROVAL` (após `RENDERED`) |
| Aprovado | `APPROVED` |
| Publicado | `PUBLISHED` |
| Falhou | `FAILED` ou `production_runs.state` falho |

| Cena no mockup | Estado | Onde / observação |
|---|---|---|
| `title` | 🔶 | `scenes.label`, **máx. 32** caracteres |
| `text` | 🔶 | `scenes.narration`, **5–400** caracteres. O mockup não limita |
| `prompt` | 🔶 | `scenes.image_prompt`, **10–500** caracteres. O mockup não limita |
| `media` (kind + imagem) | ✅ | `scenes.asset_id` → `assets` (`kind`, `provider`, `license`, `attribution`). Miniatura precisa do endpoint já previsto no design (`GET .../scenes/{idx}/asset`) |
| `audio` ok/none | ✅ | `GET/POST .../scenes/{id}/narration[/regenerate]`; devolve `duration_s` **medida**, `sha256`, `voice_id` |
| `audio` "desatualizado" | ⚙ | **[assunção]** comparar a revisão da cena com a do áudio. O `sha256` devolvido é do áudio, não do texto: confirmar como detectar |
| **`broll` + `brollNote`** | ❌ | **sem campo.** Há multicamada no plano de render (`render_plan.Shot`), mas nada liga isso a um flag por cena |
| reordenar, adicionar, excluir cena | ✅ | rotas `/script/scenes`, `/reorder`, `DELETE`, com `scene_revisions` |
| mover para outro vídeo, etc. | — | fora do mockup |

### 2.5 Composição e estilo (onde o mockup mais promete além do motor)

Fato verificado em `visual_style.py`: o estilo aceita apenas estes grupos e chaves.

| Grupo | Chaves aceitas | Aplicado ao vídeo hoje? |
|---|---|---|
| `motion` | lista de movimentos | sim (`APPLIED_GROUPS`) |
| `music` | `bpm`, `seed` | sim |
| `caption` | `font_size`, `bottom` | sim |
| `palette` | `caption_text`, `caption_box`, `accent` | sim |
| `voice` | `model` | sim |
| `transition` | `kind` (`none`/`fade`), `duration_ticks` | **não: só carregado** (`LOADED_ONLY_GROUPS`) |

| Controle do mockup | Estado | Conclusão |
|---|---|---|
| tamanho da legenda | ✅ | `caption.font_size` |
| posição (topo/meio/base) | 🔶 | só `caption.bottom` (distância da base). Topo/meio não existem |
| **fonte** (Inter/Roboto/Georgia) | ❌ | sem chave |
| **estilo** (destaque por palavra / caixa / simples) | ❌ | só dá para sugerir "caixa" por `palette.caption_box`. Destaque por palavra não existe |
| **música: trilha, volume %, "abaixar sob a voz"** | ❌ | só `bpm` e `seed`. Sem seleção de faixa, volume nem ducking |
| **transição** | 🔶 | existe `fade`/`none`, mas **não é aplicada ainda**. "Deslizar" não existe |
| movimento (zoom lento / estático) | ✅ | `motion` |
| **resolução e FPS** | ❌ | resolução fixa por formato; FPS fixo em 25 (o mockup mostra 24/30/60, padrão 30) |
| estilo do vídeo | ✅ | `videos.style_id` |

### 2.6 Qualidade, aprovação e publicação

| Item | Estado | Onde / observação |
|---|---|---|
| checagens de qualidade | 🔶 | o mockup **calcula no navegador**. A plataforma calcula no servidor e salva `videos.qa_report`. Em produção a tela só deve **exibir** o relatório do servidor |
| aprovar / rejeitar | ✅ | `POST /videos/{id}/approve` e `/reject`; `approvals`, `approval_history` |
| "desfazer aprovação" | 🔶 | existe o caso de uso e a migração (`application/reopen.py`, 0043). **[assunção]** não vi rota HTTP dedicada na lista; confirmar exposição |
| título, descrição, tags, visibilidade | ✅ | `videos.title/description/tags/privacy`; `publication_intents.visibility` |
| agendar | ✅ | `approvals.publish_at`, `publications.publish_at` |
| publicar, link do vídeo | ✅ | `publications.youtube_video_id`, `publication_intents`, rotas `/publication/*` |

### 2.7 Fontes

| Campo | Estado | Observação |
|---|---|---|
| URL, texto, `chars`, SHA256 | ✅ | `source_snapshots`; `SourceOut` já devolve `content_sha256` e `chars` |
| rótulo da fonte (`label`) | ❌ | não existe |
| fonte só com texto colado, **sem URL** | 🔶 | `SourceIn.url` é obrigatório (mín. 8). O mockup permite "texto colado" sem URL |
| remover fonte | ❌ | só `GET` e `POST /videos/{id}/sources`; não há `DELETE` |

### 2.8 Biblioteca, tendências, desempenho, equipe

| Item | Estado | Onde / observação |
|---|---|---|
| estilos: criar, versionar, arquivar | ✅ | `visual_styles` + `visual_style_revisions`; `/styles` |
| estilo: **descrição, emoji, prévia, prompt de arte** | ❌ | `params` só tem os grupos da seção 2.5. O mockup trata estilo como **direção de arte** (prompt base). Backend trata como **parâmetros de composição**. Divergência de conceito |
| vozes (biblioteca com amostra) | ❌ | sem tabela. Amostra de voz também não existe |
| músicas (biblioteca) | ❌ | sem tabela |
| modelos de roteiro | ❌ | só `script_plans.structure` por vídeo; sem biblioteca reutilizável |
| tendências | ✅ | `trend_topics`, `project_categories` |
| desempenho | ✅ | `video_metrics`, `metric_observations`, experimentos. Números do mockup são ilustrativos |
| equipe e papéis | ✅ | `memberships`, `membership_audit`; papéis `owner/editor/reviewer/viewer` |
| e-mail do convite | 🔶 | `users.email` + `memberships`; o mockup só guarda texto |

### 2.9 O que não deve ser salvo

| Item do estado `S` | Classe |
|---|---|
| `route`, `tab`, `libTab`, `setTab`, `vidFilter`, `trendNiche`, `guide`, `modal`, `toast`, `playing` | 🖥 |
| `newDraft` (rascunho do "Criar vídeo") e `wiz` (assistente de canal em andamento) | 🖥 (opcional: salvar rascunho local) |
| resultado de "Testar conexão" | 🖥 efêmero |
| qualquer chave, token, segredo | 🔒 |
| gasto, custo, métricas, tendências, rota de provider, "edições pendentes", QA | ⚙ calculado no servidor |

---

## 3. Fluxos compostos (um clique = várias gravações)

**Criar canal (assistente, passo 6).** Hoje seriam, no mínimo:

1. `POST /projects` (nome, nicho, idioma)
2. `POST /projects/{id}/channels` (estratégia, público, pilares, narrativa, duração, CTA, voz, `style_id`)
3. `PUT /projects/{id}/budget` (perfil + 4 limites)
4. `PUT /projects/{id}/config` (providers fixados, se houver)
5. `PATCH /channels/{id}/style-patch` (se personalizou legenda)
6. OAuth do YouTube (fluxo separado, por consentimento do usuário)

Risco: falha no passo 3 deixa um canal sem orçamento. Recomendação: **um caso de uso transacional e idempotente** ("criar canal") que faz 1–5, e o passo 6 sempre opcional e posterior.

**Piloto automático.** `POST /videos` → `POST /videos/{id}/sources` (se roteiro colado) → `POST /videos/{id}/production-runs` com `Idempotency-Key` (obrigatório) → acompanhar `GET .../production-runs/{run_id}`. O run congela a configuração efetiva (migração 0039). Nada disso grava "modo piloto".

**Renderizar nova versão.** Cria nova revisão das cenas e novo `render_plan`; aprovação anterior precisa ser invalidada (`approval_history`).

---

## 4. Lacunas priorizadas

| P | Lacuna | Opções | Recomendação |
|---|---|---|---|
| **P0** | Controles de composição sem lastro (fonte, estilo de legenda, posição topo/meio, trilha/volume/ducking, transição, resolução, FPS) | (a) estender motor e esquema; (b) **cortar ou desabilitar com aviso no protótipo** | **(b) agora**; (a) só por decisão de produto. Mostrar apenas o que o motor aplica: tamanho e distância da base da legenda, cores, movimento, `bpm`/`seed` |
| **P0** | Criar canal em várias chamadas | caso de uso transacional | criar antes de implementar a tela |
| **P1** | Preferências do canal (modo, formato, mídia, falha, B-roll, tentativas) | colunas em `channel_profiles` **ou** `projects.config` | **[assunção]** `projects.config` só aceita 4 chaves e valores `str`; mais simples é migração aditiva em `channel_profiles` |
| **P1** | B-roll por cena | coluna em `scenes` / shot no plano de render / metadado | decidir antes do plano de implementação; o design atual diz "sem mudar schema" mas não diz onde guardar |
| **P1** | "Adicionar provider" | remover do mockup; ou só **registrar chave BYOK** de provider existente | remover o cadastro livre; manter "Configurar credencial" |
| **P1** | Estilo como direção de arte (prompt base, descrição, prévia) | novo grupo em `params` **ou** guardar no `visual_identity` do canal | decidir o conceito de "estilo" (composição vs arte) |
| **P2** | Bibliotecas de voz, música e modelos de roteiro | tabelas novas | por ora, voz/música como lista fixa de código + amostra estática |
| **P2** | Fontes: `label`, texto sem URL, `DELETE` | pequenas | URL sintética para texto colado; adicionar remoção |
| **P2** | Alvo de duração por vídeo | coluna em `videos` | só se o produto quiser variar por vídeo |
| **P2** | Cor da marca do canal | usar `palette.accent` do estilo | não criar campo novo |

---

## 5. Ajustes no protótipo para ficar honesto

1. **Composição**: marcar os controles sem lastro (P0) como "em breve" ou removê-los. Hoje o mockup deixa o usuário mexer em tudo e a prévia reage, o que promete mais que o motor faz.
2. **QA**: texto deve dizer que as verificações vêm do servidor; manter o cálculo local só como ilustração.
3. **Providers**: trocar "Adicionar provider" por "Configurar credencial"; mostrar que **stock (`search`) não é fixável por canal** hoje.
4. **Orçamento**: expor alerta e teto (4 limites) ou explicar a derivação.
5. **Duração**: o mockup mostra duração estimada por palavras. A plataforma devolve duração **medida** do áudio (`duration_s`); usar essa quando existir.
6. **Limites de texto**: cena 5–400 caracteres, prompt 10–500, rótulo 32.
7. **Fontes**: pedir URL também para texto colado, ou aceitar a mudança de API.
8. **Idioma e perfil**: usar códigos reais por trás dos rótulos.

---

## 6. Perguntas em aberto (precisam de decisão)

1. A seção 2.5 deve virar **escopo de motor** (estender legenda/música/transição/FPS) ou o produto **assume o que o motor faz hoje**?
2. "Estilo" é **parâmetros de composição** (como está no banco) ou **direção de arte com prompt**? O mockup mistura os dois.
3. Onde mora o B-roll por cena?
4. Modo Piloto/Diretor é **preferência do canal**, **origem do vídeo**, ou os dois?
5. Providers customizados pelo usuário entram no produto, ou o catálogo continua sendo de código?

## 7. Fora do que verifiquei

- Não executei a plataforma nem consultei um banco real; a leitura é de código e SQL.
- Não li `panel_*.py` além do necessário; telas atuais podem esconder regras que não estão no domínio.
- A existência de rota HTTP para reabrir aprovação não foi confirmada (apenas o caso de uso e a migração).
