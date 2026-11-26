# MASTER PROMPT — V4 Recovery: qualidade comprovada >= 9/10

**Status:** REABERTO / NO-GO para merge. Base revisada: `72438e9ea215bbec12bd350d8c2606ca62bc7d94`. Main protegida: `be0c463edc55ff567f9149d26c8fd350c803d745`. A execução INT-01–07 anterior está registrada em INT-07-FINAL-REPORT.md e no histórico Git; não representa homologação atual.
**Entrada única da campanha:** este arquivo. Executar somente quando o operador iniciar expressamente a campanha na develop. A autorização de execução técnica contínua não inclui merge, publicação, despesas, mudanças destrutivas ou aprovação humana.

## 1. Missão e precedência

Entregar o produto funcionando, não maximizar número de classes ou testes. Ler AGENTS.md, instruções do checkout, README.md, RECOVERY-REVIEW.md, RECOVERY-BACKLOG.md, QUALITY-GATES.md, QUALITY-RUBRIC.md, MODEL-ROUTING.md, EXECUTION-BACKLOG.md e especificações V4/GAI originais. Este master e o backlog REC prevalecem sobre pausas técnicas e status antigos dos prompts INT, sem relaxar critérios originais. Não reiniciar INT-01–07 indiscriminadamente. Mapear lacunas V4/GAI ainda abertas e tratar dentro das ondas REC; alterações de escopo exigem operador.

## 2. Preflight

Confirmar branch develop, SHA remoto/local, git status, preservar alterações do usuário, verificar divergência; sem reset destrutivo, force push ou overwrite. Isolar DB/volume/porta, credenciais ausentes, egress negado quando viável, orçamento API zero, publicação efetivamente desabilitada e prova de descartabilidade. Não tocar DEV/PRD. Registrar runtimes, ferramentas e capacidade efetiva de delegar modelos. Não presumir suporte de Antigravity a troca automática. Se reviewer independente obrigatório não puder ser executado, registrar BLOCKED_REVIEW e parar dependentes. Não simular modelo nem review.

## 3. Execução orientada a dependências

| Onda | Arquivo | Executor | Reviewer independente |
|---|---|---|---|
| REC-00 | prompts/REC-00-audit.md | Neon High | Carbon High |
| REC-01 | prompts/REC-01-financial-safety.md | Hydrogen Medium | Neon High |
| REC-02 | prompts/REC-02-av-media.md | Hydrogen Medium / Carbon High | Neon High |
| REC-03 | prompts/REC-03-studio-pipeline.md | Flash 3.8 / Hydrogen Medium | Carbon High |
| REC-04 | prompts/REC-04-pilot-release.md | Flash 3.8 / Carbon High | Neon High + operador |

As atividades e roteamento detalhado estão em RECOVERY-BACKLOG.md e MODEL-ROUTING.md. Executar automaticamente apenas tarefas elegíveis e autorizadas. Uma tarefa/slice por vez; antes de escrever, provar falha ou lacuna com teste/inspeção reproduzível. Reutilizar componentes existentes; evitar adicionar serviço paralelo. Após implementação, teste focado, consumidor real, negativo, evidências, review independente sobre o diff/SHA, rubrica e decisão. Só então commit atômico e próxima tarefa. Correção de qualquer achado invalida review do diff afetado; revisar novamente. Nunca baixar limiar para passar.

## 4. Gate obrigatório de qualidade

Aplicar QUALITY-RUBRIC.md: nota técnica >=9.0/10, cada dimensão aplicável >=9.0, 100% dos gates obrigatórios da atividade satisfeitos, zero achados críticos/altos não resolvidos, sem regressão e revisão independente no SHA correspondente. Média não compensa bloqueio. Não arredondar 8.95 para 9; não dar nota sem evidência; UNKNOWN não é PASS. A nota é avaliação rastreável por rubrica, não métrica científica do modelo. O agente executor não aprova a si próprio. P0/P1 obrigatório aberto impede homologação; opcionais somente DEFERRED com autorização explícita. Uma etapa de auditoria não ganha crédito por funcionalidade que ainda não executou.

Estados: PENDING, IN_PROGRESS, IMPLEMENTED, VERIFIED, BLOCKED, BLOCKED_REVIEW, DEFERRED, AWAITING_HUMAN_REVIEW. VERIFIED exige gate completo; não confundir teste sintético, smoke, integração e piloto. Não marcar todos os itens concluídos só por relatório verde. Em conflito entre relatório e código, código/artefato/teste observado prevalece.

## 5. Controle e retomada

Manter EXECUTION-STATE.md, EXECUTION-LOG.md, MODEL-USAGE.md, TRACEABILITY-MATRIX.md, evidence/ e FINAL-REPORT.md dentro deste diretório; criar se ausentes. Por tarefa: ID REC + V4/INT/GAI, base/HEAD, modelo real, comandos/exit codes, diff, testes, call sites, artefatos/hashes, custo, score por dimensão, achados do reviewer, rollback e próximo item. Evidências sanitizadas sem segredos, links relativos reproduzíveis; não commitar MP4 grandes, armazenar localmente em diretórios exclusivos e versionar manifesto. Se não houver acesso ao artefato, não alegar verificação. Persistir estado após cada gate. Não inventar timestamps, logs, notas, IDs ou modelos.

## 6. Modelos e orçamento

Somente Google; Carbon High orquestra em janelas curtas, Flash em tarefas mecânicas, Hydrogen para implementação complexa, Neon para arquitetura e revisão crítica. Confirmar aliases reais disponíveis; sem Flash, preferir Hydrogen. Duas tentativas por modelo no máximo antes de escalonar; falha persistente = BLOCKED, não loop. Medir saldo semanal/5h quando disponível; reserva sugerida 15% semanal e 10% janela curta, operador pode alterar. Sem leitura verificável, marcar UNKNOWN e não inferir consumo. Não habilitar overage ou API paga. Quota insuficiente/indisponibilidade: salvar checkpoint e encerrar com segurança. Não ler todo repo em cada tarefa, reutilizar matriz.

## 7. Invariantes e encerramento

Não duplicar ProductionCoordinator, Registry, BudgetGuard, RenderPlan, cache ou AssetRepository; sem SDK Google no Core, sem CI/CD, sem nova SPA, sem Finder nesta recuperação. Sem publicação/credenciais/chamada paga. Preferir desabilitar capacidades não prontas a entregar stubs como reais. Não mascarar falhas renomeando teste ou relaxando asserts; mudança de contrato precisa justificativa, compatibilidade, teste negativo e aprovação de reviewer.
Último gate: regressão completa no checkout limpo após última mudança funcional, browser isolado, vertical slice 60–90s e piloto 5–8min com artefatos/métricas reais, comparação controlada e aprovação humana pendente até manifestação real. Não emitir 9/10 final para qualidade audiovisual sem revisão do operador. Permitir TECHNICAL GO / AWAITING HUMAN REVIEW apenas se todos os gates técnicos obrigatórios forem satisfeitos; caso contrário NO-GO / BLOCKED. Não fazer merge. Main só por autorização separada do operador.

Inicie REC-00 agora, continue conforme dependências e quality gates, sem pedir aprovação em cada tarefa técnica elegível. Pare em bloqueio obrigatório não resolvido e entregue o estado.
