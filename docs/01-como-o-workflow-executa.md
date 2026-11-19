# Como o workflow é executado

Este documento responde: **o que roda, onde, em que ordem, e o que acontece quando algo falha.**
Vale para Windows e macOS: a execução é idêntica, porque tudo roda em containers Docker.
O que muda por sistema operacional está em [02-macos](02-configuracao-macos.md) e [03-windows](03-configuracao-windows.md).

## 1. Visão geral

```
 Você (curl / PowerShell / n8n UI)
        │  HTTP POST
        ▼
┌──────────────────────────── Docker Compose (rede interna) ───────────────────────────┐
│                                                                                       │
│  n8n  (:5678)  ── workflow "Faceless V1 - Create Demo Short" ──┐                      │
│   │  Webhook → HTTP Request → Respond to Webhook               │                      │
│   │                                                            ▼                      │
│   │                                          renderer (:8000)  FastAPI + FFmpeg       │
│   │                                            │  1. gera roteiro (Gemini ou demo)    │
│   │                                            │  2. desenha 4 slides PNG (Pillow)    │
│   │                                            │  3. FFmpeg: PNG → MP4 por cena       │
│   │                                            │  4. FFmpeg: concatena em 1 MP4       │
│   ▼                                            ▼                                      │
│  postgres (interno)                       ./storage  (jobs/ e output/ no host)        │
│  (só guarda dados do n8n)                                                             │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

Três containers, definidos em `docker-compose.yml`:

| Serviço    | Papel                                                        | Porta no host (somente 127.0.0.1) |
|------------|--------------------------------------------------------------|-----------------------------------|
| `postgres` | Banco **interno do n8n** (workflows, execuções, credenciais). Não guarda vídeos. | não exposta |
| `n8n`      | Orquestrador. Recebe o webhook e chama o renderer.           | 5678 |
| `renderer` | API que gera o MP4. Pode ser chamada **sem** o n8n.          | 8000 |

## 2. Dois jeitos de disparar

### A) Direto no renderer (sem n8n)
Útil para validar o ambiente. Não depende de importar workflow.

```
POST http://localhost:8000/videos
```
Scripts prontos: `scripts/test-create.sh` (macOS/Linux) e `scripts/test-create.ps1` (Windows).

### B) Pelo n8n (o workflow de fato)
```
POST http://localhost:5678/webhook-test/faceless-create   (modo teste)
POST http://localhost:5678/webhook/faceless-create        (workflow ativo)
```

| URL | Quando funciona | Observação |
|-----|-----------------|------------|
| `/webhook-test/...` | Só depois de clicar em **Listen for test event** no nó Webhook | Atende **uma** chamada por clique. Execução aparece no editor. |
| `/webhook/...` | Só com o workflow **ativo** (toggle *Active* ligado) | Uso "de produção". Execução fica no histórico (*Executions*). |

## 3. Passo a passo de uma execução (workflow `01-create-short.json`)

O workflow tem **3 nós**:

1. **New Video Webhook** (`POST faceless-create`, resposta pelo nó *Respond to Webhook*).
   Recebe `{"topic": "...", "duration_seconds": 20, "style": "documentary"}`.
2. **Render Demo Video** (HTTP Request → `http://renderer:8000/videos`, timeout 240 s).
   Monta o JSON com valores padrão (`topic` = "Como funciona a inteligência artificial?", `duration_seconds` = 30,
   `style` = `documentary`) e envia ao renderer.
   > Dentro do Compose o host é `renderer`, **não** `localhost`. `localhost` dentro do container do n8n seria o próprio n8n.
3. **Return Video Manifest** devolve ao chamador o JSON retornado pelo renderer.

O renderer (`renderer/app/main.py`, endpoint `POST /videos`) executa, **de forma síncrona**:

1. Valida o pedido (`topic` 3–300 caracteres; `format` só `short`; `duration_seconds` 10–60; `style` até 80).
2. Cria `storage/jobs/<id>/` (id = UUID hex de 32 caracteres).
3. **Roteiro**: se `GEMINI_API_KEY` estiver definida, chama o Gemini pedindo exatamente 4 frases em JSON
   (cada uma cortada em 260 caracteres). Se não houver chave, usa 4 frases fixas de demonstração.
   Resposta inválida ou erro de API → HTTP **502**.
4. Desenha 4 PNGs 720×1280 com Pillow (fonte DejaVu Sans do container).
5. FFmpeg converte cada PNG em um MP4 de `duration_seconds / 4` segundos (25 fps, H.264, sem áudio).
6. FFmpeg concatena os 4 clipes (`-c copy`) em `storage/output/<id>.mp4`.
7. Grava `storage/jobs/<id>/manifest.json` e devolve:

```json
{
  "id": "…32 hex…",
  "topic": "…",
  "status": "AWAITING_APPROVAL",
  "script": ["…", "…", "…", "…"],
  "duration_seconds": 20,
  "video_url": "http://localhost:8000/videos/<id>/file",
  "note": "Demo silent slideshow; not yet voice/image generation or YouTube upload"
}
```

> `status: AWAITING_APPROVAL` é só um rótulo. **Ainda não existe fluxo de aprovação** (previsto na fase P05).

### Endpoints do renderer

| Método | Rota | Função |
|--------|------|--------|
| GET | `/health` | Verificação simples (`{"status":"ok"}`) |
| POST | `/videos` | Cria o vídeo (síncrono) |
| GET | `/videos/{id}` | Lê o manifest salvo |
| GET | `/videos/{id}/file` | Baixa o MP4 |
| GET | `/docs` | Swagger UI para testar no navegador |

## 4. Onde ficam os dados

| O quê | Onde | Persistência |
|-------|------|--------------|
| MP4 final | `storage/output/<id>.mp4` (no seu disco) | Sim, **nunca é apagado automaticamente** |
| PNGs, clipes, manifest | `storage/jobs/<id>/` | Sim, idem |
| Workflows, credenciais, execuções do n8n | volume Docker `n8n_data` + banco no volume `pg_data` | Sim, enquanto os volumes existirem |

`docker compose down` **preserva** os volumes. `docker compose down -v` **apaga** `pg_data` e `n8n_data`
(workflows e conta do n8n vão junto). `storage/` não é afetado pelo `-v`.

## 5. Falhas e comportamentos conhecidos

| Situação | O que acontece |
|----------|----------------|
| `GEMINI_API_KEY` ausente | Roteiro de demonstração; nenhum erro |
| Chave/modelo/cota inválidos | O renderer responde **502** (comportamento do código; não testado com chave real). Pelo n8n, o chamador recebe **HTTP 200 com corpo vazio** (veja abaixo). |
| `duration_seconds` fora de 10–60 ou `topic` curto demais | O renderer responde **422** (testado). Pelo n8n, o chamador recebe **HTTP 200 com corpo vazio** (testado). |
| Body vazio ou campos ausentes no webhook | Funciona: o workflow aplica os padrões (`topic`, 30 s, `documentary`) (testado) |
| Renderização demorada | O n8n espera até 240 s; o renderer permite até 150 s **por chamada** de FFmpeg (5 chamadas). Se o n8n desistir, o renderer pode continuar trabalhando. |
| Várias chamadas simultâneas | Sem fila nem limite: disputam CPU. O renderer não tem autenticação. |
| Falha no meio | Pode sobrar pasta em `storage/jobs/` sem MP4 correspondente |
| Workflow não ativo e uso de `/webhook/...` | 404 do n8n |
| `/webhook-test/...` sem *Listen for test event* | 404 do n8n |

> **Atenção — erro silencioso pelo n8n.** O workflow não trata erro do nó *Render Demo Video*. Quando o renderer
> rejeita ou falha, o webhook responde `200 OK` com corpo vazio. Quem integra **não pode usar o status HTTP**
> do webhook como sinal de sucesso: confira se o corpo traz `id` e `video_url`, ou veja a falha em
> *Executions* no n8n. Para ver o erro real, chame o renderer direto (`POST :8000/videos`). Correção planejada: tratar
> erro no nó e responder com status e mensagem.

Estas limitações são esperadas no MVP e estão no roadmap (P01, P06).

## 8. Importar o workflow

- **Pela interface (caminho documentado):** *Import from File* → `workflows/01-create-short.json`. Validado de forma equivalente pela API interna do n8n (criar e ativar), ver [05-validacao](05-validacao-realizada.md).
- **Pela CLI não funciona com este arquivo:** `n8n import:workflow` na versão 1.123.5 falha com
  `null value in column "versionId"`, porque o JSON não traz `id` nem `versionId` (a interface os gera). Use a interface.
- Depois de importar, o workflow vem **inativo** (`"active": false`). Ative-o para usar `/webhook/...`.

## 6. Como acompanhar uma execução

```bash
docker compose ps                      # estado dos serviços
docker compose logs -f renderer        # logs do renderer (erros do FFmpeg aparecem aqui)
docker compose logs -f n8n             # logs do n8n
```
No n8n: menu **Executions** mostra cada execução e o dado de entrada/saída de cada nó.

## 7. Escopo desta versão

- Gera MP4 vertical **mudo** com 4 slides de texto.
- **Não** gera imagens reais, voz, legendas nem publica no YouTube.
- Não há aprovação humana, fila, banco de domínio, métricas ou controle de custo.
