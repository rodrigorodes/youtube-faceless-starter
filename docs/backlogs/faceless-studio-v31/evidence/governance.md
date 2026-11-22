# Governança e registros (F00.T04)

## Registros únicos

| Registro | Fonte única | Duplicatas encontradas | Ação |
|---|---|---|---|
| Roadmap | [05-roadmap](../05-roadmap.md) | nenhum outro roadmap ativo no pacote | manter |
| Matriz de gaps | [02-gap-analysis](../02-gap-analysis.md) | G01–G14 citados no documento-fonte | documento-fonte rebaixado a histórico |
| Decisões | [adr/](../adr/README.md) (FS31-ADR-001..007) | `docs/adr/ADR-001-render-plan.md` (registro do produto) | ADRs do pacote renomeados com prefixo `fs31-` para não colidir |
| Evidência de execução | [evidence/](.) | `docs/backlogs/Faceless_Studio_V2_*/gestao/` (histórico V2) | histórico preservado, não é fonte ativa |

## Backlogs no repositório

- `docs/backlogs/faceless-studio-v31/` — **ativo** (este pacote).
- `docs/backlogs/Faceless_Studio_V2_Projeto_Completo/`,
  `docs/backlogs/Faceless_Studio_V2_DarkPlanner_Provider_Project/`,
  `docs/backlogs/ux/`, `docs/backlogs/writing-block.md` — históricos da V2/UX. Não foram
  apagados nem editados; nenhum deles é roadmap ativo.
- `docs/superpowers/plans`, `docs/superpowers/specs` — planos e specs de fatias já concluídas.

## Integridade do pacote

- Links relativos verificados: 0 quebrados (script de conferência executado sobre todos os `.md`).
- Nomes de arquivo do pacote: ASCII (apenas `fs31-`, `F00..F07`, `01..06` etc.).
- Nenhum segredo, `.env`, mídia de cliente ou token foi copiado para o pacote.
- O pacote ainda **não** está rastreado pelo Git (nenhum commit feito; commit exige autorização).

## Divergência de local

O `README.md` do pacote mandava copiá-lo para `docs/projects/faceless-studio-v31/`. O
operador o colocou em `docs/backlogs/faceless-studio-v31/`. Mantido no caminho real; o
README foi corrigido. `docs/projects/` não existe neste repositório.