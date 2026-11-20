# F4 — Motor editorial long-form e aprovação de roteiro (P0)

**Prioridade:** P0  
**Dependências:** F3: ContentBrief/SourceSnapshot; F1: gate de aprovação.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** roteiro projetado para duração/retensão, e não apenas resolução horizontal.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F4-01` | Expandir briefing com `target_duration_seconds`, público, voz, ritmo, estrutura, linguagem e restrições. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-02` | Separar prompt short vs long; long deve gerar estrutura por blocos/chapters, hook, contexto, desenvolvimento, payoff/CTA. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-03` | Definir estimativa configurável de palavras/minuto e duração por cena, validada contra velocidade real do TTS. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-04` | Criar roteiro em duas passagens: outline/chapter plan e script de cenas com referências. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-05` | Validar continuidade, redundância, duração estimada, claims e ausência de invenção; aproveitar gate de fact-check atual. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-06` | Versionar scripts e criar aprovação humana atrelada a hash/versão. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-07` | Tela para editar/regerar cenas, inspecionar fontes e fazer override justificado. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-08` | Edição invalida somente outputs downstream dependentes; testar propagação de invalidation. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F4-09` | Criar teste de roteiro de aproximadamente 480 s cobrindo 2–4 temas/estilos. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

modo long de 8 min fornece outline e cenas com durações compatíveis; usuário aprova roteiro antes de mídia paga; edição parcial invalida outputs afetados, não deixa fact-check de versão antiga passar.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Roteiro alvo de 480 s com tolerância definida por perfil; aprovação vinculada a versão.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
