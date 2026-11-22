# UX — Faceless Studio Production Workspace

## Objetivo de design
Um produto para criadores sem experiência em edição. **Primeiro o conteúdo, depois a mídia, depois a composição**. A UI não deve expor conceitos como `z_index`, fingerprints, CAS ou FFmpeg a usuários comuns; esses dados ficam em detalhes técnicos opcionais.

## Navegação e linguagem
- Sidebar: Dashboard, Criar vídeo, Roteiro, Narração, Storyboard, Mídias e cenas, Composição, Qualidade, Aprovação, Publicação.
- Contexto persistente: canal, vídeo, modo, versão, etapa, status, custo previsto/real.
- Modo Automático: mínimo de intervenção, mas revisão e aprovação humana obrigatórias.
- Modo Assistido: controles por etapa, sempre com salvamento explícito ou auto-save com status claro.
- Ações irreversíveis/destrutivas exigem confirmação; publicar requer confirmação distinta de aprovar.
- Terminologia: 'Cena' = trecho narrativo; 'Mídia' = imagem/vídeo; 'Narração' = voz; 'Renderizar' = montar arquivo final; 'B-roll' = vídeo/imagem complementar; 'Prévia' = trecho reproduzível.

## Microinterações e feedback
| Ação | Feedback imediato | Consequência | Estado de erro |
|---|---|---|---|
| Salvar roteiro | 'Salvando…' → 'Salvo vN' | invalidar narração/artefatos afetados | conflito vN, recarregar |
| Gerar voz | duração/custo estimados | audio asset e duração real | provider falhou, tentar novamente |
| Trocar mídia | candidato + licença + custo | nova revisão, cache seletivo | licença indisponível, selecionar outro |
| Renderizar | fila, cenas em execução, cache hit | MP4/checksum | falha por cena com retry |
| QA | pass/fail/not_verified por verificação | bloqueio técnico | não confundir ausência com pass |
| Aprovar | checksum + versão exibidos | gate válido só para versão atual | revisão mudou, aprovar de novo |
| Publicar | destino, privacidade, título | publicação idempotente | erro OAuth, canal errado, retry seguro |

## Estados globais
`draft`, `queued`, `running`, `waiting_human`, `failed`, `cancelled`, `succeeded` devem ser **mapeados** dos estados existentes; nomes ilustrativos, não novos enums mandatórios. Sempre mostrar diferença entre 'salvo', 'gerado', 'aprovado' e 'publicado'.

## Regras de acessibilidade
- Contraste de texto 4.5:1, foco visível, labels para campos, botões sem depender de cor/ícone.
- Layout responsivo: 390px, 768px, 1280px; sidebar vira navegação horizontal/colapsável.
- Confirmações com foco gerenciado e escape, validações em texto, não somente toast.
- Progressos reais com status acessível, não estimar porcentagens sem medição.

## Mapa do protótipo
Arquivo `../prototype/index.html`. HTML offline com dados fictícios. Suporta navegação entre dez telas, modos, edição do roteiro, adição/exclusão/reordenação de cenas, troca de mídia, parâmetros de render, revisão e publicação **simuladas**. Não usa APIs, não gera áudio/MP4, não cobra e não publica. Não confundir simulação de QA com teste real.

## Prioridade visual
Reutilizar o shell V3 violeta, hierarquia tipográfica forte, cartões de cena com origem e estado, preview contextual, ações primárias claras e estados honestos. Não copiar branding, imagens ou assets de sites de referência.
