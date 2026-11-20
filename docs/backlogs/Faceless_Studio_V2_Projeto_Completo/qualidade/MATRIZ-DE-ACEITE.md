# Matriz de aceitação e qualidade transversal

| Gate | Cenário | Esperado |
|---|---|---|
| Segurança | Empacotar e escanear | ZIP não contém `.env`, tokens, DB backup, storage, `.git` |
| Robustez | Duas chamadas `produce` com mesma key | Uma execução apenas |
| Robustez | Crash após provider call antes de commit | Recovery sem duplicação indevida; resultado reconciliado quando possível |
| Humano | Worker alcança script review | Libera worker e persiste `WAITING_HUMAN` |
| Versões | Editar cena após aprovar render | Invalida QA e aprovação afetados |
| Research | URL fora do ar | Falha tratada, não inventa fonte |
| Long-form | Vídeo alvo 480s | Duração estimada medida contra TTS real e tolerância configurável |
| Media | Regenerar um beat | Reusa artefatos não afetados |
| Publicação | Crash/retry de resumable upload | Reconciliar sessão e remote ID antes de repetir |
| Acesso | Tenant A consulta vídeo/asset de B | 403/404 e nenhuma informação sensível vazada |
| Custos | Previsão excede hard limit | Etapa paga não inicia e mostra alternativa |
| UI | Run bloqueado ou parcialmente falho | Próxima ação clara sem APIs manuais |

## Definition of Done global

- [ ] Contrato e migration versionados; compatibilidade checada.
- [ ] Testes com fakes/stubs mais integração com infraestrutura relevante.
- [ ] Casos de concorrência/falha documentados e ensaiados.
- [ ] Custo, permissões, auditoria e secrets revisados.
- [ ] Estados vazios, loading, erro, retry e sucesso em UI.
- [ ] Observabilidade com correlação fim a fim.
- [ ] Rollback/feature flag testado.
- [ ] Documentação e runbook atualizados.
- [ ] Evidência de teste anexada ao card.

## Indicadores de operação

Taxa de vídeos publicados, custo total e por minuto, taxa de sucesso por estágio, tempo de ciclo, retries, % revisões, reaproveitamento de assets, custo de reprocessamento, incidentes de upload duplicado, métricas de desempenho do YouTube quando autorizadas e disponíveis.
