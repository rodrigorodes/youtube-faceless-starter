# Grafo de dependências

Diagrama conceitual da arquitetura alvo, não uma representação de implementação já validada. Nomes de estados e contratos devem ser reconciliados no HEAD.

```mermaid
flowchart TD
  F00[F00 Baseline e ADRs] --> F01[F01 Segurança]
  F00 --> F02[F02 Fundação Settings]
  F00 --> F03[F03 Configuração efetiva]
  F02 -->|estilo persistido| F03
  F01 -->|operações reais| F03
  F03 --> F04[F04 Editorial]
  F03 --> F05[F05 Estilos]
  F02 --> F05
  F03 --> F06[F06 Routing]
  F01 --> F06
  F01 --> F07[F07 Validação]
  F02 --> F07
  F04 --> F07
  F05 --> F07
  F06 --> F07
  F05 -. futuro .-> B[Projeto B Audiovisual]
  F00 -. separado .-> C[Projeto C SaaS]
```
