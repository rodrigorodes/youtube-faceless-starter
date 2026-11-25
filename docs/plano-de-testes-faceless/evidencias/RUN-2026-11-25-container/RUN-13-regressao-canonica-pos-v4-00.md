# Evidência RUN-13 — Regressão Canônica Completa Pós-Ajustes V4-00

**Data:** 25 de Novembro de 2026  
**Hora:** 19:20:29 (UTC-3)  
**Ambiente:** Container Docker oficial `faceless-renderer-pytest:test` sobre Debian Bookworm slim (aarch64)  
**Comando Canônico:** `./scripts/test-container.sh`  
**Configuração de Isolamento:** PostgreSQL 16-alpine em `tmpfs` efêmero (`faceless-test-net-$$`), sem portas expostas no host, prova de isolamento `/proof/proof`, `STUDIO_PUBLICATION_ENABLED=0`, orçamento de API $0.00.  
**Rastreabilidade de Código e SHA Testado:**
- **SHA Base no Início da RUN-13:** [`f35976d`](https://github.com/rodrigorodes/youtube-faceless-starter/commit/f35976d)
- **Estado do Checkout durante a Execução:** O checkout continha alterações ativas em `tests/` e `renderer/app` (`alterações_em_renderer/tests=sim`), representando exatamente o pacote de correções da V4-00.
- **SHA que Congelou as Alterações Testadas:** [`8904b4c`](https://github.com/rodrigorodes/youtube-faceless-starter/commit/8904b4c)
- **Alinhamento da Imagem:** `hash renderer/app: checkout=949dde6397a2654a imagem=949dde6397a2654a` | `migrações: checkout=48 imagem=48`

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

## 2. Nomenclatura Padronizada das Evidências V4-00

1. **Benchmark audiovisual longo:** **345,60 segundos** (`storage/output/v4_piloto_audiovisual_5min.mp4`, 18 cenas documentais, -15,5 LUFS, SHA `9b20e2e7...`).
2. **Jornada real do Studio:** **Short** (`tests/test_v4_studio_real_flow_pilot.py` — jornada de 15s com FastAPI, PostgreSQL, FFmpeg nativo, QA real, aprovação humana e kill switch de publicação).
3. **Integração do coordenador:** **handlers simulados** (`tests/test_v4_production_flow_pilot.py` — coordenador assíncrono com handlers simulados contra PostgreSQL descartável).
4. **Avaliação humana:** **pendente** (critério V4-00.06 aguardando revisão subjetiva do operador para os MP4s e frames gerados).

---

## 3. Rastreabilidade e Evolução da Suíte

- **RUN-12 (HEAD `a493d2f`):** 4.071 passed, 20 skipped, 0 failed.
- **RUN-13 (HEAD `8904b4c`):** 4.262 passed, 20 skipped, 0 failed.
- **Diferencial (+191 testes aprovados):**
  1. `tests/test_v4_baseline_metrics.py` (+11 testes): validadores de duração, critérios estritos de QA com falha fechada para métricas ausentes, CPU, memória pai/filhos/limite superior, disco e SHA-256.
  2. `tests/test_v4_subtitles_ticks_regression.py` (+178 testes): continuidade binária de floats em `make_cues`, não sobreposição de ticks em `_subtitle_cues`, limites temporais de narração/cena e validação da timeline de 18 cenas do piloto.
  3. `tests/test_v4_production_flow_pilot.py` (+1 teste): Integração do coordenador: handlers simulados contra o PostgreSQL descartável.
  4. `tests/test_v4_studio_real_flow_pilot.py` (+1 teste): Jornada real do Studio: Short com FastAPI, banco real, providers locais gratuitos, FFmpeg nativo, QA real e bloqueio de publicação externa.
