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
- A API `/studio` confere `Host` e rejeita `Origin` diferente; a lista padrão
  permite `localhost`, `127.0.0.1` e `renderer`, configurável por
  `STUDIO_ALLOWED_HOSTS`. Isso mitiga CSRF e DNS rebinding no navegador, mas
  **não autentica clientes**: mantenha a API acessível apenas localmente.
- O fluxo ainda exige autenticação na API. A URI da sessão é omitida das
  respostas comuns, mas continua acessível no `claim` ao worker sem autenticação.
  Faltam timeout/renovação do lease, tratamento de
  falhas dos nós n8n e teste de interrupção real seguro. Não executar novos
  uploads até resolver os riscos; não expor o renderer à rede.
- O desenho antigo do plano P05 que propunha criar nova sessão após 404/410
  foi abandonado por segurança. Retry manual preserva a sessão e não é uma
  autorização para criar outro vídeo sem reconciliação.

## P06 e P07: versões iniciais, com pendências

P06 possui registros de etapas, logs do render, retry transitório e retomada
limitada a `ASSETS_READY`; faltam instrumentar outras etapas, alertas e teste
com interrupção real do FFmpeg. P07 possui coleta diária inativa, upsert e
relatório agregado testados offline. Analytics exige credencial própria de
leitura no n8n; não há dados reais nem validação com credencial nesta etapa.
O aceite de P07 exige relatório com pelo menos um vídeo real e amostra pequena
explicitada. A validação real no Lenovo continua como pré-requisito da P05.

Não houve push, alteração remota nem novo upload real nesta continuação.
