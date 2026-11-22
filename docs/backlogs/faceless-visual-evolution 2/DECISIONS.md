# Decisões consolidadas · revisão 3

Esta revisão prevalece sobre a documentação V1 arquivada e sobre instruções contraditórias do plano recebido. Histórico permanece intacto. Status: decisões de projeto para implementação futura.

| ID | Decisão | Consequência |
|---|---|---|
| UX-01 | Canal como contexto; vídeo como unidade de trabalho | Menu não representa DAG de produção |
| UX-02 | Abas completas dentro do vídeo: Fontes/roteiro, Narração, Cenas, Composição, Qualidade, Publicação, Produção | Preservar capacidades da V1 e manter contexto de vídeo |
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

## Correção de cobertura UX-08
A navegação global mantém Tendências/ideias, Desempenho e Biblioteca. Settings expõe sete áreas completas conforme UX-SPEC e FEATURE-COVERAGE-V3. Não remover funcionalidades existentes para simplificar. Fontes são etapa explícita; pesquisa autônoma não é assumida.

## Decisões do operador · 22/11/2026, sessão 3 (itens AUSENTES)
Autorização: implementar os oito itens ausentes do [ABSENT-ITEMS-ANALYSIS](evidence/ABSENT-ITEMS-ANALYSIS.md). Três decisões de arquitetura foram tomadas pelo operador; as demais o executor decide com default declarado (ordem das ondas, migrações aditivas, nomes de rota, ADR P-04 já aceito em D-B).

| ID | Decisão | Consequência |
|---|---|---|
| D-E | **ISO:** hoje acessa **apenas o operador**; preparar para acesso com papéis no futuro, **sem complexidade agora**. | `organization_id` entra como camada de dados (migração aditiva, default de um tenant) e o escopo por conta fica atrás de porta/flag. Sessão real e RBAC **não** são implementados nesta rodada; o desenho não deve impedir a adição posterior. |
| D-F | **QA semântico:** manter **"não verificado" honesto** como padrão; core **extensível** a outras estratégias. | Porta `SemanticChecker` com implementação `NotVerified`; heurística ou LLM pago entram como adapters novos, sem mudar o contrato nem exibir selo falso. |
| D-G | **Mídia:** seguir com **Pexels**; extensível a outros provedores grátis ou pagos. | Porta `MediaSearch` com adapter Pexels; novos provedores entram por adapter, com licença e proveniência obrigatórias no core. Pago exige gate de orçamento quando existir. |

Regra transversal: **extensibilidade por porta, não por condicional espalhado.** Nenhum dos três itens pode virar `if provider == "pexels"` ou `if mode == "llm"` no meio do fluxo.

## Regra de arquitetura · 22/11/2026, sessão 3 (instrução do operador)
**Toda ferramenta do core deve poder ser conectada a diferentes tipos de fornecedor. Clean Architecture e contrato com a ferramenta são obrigatórios.**

Como isso se aplica no código que já existe:

| Camada | Regra | Onde |
|---|---|---|
| Domínio | Não conhece fornecedor. Só política, capacidade e custo | `domain/provider.py` (`ProviderKind`, `route_provider`, `Availability`) |
| Aplicação | Depende de **porta** (`Protocol`), nunca de SDK ou nome de fornecedor | `application/ports.py` (40+ portas) |
| Composição | Registra implementação por `(porta, nome)` e declara capacidade, custo, qualidade e disponibilidade | `composition.py` (`register`, `_provider_implementations`, `ProviderImplementation`) |
| Adaptador | Único lugar que cita o fornecedor e fala com o SDK/HTTP | `adapters/*` |
| Seleção | Rota por capacidade + perfil econômico, com auditoria e reavaliação explícita; sem fallback silencioso | `ProviderRouter`, `ProviderService.route` |

Consequência para os itens novos: `MediaSearch` e `SemanticChecker` entram como **porta + adaptador + entrada de catálogo + capability + auditoria**, nunca como `if` no meio do fluxo. Nenhum nome de fornecedor pode aparecer em `domain/` ou `application/` (exceto o que é o próprio produto, como YouTube).
