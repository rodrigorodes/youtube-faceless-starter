# P06/P07: base offline e integração pendente

## P06

- `Resume.execute(video_id)` encaminha ao render existente somente em
  `ASSETS_READY`; o render é refeito e os assets existentes são reutilizados.
  Estados anteriores e `FAILED` não têm informação suficiente para retomada
  automática segura. Há endpoint HTTP de resume.
- `PostgresStepRepository` registra tentativas com hash e serializa o início
  por vídeo. `run_step` registra JSON com vídeo, etapa, tentativa e resultado,
  e pula sucesso com a mesma entrada. Use somente quando o resultado da etapa
  for durável e o chamador verificar que continua válido. O render está ligado
  com reutilização desativada: cada job executa novamente e mantém seu hash.
  Na inicialização, registros RUNNING de render são marcados FAILED junto dos
  jobs interrompidos, somente sob a premissa de processo único. Não usar essa
  recuperação com réplicas ou em upload externo.
- `retry_transient` só repete 429, 5xx e `TimeoutError`, com jitter e limite;
  exceções específicas de bibliotecas precisam ser traduzidas pelo adaptador.
  Não aplicar a efeitos externos ambíguos sem idempotência comprovada.
- Ainda faltam integração das demais etapas, logs do pipeline inteiro, alertas
  de bridge/token e teste com processo realmente morto durante FFmpeg. O teste
  simula estado interrompido, retoma o render e verifica os mesmos assets. A
  implementação de render existente marca jobs interrompidos na inicialização
  sob a premissa de um único processo; não é coordenação entre réplicas.

## P07

- `DailyMetric` valida dados sem segredos, e `Analytics.upsert` faz upsert por
  vídeo e data. `Analytics.weekly(start, end)` agrega no banco um intervalo de
  até sete dias e inclui as datas usadas como proveniência.
- Menos de 100 visualizações conhecidas, ou total ausente, é tratado como
  amostra pequena e não gera sugestão. Com 100 ou mais, retorna apenas uma
  sugestão exploratória do mesmo tema, não uma afirmação de desempenho
  superior; 100 é um limiar operacional arbitrário, não significância
  estatística. Dados ausentes podem tornar o agregado incompleto.
- `workflows/04-analytics-daily.json` é inativo e começa com mapa vazio. Antes
  de usá-lo, o humano configura em `Prepare queries` pares `{video_id,
  youtube_id}` conferidos contra a publicação local, e associa ao nó de leitura
  uma credencial OAuth2 genérica **separada**, `youtube_analytics_readonly`,
  com os escopos `https://www.googleapis.com/auth/yt-analytics.readonly` e
  `https://www.googleapis.com/auth/youtube.readonly`. Tokens ficam no n8n.
  A janela UTC de 14 dias termina três dias antes de hoje; dias sem linhas
  não são fabricados. Cada execução refaz upserts idempotentes; uma falha
  parcial pode deixar parte já gravada e a execução seguinte a repete.
- A resposta e os dados de OAuth não foram validados contra n8n/Google reais:
  verificar credencial, compatibilidade dos nós, disponibilidade das métricas,
  fuso e atraso antes de ativar. Retenção maior que 14 dias exige backfill
  separado. A associação automática de vídeos, sugestões à P02 e relatório
  com dados reais continuam pendentes. Não foi feita chamada remota.

O banco de testes desta frente é o contêiner local isolado
`yfs-p06-p07-isolated`, porta 55439 (DSN sem senha:
`postgresql://postgres@host.docker.internal:55439/postgres`). Os testes apagam
o schema `studio`: não apontá-los para um banco com dados importantes.
