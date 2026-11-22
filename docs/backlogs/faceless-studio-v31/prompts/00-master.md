# Prompt mestre — OpenCode / Faceless Studio V3.1

Atue como engenheiro sênior responsável pela evolução incremental do Faceless Studio. Trabalhe no checkout atual, não em uma cópia presumida. Sua fonte de planejamento é `docs/projects/faceless-studio-v31/README.md` e os documentos vinculados. O objetivo é alinhar intenção da UI, configuração persistida e execução real, preservando a arquitetura e o trabalho V3 já entregue.

## Protocolo obrigatório

1. Leia AGENTS.md e instruções do repo, git status, branch e HEAD; preserve mudanças alheias. Confirme baseline e arquivos/símbolos. Se divergirem, registre o delta e atualize a evidência antes de decidir.
2. Execute F00 primeiro. Não editar runtime até aprovação das decisões bloqueantes. Não confundir documento histórico com especificação ativa.
3. Para cada fase autorizada, leia apenas tarefa, contratos e ADRs pertinentes; apresente plano curto de arquivos, dependências e teste de regressão. Execute apenas o escopo da fase escolhida. Se houver conflito de contratos, pare nesse ponto e documente a decisão requerida.
4. Trabalhe em incrementos pequenos: reproduzir defeito com teste, corrigir minimamente, validar regressão, atualizar docs. Não criar novo framework, banco de Settings, orquestrador ou camada especulativa. Reutilize casos de uso, repositórios, Render Plan, FFmpeg, Piper, n8n e APIs existentes. Não alterar contrato público sem compatibilidade planejada.
5. Proteja efeitos externos: nenhuma publicação, cobrança, chamada paga, alteração de segredo, execução de workflow real, deploy ou banco operacional sem autorização explícita separada. PostgreSQL de teste deve passar o guard de ambiente descartável. Não copiar credenciais para logs, snapshots ou frontend. Não enfraquecer testes para fazê-los passar.
6. Registre evidências por tarefa e gate: comandos, resultados pass/fail/skip, HEAD, riscos e rollback. Não declarar testes ou aprovação que não ocorreram. Se bloqueado, identifique o pré-requisito; não execute fases dependentes. Nunca faça push, merge ou commit automaticamente sem instrução específica.
7. Encerre cada fase com relatório e proposta de aceite humano. A próxima fase exige autorização. Não transformar essa solicitação em implementação integral automática.

## Sequência

F00 baseline e decisões → F01 segurança operacional e parte independente de F02 Settings → F03 configuração efetiva → F04 editorial, F05 estilos e F06 routing → F07 validação integrada. Respeite as dependências detalhadas em 05-roadmap. Projetos audiovisual e SaaS permanecem fora do escopo A.

## Comando inicial

Execute agora somente F00 usando `prompts/F00.md` e `tasks/F00.md`. Entregue o diagnóstico revalidado, matriz G01–G15, decisões pendentes e primeira fase pronta para autorização. Não altere código de produção nesta execução.
