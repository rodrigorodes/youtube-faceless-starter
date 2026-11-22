# W3.3 (VE-05) + S6 — QA técnico do overlay, semântico honesto e portas declaradas

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` · **Nada commitado**. Implementado em `ve-w3-3-qa` e **portado**.
**Testes:** container, tags `faceless-renderer:w43`.

## Entregue
- `application/ports.py` (S6): `OverlayVerifier`, `SemanticChecker`, `TenantContext` declaradas **antes** do adaptador; `QualityEvaluator` documenta a medição técnica + declaração semântica.
- `domain/quality.py`: `SemanticResult` (motivo obrigatório em `not_verified`/`failed`), `OverlayEvidence`, campos aditivos e coletores; plano sem overlay não acrescenta check/achado/lacuna.
- `adapters/quality_ffmpeg.py`: `FfmpegOverlayVerifier` (mede a descontinuidade nas bordas da janela; `measured=False` quando não há como medir) e avaliador que só chama os verificadores quando o plano tem overlay.
- `adapters/quality_semantic.py` (novo): `NotVerifiedSemanticChecker` — sem provedor, `not_verified` com motivo; nunca "passou" inventado.
- `composition.py`: fiação explícita. Testes: `test_quality_overlay.py` (novo), `test_port_contracts.py`, `test_quality.py`.

## Evidência (checkout principal)
| Comando | Resultado |
|---|---|
| conjunto de render/style/QA acima | **236 passed** em 45.81 s |

## Lacunas
- `TenantContext` é só declaração (adaptador single-tenant/sessão é fase posterior).
- Overlay cobrindo o render inteiro: `measured=False` → cobertura `not_verified` (honesto).
- Bug pré-existente de isolamento `_REGISTRY` entre `test_editorial_api` e `test_port_contracts` (achado #11) — não corrigido aqui.
