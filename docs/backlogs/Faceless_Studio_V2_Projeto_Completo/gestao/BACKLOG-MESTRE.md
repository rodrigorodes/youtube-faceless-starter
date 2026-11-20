# Backlog mestre F0–F11

**Total:** 95 cards candidatos. Os IDs são estáveis para importar manualmente em Jira/GitHub Issues.

| ID | Fase | Prioridade | Tarefa | Status |
|---|---|---|---|---|
| `F0-01` | F0 | P0 | Rotacionar tokens/chaves OAuth/API encontrados no pacote; revisar acesso e histórico de distribuição. | A fazer |
| `F0-02` | F0 | P0 | Criar `scripts/package-starter.sh` com allowlist de código/docs, sem `.env`, `credentials/`, `storage/`, backups, `.git/` ou dados pessoais. | A fazer |
| `F0-03` | F0 | P0 | Adicionar secret scanning no CI e teste que inspeciona ZIP gerado. | A fazer |
| `F0-04` | F0 | P0 | Gerar inventário das rotas, estados, providers, workflows, capacidades e gaps; marcar adapters `working/experimental/disabled`. | A fazer |
| `F0-05` | F0 | P0 | Reconciliar `README` e docs com comportamento executável; arquivar materiais históricos. | A fazer |
| `F0-06` | F0 | P0 | Criar baseline de testes, migrations, segurança, custo, fixture de 8 min e relatório de cobertura; corrigir CI. | A fazer |
| `F0-07` | F0 | P0 | Definir flags e rollout progressivo para V2. | A fazer |
| `F1-01` | F1 | P0 | Criar `ProductionRun`/`StageExecution`/outbox e migrations. | A fazer |
| `F1-02` | F1 | P0 | Definir DAG de estágios, dependências e contratos I/O; manter checkpoints do vídeo atuais. | A fazer |
| `F1-03` | F1 | P0 | Criar `ProductionCoordinator` e executor/worker port; avaliar se aproveitar worker atual ou adapter assíncrono dedicado. | A fazer |
| `F1-04` | F1 | P0 | Criar `POST production-runs`, status e eventos de progresso. | A fazer |
| `F1-05` | F1 | P0 | Implementar etapas research/script/factcheck/storyboard/assets/render/QA/approval/publish como handlers; nenhum efeito irreversível sem gate. | A fazer |
| `F1-06` | F1 | P0 | Idempotency key, CAS, lease, heartbeat, fencing, checkpoint e replay determinístico. | A fazer |
| `F1-07` | F1 | P0 | Pausa humana persistida: liberar worker e retomar com versão aprovada; sem processo aguardando bloqueado. | A fazer |
| `F1-08` | F1 | P0 | Retry seletivo, cancelamento, DLQ e trilha de auditoria. | A fazer |
| `F1-09` | F1 | P0 | Testes de falha entre persistência, provider call, commit e recuperação; concorrência entre 2 workers. | A fazer |
| `F2-01` | F2 | P0 | Desenhar mapa de navegação, wireframes e estados vazios/erros. | A fazer |
| `F2-02` | F2 | P0 | Criar wizard `Novo vídeo`: canal, tema, briefing, duração, estilo, idioma, budget. | A fazer |
| `F2-03` | F2 | P0 | Botão primário `Produzir vídeo` chamando Production Coordinator. | A fazer |
| `F2-04` | F2 | P0 | Página de execução com stepper, próxima ação, tempo decorrido, custo estimado/real e eventos. | A fazer |
| `F2-05` | F2 | P0 | Ações `Pausar`, `Continuar`, `Cancelar`, `Tentar novamente`, `Revisar` condicionadas a permissões/estado. | A fazer |
| `F2-06` | F2 | P0 | Unificar lista `Vídeos` por estado de negócio e filtros `precisa de mim`, `em andamento`, `concluído`, `falhou`. | A fazer |
| `F2-07` | F2 | P0 | Mover IDs/traces/model usage para diagnóstico avançado. | A fazer |
| `F2-08` | F2 | P0 | Acessibilidade (teclado, contraste, feedback), responsividade, testes E2E com operador não técnico. | A fazer |
| `F3-01` | F3 | P0 | Criar `ContentBrief` versionado com `trend_id`, hipótese de interesse, público, objetivo e referências. | A fazer |
| `F3-02` | F3 | P0 | Ao selecionar tendência, transportar IDs de evidências, timestamps e URLs para research; nunca confiar em claims de vídeos de terceiros sem checagem. | A fazer |
| `F3-03` | F3 | P0 | Criar `ResearchPort` com estratégias fonte oficial, feeds e busca permitida; fallback para fontes manuais. | A fazer |
| `F3-04` | F3 | P0 | Canonicalizar URLs, deduplicar, gravar `SourceSnapshot`, status de licença e proveniência. | A fazer |
| `F3-05` | F3 | P0 | Avaliar fonte por data, reputação, pertinência e suporte a claims; rejeitar fonte inacessível sem inventar conteúdo. | A fazer |
| `F3-06` | F3 | P0 | Criar UI de fontes (`aprovar`, `descartar`, `adicionar`, `inspecionar claims`). | A fazer |
| `F3-07` | F3 | P0 | Corrigir rotulagem de `regionCode=US` para EUA; `Global` somente como agregação real com origem explícita. | A fazer |
| `F3-08` | F3 | P0 | Observar custos/cotas YouTube e impor throttle/cache. | A fazer |
| `F4-01` | F4 | P0 | Expandir briefing com `target_duration_seconds`, público, voz, ritmo, estrutura, linguagem e restrições. | A fazer |
| `F4-02` | F4 | P0 | Separar prompt short vs long; long deve gerar estrutura por blocos/chapters, hook, contexto, desenvolvimento, payoff/CTA. | A fazer |
| `F4-03` | F4 | P0 | Definir estimativa configurável de palavras/minuto e duração por cena, validada contra velocidade real do TTS. | A fazer |
| `F4-04` | F4 | P0 | Criar roteiro em duas passagens: outline/chapter plan e script de cenas com referências. | A fazer |
| `F4-05` | F4 | P0 | Validar continuidade, redundância, duração estimada, claims e ausência de invenção; aproveitar gate de fact-check atual. | A fazer |
| `F4-06` | F4 | P0 | Versionar scripts e criar aprovação humana atrelada a hash/versão. | A fazer |
| `F4-07` | F4 | P0 | Tela para editar/regerar cenas, inspecionar fontes e fazer override justificado. | A fazer |
| `F4-08` | F4 | P0 | Edição invalida somente outputs downstream dependentes; testar propagação de invalidation. | A fazer |
| `F4-09` | F4 | P0 | Criar teste de roteiro de aproximadamente 480 s cobrindo 2–4 temas/estilos. | A fazer |
| `F5-01` | F5 | P1 | Introduzir `VisualBeat` (scene_id, start/end, asset_kind, reference, transition, provenance, license). | A fazer |
| `F5-02` | F5 | P1 | Permitir 1:N beats por cena e mídia `stock`, `AI image`, `AI clip`, `diagram`, `screen capture` fornecida, `text animation`. | A fazer |
| `F5-03` | F5 | P1 | Criar `MediaProviderPort` e capability registry (`SUPPORTED`, `EXPERIMENTAL`, `UNAVAILABLE`); Veo atualmente deve aparecer indisponível até implementação validada. | A fazer |
| `F5-04` | F5 | P1 | Reusar stock primeiro onde licença permite, imagens geradas quando agregam, clipes IA apenas em momentos-chave. | A fazer |
| `F5-05` | F5 | P1 | Storyboard define duração, beat, objetivo visual, safe area, asset fallback e proporção. | A fazer |
| `F5-06` | F5 | P1 | Evoluir render FFmpeg para beats múltiplos, trilha por camadas, crossfades, áudio, legendas e transições. | A fazer |
| `F5-07` | F5 | P1 | Regeração granular por beat/cena; cache por conteúdo e versão do provider; invalidation. | A fazer |
| `F5-08` | F5 | P1 | Auditoria de licença, uso de marca/pessoa e proveniência; QA de assets e falhas de download. | A fazer |
| `F5-09` | F5 | P1 | Perfis de custo `economy`, `balanced`, `premium` com fallback condicionado ao budget. | A fazer |
| `F6-01` | F6 | P1 | Player + timeline por cena/beat com thumbnails, waveforms opcional e navegação por timestamp. | A fazer |
| `F6-02` | F6 | P1 | Editor de narração, legenda e referência visual por cena (MVP: edição por formulário, não NLE completo). | A fazer |
| `F6-03` | F6 | P1 | Trocar asset/voz, regerar trecho e renderizar nova versão com status. | A fazer |
| `F6-04` | F6 | P1 | QA técnico: codec/dimensões, áudio, duração, picos/silêncio, legendas, artefatos, frame preto. | A fazer |
| `F6-05` | F6 | P1 | QA editorial: claims, consistência, pronúncia, ritmo, safe areas, repetição visual; checks heurísticos primeiro. | A fazer |
| `F6-06` | F6 | P1 | Mostrar severidade `blocking/warning/info`, evidências e ação de correção. | A fazer |
| `F6-07` | F6 | P1 | Aprovação final requer `render_id`/checksum mais recente e relatório QA compatível. | A fazer |
| `F6-08` | F6 | P1 | Testes de regressão visual e de mídia com fixtures curtas e longas. | A fazer |
| `F7-01` | F7 | P1 | Criar `PackagingAgent` (contrato com título, descrição, tags, capítulos, fontes e CTA). | A fazer |
| `F7-02` | F7 | P1 | Gerar 3 conceitos de thumbnail e títulos correspondentes com justificativa editorial; sem clickbait enganoso. | A fazer |
| `F7-03` | F7 | P1 | Templates gráficos por canal; text overlays, safe areas, legibilidade mobile e exportação. | A fazer |
| `F7-04` | F7 | P1 | Review UI para comparar variantes, escolher e editar metadados. | A fazer |
| `F7-05` | F7 | P1 | Persistir versão escolhida junto a `publication_intent`. | A fazer |
| `F7-06` | F7 | P1 | Validar dimensões/formato/peso e regras vigentes da API do YouTube por integração. | A fazer |
| `F7-07` | F7 | P1 | Testes de conteúdo enganoso, imagem sem licença e edição de metadados pós-aprovação. | A fazer |
| `F8-01` | F8 | P0 | Mapear fluxo atual: aprovações, claims, lease, resumable upload, sessão, recovery, workflow `03-publish-approved.json`. | A fazer |
| `F8-02` | F8 | P0 | Implementar `PublicationIntent` transacional com versão de vídeo e media checksum imutáveis. | A fazer |
| `F8-03` | F8 | P0 | Claim por lease+fencing; sessão de upload salva de forma segura; reconciliar remoto antes de iniciar sessão nova. | A fazer |
| `F8-04` | F8 | P0 | Controlar repetição, timeout, crash, lease expirado, upload parcial e callback atrasado; preservar remote video ID. | A fazer |
| `F8-05` | F8 | P0 | Validar canal autorizado, scopes e erro OAuth; mensagens de reconexão claras; não expor secrets nem URLs resumable. | A fazer |
| `F8-06` | F8 | P0 | Definir política de publicação privada por padrão; agendamento e visibilidade pública requerem regras explícitas/consentimento. | A fazer |
| `F8-07` | F8 | P0 | Reabilitar workflow automático apenas depois de testes de falha e concorrência passarem. | A fazer |
| `F8-08` | F8 | P0 | Teste manual de ponta a ponta em canal de teste, incluindo reconciliação depois de falha artificial. | A fazer |
| `F9-01` | F9 | P2 | Conectar dados observados às versões de briefing, roteiro, embalagem e publicação. | A fazer |
| `F9-02` | F9 | P2 | Coletar métricas autorizadas (views, CTR/impressões quando disponíveis, watch time e retenção conforme API/permissão). | A fazer |
| `F9-03` | F9 | P2 | Dashboard por canal, vídeo, pilar e período; mostrar quando dados ainda não estão disponíveis. | A fazer |
| `F9-04` | F9 | P2 | Criar insights com evidência e nível de confiança, separando observação de hipótese. | A fazer |
| `F9-05` | F9 | P2 | Recomendar temas/formatos e mudanças de hook ou pacing para revisão humana. | A fazer |
| `F9-06` | F9 | P2 | Histórico de experimentos thumbnail/título conforme recursos realmente oferecidos pelo YouTube. | A fazer |
| `F10-01` | F10 | P1 | CRUD de canais/projetos, arquivamento, estratégia, idioma, público e pilares. | A fazer |
| `F10-02` | F10 | P1 | `ChannelProfile` versionado: narrativa, duração, identidade visual, voz, áudio, thumbnail e CTA. | A fazer |
| `F10-03` | F10 | P1 | Tela de providers com capabilities, custo estimado, rate limits, disponibilidade e teste de conexão. | A fazer |
| `F10-04` | F10 | P1 | Profiles econômicos e roteamento de provider por tarefa/custo/qualidade; fallback controlado. | A fazer |
| `F10-05` | F10 | P1 | Budget por canal/produção, limites hard/soft e painéis de custo honesto. | A fazer |
| `F10-06` | F10 | P1 | Associar canal YouTube e status OAuth, sem mostrar secrets. | A fazer |
| `F10-07` | F10 | P1 | Manter configs sensíveis em vault/secret store, não no `Project.config` devolvido ao browser. | A fazer |
| `F11-01` | F11 | P2 | Introduzir `Organization`, `Workspace`, `User`, `Role`, `Membership`, isolando `Project`/Video e storage por tenant. | A fazer |
| `F11-02` | F11 | P2 | Autenticação por sessão/OIDC, RBAC com `owner/editor/reviewer/viewer` e auditoria. | A fazer |
| `F11-03` | F11 | P2 | Isolamento de registros, storage, jobs, filas, custos, secrets e logs por tenant; testes de vazamento. | A fazer |
| `F11-04` | F11 | P2 | BYOK por tenant e provider; criptografia, rotação, autorização por uso, masks, revogação. | A fazer |
| `F11-05` | F11 | P2 | Metering e quotas de plataforma vs custo direto das APIs do cliente; modelo de cobrança transparente. | A fazer |
| `F11-06` | F11 | P2 | Billing com controle de créditos, uso, limites, falha de pagamento e webhooks idempotentes (provedor a escolher). | A fazer |
| `F11-07` | F11 | P2 | Deploy com API/worker separados, assets em object storage, observabilidade, backups/restore e retenção. | A fazer |
| `F11-08` | F11 | P2 | Revisar termos de n8n, modelos e stock para uso SaaS, mais direitos autorais, privacidade e YouTube policies vigentes. | A fazer |
| `F11-09` | F11 | P2 | Escalonamento de workers, rate limit por tenant/provider, antifraude, SLO e plano de incidentes. | A fazer |
