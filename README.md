# YouTube Faceless — n8n Starter (Windows + macOS)

Projeto inicial para montar um ambiente local de automação de vídeos. **MVP demonstrável**, não uma fábrica de vídeos pronta para publicação: gera um MP4 vertical com slides de texto (sem narração), usando FFmpeg. Com `GEMINI_API_KEY`, usa Gemini para redigir os slides; sem chave, utiliza texto de demonstração. O n8n recebe um pedido por webhook e chama o renderizador. **Não publica no YouTube nem gera imagens/voz reais nesta versão.**

## Documentação

- [Como o workflow é executado](docs/01-como-o-workflow-executa.md)
- [Configuração no macOS](docs/02-configuracao-macos.md)
- [Configuração no Windows](docs/03-configuracao-windows.md)
- [Variáveis de ambiente](docs/04-variaveis-de-ambiente.md)
- [O que foi validado (e o que não)](docs/05-validacao-realizada.md)
- [Vertex AI como provider de roteiro](docs/06-vertex-ai.md)
- [OpenAI Luna via OAuth (OpenCode)](docs/07-openai-luna-oauth.md)
- [Publicar no YouTube (workflow V2)](docs/08-publicar-no-youtube.md)
- [Modo rich: imagens, narração e música](docs/09-modo-rich-imagens-voz-musica.md)
- [Arquitetura e contratos (gerado)](docs/10-arquitetura.md)
- [Validação real no Lenovo (roteiro)](docs/11-validacao-lenovo.md)
- [Fluxo editorial: fontes, roteiro e checagem factual](docs/12-editorial.md)
- [Storyboard e mídia: imagens por cena, cache, licença e custo](docs/13-midia.md)

## Pré-requisitos

- Windows 11 com Docker Desktop + WSL2, **ou** macOS com Docker Desktop (Apple Silicon ou Intel)
- Docker Compose v2, 16 GB RAM recomendado, 10 GB livres no disco
- Acesso ao Docker Hub e ao registro de imagens n8n

## Instalação

1. Copie `.env.example` para `.env` (Windows PowerShell: `Copy-Item .env.example .env`; macOS: `cp .env.example .env`).
2. Edite `.env` e configure **duas senhas longas e diferentes** para `POSTGRES_PASSWORD` e `N8N_ENCRYPTION_KEY`. Não publique o arquivo.
3. Execute `docker compose up -d --build` no diretório do projeto.
4. Acesse **http://localhost:5678** e crie a conta local de proprietário do n8n.
5. Acesse **http://localhost:8000/docs** para testar o renderizador diretamente.
6. No n8n, importe `workflows/01-create-short.json` via **Import from File**. Salve e clique em **Listen for test event** no nó Webhook.
7. Em outro terminal, teste o webhook:

```bash
curl -X POST 'http://localhost:5678/webhook-test/faceless-create' \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Como será a IA em 2030?","duration_seconds":20,"style":"documentary"}'
```

No Windows PowerShell, use `Invoke-RestMethod` em vez de `curl`:

```powershell
$body = @{topic="Como sera a IA em 2030?";duration_seconds=20;style="documentary"} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5678/webhook-test/faceless-create' -Method Post -ContentType 'application/json' -Body $body
```

O retorno contém `video_url` apontando para o MP4 em `http://localhost:8000/videos/<id>/file`. O arquivo também fica em `storage/output/`.

**Observação:** o webhook de teste funciona apenas enquanto o n8n está escutando. Para utilizar `/webhook/faceless-create`, ative o workflow. A renderização é síncrona e deve ser usada apenas para testes locais curtos.

## Teste sem n8n

macOS/Linux: `bash scripts/test-create.sh`

Windows: `./scripts/test-create.ps1`

## Componentes

- **n8n**: orquestração visual e histórico de execuções
- **PostgreSQL**: banco interno do n8n (não é ainda o banco de domínio dos vídeos)
- **Renderer FastAPI + FFmpeg**: gera MP4 demonstrativo, expõe API HTTP
- **storage/**: arquivos e manifests persistidos no host

## Contrato inicial

`POST /videos`:

```json
{"topic":"Como funciona a IA?","format":"short","duration_seconds":30,"style":"documentary"}
```

Resposta: `{id, topic, status, script, duration_seconds, video_url, note}`.

## Próximas fases

1. P01: persistir pedidos, estados e custos em banco de domínio separado; criar fila de jobs assíncrona.
2. P02: roteiro com fontes verificáveis, storyboard estruturado e revisão editorial.
3. P03: imagens reais (Gemini Image/stock), voz TTS, licenças e legendas.
4. P04: templates 9:16 e 16:9, transições, áudio, normalização e QC.
5. P05: aprovação humana persistente e YouTube OAuth/upload privado.
6. P06: limites de gasto, retries seguros, idempotência, métricas e analytics.

## Segurança e limitações

- Serviços HTTP são expostos apenas em `127.0.0.1`; não abra as portas para a internet sem autenticação, HTTPS e revisão de segurança.
- Proteja `.env` e os volumes do Docker; faça backup de `pg_data`, `n8n_data` e `storage/`.
- O n8n pode mudar parâmetros entre versões. O JSON foi preparado para importação, mas **não foi validado contra uma instância n8n em execução neste ambiente**.
- O renderizador é demonstrativo, usa execução síncrona, sem fila ou autenticação interna, e gera slides silenciosos. Não use como serviço público.
- Confirme preços, limites, licenças e requisitos de acesso dos serviços de IA antes de ativar faturamento.
- O n8n é distribuído sob licença fair-code; confira os termos para seu caso de uso.
