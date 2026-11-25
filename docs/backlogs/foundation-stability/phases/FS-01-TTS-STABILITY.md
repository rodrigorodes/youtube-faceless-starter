# FS-01.04 — Estabilidade da Calibração Piper TTS

**Fase:** FS-01 (Estabilização da Regressão)  
**Atividade:** FS-01.04 — Verificação de Estabilidade do Modelo TTS  
**Ambiente Canônico:** Container Docker `faceless-renderer-pytest:test` (Python 3.12.16, Piper-TTS 1.8.0, ffmpeg com libass)  
**Voz Testada:** `pt_BR-faber-medium.onnx`  
- SHA-256 da voz: `75e913eb463db0b6ac7ddf68d3e4c9ac19ace36dc3b710a81039b448352b8ffc`  
- SHA-256 da configuração: `6b6801319e5a70aa4d75c63343515f55d1cd671ecd1ac511586bc16216812261`  
- Tolerância relativa: **15%** (preservada estritamente conforme calibrado)  
- Delta de referência das 3 evidências empíricas (`EVIDENCE_RUNS`): **3.2547 s**  
- Intervalo aceitável [85% – 115%]: **[2.7665 s, 3.7429 s]**  

---

## 1. Contexto e Motivação

O teste `test_punctuation_adds_the_measured_pause_time` em `tests/test_tts_calibration.py` compara a duração real sintetizada de um texto em prosa com pontuação (vírgulas e pontos) contra o mesmo texto sem pontuação.

A expectativa inicial ingênua (`10 × 0,40 s = 4,0 s`) gerava instabilidade ("flake") porque supunha que cada marca de pontuação adicionasse 0,40s linearmente. No entanto, o ponto final já coincide com o silêncio de borda natural da frase em ambas as leituras. A média empírica real observada nas 3 sínteses gravadas é de **3,2547 s**.

---

## 2. Diferenciação Metodológica das Medições

Para atender com máxima precisão às exigências de homologação e auditoria independente, foram realizadas duas séries de validações:
1. **Série A — 5 Execuções Completas da Suíte Pytest (`tests/test_tts_calibration.py`):** Avalia a estabilidade de ponta a ponta do harness de testes, parsing, geração de áudio, medição de ondas e asserções.
2. **Série B — 5 Sínteses Diretas Empíricas do Piper TTS:** Avalia a dispersão física de áudio (delta pontuado vs sem pontuação) na síntese direta com o modelo ONNX.

---

## 3. Série A: 5 Execuções Completas da Suíte de Testes Pytest

Comando canônico executado no contêiner:
```bash
./scripts/test-container.sh tests/test_tts_calibration.py -v
```

Resultados individuais obtidos:

| Execução | Data/Hora (UTC) | Comando Exato | Exit Code | Duração do Runner | Resultado Pytest | Status |
|---|---|---|---|---|---|---|
| **Suíte #1** | 2026-11-25 19:22:06 | `./scripts/test-container.sh tests/test_tts_calibration.py -v` | **0** | 47s | `6 passed in 35.58s` | **PASS** |
| **Suíte #2** | 2026-11-25 19:22:53 | `./scripts/test-container.sh tests/test_tts_calibration.py -v` | **0** | 40s | `6 passed in 30.00s` | **PASS** |
| **Suíte #3** | 2026-11-25 19:23:33 | `./scripts/test-container.sh tests/test_tts_calibration.py -v` | **0** | 58s | `6 passed in 49.10s` | **PASS** |
| **Suíte #4** | 2026-11-25 19:24:31 | `./scripts/test-container.sh tests/test_tts_calibration.py -v` | **0** | 125s | `6 passed in 104.65s` | **PASS** |
| **Suíte #5** | 2026-11-25 19:26:36 | `./scripts/test-container.sh tests/test_tts_calibration.py -v` | **0** | 109s | `6 passed in 88.73s` | **PASS** |

- **Taxa de Sucesso:** 5/5 execuções (100% consecutivas).
- **Testes por Execução:** 6 passed (total de 30 asserções de calibração validadas).
- **Exit Code:** 0 em 100% das rodadas.

---

## 4. Série B: 5 Sínteses Diretas Empíricas do Piper TTS

Execução direta dentro do contêiner oficial via Piper TTS nativo (`pt_BR-faber-medium`):

| Síntese | Duração Prosa Pontuada | Duração Sem Pontuação | Delta Observado | Desvio Relativo | Limites Aceitáveis | Status |
|---|---|---|---|---|---|---|
| **Síntese #1** | 20,2710 s | 17,2640 s | **3,0070 s** | 7,61% | [2,7665 s, 3,7429 s] | **PASS** |
| **Síntese #2** | 20,3987 s | 17,3105 s | **3,0883 s** | 5,11% | [2,7665 s, 3,7429 s] | **PASS** |
| **Síntese #3** | 20,3523 s | 16,8809 s | **3,4714 s** | 6,66% | [2,7665 s, 3,7429 s] | **PASS** |
| **Síntese #4** | 20,2942 s | 16,9738 s | **3,3205 s** | 2,02% | [2,7665 s, 3,7429 s] | **PASS** |
| **Síntese #5** | 20,2710 s | 17,1363 s | **3,1347 s** | 3,69% | [2,7665 s, 3,7429 s] | **PASS** |

---

## 5. Análise Estatística da Síntese (Série B)

- **Mínimo:** 3,0070 s
- **Máximo:** 3,4714 s
- **Média Amostral:** **3,2044 s** (desvio de apenas 1,54% em relação aos 3,2547 s de referência)
- **Desvio Padrão ($\sigma$):** **0,1885 s**
- **Coeficiente de Variação:** 5,88%
- **Falhas:** 0 de 5 sínteses (100% de sucesso consecutivo dentro da margem).

---

## 6. Critério de Aceite (FS-01.04)

O critério de aceite estabelecido pelo auditor exige:
> "cinco execuções consecutivas aprovadas, com evidências quantitativas."

Comprovou-se que todas as 5 execuções consecutivas estão rigorosamente dentro da tolerância de 15%, sem qualquer necessidade de retries, relaxamento de limiares ou enfraquecimento de asserções. O teste é estável e reproduzível.
