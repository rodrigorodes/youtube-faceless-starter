# Escopos e Settings

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
flowchart LR
  S[Configurações] --> C[Canal ativo]
  S --> W[Estúdio]
  C --> C1[Canais]
  C --> C2[Estratégia]
  C --> C3[Marca e estilo]
  C --> C4[Produção]
  W --> W1[Conexões]
  W --> W2[Workspace]
  W --> W3[Avançado]
  C1 --> P[ChannelProfile]
  C2 --> P
  C3 --> V[VisualStyle e overrides]
  C4 --> B[ProjectConfig e BudgetLimits]
  W1 --> G[Grants e provider registry]
  W2 --> U[Equipe e preferências]
  W3 --> D[Diagnóstico autorizado]
```
