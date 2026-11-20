# Plano de testes e qualidade

## Camadas
**Unitários**: normalização do resultado, WAV válido e não silencioso, duração obtida localmente, payload vazio, conversão de erros, timeout, codec inválido, limites, sanitização de logs, allowlist/SSRF.

**Contrato (parametrizado)**: executar o mesmo harness em `PiperVoice`, `FakeVoice` e `DarkPlannerVoiceAdapter` com servidor mock; exigir output WAV em `out_path`, duração >0, falha de input com erro seguro e nenhuma mutação no core.

**Integração**: `ProjectConfig.voice` → `build('voice',...)` → `RunRender` em fixture com 2–3 cenas; verificar FFmpeg/QA, subtitles geradas localmente e não alteração dos estados de domínio.

**Resiliência**: HTTP 429/5xx, timeout antes/depois do submit, perda de lease/worker, sessão sem confirmação, download parcial, resposta com corpo malicioso, áudio sem frames, side effects após cancelamento. Para API sem idempotência, marcar `NEEDS_RECONCILIATION` e **não** reenviar.

**E2E fornecedor (manual/ambiente controlado)**: com API oficialmente disponível, 1 narração curta, 1 vídeo de 8 minutos por cenas, 1 cenário de erro e 1 reconciliação; medir custo real, latência e qualidade em PT-BR.

**Segurança/SaaS**: organização A não acessa secret/artifact/jobs da B; tokens não aparecem em logs; BYOK rejeita secrets inválidos; permissões de settings; limites por tenant.

## Aceite objetivo
- Zero imports do provider em `domain/` e `application/` (grep/architecture test).
- Switch `piper` ⇄ `darkplanner` somente por configuração + flag, mantendo render invariável.
- Tempo, custo, status e ID externos rastreados sem segredo.
- Nenhum retry de submit sem comprovação de idempotência/reconciliação.
- Áudio gerado e convertido para WAV medido corretamente; QA aprova fixture representativa.
- Dependências atuais funcionam sem chaves DarkPlanner quando o provider está desligado.
