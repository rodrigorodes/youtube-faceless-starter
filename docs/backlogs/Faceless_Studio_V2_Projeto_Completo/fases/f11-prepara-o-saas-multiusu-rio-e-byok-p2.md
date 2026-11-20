# F11 — Preparação SaaS, multiusuário e BYOK (P2)

**Prioridade:** P2  
**Dependências:** F0: segurança; F8: publicação; F10: gestão de canais e provedores; baseline de operação.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** permitir operação hospedada com isolamento e faturamento, somente após MVP estável.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F11-01` | Introduzir `Organization`, `Workspace`, `User`, `Role`, `Membership`, isolando `Project`/Video e storage por tenant. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-02` | Autenticação por sessão/OIDC, RBAC com `owner/editor/reviewer/viewer` e auditoria. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-03` | Isolamento de registros, storage, jobs, filas, custos, secrets e logs por tenant; testes de vazamento. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-04` | BYOK por tenant e provider; criptografia, rotação, autorização por uso, masks, revogação. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-05` | Metering e quotas de plataforma vs custo direto das APIs do cliente; modelo de cobrança transparente. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-06` | Billing com controle de créditos, uso, limites, falha de pagamento e webhooks idempotentes (provedor a escolher). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-07` | Deploy com API/worker separados, assets em object storage, observabilidade, backups/restore e retenção. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-08` | Revisar termos de n8n, modelos e stock para uso SaaS, mais direitos autorais, privacidade e YouTube policies vigentes. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F11-09` | Escalonamento de workers, rate limit por tenant/provider, antifraude, SLO e plano de incidentes. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

teste cross-tenant não acessa conteúdo/credenciais; custo de API do cliente é separado da taxa da plataforma; deploy pode recuperar-se sem inconsistência relevante; termos comerciais/licenças revisados.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Cross-tenant isolation testado; BYOK auditável; metering reconciliado e restore ensaiado.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
