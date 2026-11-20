# ADR-001 — DarkPlanner somente em adapter de voz

**Status:** Proposto (aguarda avaliação do time).

## Contexto
O starter já usa uma porta `Voice` síncrona com `PiperVoice` e provider registry. Adicionar integração diretamente no domínio ou em `RunRender` aumentaria acoplamento e risco de regressão.

## Decisão
Adicionar `DarkPlannerVoiceAdapter` à infraestrutura; registrar factory na composition root; preservar contrato atual no MVP. Particularidades da API ficam no adapter/client; recursos assíncronos e capacidades opcionais devem ser modelados em porta auxiliar, sem contaminar `Voice`.

## Consequências
**Prós:** substituição por configuração, testes com fake, segregação de segredos, fallback explícito, menor refactor. **Trade-offs:** potencial conversão de formato e overhead de I/O; para APIs assíncronas, trabalho adicional de persistência/checkpoint será obrigatório.

## Regras verificáveis
1. Nenhum `import darkplanner` no domínio e casos de uso.
2. `RunRender` não recebe dependência concreta DarkPlanner.
3. `register('voice', 'darkplanner', ...)` ocorre somente na composition root.
4. Testes de contrato passam em Piper e adapter fake.
5. A chamada comercial só é habilitada após discovery e testes de integração.
