# Evolução estrutural incremental — FS-08

Status: proposta documentada, não implementada. Baseline main 79e3585 (25/11/2026), leitura estática dos cinco módulos. Contagem por split de linhas (inclui linha final vazia quando presente); não é medida de complexidade nem justificativa isolada para refatorar. Objetivo: reduzir acoplamento e contexto de mudança para V4.1/Finder, sem construir infraestrutura corporativa nem reescrever o core.

## AS-IS e fronteiras

| Módulo (renderer/app/studio/) | Linhas aproximadas | Evidência | Direção |
|---|---:|---|---|
| api/routes.py | 3153 | make_router; 140 declarações de decoradores @router; _authenticate, _browser_guard e idempotency helpers; DTOs e endpoints | Routers por contexto, manter make_router como agregador |
| application/production.py | 1313 | StageContext, StageOutcome, StageHandler, handlers, worker step, frozen_provider_selection, recovery e _enqueue | Isolar handlers/execução/recuperação quando tocados; manter fachada e invariantes |
| composition/wiring.py | 856 | Studio._wire, _build_provider, tracked_submit, _effective_config_for, use_cases e lifecycle | Funções de composição por capacidade, uma raiz Studio |
| application/ports.py | 1183 | Protocols VideoRepository, TextModel, ImageModel, MediaSearch, MediaFetcher, Voice, Renderer; RenderSpec | Agrupar contratos por capacidade, reexportar tipos existentes |
| application/render_compiler.py | 486 | structure_render_plan, _validate_overlays, _compile_layers, _shot_plan, _compile_narration, _compile_music | Separar validação, visual e áudio sem alterar RenderPlan/PlanStructure |

Já há módulos independentes: composition/providers.py, composition/settings.py, application/lease_heartbeat.py, application/observability.py, domain/render_plan.py, domain/render_plan_builder.py. Não duplicar essas responsabilidades.

## Desenho alvo conceitual
Nomes abaixo são sugestões, sujeitos ao mapa de imports e testes. Não criar diretórios vazios ou mover código sem benefício medido.

- API: routes.py agrega APIRouter(s) de channels/config, videos/editorial, production/render, trends/finder, publication/analytics e providers. Guards e DTOs compartilhados somente onde necessário. Preservar métodos, paths, prefixos, nomes, ordem de rotas que possam colidir, OpenAPI, status, headers/redirects, autenticação, CSRF e idempotência.
- Production: manter fachada Production e contratos atuais; extrair handlers por etapa/coorte, executor de etapa e recovery conforme dependências. Reusar LeaseHeartbeat e ActiveRuns. Não criar segundo coordenador, registry de estados nem fila paralela.
- Composition: manter Studio, Settings, lifecycle, _wire como ponto canônico. Extrair funções de wiring de providers, produção/render e Finder/Research com dependências explícitas; usar composition/providers.py já existente. Evitar service locator, circular imports, instâncias duplicadas, novo container DI ou conexão independente por extração.
- Ports: módulos por editorial/research, media/voice/render, storage/repositories, production/budget/publication e trends/analytics quando necessário. Reexports transitórios de ports.py devem referenciar as MESMAS classes; preservar signatures, identidade, dataclasses, Protocols, exceptions, defaults e import paths existentes até migração de consumidores.
- Compiler: manter structure_render_plan e PlanStructure públicos. Extrair validação de asset/overlay/trajetória, compilação visual/shot/caption e áudio/narration/music em unidades puras. Não alterar ticks, fps/framing, ordering, arredondamento, transições, duração, filtros, erros ou capacidades no mesmo commit mecânico. FFmpeg e RenderPlan únicos.

## Ordem proporcional
| Incremento | Janela recomendada | Dependência / gate |
|---|---|---|
| FS-08.01 mapa de responsabilidades/imports, rotas, consumidores, invariantes, testes de caracterização faltantes | Foundation depois de FS-01/02; não exige extração | baseline verde e decisão de UI |
| FS-08.02 API por contexto (começar trends ou outro recorte pequeno) | Antes da alteração grande na UX/Finder, FI-01/FI-08 ou V4-10 | inventário de API e auth; teste de compatibilidade |
| FS-08.03 ports por capacidade | V4-01 | contratos/imports existentes preservados |
| FS-08.04 wiring por capacidade | V4-01 após ports quando necessário | uma instância por responsabilidade, frozen config, budget e lifecycle |
| FS-08.05 compiler | V4-04 antes da extensão multicamadas | golden/PlanStructure/FFmpeg comparáveis |
| FS-08.06 production | V4-12 ou antes se FS-06 provar necessidade | fencing, CAS, heartbeat, recovery, approval, idempotência |
| FS-08.07 validação integrada | em cada extração | regressão e smoke local, sem mudança funcional misturada |

A preparação obrigatória é o mapa e caracterização mínima quando necessários. Extrações P1 podem ser deferidas para as fases consumidoras. Se uma mudança P0 exigir extração, justificar o delta mínimo; não refatorar os cinco arquivos de uma vez.

## Invariantes e compatibilidade
1. Não modificar schema/migrações, DTOs, endpoints, estados, semantics de budget/lease/publicação ou contrato de RenderPlan em commits de movimentação.
2. Dependências: domínio puro, application depende de ports/domínio, adapters implementam portas, composition conhece implementações; API chama casos de uso. Validar testes/test_architecture.py e imports existentes.
3. Testes de caracterização antes e após; inventário OpenAPI/métodos/paths e handlers, imports públicos, eventos, estados, ownership, outputs determinísticos, erro e rollback. Comparação de render por estrutura e tolerâncias de mídia, não exigir hash MP4 idêntico quando encoder variar.
4. Um recorte por commit; sem dependência nova para movimentação de código; rollback por revert do recorte, sem reset de dados ou force push.
5. Evidências: SHA, arquivos movidos, dependências removidas/adicionadas, testes focados e regressão, compatibilidade, risco residual e decisão GO/NO-GO. Não fixar meta arbitrária de linhas/arquivo; medir área de mudança, dependências e cobertura.
6. Não antecipar funcionalidades Finder/V4 durante refatoração. Sem CI/CD, broker, microserviços, Kubernetes ou SaaS nesta iniciativa.

Ver [fase FS-08](phases/FS-08-modularization.md), [AS-IS](diagrams/code-structure-as-is.mmd) e [TO-BE](diagrams/code-structure-to-be.mmd).
