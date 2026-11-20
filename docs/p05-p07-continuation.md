# Continuação P05–P07 — estado e riscos

## P05: não habilitar publicação automática ainda

- Uma sessão de upload registrada nunca é substituída automaticamente. Resposta
  404/410 ou confirmação de todos os bytes sem ID interrompe a tentativa:
  confira manualmente o canal e reconcilie o ID antes de tentar outro upload.
  Sessão expirada **não prova** que o vídeo não foi criado.
- O servidor só reivindica vídeos sem publicação anterior. `UPLOADING`, inclusive
  com lease vencido ou liberado, `FAILED` e `PENDING` legado não são reivindicados;
  retry retorna 409. Sessão e tentativa são preservadas. Um lease vencido não
  cancela o executor anterior; esse bloqueio impede novo claim, não cancela
  executores já existentes. Não há exactly-once entre banco, n8n e YouTube.
- A API `/studio` confere `Host` e rejeita `Origin` diferente; a lista padrão
  permite `localhost`, `127.0.0.1` e `renderer`, configurável por
  `STUDIO_ALLOWED_HOSTS`. Host/Origin não autenticam clientes. A autenticação
  local separada exige configuração explícita: veja [17](17-studio-auth.md).
- A URI da sessão é omitida das respostas comuns; o claim autenticado fornece
  dados ao worker. Faltam timeout/renovação do lease, tratamento de
  falhas dos nós n8n e teste de interrupção real seguro. Não executar novos
  uploads até resolver os riscos; não expor o renderer à rede.
- Reconciliação: mantenha o workflow inativo, identifique e pare todos os
  executores antigos, confira no YouTube Studio, no histórico de execuções e
  na sessão preservada se há vídeo/ID, e registre as evidências. Ausência de
  URI ou sessão expirada não prova ausência de upload. Se encontrar ID, valide-o
  antes de registrar o resultado por um canal protegido. Se não houver prova
  conclusiva, mantenha a publicação bloqueada; não apague registros nem altere
  o banco para forçar retry. Ainda não existe procedimento de retomada segura
  implementado, nem botão que autorize novo upload.

### Autenticação local v1

O código prevê Basic para navegador e Bearer separado para worker, mas a
instalação ativa precisa ser provisionada e validada conforme [17](17-studio-auth.md).
Não ativar o workflow 03 por causa dos demais riscos de publicação acima;
não expor o HTTP local à rede.

## P06 e P07: versões iniciais, com pendências

P06 possui registros de etapas, logs do render, retry transitório e retomada
limitada a `ASSETS_READY`; faltam instrumentar outras etapas, alertas e teste
com interrupção real do FFmpeg. P07 possui coleta diária inativa, upsert e
relatório agregado testados offline. Analytics exige credencial própria de
leitura no n8n; não há dados reais nem validação com credencial nesta etapa.
O aceite de P07 exige relatório com pelo menos um vídeo real e amostra pequena
explicitada. A validação real no Lenovo continua como pré-requisito da P05.

Não houve push, alteração remota nem novo upload real nesta continuação.
