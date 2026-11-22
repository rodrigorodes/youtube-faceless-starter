# Workflow 03 (`03-publish-approved.json`) — o Core executa; o n8n orquestra

**Estado: `"active": false`.** O workflow automático ainda **não** foi reabilitado.

## O que mudou (F01.T02)

O n8n não sobe mais o vídeo: a credencial `youTubeOAuth2Api` saiu do workflow e o nó `Upload`
deixou de existir. O único caminho de publicação agora é

```
POST /studio/publications/execute
```

que roda, no Core: claim por lease → preparação (gate de QA, intenção, arquivo) → token do
**grant** do canal de destino → gate de identidade → upload → settle (`UPLOADED` / `RETRY` /
`RECONCILE` / `DEAD_LETTER` / `BLOCKED`). O workflow só decide o que fazer com o resultado:

| Resultado | Caminho no workflow |
|---|---|
| `UPLOADED` | `Set thumbnail` (Core, `/publications/{id}/thumbnail-set`) → `Thumbnail outcome` (falha não é fatal) |
| `IDLE` | `Nada a publicar` |
| `RECONCILE` | `Reconciliação necessária` (o Core já marcou `UNKNOWN`; humano/reconciliação decide) |
| qualquer outro (inclusive `BLOCKED`, `DEAD_LETTER`) | `Bloqueado ou DLQ` |

## Por que continua inativo

1. O caminho nativo (Core) está testado (`test_publication_execution.py`,
   `test_publication_resilience_repo.py`, `test_youtube_publisher.py`, `test_channel_grant_token.py`),
   mas o **workflow em si** ainda não foi exercitado numa instância n8n real com falha,
   concorrência e lease vencido.
2. Ativar sem essa prova seria declarar operação que não foi medida.

## Condições para reabilitar (ordem obrigatória)

1. Importar este workflow numa instância n8n de teste e exercitar: dois workers no mesmo vídeo,
   lease vencido, timeout depois do envio e callback atrasado — registrando a evidência.
2. Confirmar que nenhum nó carrega credencial do YouTube (o teste
   `test_no_node_carries_a_youtube_credential` já protege o JSON).
3. Só então mudar `"active"` para `true`, em mudança própria e revisada. **Nunca** ativar para
   "deixar pronto".

## Credenciais

- `studio_worker` (header do worker) para todas as chamadas ao Core.
- Nenhuma credencial do YouTube vive no n8n.