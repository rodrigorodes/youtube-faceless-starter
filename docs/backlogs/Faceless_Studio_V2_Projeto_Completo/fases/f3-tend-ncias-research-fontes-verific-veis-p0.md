# F3 — Tendências → research → fontes verificáveis (P0)

**Prioridade:** P0  
**Dependências:** F0 e F1: persistência, contratos e estados da produção.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** transformar uma tendência em briefing com evidências, e não apenas texto.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F3-01` | Criar `ContentBrief` versionado com `trend_id`, hipótese de interesse, público, objetivo e referências. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-02` | Ao selecionar tendência, transportar IDs de evidências, timestamps e URLs para research; nunca confiar em claims de vídeos de terceiros sem checagem. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-03` | Criar `ResearchPort` com estratégias fonte oficial, feeds e busca permitida; fallback para fontes manuais. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-04` | Canonicalizar URLs, deduplicar, gravar `SourceSnapshot`, status de licença e proveniência. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-05` | Avaliar fonte por data, reputação, pertinência e suporte a claims; rejeitar fonte inacessível sem inventar conteúdo. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-06` | Criar UI de fontes (`aprovar`, `descartar`, `adicionar`, `inspecionar claims`). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-07` | Corrigir rotulagem de `regionCode=US` para EUA; `Global` somente como agregação real com origem explícita. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F3-08` | Observar custos/cotas YouTube e impor throttle/cache. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

tendência selecionada gera briefing rastreável; pesquisa gera fontes efetivamente utilizáveis pelo roteiro; falhas exibem ação humana possível; região refletida corretamente.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

100% das claims testáveis com origem e provenance; nenhuma fonte inacessível inventada.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
