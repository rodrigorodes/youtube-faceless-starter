# YouTube Faceless — n8n Starter (Windows + macOS)

Ambiente local de automação de vídeos com n8n, Postgres e renderer Python
(FastAPI/FFmpeg). O Studio gera roteiro, mídia, voz, vídeo e prévia de
aprovação; alguns provedores podem ser trocados por configuração. Inclui
versões iniciais de recuperação e analytics.

**Publicação segura:** o fluxo legado V2 que publicava sem aprovação humana
foi removido. O Studio exige aprovação humana obrigatória via painel antes
que qualquer vídeo possa ser reivindicado para publicação no YouTube. A intenção
define destino e visibilidade; publicação pública exige confirmação explícita.
Veja [guia do operador](docs/18-painel.md) e [publicação segura](docs/15-publicacao.md).

## Documentação

- [Configuração no macOS](docs/02-configuracao-macos.md)
- [Configuração no Windows](docs/03-configuracao-windows.md)
- [Variáveis de ambiente](docs/04-variaveis-de-ambiente.md)
- [OpenAI Luna via OAuth (OpenCode)](docs/07-openai-luna-oauth.md)
- [Arquitetura e contratos (gerado)](docs/10-arquitetura.md)
- [Arquitetura operacional: módulos, dados, execução e limites](docs/11-arquitetura-operacional.md)
- [Revisão de arquitetura e prioridades — 24/11/2026](docs/reviews/2026-11-24-architecture-review.md)
- [Modelo de dados (snapshot gerado)](docs/22-modelo-de-dados.md)
- [Fluxo editorial: fontes, roteiro e checagem factual](docs/12-editorial.md)
- [Storyboard e mídia: imagens por cena, cache, licença e custo](docs/13-midia.md)
- [Narração e renderização: vídeo, legenda, QA e fila](docs/14-render.md)
- [Aprovação e publicação: prévia, gate de QA e publicação nativa](docs/15-publicacao.md)
- [Recuperação e analytics: versão inicial e limites](docs/p06-p07-offline.md)
- [Alertas passivos e suas limitações](docs/16-alertas-p06.md)
- [Estender o stúdio: providers e portas](docs/21-extensao.md)

## Pré-requisitos

- Windows 11 com Docker Desktop + WSL2, **ou** macOS com Docker Desktop (Apple Silicon ou Intel)
- Docker Compose v2, 16 GB RAM recomendado, 10 GB livres no disco
- Acesso ao Docker Hub e ao registro de imagens n8n

## Instalação

1. Copie `.env.example` para `.env` (Windows PowerShell: `Copy-Item .env.example .env`; macOS: `cp .env.example .env`).
2. Edite `.env` e configure `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY` e as três variáveis de [autenticação Studio](docs/17-studio-auth.md). Use segredos distintos e não publique o arquivo. Para gerar com OpenCode, configure também o bridge conforme [guia](docs/07-openai-luna-oauth.md).
3. Execute `docker compose up -d --build` no diretório do projeto.
4. Acesse **http://localhost:5678** e crie a conta local de proprietário do n8n.
5. Acesse **http://localhost:8000/docs** para testar o renderizador diretamente.
6. Acesse o **Painel do Faceless Studio** em **http://localhost:8000/studio/panel** (autenticado com `STUDIO_BROWSER_USER` e `STUDIO_BROWSER_PASSWORD`). Crie e gerencie vídeos pelo painel.
7. Os workflows seguros de publicação, analytics e tendências (`03-publish-approved.json`, `04-analytics-daily.json`, `05-trends-daily.json`) podem ser importados no n8n com a credencial `studio_worker`. Veja [guia de autenticação](docs/17-studio-auth.md).

## Teste rápido

O renderer expõe `GET /health` (ex.: `curl -fsS http://localhost:8000/health`). O fluxo
antigo de criação por `POST /videos` foi removido: a rota responde **410 Gone**. Crie e
gerencie vídeos pelo painel do Studio em <http://localhost:8000/studio/panel>.

## Componentes

- **n8n**: agendamento/integração opcional por workflows importados inativos; chama a API Studio.
- **PostgreSQL**: banco do n8n e domínio persistente no schema `studio`, na mesma instância e banco no Compose padrão.
- **Studio FastAPI**: painel HTML/JS servido pelo backend, API, coordenador de produção e executor local de tarefas; FFmpeg/Piper geram vídeo e voz.
- **Bridge OpenCode no host**: integra provedores de texto/imagem por HTTP autenticado.
- **storage/**: mídia, planos/cache de render e cofre de segredos em arquivos. O dump SQL não cobre esses arquivos.

## Contrato do Studio

A criação deixou de ser um `POST /videos` síncrono. O Studio expõe a API autenticada em
`/studio` (projetos → vídeos → roteiro → mídia → render → aprovação → publicação); o
detalhamento está em [10-arquitetura](docs/10-arquitetura.md) e no
[guia de autenticação](docs/17-studio-auth.md).

## Estado e evolução

Já existem persistência, produção por etapas, snapshots de configuração, orçamento,
aprovação versionada, publicação nativa com reconciliação e analytics. A instalação
continua voltada a **um operador local**: canais não equivalem a tenants isolados,
e a fila executora vive no processo da API.

Prioridades fundamentadas, esforço e dependências estão na
[revisão de arquitetura](docs/reviews/2026-11-24-architecture-review.md).
Backlogs e protótipos em `docs/backlogs/` descrevem intenções/histórico; não comprovam
capacidade entregue. Views e tendências são sinais editoriais, não garantia de monetização.

## Segurança e limitações

- Serviços HTTP são expostos apenas em `127.0.0.1`; não abra as portas para a internet sem autenticação, HTTPS e revisão de segurança.
- Proteja `.env` e os volumes do Docker; faça backup de `pg_data`, `n8n_data` e `storage/`.
- O n8n pode mudar parâmetros entre versões. O JSON foi preparado para importação, mas **não foi validado contra uma instância n8n em execução neste ambiente**.
- O endpoint legado `/videos` foi removido (responde **410 Gone**). Configure a [autenticação local](docs/17-studio-auth.md) para o `/studio`; não use o renderer como serviço público.
- O painel web do Faceless Studio fica em `http://localhost:8000/studio/panel`; veja o [guia do operador](docs/18-painel.md) e o [guia de tendências](docs/19-tendencias.md).
- Confirme preços, limites, licenças e requisitos de acesso dos serviços de IA antes de ativar faturamento.
- O n8n é distribuído sob licença fair-code; confira os termos para seu caso de uso.
