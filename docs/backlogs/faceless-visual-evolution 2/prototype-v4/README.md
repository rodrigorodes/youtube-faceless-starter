# Mockup v4 · Faceless Studio (Rápido + Diretor)

Abra `index.html` no navegador (arquivo único, sem build, sem rede). Dados 100% ilustrativos, estado só em memória.

- Menu: Início, Criar vídeo, Vídeos, Tendências, Desempenho, Biblioteca, Configurações.
- Workspace do vídeo: Cenas & Storyboard (texto + mídia + B-roll + áudio por cena), Composição & Legendas, Qualidade & Aprovação, Publicação YouTube, Fontes & Evidências, Produção.
- Jornada Rápida: Criar vídeo → Piloto automático → abre na aprovação → aprovar → publicar.
- Jornada Diretor: Criar vídeo → Modo Diretor → editar cenas/mídia/voz/legendas → renderizar → aprovar → publicar.
- Criação de canal: assistente em 6 passos (identidade, estratégia, visual e voz, produção, providers e YouTube, revisão). Entra pelo menu do canal ("＋ Novo canal…") ou por Configurações → Canais.
- Providers externos: catálogo por tarefa (texto, voz, imagem, stock, montagem) com custo, rate limit, disponibilidade, teste e credencial só por referência; roteamento por perfil com fallback; YouTube conectado por canal.
- Botão "Roteiro da demo" (lateral) leva a cada passo das três jornadas.

Verificação automatizada (Playwright): `python3 check_mockup.py` (rotas e jornadas Rápida/Diretor) e `python3 check_channel_providers.py` (criação de canal e providers).
