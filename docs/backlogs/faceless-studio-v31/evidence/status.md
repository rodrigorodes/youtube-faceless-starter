# Registro de execução

Execução em 21/11/2026 no checkout `/Users/rodrigomendes/youtube-faceless-starter`.
HEAD de base `e254b61`; mudanças da F02 **não commitadas** (commit não autorizado).

| Fase | Status | Dono | Revisor | Data | Gate |
|---|---|---|---|---|---|
| F00 | Em revisão (execução técnica concluída) | Operador | A designar | 21/11/2026 | T01/T03 aceitas tecnicamente; T02 com ADRs validados e o operador autorizando o avanço (aprovação formal do responsável técnico segue pendente); T04 aguarda commit |
| F01 | T01/T02/T03 integradas; T04 com contingência pronta | Operador | A designar | 21/11/2026 | parcial: falta decisão de política do `budget_guard` |
| F02 | Em revisão (T01–T04 implementadas e testadas) | Operador | A designar | 21/11/2026 | Falta validação em navegador e aceite humano |
| F03 | T01/T02 integradas; T03 em integração; T04 em stream | Operador | A designar | 21/11/2026 | parcial |
| F04 | T01/T02 integradas; T03 é levantamento de consumidores | Operador | A designar | 21/11/2026 | parcial: campos fora do schema 1 declarados como não governados |
| F05 | T01/T02 integradas; T04 pendente | Operador | A designar | 21/11/2026 | parcial |
| F06 | T01 integrada; T02/T03 pendentes | Operador | A designar | 21/11/2026 | parcial |
| F07 | T01 em andamento (testes V2 modernizados); T02–T04 bloqueadas | Operador | A designar | 21/11/2026 | bloqueado por ambiente/credenciais |

## Autorizações do operador (21/11/2026, 2ª rodada)

- **Commit local: autorizado.** Onda 1–4 commitada em `ea5782f` (147 arquivos), sem push.
- **`budget_guard`: permanece desligado** por decisão do operador; a contingência
  `STUDIO_PUBLICATION_ENABLED` continua sendo o caminho de desligar publicação.
- **Publicação/render reais: não autorizados** — F07.T02–T04 seguem bloqueadas por ambiente,
  credenciais e autorização específica.
- Efeito colateral declarado: o documento-fonte `docs/backlogs/Faceless Studio V3.1 — UX &
  Settings Redesign.md` (antes não rastreado, decisão pendente) entrou no commit por estar sob
  `docs/`. Se a decisão for mantê-lo fora do repositório, remover em commit próprio.

## O que foi autorizado nesta execução

- O operador autorizou seguir sem pausa entre as atividades e definiu três critérios: UX e
  facilidade de configuração/geração em primeiro lugar; capacidade de configurar **N providers**;
  Clean Architecture, nada acoplado ao core.
- Ainda **não** autorizado: publicação real, chamada paga, deploy, alteração de credenciais,
  acesso a banco operacional, commit/push/merge.
- Ordem escolhida: F02 (parte não operacional, permitida em paralelo após F00) antes de F01,
  porque entrega a prioridade declarada e não depende dos gates de segurança.

## Paralelização (21/11/2026)

Três streams isolados por worktree + PostgreSQL descartável próprio, para as fases que o
roadmap permite em paralelo:

| Stream | Escopo | Worktree | Banco | Observação |
|---|---|---|---|---|
| A | F01.T01 identidade YouTube | `…worktrees/f01-identity` | 55436 | dono de `composition.py` |
| B | F01.T03 escopo/reserva de orçamento | `…worktrees/f01-budget` | 55434 | não edita `composition.py`; entrega a fiação |
| C | F06.T01 política de providers | `…worktrees/f06-providers` | 55435 | não edita `composition.py` |

Regras: nenhuma worktree faz commit/push; `docs/backlogs` só é editado na árvore principal;
nenhuma roda a suíte completa; integração por diff em ordem A → B → C seguida de uma suíte
completa única. F01.T02 (n8n/publicação) continua sequencial após A e B.

## Falhas pré-existentes (não corrigidas)

63 falhas na suíte completa quando existe banco — 42 testes de tela desatualizados após o port
V3, 17 dependentes de FFmpeg ausente no host, 2 de contrato gerado com pydantic divergente, 2
sensíveis à ordem. Ver [pre-existing-failures](pre-existing-failures.md).

## Extra fora do backlog (pedido do operador, 21/11/2026)

Lista de Tendências com **paginação real**: filtro e página passam a vir da URL
(`?filtro=…&pagina=N`), com 24 itens por página, contagem por filtro, link de página estável
(preserva canal e período), clamp de página fora do intervalo, filtro desconhecido com vazio
explícito e borda indisponível não focável. O filtro deixou de ser client-side — antes os chips
escondiam cartões só na página atual, o que ficaria inconsistente com paginação. Testes em
`tests/test_trends_v3.py` (8 novos).
