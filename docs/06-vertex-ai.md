# Vertex AI como provider de roteiro (teste)

O renderer gera o roteiro (4 frases) por um **provider** escolhido em `AI_PROVIDER`:

| Valor | Comportamento |
|-------|---------------|
| `auto` (padrão) | `gemini` se houver `GEMINI_API_KEY`, senão `demo`. É o comportamento anterior. |
| `demo` | Texto fixo de demonstração. Não chama nenhuma API. |
| `gemini` | Gemini API com chave (`GEMINI_API_KEY`). |
| `vertex` | **Vertex AI** (Gemini no Google Cloud), autenticando por *Application Default Credentials* (ADC). Sem chave de API. |

Só o **roteiro** muda. Imagens, voz e vídeo seguem como antes (slides + FFmpeg).

## Atenção: use um projeto seu

`VERTEX_PROJECT` **não tem valor padrão de propósito**. A chamada ao Vertex é **cobrada no projeto informado**, e a credencial
montada no container é a da conta logada. Não use projeto corporativo para este teste pessoal.
Se o `gcloud` da máquina estiver logado em conta/projeto de trabalho, use outro login ou uma service account própria (veja abaixo).

## 1. Preparar o Google Cloud (uma vez)

Com um projeto seu e faturamento ativo:

```bash
gcloud config set project SEU_PROJETO          # confirme com: gcloud config get project
gcloud services enable aiplatform.googleapis.com
```
A conta que vai chamar precisa do papel **Vertex AI User** (`roles/aiplatform.user`) no projeto.
Confirme preço, cotas e disponibilidade do modelo na região antes de usar.

## 2. Credencial (ADC)

**Opção A, recomendada para teste local: login ADC**
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project SEU_PROJETO
```
Arquivo gerado:

| SO | Caminho |
|----|---------|
| macOS / Linux | `~/.config/gcloud/application_default_credentials.json` |
| Windows | `%APPDATA%\gcloud\application_default_credentials.json` |

**Opção B: service account** (conta própria, só com `roles/aiplatform.user`). Crie uma chave JSON, guarde fora do repositório e use esse caminho.
Chaves de service account são credenciais de longa duração: apague-a quando terminar o teste.

O arquivo é montado **somente leitura** no container, e só quando você usa o override `docker-compose.vertex.yml`. Nunca o coloque dentro do projeto nem o publique.

## 3. Configurar o `.env`

```
AI_PROVIDER=vertex
VERTEX_PROJECT=seu-projeto
VERTEX_LOCATION=global
VERTEX_MODEL=gemini-2.5-flash
GCP_CREDENTIALS_FILE=/Users/voce/.config/gcloud/application_default_credentials.json
```
Windows: use barras normais, por exemplo `GCP_CREDENTIALS_FILE=C:/Users/voce/AppData/Roaming/gcloud/application_default_credentials.json`.
O Docker Desktop precisa ter acesso à unidade (*Settings → Resources → File sharing*, ou WSL integration).

`VERTEX_LOCATION=global` usa `aiplatform.googleapis.com`. Uma região (ex.: `us-central1`) usa `<região>-aiplatform.googleapis.com`.
Nem todo modelo está disponível em toda região.

## 4. Subir com o override

```bash
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
bash scripts/test-create.sh        # Windows: .\scripts\test-create.ps1
```
Sem `GCP_CREDENTIALS_FILE`, o compose aborta com mensagem clara. Para não repetir `-f`, defina `COMPOSE_FILE=docker-compose.yml:docker-compose.vertex.yml` no `.env`
(no Windows o separador é `;`, ou defina `COMPOSE_PATH_SEPARATOR=:`).

Para voltar ao modo anterior: `AI_PROVIDER=auto` e suba sem o override.

## 5. Erros e o que significam

O renderer devolve `502` com o tipo do erro (sem detalhes sensíveis) e, quando houver, o status HTTP do Vertex:

| Resposta | Causa provável |
|----------|----------------|
| `500 AI_PROVIDER=vertex requires VERTEX_PROJECT` | `VERTEX_PROJECT` vazio |
| `502 Vertex auth failed: RefreshError` | ADC expirada ou inválida: refaça `gcloud auth application-default login` |
| `502 Vertex auth failed: DefaultCredentialsError` | Override não aplicado ou arquivo não montado |
| `502 Vertex failed: HTTPStatusError (HTTP 403)` | Sem permissão, API desativada ou faturamento inativo |
| `502 Vertex failed: HTTPStatusError (HTTP 404)` | Modelo ou região inexistentes para o projeto |
| `502 Vertex failed: HTTPStatusError (HTTP 429)` | Cota excedida |
| `502 Vertex failed: ValueError` | O modelo não devolveu exatamente 4 strings em JSON |

Lembrete: pelo **n8n**, essas falhas aparecem como HTTP 200 com corpo vazio (veja [01](01-como-o-workflow-executa.md)). Para ver o erro real, chame `POST :8000/videos` direto.

## 6. Testes

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q tests"
```
(ou `pip install -r requirements-dev.txt && pytest` em um venv).

## 7. Validado e não validado

Validado (19/11/2026, macOS arm64):
- 11 testes unitários: seleção de provider, endpoints `global` e regional, cabeçalho `Bearer`, cache e refresh do token, erros 500/502 sem vazar detalhes.
- Stack real: `auto` sem chave gera o vídeo como antes (sem regressão); `vertex` sem projeto devolve 500; `vertex` com credencial **falsa** montada pelo override devolve `502 RefreshError` (prova que o ADC é carregado dentro do container).
- `docker compose config` com e sem `GCP_CREDENTIALS_FILE`.

**Não validado: nenhuma chamada real ao Vertex.** Isso exige um projeto seu com faturamento. Faça o primeiro teste com `duration_seconds` curto e confira o resultado do roteiro e o custo.
