# F5 — Motor audiovisual, mídia e montagem dinâmica (P1)

**Prioridade:** P1  
**Dependências:** F4: roteiro, storyboard e versões de artefatos.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** aumentar retenção com variação visual e custo controlado.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F5-01` | Introduzir `VisualBeat` (scene_id, start/end, asset_kind, reference, transition, provenance, license). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-02` | Permitir 1:N beats por cena e mídia `stock`, `AI image`, `AI clip`, `diagram`, `screen capture` fornecida, `text animation`. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-03` | Criar `MediaProviderPort` e capability registry (`SUPPORTED`, `EXPERIMENTAL`, `UNAVAILABLE`); Veo atualmente deve aparecer indisponível até implementação validada. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-04` | Reusar stock primeiro onde licença permite, imagens geradas quando agregam, clipes IA apenas em momentos-chave. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-05` | Storyboard define duração, beat, objetivo visual, safe area, asset fallback e proporção. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-06` | Evoluir render FFmpeg para beats múltiplos, trilha por camadas, crossfades, áudio, legendas e transições. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-07` | Regeração granular por beat/cena; cache por conteúdo e versão do provider; invalidation. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-08` | Auditoria de licença, uso de marca/pessoa e proveniência; QA de assets e falhas de download. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F5-09` | Perfis de custo `economy`, `balanced`, `premium` com fallback condicionado ao budget. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

render long-form usa beats múltiplos em pelo menos cenas configuradas; troca de asset não exige gerar novo roteiro; fontes/licenças permanecem auditáveis; output MP4 passa QA objetivo.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Diversidade visual e custo por minuto mensuráveis; reprocessamento por beat demonstrado.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
