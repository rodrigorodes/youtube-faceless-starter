# Configuração no Windows

Alvo: **Windows 11** com **Docker Desktop + WSL2**. Os comandos abaixo são do **PowerShell** (rode na pasta do projeto).

## 1. Pré-requisitos

1. **WSL2** habilitado. Em um PowerShell como administrador:
   ```powershell
   wsl --install
   wsl --status
   ```
   (reinicie se pedir).
2. **Docker Desktop** instalado, com *Use the WSL 2 based engine* marcado (*Settings → General*). Abra e aguarde o estado *running*.
3. Confira:
   ```powershell
   docker --version
   docker compose version
   ```
4. Recomendado: 16 GB de RAM e 10 GB livres. O WSL2 usa memória do Windows; se necessário, limite em `%UserProfile%\.wslconfig`:
   ```ini
   [wsl2]
   memory=6GB
   ```
   e aplique com `wsl --shutdown`.
5. Não precisa instalar Python, FFmpeg nem Node.

### Onde deixar o projeto
- **Pasta normal do Windows** (ex.: `C:\dev\youtube-faceless-starter`): funciona. É o caminho mais simples.
- **Dentro do WSL** (ex.: `~/youtube-faceless-starter`, no sistema de arquivos Linux): o acesso aos arquivos de `storage/` costuma ser mais rápido. Neste caso rode os comandos dentro da distro WSL (siga o guia do macOS, com `openssl`).
- Evite pastas sincronizadas (OneDrive, Dropbox) e caminhos muito longos: podem causar bloqueio de arquivo e lentidão em `storage/`.

## 2. Gerar as senhas

```powershell
Copy-Item .env.example .env

function New-Secret($bytes) {
  $b = New-Object byte[] $bytes
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  -join ($b | ForEach-Object { $_.ToString('x2') })
}
New-Secret 24   # use para POSTGRES_PASSWORD
New-Secret 32   # use para N8N_ENCRYPTION_KEY
```
Abra o `.env` (`notepad .env`) e cole **valores diferentes** nas duas variáveis. Salve como UTF-8 sem formatação extra. Não compartilhe o arquivo.

O roteiro é gerado pelo provider de texto do Studio (`STUDIO_TEXT`); com `opencode`, deixe o bridge do OpenCode rodando. Veja [04-variaveis-de-ambiente](04-variaveis-de-ambiente.md) e [07-openai-luna-oauth](07-openai-luna-oauth.md).

## 3. Subir

```powershell
docker compose up -d --build
docker compose ps
```
O primeiro build baixa imagens e pacotes (alguns minutos). Esperado: `postgres` *healthy*, `n8n` e `renderer` *running*.

Teste do renderer:
```powershell
Invoke-RestMethod http://localhost:8000/health
```
O fluxo antigo de criação por `POST /videos` foi removido (a rota responde **410 Gone**). Crie e gerencie vídeos pelo painel do Studio em <http://localhost:8000/studio/panel> (veja [18-painel](18-painel.md)).

## 4. Configurar o n8n (opcional)

1. Abra <http://localhost:5678> e crie a conta de proprietário (local).
2. O fluxo de criação não depende mais do n8n: crie os vídeos pelo painel do Studio em <http://localhost:8000/studio/panel>.
3. Os workflows seguros de publicação, analytics e tendências (`workflows/03-publish-approved.json`, `04-analytics-daily.json`, `05-trends-daily.json`) podem ser importados com a credencial `studio_worker`; veja [17-studio-auth](17-studio-auth.md).

### Particularidades do PowerShell
- **`curl` no Windows PowerShell 5.1 é um alias de `Invoke-WebRequest`**, não o curl real. Use `Invoke-RestMethod` (como acima) ou `curl.exe` explicitamente.
- **Acentos no PowerShell 5.1**: o corpo em string pode ser enviado em codificação não-UTF-8 e o texto chegar corrompido. Por isso os exemplos usam "sera" sem acento. Para enviar acentos, converta para bytes UTF-8:
  ```powershell
  Invoke-RestMethod -Uri '…' -Method Post -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($body))
  ```
  No PowerShell 7 isso não costuma ser necessário.

## 5. Parar, reiniciar, limpar

```powershell
docker compose stop            # para, mantém tudo
docker compose up -d           # volta
docker compose down            # remove containers, MANTÉM volumes e storage\
docker compose down -v         # remove também pg_data e n8n_data (perde workflows e conta)
```

## 6. Problemas comuns no Windows

| Sintoma | Causa provável | O que fazer |
|---------|----------------|-------------|
| `error during connect … dockerDesktopLinuxEngine` | Docker Desktop fechado ou WSL parado | Abra o Docker Desktop; `wsl --status`; `wsl --shutdown` e reabra |
| WSL2/virtualização indisponível | Virtualização desligada na BIOS ou recurso do Windows desabilitado | Habilite virtualização na BIOS e *Plataforma de Máquina Virtual* e *WSL* nos recursos do Windows |
| `required variable POSTGRES_PASSWORD is missing` | `.env` ausente/vazio | Refaça o passo 2 na pasta do projeto |
| `ports are not available` / `bind: Only one usage of each socket address` (5678 ou 8000) | Porta em uso ou reservada pelo Windows | `netstat -ano \| findstr :8000`; `netsh interface ipv4 show excludedportrange protocol=tcp`; troque a porta no compose |
| `.ps1` bloqueado | *Execution policy* | Veja a nota do passo 3 |
| Acentos quebrados na resposta | Codificação do PowerShell 5.1 | Veja *Particularidades* |
| Antivírus ou OneDrive travando `storage\` | Varredura/sincronização nos arquivos de vídeo | Mova o projeto para fora do OneDrive; exclua a pasta da varredura em tempo real, se a política permitir |
| Webhook 404 | Não está escutando (`/webhook-test`) ou workflow inativo (`/webhook`) | Veja o passo 4 |

Logs: `docker compose logs -f renderer` e `docker compose logs -f n8n`.
