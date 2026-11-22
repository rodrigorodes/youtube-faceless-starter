# VE-07 — Workspace por vídeo · revisão 3

Substitui a proposta das dez telas. Status: proposta, sem implementação no aplicativo.

## Resultado
Canal → vídeo → Visão geral / Fontes e roteiro / Narração / Cenas e mídias / Composição / Qualidade / Publicação / Produção. Mesmo Production Coordinator para todos os usuários; revisar roteiro é preferência de pausa, não segundo pipeline. Detalhes de execução ficam secundários.

## Escopo
1. Contexto persistente e rascunho com padrões do canal.
2. Conteúdo: tema/roteiro e revisão opcional antes de cenas.
3. Edição: seleção de cena, texto/voz, mídia e aparência no mesmo espaço.
4. Prévia atual ou antiga explicitamente identificada, ações de atualização seletiva e custos.
5. Histórico recuperável como nova revisão; job atrasado não sobrescreve revisão atual.
6. QA contextual, aprovação de artefato exato e intenção de publicação no canal correto.
7. Resiliência: sair/voltar, erro, cancelamento, retry e conflito entre abas.

## Dependências e implementação
Shell/read-only pode começar após BASE-01. Escrita depende de revisão/CAS/invalidadores. Voz depende de capacidade real. Mídia depende de VE-03/06. Publicação depende de gates existentes verificados. Ver [backlog](BACKLOG-V2.md) para sequência BASE, UX, EDIT, PUB, QA e ISO.

## Aceite
- Novo vídeo herda identidade e pode sobrescrevê-la sem modificar canal.
- Trocar de canal não move o vídeo aberto.
- Alterar cena não dispara chamada paga no salvamento.
- Atualizar seletivamente respeita dependências e apresenta prévia com versão.
- Falha pode ser retomada sem duplicar cobrança ou perder rascunho.
- Aprovação anterior não libera versão alterada.
- Vídeo já publicado conserva publicação histórica ao receber edição local.
- APPROVED não aparece como PUBLISHED.
- N providers não exigem fluxo de UX novo; capacidades filtram opções.
- Backend aplica permissão e escopo; ISO aprovado antes de clientes independentes.

## Fora do escopo
NLE, billing, multiusuário simultâneo em tempo real, clone de voz, TTS word-level sem alinhador, importação SRT com alinhamento automático não comprovado, segundo renderer e reescrita de n8n.

## Cobertura obrigatória
Aplicar FEATURE-COVERAGE-V3 e Settings completo; manter Fontes, tendências, analytics, providers por tarefa, orçamento, equipe e diagnóstico. O workspace reorganiza as etapas anteriores dentro do vídeo, sem eliminar suas telas e ações.
