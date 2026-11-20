# Continuação P05–P07 — estado e riscos

## P05: não habilitar publicação automática ainda

- Uma sessão de upload registrada nunca é substituída automaticamente. Resposta
  404/410 ou confirmação de todos os bytes sem ID interrompe a tentativa:
  confira manualmente o canal e reconcilie o ID antes de tentar outro upload.
  Sessão expirada **não prova** que o vídeo não foi criado.
- A tentativa é monotônica, inclusive depois de retry manual; sessão e histórico
  da tentativa são preservados. O claim concorrente de sessão vencida tem teste
  com PostgreSQL, mas lease vencido não cancela o executor anterior: dois
  executores ainda podem atingir o YouTube simultaneamente. Não há garantia
  exatamente-uma-vez entre banco, n8n e YouTube.
- O fluxo ainda exige revisão de autenticação, CSRF e DNS rebinding na API
  local, proteção da URI de upload, timeout/renovação do lease, tratamento de
  falhas dos nós n8n e teste de interrupção real seguro. Não executar novos
  uploads até resolver os riscos; não expor o renderer à rede.
- O desenho antigo do plano P05 que propunha criar nova sessão após 404/410
  foi abandonado por segurança. Retry manual preserva a sessão e não é uma
  autorização para criar outro vídeo sem reconciliação.

## P06 e P07: pendentes

P06 ainda precisa de logs JSON correlacionados, `step_runs`, retomada válida,
retry limitado a falhas transitórias, recuperação de render interrompido e
alertas. P07 ainda precisa da coleta diária idempotente, relatório agregado,
sugestões fundamentadas e testes offline. Analytics exige credencial própria de
leitura no n8n; não há dados reais nem validação com credencial nesta etapa.
O aceite de P07 exige relatório com pelo menos um vídeo real e amostra pequena
explicitada. A validação real no Lenovo continua como pré-requisito da P05.

Não houve push, alteração remota nem novo upload real nesta continuação.
