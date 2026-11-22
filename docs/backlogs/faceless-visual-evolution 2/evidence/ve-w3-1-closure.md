# W3.1 — Porta `MediaSearch` + adaptador Pexels: fechamento

**Data:** 22/11/2026. Implementado no worktree `ve-w3-media` (branch `ve/w3-media`) e **portado
para o checkout principal**. Nada commitado.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `application/ports.py` | `MediaCandidate` (licença/proveniência/atribuição obrigatórias; custo e dimensões opcionais) e `MediaSearch` (Protocol `runtime_checkable`) |
| `adapters/media_pexels.py` | **novo** `PexelsMediaSearch` — único lugar que conhece o fornecedor; sem licença/proveniência o candidato é recusado |
| `domain/provider.py` | `ProviderKind.SEARCH` + `Capability.SEARCH` no `REQUIRED_CAPABILITY` (aditivo) |
| `application/config.py` | `BUILD_KINDS` inclui `search` (capacidade sem chave em `Project.config`) |
| `application/providers.py` | `_spec_for` resolve capacidades de catálogo sem chave de projeto; `list`, `test_connection` e `route` usam |
| `composition.py` | `ProviderImplementation(SEARCH, "pexels")` no catálogo + `register("search", "pexels", ...)` |
| `adapters/image_stock.py` | `trusted_image_url` exportado (reuso pelo adaptador) |
| `tests/test_media_search.py` | **novo**, 19 testes |
| `tests/test_architecture.py` | guarda de fornecedor de mídia em `domain/`/`application/` |
| `tests/test_port_contracts.py` | baseline da porta `MediaSearch` + par `("search","pexels")` |

## Evidência real

- No worktree: `tests/test_media_search.py` → **19 passed**; conjunto afetado (8 arquivos) →
  **144 passed**.
- **Portado para o checkout principal:** `test_media_search.py test_architecture.py
  test_port_contracts.py test_ports.py test_provider_service.py test_provider_catalog.py
  test_effective_config.py` → **115 passed** (1,76 s), `hash renderer/app=4cfb884a54fcd281`,
  `migrações=37`.
- Integração com composição/produção: `test_composition.py test_production_coordinator.py
  test_production_handlers.py test_provider_service.py` → **102 passed**.

## Decisões de contrato

- **Licença obrigatória.** `MediaCandidate` recusa sem `license`, `source_url`, `url`, `attribution`
  e `media_type`. O adaptador nunca inventa licença: sem licença/proveniência, o candidato é
  recusado.
- **Sem fornecedor no núcleo.** `domain/` e `application/` não citam "pexels"/"pixabay"; a guarda
  de arquitetura foi adicionada (não enfraquecida).
- **`search` é capacidade de catálogo, não chave de projeto.** `BUILD_KINDS` inclui `search`;
  `KINDS` (chaves de `Project.config`) permanece igual.

## Limitações

- A suíte completa no worktree foi invalidada pelo ambiente (Postgres/ffmpeg sob contenção:
  16 failed/157 errors com `psycopg.OperationalError` e `SIGKILL`), igual às demais frentes.
- UI de troca de mídia (W4.4/EDIT-03) **não** foi implementada — fora do escopo desta fatia.
