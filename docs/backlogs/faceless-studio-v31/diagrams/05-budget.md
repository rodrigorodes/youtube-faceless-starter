# Reserva financeira atômica

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
flowchart TD
  A[Operação paga] --> B[Resolver escopo projeto/vídeo]
  B --> C[Estimar custo e carregar limites vigentes]
  C --> D{Custo aceitável?}
  D -->|Não| X[Bloquear e explicar]
  D -->|Sim| E[Transação: locks em ordem estável]
  E --> F{Teto global e projeto e vídeo respeitados?}
  F -->|Não| X
  F -->|Sim| G[Persistir reserva e confirmar transação]
  G --> H[Executar provider]
  H --> I{Resultado conhecido?}
  I -->|Sim| J[Liquidar ou liberar reserva]
  I -->|Não| K[Reconciliar antes de liberar/repetir]
  J --> L[Ledger e resumo no mesmo escopo]
```
