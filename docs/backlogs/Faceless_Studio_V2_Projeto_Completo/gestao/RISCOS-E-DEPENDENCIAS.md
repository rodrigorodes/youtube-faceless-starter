# Riscos de execução e mitigação

| Risco | Impacto | Mitigação / gate |
|---|---|---|
| Secrets em pacotes e backups | Crítico | F0 antes de distribuição; rotação e scan automático |
| Duplicação de publicação | Crítico | Intent e reconciliação de upload; F8 não habilitado antes de fault injection |
| Invalidação incorreta de versões | Alto | ArtifactVersion + dependency graph + testes F4/F6 |
| Custo excessivo de vídeo de IA | Alto | Custo por estágio, profiles e hard caps; preferir stock/FFmpeg onde adequado |
| Provider ausente ou instável | Alto | Capability registry, fallback, timeout e filas |
| Direitos de mídia inadequados | Alto | Licença/proveniência por asset e gate de revisão |
| Trabalho longo preso ao HTTP | Alto | Worker queue/lease/checkpoint e UX assíncrona |
| API YouTube OAuth/restrições | Alto | Healthcheck, escopos, conta de testes e comportamento de reconexão |
| Acoplamento ao n8n | Médio/alto | Core guarda estado e n8n apenas na borda |
| Isolamento multi-tenant | Crítico para SaaS | Testes adversariais de RBAC, DB, storage, cache e logs |
| Escopo exagerado de editor | Alto | Editor por cenas e formulário primeiro, sem NLE completo |

**Regra:** risco crítico bloqueia release de uso externo até evidência de mitigação.
