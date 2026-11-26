# Relatório de Auditoria Arquitetural — INT-01

**Data:** 2026-11-26  
**Referência Fixada:** `develop` (`0257c045dbff8ef3f78b4f8ffba76b20db226433`)  
**Baseline Intocado:** `main` (`be0c463edc55ff567f9149d26c8fd350c803d745`)  
**Auditor:** Staff Software Architect Independente

---

## 1. Sumário Executivo da Auditoria

A análise detalhada dos 13 commits (+7564 / -304 linhas) em `develop` revelou que:
1. **Componentes de Domínio e Contratos Ricos Foram Criados:** A base de código possui modelagens puras e robustas para áudio multitrack, legendas sincronizadas, controle de qualidade multimodal, governança de assets, resiliência determinística e composição visual.
2. **Desacoplamento e Isolamento de Consumidores (Gargalo de Integração):** Grande parte dos novos componentes sob `renderer/app/studio/domain/` e `renderer/app/studio/application/` operavam em isolamento de teste (`MOCK_ONLY` ou `MODEL_ONLY`), sem ligação efetiva com os orquestradores canônicos de produção:
   - O `ProductionCoordinator` existente continuava usando o fluxo pré-V4.
   - O compilador FFmpeg (`render_compiler.py`) ainda impunha `MAX_OVERLAYS_PER_SCENE = 1` e rejeitava transições `crossfade`.
   - O Kokoro TTS gerava tom senoidal de 220Hz mas estava marcado como `validated=True` no `providers.py`.
   - A resiliência utilizava `InMemoryOperationStore` e simulação de timeout, em vez do CAS real do Postgres.
   - O módulo de mídia (`media.py`) rejeitava MP4, impedindo o cumprimento de GAI-01.

---

## 2. Matriz de Auditoria dos Achados (A01 a A13)

| ID | Área / Fase | Prioridade | Símbolo / Evidência no Código | Diagnóstico Real (AS-IS) | Ação de Integração (TO-BE) | Status G1 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A01** | Voz (V4-02) | **P0** | `adapters/voice_kokoro.py` linha 60; `composition/providers.py` linha 172 | Kokoro sintetiza senoide 220Hz; marcado como `validated=True` no registry. | Marcar `validated=False` (experimental). Tornar Piper o provedor offline validado oficial. Falhar com erro semântico claro se kokoro nativo não estiver instalado. | **VERIFIED (Aberto)** |
| **A02** | Voz (V4-02/01) | **P1** | `adapters/voice_elevenlabs.py` linha 44 | Lança `NotImplementedError` sem chamada externa. | Manter desabilitado (`validated=False`), estritamente opt-in, sem tráfego de rede no teste ($0.00). | **VERIFIED (Conforme)** |
| **A03** | Composição (V4-04) | **P0** | `application/render_compiler.py` linhas 45 e 296 | `MAX_OVERLAYS_PER_SCENE = 1`; rejeita mais de 1 overlay por cena. | Elevar para suporte a múltiplas camadas simultâneas (imagem/gráfico/vídeo) com z-index e limites explícitos de recursos. | **VERIFIED (Aberto)** |
| **A04** | Efeitos (V4-04/05) | **P0** | `adapters/render_plan_compiler.py` linha 514 e 457 | `crossfade` rejeitado com erro; `_overlay_filter` apenas centraliza e não aplica escala/posição x-y/opacidade. | Implementar filtro FFmpeg de posicionamento x/y, escala, opacidade e transição funcional; validar pixels no MP4. | **VERIFIED (Aberto)** |
| **A05** | Piloto (V4-13) | **P0** | `tests/test_v4_professional_pilot.py` | Dados sintéticos fornecidos manualmente no teste unitário sem render físico associado. | Rotular claramente como teste de contrato sintético; executar piloto real via Studio gerando MP4 medido. | **VERIFIED (Aberto)** |
| **A06** | Áudio (V4-03) | **P1** | `domain/audio_dsp.py` | True Peak estimado por pico máximo de amostras discretas, não por EBU R128 oversampled. | Integrar com `FfmpegQualityEvaluator` / `ebur128` do FFmpeg para medição real de dBTP. | **VERIFIED (Aberto)** |
| **A07** | Motion / Roteiro (V4-05/06/07) | **P1** | `motion_effects.py`, `creative_director.py`, `captions_exporters.py` | Criados no domínio, mas sem integração com o `PlanFfmpegRenderer` e exportadores. | Integrar com o fluxo de renderização e storyboard. | **VERIFIED (Aberto)** |
| **A08** | Render Engine & QA (V4-08/09) | **P1** | `application/render_engine.py`, `domain/quality.py` | Criados em isolamento; `wiring.py` não conectava os novos serviços ao app. | Conectar ao pipeline real de produção, provando invalidação seletiva de cache de cena. | **VERIFIED (Aberto)** |
| **A09** | UX Storyboard (V4-10) | **P1** | `application/studio_workbench.py` | Operações de Undo/Redo no domínio sem rotas FastAPI correspondentes no painel. | Expor endpoints de bancada e persistência de revisão de storyboard. | **VERIFIED (Aberto)** |
| **A10** | Acervo (V4-11) | **P1** | `application/asset_registry.py` | Armazenamento de assets em dicionários locais (`dict`), sem banco Postgres. | Integrar com `PostgresVideoRepository` e `FileAssetStore` com deduplicação por hash SHA-256 e licença. | **VERIFIED (Aberto)** |
| **A11** | Resiliência (V4-12) | **P0** | `application/resilience.py` | `InMemoryOperationStore` e simulação de timeout em teste unitário. | Integrar diretamente com `ProductionCoordinator` e `PostgresProductionRunRepository` (CAS real). | **VERIFIED (Aberto)** |
| **A12** | Mídia Externa (GAI-01/02) | **P1** | `application/media.py` | Rejeita MP4 (`ALLOWED_MIME` apenas imagens); falta importação genérica autorizada. | Suportar upload de PNG e MP4 com validação mágica de bytes, sanitização e trim. | **VERIFIED (Aberto)** |
| **A13** | Gates & Homologação | **P0** | Relatórios anteriores | Relatórios V4 anteriores declaravam GO sem evidências integradas fim a fim. | Executar suíte completa integrada G0-G7, sem simular aprovação do operador humano. | **VERIFIED (Aberto)** |

---

## 3. Plano de Ação das Ondas INT-02 a INT-07

1. **INT-02 (Providers):** Desabilitar Kokoro validado no registry; Piper estabelecido como síntese local padrão validada; ElevenLabs mantido opt-in inativo.
2. **INT-03 (Composição):** Elevar `MAX_OVERLAYS_PER_SCENE` em `render_compiler.py`; implementar render real de múltiplas camadas, x/y, escala, opacidade e transições no FFmpeg.
3. **INT-04 (Pipeline & Resiliência):** Integrar cache por cena, idempotência e reconciliação pré-retry com o `ProductionCoordinator` real sobre PostgreSQL.
4. **INT-05 (Acervo & Mídia GAI-01/02):** Permitir upload e preview de MP4 e PNG externos com validação de bytes e vínculo com Storyboard.
5. **INT-06 (Piloto Real):** Produzir Vertical Slice real medido via FFmpeg com QA EBU R128 real, sem dados sintéticos simulados.
6. **INT-07 (Regressão & Release):** Regressão canônica completa, Clean Architecture auditada e parada para avaliação humana do operador.

**Decisão da Auditoria INT-01:** Plano aprovado para início imediato da onda **INT-02**.
