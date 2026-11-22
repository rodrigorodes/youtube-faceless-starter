# Comece aqui — fluxo completo + configurações

## O que abrir
Abra `prototype/index.html` em navegador; não precisa de servidor. O CSS da proposta V3 original foi incorporado à casca. A revisão recupera recursos omitidos na V2 e mantém o contexto canal/vídeo.

## Roteiro de avaliação
1. **Início**: veja padrão do canal e vídeos recentes; digite uma ideia para criar.
2. **Vídeos → Continuar**: entre no vídeo de exemplo. Use as abas Fontes e roteiro, Narração, Cenas e mídias, Composição, Qualidade, Publicação e Produção.
3. **Fontes e roteiro**: adicione texto ou URL, edite o roteiro e salve. URL registrada não é evidência verificada.
4. **Narração**: altere voz/provider/velocidade, simule geração e abra o trecho de uma cena.
5. **Cenas e mídias**: altere texto, adicione/reordene/remova cenas e troque a origem da mídia.
6. **Composição**: ajuste legendas, B-roll, música, resolução, FPS e transição. Simule montagem.
7. **Qualidade**: simule verificação técnica, aprove a versão e siga para Publicação. Semântica continua não verificada.
8. **Publicação**: prepare título, descrição, privacidade, thumbnail e data desejada; confirme publicação fictícia.
9. **Produção**: veja etapas, custo indisponível, limites e controles de pausa/retomada/retry/cancelamento.
10. **Configurações**: visite todas as sete seções. Cadastre um provider fictício e veja-o aparecer em Produção e orçamento por capacidade. Configure limites, marca, legenda, música, estratégia e equipe.
11. Troque o canal e confirme separação dos vídeos e preferências. Alterações de identidade não modificam snapshots dos vídeos existentes.
12. Explore Tendências/ideias → criar vídeo, Desempenho ilustrativo e Biblioteca de estilos/vozes/mídias.

## O que é simulado
Não há API, autenticação, isolamento real, áudio, vídeo, IA, extração de fonte, conexão OAuth, cobrança, QA real, agenda ou upload. Nunca inserir credenciais reais. Dados de demonstração persistem no navegador; a demo pode funcionar em memória se armazenamento for bloqueado. Configurações são salvas ao mudar campos; roteiro/texto usam botão Salvar.

## Implementação
Leia PROJECT-V3.md e FEATURE-COVERAGE-V3.md antes do backlog e do prompt mestre. A matriz exige rastrear funcionalidades pré-existentes e propostas; esconder/remover não conta como simplificação. O HTML é protótipo, não base para copiar contratos ou lógica de domínio ao frontend.

## Validação contra o repositório e plano de integração (22/11/2026)
- [evidence/REPO-VALIDATION.md](evidence/REPO-VALIDATION.md): matriz de cobertura contra o código real, riscos R1–R11 e divergências.
- [phases/INTEGRATION-PLAN.md](phases/INTEGRATION-PLAN.md): ondas W0–W5 que adicionam a proposta ao core e à UX atuais, com decisões P-01–P-07 pendentes de aprovação.
- [phases/VE-01-render-overlay.md](phases/VE-01-render-overlay.md): especificação da VE-01 (**implementada**; fechamento em [evidence/ve-01-closure.md](evidence/ve-01-closure.md)).
- [CONTINUITY.md](CONTINUITY.md): estado, decisões do operador e próximas ações para retomar em outra sessão.

## Ondas implementadas (22/11/2026, sessão 2)
- **W0 (baseline + correções funcionais)** — fechada. Fechamento: [evidence/ve-00-closure.md](evidence/ve-00-closure.md) (baseline e suíte) e [evidence/ve-w0b-closure.md](evidence/ve-w0b-closure.md) (orçamento provado, publicação fail-closed, perfil econômico no snapshot, rótulos honestos). Ledger: [evidence/WORK-LEDGER-W0B.md](evidence/WORK-LEDGER-W0B.md).
- **W1 (UX da proposta)** — fechada. Fechamento: [evidence/ve-w1-closure.md](evidence/ve-w1-closure.md). Ledger: [evidence/WORK-LEDGER-W1.md](evidence/WORK-LEDGER-W1.md).
  - Menu: **Início · Criar vídeo · Vídeos · Tendências e ideias · Desempenho · Biblioteca** (+ Configurações no rodapé).
  - Vídeo: **8 áreas como rotas** (`/studio/panel/videos/{id}/{area}`), links de servidor com `aria-current`, áreas somente leitura sem controle falso; rotas antigas (`/roteiro`, `/preview`, `production-runs`) preservadas.
  - Configurações: **7 seções**, com páginas próprias para Estratégia editorial, Marca e estilo e Produção e orçamento (reusando os cartões de Canais); **Biblioteca** virou destino próprio.
  - Aprovado ≠ Publicado; "Criar vídeo deste tema" preserva o canal; Fontes dizem "registrada ≠ extraída ≠ verificada".
- **W2+ autorizada pelo operador** ("seguir até a última atividade"); VE-01 implementada e W4.0/W4.1/W4.2/W3.1 portadas. S8 portado. Nenhuma frente em execução.

## Frentes portadas (sessão 3, 22/11/2026 — nada commitado)

| Frente | Onde | Estado |
|---|---|---|
| VE-01 (overlay: contrato + compilador) | checkout principal | **implementado** (T01–T25, T27, T26 verdes após regenerar contrato; T28 = suíte completa pendente) — [evidence/ve-01-closure.md](evidence/ve-01-closure.md) |
| W4.0 (IDs de cena estáveis) | portado do worktree `ve-w4-0-scene-ids` | **portado e verde** (36 passed) — [evidence/ve-w4-0-closure.md](evidence/ve-w4-0-closure.md) |
| W3.1 (porta `MediaSearch` + Pexels) | portado do worktree `ve-w3-media` | **portado e verde** (115 passed) — [evidence/ve-w3-1-closure.md](evidence/ve-w3-1-closure.md) |
| W4.1 (edição de cena com CAS + idempotência) | portado do worktree `ve-w4-1-edit` | **portado e verde** (66 passed; suíte completa 2 failed pré-existentes / 3186 passed) — [evidence/ve-w4-1-closure.md](evidence/ve-w4-1-closure.md) |
| W4.2 (reabrir aprovado, ADR-002) | portado do worktree `ve-w4-2-reopen` | **portado e verde** (36 passed) — [evidence/ve-w4-2-closure.md](evidence/ve-w4-2-closure.md) |
| S1/S2/S7 (saneamento de arquitetura) | portado do worktree `ve-arch-saneamento` | **portado e verde** (61 passed) — [evidence/ve-s1-s2-s7-closure.md](evidence/ve-s1-s2-s7-closure.md) |
| S8 (congelar seleção de provider) | portado do worktree `ve-s8-freeze` | **portado e verde** (150 passed) — [evidence/ve-s8-closure.md](evidence/ve-s8-closure.md) |
| S6 (portas `MediaSearch`, `SemanticChecker`, `TenantContext`) | — | aguarda VE-01/W3.1 fecharem (mesmo `application/ports.py`) |

**ADRs escritos:** [ADR-001](docs/adr/ADR-001-render-plan.md) (render plan),
[ADR-002](docs/adr/ADR-002-reabrir-video-aprovado.md) (reabrir aprovado),
[ADR-003](docs/adr/ADR-003-isolamento-por-organizacao.md) (isolamento por organização).
