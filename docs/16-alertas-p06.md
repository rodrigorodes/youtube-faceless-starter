# Alertas P06 sem acesso a credenciais

## Bridge: observação passiva

Os adaptadores OpenCode de texto e imagem observam as chamadas que já fariam
durante a geração. Não há sondagem nova, envio adicional ou leitura de
credenciais pelo monitor. Se uma conexão falhar ou expirar antes de ser
estabelecida, o log `studio.alerts` emite o evento JSON fixo
`bridge_unreachable`. Não inclui URL, prompt, mensagem de exceção ou token.

`studio.bridge_alerts.status()` retorna:

- `unknown`: nenhuma observação recente;
- `unreachable`: a última tentativa de conexão observada falhou;
- `reachable`: a última observação recebeu uma resposta HTTP, inclusive erro.

O estado vive somente no processo e volta a `unknown` após cinco minutos sem
observação ou após reinicialização. `reachable` não prova que a autenticação,
o modelo ou o serviço downstream funcionam; `unreachable` não prova a causa da
falha. Um timeout de leitura não prova falha de conexão e não produz esse
alerta. Sem tráfego de geração, não há checagem real de disponibilidade. A
interface acima é Python: não foi criada rota HTTP nem integração com um
sistema externo de alertas.

## OAuth: validade desconhecida sem metadado confiável

`check_oauth_expiry(expires_at, now=..., warning_window=...)` aceita somente
um `datetime` com fuso, fornecido por uma fonte confiável de metadados; não
recebe nem inspeciona credenciais. Retorna `unknown` se a data ou o relógio
não tiverem fuso ou se não houver data; caso contrário retorna `expired`,
`expiring` (até sete dias, por padrão) ou `not_expiring`. Os estados
`expired` e `expiring` também emitem, respectivamente, os eventos JSON fixos
`oauth_expired` e `oauth_expiring` no log `studio.alerts`, sem data nem
credenciais. `not_expiring` significa apenas que a data fornecida está fora
da janela, não que a credencial seja válida ou autorizada.

Não existe aqui uma fonte integrada e confiável para a expiração das
credenciais OAuth do n8n ou OpenCode; portanto nenhum alerta automático de
expiração é produzido para elas. Integrar no futuro exigiria uma fonte de
metadados adequada, sem transferir tokens. Não se deve inferir validade a
partir de 401, tempo decorrido, presença de configuração ou sucesso do bridge.
