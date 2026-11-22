# ADR — Identidade YouTube

**Status:** proposto, requer aprovação em F00 ou antes da tarefa dependente.
**Gaps:** G02/G03
**Dono/revisor:** a designar.

## Decisão proposta

Resolver grant autorizado a partir do destino do projeto. Upload via caso de uso protegido comum, n8n orquestra. Analytics usa autorização/scopes pertinentes. Legado somente com política explícita e validação de identidade.

## Alternativa rejeitada

Manter caminhos divergentes ou adicionar configuração paralela apenas para simplificar a interface. Reavaliar alternativas específicas no discovery quando evidência exigir.

## Pendências

Definir migração de tokens legados, política de perfil sem destino e reconciliação de resultado ambíguo.

## Critério para aceitar

Token de B nunca publica em A; revogação bloqueia; teste de renovação e idempotência.

Registrar impacto, migração, compatibilidade, decisão final e data antes de implementar.
