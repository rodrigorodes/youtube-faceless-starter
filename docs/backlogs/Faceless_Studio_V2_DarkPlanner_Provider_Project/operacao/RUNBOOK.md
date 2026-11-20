# Runbook — Segurança, configuração, monitoração, rollback

## Pré-requisitos
API confirmada e termos aprovados; credencial em secret manager; endpoint e allowlist verificados; provider flag desligada inicialmente.

## Configuração exemplo (não funcional até integração comprovada)
```dotenv
# Alternativa mantida
STUDIO_VOICE=piper:pt_BR-faber-medium
# Após deploy + feature flag por projeto:
# STUDIO_VOICE=darkplanner:<voice-id-real>
```
Não salvar API key no `.env` distribuído, README, dump ou payload do projeto. Usar secret ref por ambiente e, na F11, por organização.

## Proteções
Timeouts para request e download; limite de tamanho/duração; HTTPS + host allowlist; não logar tokens/roteiro integral/URLs assinadas; rate limit e teto por vídeo; hash de input e versão da voz para cache; conta de custo por job; verificações de silêncio e codec; retenção controlada de artefatos.

## Métricas e alertas
`audio_generation_total{provider,outcome}`, `audio_generation_duration_seconds`, `audio_generation_cost_usd`, `audio_generation_retries_total`, `audio_generation_needs_reconciliation`, `audio_wav_invalid_total`, uso por canal/organização (IDs não sensíveis). Alertar por falhas/reconciliações/custo excedido e fila parada.

## Rollout
1. Fake adapter + contrato.
2. Integração em sandbox com voz curta; validações de download e áudio.
3. 1 canal de teste via flag; vídeos não publicados automaticamente.
4. Comparar Piper e DarkPlanner: duração, pronúncia, silêncio, custo, qualidade percebida.
5. Expandir por canal após aceites e aprovação do responsável.

## Rollback
Trocar configuração do projeto para `voice: piper:...`, desabilitar flag e drenar jobs com cautela. Jobs `SUBMITTED/PROCESSING` são reconciliados ou cancelados conforme capacidade confirmada na API; nunca repetir submit cegamente. Preservar histórico de custos, erros e tokens protegidos.
