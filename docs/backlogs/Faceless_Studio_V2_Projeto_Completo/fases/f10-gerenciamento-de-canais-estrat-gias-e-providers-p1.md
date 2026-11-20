# F10 — Gerenciamento de canais, estratégias e providers (P1)

**Prioridade:** P1  
**Dependências:** F0: segredos; F2: UI; F1: budget do run. Pode avançar em paralelo a F3–F8.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** administrar perfis sem editar `.env` e sem trocar código.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F10-01` | CRUD de canais/projetos, arquivamento, estratégia, idioma, público e pilares. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-02` | `ChannelProfile` versionado: narrativa, duração, identidade visual, voz, áudio, thumbnail e CTA. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-03` | Tela de providers com capabilities, custo estimado, rate limits, disponibilidade e teste de conexão. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-04` | Profiles econômicos e roteamento de provider por tarefa/custo/qualidade; fallback controlado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-05` | Budget por canal/produção, limites hard/soft e painéis de custo honesto. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-06` | Associar canal YouTube e status OAuth, sem mostrar secrets. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F10-07` | Manter configs sensíveis em vault/secret store, não no `Project.config` devolvido ao browser. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

adicionar canal, configurar estratégia/provedores/orçamento e iniciar vídeo sem alterações manuais no servidor; configuração versionada e auditável.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Novo canal configurado via UI e produção iniciada sem editar código nem .env.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
