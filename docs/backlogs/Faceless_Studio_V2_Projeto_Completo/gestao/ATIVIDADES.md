# Quadro de atividades — Estilos de canal + Identidade de publicação

**Atualizado:** 2026-11-21
**Base:** `main` @ `f848a57`
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

## Em execução (paralelo)

**Nada em execução.** Todas as fatias do plano foram mescladas e verificadas por mim antes do merge. Restam o **veredito completo da suíte** (rodando em 8 partições) e a **limpeza dos Postgres extras**.

## Na fila

| ID | Atividade | Depende de |
| --- | --- | --- |
| — | (vazio — plano concluído; falta só o veredito da suíte e a limpeza dos Postgres extras) | — |

## Bloqueadas

| ID | Atividade | Bloqueio |
| --- | --- | --- |
| **YT-05** | Teste ao vivo A/B (dois canais na mesma conta) — valida o **adapter**, não o domínio | Precisa da sua conta Google real e do seu "ok" para rodar |

## Itens abertos conhecidos (registrados, não escondidos)

- **Voz — "duas verdades"**: o estilo carrega `voice`, mas a precedência ainda não foi resolvida
  (`estilo.voice.model` vs `STUDIO_VOICE`/config do projeto vs `PIPER_VOICE`). Recomendação no
  relatório da VS-04; decisão pendente do dono.
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
