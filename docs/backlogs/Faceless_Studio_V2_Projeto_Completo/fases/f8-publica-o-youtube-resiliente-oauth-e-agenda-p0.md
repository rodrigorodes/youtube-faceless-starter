# F8 — Publicação YouTube resiliente, OAuth e agenda (P0)

**Prioridade:** P0  
**Dependências:** F1: locks e intents; F6: QA/aprovação; F7: pacote de publicação. Hardening pode começar após F1, em paralelo às fases visuais.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** efetuar uploads apenas aprovados e sem duplicações em falhas concorrentes.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F8-01` | Mapear fluxo atual: aprovações, claims, lease, resumable upload, sessão, recovery, workflow `03-publish-approved.json`. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-02` | Implementar `PublicationIntent` transacional com versão de vídeo e media checksum imutáveis. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-03` | Claim por lease+fencing; sessão de upload salva de forma segura; reconciliar remoto antes de iniciar sessão nova. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-04` | Controlar repetição, timeout, crash, lease expirado, upload parcial e callback atrasado; preservar remote video ID. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-05` | Validar canal autorizado, scopes e erro OAuth; mensagens de reconexão claras; não expor secrets nem URLs resumable. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-06` | Definir política de publicação privada por padrão; agendamento e visibilidade pública requerem regras explícitas/consentimento. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-07` | Reabilitar workflow automático apenas depois de testes de falha e concorrência passarem. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F8-08` | Teste manual de ponta a ponta em canal de teste, incluindo reconciliação depois de falha artificial. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

nenhum upload sem render/QA/aprovação válidos; concorrência e restart não criam dupla publicação em cenários ensaiados; operador vê estado verdadeiro e URL final.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Zero publicação duplicada em cenários de falha testados; publicação sem aprovação sempre bloqueada.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
