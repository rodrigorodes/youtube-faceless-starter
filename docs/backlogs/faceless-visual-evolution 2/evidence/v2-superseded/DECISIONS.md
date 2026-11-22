# Decisões consolidadas · revisão 2

Esta revisão prevalece sobre a documentação V1 arquivada e sobre instruções contraditórias do plano recebido. Histórico permanece intacto. Status: decisões de projeto para implementação futura.

| ID | Decisão | Consequência |
|---|---|---|
| UX-01 | Canal como contexto; vídeo como unidade de trabalho | Menu não representa DAG de produção |
| UX-02 | Conteúdo, Edição, Publicação | QA contextual e histórico secundário |
| UX-03 | Revisar roteiro é preferência | Um pipeline com pausa, sem dois modos incompatíveis |
| UX-04 | Padrões por canal, snapshot por execução | Mudanças no canal não alteram vídeos em andamento automaticamente |
| UX-05 | Editar sem gerar; gerar explicitamente | Autosave não dispara chamadas pagas |
| UX-06 | Prévia vinculada à revisão | Nunca mostrar render antigo como atualizado |
| UX-07 | Aprovar e publicar são ações distintas | Aprovação amarra render/checksum e publicação valida destino |
| DOM-01 | Não criar segundo Project/Channel | Mapear FK project/profile existente |
| DOM-02 | Usuários participam da conta | Autorizar recursos no backend, não apenas filtrar UI |
| DOM-03 | Publicado não equivale a aprovado | Separar estado editorial, execução e publicação |
| PROV-01 | N providers por capacidades | Portas estáveis, adapter por implementação |
| PROV-02 | Voz e orçamento não mudam silenciosamente | Fallback controlado e auditado |
| VE-D1 | Estender Shot, sem novo Layer paralelo | Preservar RenderPlan canônico |
| VE-D2 | Versionar mudanças incompatíveis | A limpeza histórica NÃO autoriza apagar dados atuais; inventariar e migrar/preservar |
| VE-D3 | Overlays no grafo da cena base | Um renderer e cache seletivo |
| VE-D4 | Paridade funcional sem exigir digest legado idêntico | Manter determinismo do novo contrato e invalidar cache incompatível |
| VE-D5 | Reusar entrada RenderSpec existente | Confirmar representação de layers antes de implementação |
| VE-D6 | Camadas como caminho normal, sem flag obrigatória | Sem overlay mantém comportamento funcional; flags apenas por necessidade fundamentada |
| VE-D7 | Validar produto no container renderer/Postgres | Testes offline do protótipo não substituem validação de produção |

## SaaS e escopo
A exclusão total de multi-tenancy da V1 é substituída por duas entregas: UX solo/equipe e fundação de isolamento. Clientes independentes só podem ser atendidos após critérios de autorização/isolamento da fase ISO. Billing, quotas comerciais e administração enterprise continuam fora do MVP. Membership atual é por organização; permissões por canal só entram com modelo/validação explícitos, nunca implícitas em query string.

## Aprovação, publicação e edições
Nova revisão exige artefato/QA/aprovação próprios. Uma publicação já concluída mantém seu registro histórico e referência ao render publicado; não “despublicar” por editar rascunho. Uma publicação pendente fica obsoleta se conteúdo/destino/metadados autorizados mudarem. Não substituir arquivo de vídeo já publicado por uma atualização local. Duplicar para outro canal cria vídeo independente e nova revisão contextual.

## Autorizações históricas
Relatos de limpeza, commits ou chamadas reais em outros documentos são registros históricos, não permissões atuais. Implementar o escopo autorizado na sessão sem pedir novamente aprovação de ações já autorizadas. Não extrapolar para deploy, publicação YouTube ou cobranças reais.
