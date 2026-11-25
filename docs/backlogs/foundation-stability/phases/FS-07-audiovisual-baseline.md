# Baseline Técnico e Referência Audiovisual — FS-07
**Data:** 25/11/2026 | **Baseline:** `feat/foundation-stability` | **Quality Gate:** G5 (Baseline)  
**Referência:** [PLAN.md](../PLAN.md), [PLANO-EXECUCAO-PILOTO.md](../../../docs/plano-de-testes-faceless/PLANO-EXECUCAO-PILOTO.md) e [render_baseline.json](../../../tests/golden/render_baseline.json)

---

## 1. Objetivo
Estabelecer e documentar o baseline técnico reproduzível do RenderPlan V2 e registrar os limites do pipeline audiovisual atual (AS-IS) para suportar a transição segura para os épicos da **V4.1 (Profissionalização Audiovisual)** e **Finder Intelligence (FI)**.

---

## 2. Fixture Técnica Sintética (FS-07.01)

A fixture técnica é executada offline no contêiner canônico com Piper TTS local e FFmpeg (`libass`), validando o determinismo e a paridade audiovisual do motor sem depender de rede ou chamadas pagas:

| Caso de Teste | Resolução | Duração | Frames | Codec Vídeo / Áudio | Loudness (LUFS) | Status |
|---|---|---|---|---|---|---|
| `short_1scene_music` | 1080x1920 (9:16) | 2,80 s | 70 | H.264 / AAC 96kHz | -16.0 LUFS | **PASS (Golden)** |
| `short_1scene_silent_music` | 1080x1920 (9:16) | 2,80 s | 70 | H.264 / AAC 96kHz | -16.0 LUFS | **PASS (Golden)** |
| `long_2scenes_music` | 1920x1080 (16:9) | 5,16 s | 129 | H.264 / AAC 96kHz | -15.3 LUFS | **PASS (Golden)** |
| `short_2scenes_subtitles` | 1080x1920 (9:16) | 5,60 s | 140 | H.264 / AAC (Legenda ASS) | -16.0 LUFS | **PASS (Golden)** |
| `short_transitions` | 1080x1920 (9:16) | 5,60 s | 140 | H.264 / AAC (Crossfade) | -16.0 LUFS | **PASS (Golden)** |

* **Evidência Rastreável:** `tests/test_render_golden.py`, `tests/test_quality_ffmpeg_v2.py` e `tests/golden/render_baseline.json`.
* **Garantias Técnicas:** `black_ratio: 0.0`, `silence_ratio: 0.0`, paridade de framerate (25 fps cravados) e ausência de clipping de áudio.

---

## 3. Parametrização e Perfil de Vídeo Longo (FS-07.02)

Para viabilizar vídeos longform (5 a 8 minutos, i.e., 300s a 480s) sem comprometer a proteção padrão do ambiente de desenvolvimento:
* **`MAX_DURATION_SECONDS`:** Parametrizado como `${MAX_DURATION_SECONDS:-60}` em `docker-compose.yml` e `docker-compose.e2e.yml`.
  * *Padrão (60s):* Previne saturação acidental de CPU/disco em desenvolvimento diário e testes rápidos.
  * *Perfil Longo (480s):* Ativado explicitamente via variável de ambiente `MAX_DURATION_SECONDS=480` para campanhas longform.
* **Validação de Roteiro Longo:** O domínio longform suporta formalmente de 12 a 16 cenas para ~480 segundos com ritmo controlado (145 a 160 palavras por minuto), conforme coberto por `tests/test_longform_480s.py` e `tests/test_longform_domain.py`.

---

## 4. Diagnóstico de Limitações do Pipeline Atual (AS-IS — FS-07.03)

Antes da profissionalização na V4.1, as seguintes limitações reais foram catalogadas e não devem ser mascaradas por fixtures curtas:

1. **Composição Visual:**
   - Suporte a 1 asset/overlay principal por cena (sem camadas múltiplas ou B-roll complexo simultâneo).
   - Movimento de câmera limitado a zoom/pan linear básico.
2. **Síntese de Voz:**
   - Voz única calibrada com alta precisão métrica: `pt_BR-faber-medium` (Piper TTS).
   - Inserção de novas vozes requer calibração empírica prévia via `scripts/tts_calibration.py`.
3. **Mixagem de Áudio:**
   - Trilha sonora CC0 selecionada a partir de `storage/music-candidates/` com BPM/seed e ducking estático.
4. **Inteligência de Pesquisa:**
   - `AutoResearch` baseada em 1 documento da Wikipédia por padrão, com extração léxica de claims.

---

## 5. Critérios de Transição para V4-00 e FI-00 (FS-07.04)

1. **Reutilização de Evidências:** A iniciativa V4 (Audiovisual) e Finder Intelligence devem reutilizar diretamente as garantias de isolamento (FS-02), flags (FS-04), readiness (FS-05) e capacidade (FS-06) sem duplicar infraestrutura.
2. **Sem Custos Ocultos:** Nenhuma chamada a provedores externos pagos (ex: OpenAI, Veo, Pexels comercial) pode ser disparada sem canal autorizado e teto orçamentário configurado (`MAX_COST_USD_PER_VIDEO`).
3. **Decisão GO/NO-GO:** O baseline técnico está **APROVADO** e pronto para absorver as extensões modulares planejadas.
