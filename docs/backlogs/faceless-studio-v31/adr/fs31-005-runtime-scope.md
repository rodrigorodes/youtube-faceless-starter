# ADR — Escopo mono-operador e SaaS

**Status:** proposto, requer aprovação em F00 ou antes da tarefa dependente.
**Gaps:** G04/G10
**Dono/revisor:** a designar.

## Decisão proposta

V3.1 é mono-operador com múltiplos canais; equipe/BYOK modelados não implicam isolamento operacional. SaaS Runtime separado e obrigatório antes de múltiplos clientes.

## Alternativa rejeitada

Manter caminhos divergentes ou adicionar configuração paralela apenas para simplificar a interface. Reavaliar alternativas específicas no discovery quando evidência exigir.

## Pendências

Definir responsável e gate comercial; decidir quais controles de equipe/BYOK ficam visíveis.

## Critério para aceitar

Sem promessa de isolamento; release SaaS bloqueada até testes de acesso cruzado e secret store.

Registrar impacto, migração, compatibilidade, decisão final e data antes de implementar.
