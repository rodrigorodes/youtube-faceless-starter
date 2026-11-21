# Validação real no Lenovo (P01, Task 11)

> Os comandos históricos do Studio exigem adaptação para a
> [autenticação local](17-studio-auth.md); não coloque segredos em comandos ou logs.

> **Status: PENDENTE.** Este roteiro só vira "concluído" quando você colar abaixo a saída real. Eu não consigo executar nada no Lenovo.
> Suposição: Windows 11 + Docker Desktop (WSL2). Se for Linux, use os comandos de `docs/02-configuracao-macos.md` no lugar dos de PowerShell.

Todos os comandos em **PowerShell**, na pasta do repositório. Não cole segredos (valores do `.env`) em lugar nenhum.

## 0. Pré-requisitos
```powershell
docker --version; docker compose version; python --version; git --version
```
Docker Desktop aberto, com WSL2 ativo. Anote as versões na tabela do fim.

## 1. Clonar e configurar
```powershell
git clone https://github.com/rodrigorodes/youtube-faceless-starter.git; cd youtube-faceless-starter
git switch feat/p00-p01          # até a branch ser integrada na main
Copy-Item .env.example .env
```
Preencha `POSTGRES_PASSWORD` e `N8N_ENCRYPTION_KEY` com valores gerados por `python -c "import secrets;print(secrets.token_urlsafe(32))"` (um por variável). Para este teste, **sem bridge nem rede**, deixe no `.env`:
```
AI_PROVIDER=demo
IMAGE_PROVIDER=placeholder
```

## 2. Subir a stack (cronometre o primeiro build)
```powershell
Measure-Command { docker compose up -d --build } | Select-Object TotalMinutes
docker compose ps
```
Esperado: `postgres`, `n8n` e `renderer` em `running`/`healthy`. O build baixa a voz Piper (~61 MB) e o `onnxruntime`.

## 3. `doctor`
```powershell
python scripts\doctor.py
```
Esperado: `Ambiente OK.` (sem o bridge, `OPENCODE_BRIDGE_TOKEN` aparece como aviso, não falha).

## 4. Vídeo de teste (sem rede)
```powershell
Invoke-RestMethod http://localhost:8000/health
.\scripts\test-create.ps1
Invoke-RestMethod -Method Post -Uri http://localhost:8000/videos -ContentType 'application/json' -InFile examples\rich-smoke.json | Select-Object mode, scenes, has_audio, duration_seconds
```
Esperado: `/health` com `studio_db: ok`; o vídeo `slides` gerado; o `rich` com `has_audio: True`.

## 5. API do estúdio
```powershell
$p = Invoke-RestMethod -Method Post -Uri http://localhost:8000/studio/projects -ContentType 'application/json' -Body '{"name":"teste"}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/studio/videos -ContentType 'application/json' -Body (@{project_id=$p.id; topic='ADE 2026'; format='short'} | ConvertTo-Json)
```
Esperado: vídeo em `IDEA`, `privacy: private`.

## 6. Backup
```powershell
python scripts\backup.py backup
python scripts\backup.py verify (Get-ChildItem backups\*.sql.gz | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
```
Esperado: `backup gravado … (verificado)` e `íntegro`.

## 7. Testes (opcional, via Docker, sem instalar Python)
```powershell
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim sh -c "apt-get update -qq >/dev/null; apt-get install -y -qq fonts-dejavu-core >/dev/null; pip install -q -r requirements-dev.txt; python -m pytest -q"
```
Esperado: tudo verde; os testes de banco aparecem como `skipped` sem `STUDIO_TEST_DSN`.

## Registro (preencher)
| Item | Resultado |
|---|---|
| Versões (docker / compose / python / git) | |
| Tempo do primeiro build | |
| `docker compose ps` | |
| `doctor` | |
| `/health` e vídeo `slides` | |
| Vídeo `rich` (`has_audio`) | |
| `/studio` (vídeo em `IDEA`, `private`) | |
| Backup + verify | |
| Testes | |
| Erros encontrados e correção | |

Para cada falha: corrija `docs/03-configuracao-windows.md` (ou o script) e repita só o passo afetado.
