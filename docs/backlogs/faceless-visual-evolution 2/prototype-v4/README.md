# Mockup v4 · Faceless Studio (Rápido + Diretor)

Abra `index.html` no navegador (arquivo único, sem build, sem rede). Dados 100% ilustrativos, estado só em memória.

- Menu: Início, Criar vídeo, Vídeos, Tendências, Desempenho, Biblioteca, Configurações.
- Workspace do vídeo: Cenas & Storyboard (texto + mídia + B-roll + áudio por cena), Composição & Legendas, Qualidade & Aprovação, Publicação YouTube, Fontes & Evidências, Produção.
- Jornada Rápida: Criar vídeo → Piloto automático → abre na aprovação → aprovar → publicar.
- Jornada Diretor: Criar vídeo → Modo Diretor → editar cenas/mídia/voz/legendas → renderizar → aprovar → publicar.
- Botão "Roteiro da demo" (lateral) leva a cada passo das duas jornadas.

Verificação automatizada: `python3 check_mockup.py` (Playwright; percorre todas as rotas e as duas jornadas).
