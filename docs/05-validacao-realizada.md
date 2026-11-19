# O que foi validado de fato (e o que não foi)

Data: 19/11/2026. Ambiente: **macOS, Apple Silicon (arm64)**, Docker Desktop 29.1.3, `docker compose up -d --build` do zero, sem `GEMINI_API_KEY` (roteiro de demonstração).

## Validado

| Item | Resultado |
|------|-----------|
| Build e subida dos 3 serviços | OK. `postgres` healthy, `n8n` e `renderer` rodando. |
| `GET /health` | `{"status":"ok","ffmpeg":true}` (observação: o `ffmpeg: true` é fixo no código, não testa o binário) |
| `bash scripts/test-create.sh` (renderer direto) | OK em ~1,7 s para 20 s de vídeo |
| MP4 gerado (`ffprobe`) | h264, 720×1280, 25 fps, duração 20,0 s |
| `POST /videos` com `topic` curto | HTTP 422 |
| `GET /videos/xyz/file` (ID inválido) | HTTP 400 |
| Download `video_url` | HTTP 200, `video/mp4` |
| Workflow importado e ativado no n8n 1.123.5 (via API interna do n8n, equivalente ao da interface) | OK: os 3 nós e os parâmetros são aceitos |
| `POST /webhook/faceless-create` (workflow ativo) | HTTP 200 com o manifest, ~1,9 s |
| Webhook com body vazio | HTTP 200 com os padrões aplicados |
| `/webhook-test/...` sem *Listen for test event*, e `/webhook/...` com workflow inativo | HTTP 404 (como documentado) |

## Achados na validação

1. **Erro silencioso pelo n8n.** Com `duration_seconds: 5`, o renderer retorna 422, mas o webhook responde **200 com corpo vazio**. Veja o aviso em [01](01-como-o-workflow-executa.md).
2. **Importação por CLI falha** com este JSON (`versionId` nulo). Use a interface.
3. **`MAX_DURATION_SECONDS`** no compose não é lida pelo código (o limite real é `le=60` no modelo).

## NÃO validado

- **Windows.** Nada foi executado em Windows. O guia [03](03-configuracao-windows.md) segue a documentação oficial do Docker Desktop/WSL2 e o comportamento conhecido do PowerShell, e deve ser conferido na primeira execução real. Os scripts `.ps1` não foram rodados.
- A **interface web do n8n** (clique em *Import from File* e *Listen for test event*): validei o equivalente por API, não a tela.
- **Gemini** com chave real (cota, preço e formato de resposta).
- Execuções simultâneas, vídeos longos (60 s) e o tempo em máquinas mais lentas. Os ~2 s medidos são desta máquina, com roteiro de demonstração.
