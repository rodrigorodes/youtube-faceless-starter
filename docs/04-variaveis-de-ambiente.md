# Variáveis de ambiente e configuração

Todas ficam no arquivo `.env` na raiz do projeto (copiado de `.env.example`). O `.env` está no `.gitignore`: **nunca o publique**.

| Variável | Obrigatória | Padrão | Para quê |
|----------|-------------|--------|----------|
| `POSTGRES_USER` | não | `n8n` | Usuário do banco interno do n8n |
| `POSTGRES_DB` | não | `n8n` | Nome do banco |
| `POSTGRES_PASSWORD` | **sim** | — | Senha do banco. O `docker compose` aborta se faltar. |
| `N8N_ENCRYPTION_KEY` | **sim** | — | Chave que cifra as credenciais salvas no n8n. O `docker compose` aborta se faltar. |
| `TZ` | não | `America/Sao_Paulo` | Fuso do n8n (também usado como `GENERIC_TIMEZONE`) |
| `GEMINI_API_KEY` | não | vazio | Se definida, o roteiro vem do Gemini. Vazia = texto de demonstração. |
| `GEMINI_MODEL` | não | `gemini-2.5-flash` | Modelo usado na chamada do Gemini |

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
