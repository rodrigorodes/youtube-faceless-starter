# Publicação com identidade única

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
sequenceDiagram
  participant O as UI/API/n8n
  participant P as Publication use case
  participant I as Identity resolver
  participant S as Secret store
  participant Y as YouTube
  O->>P: executar publicação aprovada
  P->>I: resolver destino do vídeo
  I->>S: obter grant autorizado e renovar se necessário
  I->>Y: verificar identidade do token
  Y-->>I: canal autenticado
  alt destino autorizado e identidade coincide
    I-->>P: credencial válida (somente backend)
    P->>P: claim idempotente e aprovação
    P->>Y: upload
    Y-->>P: resultado
    P->>P: persistir ou reconciliar resultado ambíguo
  else divergente ou revogado
    I-->>P: bloquear
    P-->>O: erro acionável sem segredo
  end
```
