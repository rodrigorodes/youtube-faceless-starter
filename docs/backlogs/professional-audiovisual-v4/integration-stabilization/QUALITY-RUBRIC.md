# Rubrica de qualidade 9/10 — gate objetivo e independente

Nota mínima solicitada: **9,0/10** por atividade técnica verificada e por onda; mínimo também de 9,0 em cada dimensão aplicável. Sem arredondamento para atingir o limiar. Pontuação não substitui gates G0–G7 e critérios originais. Não confundir nota qualitativa anterior de 7,2 com medição desta rubrica.

| Dimensão | Peso | Evidência para pontuar |
|---|---:|---|
| Correção funcional e integração | 25% | requisito, consumidor real, sucesso e negativo, artefato/estado observado |
| Arquitetura e simplicidade | 20% | dependências, ausência de duplicação, interfaces compatíveis, reutilização, rollback |
| Testes e regressão | 20% | comandos/exit code, testes relevantes, fronteira real, casos de falha, golden/contratos conforme escopo |
| Segurança, orçamento e confiabilidade | 20% | identidade/escopo, falha fechada, orçamento, CAS/retry/restart e licença aplicáveis |
| Evidências e operação | 15% | SHA, logs/hashes, métricas observadas, UX/operabilidade e limitações, rastreabilidade |

Para cada dimensão aplicável, reviewer atribui 0–10 com justificativa por evidência:
- 0: inexistente/contradito; 1–4: stub, mock não rotulado, defeito grave ou evidência insuficiente.
- 5–6: parcial, integração/negativos ausentes.
- 7–8: funciona em parte, mas critérios ou evidências relevantes ainda pendentes.
- 9: todos os critérios aplicáveis satisfeitos por evidência verificável, nenhum achado crítico/alto; pequenas melhorias opcionais documentadas.
- 10: além de 9, validação adicional proporcional e robustez comprovada; não exigir perfeição ou refatoração especulativa.

A média ponderada = soma(nota × peso aplicável)/soma(pesos aplicáveis). N/A só se não pertinente e justificado pelo reviewer; UNKNOWN/BLOCKED não vira N/A. Para auditoria documental, julgar completude/rastreabilidade da auditoria, não aprovação de funcionalidades. Sem reviewer independente real ou evidência insuficiente, score não validado, status BLOCKED_REVIEW. Registrar nota de executor apenas como autoavaliação sem poder de aprovação.

## Bloqueios absolutos, mesmo com nota alta
- P0 ou P1 obrigatório aberto; gate obrigatório não executado/reprovado; segurança financeira/isolamento/licença comprometidos.
- Teste relaxado para mascarar defeito, métrica sintética apresentada como real, log/artefato ausente apresentado como observado, review/modelo simulado.
- Capability falsa, regressão funcional, persistência/CAS/restart insuficiente quando exigido, incompatibilidade não autorizada.
- Falta de regressão final completa, browser obrigatório, comparação real ou revisão humana conforme gate de release.

Por tarefa, registrar tabela dimensão/peso/nota/evidência/achado, média exata, gates aplicáveis, reviewer/modelo efetivo, SHA/diff revisado, decisão e pendências. Revisar de novo após correção. Só marcar VERIFIED com >=9 em todas as dimensões aplicáveis, média >=9 e nenhum bloqueio. DEFERRED não conta como fechado; precisa autorização e não pode remover P0/P1 obrigatório. Homologação final audiovisual exige nota humana >=9/10 em inteligibilidade, composição, ritmo, relevância da mídia, áudio e legenda, com rubrica acordada e avaliação real; enquanto pendente, apenas GO técnico condicional se gates técnicos passarem. Não inventar avaliação humana.
