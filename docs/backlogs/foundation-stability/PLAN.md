# Plano mínimo — Foundation & Stability
Estimativa de engenharia assistida por IA: 4–7 dias úteis sequenciais; P0 2,5–4 dias. Recalibrar após execução limpa. CI/CD fora do escopo. Utilizar plano de testes existente, não criar outro.

| ID | Prioridade | Esforço | Entregável |
|---|---|---|---|
| FS-01 | P0 | 0,5–1d | Regressão estável |
| FS-02 | P0 | 1d | Ambientes isolados e evidências |
| FS-03 | Adiado | — | CI/CD não implementar |
| FS-04 | P0 | 0,5–1d | Configuração efetiva e flags |
| FS-05 | P1 | 0,5–1d | Readiness e diagnóstico mínimo |
| FS-06 | P1 | 1–2d | Observabilidade e capacidade mínima |
| FS-07 | P0 | 0,5–1d | Baseline técnico e audiovisual |

## FS-01 — testes
- [ ] Aprovar contrato de UI e revisar as 23 divergências A2 individualmente. Corrigir teste ou produto conforme comportamento aprovado; não enfraquecer asserções para obter verde.
- [ ] Investigar TTS flake e classificar os 20 skips com impacto e cobertura alternativa.
- [ ] Executar scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q em checkout limpo. Registrar SHA, ambiente, comando, resultado, duração e skips.
Gate: zero falhas não justificadas; skips críticos resolvidos; cenários do plano só PASS com evidência própria.

## FS-02 — isolamento
- [ ] Reutilizar runners, separar coleta unit/integration de browser, declarar Playwright e browser quando aplicável.
- [ ] DEV (uso), TEST (DB descartável), E2E (stack isolada), PILOT (perfil próprio); não duplicar serviços. Preflight de destino, nomes/portas exclusivos ou lock de exclusividade, prova de descartabilidade.
- [ ] Persistir JUnit/logs/artefatos em diretório gravável sanitizado; checkout RO.
- [ ] E2E local sem chamadas pagas/uploads; desativar publicação explicitamente; budget guard em campanha dedicada (demo E2E atual desliga guard).
Gate: isolamento, repetibilidade, ausência de efeito externo, cleanup apenas de recursos próprios e evidências preservadas.

## FS-04 — configuração
- [ ] Matriz Settings/.env.example/Compose: campos, defaults, exceções, paths, flags, segredos; encaminhar somente campos suportados.
- [ ] Testar efeito de STUDIO_PUBLICATION_ENABLED=0, STUDIO_RENDER_PLAN_ENABLED, STUDIO_AUTO_RESEARCH, STUDIO_TREND_SOURCES e STUDIO_TOKEN_ENV_PATH conforme contrato.
- [ ] Revalidar Budget Guard, provider production, fallback, recuperação; teto zero bloqueia pago, demo não aparece como produção. Manter ACH-09, desativar publicação em campanha.
Gate: testes de paridade e efeito final com doubles; diagnóstico sem segredos; zero gasto/upload não aprovado.

## FS-05 — readiness mínimo
- [ ] Preservar /health compatível ou migrar consumidores explicitamente; separar liveness de readiness (503 quando indisponível, timeout, DB/schema/FFmpeg local).
- [ ] Diagnóstico sanitizado; Compose verifica prontidão. Falha de provider externo não derruba liveness.
Gate: banco/FFmpeg indisponível, recuperação, nenhum segredo exposto. Sem infraestrutura dedicada.

## FS-06 — capacidade mínima
- [ ] Reusar observabilidade/ActiveRuns; duração por etapa, fila/idade, falhas, custo/run/canal, cache, CPU/RAM/disco quando disponível; desconhecido != zero.
- [ ] Medir necessidade de limite simples de admissão, configurável, feedback e redrive sem descartar run persistido. Preservar fencing/heartbeat; testar saturação, restart, falha de submit, concorrência, ausência de duplicação.
Gate: evidências locais e limites documentados; processo único; sem broker/cluster. P1 pode ser recortado após medição.

## FS-07 — baseline
- [ ] Reusar PLANO-EXECUCAO-PILOTO.md G0–G3, render_golden e render_benchmark; fixture 60s, jornada, aprovação sem upload, edição/invalidação, falhas/recuperação.
- [ ] Vídeo original 5–8 min, mídia autorizada, perfil PILOT, verificar limites longform; autorização e teto antes de chamadas pagas. Medir tempo humano, wall time, CPU/RAM, custo/minuto, cache, sincronização, voz, relevância, mix e QA. Capturar MP4, metadata, hash, frames, avaliação humana; sem publicação.
Gate: baseline técnico reproduzível e referência audiovisual comparável. Se provider/autorização faltar, marcar audiovisual BLOCKED; fixture não substitui qualidade. V4-00 só encerra com evidência aplicável e aprovação.

## Transição e gates
Sequência: FS-01/02/04 → FS-07; FS-05/06 em paralelo quando possível. P1 deferível com decisão de risco, responsável e revisão. V4-00/FI-00 recebem evidências, completam apenas lacunas. Quality gate local por incremento: plano → código/testes → regressão → review → browser/render quando aplicável → aprovação → commit/PR. Sem CI/CD. Sem gasto ou publicação não autorizados. Não confundir estabilidade técnica com qualidade profissional. Reconciliar HEAD antes de executar.
