# Ciclo conceitual de produção

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
stateDiagram-v2
  [*] --> Draft
  Draft --> Sources: criar vídeo
  Sources --> Ready: evidências suficientes
  Ready --> Running: start e snapshot
  Running --> Paused: pause permitido
  Paused --> Running: resume mesmo snapshot
  Running --> Failed: erro
  Failed --> Running: retry autorizado
  Running --> Review: render e QA
  Review --> Running: regeneração controlada
  Review --> Approved: revisão humana
  Approved --> Published: destino revalidado
  Running --> Cancelled: cancelar
  Published --> [*]
  Cancelled --> [*]
```
