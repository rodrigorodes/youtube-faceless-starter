# Faceless Studio V3.1 — projeto de implementação

**Status:** F00 (baseline e planejamento) executada e **em revisão** para aceite humano; nenhuma
mudança no código de produção foi realizada. F01–F07 continuam planejadas e exigem autorização.
**Baseline:** `main` em `e254b61` no checkout ativo (árvore idêntica ao ZIP `c0cd97c`, que não
tem ancestral comum com o HEAD — ver [baseline](evidence/baseline.md)).
**Data:** 21/11/2026.
**Escopo:** Studio mono-operador com múltiplos canais, segurança operacional, Settings, configuração efetiva, editorial, estilos e routing. SaaS multi-tenant/BYOK operacional e evolução audiovisual avançada são projetos separados.

## Comece aqui

1. O pacote vive em `docs/backlogs/faceless-studio-v31/` (o texto original mandava
   `docs/projects/`; o repositório não tem essa pasta — corrigido na F00).
2. Leia [estado atual](01-current-state.md), [gaps](02-gap-analysis.md), [arquitetura](03-architecture.md) e [contratos de Settings](04-settings-contracts.md).
3. Use [roadmap único](05-roadmap.md) e [validação](06-validation.md).
4. Execute o [prompt mestre](prompts/00-master.md) no OpenCode. Depois execute apenas uma fase autorizada usando seu prompt em `prompts/`.
5. Registre evidências e aprovação de cada gate. Não pule F00 nem execute fases dependentes sem aceite.

## Resultado da F00

- [Inventário revalidado](evidence/inventory.md) — HEAD, telas, símbolos e ambiente.
- [Decisões requeridas](evidence/decisions-needed.md) — validação técnica dos 7 ADRs e o que falta decidir.
- [Testes](evidence/test-results.md) — comandos e resultados reais.
- [Governança](evidence/governance.md) e [documento-fonte](evidence/source-document.md).
- [Falhas pré-existentes](evidence/pre-existing-failures.md) — o que a suíte acusa e não é regressão.
- [Provedores](evidence/providers-audit.md) — o que já é porta/adapter e o que falta para N provedores.
- [Onda paralela 1](evidence/wave-parallel-01.md) — streams A (identidade), B (orçamento) e C (providers).

## F02 entregue (sem commit)

- Estilo real no Create, canal ativo validado no Core, sete áreas de Configurações com tela
  **Avançado** read-only, predefinição do canal com idioma/voz reais. Detalhe e evidências em
  [F02](tasks/F02.md) e [testes](evidence/test-results.md).
- [Status](evidence/status.md) e [changelog](evidence/changelog.md).

## Regras

- Preservar shell V3, APIs/casos de uso existentes, FFmpeg, Piper, Render Plan e n8n como orquestrador.
- Uma fonte de verdade por agregado; nenhum novo framework ou serviço sem ADR aprovado.
- UI simples, controles reais, segurança e orçamento no Core.
- Planejamento não autoriza execução paga, upload, acesso a banco operacional, deploy ou alteração de credenciais.
- Não copiar segredos do ZIP ou de ambientes. Não versionar arquivos `.env`, mídia de clientes ou tokens.

## Índice de diagramas

[Arquitetura](diagrams/01-architecture.md) · [Dependências](diagrams/02-roadmap.md) · [Configuração](diagrams/03-configuration.md) · [Publicação](diagrams/04-youtube.md) · [Orçamento](diagrams/05-budget.md) · [Produção](diagrams/06-production.md) · [Settings](diagrams/07-settings.md) · [Estilos](diagrams/08-styles.md)

## Governança

Responsável técnico e revisor: **a designar** (bloqueia o aceite de F00.T02).
Registro de decisões: [adr/](adr/README.md), com prefixo `fs31-` para não colidir com
`docs/adr/ADR-001` do produto. Registro de mudanças: [evidence/changelog.md](evidence/changelog.md).
Datas e estimativas por tarefa: definir após rebaseline; não inventar compromissos.