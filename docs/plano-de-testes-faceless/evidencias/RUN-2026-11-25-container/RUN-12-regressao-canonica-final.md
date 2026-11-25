# RUN-12 — Regressão Canônica Completa Final (Pós-Correção de Wiring no HEAD)

- **Data:** 25 de Novembro de 2026 (19:46 UTC)
- **Base / Commit SHA:** `a493d2f` (HEAD de `feat/fs-01-homologation` e `main`)
- **Estado do Checkout:** Limpo (`alterações_em_renderer/tests=não`, código de produto e testes 100% idênticos ao commit)
- **Ambiente:** `scripts/test-container.sh` (Docker oficial, Debian Bookworm slim, Python 3.12.16, PostgreSQL 16-alpine efêmero em tmpfs, FFmpeg 7.1 com `--enable-libass`, Piper-TTS 1.8.0)
- **Comando Canônico Executado:**
  ```bash
  ./scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -ra -q --junitxml=/test-reports/junit_canonical_run12.xml
  ```

---

## 1. Condições de Isolamento e Segurança

- **Banco de Dados:** PostgreSQL 16 Alpine efêmero em rede de contêiner isolada (`faceless-test-net-$$`), com dados em `tmpfs`, sem mapeamento de porta para o host e com prova criptográfica `/proof/proof`.
- **Publicação:** `STUDIO_PUBLICATION_ENABLED=0` em todos os testes; publicação efetiva estritamente bloqueada.
- **Orçamento de APIs:** Orçamento $0.00. Zero chamadas a serviços remotos ou APIs pagas.
- **Relatório Estruturado:** JUnit XML persistido em `storage/test-reports/junit_canonical_run12.xml` (721 KB, 4.091 testes catalogados).

---

## 2. Resultado Mecânico da Execução

```
4071 passed, 20 skipped, 1 warning in 1016.91s (0:16:56)
== pytest saiu com código 0
```

- **Exit Code:** **0**
- **Total Coletado:** 4.091 testes
- **Passed:** **4.071**
- **Skipped:** **20**
- **Failed:** **0**
- **Duração do Runner:** 1.016,91 segundos (~16 minutos e 56 segundos)
- **Warnings:** 1 deprecation warning de biblioteca de terceiros (`Starlette/AnyIO BlockingPortal`)

---

## 3. Rastreabilidade e Evolução da Contagem de Testes

- **RUN-10 / RUN-11 (Commit canônico FS-01 `4eba59c`):** 4.059 passed, 20 skipped, 0 failed.
- **RUN-12 (HEAD `a493d2f`):** 4.071 passed, 20 skipped, 0 failed.
- **Diferencial (+12 testes aprovados):**
  A diferença de exatamente 12 novos testes aprovados decorre de implementações posteriores à FS-01 já integradas ao HEAD do repositório (referentes às fases FS-02, FS-04, FS-05 e FS-06), tais como:
  - `tests/test_production_capacity.py` (admissão de capacidade e limites de concorrência);
  - `tests/test_compose_env.py` (validações estritas de variáveis de ambiente e Compose);
  - `tests/test_e2e_isolation.py` (isolamento de portas e endpoints).
- Nenhuma regressão foi observada nas suítes prévias. O bloqueio introduzido em FS-06 (`wiring.py:743: NameError`) foi integralmente resolvido no commit `a493d2f`.

---

## 4. Auditoria dos 20 Skips na RUN-12

Os 20 testes ignorados pelo runtime do Pytest foram extraídos mecanicamente do sumário (`short test summary info`) e correspondem exatamente aos 20 itens catalogados em `docs/backlogs/foundation-stability/phases/FS-01-SKIP-CLASSIFICATION.md`:

1. `tests/test_reference_browser.py:13` (importorskip Playwright)
2. `tests/ve08/test_composition_functional.py:8` (importorskip Playwright)
3. `tests/ve08/test_storyboard_functional.py:11` (importorskip Playwright)
4. `tests/test_erro_js.py:29` (Node.js)
5. `tests/test_erro_js.py:39` (Node.js)
6. `tests/test_erro_js.py:46` (Node.js)
7. `tests/test_erro_js.py:50` (Node.js)
8. `tests/test_erro_js.py:56` (Node.js)
9. `tests/test_erro_js.py:63` (Node.js)
10. `tests/test_falha_producao.py:47` (Node.js)
11. `tests/test_panel.py:522` (Node.js)
12. `tests/test_publicacao_acao.py:58` (Node.js)
13. `tests/test_publicacao_acao.py:64` (Node.js)
14. `tests/test_publicacao_acao.py:73` (Node.js)
15. `tests/test_publicacao_acao.py:87` (Node.js)
16. `tests/test_workflow_analytics.py:42` (Node.js)
17. `tests/test_workflow_analytics.py:53` (Node.js)
18. `tests/test_workflow_publish.py:70` (Node.js)
19. `tests/test_workflow_trends.py:39` (Node.js)
20. `tests/test_workflow_trends.py:69` (Node.js)

---

## 5. Decisão de Homologação

- **Status da FS-01:** **HOMOLOGADA (GO)**.
- Critérios de aceite de estabilidade, isolamento, cobertura sem quebra de guards e repetibilidade canônica 100% atendidos.
