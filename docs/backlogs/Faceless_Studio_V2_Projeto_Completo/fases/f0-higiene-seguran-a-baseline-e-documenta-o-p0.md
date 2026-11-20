# F0 — Higiene, segurança, baseline e documentação (P0)

**Prioridade:** P0  
**Dependências:** Nenhuma. É bloqueante para habilitar distribuição e CI.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** estabilizar a base antes de adicionar novas funcionalidades.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F0-01` | Rotacionar tokens/chaves OAuth/API encontrados no pacote; revisar acesso e histórico de distribuição. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-02` | Criar `scripts/package-starter.sh` com allowlist de código/docs, sem `.env`, `credentials/`, `storage/`, backups, `.git/` ou dados pessoais. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-03` | Adicionar secret scanning no CI e teste que inspeciona ZIP gerado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-04` | Gerar inventário das rotas, estados, providers, workflows, capacidades e gaps; marcar adapters `working/experimental/disabled`. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-05` | Reconciliar `README` e docs com comportamento executável; arquivar materiais históricos. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-06` | Criar baseline de testes, migrations, segurança, custo, fixture de 8 min e relatório de cobertura; corrigir CI. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F0-07` | Definir flags e rollout progressivo para V2. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

pacote sem segredos; credenciais comprometidas substituídas; docs refletem executável; CI consistente; baseline reproduzível.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

100% dos arquivos de distribuição verificados sem secrets; CI verde e documentação atualizada.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
