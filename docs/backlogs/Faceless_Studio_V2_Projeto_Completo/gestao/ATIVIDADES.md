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

## Em execução (paralelo)

**Onda 4 (em execução):** VS-05b (seletor de estilo no canal + override no vídeo) e YT-04a (serviço + API de Conexões: conectar conta → canais → vincular → revogar; **sem** painel). Postgres dedicados `integ-pg-a`/`integ-pg-b`.

## Na fila

| ID | Atividade | Depende de |
| --- | --- | --- |
| **YT-04b** | UX: página **Conexões** + item de menu (conectar → escolher canal → confirmar → revogar) | YT-04a |
| **RF-01** | Reframe de produto: "projeto" → "canal" na UX (o canal é a unidade) | VS-05b, YT-04b |

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
  devolve a primeira na ordem de entrada; a política fica para a YT-04.

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


