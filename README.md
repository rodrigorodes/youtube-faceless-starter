# YouTube Faceless — n8n Starter (Windows + macOS)

Ambiente local de automação de vídeos com n8n, Postgres e renderer Python
(FastAPI/FFmpeg). O Studio gera roteiro, mídia, voz, vídeo e prévia de
aprovação; alguns provedores podem ser trocados por configuração. Inclui
versões iniciais de recuperação e analytics.

**Publicação segura:** o fluxo legado V2 que publicava sem aprovação humana
foi removido. O Studio exige aprovação humana obrigatória via painel antes
que qualquer vídeo possa ser reivindicado para publicação privada no YouTube.
Veja [guia do operador](docs/18-painel.md) e [publicação segura](docs/15-publicacao.md).

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
- [Narração e renderização: vídeo, legenda, QA e fila](docs/14-render.md)
- [Aprovação e publicação: prévia, fila, upload retomável](docs/15-publicacao.md)
- [Recuperação e analytics: versão inicial e limites](docs/p06-p07-offline.md)
- [Alertas passivos e suas limitações](docs/16-alertas-p06.md)

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
6. Acesse o **Painel do Faceless Studio** em **http://localhost:8000/studio/panel** (autenticado com `STUDIO_BROWSER_USER` e `STUDIO_BROWSER_PASSWORD`). Crie e gerencie vídeos pelo painel.
7. Os workflows seguros de publicação, analytics e tendências (`03-publish-approved.json`, `04-analytics-daily.json`, `05-trends-daily.json`) podem ser importados no n8n com a credencial `studio_worker`. Veja [guia de autenticação](docs/17-studio-auth.md).

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
- O endpoint legado `/videos` não tem autenticação. Para `/studio`, configure a [autenticação local](docs/17-studio-auth.md); não use o renderer como serviço público.
- O painel web do Faceless Studio fica em `http://localhost:8000/studio/panel`; veja o [guia do operador](docs/18-painel.md) e o [guia de tendências](docs/19-tendencias.md).
- Confirme preços, limites, licenças e requisitos de acesso dos serviços de IA antes de ativar faturamento.
- O n8n é distribuído sob licença fair-code; confira os termos para seu caso de uso.
