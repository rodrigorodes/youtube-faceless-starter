# Itens AUSENTES no core — análise e ordem de desenvolvimento

**Autorizado pelo operador em 22/11/2026:** implementar os oito itens ausentes
(pré-escuta/duração, camadas/B-roll, troca de mídia com candidatos, QA semântico,
ID de cena estável, editar após aprovar, edição de cena de roteiro, isolamento por
organização). Este documento registra o que **existe hoje no código**, o que falta,
o tamanho, o risco e a ordem. Evidência `arquivo:linha` relativa a `renderer/app/studio/`.

Regra de honestidade: nenhum item abaixo é "novo" — todos já estavam classificados
AUSENTE/PARCIAL em [FEATURE-COVERAGE-V3.md](../FEATURE-COVERAGE-V3.md). O que muda é
que passam a ter autorização para implementação.

## 1. Quadro geral

| # | Item | Onda / ID | Existe hoje | Falta | Tamanho | Depende de |
|---|---|---|---|---|---|---|
| 1 | Pré-escuta / duração real de áudio | W4.3 / EDIT-02 | `_wav_seconds` mede WAV real (`application/render.py:52`); **implementado**: `SceneDurationStore`/`SceneNarrationStore`, `application/scene_narration.py`, `PostgresSceneDurationRepository`, rotas `/scenes/{id}/narration[.wav]` e `/regenerate`; `RunRender` grava `duration_s` e copia o WAV | **feito** (ver [evidence/ve-w4-3-closure.md](ve-w4-3-closure.md)) | — | — |
| 2 | Camadas / B-roll | W2.1–W2.3 / VE-01–03 | **implementado**: `Shot.role`/`z_index`, compilador de overlay, compositor FFmpeg (VE-02), aba Composição em leitura (W2.3) | **feito** ([ve-w2-2-closure.md](ve-w2-2-closure.md), [ve-w2-3-closure.md](ve-w2-3-closure.md)) | — | — |
| 3 | Troca de mídia com candidatos | W3.1 / W4.4 / VE-03, EDIT-03 | **implementado**: porta `MediaSearch`/`MediaFetcher`, `ListSceneCandidates`/`SwapSceneMedia`, `swap_scene_asset` (CAS), rotas de candidatos/troca, invalidação seletiva | **feito** ([ve-w3-1-closure.md](ve-w3-1-closure.md), [ve-w4-4-closure.md](ve-w4-4-closure.md)) | — | — |
| 4 | QA semântico | W3.3 / VE-05 | **implementado**: portas `OverlayVerifier`/`SemanticChecker`/`TenantContext` (S6), `FfmpegOverlayVerifier`, `NotVerifiedSemanticChecker` (`not_verified` com motivo), `OverlayEvidence`/`SemanticResult` no domínio | **feito** ([ve-w3-3-closure.md](ve-w3-3-closure.md)) — sem provedor de visão o resultado é `not_verified` honesto | — | provedor de visão (opcional, para `verified`) |
| 5 | ID de cena estável | W4.0 / R2 | `_write_script` faz `DELETE` de todas as cenas e `INSERT` com `uuid4` a cada versão (`editorial_repo.py:77-81`); `UNIQUE (video_id, idx)` | identidade independente de `idx`; ordem como atributo; `asset_id` preservado só em cenas não afetadas; mídia marcada para revisão quando texto/intenção muda | M/G | — (iniciado em worktree) |
| 6 | Editar após aprovar | W4.2 / P-04 | **implementado**: ADR-002, `ReopenForEditing` com invalidação de aprovação/render/QA/intenção e coordenação com upload; migração `0043` | **feito** ([ve-w4-2-closure.md](ve-w4-2-closure.md)) | — | — |
| 7 | Edição de cena de roteiro | W4.1 / EDIT-01 | **implementado**: rotas de edição/add/remove/reorder com CAS + `Idempotency-Key`; histórico recuperável em W4.5 | **feito** ([ve-w4-1-closure.md](ve-w4-1-closure.md), [ve-w4-5-closure.md](ve-w4-5-closure.md)) | — | — |
| 8 | Isolamento por organização | ISO-01/02 / RELEASE-01 | `organization_id` só em `visual_styles` e no SaaS (`saas_repo.py`, `visual_style_repo.py`); auth é Basic de um único usuário (`api/routes.py:129`) | `organization_id` em vídeos/assets/render/produção; escopo derivado da sessão; RBAC aplicado nas rotas de vídeo | G | sessão/RBAC (ADR) |

## 2. Ordem de execução (por dependência real)

```
W2.1 VE-01 (overlay: contrato/compilador)  ──► W2.2 VE-02 (compositor) ──► W2.3 (aba Composição)
        │                                              │
        │                                              ├──► W3.1 VE-03 (candidatos de mídia)
        │                                              └──► W3.3 VE-05 (QA semântico)
        │
W4.0 IDs estáveis ──► W4.1 rota de edição ──► W4.2 reabrir após aprovar
        │
        └──► W4.3 pré-escuta/duração real
W4.4 troca de mídia por cena (depende de W2.2 + W3.1)
ISO isolamento por organização (trilha separada; exige ADR de sessão/RBAC)
```

Duas trilhas paralelas sem sobreposição de arquivos:

- **Trilha A (checkout principal):** `domain/`, `application/`, `adapters/render_*` — VE-01 em diante.
- **Trilha B (worktree `ve-w4-0-scene-ids`):** `adapters/postgres/editorial_repo.py`, migração nova, testes de edição.

## 3. Critérios de aceite que valem para todos

- [qa/ACCEPTANCE.md](../qa/ACCEPTANCE.md): A06 (editar cena 3 mantém IDs das outras), A08 (add/reorder/remove), A10 (duas abas → segunda rejeitada), A12 (restore cria revisão), A15 (sem alinhamento por palavra quando o provider não suporta).
- Suíte completa só no container (`scripts/test-container.sh`); nenhuma regressão nova em relação ao baseline registrado em [ve-00-closure.md](ve-00-closure.md).
- Migrações **aditivas** com default; nada apagado (VE-D2).
- Nenhum controle exibido sem consumidor no core (regra de honestidade do plano §2.1).

## 4. Riscos transversais

| Risco | Mitigação |
|---|---|
| W4.0 muda identidade de cena e invalida cache/plano | migração aditiva; teste de reuso entre versões; fazer antes de qualquer escrita por cena |
| Compositor de overlay quebra paridade audiovisual | golden existente como envelope; recusa fail-closed até VE-02 |
| QA semântico virar selo falso | classificar como "não verificado" quando não houver verificador real |
| Reabrir após aprovar corromper publicação histórica | ADR P-04; aprovação anterior fica no histórico e não vale para a nova revisão |
| Isolamento por organização quebrar fluxo solo | RBAC atrás de feature flag; migração aditiva; testes com dois tenants sintéticos |

## 5. Progresso (22/11/2026, sessão 3)

| Frente | Onde | Estado |
|---|---|---|
| VE-01 (overlay: contrato + compilador) | checkout principal | em execução |
| W4.0 (IDs de cena estáveis) | worktree `ve-w4-0-scene-ids` | em execução |
| S1/S2/S7 (saneamento de arquitetura) | worktree `ve-arch-saneamento` | em execução |
| W3.1 (porta `MediaSearch` + adaptador Pexels) | worktree `ve-w3-media` | em execução |
| ADR-002 (reabrir aprovado) | `docs/adr/ADR-002-reabrir-video-aprovado.md` | escrito |
| ADR-003 (isolamento por organização) | `docs/adr/ADR-003-isolamento-por-organizacao.md` | escrito |
| S6 (portas `MediaSearch`, `SemanticChecker`, `TenantContext`) | — | aguarda VE-01 fechar (mesmo `ports.py`) |
| S8 (congelar seleção de provider no run) | — | aguarda VE-01 fechar |

**Correção de estimativa:** o QA semântico já tem a declaração honesta (`not_verified`)
implementada; falta o verificador. O item cai de M para P.
