# Roteamento — Google somente

Aliases são os nomes usados no ambiente do operador, verificar disponibilidade real antes de delegar. Não presumir disponibilidade, equivalência de custo ou automação de seleção. Carbon High como orquestrador inicial se disponível; separar executor/reviewer por sessão/agente real sem contexto de autoaprovação. Não chamar API externa para trocar modelo.

| Tarefa | Executor preferido | Escalonamento | Review obrigatório |
|---|---|---|---|
| REC-00.01–02 | Neon High | Carbon High para inventário mecânico | Carbon High independente |
| REC-01.01–03 | Hydrogen Medium | Carbon High | Neon High |
| REC-02.01–02 | Hydrogen Medium | Carbon High | Neon High |
| REC-02.03–04 | Hydrogen Medium | Carbon High | Neon High |
| REC-02.05 | Flash 3.8 | Hydrogen Medium | Carbon High |
| REC-03.01–02 | Flash 3.8 | Hydrogen Medium | Carbon High; Neon para segurança/contratos críticos |
| REC-03.03 | Hydrogen Medium | Carbon High | Neon High |
| REC-04.01–02 | Flash 3.8 | Hydrogen/Carbon High | Carbon High independente |
| REC-04.03–04 | Carbon High | Neon High | Neon High independente; operador para audiovisual |

Flash ausente → Hydrogen; se reviewer exigido não disponível, BLOCKED_REVIEW. Não substituir Neon obrigatório por auto-review Flash. Modelos diferentes não garantem independência: sessão/revisor separado, acesso ao diff e evidência. Se ambiente não permite delegação, executar tarefa compatível e parar no gate solicitando troca; não fingir. Até duas tentativas por modelo; escalonar com contexto reduzido e achado concreto. Salvar checkpoint se quota próxima da reserva (15% semanal/10% 5h sugeridas). Registrar saldo inicial/final se observável, modelo real, tarefas aceitas, sem estimar tokens a partir de percentuais. Nenhum overage automático.
