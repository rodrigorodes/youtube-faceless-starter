# Faceless Studio — Projeto consolidado · revisão 3

22/11/2026 · Base: youtube-faceless-starter(5).zip + propostas V3/V3.1 + Visual Evolution VE-00–07.

**Correção de direção:** preservar funcionalidades e visual existentes; melhorar a organização do fluxo sem reduzir o produto. A revisão 2 foi rejeitada pelo usuário por omitir funcionalidades e configurações avançadas. Esta revisão a substitui.

Entrega: documentação/backlog e protótipo interativo offline. **Código de produção preservado; as funcionalidades demonstradas não estão integradas às APIs.**

## Abrir
- [Comece aqui](START-HERE.md)
- [Protótipo completo](prototype/index.html)
- [Projeto atualizado](PROJECT-V3.md)
- [Matriz de cobertura funcional](FEATURE-COVERAGE-V3.md)
- [UX e navegação](ux/UX-SPEC.md)
- [Backlog de implementação](phases/BACKLOG-V2.md)
- [Validação desta entrega](evidence/DELIVERY-VALIDATION.md)

## O que volta a ficar visível
| Produto | Áreas |
|---|---|
| Navegação principal | Início, Criar vídeo, Vídeos, Tendências e ideias, Desempenho, Biblioteca, Configurações |
| Dentro de cada vídeo | Visão geral, Fontes e roteiro, Narração, Cenas e mídias, Composição, Qualidade, Publicação, Produção |
| Configurações | Canais, Estratégia editorial, Marca e estilo, Produção e orçamento, Conexões e providers, Conta e equipe, Avançado e diagnóstico |

Canal ativo atravessa todas as áreas. Os recursos não são excluídos por não caberem no menu inicial. As etapas de produção pertencem ao vídeo, e as preferências reutilizáveis pertencem ao canal/conta.

## Precedência
Instruções atuais do usuário → README/PROJECT-V3/FEATURE-COVERAGE-V3 → DECISIONS/UX-SPEC/contratos/backlog → fontes históricas. Documentos substituídos estão em evidence/v1-superseded e evidence/v2-superseded. PLAN-VE00-VE06-AS-RECEIVED e ve-00-review permanecem históricos intactos. O arquivo PROJECT-V2 agora é somente um encaminhamento.

## Aplicar no repositório
Extrair em pasta separada. Comparar e incorporar `docs/backlogs/faceless-visual-evolution 2/` no checkout real. Não sobrescrever código local mais recente com a cópia de baseline. Esta entrega altera somente essa pasta; SQL, Python, testes e workflows originais continuam preservados.
