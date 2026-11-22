# Diagramas de arquitetura

## Hoje — caminho observado
```mermaid
flowchart TD
    A[n8n / Production Coordinator] --> B[Research / Script / Factcheck]
    B --> C[Storyboard / Assets]
    C --> D[Render Plan Builder]
    D --> E[Render Compiler]
    E --> F{Single layer check}
    F -->|válido| G[Plan FFmpeg Renderer]
    F -->|sobreposição| X[CompileError]
    G --> H[QA técnico]
    H --> I[Aprovação humana]
    I --> J[YouTube]
```

## Depois — arquitetura alvo
```mermaid
flowchart TD
    A[n8n / Production Coordinator] --> B[Content + Storyboard]
    B --> C[Scene Intelligence opcional]
    P[Media providers via ports] --> C
    S[Visual Style existente] --> D[Render Plan versionado]
    C --> D
    B --> D
    D --> E[Composition Compiler puro]
    E --> F[Plan FFmpeg Renderer expandido]
    F --> G[QA técnico existente]
    G --> H[QA semântico opcional]
    H --> I[Scene review / approval]
    I --> J[YouTube]
    H -. replanejar apenas cena reprovada .-> C
```

## Camadas em uma cena (exemplo ilustrativo)
```mermaid
flowchart LR
    A[Base visual 0-15s] --> D[Composição]
    B[B-roll 4-9s / z=10] --> D
    C[Texto 7-12s / z=20] --> D
    E[Narração 0-15s] --> F[Mix final]
    D --> F
    F --> G[MP4]
```

## Fronteiras de dependência
```mermaid
flowchart LR
    API[API / Coordinator] --> APP[Application / use cases]
    APP --> DOMAIN[Domain / contracts]
    APP --> PORTS[Ports]
    ADAPTERS[FFmpeg / providers / storage] -. implementam .-> PORTS
    ADAPTERS --> DOMAIN
```

## VE-07 — Jornada do usuário
```mermaid
flowchart TD
 A[Dashboard] --> B[Briefing e modo]
 B --> C{Modo?}
 C -->|Automático| D[Pipeline existente]
 C -->|Assistido| E[Roteiro por cena]
 E --> F[Narração]
 F --> G[Storyboard]
 G --> H[Mídias e composição]
 H --> D
 D --> I[Render + QA]
 I --> J{Revisão OK?}
 J -->|Não| K[Editar cena / áudio / mídia]
 K --> L[Invalidar dependências e aprovação]
 L --> I
 J -->|Sim| M[Aprovação humana da versão]
 M --> N[Publicação YouTube]
```

## VE-07 — Invalidação de dependências
```mermaid
flowchart LR
 Text[Editar texto da cena] --> Voice[Regerar narração da cena]
 Voice --> Timing[Atualizar duração e timeline]
 Timing --> Render[Recompilar/render afetados]
 Media[Trocar mídia da cena] --> Render
 Style[Mudar estilo] --> Render
 Render --> QA[QA novamente]
 QA --> Approval[Nova aprovação render_id + checksum]
 Approval --> Publish[Publicar]
```
