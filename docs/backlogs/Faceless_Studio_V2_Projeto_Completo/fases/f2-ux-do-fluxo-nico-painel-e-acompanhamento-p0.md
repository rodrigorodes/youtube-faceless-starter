# F2 — UX do fluxo único, painel e acompanhamento (P0)

**Prioridade:** P0  
**Dependências:** F1: contrato de ProductionRun/status/eventos.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** tornar o produto operável sem conhecimento de API ou pipeline.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F2-01` | Desenhar mapa de navegação, wireframes e estados vazios/erros. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-02` | Criar wizard `Novo vídeo`: canal, tema, briefing, duração, estilo, idioma, budget. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-03` | Botão primário `Produzir vídeo` chamando Production Coordinator. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-04` | Página de execução com stepper, próxima ação, tempo decorrido, custo estimado/real e eventos. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-05` | Ações `Pausar`, `Continuar`, `Cancelar`, `Tentar novamente`, `Revisar` condicionadas a permissões/estado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-06` | Unificar lista `Vídeos` por estado de negócio e filtros `precisa de mim`, `em andamento`, `concluído`, `falhou`. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-07` | Mover IDs/traces/model usage para diagnóstico avançado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F2-08` | Acessibilidade (teclado, contraste, feedback), responsividade, testes E2E com operador não técnico. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

usuário cria um vídeo, acompanha produção e resolve pendências pelo painel; nenhum passo manual escondido nos docs é necessário no fluxo feliz.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Fluxo feliz executável por UI sem Swagger/n8n; todos os estados têm ação contextual.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
