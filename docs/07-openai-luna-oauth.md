# OpenAI (modelo Luna) via OAuth, usando o OpenCode

Permite testar o roteiro com **OpenAI `gpt-6-luna`** usando o **login OAuth da sua conta pessoal no OpenCode**, sem chave de API e sem copiar tokens para o projeto.

## Por que um bridge

- O login OAuth do OpenCode dá um token de **assinatura (ChatGPT)**. Ele **não vale** para `api.openai.com` (a API paga exige chave de API), e extrair esse token para uso fora do OpenCode não é um caminho suportado. Este projeto **não lê** o `auth.json` do OpenCode.
- Em vez disso, um pequeno servidor **no seu computador (host)**, `scripts/opencode-bridge.py`, pede a geração de texto ao próprio OpenCode. Os tokens ficam lá dentro.

```
renderer (Docker) --HTTP + Bearer--> opencode-bridge (host, 127.0.0.1:8787) --opencode api--> OpenCode --OAuth--> OpenAI (Luna)
```

Garantias do bridge:
- Só escuta em `127.0.0.1`. Exige `Authorization: Bearer <OPENCODE_BRIDGE_TOKEN>` (comparação em tempo constante).
- Usa o endpoint **stateless de texto** do OpenCode (`/api/experimental/generate/text`): **sem agente, sem ferramentas, sem acesso a arquivos ou shell**. O tema do vídeo (entrada externa) só vira texto de prompt.
- Prompt limitado a 4000 caracteres, uma geração por vez (a segunda recebe 429) e timeout de 90 s.
- Não registra prompts nem cabeçalhos. Erros não vazam detalhes internos.

## Pré-requisitos

1. **OpenCode instalado e logado na OpenAI** (a conta que você quer usar). Confirme: `opencode auth list` (deve listar `OpenAI`) e que o modelo existe: `opencode models | grep luna`.
2. **Python 3.9+ no host** (o bridge usa só a biblioteca padrão).
3. O stack Docker funcionando ([02 macOS](02-configuracao-macos.md) / [03 Windows](03-configuracao-windows.md)).

> **Qual conta?** O bridge usa o provider `openai` do OpenCode. Se você tem mais de um login OpenAI no OpenCode, confirme no OpenCode que o ativo é o pessoal. O bridge não consegue saber de quem é a conta.

## Configurar

No `.env`:

```
AI_PROVIDER=opencode
OPENCODE_BRIDGE_TOKEN=<token aleatório, 16+ caracteres>
OPENCODE_MODEL=openai/gpt-6-luna
```
Gerar o token: macOS `openssl rand -hex 24`; Windows (PowerShell) `-join ((1..24) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })` ou a função `New-Secret 24` do guia do Windows.
Variantes de raciocínio: `OPENCODE_MODEL=openai/gpt-6-luna#low` (também `medium`, `high`...). Evite as variantes `-fast` no teste.

## Executar

1. **Terminal 1, no host**, na pasta do projeto: 
   - macOS: `python3 scripts/opencode-bridge.py`
   - Windows: `py scripts\opencode-bridge.py`

   Saída esperada: `opencode-bridge em http://127.0.0.1:8787 (modelo openai/gpt-6-luna)`.
2. **Terminal 2**: `docker compose up -d --build` e então `bash scripts/test-create.sh` (Windows: `.\scripts\test-create.ps1`).
3. Para parar: `Ctrl+C` no terminal do bridge.

O container alcança o host por `host.docker.internal` (Docker Desktop no Mac e no Windows; no Linux o compose já inclui `extra_hosts: host-gateway`). Se mudar a porta do bridge, ajuste `OPENCODE_BRIDGE_PORT` **e** `OPENCODE_BRIDGE_URL`.

## Erros

| Resposta do renderer | Causa |
|----------------------|-------|
| `500 AI_PROVIDER=opencode requires OPENCODE_BRIDGE_TOKEN` | Token ausente no `.env` do renderer |
| `502 OpenCode bridge failed: ConnectError` | Bridge não está rodando, ou porta/URL errada |
| `502 ... HTTPStatusError (HTTP 401)` | Token do renderer diferente do token do bridge |
| `502 ... HTTPStatusError (HTTP 429)` | Já há uma geração em andamento |
| `502 ... HTTPStatusError (HTTP 502/504)` | O OpenCode falhou ou expirou: veja se `opencode` está logado e com cota de uso |
| `502 ... ValueError` / `JSONDecodeError` | O modelo não devolveu exatamente 4 strings em JSON |

Pelo n8n, essas falhas aparecem como HTTP 200 com corpo vazio ([01](01-como-o-workflow-executa.md)). Chame `POST :8000/videos` direto para ver o erro real.

## Limites e cuidados

- O uso consome a **cota da sua assinatura**, e os termos dela se aplicam. Uso pessoal e de teste, sem automação em volume.
- O bridge depende do endpoint **experimental** `/api/experimental/generate/text` do OpenCode v2 (testado na 2.3.x). Pode mudar.
- É uma ponte de **teste local**: não a exponha na rede nem a rode em servidor.
- Windows não foi executado (veja [05](05-validacao-realizada.md)).

## Validado

macOS arm64, OpenCode 2.3.x, `openai/gpt-6-luna`: 25 testes (provider e bridge); chamada real direta ao OpenCode (3,4 s); fluxo completo com o renderer em Docker chamando o bridge no host (roteiro de 4 frases em 4,8 s, vídeo gerado); 401 sem token; 502 com bridge parado.
