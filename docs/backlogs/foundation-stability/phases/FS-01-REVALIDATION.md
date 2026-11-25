# FS-01 — Relatório de Homologação e Revalidação Técnica

**Fase:** FS-01 (Estabilização da Regressão e Suíte Verde)  
**Status Oficial:** **HOMOLOGADO INTEGRALMENTE / PASS PARA FS-01 (HEAD TOTALMENTE DESBLOQUEADO)**  
**Auditor Responsável:** Engenheiro de Software Sênior (Antigravity)  
**Data:** 25 de Novembro de 2026  
**Commit Canônico da FS-01:** `4eba59c6103d0aeb991fd73840eb74e5a17c45fc`  
**HEAD do Repositório:** `a493d2f` (`main` / `feat/fs-01-homologation`)  

---

## 1. Atividade FS-01.01 — Preflight e Rastreabilidade

O preflight executado comprovou total isolamento e repetibilidade:

- **Branch de Trabalho:** `feat/fs-01-homologation` (ramificada a partir da `main`).
- **Worktree Limpo de Auditoria:** `/tmp/faceless-fs01-check` no commit canônico `4eba59c`.
- **Estado do Checkout:** Limpo (`nothing to commit, working tree clean`).
- **Isolamento de Banco e Containers:** 
  - PostgreSQL 16 Alpine (`postgres:16-alpine`) executado em contêiner efêmero com rede isolada (`faceless-test-net-$$`) e armazenamento em `tmpfs`.
  - Sem mapeamento de portas locais para o host, sem concorrência com o Postgres de DEV (portas 5432/8000).
  - Prova criptográfica de descartabilidade em `/proof/proof` exigida por `tests/conftest.py`.
- **Segurança de Gastos e Publicação:**
  - `STUDIO_PUBLICATION_ENABLED=0` em todos os testes de integração.
  - Zero chamadas a APIs pagas (OpenAI, Gemini, Anthropic, ElevenLabs, Runway). Custo efetivo: **$0.00**.
- **Versões dos Runtimes Canônicos (Registradas no Container):**
  - **Python:** `3.12.16` (Debian bookworm slim).
  - **PostgreSQL:** `16-alpine`.
  - **FFmpeg:** `7.1.5-0+deb13u1` com `--enable-libass` nativo habilitado.
  - **Piper-TTS:** `1.8.0` (`piper-tts==1.8.0`).
  - **Voz de Narração:** `pt_BR-faber-medium.onnx` (SHA-256 `75e913eb463db0b6ac7ddf68d3e4c9ac19ace36dc3b710a81039b448352b8ffc`).
- **Higiene de Segredos:** `scripts/secret_hygiene.py scan` aprovado com 0 violações em todos os arquivos rastreados.
- **Plano de Testes:** `python3 docs/plano-de-testes-faceless/validar.py` validado (**14 capítulos, 88 regras, 131 cenários coerentes**).

---

## 2. Atividade FS-01.02 — Matriz das 23 Divergências de UI

A matriz completa e exaustiva de cada uma das 23 falhas de UI identificadas na RUN-08 foi consolidada em:
- [FS-01-UI-RECONCILIATION.md](FS-01-UI-RECONCILIATION.md)

**Resumo da Homologação:**
- **Zero bugs de produto nas 23 falhas:** Todas decorreram de drift de asserções em testes legados que esperavam marcações da V2/V3 diante da evolução aprovada da V4/V3 (onboarding ativo, chips de filtro, dark mode padrão, breakpoint 1000px, 4 hubs de configurações, glifos de navegação e rotas separadas da IA-01).
- **Sem enfraquecimento de asserções:** Toda a cobertura funcional, sanitização CSP/XSS e regras de negócio foram rigorosamente preservadas.
- **Validação:** Todos os 170 testes das páginas de UI e painel passam 100% no ambiente canônico (`170 passed in 96.01s`).

---

## 3. Atividade FS-01.03 — Preservação das Correções Existentes

Foi auditado que as correções de produto e integrações prévias continuam ativas e estáveis:
- **`TrendItemView.query`:** Propagação preservada (`renderer/app/studio/application/panel.py`), renderizando `"Busca: {query}"` quando a tendência decorre de termo de busca.
- **Origem e Região:** Rótulo honesto `"Região não informada"` quando a região não é retornada pela API, evitando inferências enganosas.
- **Criação de Vídeos:** Navegação de `"Criar com piloto"` preserva o canal ativo e o tópico para `/studio/panel/novo-video?project_id=...&topic=...`.
- **Pilares:** Diálogo acessível por `"Gerenciar pilares"` (`#btn-gerenciar-pilares`), sem links mortos.
- **Segurança CSP & XSS:** Proteção estrita contra injeção em títulos de tendências, temas e roteiros (`tests/test_panel_page.py` e `tests/test_script_page.py`).

---

## 4. Atividade FS-01.04 — Estabilidade da Calibração Piper TTS

Foram executadas **5 baterias independentes e consecutivas** do teste de calibração TTS no contêiner oficial (tanto da suíte completa de testes quanto das medições diretas de síntese):
- Evidência completa em [FS-01-TTS-STABILITY.md](FS-01-TTS-STABILITY.md).

**Resultados Quantitativos:**
- **Série A (5 execuções da suíte pytest `tests/test_tts_calibration.py`):**
  - Run 1: 6 passed em 35.58s (exit code 0)
  - Run 2: 6 passed em 30.00s (exit code 0)
  - Run 3: 6 passed em 49.10s (exit code 0)
  - Run 4: 6 passed em 104.65s (exit code 0)
  - Run 5: 6 passed em 88.73s (exit code 0)
  - Taxa de sucesso: 100% (5 de 5 consecutivas, 0 falhas).
- **Série B (5 sínteses diretas do modelo Piper TTS):**
  - Referência empírica calibrada: 3,2547 s (tolerância de 15%: [2,7665 s a 3,7429 s]).
  - Média amostral observada: **3,2044 s** (desvio médio de apenas 1,54%).
  - Desvio padrão: **0,1885 s**.
  - Taxa de sucesso: 100% (5/5 consecutivas aprovadas, sem retries).

---

## 5. Atividade FS-01.05 — Classificação dos 20 Testes Ignorados

A auditoria individual e extração mecânica dos 20 skips foi detalhada em:
- [FS-01-SKIP-CLASSIFICATION.md](FS-01-SKIP-CLASSIFICATION.md)

**Estrutura Mecânica dos Skips:**
- **17 testes de Helpers JS / Nós n8n:** Decorrentes da ausência do binário `node` na imagem Python slim do renderer (4 funções individuais em `test_panel.py`, `test_workflow_publish.py`, `test_workflow_analytics.py`, `test_workflow_trends.py`, `test_falha_producao.py`, 6 testes no módulo `test_erro_js.py` e 4 funções em `test_publicacao_acao.py`). Cobertura alternativa assegurada por testes unitários Python dos domínios analítico, publicação e tendências.
- **3 módulos de Navegador Playwright:** `tests/test_reference_browser.py`, `tests/ve08/test_composition_functional.py` e `tests/ve08/test_storyboard_functional.py` (exigem `pytest_playwright`, ausente na imagem headless slim). Cobertura alternativa assegurada por testes de contrato HTML e APIs.
- **Avaliação de Risco:** Zero testes críticos ou financeiros ignorados. Decisão oficial: **Aceitar temporariamente** na suíte canônica headless e consolidar formalmente na fase FS-02.

---

## 6. Validação da Publicação — Cenário PUB-13

O cenário PUB-13 foi validado no ambiente isolado:
- Verificado via `tests/test_publication_execution.py` (**48 passed in 1.10s**).
- Comprovou-se que `STUDIO_PUBLICATION_ENABLED=0`:
  1. Bloqueia o executor com resultado `PublicationResult.BLOCKED`.
  2. Impede reivindicação de publicação (`pubs.calls == []`).
  3. Impede requisição de credencial ou token OAuth (`tokens.calls == 0`).
  4. Impede qualquer tentativa de upload para o YouTube (`uploads.uploads == []`).
  5. Não registra sucesso espúrio (`pubs.uploaded is None` e `uploads.reconciliations == []`).

---

## 7. Diferenciação das Métricas de Cobertura

Em estrito cumprimento às diretrizes de auditoria:
- **Mapeamento de Requisitos de Negócio:** 100% das 88 regras de negócio estão cobertas por ao menos um cenário de teste documentado no modelo GC (total de 131 cenários em 14 capítulos).
- **Status dos Cenários Documentais:** Todos os 131 cenários permanecem como `A_PROJETAR`. Nenhum cenário documental foi promovido a `PASS` sem execução em campanha formal.
- **Cobertura de Código Automatizada:** A suíte canônica de testes do repositório cobre as camadas unitárias, de repositório Postgres e de compilação/render FFmpeg.
- **Cobertura Funcional / E2E:** Desacoplada nas suítes `tests/e2e_full` e `tests/e2e_ux`, tratadas no preflight FS-02.

---

## 8. Resolução do Bloqueio Identificado em FS-06 no HEAD (`a493d2f`)

Durante a auditoria da estabilização da regressão, foi identificado que o commit `54fa27b` (referente à fase **FS-06**) introduziu uma regressão em `renderer/app/studio/composition/wiring.py`:
- **Local:** Linha 743:
  ```python
  submit=tracked_submit(self._executor, worker.work, self._active_runs, max_active=settings.max_active_runs)
  ```
- **Erro:** `NameError: name 'settings' is not defined`. No escopo local de `_build()`, a instância de configurações é `s`.
- **Resolução Implementada e Auditada:**
  - Aplicação da correção de 1 token em `wiring.py:743` (`settings.max_active_runs` -> `s.max_active_runs`), comitada em `a493d2f`.
  - Validação imediata: 170 testes de UI executados e aprovados (`170 passed in 89.92s`) e 30 testes pós-FS01 aprovados (`30 passed in 1.42s`).
  - O bloqueio está **100% resolvido**, sem impactos colaterais ou débitos técnicos.

---

## 9. Regressão Canônica Completa (RUN-12)

A regressão canônica oficial sobre o HEAD limpo (`a493d2f`) foi executada no ambiente canônico oficial (`scripts/test-container.sh`) com relatório JUnit estruturado.

- **Evidência Consolidada:** [RUN-12-regressao-canonica-final.md](../../../plano-de-testes-faceless/evidencias/RUN-2026-11-25-container/RUN-12-regressao-canonica-final.md).
- **Métricas Mecânicas Reais:** **4.071 passed, 20 skipped, 0 failed** em 1.016,91s (~16m 56s), com exit code 0.
- **JUnit XML Gerado:** `storage/test-reports/junit_canonical_run12.xml` (721 KB, 4.091 testes catalogados).
- **Justificativa da Variação de Cobertura:** Os 12 testes adicionais em relação à RUN-11 (4.059 -> 4.071) decorrem de testes de capacidade, Compose e isolamento implementados em fases posteriores no HEAD (`tests/test_production_capacity.py`, `tests/test_compose_env.py`).
- **Skips:** Exatamente 20 skips, 100% categorizados e justificados individualmente em [FS-01-SKIP-CLASSIFICATION.md](FS-01-SKIP-CLASSIFICATION.md).
- **Decisão Final para FS-01:** **GO / HOMOLOGADA**.
