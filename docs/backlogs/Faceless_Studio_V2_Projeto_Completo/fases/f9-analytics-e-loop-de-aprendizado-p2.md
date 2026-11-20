# F9 — Analytics e loop de aprendizado (P2)

**Prioridade:** P2  
**Dependências:** F8: publicações e IDs remotos; F10: identidade de canal.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** usar dados reais para melhorar as próximas produções.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F9-01` | Conectar dados observados às versões de briefing, roteiro, embalagem e publicação. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F9-02` | Coletar métricas autorizadas (views, CTR/impressões quando disponíveis, watch time e retenção conforme API/permissão). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F9-03` | Dashboard por canal, vídeo, pilar e período; mostrar quando dados ainda não estão disponíveis. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F9-04` | Criar insights com evidência e nível de confiança, separando observação de hipótese. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F9-05` | Recomendar temas/formatos e mudanças de hook ou pacing para revisão humana. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F9-06` | Histórico de experimentos thumbnail/título conforme recursos realmente oferecidos pelo YouTube. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

insights têm métrica, janela temporal e fonte; nenhum desempenho é inventado; sugestões não reconfiguram o canal automaticamente.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Recomendações com métrica, período, origem e hipótese explicitados.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
