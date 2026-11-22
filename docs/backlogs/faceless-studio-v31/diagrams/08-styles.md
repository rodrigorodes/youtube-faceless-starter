# Composição de estilos

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
flowchart TD
  A[Estilo do vídeo se definido] --> S[Selecionar uma base]
  B[Estilo do canal senão] --> S
  C[Default do motor senão] --> S
  S --> R[Resolver estilo versionado]
  D[Patch do canal compatível] --> M[Merge tipado]
  R --> M
  E[Patch do vídeo] --> M
  M --> V{Validar parâmetros finais}
  V -->|Inválido| X[Erro explícito]
  V -->|Válido| F[Effective style no snapshot]
  F --> P[Render Plan]
```
