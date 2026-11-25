# Revisão técnica de produção audiovisual e custos

Este documento consolida os achados e análises de código das etapas editoriais, mídia, voz, render e coordenação assíncrona com orçamentos (Capítulos 04, 05, 06 e 07).

## Achados confirmados no código

1. **Inconsistência de retorno no guard de Longform (F04 / EDT.R08)**:
   - *Evidência*: Em `renderer/app/studio/application/longform.py:294-374` e `renderer/app/studio/application/budget.py:427-469`, a chamada via `PaidOperationGuard.run()` com função de validação retorna o objeto parseado (ex: `ScriptPlan`). O código subsequente em `longform.py` tenta acessar `result.usage`, gerando `AttributeError` em chamadas com guard pago ativo.
   - *Impacto*: Chamadas pagas de longform falham ao registrar telemetria de uso sem adaptação de retorno.

2. **Tolerância a citação isolada ausente no roteiro curto (F04 / EDT.R03)**:
   - *Evidência*: `renderer/app/studio/application/editorial.py:369-428`. O parser aceita uma cena sem citação explícita se houver claims disponíveis, associando automaticamente o primeiro ID válido (`claim_ids[0]`).
   - *Impacto*: Divergência em relação à documentação estrita de `docs/12-editorial.md`, que afirmava obrigatoriedade de citação explícita por cena.

3. **Chave de cache de narração de cena não inclui conteúdo (F06 / REN.R09)**:
   - *Evidência*: `renderer/app/studio/application/scene_narration.py:103-137`. A operação usa a chave financeira `narration:{video_id}:{scene_id}`, sem o hash do texto ou voz na chave.
   - *Impacto*: Reexecuções com texto alterado sob a mesma cena exigem atenção para não reutilizar indevidamente reserva ou estado anterior sem checagem de fingerprint físico.

4. **Fencing Token e Leases no Coordenador (F07 / PRO.R03)**:
   - *Evidência*: `renderer/app/studio/domain/production_run.py:390-420` e `renderer/app/studio/application/lease_heartbeat.py:21-50`. Leases de estágio possuem número de versão monótono. Se o heartbeat for interrompido, um novo worker assume com token incrementado, e qualquer escrita atrasada pelo worker anterior é rejeitada com `LeaseLost`.
   - *Impacto*: Proteção robusta contra escrita dupla após partição temporária de worker.

5. **Reversão e estorno de orçamento em falhas (F07 / PRO.R06)**:
   - *Evidência*: `renderer/app/studio/application/budget.py:400-475`. Operações pagas efetuam `RESERVED` antes da invocação da API. Se ocorrer erro ou cancelamento, a reserva é marcada como `RELEASED`, impedindo consumo fantasma de saldo.

## Hipóteses e riscos estáticos a verificar na campanha

- **Concorrência em arquivo temporário de cena**: Múltiplas regenerações concorrentes da mesma cena no mesmo vídeo poderiam disputar o arquivo `.tmp.wav` se disparadas simultaneamente antes de lock de nível de aplicação.
- **Transação de banco no snapshot de DAG**: Garantir que atualizações de estado de `ProductionRun` e estágios dependentes ocorram sob transação única atômica para evitar estágios órfãos durante reinicializações súbitas do contêiner.
- **Consistência de duração entre TTS e FFmpeg**: Variações de amostragem ou arredondamento de quadros (25 fps) exigem confirmação de que os cues de legenda SRT acompanhem exatamente a timeline do áudio mixado.
