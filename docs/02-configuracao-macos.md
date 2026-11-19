# Configuração no macOS

Funciona em Apple Silicon (arm64) e Intel. As imagens usadas (`postgres:16-alpine`, `n8n`, `python:3.12-slim`) têm variantes arm64 e amd64; o Docker escolhe sozinho.

## 1. Pré-requisitos

- **Docker Desktop** para Mac, aberto e com o ícone indicando *running*.
- Docker Compose v2 (já vem no Docker Desktop). Confira:
  ```bash
  docker --version
  docker compose version
  ```
- Recomendado: 16 GB de RAM no Mac e 10 GB livres. Em *Docker Desktop → Settings → Resources*, deixe pelo menos 4 GB de memória para o Docker.
- Não precisa instalar Python, FFmpeg nem Node: tudo roda nos containers.
- Acesso à internet para baixar imagens (Docker Hub e `docker.n8n.io`) e pacotes (Debian, PyPI) no primeiro build.

## 2. Gerar as senhas

```bash
cp .env.example .env
openssl rand -hex 24   # use para POSTGRES_PASSWORD
openssl rand -hex 32   # use para N8N_ENCRYPTION_KEY
```
Edite o `.env` (qualquer editor) e cole **valores diferentes** nas duas variáveis. Ou, de uma vez:
```bash
sed -i '' "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/; s/^N8N_ENCRYPTION_KEY=.*/N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)/" .env
```
> No macOS o `sed -i` exige o `''` depois do `-i`. Não imprima nem compartilhe o `.env`.

Opcional: preencha `GEMINI_API_KEY` para o roteiro vir do Gemini. Veja [04-variaveis-de-ambiente](04-variaveis-de-ambiente.md).

## 3. Subir

```bash
docker compose up -d --build
docker compose ps
```
O primeiro build baixa imagens e pacotes (alguns minutos). Esperado: `postgres` *healthy*, `n8n` e `renderer` *running*.

Teste rápido do renderer (sem n8n):
```bash
curl -fsS http://localhost:8000/health
bash scripts/test-create.sh
```
O retorno traz `video_url`. Abra a URL no navegador ou veja o arquivo em `storage/output/`.

## 4. Configurar o n8n

1. Abra <http://localhost:5678> e crie a conta de proprietário (local).
2. **Import from File** → `workflows/01-create-short.json`.
3. Para testar: clique em **Listen for test event** no nó Webhook e, em outro terminal:
   ```bash
   curl -X POST 'http://localhost:5678/webhook-test/faceless-create' \
     -H 'Content-Type: application/json' \
     -d '{"topic":"Como será a IA em 2030?","duration_seconds":20,"style":"documentary"}'
   ```
4. Para usar `/webhook/faceless-create`, ative o workflow (toggle *Active*).

Como o fluxo funciona por dentro: [01-como-o-workflow-executa](01-como-o-workflow-executa.md).

## 5. Parar, reiniciar, limpar

```bash
docker compose stop            # para, mantém tudo
docker compose up -d           # volta
docker compose down            # remove containers, MANTÉM volumes e storage/
docker compose down -v         # remove também pg_data e n8n_data (perde workflows e conta)
```

## 6. Problemas comuns no macOS

| Sintoma | Causa provável | O que fazer |
|---------|----------------|-------------|
| `Cannot connect to the Docker daemon` | Docker Desktop fechado | Abra o Docker Desktop e aguarde |
| `required variable POSTGRES_PASSWORD is missing` | `.env` ausente ou vazio | Refaça o passo 2 na pasta do projeto |
| `port is already allocated` (5678 ou 8000) | Outro processo usa a porta | `lsof -iTCP:8000 -sTCP:LISTEN`; encerre-o ou troque a porta no compose |
| n8n não conecta no banco depois de mudar a senha | Senha do Postgres só vale na criação do volume | Restaure a senha antiga ou `docker compose down -v` (apaga dados do n8n) |
| Webhook 404 em `/webhook-test/...` | Não está escutando | Clique em *Listen for test event* de novo (vale para 1 chamada) |
| Webhook 404 em `/webhook/...` | Workflow inativo | Ative o workflow |
| Build lento ou memória insuficiente | Recursos do Docker baixos | Aumente em *Settings → Resources* |
| Erro no `docker compose build` ao baixar pacotes | Rede/VPN/proxy | Teste fora da VPN; configure proxy no Docker Desktop |

Logs: `docker compose logs -f renderer` e `docker compose logs -f n8n`.
