# Autenticação local do Studio

O Studio exige três variáveis não vazias no ambiente do renderer:
`STUDIO_BROWSER_USER`, `STUDIO_BROWSER_PASSWORD` e `STUDIO_WORKER_TOKEN`.
O usuário não pode conter `:` e a senha e o token devem ser diferentes.
Sem configuração válida, `/studio` responde 503; `/videos` e `/health`
continuam independentes. Escolha uma senha e um token distintos, aleatórios e
longos (por exemplo, pelo menos 32 bytes de entropia), sem reutilizar outros
segredos. Não os registre em tickets, logs, comandos de shell ou no Git.

Guarde os valores persistentemente em `.env` privado, com acesso restrito ao
usuário local. Configure as três variáveis antes de recriar o renderer pelo
Compose; alterar o arquivo não atualiza um container já existente. Não altere
os valores de PostgreSQL ou `N8N_ENCRYPTION_KEY`: esta última precisa permanecer
persistente para que o n8n consiga ler suas credenciais salvas.

No navegador acesse `http://localhost:8000/studio/...` e informe o usuário e a
senha quando solicitados. O navegador nunca recebe o token do worker. Os
pedidos de alteração com Basic precisam enviar `Origin` exata do mesmo host,
porta e esquema; ferramentas sem `Origin` devem usar a credencial de worker.
O guard de host continua ativo; `STUDIO_ALLOWED_HOSTS` não autentica usuários.

No n8n crie uma credencial **Header Auth** chamada `studio_worker`, com nome
de cabeçalho `Authorization` e valor `Bearer ` seguido do token provisionado
em `STUDIO_WORKER_TOKEN`. O valor fica na credencial do n8n, nunca no JSON.
Depois de importar os workflows 03 e 04 inativos, selecione essa credencial
em todos os seus nós HTTP que chamam o renderer; a associação pelo nome pode
precisar de seleção manual no n8n. Mantenha as credenciais OAuth do YouTube
separadas. Não ative workflows até verificar configuração e autorizações.
Na rotação, atualize renderer e credencial n8n de forma coordenada: requisições
com o token anterior falharão e execuções em andamento podem precisar retomar.

O HTTP Basic e o Bearer trafegam sem criptografia no HTTP local e na rede
Docker. Esta configuração é apenas para máquina e rede Docker confiáveis:
não exponha as portas ou a rede a outros hosts/usuários, e use TLS com proxy
corretamente configurado antes de qualquer acesso remoto. Outros processos com
acesso à máquina, Docker, ambiente ou credenciais n8n podem ler os segredos.
Não há limitação de tentativas ou contas individuais. Não use esta v1 como
autenticação multiusuário ou para exposição pública. Ambas as credenciais têm
acesso a todas as rotas Studio: o token do worker não restringe privilégios e
deve ser protegido como a senha do navegador. A autenticação Studio não protege
webhooks do n8n nem os endpoints legados `/videos`.

O workflow 03 processa a URI de sessão de upload: ela pode ficar registrada
no histórico de execuções do n8n e no banco do Studio. Trate ambos, seus backups
e os acessos administrativos como sensíveis; não compartilhe execuções nem
reproduza a URI em logs ou capturas de tela. Uma credencial ausente no JSON
do workflow não implica ausência de dados sensíveis durante a execução.
