# V4-01 — Provider Extensibility
Status: CONCLUÍDO. Dependências: 00.
Relatório de Entrega: [V4-01-REPORT.md](V4-01-REPORT.md)

## Atividades
- [x] V4-01.01 — Evoluir ProviderKind e Capability. Adicionado ProviderKind.VIDEO ('video') e novas Capabilities (VIDEO_GENERATE, VOICE_NEURAL, TEXT_REASONING) com REQUIRED_CAPABILITY tipado em domain/provider.py.
- [x] V4-01.02 — Revisar ports. Introduzidos VideoModel(Protocol) e NeuralVoice(Voice, Protocol) em application/ports.py com runtime_checkable.
- [x] V4-01.03 — Normalizar resultados. Contrato VideoResult normalizado com data, mime, duration_s, dimensões, usage, licença e proveniência.
- [x] V4-01.04 — Registrar formatos e limites. Criado ProviderLimits com duration min/max, aspectos suportados, formatos e max_chars, integrado a ProviderImplementation e ProviderCard.
- [x] V4-01.05 — Expandir roteamento econômico. Roteamento de ProviderKind.VIDEO suportado sob EconomicProfile (ECONOMY, BALANCED, PREMIUM) sem quebra de retrocompatibilidade.
- [x] V4-01.06 — Health checks. Probes LocalProviderProbe e HttpReachableProbe validados para novos providers locais e remotos.
- [x] V4-01.07 — Congelar seleção por run. frozen_provider_selection preserva seleções incluindo portas de vídeo e áudio em retries de DAG.
- [x] V4-01.08 — Fallback explícito. Roteador suporta exclusão explícita auditada de candidato falhado sem downgrade silencioso.
- [x] V4-01.09 — Classificar erros. Hierarquia semântica tipada (ProviderTransientError, ProviderQuotaExceeded, ProviderBudgetBlocked, ProviderPermanentError).
- [x] V4-01.10 — Integrar ledger. BudgetGuard e CostGuard asseguram teto rígido de $0.00 sem chamadas externas pagas.
- [x] V4-01.11 — Testes de conformidade. tests/test_v4_provider_extensibility.py comprova extensão completa via FakeExtensibleProvider sem alterar o Core.
- [x] V4-01.12 — Configuração Studio. BUILD_KINDS e ProjectConfig em application/config.py, KIND_LABELS em panel_channels.py e implementações em composition/providers.py.

## Aceite
Piper e FFmpeg continuam funcionando; adapter fake comprova extensão sem mudança no domínio (246 testes aprovados, exit code 0).

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-01 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Complemento GAI-03/04/09
Registrar candidatos Google API com capabilities e disponibilidade reais, Text/Image opcional, billing distinto de assinatura e custo guardado antes de chamada; manter OpenCode Bridge e Registry. Não representar Flow assistido como API. Ver [GAI](../GAI-EXECUTION-PLAN.md).
