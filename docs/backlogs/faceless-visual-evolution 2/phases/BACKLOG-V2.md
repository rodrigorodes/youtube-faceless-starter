# Backlog executável · revisão 3

Todos os itens abaixo são propostos. Evidência do ZIP é baseline estático, não aceite técnico.

| ID | Entrega e arquivos candidatos | Dependência | Aceite |
|---|---|---|---|
| BASE-01 | Inventário de rotas, dados, contratos e V3.1; revisar imagem Docker | — | Matriz implementado/parcial/ausente, baseline reproduzível |
| BASE-02 | Resolver estado de orçamento e publicação antes de efeitos pagos | BASE-01 | Guard efetivo comprovado por teste; config desligada não tratada como proteção |
| UX-01 | Navegação canal/vídeo em shell_v3 e panel_videos | BASE-01 | Contexto preservado; aprovado não aparece em publicados |
| UX-02 | Novo vídeo + snapshot de padrões do canal | UX-01 | Tema/roteiro; override local não muda canal; rascunho sem gasto |
| UX-03 | Workspace com todas as áreas de produção dentro do vídeo | UX-02 | Mesmo vídeo e seleção de cena entre abas; prévia com versão |
| ISO-01 | Mapear ownership/memberships e fronteiras | BASE-01 | Plano de migração e matriz de permissões revisados |
| ISO-02 | Enforce backend + jobs + assets/cache/segredos | ISO-01 | Negativas A/B sem vazamento, inclusive referências indiretas |
| VE-01 | Shot base/overlay e compilador | BASE-01 | Cobertura base, ordem, intervalos; determinismo e paridade funcional |
| VE-02 | Compositor FFmpeg e cache | VE-01 | Overlay aparece só na janela; áudio/legendas/duração preservados |
| VE-03 | MediaSearch/candidatos e router | VE-02, BASE-02 | Licença/proveniência/custo; fallback válido sem cena vazia |
| VE-04 | Presets/legendas/motion existentes | VE-02 | Paridade sem novos campos; controles por capacidade |
| VE-05 | QA técnico e semântico opcional | VE-02 | Técnico bloqueante; ausência semântica explícita |
| VE-06 | Troca de mídia e prévia seletiva | VE-03, VE-05 | Invalida afetadas/final; aprovação antiga bloqueada |
| EDIT-01 | Texto/add/remove/reorder com revisão | UX-03 | IDs estáveis, CAS, conflito, idempotência e auditoria |
| EDIT-02 | Regeneração de voz/timing por cena | EDIT-01, BASE-02 | Duração medida; nenhuma geração no autosave; identidade preservada |
| EDIT-03 | Mídia/estilo integrados ao editor | EDIT-02, VE-04, VE-06 | Substituir e atualizar sem navegar fora do vídeo |
| EDIT-04 | Histórico/restaurar + resultados obsoletos | EDIT-03 | Restaurar cria revisão; job antigo não promove nova revisão |
| PUB-01 | Checklist + aprovação + intenção/destino | EDIT-03, VE-05 | Render/checksum e permissão no servidor; metadados revalidados |
| PUB-02 | Retomada/retry/estado de publicação | PUB-01 | Falha não perde rascunho; duplo clique não duplica efeito |
| QA-01 | E2E, teclado, mobile e métricas de jornada | EDIT-04, PUB-02 | Cenários de qa/ACCEPTANCE aprovados |
| RELEASE-01 | Gate de clientes independentes | QA-01, ISO-02 | Isolamento e custos comprovados; migrações ensaiadas |

## Ordem sugerida
BASE → UX-01/02/03 para validar a experiência → VE-01–06 e EDIT por dependências → PUB → QA. ISO pode ser desenvolvido como trilha de fundação, mas é bloqueante para RELEASE multi-cliente. Não exigir VE-06 completa para desenhar/testar o shell com dados controlados. Integração de escrita exige contratos/invalidadores prontos.

## Estratégia de implantação e migração
1. Inventariar dados reais; não reutilizar autorização histórica de limpeza.
2. Mapeamento project/profile e organização: detectar órfãos, identidades ambíguas e vínculos sem owner; bloquear atribuição automática ambígua.
3. Aplicar mudanças aditivas e backfill validado antes de constraints obrigatórias. DDL consolidado é gerado; editar migrações e exportar pelo fluxo existente.
4. Não alterar publicação histórica ao migrar estados visuais. Projeção da UI deve usar fonte de publicação real.
5. Render/cache: versionar fingerprints incompatíveis e evitar falso hit; não prometer rollback para formato que código antigo não lê.
6. Implementar e testar cada fatia; manter fonte antiga preservada até confirmar conversão. Registrar reversibilidade/limites por migração.

## Definition of done por tarefa
Requisito ligado a cenário; diff pequeno; teste unitário/contrato e integração apropriados; execução no ambiente correto; falhas pré-existentes separadas; docs e status atualizados; nenhum resultado simulado apresentado como real. Sem execução paga/publicação real para validar interface. Testes externos só no escopo explicitamente autorizado.

## Adições obrigatórias da revisão 3
| ID | Entrega | Dependência | Aceite |
|---|---|---|---|
| COV-01 | Inventário ponta a ponta da FEATURE-COVERAGE-V3 | BASE-01 | Nenhuma capacidade anterior omitida sem decisão |
| SET-01 | Canais e estratégia completa | COV-01 | Campos persistidos/consumidos e independência por canal |
| SET-02 | Marca, estilos, voz, legendas, música e motion | SET-01, VE-04 | Overrides/previews reais e grupos suportados identificados |
| SET-03 | Orçamento, perfis, providers por tarefa e fallback | BASE-02, COV-01 | Provider executado coincide com escolha; limites efetivos |
| SET-04 | Conexões, catálogo/modelos, YouTube e BYOK | SET-03 | Credencial usada pertence à conta; segredos nunca expostos |
| SET-05 | Equipe/papéis, preferências e avançado | ISO-01 | CRUD autorizado, estado real, config sanitizada |
| FLOW-01 | Fontes e fact-check explícitos no vídeo | COV-01 | URL registrada não é tratada como evidência processada |
| FLOW-02 | Etapas completas e controles de produção | UX-03, EDIT-03 | Usuário acha voz, mídia, composição, QA e publicação sem perder vídeo |
| KEEP-01 | Tendências/pilares, analytics e biblioteca | COV-01 | Fluxos anteriores preservados; ideia → vídeo mantém canal |

COV-01 precede a implementação visual. SET-01–05, FLOW-01/02 e KEEP-01 fazem parte do aceite completo; não são removíveis como “detalhes avançados”. Reaproveitar entregas V3.1 já existentes em vez de duplicá-las.
