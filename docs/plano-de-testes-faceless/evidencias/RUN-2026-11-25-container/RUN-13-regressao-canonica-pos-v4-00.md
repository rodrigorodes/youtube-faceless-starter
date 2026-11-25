# Evidência RUN-13 — Regressão Canônica Completa Pós-Ajustes V4-00

**Data:** 25 de Novembro de 2026  
**Hora:** 19:20:29 (UTC-3)  
**Ambiente:** Container Docker oficial `faceless-renderer-pytest:test` sobre Debian Bookworm slim (aarch64)  
**Comando Canônico:** `./scripts/test-container.sh`  
**Configuração de Isolamento:** PostgreSQL 16-alpine em `tmpfs` efêmero (`faceless-test-net-$$`), sem portas expostas no host, prova de isolamento `/proof/proof`, `STUDIO_PUBLICATION_ENABLED=0`, orçamento de API $0.00.  
**Alinhamento da Imagem:** `hash renderer/app: checkout=949dde6397a2654a imagem=949dde6397a2654a` | `migrações: checkout=48 imagem=48`

---

## 1. Resultado Mecânico da Execução

```text
4262 passed, 20 skipped, 1 warning in 1110.03s (0:18:30)
== pytest saiu com código 0
```

- **Exit Code:** **0**
- **Total Coletado:** 4.282 testes
- **Passed:** **4.262**
- **Skipped:** **20** (17 Node.js e 3 Playwright catalogados por ausência de runtime de browser/node na imagem slim)
- **Failed:** **0**
- **Duração:** 1.110,03 segundos (18 minutos e 30 segundos)
- **Warnings:** 1 deprecation warning de biblioteca de terceiros (`Starlette/AnyIO BlockingPortal`)

---

## 2. Rastreabilidade e Evolução

- **RUN-12 (HEAD `a493d2f`):** 4.071 passed, 20 skipped, 0 failed.
- **RUN-13 (HEAD com ajustes V4-00):** 4.262 passed, 20 skipped, 0 failed.
- **Diferencial (+191 testes aprovados):**
  1. `tests/test_v4_baseline_metrics.py` (+11 testes): validadores de duração, critérios estritos de QA com falha fechada para métricas ausentes, CPU, memória pai/filhos/limite superior, disco e SHA-256.
  2. `tests/test_v4_subtitles_ticks_regression.py` (+178 testes): continuidade binária de floats em `make_cues`, não sobreposição de ticks em `_subtitle_cues`, limites temporais de narração/cena e validação da timeline de 18 cenas do piloto.
  3. `tests/test_v4_production_flow_pilot.py` (+1 teste): máquina de estados do coordenador com handlers simulados contra o PostgreSQL descartável.
  4. `tests/test_v4_studio_real_flow_pilot.py` (+1 teste): jornada pelo fluxo real do Studio com FastAPI, banco real, providers locais gratuitos, FFmpeg nativo, QA real e bloqueio de publicação externa.
