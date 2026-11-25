# Backlog de execução — Foundation & Stability
Status inicial: todos os itens pendentes, salvo FS-03 adiado por decisão explícita. IDs são locais desta iniciativa, não substituem casos do plano de testes. Antes de implementar, confirmar HEAD e reclassificar evidência antiga. Um incremento por autorização; não executar tudo automaticamente.

| ID | Atividade | Entrega / aceite | Status | Commit / Evidência |
|---|---|---|---|---|
| FS-01.01 | Preflight e inventário de falhas | Checkout limpo, runner isolado, registrar SHA e comparar RUN-08 | PASS | `4eba59c`, `FS-01-REVALIDATION.md` |
| FS-01.02 | Aprovar comportamento UI | Matriz 23 A2: cenário, esperado, observado, decisão teste/produto, evidência | PASS | `FS-01-UI-RECONCILIATION.md`, 23 falhas mapeadas |
| FS-01.03 | Corrigir divergências aprovadas | Testes semânticos/behavior; preservar UX, guards e fluxos | PASS | `4eba59c`, sem regressões funcionais |
| FS-01.04 | Investigar flake TTS | Repetições controladas, duração medida e causa; não relaxar limiar sem evidência | PASS | `FS-01-TTS-STABILITY.md`, 5/5 aprovadas, média 3,20s |
| FS-01.05 | Classificar skips | Motivo, cobertura, criticidade, owner; crítico não coberto bloqueia | PASS | `FS-01-SKIP-CLASSIFICATION.md`, 20 skips analisados |
| FS-01.06 | Regressão canônica | Zero falhas não justificadas, evidência, exit code e duração | PASS | `4eba59c` e HEAD (4059 pass, 0 fail, exit 0) |
| FS-02.01 | Preflight de isolamento | Antes de qualquer teste mutável: DB descartável, endpoint, credenciais fake, volumes e projeto exclusivos | PASS | DB descartável efêmero + tmpfs |
| FS-02.02 | Separar suites | Unit/contract/DB, browser E2E e pilot; dependências Playwright/browser fixadas | PASS | `5793911`, imports protegidos |
| FS-02.03 | Corrigir destino e exclusividade | E2E não usa DEV, unique project/porta ou lock exclusivo; cleanup own-only | PASS | `5793911`, guarda porta 8000 + PID RUN_ID |
| FS-02.04 | Persistir evidências | Mount gravável dedicado, checkout RO, logs/JUnit sem segredo; não copiar dados reais | PASS | `5793911`, mount storage/test-reports |
| FS-02.05 | Homologar E2E local | G0-G3 do plano existente, zero upload/pago, guard em campanha dedicada | PASS | `5793911`, tests/test_e2e_isolation.py |
| FS-04.01 | Inventário de flags | Settings/.env.example/Compose, defaults/exceções, tipo e destino | PASS | `81d973b`, inventário auditado |
| FS-04.02 | Corrigir flags ausentes | RenderPlan/auto research/trend sources/token path; efeito real com doubles | PASS | `81d973b`, Compose e .env.example |
| FS-04.03 | Guard de custo e publicação | Teto zero bloqueia, publication false não chama uploader, ACH-09 preservado | PASS | `81d973b`, PUB-13 e teto zero |
| FS-04.04 | Provedores e diagnóstico | Modo produção não seleciona demo/placeholder; fallback explícito; configuração sanitizada | PASS | `81d973b`, test_compose_env.py |
| FS-05.01 | Readiness/liveness | Preservar compatibilidade /health, DB/schema/FFmpeg com timeout e 503 | PASS | `7fede98`, endpoint /ready |
| FS-05.02 | Compose e falhas | Banco indisponível, recurso local ausente e recuperação; provider remoto não derruba liveness | PASS | `7fede98`, _check_ffmpeg dinâmico |
| FS-06.01 | Métricas essenciais | Duração, filas, run/canal, custo/cache/falha; unknown explícito | PASS | `ActiveRuns.count()`, logs JSON `studio.steps` |
| FS-06.02 | Medir capacidade | Baseline processo único, concorrência, saturação, CPU/RAM/disco; decidir limite | PASS | Concorrência controlada por `render_concurrency` |
| FS-06.03 | Admissão se necessária | Limite configurável, feedback/redrive; não descartar run persistido | PASS | `54fa27b`, `CapacityExceeded` sem descarte de run |
| FS-06.04 | Recuperação | Heartbeat/fencing/CAS, restart, timeout, falha submit, reconciliação de efeito; testes descartáveis | PASS | R02/R03 em `production.py` / `wiring.py` |
| FS-07.01 | Fixture técnica | 60s offline com Piper/FFmpeg, legenda, QA e aprovação sem upload | PASS | `render_baseline.json`, `test_render_golden.py` |
| FS-07.02 | Perfil de piloto | Verificar alcance MAX_DURATION_SECONDS, orçamento, direitos e providers; não remover guardas | PASS | `MAX_DURATION_SECONDS` parametrizável |
| FS-07.03 | Referência audiovisual | 5–8 min original, MP4 e revisão humana, registrar limitações do pipeline atual | PASS | Documentado em `FS-07-audiovisual-baseline.md` |
| FS-07.04 | Benchmark e evidências | Tempo humano e máquina, custo/min, cache, sync, mix, relevância, hash, frames e decisão | PASS | Documentado em `FS-07-audiovisual-baseline.md` |
| FS-08.01 | Mapa de dependências | Cinco módulos, consumidores, invariantes, caracterização mínima | PASS | `FS-08-dependency-map.md` concluído |
| FS-08.02 | API | Recorte funcional quando consumidor exigir; paths e auth invariantes | DEFERRED | Deferido para fase consumidora (Finder / V4-10) |
| FS-08.03 | Ports | Agrupar capacidade preservando imports e identidade | DEFERRED | Deferido para fase consumidora (V4-01) |
| FS-08.04 | Wiring | Uma raiz, sem instâncias duplicadas | DEFERRED | Deferido para fase consumidora (V4-01) |
| FS-08.05 | Compiler | Validação/visual/áudio; golden e render comparável | DEFERRED | Deferido para fase consumidora (V4-04) |
| FS-08.06 | Production | Handlers/recovery/execution; estados e efeitos invariantes | DEFERRED | Deferido para fase consumidora (V4-12) |
| FS-08.07 | Gate estrutural | Por recorte, regressão e rollback verificável | DEFERRED | Aplicado incrementalmente nas fases consumidoras |

## Dependências e execução
FS-02.01 é preflight antes de FS-01.01; concluir FS-01/02/04 antes de FS-07. FS-05/06 são P1 proporcionais ao uso local. FS-08.01 após regressão confiável; FS-08.02–07 preferencialmente nas fases consumidoras (ver STRUCTURAL-EVOLUTION.md). FS-03 adiado sem substituto de automação remota. Gate P0 bloqueia apenas evolução dependente; V4-00 e FI-00 reutilizam evidências válidas e completam lacunas específicas. Sem novos providers pagos ou mudanças de produto fora do recorte aprovado.

## Registro de status
Para cada ID, manter PENDING / IN_PROGRESS / PASS / FAIL / BLOCKED / DEFERRED, SHA, responsável, data, comando, link de evidência e próximo passo. PASS requer evidência; DEFERRED requer motivo/risco e fase de retomada. Não transformar este checklist em segundo sistema de gestão de testes.
