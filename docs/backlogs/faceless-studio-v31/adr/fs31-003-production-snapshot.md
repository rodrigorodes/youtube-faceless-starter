# ADR — Configuração efetiva e snapshot

**Status:** proposto, requer aprovação em F00 ou antes da tarefa dependente.
**Gaps:** G06/G05
**Dono/revisor:** a designar.

## Decisão proposta

Resolver configuração criativa antes de efeitos e persistir no run ou por referência imutável; mesma entrada para voz e render. Segurança, preço e permissões seguem dinâmicos.

## Alternativa rejeitada

Manter caminhos divergentes ou adicionar configuração paralela apenas para simplificar a interface. Reavaliar alternativas específicas no discovery quando evidência exigir.

## Pendências

Definir schema, atomicidade, política de runs legados, retry/regenerate e cache de assets.

## Critério para aceitar

Mutação durante TTS não muda run; novo run resolve atual; sem segredo persistido.

Registrar impacto, migração, compatibilidade, decisão final e data antes de implementar.
