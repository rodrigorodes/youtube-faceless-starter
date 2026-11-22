# Resolução e congelamento

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
sequenceDiagram
  participant UI as UI/API/n8n
  participant Run as Production service
  participant R as Config resolver
  participant DB as Repositórios
  participant W as Worker
  UI->>Run: start(video_id)
  Run->>R: resolve configuração vigente
  R->>DB: ler perfil, estilo, projeto e vídeo
  DB-->>R: valores e revisões
  R-->>Run: effective config validada
  Run->>DB: persistir run e snapshot atomicamente
  Run->>W: iniciar execução
  W->>DB: ler snapshot do run
  Note over W: Roteiro, voz e render usam as mesmas entradas
  UI->>DB: editar estilo para futuras execuções
  W->>DB: retry/resume lê snapshot original
  Note over W: Budget, permissões e credenciais revalidados
```
