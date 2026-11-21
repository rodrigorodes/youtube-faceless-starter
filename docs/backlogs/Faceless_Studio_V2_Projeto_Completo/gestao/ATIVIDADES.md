# Quadro de atividades — Estilos de canal + Identidade de publicação

**Atualizado:** 2026-11-21
**Base:** `main` @ `2d7a471`
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

## Em execução (paralelo)

| ID | Atividade | Depende de | Arquivos-alvo |
| --- | --- | --- | --- |
| **VS-03** | O estilo **aplica**: o plano grava o `StyleSnapshot` do `VisualStyle` e usa `motion`/`music`/`transition` do estilo | — | `domain/visual_style.py`, `application/ports.py`, `application/render.py`, `adapters/render_plan_ffmpeg.py`, `composition.py` |
| **YT-01b** | Repositórios da identidade YouTube (contas, grants, canais, vínculos) + portas | YT-01 | `adapters/postgres/youtube_identity_repo.py` (novo), `application/ports.py` |
| **VS-02b** | Override de estilo por vídeo (`videos.style_id`) — o "herda e pode sobrepor" | VS-02 | `domain/contracts.py`, `adapters/postgres/repo.py`, migração `0036` |

## Na fila

| ID | Atividade | Depende de |
| --- | --- | --- |
| **VS-04** | `caption`/`palette`/`voice` do estilo aplicados no renderer (tira o hardcode; resolve a "duas verdades" da voz) | VS-03 |
| **YT-02** | O canal referencia o canal de publicação; a publicação resolve a autorização **pelo canal**, não pelo projeto | YT-01b |
| **YT-03** | **A regra**: verifica que a autorização resolve para o canal esperado; **bloqueia** a divergência | YT-02 |
| **VS-05** | UX: superfície de Estilos + seletor no canal + override no vídeo | VS-03, VS-04, VS-02b |
| **YT-04** | UX: conectar conta, escolher/validar canal, revogar (reconexão isolada) | YT-03 |
| **RF-01** | Reframe de produto: "projeto" → "canal" na UX (o canal é a unidade) | VS-05, YT-04 |

## Bloqueadas

| ID | Atividade | Bloqueio |
| --- | --- | --- |
| **YT-05** | Teste ao vivo A/B (dois canais na mesma conta) — valida o **adapter**, não o domínio | Precisa da sua conta Google real e do seu "ok" para rodar |

## Princípios que valem para toda fatia

1. **Nada é removido sem prova de morte** e nada sai sem cópia verbatim em `archive/`.
2. O painel **não inventa dado**; sem medição, sem percentual.
3. `domain`/`application` puros; adapters isolados; wiring só em `composition.py`
   (`tests/test_architecture.py`).
4. Suíte Postgres precisa das **duas** DSNs + `STUDIO_BUDGET_TEST_PROOF_FILE`.
5. Nada de `git push`/merge remoto; `origin` intocado.
