# Faceless Studio — Visual Evolution + UX centrada no vídeo · revisão 2

Data: 22/11/2026. Base: `youtube-faceless-starter(5).zip`.
**Entrega: projeto de implementação, documentação e protótipo navegável. Nenhuma funcionalidade de produção implementada nesta revisão.**

Configurar a identidade uma vez por canal, criar vídeos com poucas decisões e editar diretamente a cena que precisa melhorar.

## Começar
Leia [START-HERE](START-HERE.md), [projeto consolidado](PROJECT-V2.md) e abra [protótipo](prototype/index.html).

## Fontes de verdade
1. Este README e [decisões consolidadas](DECISIONS.md).
2. [UX](ux/UX-SPEC.md), [modelo e contratos](architecture/DOMAIN-CONTRACTS.md), [backlog](phases/BACKLOG-V2.md).
3. [VE-07 revisada](phases/VE-07-production-workspace.md) e [aceite](qa/ACCEPTANCE.md).
4. Código real e testes: comprovar antes de alterar. Documentação não comprova comportamento em execução.

`PLAN-VE00-VE06-AS-RECEIVED.md` e `evidence/ve-00-review.md` são históricos preservados. As regras contraditórias desse plano são resolvidas por DECISIONS.md. Documentos substituídos e protótipo anterior estão em `evidence/v1-superseded/`; não são especificações ativas.

## Escopo
- Conta/equipe → canais → vídeos → cenas; versões e execuções dentro do vídeo.
- Criar com tema ou roteiro e padrões do canal. Revisão do roteiro configurável.
- Conteúdo, Edição e Publicação no mesmo vídeo; editor por cena.
- N providers via portas/adapters, capacidades reais, orçamento e seleção avançada.
- Multilayer, mídia híbrida, estilos, QA e regeneração seletiva VE-01–06.
- Fundamentos de autorização e isolamento obrigatórios antes de atender clientes independentes.

Não inclui NLE completo, billing SaaS, editor colaborativo em tempo real, nova SPA obrigatória, segundo renderer ou reescrita de n8n.

## Conteúdo do pacote
| Arquivo | Uso |
|---|---|
| PROJECT-V2.md | Objetivo, experiência e mapa de reuso |
| DECISIONS.md | Decisões e resolução de contradições |
| ux/UX-SPEC.md | Telas, jornadas, estados e acessibilidade |
| architecture/DOMAIN-CONTRACTS.md | Entidades, autorização e contratos conceituais |
| phases/BACKLOG-V2.md | Ordem de implementação e critérios por tarefa |
| phases/VE-07-production-workspace.md | Workspace revisado |
| qa/ACCEPTANCE.md | Jornadas, testes e métricas |
| prototype/index.html | Protótipo offline com dados fictícios |
| prompts/00-master.md | Instrução para implementação incremental |
| evidence/DELIVERY-VALIDATION.md | Verificações desta entrega |

O código-fonte fora desta pasta permanece igual ao ZIP recebido. O ZIP atualizado é uma cópia; não sobreponha alterações locais mais recentes. Para incorporar somente o planejamento, copie esta pasta para o mesmo caminho do repositório.
