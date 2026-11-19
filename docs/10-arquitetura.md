# Arquitetura e contratos (gerado)

> Gerado por `scripts/export_contracts.py`. Não edite à mão.

## Camadas

`domain` ← `application` ← `adapters` / `api`. Só `composition.py` conhece adaptadores concretos.

## Estados do vídeo

```mermaid
stateDiagram-v2
    [*] --> IDEA
    IDEA --> SCRIPTED
    IDEA --> FAILED
    SCRIPTED --> FACT_CHECKED
    SCRIPTED --> FAILED
    FACT_CHECKED --> STORYBOARDED
    FACT_CHECKED --> FAILED
    STORYBOARDED --> ASSETS_READY
    STORYBOARDED --> FAILED
    ASSETS_READY --> RENDERED
    ASSETS_READY --> FAILED
    RENDERED --> AWAITING_APPROVAL
    RENDERED --> FAILED
    AWAITING_APPROVAL --> APPROVED
    AWAITING_APPROVAL --> REJECTED
    APPROVED --> PUBLISHED
    FAILED --> IDEA
    FAILED --> SCRIPTED
    FAILED --> FACT_CHECKED
    FAILED --> STORYBOARDED
    FAILED --> ASSETS_READY
    FAILED --> RENDERED
    PUBLISHED --> [*]
    REJECTED --> [*]
```

## Entidades

| Entidade | Schema |
|---|---|
| `Project` | `contracts/v1/project.schema.json` |
| `Video` | `contracts/v1/video.schema.json` |
| `Script` | `contracts/v1/script.schema.json` |
| `Scene` | `contracts/v1/scene.schema.json` |
| `Asset` | `contracts/v1/asset.schema.json` |
| `RenderJob` | `contracts/v1/renderjob.schema.json` |
| `Publication` | `contracts/v1/publication.schema.json` |
| `UsageEntry` | `contracts/v1/usageentry.schema.json` |
| `QaReport` | `contracts/v1/qareport.schema.json` |
