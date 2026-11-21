# Workflow 03 (`03-publish-approved.json`) — por que continua inativo (F8-07)

**Estado: `"active": false`.** O workflow automático **não** foi reabilitado nesta fatia.

## Motivos verificados no código, não suposições

1. **Ele contorna o gate novo de publicação.** O workflow usa `POST /studio/publications/claim`
   (o caminho legado do F6), não o executor nativo F8. O `claim` antigo não exige a
   `publication_intents` (render_id/checksum imutáveis) nem o gate de QA acoplado à publicação.
   Ativá-lo agora permitiria publicar sem a prova que a F8 passou a exigir.
2. **A credencial OAuth do YouTube dentro do n8n não foi validada.** O contrato de credenciais
   (`youtube_videos_app`) e os nós de upload/thumb não foram exercitados contra o YouTube real.
   Ativar "para ficar pronto" seria exatamente o que a fatia proíbe.
3. **A publicação real agora tem caminho nativo.** `POST /studio/videos/{id}/publication/publish`
   + reconciliação usam a porta `YouTubeUploader`, o cofre de tokens e o executor testado
   (`test_publication_execution.py`, `test_publication_resilience_repo.py`,
   `test_youtube_publisher.py`). O n8n deixa de ser necessário para publicar e permanece como
   legado até ser migrado.

## Condições para reabilitar (ordem obrigatória)

1. Migrar os nós de upload para chamar o endpoint nativo `.../publication/publish` e
   `.../publications/{id}/reconcile`, **sem** credencial YouTube no n8n.
2. Rodar os testes de falha/concorrência do n8n contra uma instância real (dois workers no mesmo
   vídeo, lease vencido, timeout depois do envio, callback atrasado) e registrar a evidência.
3. Só então mudar `"active"` para `true` num PR próprio e com revisão. **Nunca** ativar para
   "deixar pronto".