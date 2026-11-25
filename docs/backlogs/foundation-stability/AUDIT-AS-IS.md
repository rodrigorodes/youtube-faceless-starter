# AS-IS — main b642f44 (25/11/2026)
Método: leitura de arquivos e diff; nenhum teste/render executado nesta auditoria. Documentação de execução local dirty não comprova o HEAD limpo.

| Evidência | Implicação |
|---|---|
| [CONTINUITY](../../plano-de-testes-faceless/CONTINUITY.md) e [99-lacunas](../../plano-de-testes-faceless/99-lacunas.md): RUN-08, 4035 passed, 23 failed, 20 skipped, 767s, exit 1, browser E2E excluído | 23 falhas classificadas A2 (drift de UI), não 23 bugs confirmados; investigar TTS flake e skips; repetir em checkout limpo |
| Plano existente: 14 capítulos, 88 regras e 130 cenários planejados | Reusar, não promover cenários a PASS sem evidência própria |
| scripts/test-container.sh e scripts/run-e2e-full.sh | Runner canônico Docker, DB descartável; Playwright não instalado no padrão, relatório sem volume gravável; E2E com nome fixo e down -v; isolamento obrigatório |
| scripts/run-e2e-tests.sh e docker-compose.e2e.yml | UX aponta por padrão para stack de uso; E2E demo/placeholder e budget desligado, 60s; não comprova provider real, orçamento ou longform |
| docker-compose.yml e composition/settings.py | Budget/publicação/recuperação/provider production encaminhados; STUDIO_RENDER_PLAN_ENABLED, STUDIO_AUTO_RESEARCH, STUDIO_TREND_SOURCES, STUDIO_TOKEN_ENV_PATH ausentes no Compose principal; reconciliar defaults |
| renderer/app/main.py | /health sempre 200, ffmpeg constante true; separar readiness de liveness |
| composition/wiring.py tracked_submit | ActiveRuns e executor existentes, sem limite explícito de admissão nesse ponto; medir antes de escalar |
| scripts/render_benchmark.py | Fixture curta sintética, custo/cache ausentes; não mede qualidade profissional |
| MAX_DURATION_SECONDS=60 no Compose principal | Investigar alcance e preparar perfil de piloto longo, sem remover proteções indiscriminadamente |
| [Revisão arquitetural](../../reviews/2026-11-24-architecture-review.md) | R02/R03 heartbeat e recuperação endereçados; preservar e testar. R01 parcial, R04/R07 em escopo mínimo; R05/R08 registrados para expansão |
| domain/media_ranker.py, application/research.py, application/render_compiler.py, composition/wiring.py | Ranking lexical existente, research default 1 documento, 1 overlay por cena, semantic checker não verificado: evoluir em V4-04/05/06/09, não antecipar |
| domain/trend_priority.py | VPH acumulada, concorrência fixa, aderência por categoria: transparência e conformidade em FI-00/03/05 |

Host macOS sem libass não é ambiente canônico conforme relato. Publicação ligada por padrão é decisão ACH-09; manter, desligar explicitamente nas campanhas. Sem CI/CD. Backup integral, concorrência multiprocesso e isolamento tenant permanecem riscos para expansão/SaaS; proteger dados locais agora. Não refatorar módulos só por quantidade de linhas.

## Concentração estrutural — confirmada em main 79e3585
Contagens aproximadas por leitura: routes.py 3153, production.py 1313, wiring.py 856, ports.py 1183, render_compiler.py 486. routes.py contém 140 declarações @router (não necessariamente 140 operações únicas). Não é defeito isolado. [Evolução estrutural](STRUCTURAL-EVOLUTION.md) especifica responsabilidades, invariantes e recortes; FS-08 P1, sem refatoração geral. Baseline do código é posterior ao merge documental; RUN-08 continua evidência histórica, não teste deste SHA.
