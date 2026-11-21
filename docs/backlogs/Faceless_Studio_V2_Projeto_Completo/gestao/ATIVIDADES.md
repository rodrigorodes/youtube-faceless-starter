# Quadro de atividades — Estilos de canal + Identidade de publicação

**Atualizado:** 2026-11-21
**Base:** `main` @ `efd697b`
**Regra de trabalho:** cada fatia em worktree isolada, branch própria, merge no `main` só depois de
teste verde + arquitetura limpa + árvore limpa. Nada removido sem prova de morte. Sem `git add -A`.
Sem push/merge remoto (bloqueado pelo harness).

## Legenda de estado

- 🟢 **CONCLUÍDA** — no `main`, com prova
- 🔵 **EM EXECUÇÃO** — um agente está trabalhando agora
- 🟡 **NA FILA** — especificada, esperando dependência
- 🔴 **BLOQUEADA** — espera decisão ou ação humana

## Concluídas

| ID | Atividade | Prova | Commit |
| --- | --- | --- | --- |
| ITEM-1 | O estilo do canal entra no plano (para de gravar `studio-default@1`) | 112 testes focados | `a0c8417` |
| VS-01 | Biblioteca de estilos visuais versionada (domínio + migração `0033` + repo) | 42 testes focados | `02fc6ea` |
| VS-02 | O canal aponta para um estilo (`channel_profiles.style_id`, recusa estilo inexistente) | 133 testes focados | `6f33692` |
| YT-01 | Identidade de publicação: schema `0035` + domínio (conta → grants → canais) | 56 testes focados | `2d7a471` |
| VS-02b | Override de estilo por vídeo (`videos.style_id`, `set_video_style`, recusa estilo inexistente) | 47 testes focados | `d57a272` |
| VS-03 | O estilo **aplica**: plano grava o snapshot do `VisualStyle` + `motion`/`music` do estilo | 133 testes | merge `475ae63` |
| YT-01b | Repositórios da identidade YouTube (conta/grants/canais/vínculos) + 4 portas | 41 testes | merge `473492c` |
| UX-00 | Desenho de UX das configurações (IA, telas, estados vazios, referências) | doc | `docs/superpowers/specs/2026-11-21-backoffice-settings-ux-design.md` |
| VS-04 | `caption`/`palette` do estilo **aplicados** no overlay (`caption_layout`/`overlay_colors`); `voice` carregada, precedência só reportada | 107 testes | merge `28cb4e5` |
| YT-02 | O canal referencia o **destino** no YouTube (`channel_profiles.youtube_channel_id`, migração `0037`) + resolvedor puro | 134 testes | merge `f848a57` |
| DOC-01 | **Modelo de dados + DDL** gerados (`docs/22-modelo-de-dados.md`, `docs/schema/studio.sql`) com teste de snapshot | 28 testes | `scripts/export_schema.py` |
| YT-03 | A publicação **bloqueia** quando o token não resolve para o canal esperado (a regra do desenho) | 153 testes | merge `145c786` |

| VS-05a | Biblioteca de Estilos: API `/styles`, tela `/panel/estilos`, menu; contagem de uso medida | 438 testes (integração) | merge `759fe71` |
| YT-04a | Serviço + API de Conexões (conta → canais → vínculo validado → revogar isolado); tokens só no cofre | 442 testes (integração) | merge `8e2556e` |
| VS-05b | Seletor de estilo no canal (Aparência) + override no vídeo + `PATCH /videos/{id}/style` | 485 testes (integração) | merge `6df1762` |
| VS-05c | **Correções**: override do vídeo chega ao render (precedência vídeo > canal > neutro); `archive` limpa os vínculos + docstring corrigida | 211 testes | merge `08508ab` |
| YT-04b | Página **Conexões** no painel (conta → canais → confirmar → revogar) + menu | 378 testes (integração) | merge `42f73ca` |
| RF-01 | Reframe de vocabulário: "projeto" → "canal" na interface (16 textos; 5 mantidos por serem identificador/comentário) + teste-guarda | 202 testes | merge `ec8bda2` |
| VS-06 | Voz com **precedência única** (estilo > projeto > default; `PIPER_VOICE` como fallback de deployment/teste), o **mesmo** valor para síntese e ledger | 182 focados + 386 integração | merge `e7a5182` |
| PROD-01 | **Fecha o ciclo de produção pela UI**: Início cria **e inicia**; página do vídeo ganha **Fontes** (URL+texto) e **Iniciar produção** / **Tentar novamente** com o motivo real | 258 focados + 105 UX/nav (re-verificados por mim) | merge `efd697b` |
| PROD-02 | **Retomar/retentar religa o worker** (o gate humano era intransponível) + run `RUNNING` órfão recuperável pela tela de execução | 104 (re-verificados) + falsificação do teste (sabotei o `_enqueue`: 2 falham) | merge `59c32da` |
| IA-01 | **Início, Produção e Tendências como telas separadas**: rotas de servidor (`/panel`, `/panel/producao`, `/panel/tendencias`), `/panel/videos` → 302, nav sem âncoras; o HTML de uma tela nunca entra na outra | 301 (re-verificados) + verificação viva (3×200, 302, zero vazamento, 1 `aria-current`/página) | merge `1b98ddd` |

## Em execução (paralelo)

**PROD-04 (em execução):** a criação não pode perder a fonte nem iniciar produção fadada ao
`SourceRefused`; e um vídeo sempre pode iniciar produção nova. Fundiu o antigo PROD-05 (achado 5).

**PROD-03 (em execução):** recuperação de runs em voo no boot (o `lifespan` não varre nada hoje).

## Na fila

| ID | Atividade | Depende de |
| --- | --- | --- |
| — | (vazio) | — |

## Achado do dono (2) — 2026-11-21: o gate humano travava toda produção

O dono rodou a produção `04260fa5ed8f5fdfb4ab0b7a23d1456c` (vídeo `e0ae111f86084e3585de00fd5dc5cc65`). O
roteiro foi gerado (17 s, 6 cenas, `SCRIPTED`), o run pausou em `WAITING_HUMAN` ("roteiro gerado:
revisão humana obrigatória"), o dono clicou **Continuar** — o log mostra
`POST /production-runs/04260.../resume → 200 OK` — o estado virou `RUNNING` e **nada mais aconteceu**:
20+ min depois, nenhuma etapa com lease, nada reivindicado, nenhum erro.

**Causa raiz:** `ProductionWorker.work` só é lançado por `Production.start`
(`application/production.py:713`); os endpoints `/resume` e `/retry` (`routes.py`) chamam
`coordinator.resume/retry` direto e **nunca** `submit`. Como o laço encerra quando o coordenador pausa,
depois do gate não há quem religue. Em modo `INTERACTIVE` (o do dono) **toda** produção parava no
primeiro gate — e o "Tentar novamente" da PROD-01 tinha o mesmo defeito.

**Fonte suspeita:** a "fonte" registrada no vídeo é um **trecho da minha própria mensagem de chat**
("a URL vira só referência — é isso que contorna a lista de nicho travada em amsterdam-dance-event.nl)",
100 caracteres), com URL `https://www.youtube.com/watch?v=nTJ5Z9gZsZU`. Ou seja: o roteiro foi gerado
**sem base factual** — é o dono colar o texto real da fonte. Registrado porque o fact-check seguinte
tende a reprovar.

## Achado do dono (3) — 2026-11-21: "criar vídeo da tendência" não leva o link do YouTube

Relato: *"ao criar video da trend nao carrega o link do video do youtube URL da fonte * vem vazio"*.

**Diagnóstico (verificado; o elo foi provado com dados reais).** O tema do vídeo do dono é
`GTA VI: DIA 3 ZERANDO  🔴 CORINGA AO VIVO` e existe a trend correspondente
(`trend_topics.id = 35db5b7c…`), cujo `evidence` traz
`https://youtube.com/watch?v=nTJ5Z9gZsZU` — **exatamente a URL que o dono digitou à mão** na fonte. Ou
seja: o dado já estava no estúdio e não chegou à tela. Três lacunas independentes:

1. **A URL é descartada no botão.** `panel.py:1966` — o botão "✨ Criar Vídeo deste Tema" carrega
   **só** `data-topic`; a URL do vídeo (`TrendCard.video_url`, vinda de `evidence[].url`, já renderizada
   como "▶️ Assistir no YouTube") **não** é passada.
2. **Não existe onde guardar.** `VideoIn` (`routes.py:151`) é `project_id/topic/format` e
   `studio.videos` **não tem** coluna de origem (cols reais: `id, project_id, topic, format, status,
   title, description, tags, privacy, qa_report, schema_version, created_at, updated_at, style_id`).
3. **O campo nunca é preenchido.** `#source-url` (`panel.py:3101`) é renderizado **sempre vazio** — é um
   formulário de "adicionar fonte", nada conhece a procedência.

**O vínculo já existe e dispensa migração:** o cartão da tendência conta os vídeos por
`topic_key` (`application/panel.py:324`, `grouped_videos[r.topic_key]`), e a normalização do tema do
vídeo **casa exatamente** com a da trend (`topic_key(...) == "gta vi: dia 3 zerando 🔴 coringa ao vivo"`,
conferido rodando a função do domínio). Então a URL do vídeo base é **resolvível** a partir do tema.

**Correção proposta (fatia PROD-04, depende da IA-01 — mesma tela/arquivo):** resolver a URL do vídeo
base pelo `topic_key` (porta dedicada no repositório de tendências, resolução na aplicação pura) e
**pré-preencher** `#source-url`, mostrando "vídeo base" como no desenho aprovado. **Não** criar fonte
automaticamente: com `text=None` a busca seria recusada pela allowlist de nicho, e fonte sem texto não é
evidência.

**Limitação honesta:** se o dono **editar** o tema ao criar, o `topic_key` deixa de casar e a URL não se
resolve. Gravar a procedência (id da trend no vídeo) resolveria isso, mas exige migração — registrado
como opção, não incluído no escopo.

## Achado do dono (4) — 2026-11-21: criar pelo Início começa uma produção que **já nasce falhando**

Consequência do PROD-01 que eu não vi ao entregá-lo: o formulário do Início **cria e inicia** a
produção, mas a 1ª etapa do DAG (`script`) **exige fontes** — e a fonte só pode ser adicionada **depois**
que o vídeo existe (cartão Fontes, na página do vídeo). Logo, todo vídeo novo criado por ali nasce com um
run `FAILED` e a razão `SourceRefused: no sources with checkable claims: add sources first`.

**Prova:** no meu diagnóstico da execução presa, criei um run para um vídeo com 0 fontes e ele falhou
imediatamente com essa mensagem exata (os 2 runs de teste foram removidos depois).

**Não é beco sem saída** (com o PROD-02, "Tentar novamente" funciona: adicionar a fonte e retentar
recomeça o roteiro), mas é um defeito de fluxo: o ato de criar mostra "Falhou" na cara do usuário. O
caminho aprovado em `JORNADA-E-TELAS.md` é **Produzir vídeo → Pesquisar fontes → Roteiro** — a produção
não deveria começar antes de existir fonte. Escopo a resolver junto no **PROD-04**.

## Achado do dono (5) — 2026-11-21: não há como **iniciar uma produção nova** num vídeo que já tem run

A página do vídeo só oferece "Iniciar produção" quando `latest_run` é `None` (`panel.py:3134`). Com
qualquer run existente (mesmo `FAILED`/`CANCELLED`), a tela não expõe a ação — embora a API aceite:
`coordinator.start` → `runs.create_run(...)` **não tem guarda** de run ativo. Sem isso, não há como
refazer um vídeo cujo roteiro nasceu de fonte ruim (retry re-executa a etapa falha, não reescreve o
roteiro). Absorvido pelo **PROD-04**, que decide onde a produção começa.

## Bloqueadas

| ID | Atividade | Bloqueio |
| --- | --- | --- |
| **YT-05** | Teste ao vivo A/B (dois canais na mesma conta) — valida o **adapter**, não o domínio | Precisa da sua conta Google real e do seu "ok" para rodar |

## Itens abertos conhecidos (registrados, não escondidos)

- **Voz — "duas verdades"**: **DECIDIDA pelo dono: Opção A** — estilo > projeto > default, com
  `PIPER_VOICE` rebaixado a fallback de deployment/teste, e o **mesmo** valor para síntese e para o
  ledger/cache. Em execução na **VS-06**.
- **Cache do render × estilo**: o fingerprint do nó visual **não** inclui `style_snapshot` nem a
  geometria/cor do overlay — mudar só `caption.font_size`/`palette` **não invalida** o cache
  (gap pré-existente, documentado na VS-04).
- **Preferência de grant**: com várias autorizações `CONECTADAS` para o mesmo canal, o resolvedor
  devolve a primeira na ordem de entrada; a política segue aberta.
- **`archive` mentia (sendo corrigido na VS-05c)**: a docstring prometia que "os canais passam a
  resolver o padrão do estúdio", mas o `archive` **não** limpava `channel_profiles.style_id` e o
  `get` devolvia estilo arquivado — verificado em `visual_style_repo.py::archive` + `composition.py`.
- **Override do vídeo não chegava ao render (sendo corrigido na VS-05c)**: `render.py:220` chamava
  `style_for(video.project_id)` e `_style_for_project` só olhava o estilo do canal — o
  `videos.style_id` existia na tela e era ignorado no render.
- **Abas do canal (§5.2) não construídas**: a VS-05b entregou a **Aparência** como card, sem
  reescrever a tela em abas (Identidade/Publicação/Custos seguem como estão).
- **E-mail da conta Google (YT-04a)**: com os escopos atuais (`youtube.upload`/`youtube.readonly`)
  o Google não expõe o e-mail (isso exige `openid`/`userinfo.email`). O callback aceita `email`
  opcional como reserva; sem nenhum dos dois, o serviço **recusa** (`AccountIdentityUnavailable`,
  422) em vez de inventar uma conta. Habilitar o e-mail real exige escopo/extensão do adapter.
- **Guard do scanner de segredos**: `secret_hygiene.py` **recusa rodar** com arquivo em conflito
  (`if stage != b"0": raise ValueError("Unmerged files ... cannot be scanned safely")`). Rodá-lo no
  meio de um merge **não** indica vazamento — foi o que aconteceu uma vez nesta orquestração.

## Princípios que valem para toda fatia

1. **Nada é removido sem prova de morte** e nada sai sem cópia verbatim em `archive/`.
2. O painel **não inventa dado**; sem medição, sem percentual.
3. `domain`/`application` puros; adapters isolados; wiring só em `composition.py`
   (`tests/test_architecture.py`).
4. Suíte Postgres precisa das **duas** DSNs + `STUDIO_BUDGET_TEST_PROOF_FILE`.
5. Nada de `git push`/merge remoto; `origin` intocado.

## Infra de teste — lição aprendida (2026-11-21)

O fixture `conn` faz `DROP SCHEMA IF EXISTS studio CASCADE` **no mesmo banco**. Consequência:
**suítes concorrentes no mesmo Postgres colidem** (`schema "studio" does not exist`,
`duplicate key ... (nspname)=(studio)`). Rodar duas fatias em paralelo contra o `integ-pg`
compartilhado produz falhas **fantasma** — que não são bug de código.

**Regra:** cada fatia em execução paralela usa o **seu** Postgres. Há quatro no ar:
`integ-pg` (compartilhado), `integ-pg-orch` (orquestrador), `integ-pg-a`, `integ-pg-b` (agentes).
Antes de mesclar qualquer fatia, o orquestrador **re-verifica serialmente** numa base só dele.

## Modelo de dados e DDL — como se mantêm honestos

`scripts/export_schema.py` gera dois artefatos versionados:

| Artefato | O que é | Como é obtido |
| --- | --- | --- |
| `docs/schema/studio.sql` | DDL consolidado do schema `studio` | as **migrações concatenadas verbatim**, em ordem de aplicação (é o próprio SQL que cria o schema) |
| `docs/22-modelo-de-dados.md` | diagrama ER (Mermaid) + colunas/chaves/índices + histórico | **introspecção do banco real** após aplicar as migrações (não leitura de texto) |

`tests/test_schema_docs.py` prende os dois ao código: o DDL é conferido **offline**, o modelo
exige banco (é pulado sem `STUDIO_TEST_DSN`). **Consequência prática: toda migração nova obriga a
regerar os dois** (`python scripts/export_schema.py --dsn "$STUDIO_TEST_DSN" --build`), senão a
suíte acusa divergência. O gerador só lê; não altera dados.

## Verificações que eu fiz por conta própria (não aceitei de relatório)

- **RF-01 — teste-guarda não é vazio**: injetei `<p>Projeto</p>` na navegação do painel e o guard
  falhou (**8 failed**); revertida a sonda, o teste passa. Um assert que não pode falhar não vale nada.
- **RF-01 — acidente de caminho relativo**: a fatia relatou ter editado, por engano, o worktree da
  sessão pai. Conferi **os dois worktrees**: `faceless-v2-impl` e `main` estão **limpos** — o engano
  foi revertido e nada vazou.
- **VS-05b — duas promessas falsas**: o override do vídeo não chegava ao render (`render.py:220`
  chamava `style_for(video.project_id)`) e a docstring do `archive` mentia (não limpava vínculos).
  Ambos confirmados no código e corrigidos na VS-05c.
- **Alarme falso — scanner de segredos**: falhou uma vez por eu tê-lo rodado com arquivo em conflito
  (`composition.py` nos stages 1/2/3); o guard recusa rodar assim, por projeto. Não era vazamento.

## Veredito final da suíte (2026-11-21)

`main` @ `990136b` — **2603 passed, 0 failed, 35 skipped**, em 8 partições (**8/8 verdes**).
Baseline anterior: 2430 passed / 0 failed / 35 skipped. Ou seja: **+173 testes** novos,
nenhuma falha nova, o mesmo número de skips (35, pré-existentes).

Cobertura do veredito: a suíte inteira (148 arquivos de teste), não só as fatias.

## Encerramento da orquestração

- **Postgres extras removidos**: `integ-pg-a`, `integ-pg-b`, `integ-pg-orch`
  (preservados: `integ-pg`, o stack do app, o n8n e os volumes).
- **Worktrees das 12 fatias removidos** — as **branches foram preservadas**, então nada do
  trabalho se perde; só as pastas de trabalho saíram. O repo do dono ficou intacto.
- Nenhum container de teste órfão.
- **Base do app resetada e migrada**: ver `OPERACAO-reset-base-2026-11-21.md`.

## Achado do dono (2026-11-21) — o fluxo de produção não fechava pela UI

O dono criou um vídeo e ele ficou **preso em `IDEA`**. Diagnóstico verificado, com prova:

1. **Dois fluxos de criação.** O form do **Início** (`panel.py`) só criava o vídeo
   (`POST /studio/videos`) e recarregava a página; quem iniciava a produção era o assistente de
   `/panel/novo-video` (`panel_production.py` → `POST /production-runs`). Prova: log com
   `POST /studio/videos 201` e **nenhum** `POST .../production-runs`; e a página do vídeo sem
   nenhum controle de produção.
2. **A produção exige fontes.** O stage `SCRIPT` (1º do `COORDINATOR_DAG`) recusa sem claims:
   `SourceRefused: no sources with checkable claims: add sources first`
   (`application/editorial.py:215`). Confirmado disparando um run real — falhou com essa mensagem.
3. **A UI não expõe fontes.** `POST /videos/{id}/sources` existe, mas nenhuma tela o usava (a tela
   "Pesquisa" do desenho aprovado não foi implementada).
4. **A allowlist default é de outro nicho** (`amsterdam-dance-event.nl`). Mas `execute_text`
   (URL + texto colado) **não** valida allowlist — é a saída legítima para qualquer nicho.

Os 2 runs de teste criados pelo orquestrador para provar o item 2 foram **removidos** (o vídeo
voltou a `IDEA`, 0 fontes, 0 runs).
