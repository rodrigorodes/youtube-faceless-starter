# F6 — Editor visual, preview e QA (P1)

**Prioridade:** P1  
**Dependências:** F5: timeline e assets; F1: estágios e gates.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** permitir revisão e correção localizada sem conhecer ferramentas técnicas.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F6-01` | Player + timeline por cena/beat com thumbnails, waveforms opcional e navegação por timestamp. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-02` | Editor de narração, legenda e referência visual por cena (MVP: edição por formulário, não NLE completo). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-03` | Trocar asset/voz, regerar trecho e renderizar nova versão com status. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-04` | QA técnico: codec/dimensões, áudio, duração, picos/silêncio, legendas, artefatos, frame preto. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-05` | QA editorial: claims, consistência, pronúncia, ritmo, safe areas, repetição visual; checks heurísticos primeiro. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-06` | Mostrar severidade `blocking/warning/info`, evidências e ação de correção. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-07` | Aprovação final requer `render_id`/checksum mais recente e relatório QA compatível. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F6-08` | Testes de regressão visual e de mídia com fixtures curtas e longas. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

operador encontra cena ruim pelo preview, edita e re-renderiza versão atualizada; versão aprovada é exatamente a versão passível de publicação.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Render aprovado corresponde exatamente ao artefato publicado; QA bloqueante verificável.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
