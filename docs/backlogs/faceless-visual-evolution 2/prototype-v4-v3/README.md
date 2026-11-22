# Faceless Studio — Mockup V3

Abra `index.html`. Ele carrega `v3.js` da mesma pasta; não requer build.
V1 e V2 permanecem intactas em suas pastas.

## Melhorias
- Ideia e roteiro são escolhas explícitas. Roteiro colado é preservado nas cenas.
- Duração, formato, voz e estilo seguem o canal.
- Storyboard mostra uma cena em foco e permite consultar o roteiro completo.
- Desfazer/refazer edições (30 snapshots em memória).
- Histórico de gerações de voz por cena, com restauração e indicação de áudio desatualizado.
- Antes de renderizar, explica o escopo da atualização e apresenta a estimativa ilustrativa.
- Aprovação prioriza a prévia; verificações técnicas ficam em seção expansível.
- Biblioteca contextual: deste vídeo, do canal, arquivos próprios, stock e geração.
- Providers necessários aparecem primeiro; catálogo completo continua acessível.
- Agendamento futuro em Brasília (UTC−03:00), separado de publicação imediata.

Todas as telas herdadas continuam disponíveis: canais, configurações, biblioteca, tendências, desempenho, fontes, cenas, composição, aprovação, publicação e diagnóstico.

## Limites explícitos
Somente simulação em memória. Recarregar reinicia dados.
Não há áudio real, upload, busca stock, API externa, cobrança ou publicação.
“Ouvir versão” demonstra a ação com mensagem; arquivos próprios apenas demonstram seleção.
Histórico representa texto/voz e estado, não arquivos de áudio reais.
A estimativa é do vídeo completo, não custo incremental.
Nenhuma persistência, favoritos, geração por seleção de palavras ou sincronização remota foi implementada.
O mockup propõe UX; não certifica disponibilidade dessas capacidades no motor atual.

## Testes
`python3 check_v3.py`

Testa roteiro literal, herança, desfazer/refazer, histórico de voz, mídia, confirmação de atualização, QA, publicação, agendamento, rotas e quatro telas em viewport móvel.
Resultado verificado: PASS, sem erros JavaScript capturados.

Referências: `docs/superpowers/specs/2026-11-22-benchmark-ux-jornadas-v2.md`.
