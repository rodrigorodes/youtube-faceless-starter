# Backlog de execução — Foundation & Stability
Status inicial: todos os itens pendentes, salvo FS-03 adiado por decisão explícita. IDs são locais desta iniciativa, não substituem casos do plano de testes. Antes de implementar, confirmar HEAD e reclassificar evidência antiga. Um incremento por autorização; não executar tudo automaticamente.

| ID | Atividade | Entrega / aceite |
|---|---|---|
| FS-01.01 | Preflight e inventário de falhas | Checkout limpo, runner isolado, registrar SHA e comparar RUN-08 |
| FS-01.02 | Aprovar comportamento UI | Matriz 23 A2: cenário, esperado, observado, decisão teste/produto, evidência |
| FS-01.03 | Corrigir divergências aprovadas | Testes semânticos/behavior; preservar UX, guards e fluxos |
| FS-01.04 | Investigar flake TTS | Repetições controladas, duração medida e causa; não relaxar limiar sem evidência |
| FS-01.05 | Classificar skips | Motivo, cobertura, criticidade, owner; crítico não coberto bloqueia |
| FS-01.06 | Regressão canônica | Zero falhas não justificadas, evidência, exit code e duração |
| FS-02.01 | Preflight de isolamento | Antes de qualquer teste mutável: DB descartável, endpoint, credenciais fake, volumes e projeto exclusivos |
| FS-02.02 | Separar suites | Unit/contract/DB, browser E2E e pilot; dependências Playwright/browser fixadas |
| FS-02.03 | Corrigir destino e exclusividade | E2E não usa DEV, unique project/porta ou lock exclusivo; cleanup own-only |
| FS-02.04 | Persistir evidências | Mount gravável dedicado, checkout RO, logs/JUnit sem segredo; não copiar dados reais |
| FS-02.05 | Homologar E2E local | G0-G3 do plano existente, zero upload/pago, guard em campanha dedicada |
| FS-04.01 | Inventário de flags | Settings/.env.example/Compose, defaults/exceções, tipo e destino |
| FS-04.02 | Corrigir flags ausentes | RenderPlan/auto research/trend sources/token path; efeito real com doubles |
| FS-04.03 | Guard de custo e publicação | Teto zero bloqueia, publication false não chama uploader, ACH-09 preservado |
| FS-04.04 | Provedores e diagnóstico | Modo produção não seleciona demo/placeholder; fallback explícito; configuração sanitizada |
| FS-05.01 | Readiness/liveness | Preservar compatibilidade /health, DB/schema/FFmpeg com timeout e 503 |
| FS-05.02 | Compose e falhas | Banco indisponível, recurso local ausente e recuperação; provider remoto não derruba liveness |
| FS-06.01 | Métricas essenciais | Duração, filas, run/canal, custo/cache/falha; unknown explícito |
| FS-06.02 | Medir capacidade | Baseline processo único, concorrência, saturação, CPU/RAM/disco; decidir limite |
| FS-06.03 | Admissão se necessária | Limite configurável, feedback/redrive; não descartar run persistido |
| FS-06.04 | Recuperação | Heartbeat/fencing/CAS, restart, timeout, falha submit, reconciliação de efeito; testes descartáveis |
| FS-07.01 | Fixture técnica | 60s offline com Piper/FFmpeg, legenda, QA e aprovação sem upload |
| FS-07.02 | Perfil de piloto | Verificar alcance MAX_DURATION_SECONDS, orçamento, direitos e providers; não remover guardas |
| FS-07.03 | Referência audiovisual | 5–8 min original, MP4 e revisão humana, registrar limitações do pipeline atual |
| FS-07.04 | Benchmark e evidências | Tempo humano e máquina, custo/min, cache, sync, mix, relevância, hash, frames e decisão |
| FS-08.01 | Mapa de dependências | Cinco módulos, consumidores, invariantes, caracterização mínima |
| FS-08.02 | API | Recorte funcional quando consumidor exigir; paths e auth invariantes |
| FS-08.03 | Ports | Agrupar capacidade preservando imports e identidade |
| FS-08.04 | Wiring | Uma raiz, sem instâncias duplicadas |
| FS-08.05 | Compiler | Validação/visual/áudio; golden e render comparável |
| FS-08.06 | Production | Handlers/recovery/execution; estados e efeitos invariantes |
| FS-08.07 | Gate estrutural | Por recorte, regressão e rollback verificável |

## Dependências e execução
FS-02.01 é preflight antes de FS-01.01; concluir FS-01/02/04 antes de FS-07. FS-05/06 são P1 proporcionais ao uso local. FS-08.01 após regressão confiável; FS-08.02–07 preferencialmente nas fases consumidoras (ver STRUCTURAL-EVOLUTION.md). FS-03 adiado sem substituto de automação remota. Gate P0 bloqueia apenas evolução dependente; V4-00 e FI-00 reutilizam evidências válidas e completam lacunas específicas. Sem novos providers pagos ou mudanças de produto fora do recorte aprovado.

## Registro de status
Para cada ID, manter PENDING / IN_PROGRESS / PASS / FAIL / BLOCKED / DEFERRED, SHA, responsável, data, comando, link de evidência e próximo passo. PASS requer evidência; DEFERRED requer motivo/risco e fase de retomada. Não transformar este checklist em segundo sistema de gestão de testes.
