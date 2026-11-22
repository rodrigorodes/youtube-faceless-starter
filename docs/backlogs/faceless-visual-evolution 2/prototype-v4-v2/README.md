# Mockup v2 — menos fricção

Abra `index.html` diretamente no navegador. O original `prototype-v4` foi preservado.

## Jornadas
- Home: tema → gerar vídeo com os padrões do canal, sem tela intermediária.
- Diretor: tema → storyboard editável, com voz, mídia e B-roll por cena.
- Canal: nome e predefinição → criar. Todas as configurações editoriais, visuais, orçamento e conexões permanecem em seções opcionais expansíveis.
- Providers: resolver sem sair da criação; o rascunho permanece.
- Workspace: cinco áreas; Produção continua acessível em “Ver progresso / Diagnóstico”.
- Aprovar abre preparação da publicação; publicar exige outro clique.

Biblioteca, tendências, desempenho, equipe, fontes, composição e configurações continuam disponíveis.
Simulação em memória: recarregar reinicia os dados. Não conecta serviços, gera mídia nem publica.
Controles representam a proposta de produto, incluindo capacidades ainda não implementadas no backend.

## Validação
`python3 check_v2.py` — Chromium via Playwright; testa as jornadas, correções de estado e overflow em quatro telas móveis.
Os scripts da versão anterior permanecem na pasta original; seus seletores descrevem a jornada antiga.
