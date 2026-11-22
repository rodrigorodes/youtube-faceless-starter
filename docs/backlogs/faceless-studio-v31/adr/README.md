# Registro de decisões do projeto Faceless Studio V3.1

Os arquivos deste diretório usam o prefixo `fs31-` no nome para não colidir com o registro
canônico do repositório em `docs/adr/` (que já tem `ADR-001` do Render Plan).

- No texto dos documentos, "ADR-NNN" refere-se a **FS31-ADR-NNN** (este diretório).
- Referência ao registro do produto deve ser escrita como `docs/adr/ADR-001` e não "ADR-001".

| Arquivo | Assunto | Gaps | Status |
|---|---|---|---|
| [fs31-001-youtube-identity](fs31-001-youtube-identity.md) | Identidade YouTube | G02/G03 | proposto |
| [fs31-002-budget-scope](fs31-002-budget-scope.md) | Escopo de orçamento | G01 | proposto |
| [fs31-003-production-snapshot](fs31-003-production-snapshot.md) | Configuração efetiva e snapshot | G06/G05 | proposto |
| [fs31-004-style-lifecycle](fs31-004-style-lifecycle.md) | Precedência e ciclo de estilos | G07/G08/G15 | proposto |
| [fs31-005-runtime-scope](fs31-005-runtime-scope.md) | Escopo mono-operador e SaaS | G04/G10 | proposto |
| [fs31-006-routing](fs31-006-routing.md) | Perfis e roteamento | G09 | proposto |
| [fs31-007-editorial-pillars](fs31-007-editorial-pillars.md) | Pilares e contexto editorial | G05/G13 | proposto |

Validação técnica de cada proposta contra o HEAD `e254b61`: [decisions-needed](../evidence/decisions-needed.md).
Nenhuma aprovação foi registrada nesta execução; o status só muda por decisão do responsável
técnico, com data e assinatura no próprio arquivo do ADR.