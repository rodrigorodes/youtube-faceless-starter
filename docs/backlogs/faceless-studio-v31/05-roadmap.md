# Roadmap único

Aprovação por fase obrigatória. Não iniciar implementação por este documento sozinho.

**Status em 21/11/2026 (HEAD `e254b61`):** F00 — em revisão (execução sem mudança de runtime;
aceite pendente do responsável técnico). F02 — em revisão (T01–T04 implementadas e testadas,
sem commit; falta validação em navegador). F01, F03–F07 — planejadas. Detalhe e evidências em
[F00](tasks/F00.md), [F02](tasks/F02.md) e [status](evidence/status.md).

| Fase | Objetivo | Gaps | Dependências | Tarefas |
|---|---|---|---|---|
| [F00](tasks/F00.md) Baseline e planejamento | Consolidar a referência factual e aprovar as decisões antes de modificar runtime. | G01–G15 | Nenhuma | 4 |
| [F01](tasks/F01.md) Segurança operacional | Garantir destino autorizado e limites financeiros consistentes antes de habilitar publicação e operações pagas. | G01 G02 G03 | F00 aprovado | 4 |
| [F02](tasks/F02.md) Fundação de Settings | Consolidar UX V3 existente, corrigir intenção do usuário e reorganizar configurações. | G11 G12 G15 | F00; F01 para habilitar operações protegidas | 4 |
| [F03](tasks/F03.md) Configuração efetiva de produção | Resolver e congelar entradas criativas antes do primeiro efeito, mantendo segurança operacional dinâmica. | G06 G08 (pré-requisito de G07) | F00 ADRs; F01 para operações reais; F02.T02 para fluxo UI | 4 |
| [F04](tasks/F04.md) Contexto editorial | Fazer preferências editoriais governarem os geradores, sem relaxar a exigência de evidências. | G05 G13 (decisão) | F03 | 3 |
| [F05](tasks/F05.md) Personalização de estilos | Reutilizar estilos versionados e permitir exceções locais sem efeitos colaterais. | G07 G08 | F03; F02 para UI | 4 |
| [F06](tasks/F06.md) Roteamento de produção | Conectar perfis econômicos às decisões reais, sem introduzir BYOK multi-tenant prematuramente. | G09; G10 explicitamente fora do marco mono-operador | F01 orçamento; F03 configuração | 3 |
| [F07](tasks/F07.md) Validação integrada e release | Comprovar uma produção real controlada, com publicação opcional explicitamente autorizada. | G01–G15 em escopo | F01–F06 concluídas | 4 |

F01 e a parte não operacional de F02 podem avançar em paralelo após F00.

**Onda paralela em execução (21/11/2026):** F01.T01 (identidade YouTube), F01.T03 (escopo/reserva
de orçamento) e F06.T01 (política/catálogo de providers) correm em worktrees isoladas com banco
descartável próprio; `composition.py` tem dono único (F01.T01) e a fiação dos outros streams é
integrada depois. F01.T02 segue sequencial após T01/T03. Detalhe em
[status](evidence/status.md). F03 resolve contratos antes de F04/F05/F06; essas três podem avançar em paralelo com integração coordenada, evitando edições simultâneas nos mesmos arquivos. F07 é gate de release, não substitui testes de cada fase.

## Projetos separados (mesmo repo)

| Projeto | Escopo | Dependência / gate |
|---|---|---|
| B — Audiovisual Engine | G14: transições, captions dinâmicas, motion presets, preview de voz/estilo, thumbnail, avaliação estética | Contratos F03/F05; benchmark audiovisual e custo antes da exposição UI |
| C — SaaS Runtime | G04/G10: identidade autenticada, scoping em queries/jobs, RBAC por recurso, isolamento de secrets, BYOK real | Antes de clientes externos; testes de acesso cruzado e revogação; não ativar via UI |
| Finder / Intelligence | coleta, ranking e contexto editorial independente; provedores plugáveis | Contexto F04, contrato separado; não obrigatório na V3.1 |

## Definition of done por tarefa

Código e docs coerentes; testes de regressão escritos e executados; evidências com comandos/resultado/HEAD; critérios mensuráveis; migração e rollback revisados; sem segredos; sem regressão em comportamento legado; revisão humana. Status: planejado → em execução → em revisão → aceito ou bloqueado. Dono e data definidos em F00 ou no início da tarefa; nunca preencher ficticiamente.
