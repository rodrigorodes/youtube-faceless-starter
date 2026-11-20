# P06/P07: base offline e integração pendente

## P06

- `Resume.execute(video_id)` encaminha ao render existente somente em
  `ASSETS_READY`; o render é refeito e os assets existentes são reutilizados.
  Estados anteriores e `FAILED` não têm informação suficiente para retomada
  automática segura. O endpoint HTTP ainda precisa ser conectado.
- `PostgresStepRepository` registra tentativas com hash e serializa o início
  por vídeo. `run_step` registra JSON com vídeo, etapa, tentativa e resultado,
  e pula sucesso com a mesma entrada. Use somente quando o resultado da etapa
  for durável e o chamador verificar que continua válido; ainda não foi ligado
  às etapas existentes. RUNNING após processo morto não é liberado
  automaticamente: confirmação de que o processo antigo terminou e política
  de recuperação ainda são necessárias. Não usar em upload externo.
- `retry_transient` só repete 429, 5xx e `TimeoutError`, com jitter e limite;
  exceções específicas de bibliotecas precisam ser traduzidas pelo adaptador.
  Não aplicar a efeitos externos ambíguos sem idempotência comprovada.
- Ainda faltam integração das etapas, logs do pipeline inteiro, alertas de
  bridge/token e teste de interrupção real com reaproveitamento integral. A
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
- Para integração, expor `UseCases.analytics.upsert(DailyMetric)` e
  `UseCases.analytics.weekly(start, end)` via rotas com a proteção adequada.
  Implementar coleta diária no n8n com credencial separada e escopos
  `yt-analytics.readonly` e `youtube.readonly`; tokens não entram no renderer.
  Falta associar sugestões à P02, tratar atraso das métricas e validar com
  dados reais. Nenhuma coleta real ou chamada remota foi realizada.

O banco de testes desta frente é o contêiner local isolado
`yfs-p06-p07-isolated`, porta 55439 (DSN sem senha:
`postgresql://postgres@host.docker.internal:55439/postgres`). Os testes apagam
o schema `studio`: não apontá-los para um banco com dados importantes.
