# ADR — Precedência e ciclo de estilos

**Status:** proposto, requer aprovação em F00 ou antes da tarefa dependente.
**Gaps:** G07/G08/G15
**Dono/revisor:** a designar.

## Decisão proposta

Separar seleção inteira de patch. Override tipado com allowlist, reset remove patch, listas substituem; validar configuração final. Arquivamento preserva referências históricas e impede novas seleções.

## Alternativa rejeitada

Manter caminhos divergentes ou adicionar configuração paralela apenas para simplificar a interface. Reavaliar alternativas específicas no discovery quando evidência exigir.

## Pendências

Definir aplicação de patch de canal quando base do vídeo muda, pin de versão e revisão transacional se desvincular.

## Critério para aceitar

Isolamento A/B, reset, conflito otimista e histórico íntegro.

Registrar impacto, migração, compatibilidade, decisão final e data antes de implementar.
