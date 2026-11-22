# Diagramas — arquitetura alvo

## Propriedade
```mermaid
flowchart TD
 U[Usuários] --> M[Memberships]
 M --> O[Conta]
 O --> C[Canais]
 C --> V[Vídeos]
 V --> S[Cenas]
 V --> R[Revisões]
 R --> E[Execuções e renders]
 E --> P[Publicação aprovada]
```

## Jornada com revisão contextual
```mermaid
flowchart TD
 C[Canal] --> B[Novo vídeo]
 B --> T[Conteúdo]
 T --> G[Gerar]
 G --> E[Edição por cena]
 E --> Q{Revisão pronta?}
 Q -->|Ajustar| E
 Q -->|Sim| A[Aprovar versão]
 A --> P[Confirmar publicação]
 G --> F[Falha recuperável]
 F --> G
```

## Dependências Clean Architecture
```mermaid
flowchart TD
 UI[Interface] --> API[API autenticada]
 API --> APP[Aplicação e coordenador]
 APP --> DOM[Domínio puro]
 APP --> PORT[Portas]
 AD[Adapters registrados] -. implementam .-> PORT
 AD --> EXT[Providers e infraestrutura]
```

## Invalidação
```mermaid
flowchart TD
 T[Texto] --> A[Narração e duração]
 A --> C[Composição afetada]
 M[Mídia ou estilo] --> C
 C --> R[Novo render e QA]
 R --> AP[Nova aprovação]
 OLD[Publicação concluída] --> H[Histórico preservado]
```

Os diagramas são conceituais. Schema e endpoints atuais precisam ser mapeados antes de implementar. n8n aciona os mesmos casos de uso; não recebe uma cópia das regras de domínio.
