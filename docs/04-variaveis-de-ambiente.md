# Variáveis de ambiente e configuração

Todas ficam no arquivo `.env` na raiz do projeto (copiado de `.env.example`). O `.env` está no `.gitignore`: **nunca o publique**.

| Variável | Obrigatória | Padrão | Para quê |
|----------|-------------|--------|----------|
| `POSTGRES_USER` | não | `n8n` | Usuário do banco interno do n8n |
| `POSTGRES_DB` | não | `n8n` | Nome do banco |
| `POSTGRES_PASSWORD` | **sim** | — | Senha do banco. O `docker compose` aborta se faltar. |
| `N8N_ENCRYPTION_KEY` | **sim** | — | Chave que cifra as credenciais salvas no n8n. O `docker compose` aborta se faltar. |
| `TZ` | não | `America/Sao_Paulo` | Fuso do n8n (também usado como `GENERIC_TIMEZONE`) |
| `AI_PROVIDER` | não | `auto` | `auto` (Gemini se houver chave, senão demo), `demo`, `gemini`, `vertex` ou `opencode` |
| `GEMINI_API_KEY` | não | vazio | Chave da Gemini API. Em `auto`, se definida o roteiro vem do Gemini; vazia = demonstração. |
| `GEMINI_MODEL` | não | `gemini-2.5-flash` | Modelo usado na chamada do Gemini |
| `VERTEX_PROJECT` | só com `vertex` | vazio | Projeto GCP **seu** (cobrança). Sem padrão de propósito. |
| `VERTEX_LOCATION` | não | `global` | `global` ou região (ex.: `us-central1`) |
| `VERTEX_MODEL` | não | `gemini-2.5-flash` | Modelo no Vertex |
| `OPENCODE_BRIDGE_TOKEN` | só com `opencode` | vazio | Token (16+ caracteres) compartilhado entre renderer e bridge. Veja [07](07-openai-luna-oauth.md). |
| `OPENCODE_MODEL` | não | `openai/gpt-6-luna` | Modelo do bridge: `provider/model[#variante]` |
| `OPENCODE_IMAGE_MODEL` | não | `openrouter/recraft/recraft-v4.1-flash-v2:free` | Modelo de imagem do modo rich; o bridge recusa os que não terminam em `:free` |
| `OPENCODE_ALLOW_PAID_IMAGES` | não | (vazio) | `1` libera modelos de imagem pagos no bridge |
| `STUDIO_TEXT`, `STUDIO_IMAGE`, `STUDIO_VOICE`, `STUDIO_RENDERER` | não | `opencode:openai/gpt-6-luna`, `opencode:openrouter/recraft/recraft-v4.1-flash-v2:free`, `piper:pt_BR-faber-medium`, `ffmpeg:rich` | Provedor padrão de cada porta (`<provedor>:<modelo>`); o `config` do projeto sobrescreve. Em uso: `STUDIO_TEXT` (`opencode`, `demo`) e `STUDIO_IMAGE` (`opencode`, `placeholder`, `stock`, `veo`). `STUDIO_VOICE` (`piper`) e `STUDIO_RENDERER` (`ffmpeg`) |
| `STUDIO_DATABASE_URL` | não | montada pelo compose | Banco do schema `studio`; sem ela o `/studio` responde 503 e o `/videos` segue normal |
| `STUDIO_BROWSER_USER`, `STUDIO_BROWSER_PASSWORD`, `STUDIO_WORKER_TOKEN` | sim para Studio | vazios | Credenciais distintas e persistentes; configuração e limites em [17](17-studio-auth.md). Sem elas `/studio` responde 503. |
| `STUDIO_ALLOWED_HOSTS` | não | `localhost,127.0.0.1,renderer` | Hosts aceitos pela API `/studio`, separados por vírgula. Configuração protege contra DNS rebinding, mas **não substitui autenticação**; não exponha a API à rede. |
| `MAX_COST_USD_PER_VIDEO`, `MAX_COST_USD_PER_MONTH` | não | `0`, `15` | Tetos de gasto com provedores pagos; o `CostGuard` recusa antes de cada chamada de modelo do fluxo editorial |
| `PEXELS_API_KEY` | não | (vazio) | Chave do Pexels para `STUDIO_IMAGE=stock:pexels` |
| `STUDIO_PAID_IMAGE_USD`, `STUDIO_VEO_USD_PER_SECOND` | não | `0.05`, `0.40` | Estimativas de custo por imagem não `:free` e por segundo de Veo (o `CostGuard` usa antes de gerar) |
| `RENDER_CONCURRENCY` | não | `1` | Renders simultâneos do estúdio (1 a 4); o resto fica na fila. `1` evita saturar o Lenovo |
| `STUDIO_SOURCE_ALLOWLIST` | não | `amsterdam-dance-event.nl` | Domínios (vírgula) de onde o estúdio busca fontes; subdomínios incluídos |
| `STUDIO_ALLOW_NAMES` | não | `amsterda` | Nomes próprios aceitos mesmo ausentes da fonte (exônimos em português) |
| `IMAGE_PROVIDER` | não | `opencode` | `opencode` (via bridge) ou `placeholder` (degradê local) |
| `OPENCODE_BRIDGE_PORT` | não | `8787` | Porta do bridge no host |
| `OPENCODE_BRIDGE_URL` | não | `http://host.docker.internal:8787` | Como o container alcança o bridge |
| `GCP_CREDENTIALS_FILE` | só com o override | vazio | Caminho no host do JSON de ADC/service account (montado somente leitura). Veja [06-vertex-ai](06-vertex-ai.md). |

Valores fixos no `docker-compose.yml` (não vêm do `.env`): `MAX_DURATION_SECONDS=60` (ainda **não é lido** pelo código; o limite real é `le=60` em `VideoRequest`), `OUTPUT_DIR=/data/output`, `JOB_DIR=/data/jobs`, `WEBHOOK_URL=http://localhost:5678/`, `N8N_HOST=localhost`, `N8N_PROTOCOL=http`.

## Regras importantes

1. **Use senhas longas e aleatórias, diferentes entre si.** Prefira hexadecimal para evitar caracteres especiais no compose. Como gerar: veja [macOS](02-configuracao-macos.md#2-gerar-as-senhas) e [Windows](03-configuracao-windows.md#2-gerar-as-senhas).
2. **`POSTGRES_PASSWORD` só vale na primeira criação do volume `pg_data`.** Trocar depois no `.env` não altera a senha dentro do banco existente e o n8n deixará de conectar. Para recomeçar do zero: `docker compose down -v` (apaga workflows e conta do n8n).
3. **`N8N_ENCRYPTION_KEY` não pode mudar** depois que existirem credenciais salvas: elas ficam ilegíveis. Guarde a chave (cofre de senhas) junto com o backup do volume `n8n_data`.
4. **`GEMINI_API_KEY`** é opcional. Ao usá-la, confirme preços, cotas e termos do serviço: as chamadas podem ser cobradas.
5. Depois de editar o `.env`, aplique com `docker compose up -d` (recria só o que mudou).

## Portas

| Porta | Serviço | Binding |
|-------|---------|---------|
| 5678 | n8n | `127.0.0.1` (só a própria máquina) |
| 8000 | renderer | `127.0.0.1` (só a própria máquina) |

Se alguma porta já estiver em uso, o `up` falha com *port is already allocated*. Altere o lado esquerdo em `docker-compose.yml` (ex.: `"127.0.0.1:8001:8000"`) e ajuste as URLs dos comandos. Se mudar a do n8n, atualize também `WEBHOOK_URL`.

## Versões fixadas

| Componente | Versão |
|------------|--------|
| n8n | `docker.n8n.io/n8nio/n8n:1.123.5` |
| PostgreSQL | `postgres:16-alpine` |
| Renderer | `python:3.12-slim` + FFmpeg do Debian + fastapi 0.115.12, uvicorn 0.34.2, pillow 11.2.1, httpx 0.28.1, pydantic 2.11.4 |
